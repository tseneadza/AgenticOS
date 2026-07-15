---
name: osa-wake-word-tuning
description: |
  Tune, extend, or debug the "Osa" wake word and conversation mode in
  AgenticOS voice-IN. Use when the wake word misses the user, false-wakes on
  background audio, when adding wake aliases, adjusting the follow-up
  conversation window, changing speech cadence (length_scale), or auditioning
  voice changes. ALSO use whenever the user changes audio hardware —
  headphones/AirPods on or off, a new mic, USB/Bluetooth audio — and voice
  suddenly "stops hearing": drift profiles are PER-MICROPHONE and a device
  change silently invalidates the alias tuning (2026-07-10 incident). Covers
  the STT-gated architecture (why not openWakeWord), the alias-tuning loop,
  per-device drift profiles + the input_device pin, wake-word position
  matching, conversation-mode guards (echo, hallucination stoplist), all the
  constitution.voice knobs, and how to A/B audition cadence without
  restarting the sidecar.
compatibility: AgenticOS repo at ~/Codehome/AgenticOS, voice-IN live (Phase 14d)
---

# OSA Wake Word & Conversation Tuning

## Architecture (why it works this way)

openWakeWord ships NO "osa" model, so v1 is **STT-gated** (the design doc's
own §3.1 fallback): webrtcvad+energy-gate segments speech bursts →
whisper-TINY transcribes (fast) → `_match_wake` fuzzy-matches the leading
words. A trained openWakeWord "osa" model can replace the check later
without touching the loop. All in `osa_voice/pipeline.py`.

Two whisper models are cached per size: `wake_stt_model` ("tiny") for wake
checks, `stt_model` ("small") for command transcription. Follow-up commands
get RE-transcribed with the small model for accuracy.

## The alias-tuning loop (whisper never spells "Osa" one way)

1. User says the wake word; it's missed.
2. `grep -a "wake discard" /tmp/agenticos_sidecar.log | tail` — find what
   whisper actually wrote ("Osaka", "Ossa", "Oser"...).
3. Add it: `_WAKE_ALIASES` in pipeline.py (permanent, commit it) or
   `voice.wake_aliases: ["oser"]` in constitution.yaml (per-machine).
4. Restart the sidecar (kill ALL pids — see osa-sidecar-lifecycle) and
   re-enable wake (`POST /api/osa/voice/wake {"enabled":true}` — it's
   runtime-only, OFF after every restart BY DESIGN, §9 Q3).

## Drift profiles are PER-MICROPHONE (the headphones trap, 2026-07-10)

**STEP ZERO when voice misbehaves after ANY hardware change: check what mic
is actually live** — `system_profiler SPAudioDataType | grep -B3 "Default
Input Device: Yes"`. On 2026-07-10 we chased aliases and gate levels for
two rounds before discovering macOS had silently flipped input to the
headphones' inline cable mic ("External Microphone") — a dangling capsule
that produced drift, then chopped sentences, then noise-only fragments.
One `system_profiler` call at the start would have skipped all of it.
Symptom ladder of a bad/quiet mic, in worsening order: (1) new wake-word
drift spellings → (2) sentences chopped into fragments (severed tails show
as separate discards; OSA replies "you're trailing off") → (3) noise-only
discards ('You', 'Sigh.', 'Thank you.' — whisper's noise hallucinations).
Resolution: `voice.input_device: "MacBook"` pin (now ON in constitution).

Also: verify voice-OUT by EAR, not API — `POST /api/osa/voice/say` returns
`ok:true` on handoff regardless of audibility; pair it with a direct
`afplay /System/Library/Sounds/Glass.aiff` to isolate sidecar-vs-system.

**Every input device produces its own whisper drift set.** Aliases tuned
against one mic do NOT transfer to another: Bluetooth headsets run a
low-bandwidth telephony codec (HFP) that reshapes the audio whisper sees.

The incident: Tony put on Bluetooth headphones; macOS flipped the default
input to the headset mic; "Osa" — flawlessly matched for two days on the
MacBook mic — started arriving as **"O.S.", "Usa.", "Elsa.", "Oh, sir"**.
Every utterance was heard and discarded; the report was "OSA can't hear
me." The fix was four new aliases, not audio work.

Rules this encodes:

- **"Went deaf right after an audio-hardware change" → assume a NEW drift
  profile, not deafness.** Go straight to the discard log (rule #1 in
  osa-voice-in-mic-debugging); expect the wake word in unfamiliar
  costumes; extend the aliases (loop above). Tag additions with the device
  in the code comment so future tuning knows which mic taught us what.
- **`min_rms` is also per-mic.** 0.02 was calibrated on the MacBook mic at
  arm's length. A headset boom sits at the mouth (hotter) or a far-field
  mic sits colder — if the discard log shows NOTHING while the user
  speaks, recheck the energy gate with the level-calibration workflow
  before touching devices.
- **Prevention option — pin the mic:** `voice.input_device: "MacBook"`
  (name substring) makes capture ignore device switching entirely;
  headphones become output-only. Bonus: Bluetooth headsets DROP output
  quality when their own mic is active (HFP), so pinning input to the
  MacBook keeps OSA's voice hi-fi in the user's ears. Trade-off: walk away
  from the laptop and OSA hears the room, not the user. This is the
  user's call — ask, don't assume.

## Matching rules (2026-07-08, learned live)

- Wake word may sit ANYWHERE in the first 3 words: "Osa…", "Hey Osa…",
  "Hello, Osa…", "Excuse me, Osa…" all wake. Deeper mentions do NOT (guards
  against "tell me about the osa project" and background chatter).
- Matching is on per-word cleaned tokens (lowercase, alnum), but the command
  tail returns the ORIGINAL words — punctuation like "what's" survives.
- Bare "Osa" → spoken ack (`wake_ack`, "Yes?") → captures the command.
- Inline "Osa, do X" → runs X directly, no ack.

## Conversation mode (follow-up window)

After a reply FINISHES PLAYING, `followup_window_s` (8s) opens: the next
utterance needs no wake word; every reply renews the window. Guards — do not
remove them:

- **Echo guard:** the window opens only when playback ends, and follow-ups
  are refused while `_play_proc` is live — otherwise OSA's own speaker
  output becomes a command and it talks to itself.
- **Hallucination stoplist** (`_FOLLOWUP_STOPLIST`): whisper's stock noise
  outputs ("Thank you.", "Thanks for watching") are never commands. Note
  "Thank you." is TWO words — a word-count floor alone does not catch it.
- **≥2 words** for any wake-free command.

## Knobs (constitution.yaml → voice:)

| knob | default | meaning |
| --- | --- | --- |
| `length_scale` | 0.6 (Tony) | TTS cadence; 1.0=trained pace, lower=faster |
| `end_silence_ms` | 500 | silence that ends an utterance |
| `min_rms` | 0.02 | energy gate (see osa-voice-in-mic-debugging) |
| `followup_window_s` | 8 | conversation window; 0 = off |
| `wake_stt_model` | tiny | whisper size for wake checks |
| `wake_ack` | "Yes?" | spoken ack for bare wake word |
| `wake_aliases` | [] | extra whisper renderings |
| `input_device` | (unset) | mic name substring |

## Audition cadence WITHOUT sidecar restarts

Direct synthesis avoids the speak() dedupe window and config reloads —
label each option so the user can name a winner:

```bash
cd ~/Codehome/AgenticOS && .venv/bin/python - << 'EOF'
import wave, subprocess
from piper import PiperVoice, SynthesisConfig
v = PiperVoice.load("/Users/tonyseneadza/.agentic-os/voices/en_GB-alan-medium.onnx")
for ls in (0.7, 0.6, 0.5):
    p = f"/tmp/cadence_{ls}.wav"
    with wave.open(p, "wb") as wf:
        v.synthesize_wav(f"Option {ls}. Good morning, Tony.", wf,
                         syn_config=SynthesisConfig(length_scale=ls))
    subprocess.run(["afplay", p])
EOF
```

Steps of ~0.05 are inaudible — offer differences of 0.1+. Measure, don't
guess: WAV duration at 1.0 vs 0.85 vs 0.7 was 4.26s / 3.74s / 3.07s.

## Latency truths

- Most "voice lag" is the BRAIN, not the voice stack: turns that escalate to
  Claude add a cloud round-trip. Consider a local pin during voice sessions.
- Wake turns run OFF-loop (worker thread) so listening continues while OSA
  thinks/speaks — never make the loop block on `_chat_turn` again.
- Sentence-chunked playback gives first audio after ONE sentence's synth.
  ⚠️ Known bug (2026-07-08, unfixed): chunk gaps break barge-in — multiple
  replies can overlap. Fix sketch in CONTINUATION (speech generation counter).


## 2026-07-14: the echo-loop guard + the min_rms / small-model pairing

- **Conversation mode SELF-LOOPS on OSA's own voice unless echo-guarded.** With
  `followup_window_s > 0`, OSA's TTS reply is captured by the mic and — because
  the follow-up window needs no wake word — treated as the next command,
  cascading into OSA answering itself ("Tony, you're looping my replies back
  verbatim now"). The live "is audio playing NOW" check MISSES it: audio
  recorded DURING playback finishes just AFTER `_play_proc` clears. Fix
  (shipped): `voice.echo_cooldown_s` (1.0) + `_capture_was_echo(capture_start)`
  = playing-now OR `_last_reply_done >= capture_start - echo_cooldown_s`; stamp
  `_last_capture_start` at the top of `_capture_utterance`; gate in `_wake_loop`
  BEFORE `_match_wake` so BOTH the follow-up AND wake-match paths drop echo
  (logged as `echo discard:`). Cost: no voice barge-in without AEC. Raise
  `echo_cooldown_s` if a reverberant tail still self-triggers; lower it if a
  legit follow-up within ~1s feels laggy.
- **`min_rms: 0.012` only works PAIRED with `wake_stt_model: small`.** Lowering
  min_rms ALONE was reverted as noise-only in a prior session; on 2026-07-14 it
  captured Tony reliably ONLY once the wake model was upgraded tiny→small (tiny
  mangled "Osa" → "Ocer"/"also"/"Hi Mizzard"; small fixed recognition). Rule:
  if you drop `min_rms`, upgrade `wake_stt_model` too. New MacBook-mic drift
  alias added this session: "ocer".
