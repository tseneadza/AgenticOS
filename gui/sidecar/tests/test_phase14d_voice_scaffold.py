"""Phase 14d tests — OSA voice pipeline SCAFFOLD (no live audio).

Everything runs with ZERO voice deps installed (they are optional extras in
``requirements-voice.txt``, deliberately absent from the base .venv): the dep
probe is exercised for real, the service state machine is driven with
injectable config/availability, routes go through TestClient the same way
``test_phase14a_osa.py`` does, and the ``_start_osa_voice`` startup hook is
called directly with the config cache pinned. Nothing here touches a mic,
an LLM, or MySQL.
"""
from __future__ import annotations

import asyncio
import importlib.util

import pytest

import osa_voice
from core.constitution import DEFAULT_VOICE, Constitution
from osa_voice import OPTIONAL_DEPS, voice_available
from osa_voice import config as vcfg
from osa_voice.pipeline import STATES, VoiceService


@pytest.fixture(autouse=True)
def _fresh_voice_state():
    """Cold singleton + config cache pinned to pure defaults for every test.

    Pinning the cache (14e precedent) means a future edit to Tony's live
    constitution.yaml — e.g. flipping ``voice.enabled`` on-device — can't
    silently change these tests.
    """
    osa_voice.reset_service()
    vcfg._config_cache = dict(DEFAULT_VOICE)
    yield
    osa_voice.reset_service()
    vcfg.reset_config_cache()


def _service(enabled: bool = True, ok: bool = True, missing=None, **knobs) -> VoiceService:
    """A VoiceService with injected config + availability (no probes)."""
    missing = missing if missing is not None else ([] if ok else ["openwakeword"])
    cfg = {**DEFAULT_VOICE, "enabled": enabled, **knobs}
    return VoiceService(config=cfg, availability=lambda: (ok, list(missing)))


# ═══════════════════════════════════════════════════════════════════════════════
# Feature flag — hard default off, pre-14d configs keep loading
# ═══════════════════════════════════════════════════════════════════════════════

class TestVoiceConfig:
    def test_repo_constitution_voice_in_stays_opt_in(self):
        """Voice-OUT is on (Tony, 2026-07-08), but the mic side stays safe.

        The real safety invariant isn't ``enabled`` — voice-OUT (TTS) has no
        mic/privacy cost and Tony turned it on. What MUST stay opt-in is
        voice-IN: ``push_to_talk_only`` true means no always-listening mic
        (design §9 Q3 unresolved), and the CODE default (`DEFAULT_VOICE`)
        still ships off for anyone who hasn't opted in.
        """
        from core.constitution import DEFAULT_VOICE

        assert Constitution.load().voice["push_to_talk_only"] is True
        assert DEFAULT_VOICE["enabled"] is False  # code default stays off

    def test_defaults_shape(self):
        cfg = Constitution().voice
        assert cfg == DEFAULT_VOICE
        assert cfg["enabled"] is False
        assert cfg["push_to_talk_only"] is True  # §9 Q3 unresolved => PTT
        assert cfg["wake_word"] == "osa"
        assert cfg["stt_model"] == "small"
        # Voice-OUT (2026-07-08): piper_voice now defaults to the auditioned
        # model; new speak_replies / voice_dir knobs are present.
        assert cfg["piper_voice"] == "en_GB-alan-medium"
        assert cfg["speak_replies"] is True
        assert cfg["voice_dir"]
        assert cfg["mute"] is False

    def test_pre_14d_yaml_without_voice_block_merges_defaults(self, tmp_path):
        """A constitution written before 14d loads with pure voice defaults."""
        path = tmp_path / "constitution.yaml"
        path.write_text(
            "constitution:\n"
            "  version: '1.0'\n"
            "  limits:\n"
            "    max_tokens_per_workflow: 1000\n"
        )
        cfg = Constitution.load(path).voice
        assert cfg == DEFAULT_VOICE

    def test_partial_voice_block_overrides_only_named_keys(self, tmp_path):
        path = tmp_path / "constitution.yaml"
        path.write_text(
            "constitution:\n"
            "  version: '1.0'\n"
            "  voice:\n"
            "    stt_model: base\n"
        )
        cfg = Constitution.load(path).voice
        assert cfg["stt_model"] == "base"
        assert cfg["enabled"] is False          # untouched default
        assert cfg["push_to_talk_only"] is True

    def test_voice_config_falls_back_to_defaults_on_load_failure(self, monkeypatch):
        vcfg.reset_config_cache()
        monkeypatch.setattr(
            Constitution, "load",
            classmethod(lambda cls, path=None: (_ for _ in ()).throw(OSError("boom"))),
        )
        assert vcfg.voice_config() == DEFAULT_VOICE  # never raises


# ═══════════════════════════════════════════════════════════════════════════════
# Dep probe — deps are genuinely absent in this .venv
# ═══════════════════════════════════════════════════════════════════════════════

class TestVoiceAvailable:
    def test_reports_missing_cleanly_with_deps_absent(self):
        """The optional extras are NOT installed — probe must say so, not raise."""
        ok, missing = voice_available()
        assert isinstance(ok, bool)
        assert isinstance(missing, list)
        assert set(missing) <= set(OPTIONAL_DEPS)   # pip names only
        assert ok is False and missing              # extras absent in base .venv

    def test_all_present_when_every_spec_resolves(self, monkeypatch):
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
        assert voice_available() == (True, [])

    def test_all_missing_when_no_spec_resolves(self, monkeypatch):
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
        ok, missing = voice_available()
        assert ok is False
        assert missing == list(OPTIONAL_DEPS)

    def test_probe_exception_counts_as_missing_never_raises(self, monkeypatch):
        def _boom(name):
            raise ValueError("broken install")
        monkeypatch.setattr(importlib.util, "find_spec", _boom)
        ok, missing = voice_available()
        assert ok is False
        assert missing == list(OPTIONAL_DEPS)


# ═══════════════════════════════════════════════════════════════════════════════
# Service lifecycle — the state machine never lets an exception out
# ═══════════════════════════════════════════════════════════════════════════════

class TestServiceLifecycle:
    def test_initial_state_is_disabled(self):
        assert _service().state()["state"] == "disabled"

    def test_start_with_flag_off_stays_disabled(self):
        svc = _service(enabled=False, ok=True)
        assert svc.start() is False
        snap = svc.state()
        assert snap["state"] == "disabled"
        assert "voice.enabled" in snap["last_error"]

    def test_start_enabled_but_deps_missing_goes_error_with_reason(self):
        svc = _service(enabled=True, ok=False, missing=["openwakeword", "piper-tts"])
        assert svc.start() is False
        snap = svc.state()
        assert snap["state"] == "error"
        assert snap["deps_ok"] is False
        assert snap["missing"] == ["openwakeword", "piper-tts"]
        assert "openwakeword" in snap["last_error"]
        assert "requirements-voice.txt" in snap["last_error"]

    def test_start_enabled_with_deps_reaches_idle(self):
        svc = _service(enabled=True, ok=True)
        assert svc.start() is True
        assert svc.state()["state"] == "idle"
        assert svc.state()["last_error"] is None

    def test_stop_returns_to_disabled(self):
        svc = _service(enabled=True, ok=True)
        svc.start()
        svc.stop()
        assert svc.state()["state"] == "disabled"

    def test_ptt_refused_while_disabled(self):
        svc = _service(enabled=False)
        out = svc.push_to_talk()
        assert out["ok"] is False
        assert out["state"] == "disabled"
        assert out["reason"]

    def test_ptt_stub_lands_in_error_not_a_crash(self):
        """Deps 'present' but stages are 14d stubs: NotImplementedError is
        caught and recorded — the caller sees a reason, never an exception."""
        svc = _service(enabled=True, ok=True)
        svc.start()
        out = svc.push_to_talk()
        assert out["ok"] is False
        assert "not_implemented" in out["reason"]
        assert svc.state()["state"] == "error"

    def test_mute_flip_works_even_disabled(self):
        svc = _service(enabled=False)
        assert svc.state()["mute"] is False
        snap = svc.set_mute(True)
        assert snap["mute"] is True
        assert svc.set_mute(False)["mute"] is False

    def test_state_shape(self):
        snap = _service().state()
        assert set(snap) == {
            "state", "mute", "deps_ok", "missing", "last_error", "latency",
            "push_to_talk_only", "wake_word", "stt_model", "piper_voice",
            # Voice-OUT (2026-07-08):
            "speak_replies", "tts_ok",
        }
        assert snap["state"] in STATES
        assert isinstance(snap["latency"], dict)

    def test_mark_records_monotonic_latency_stamps(self):
        svc = _service()
        first = svc.mark("wake")
        second = svc.mark("text")
        lat = svc.state()["latency"]
        assert lat["wake"] == first
        assert lat["text"] == second
        assert second >= first

    def test_broken_availability_probe_counts_as_missing(self):
        def _boom():
            raise RuntimeError("probe exploded")
        svc = VoiceService(
            config={**DEFAULT_VOICE, "enabled": True}, availability=_boom
        )
        assert svc.start() is False
        assert svc.state()["state"] == "error"


# ═══════════════════════════════════════════════════════════════════════════════
# Routes — TestClient, flag off (the shipped default), no deps installed
# ═══════════════════════════════════════════════════════════════════════════════

class TestVoiceRoutes:
    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient
        from gui.sidecar.app import app as fastapi_app
        return TestClient(fastapi_app)

    def test_state_route_shape_and_disabled_default(self, client):
        r = client.get("/api/osa/voice/state")
        assert r.status_code == 200
        body = r.json()
        assert body["state"] == "disabled"
        assert body["enabled"] is False          # Constitution flag surfaced
        assert body["deps_ok"] is False          # extras absent in base .venv
        assert set(body["missing"]) <= set(OPTIONAL_DEPS)
        for key in ("mute", "last_error", "latency", "push_to_talk_only",
                    "wake_word", "stt_model", "piper_voice"):
            assert key in body

    def test_ptt_while_disabled_is_409(self, client):
        r = client.post("/api/osa/voice/ptt")
        assert r.status_code == 409
        assert r.json()["detail"]                # machine-readable reason

    def test_mute_flips_and_reports_state(self, client):
        r = client.post("/api/osa/voice/mute", json={"mute": True})
        assert r.status_code == 200
        assert r.json()["mute"] is True
        assert client.get("/api/osa/voice/state").json()["mute"] is True
        assert client.post(
            "/api/osa/voice/mute", json={"mute": False}
        ).json()["mute"] is False

    def test_mute_requires_bool_body(self, client):
        assert client.post("/api/osa/voice/mute", json={}).status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# Startup hook — flag off => no task; deps missing => logs + never raises
# ═══════════════════════════════════════════════════════════════════════════════

class TestStartupHook:
    def test_flag_off_creates_no_task_and_no_service(self):
        from gui.sidecar.app import _start_osa_voice, app as fastapi_app

        asyncio.run(_start_osa_voice())
        assert fastapi_app.state.osa_voice_task is None
        assert osa_voice._service is None        # get_service() never reached

    def test_enabled_but_deps_missing_logs_and_does_not_raise(self, monkeypatch, caplog):
        from gui.sidecar.app import _start_osa_voice, app as fastapi_app

        vcfg._config_cache = {**DEFAULT_VOICE, "enabled": True}
        monkeypatch.setattr(
            osa_voice, "voice_available", lambda: (False, ["openwakeword"])
        )
        with caplog.at_level("WARNING", logger="agenticos.osa.voice"):
            asyncio.run(_start_osa_voice())      # must not raise
        assert fastapi_app.state.osa_voice_task is None
        assert osa_voice.get_service().state()["state"] == "error"
        assert any("deps missing" in r.message for r in caplog.records)

    def test_enabled_with_deps_starts_background_task(self, monkeypatch):
        from gui.sidecar.app import _start_osa_voice, app as fastapi_app

        vcfg._config_cache = {**DEFAULT_VOICE, "enabled": True}
        monkeypatch.setattr(osa_voice, "voice_available", lambda: (True, []))

        async def _run():
            await _start_osa_voice()
            task = fastapi_app.state.osa_voice_task
            assert task is not None
            await task                          # skeleton start() returns fast

        asyncio.run(_run())
        assert osa_voice.get_service().state()["state"] == "idle"
