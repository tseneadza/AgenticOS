---
name: osa-voice-troubleshooting
description: |
  Diagnose and fix OSA voice-OUT (text-to-speech) in AgenticOS — Piper TTS spoken aloud via macOS afplay. Use this skill when OSA won't speak, speaks twice (double voice), speaks the wrong thing (e.g. reads internal text aloud), when enabling/disabling voice, choosing or changing the Piper voice, or wiring speech into new places. Covers the config path (constitution.voice.*), the enabled/speak_replies/mute gates, the dotted-path config mistake, the WebSocket-vs-POST silence bug, dedup for double voices, stripping text from speech, and how to verify audio when you can't hear it.
compatibility: macOS (afplay), AgenticOS repo, piper-tts installed, voice model in ~/.agentic-os/voices
---

# OSA Voice-OUT Troubleshooting (Piper TTS)

## Overview

Voice-OUT makes OSA speak its chat replies and announced proactive messages
aloud. Pipeline: reply text → Piper (`PiperVoice.synthesize_wav`) → temp WAV →
macOS `afplay`. It's independent of voice-IN (wake word / STT) and needs **no
mic permission**. Code lives in `osa_voice/pipeline.py` (`VoiceService.speak`),
gated by the Constitution's `voice:` block and wired into the chat routes via
`_maybe_speak_reply`.

## Config: where the knobs live (and the dotted-path trap)

`config/constitution.yaml` under `constitution.voice`:

```yaml
constitution:
  voice:
    enabled: true                    # master voice switch
    speak_replies: true              # speak chat replies + announced alerts
    piper_voice: "en_GB-alan-medium" # bare NAME under voice_dir, or .onnx path
    voice_dir: "~/.agentic-os/voices"
    mute: false                      # runtime output mute
    push_to_talk_only: true          # voice-IN only (wake word deferred)
```

**Common mistake:** "`constitution.voice.enabled`" is the *dotted PATH* to the
setting, not a literal key. Do NOT paste `constitution.voice.enabled: true` as a
new line. Edit the existing `enabled:` under the nested `voice:` block. After any
edit, **restart the sidecar** (see the `osa-sidecar-lifecycle` skill) — config is
read at startup, not hot-reloaded.

Defaults live in `core/constitution.py` `DEFAULT_VOICE` (the CODE default ships
`enabled: False`; the repo YAML may override it on this machine).

## Fast diagnosis

```bash
# 1. Is voice on and is Piper importable?
curl -s localhost:5130/api/osa/voice/state | python3 -m json.tool
#   enabled:true, speak_replies:true, tts_ok:true, mute:false  → should speak

# 2. Direct audition (bypasses chat entirely):
curl -s -X POST localhost:5130/api/osa/voice/say \
  -H 'Content-Type: application/json' -d '{"text":"Test one two three."}'
#   {"ok":true} means HANDED to a worker — NOT proof of sound. Listen.
```

`speak()` returns non-blocking: `{"ok":true}` fires before synthesis/playback.
So a success response never proves audio came out — **confirm by ear.**

## Symptom → cause → fix

### "OSA is silent in the app, but my curl /say or /chat spoke"
The app's chat is the **WebSocket** (`/api/osa/ws/chat`); the sync `POST` is only
a fallback. If speech is wired only into POST, the app is silent. Fix: call
`_maybe_speak_reply(reply)` in `osa_chat_ws()` too (after `_scrub_reply`, before
the `final` frame). See the `osa-chat-dual-path` skill. Confirm which path the
app used:
```bash
grep -iE "osa/ws/chat|osa/chat" /tmp/agenticos_sidecar.log | tail
```

### "Double voices at the same time"
The client opened the chat socket twice (dev StrictMode / reconnect / window) →
the same reply spoken twice at once; barge-in misses same-instant calls. Fix:
`speak()` de-dupes identical text within `_dedupe_window_s` (8s). It is NOT two
sidecars (the sidecar singletons via the port). Verify only one:
`pgrep -f gui.sidecar` → one pid.

### "It reads internal/system text aloud"
Small local models sometimes echo the injected brain-status suffix; and the
escalation clause ("Took Claude for that one.") shouldn't be spoken. Speech is
cleaned separately from the displayed reply:
- `_scrub_reply` strips brain-status echoes from the reply.
- `_maybe_speak_reply` additionally removes `_ESCALATION_CLAUSE` from the spoken
  text (kept in the displayed reply — the model badge already shows the brain).
To keep something visible but unspoken, strip it in `_maybe_speak_reply`, not in
`_scrub_reply`.

### "Nothing plays, no error"
- `tts_ok:false` → `pip install piper-tts` into `.venv` (voice-OUT needs only
  Piper, not the mic stack).
- No `.onnx` found → check `voice_dir` + `piper_voice`; download a model:
  `python -m piper.download_voices en_GB-alan-medium --download-dir ~/.agentic-os/voices`
- `mute:true` → `POST /api/osa/voice/mute {"mute":false}`.
- Audio session: a sidecar launched from a detached/background context may run
  `afplay` with no audible output. Launch it from the user's GUI session. See
  `osa-sidecar-lifecycle`.

## Changing OSA's voice

```bash
# List/download voices (Piper), then point the config at the NAME:
python -m piper.download_voices en_GB-northern_english_male-medium \
  --download-dir ~/.agentic-os/voices
# set constitution.voice.piper_voice to the bare name, restart sidecar.
```
Models (~60 MB `.onnx`) live OUTSIDE the repo in `~/.agentic-os/voices` — do not
commit them.

## Testing voice headlessly

Tests mock Piper + `afplay` so no audio device is needed
(`gui/sidecar/tests/test_osa_voice_out.py`). Patterns: patch
`osa_voice.tts_available`, patch `VoiceService._synthesize` or `_load_voice`,
patch `pipeline.subprocess.Popen` and `pipeline.shutil.which`. Assert dedup,
mute, clause-strip, and gating — never rely on real sound in CI.

## Key learnings (2026-07-08 live debug with Tony)

1. `{"ok":true}` from a non-blocking speak ≠ audio played. Verify by ear.
2. App silent + curl audible = WebSocket path missing the hook (dual-path).
3. Double voice = double socket open; dedup identical text in a window.
4. Keep internal/badge-redundant text in the DISPLAYED reply but out of SPEECH.
5. `constitution.voice.enabled` is a path — edit the nested key, then restart.
