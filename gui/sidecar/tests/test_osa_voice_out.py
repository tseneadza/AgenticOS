"""OSA voice-OUT (Phase 14d, 2026-07-08) — Piper TTS speaks replies + alerts.

Voice-OUT is the first real slice of 14d: OSA speaks aloud (chat replies +
announced proactive messages) via Piper, played through macOS ``afplay``. It's
independent of the mic stack (wake word / STT), so it ships before the full
loop and its mic-permission flow.

Everything here runs HEADLESS: Piper synthesis and ``afplay`` playback are
mocked, so no audio device or model file is touched. The on-device "does it
actually make sound" check is Tony's (he already auditioned en_GB-alan-medium
live during the build).
"""

from __future__ import annotations

import osa_voice
from osa_voice.pipeline import VoiceService

VOICE_CFG = {
    "enabled": True,
    "piper_voice": "en_GB-alan-medium",
    "voice_dir": "~/.agentic-os/voices",
    "speak_replies": True,
    "mute": False,
    "push_to_talk_only": True,
}


def _svc(**over):
    cfg = {**VOICE_CFG, **over}
    # mic stack absent, but the service under test is voice-OUT only
    return VoiceService(config=cfg, availability=lambda: (False, ["sounddevice"]))


# ═══════════════════════════════════════════════════════════════════════════════
# tts_available — Piper-only subset of the full dep probe
# ═══════════════════════════════════════════════════════════════════════════════

class TestTtsAvailable:
    def test_reports_missing_cleanly(self, monkeypatch):
        import importlib.util
        real = importlib.util.find_spec

        def _fake(name):
            return None if name == "piper" else real(name)

        monkeypatch.setattr(importlib.util, "find_spec", _fake)
        ok, missing = osa_voice.tts_available()
        assert ok is False
        assert "piper-tts" in missing

    def test_subset_of_voice_available(self):
        # tts deps ⊆ full voice deps (piper is in both maps)
        assert set(osa_voice.TTS_DEPS) <= set(osa_voice.OPTIONAL_DEPS)


# ═══════════════════════════════════════════════════════════════════════════════
# speak() gating — mute / empty / missing / success
# ═══════════════════════════════════════════════════════════════════════════════

class TestSpeakGating:
    def test_empty_text_refused(self):
        assert _svc().speak("   ", blocking=True)["ok"] is False

    def test_muted_refused(self):
        assert _svc(mute=True).speak("hello", blocking=True) == {
            "ok": False, "reason": "muted"}

    def test_missing_piper_refused(self, monkeypatch):
        monkeypatch.setattr(
            osa_voice, "tts_available", lambda: (False, ["piper-tts"]))
        out = _svc().speak("hello", blocking=True)
        assert out["ok"] is False
        assert "piper-tts" in out["reason"]

    def test_success_synthesizes_and_restores_state(self, monkeypatch):
        monkeypatch.setattr(osa_voice, "tts_available", lambda: (True, []))
        svc = _svc()
        spoke = []
        monkeypatch.setattr(svc, "_synthesize", lambda t: spoke.append(t))
        out = svc.speak("Systems nominal, Sir.", blocking=True)
        assert out == {"ok": True, "reason": None}
        assert spoke == ["Systems nominal, Sir."]
        # mic stack absent + this call done ⇒ resting state is 'disabled'
        assert svc.state()["state"] == "disabled"

    def test_synth_failure_is_soft(self, monkeypatch):
        monkeypatch.setattr(osa_voice, "tts_available", lambda: (True, []))
        svc = _svc()

        def _boom(_t):
            raise RuntimeError("piper exploded")

        monkeypatch.setattr(svc, "_synthesize", _boom)
        out = svc.speak("boom", blocking=True)
        assert out["ok"] is False
        assert "piper exploded" in svc.state()["last_error"]
        assert svc.state()["state"] == "disabled"  # not stuck on 'speaking'

    def test_non_blocking_returns_immediately(self, monkeypatch):
        monkeypatch.setattr(osa_voice, "tts_available", lambda: (True, []))
        svc = _svc()
        import threading
        gate = threading.Event()
        monkeypatch.setattr(svc, "_synthesize", lambda t: gate.wait(2))
        out = svc.speak("async", blocking=False)
        assert out == {"ok": True, "reason": None}  # didn't wait on _synthesize
        gate.set()


# ═══════════════════════════════════════════════════════════════════════════════
# _voice_path — model resolution
# ═══════════════════════════════════════════════════════════════════════════════

class TestVoicePath:
    def test_resolves_name_under_voice_dir(self, tmp_path):
        (tmp_path / "en_GB-alan-medium.onnx").write_bytes(b"x")
        svc = _svc(voice_dir=str(tmp_path))
        assert svc._voice_path() == tmp_path / "en_GB-alan-medium.onnx"

    def test_absolute_onnx_path(self, tmp_path):
        model = tmp_path / "custom.onnx"
        model.write_bytes(b"x")
        svc = _svc(piper_voice=str(model))
        assert svc._voice_path() == model

    def test_missing_returns_none(self, tmp_path):
        svc = _svc(voice_dir=str(tmp_path), piper_voice="does-not-exist")
        assert svc._voice_path() is None

    def test_empty_voice_returns_none(self):
        assert _svc(piper_voice="").state() is not None
        assert _svc(piper_voice="")._voice_path() is None


# ═══════════════════════════════════════════════════════════════════════════════
# _synthesize — Piper + afplay mocked (no audio device)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSynthesize:
    def _wire(self, monkeypatch, tmp_path):
        """Patch _load_voice (synth writes a stub WAV) + afplay + mark."""
        model = tmp_path / "v.onnx"
        model.write_bytes(b"x")

        class _FakeVoice:
            def synthesize_wav(self, text, wf):
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(22050)
                wf.writeframes(b"\x00\x00" * 100)

        svc = _svc(piper_voice=str(model))
        monkeypatch.setattr(svc, "_load_voice", lambda: _FakeVoice())
        return svc

    def test_synthesizes_and_plays_via_afplay(self, monkeypatch, tmp_path):
        import subprocess
        import osa_voice.pipeline as pl

        svc = self._wire(monkeypatch, tmp_path)
        monkeypatch.setattr(pl.shutil, "which", lambda p: "/usr/bin/afplay")
        played = {}

        class _Proc:
            def __init__(self, argv):
                played["argv"] = argv

            def wait(self):
                played["waited"] = True

            def poll(self):
                return 0

        monkeypatch.setattr(pl.subprocess, "Popen", lambda argv: _Proc(argv))
        svc._synthesize("Hello, Sir.")
        assert played["argv"][0] == "/usr/bin/afplay"
        assert played["waited"] is True
        assert "first_audio" in svc.state()["latency"]

    def test_muted_synthesizes_but_does_not_play(self, monkeypatch, tmp_path):
        import osa_voice.pipeline as pl

        svc = self._wire(monkeypatch, tmp_path)
        svc._mute = True
        called = {"popen": False}
        monkeypatch.setattr(
            pl.subprocess, "Popen",
            lambda *a, **k: called.__setitem__("popen", True))
        svc._synthesize("silent")
        assert called["popen"] is False

    def test_no_afplay_binary_is_soft(self, monkeypatch, tmp_path):
        import osa_voice.pipeline as pl

        svc = self._wire(monkeypatch, tmp_path)
        monkeypatch.setattr(pl.shutil, "which", lambda p: None)
        svc._synthesize("no player")  # must not raise


# ═══════════════════════════════════════════════════════════════════════════════
# mute mid-speech / barge-in
# ═══════════════════════════════════════════════════════════════════════════════

class TestBargeIn:
    def test_set_mute_cancels_playback(self, monkeypatch):
        svc = _svc()
        killed = {"terminated": False}

        class _Proc:
            def poll(self):
                return None  # still running

            def terminate(self):
                killed["terminated"] = True

        svc._play_proc = _Proc()
        svc.set_mute(True)
        assert killed["terminated"] is True

    def test_stop_speaking_no_proc_is_safe(self):
        _svc().stop_speaking()  # must not raise


# ═══════════════════════════════════════════════════════════════════════════════
# state() surfaces voice-OUT fields
# ═══════════════════════════════════════════════════════════════════════════════

class TestStateFields:
    def test_state_has_speak_replies_and_tts_ok(self):
        s = _svc().state()
        assert s["speak_replies"] is True
        assert "tts_ok" in s


# ═══════════════════════════════════════════════════════════════════════════════
# Route: POST /api/osa/voice/say
# ═══════════════════════════════════════════════════════════════════════════════

class TestSayRoute:
    def _client(self):
        from fastapi.testclient import TestClient
        from gui.sidecar.app import app as fastapi_app
        return TestClient(fastapi_app)

    def test_say_ok(self, monkeypatch):
        from osa_voice import get_service
        monkeypatch.setattr(
            get_service(), "speak",
            lambda text, **k: {"ok": True, "reason": None})
        r = self._client().post(
            "/api/osa/voice/say", json={"text": "Good evening, Sir."})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "spoke": "Good evening, Sir."}

    def test_say_muted_409(self, monkeypatch):
        from osa_voice import get_service
        monkeypatch.setattr(
            get_service(), "speak",
            lambda text, **k: {"ok": False, "reason": "muted"})
        r = self._client().post("/api/osa/voice/say", json={"text": "x"})
        assert r.status_code == 409
        assert "muted" in r.json()["detail"]

    def test_state_route_carries_speak_replies(self):
        s = self._client().get("/api/osa/voice/state").json()
        assert "speak_replies" in s
        assert "tts_ok" in s
        assert "enabled" in s


# ═══════════════════════════════════════════════════════════════════════════════
# Chat + proactive wiring — gated on enabled + speak_replies
# ═══════════════════════════════════════════════════════════════════════════════

class TestReplyWiring:
    def test_chat_speaks_reply_when_enabled(self, monkeypatch):
        from gui.sidecar.routes import api_osa
        from osa_voice import config as vcfg

        monkeypatch.setattr(
            vcfg, "voice_config",
            lambda: {"enabled": True, "speak_replies": True})
        spoke = []
        from osa_voice import get_service
        monkeypatch.setattr(
            get_service(), "speak", lambda t, **k: spoke.append(t))
        api_osa._maybe_speak_reply("Launching worldwise, Sir.")
        assert spoke == ["Launching worldwise, Sir."]

    def test_chat_silent_when_disabled(self, monkeypatch):
        from gui.sidecar.routes import api_osa
        from osa_voice import config as vcfg

        monkeypatch.setattr(
            vcfg, "voice_config",
            lambda: {"enabled": False, "speak_replies": True})
        spoke = []
        from osa_voice import get_service
        monkeypatch.setattr(
            get_service(), "speak", lambda t, **k: spoke.append(t))
        api_osa._maybe_speak_reply("should stay silent")
        assert spoke == []

    def test_proactive_speaks_only_announced(self, monkeypatch):
        from gui.sidecar import osa_proactive as pro
        from osa_voice import config as vcfg

        monkeypatch.setattr(
            vcfg, "voice_config",
            lambda: {"enabled": True, "speak_replies": True})
        spoke = []
        from osa_voice import get_service
        monkeypatch.setattr(
            get_service(), "speak", lambda t, **k: spoke.append(t))
        pro._speak_alert("worldwise just went down")
        assert spoke == ["worldwise just went down"]

    def test_proactive_voiceless_is_noop(self, monkeypatch):
        from gui.sidecar import osa_proactive as pro
        from osa_voice import config as vcfg

        def _boom():
            raise RuntimeError("config down")

        monkeypatch.setattr(vcfg, "voice_config", _boom)
        pro._speak_alert("must not raise")  # swallowed
