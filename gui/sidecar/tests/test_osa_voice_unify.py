"""Voice <-> on-screen chat unification (14x, 2026-07-14).

Spoken turns must land in the SAME on-screen OSA transcript as typed chat.
Two mechanisms, both covered here headless (no audio, no LLM, no network):

  * a shared active-thread register (``gui.sidecar.osa_active_thread`` + the
    ``/api/osa/active-thread`` routes) the UI sets and the voice pipeline
    reads, so voice writes into the thread the user is viewing; and
  * bus events (``OSA_VOICE_TURN_STARTED`` / ``OSA_VOICE_TURN_FINISHED``,
    tagged ``source="voice"``) the UI folds into the transcript live.
"""
from __future__ import annotations

import pytest

from core.constitution import DEFAULT_VOICE
from gui.sidecar import osa_active_thread
from gui.sidecar.events import bus
from osa_voice.pipeline import VoiceService


@pytest.fixture(autouse=True)
def _reset_active_thread():
    """Each test starts with no active thread (module global is shared)."""
    osa_active_thread.set_active_thread(None)
    yield
    osa_active_thread.set_active_thread(None)


def _svc(**over):
    cfg = {**DEFAULT_VOICE, "enabled": True, **over}
    return VoiceService(config=cfg, availability=lambda: (True, []))


# ═══════════════════════════════════════════════════════════════════════════════
# Active-thread register — module + routes
# ═══════════════════════════════════════════════════════════════════════════════

class TestActiveThreadModule:
    def test_get_set_roundtrip(self):
        assert osa_active_thread.get_active_thread() is None
        osa_active_thread.set_active_thread("osa-abc123")
        assert osa_active_thread.get_active_thread() == "osa-abc123"

    def test_empty_and_whitespace_clear(self):
        osa_active_thread.set_active_thread("osa-x")
        osa_active_thread.set_active_thread("")
        assert osa_active_thread.get_active_thread() is None
        osa_active_thread.set_active_thread("osa-y")
        osa_active_thread.set_active_thread("   ")
        assert osa_active_thread.get_active_thread() is None
        osa_active_thread.set_active_thread(None)
        assert osa_active_thread.get_active_thread() is None


def _client():
    from fastapi.testclient import TestClient
    from gui.sidecar.app import app as fastapi_app
    return TestClient(fastapi_app)


class TestActiveThreadRoutes:
    def test_post_then_get(self):
        c = _client()
        r = c.post("/api/osa/active-thread", json={"thread_id": "osa-ui-1"})
        assert r.status_code == 200
        assert r.json()["thread_id"] == "osa-ui-1"
        assert osa_active_thread.get_active_thread() == "osa-ui-1"

        g = c.get("/api/osa/active-thread")
        assert g.status_code == 200
        assert g.json()["thread_id"] == "osa-ui-1"

    def test_post_null_clears(self):
        c = _client()
        c.post("/api/osa/active-thread", json={"thread_id": "osa-ui-2"})
        c.post("/api/osa/active-thread", json={"thread_id": None})
        assert osa_active_thread.get_active_thread() is None
        assert c.get("/api/osa/active-thread").json()["thread_id"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# _chat_turn — prefers the UI's active thread, falls back to the voice thread
# ═══════════════════════════════════════════════════════════════════════════════

class _FakeResp:
    def __init__(self, reply: str):
        self._reply = reply

    def raise_for_status(self):
        return None

    def json(self):
        return {"reply": self._reply}


class TestChatTurnThread:
    def _capture_post(self, monkeypatch):
        seen: dict = {}

        def _fake_post(url, json=None, timeout=None):
            seen["url"] = url
            seen["thread_id"] = (json or {}).get("thread_id")
            seen["message"] = (json or {}).get("message")
            return _FakeResp("ok reply")

        import requests
        monkeypatch.setattr(requests, "post", _fake_post)
        return seen

    def test_uses_active_thread_when_set(self, monkeypatch):
        svc = _svc()
        seen = self._capture_post(monkeypatch)
        osa_active_thread.set_active_thread("osa-ui-thread")
        reply = svc._chat_turn("what time is it")
        assert reply == "ok reply"
        assert seen["thread_id"] == "osa-ui-thread"   # UI thread, not voice
        assert seen["message"] == "what time is it"

    def test_falls_back_to_voice_thread(self, monkeypatch):
        svc = _svc()
        seen = self._capture_post(monkeypatch)
        # No active thread set → the sticky per-lifetime voice thread is used.
        svc._chat_turn("hello")
        assert seen["thread_id"] == svc._voice_thread
        assert str(seen["thread_id"]).startswith("osa-voice-")

    def test_active_thread_lookup_failure_is_defensive(self, monkeypatch):
        svc = _svc()
        seen = self._capture_post(monkeypatch)

        def _boom():
            raise RuntimeError("register down")

        monkeypatch.setattr(osa_active_thread, "get_active_thread", _boom)
        # Must not raise — falls back to the voice thread.
        svc._chat_turn("hi")
        assert str(seen["thread_id"]).startswith("osa-voice-")


# ═══════════════════════════════════════════════════════════════════════════════
# Voice turn path — publishes STARTED + FINISHED (source="voice") to the bus
# ═══════════════════════════════════════════════════════════════════════════════

class TestVoiceTurnPublishes:
    def _voice_events(self, since: int):
        return [e for e in bus.history[since:] if e.get("source") == "voice"]

    def test_voice_turn_publishes_start_and_finish(self, monkeypatch):
        svc = _svc()
        osa_active_thread.set_active_thread("osa-shared-1")
        monkeypatch.setattr(svc, "_chat_turn", lambda text: "It is noon, Sir.")
        start = len(bus.history)

        reply = svc._voice_turn("what time is it")
        assert reply == "It is noon, Sir."

        evts = self._voice_events(start)
        types = [e["type"] for e in evts]
        assert "OSA_VOICE_TURN_STARTED" in types
        assert "OSA_VOICE_TURN_FINISHED" in types

        started = next(e for e in evts if e["type"] == "OSA_VOICE_TURN_STARTED")
        finished = next(e for e in evts if e["type"] == "OSA_VOICE_TURN_FINISHED")
        assert started["user"] == "what time is it"
        assert started["thread_id"] == "osa-shared-1"
        assert finished["reply"] == "It is noon, Sir."
        # Same turn_id ties the pair together for the UI.
        assert started["turn_id"] == finished["turn_id"]

    def test_run_wake_turn_publishes_voice_events(self, monkeypatch):
        svc = _svc()
        monkeypatch.setattr(svc, "_chat_turn", lambda text: "done")
        start = len(bus.history)

        svc._run_wake_turn("status report")

        types = [e["type"] for e in self._voice_events(start)]
        assert types.count("OSA_VOICE_TURN_STARTED") == 1
        assert types.count("OSA_VOICE_TURN_FINISHED") == 1

    def test_bus_failure_never_breaks_the_turn(self, monkeypatch):
        svc = _svc()
        monkeypatch.setattr(svc, "_chat_turn", lambda text: "still works")

        def _boom(*a, **k):
            raise RuntimeError("bus exploded")

        monkeypatch.setattr(bus, "publish", _boom)
        # Publishing is best-effort — the reply must still come back.
        assert svc._voice_turn("hi") == "still works"
