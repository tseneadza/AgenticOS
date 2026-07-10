"""Idle-vs-listening (Tony, 2026-07-09).

The orb was pinned "listening" because ``_capture_utterance`` set that state
for the WHOLE start-timeout window while merely armed for the wake word. It now
stays at the resting state (idle) until VAD actually detects directed speech.
These run headless: fake ``sounddevice`` + ``webrtcvad`` so no real mic/deps.
"""
import sys
import types

from osa_voice.pipeline import VoiceService


def _svc() -> VoiceService:
    return VoiceService(
        config={
            "enabled": True,
            "start_timeout_s": 0.15,
            "end_silence_ms": 60,   # -> 2 end-silence frames at 30 ms
            "min_rms": 0.0,         # skip the numpy RMS gate; VAD verdict stands
        },
        availability=lambda: (True, []),
    )


class _FakeStream:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n):
        return (b"\x00\x00" * n, False)  # content is irrelevant; VAD is faked


def _install_audio(monkeypatch, is_speech_seq):
    """Fake the two audio libs; ``is_speech_seq`` is the per-frame VAD verdict."""
    verdicts = list(is_speech_seq)

    sd = types.ModuleType("sounddevice")
    sd.RawInputStream = lambda **kw: _FakeStream()
    sd.query_devices = lambda: []

    wv = types.ModuleType("webrtcvad")

    class _Vad:
        def __init__(self, agg):
            pass

        def is_speech(self, frame, rate):
            return verdicts.pop(0) if verdicts else False

    wv.Vad = _Vad
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    monkeypatch.setitem(sys.modules, "webrtcvad", wv)


def test_armed_window_reads_idle_not_listening(monkeypatch):
    """Nobody speaks -> capture returns b"" and the state stays idle."""
    svc = _svc()
    _install_audio(monkeypatch, [])  # silence throughout
    assert svc._capture_utterance() == b""
    assert svc._state == "idle"  # was wrongly "listening" before the fix


def test_speech_flips_state_to_listening(monkeypatch):
    """Speech detected -> the state becomes listening for the utterance."""
    svc = _svc()
    _install_audio(monkeypatch, [True, True, True, False, False])
    assert svc._capture_utterance()  # captured something
    assert svc._state == "listening"
