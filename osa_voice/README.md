# osa_voice — OSA voice pipeline (Phase 14d)

Local, offline voice shell for OSA: **openWakeWord** ("osa") → **faster-whisper**
(STT) → the existing `/api/osa/chat` agent turn → **Piper** (TTS). Runs
**in-sidecar** (design doc §2, option A) as a background service behind a hard
feature flag, with extraction to a separate process as the 14f escape hatch.

## Status: SCAFFOLD

| Real today | Stubbed (`NotImplementedError`, caught — never crashes the sidecar) |
| --- | --- |
| `voice:` config block in `config/constitution.yaml` + `DEFAULT_VOICE` merge (`core/constitution.py`) | `_wake_loop` — openWakeWord rolling-buffer detection |
| `voice_available()` dep probe (never raises, lists missing pip names) | `_capture_utterance` — sounddevice + webrtcvad end-of-speech |
| `VoiceService` state machine: `disabled / idle / listening / transcribing / speaking / error`, `start/stop/push_to_talk/set_mute/state`, `mark()` latency stamps | `_transcribe` — faster-whisper worker thread |
| Sidecar startup hook (`_start_osa_voice`) + routes `GET /api/osa/voice/state`, `POST /api/osa/voice/ptt`, `POST /api/osa/voice/mute` | `_synthesize` — Piper playback, barge-in, captions-first |

The utterance→agent contract is fixed (see `pipeline.py` module docstring):
transcribed text POSTs through the **same `/api/osa/chat`** turn as typed
input (shared graph, persona, model routing, 14b confirm flow), then the
`reply` is synthesized.

`voice.enabled` defaults **false** and `push_to_talk_only` defaults **true**
(design §9 Q3 unresolved — no always-listening until Tony opts in).

## On-device setup (Tony)

1. Install the optional extras (declared, not installed, by 14d):
   `.venv/bin/pip install -r requirements-voice.txt`
2. Flip the flag in `config/constitution.yaml`: `voice.enabled: true`.
3. Restart the sidecar. The `_start_osa_voice` hook logs the service state;
   `GET /api/osa/voice/state` should show `deps_ok: true`.
4. Grant the macOS microphone permission when prompted (first live run).
5. Test a turn: `curl -X POST http://127.0.0.1:5130/api/osa/voice/ptt`
   (until the implementation pass lands, this returns the
   `not_implemented` 409 — that's the expected skeleton behaviour).
6. Mute any time: `curl -X POST http://127.0.0.1:5130/api/osa/voice/mute -H 'Content-Type: application/json' -d '{"mute": true}'`.

## Latency budget (design §3.4, instrumented via `mark()`)

| Hop | Target |
| --- | --- |
| wake → listening | < 300 ms |
| end-of-speech → text | < ~1.5 s (small model) |
| text → first audio | < ~1 s (local reply; longer with Claude + tools) |

Captions render immediately so perceived latency stays low even when TTS lags.
