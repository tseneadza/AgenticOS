---
name: osa-voice-in-mic-debugging
description: |
  Diagnose OSA voice-IN (microphone/STT) problems in AgenticOS — "OSA is deaf",
  "it can't hear me", wake word not responding, wrong/garbled transcripts, or
  capture that mysteriously goes silent. Use this skill BEFORE touching code
  whenever the user reports the mic side of voice misbehaving. Covers the
  wake-discard log (always check it first), background-media interference and
  the min_rms energy gate, PortAudio stream contention (diagnostics fighting
  the wake loop), the phone-mic segfault, level-calibration workflow, and the
  input_device knob.
compatibility: macOS, AgenticOS repo at ~/Codehome/AgenticOS, voice-IN deps installed
---

# OSA Voice-IN Mic Debugging ("it's deaf")

## The #1 rule: read the discard log before concluding anything

"OSA can't hear me" is almost never deafness. The wake loop logs every speech
burst it heard but did NOT act on:

```bash
grep -a "wake discard\|wake turn\|follow-up" /tmp/agenticos_sidecar.log | tail -20
```

Interpret what you see:

- **Your user's words appear in discards** → hearing is fine; the MATCHER
  refused. 2026-07-08 case: "Hello, Osa. Would you happen to have the time?"
  was discarded because matching demanded the wake word be the FIRST word.
  Fix aliases/matching in `osa_voice/pipeline.py` (`_WAKE_ALIASES`,
  `_match_wake`), not audio.
- **Garbled near-misses of the wake word** ("Osaka", "Ossa") → add to
  `_WAKE_ALIASES` or `voice.wake_aliases` in constitution.yaml.
- **Unrelated speech / media dialog** → the mic hears the ROOM, not the user
  (see background media below).
- **Hallucinated fragments** ("Thank you.", "Thanks for watching!", "Okay.",
  repeated) → whisper inventing text from noise/music. Classic sign of
  background audio with no real speech.
- **No discards at all while sounds are happening** → NOW suspect real
  capture failure (device, contention, permission).

## Background media (TV/music/video) — the silent killer

webrtcvad calls ANY speech "speech", including a TV across the room. Effects:
utterances never end (no silence → capture runs to the 30s cap), the user's
words get buried inside long media bursts, and whisper hallucinates.

Fix: the **energy gate** — `voice.min_rms` in constitution.yaml (default
0.02, live-calibrated 2026-07-08: arm's-length voice ≈7× a room TV at the
MacBook mic). Frames must be VAD-speech AND ≥ min_rms to count.
User farther away → lower it; noisy room → raise it.

## NEVER run diagnostic captures while the wake loop is on

Two PortAudio input streams (your test script + the wake loop) fight, and
BOTH can go silent or flaky — we chased a phantom "everything went quiet"
for several turns because of this. Procedure:

```bash
curl -s -X POST localhost:5130/api/osa/voice/wake -H 'Content-Type: application/json' -d '{"enabled":false}'
# ... run your mic tests ...
curl -s -X POST localhost:5130/api/osa/voice/wake -H 'Content-Type: application/json' -d '{"enabled":true}'
```

## Level-calibration workflow (prove what the mic hears)

Coordinate with the user ("say X in the next 10 seconds"), then:

```bash
cd ~/Codehome/AgenticOS && .venv/bin/python - << 'EOF'
import numpy as np, sounddevice as sd
sr = 16000
rec = sd.rec(int(10*sr), samplerate=sr, channels=1, dtype="int16"); sd.wait()
pcm = rec.flatten().astype(np.float32)/32768.0
print(f"rms={float(np.sqrt(np.mean(pcm**2))):.4f} peak={float(abs(pcm).max()):.3f}")
# speech at the mic: rms>0.01, peak>0.1 · room TV: ~0.005 · silence: <0.002
from faster_whisper import WhisperModel
m = WhisperModel("small", device="cpu", compute_type="int8")
segs,_ = m.transcribe(pcm, language="en", beam_size=1)
print("heard:", " ".join(s.text.strip() for s in segs) or "(nothing)")
EOF
```

Flatline (~0.001) while sound is happening = wrong device or broken capture,
NOT a matching problem.

## Devices: don't probe blindly

- `sd.query_devices()` lists inputs; the system default is usually right.
- 2026-07-08: opening a phone-as-mic device ("T-12PM128GB") at 16 kHz
  **segfaulted python** (status 139). Don't open random devices at forced
  sample rates. Pin the mic instead via `voice.input_device: "MacBook"`
  (name substring) in constitution.yaml.
- macOS mic permission belongs to the process that opens the stream (the
  sidecar's launcher). First live capture prompts; PTT working earlier in
  the session proves permission is fine.

## Quick checklist

- [ ] STEP ZERO: `system_profiler SPAudioDataType | grep -B3 "Default Input
      Device: Yes"` — is the expected mic even live? (2026-07-10: headphone
      inline mic silently became default; note input_device is now pinned
      to "MacBook" in constitution, so check the pin matches reality)
- [ ] Read `wake discard:` lines FIRST — deaf, or refusing?
- [ ] **Audio hardware just changed (headphones/AirPods/new mic)?** → new
      per-device drift profile; see osa-wake-word-tuning "Drift profiles
      are PER-MICROPHONE" (2026-07-10 incident)
- [ ] User's words present → fix matcher/aliases, not audio
- [ ] Hallucination fragments / media dialog → energy gate (`min_rms`)
- [ ] Wake loop OFF before any diagnostic capture
- [ ] Levels: user rms ≥ 0.01 at the mic; TV ~0.005; flatline = device issue
- [ ] Never open odd devices at 16 kHz; use `voice.input_device`
