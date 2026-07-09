---
name: osa-voice-test-safety
description: |
  Write and maintain tests for AgenticOS voice code (osa_voice, voice routes)
  WITHOUT ever touching real audio hardware. Use whenever adding or changing
  voice tests, when a voice test hangs or times out, when a test passes
  standalone but fails in the full suite, or after installing/removing the
  optional voice deps. Covers the real-mic hang, singleton pollution via
  route tests, injecting fresh services, env-agnostic dep assertions,
  joining worker threads in tests, and keeping fakes in sync with new
  kwargs (syn_config).
compatibility: AgenticOS repo at ~/Codehome/AgenticOS, pytest + vitest
---

# OSA Voice Test Safety (no real audio, ever)

## The cardinal rule

A test that reaches `_capture_utterance` for real OPENS THE MICROPHONE:
best case it blocks ~6s, worst case it hangs the suite or triggers the
macOS permission prompt. 2026-07-08: a stale "stages are stubs" test
started capturing for real the moment the stages were implemented — the
suite timed out. Mock `_capture_utterance`, `_transcribe`, `_chat_turn`,
and `speak` in every pipeline test.

```python
svc = VoiceService(config={**DEFAULT_VOICE, "enabled": True},
                   availability=lambda: (True, []))
monkeypatch.setattr(svc, "_capture_utterance", lambda: b"\x00\x00" * 480)
monkeypatch.setattr(svc, "_transcribe", lambda audio, size=None: "hello")
monkeypatch.setattr(svc, "_chat_turn", lambda text: "reply")
```

Note `_transcribe` mocks need the `size=None` kwarg — the wake loop passes it.

## Route tests: NEVER the real singleton

Voice routes resolve `osa_voice.get_service()` at call time. In a FULL-suite
run, earlier tests (startup hooks) may have started the singleton against the
REAL Constitution — on Tony's machine that's `enabled: true` with deps
installed, so `set_wake(True)` through a route test would start a REAL wake
loop with a REAL mic inside pytest. This exact thing caused a
passes-standalone / fails-in-suite flake. Always inject:

```python
@pytest.fixture()
def disabled_svc(self, monkeypatch):
    import osa_voice
    svc = _svc(enabled=False)
    monkeypatch.setattr(osa_voice, "get_service", lambda: svc)
    return svc
```

(Works because routes do `from osa_voice import get_service` INSIDE the
handler — the module attribute is looked up per call.)

## Dep assertions must be env-agnostic

The mic deps are INSTALLED on Tony's Mac (2026-07-08) but may be absent in
CI. Never assert "deps are missing" or "deps are present" — assert
consistency: `ok is (not missing)`, and route shapes against
`voice_available()[0]`. Two tests broke the moment `pip install
-r requirements-voice.txt` ran; don't reintroduce that class.

Related install pitfall: webrtcvad 2.0.10 imports `pkg_resources`, removed
in setuptools 81+ → `setuptools<81` is pinned in requirements-voice.txt.
`voice_available()` uses find_spec and can say OK while the actual import
fails — verify with real imports after installing.

## Async workers: join before asserting

Wake turns run on a worker thread (`svc._turn_thread`). After driving
`_wake_loop` in a test, join it or assertions race:

```python
t = svc._turn_thread
if t is not None:
    t.join(timeout=2)
```

## Keep fakes in sync with kwargs

When `_synthesize` grew `syn_config=` (cadence), every `_FakeVoice` in
tests needed `def synthesize_wav(self, text, wf, syn_config=None)`. A new
kwarg on a mocked boundary = grep the tests for the fake and extend it.

## Frontend (vitest) equivalents

- AgentView's `stubFetch` 404s `/api/osa/voice/state` by default so the mic
  button stays hidden; pass `voiceState:` to light it up.
- Substring gotcha: `/api/osa/voice/state` does NOT contain
  `/api/osa/state` — but assert on filtered fetch calls, not
  `fetch.not.toHaveBeenCalled()`, because the orb legitimately polls
  voice state now.

## Run discipline

- Voice test files: `test_osa_voice_out.py`, `test_osa_voice_wake.py`,
  `test_phase14d_voice_scaffold.py` — run all three after ANY pipeline edit
  (fast, <1s, fully mocked).
- A voice test that takes >2s is touching something real — kill it and find
  the unmocked stage.
- Full suite to a file (45s shell caps): `pytest -q > /tmp/log; tail`.
