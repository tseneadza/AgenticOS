"""Cloud-brain fallback for durable provider failures (2026-07-24).

Locked with Tony (interview, 2026-07-24):
  * Q1 "Both" — a billing/auth failure retries the turn on the local brain
    AND arms a sticky degraded flag so later turns stop burning the dead key.
  * Q2 — cloud-worthy turns (route "default") fail in persona while degraded;
    the local-pin keys guardrail means they have no safe local home.
  * Q3 — lazy TTL re-probe (the next cloud attempt past the TTL IS the probe)
    plus the manual clear phrase "try your cloud brain again".

Transient kinds (rate_limit / overloaded) must NEVER trip the flag.

Hermetic — no MySQL, no live LLM, no Ollama.
"""
from __future__ import annotations

import time

import pytest

from agents import osa_agent
from gui.sidecar.routes import api_osa

_BILLING = (
    "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
    "'message': 'Your credit balance is too low to access the Anthropic API. "
    "Please go to Plans & Billing to upgrade or purchase credits.'}}"
)


@pytest.fixture(autouse=True)
def _clean_flag():
    """Every test starts and ends with the flag disarmed."""
    osa_agent.clear_cloud_dead()
    yield
    osa_agent.clear_cloud_dead()


# --------------------------------------------------------------------------- #
# Flag mechanics (pure, in agents.osa_agent)
# --------------------------------------------------------------------------- #
class TestFlagMechanics:
    def test_durable_kind_arms_and_first_arm_is_flagged(self):
        assert osa_agent.mark_cloud_dead("billing") is True   # newly armed
        assert osa_agent.mark_cloud_dead("billing") is False  # re-arm: quiet
        st = osa_agent.cloud_dead_status()
        assert st["kind"] == "billing" and st["fresh"] is True

    @pytest.mark.parametrize("kind", ["rate_limit", "overloaded", "local_down", "nope"])
    def test_transient_kinds_never_arm(self, kind):
        assert osa_agent.mark_cloud_dead(kind) is False
        assert osa_agent.cloud_dead_status()["kind"] is None

    def test_ttl_expiry_unfreshes_but_keeps_kind(self, monkeypatch):
        osa_agent.mark_cloud_dead("billing")
        real = time.time()
        monkeypatch.setattr(
            osa_agent.time, "time",
            lambda: real + osa_agent.CLOUD_RETRY_TTL_SECONDS + 1,
        )
        st = osa_agent.cloud_dead_status()
        assert st["kind"] == "billing"  # HUD chip stays honest
        assert st["fresh"] is False     # next cloud turn is the lazy probe

    def test_clear_and_note_cloud_ok(self):
        osa_agent.mark_cloud_dead("auth")
        osa_agent.note_cloud_ok()
        assert osa_agent.cloud_dead_status()["kind"] is None
        osa_agent.mark_cloud_dead("billing")
        osa_agent.clear_cloud_dead()
        assert osa_agent.cloud_dead_status()["kind"] is None

    @pytest.mark.parametrize("msg,expected", [
        ("try your cloud brain again", True),
        ("Try the cloud again", True),
        ("use your cloud brain", True),
        ("retry cloud", True),
        ("what's the weather", False),
        ("", False),
    ])
    def test_retry_phrase_detector(self, msg, expected):
        assert osa_agent.is_cloud_retry_request(msg) is expected


# --------------------------------------------------------------------------- #
# Sync route behavior
# --------------------------------------------------------------------------- #
class _CleanSnap:
    next = ()
    tasks = ()
    values = {"messages": []}


class _RaisingAgent:
    def __init__(self, exc):
        self._exc = exc

    def get_state(self, config):
        return _CleanSnap()

    def invoke(self, payload, config=None):
        raise self._exc

    def update_state(self, config, values):  # pragma: no cover
        pass


class _Msg:
    tool_calls = []

    def __init__(self, text):
        self.content = text


class _OkAgent:
    def __init__(self, text="Done, Sir."):
        self._text = text
        self.invoked = 0

    def get_state(self, config):
        return _CleanSnap()

    def invoke(self, payload, config=None):
        self.invoked += 1
        return {"messages": [_Msg(self._text)]}

    def update_state(self, config, values):  # pragma: no cover
        pass


class _Info:
    def __init__(self, is_local):
        self.is_local = is_local
        self.label = "stub"


def _client():
    from fastapi.testclient import TestClient
    from gui.sidecar.app import app as fastapi_app
    return TestClient(fastapi_app)


def _base_patch(monkeypatch):
    from core import llm, memory

    monkeypatch.setattr(osa_agent, "warm_ollama", lambda: True)
    monkeypatch.setattr(memory, "checkpointer_conn", lambda: None)
    monkeypatch.setattr(memory, "get_checkpointer", lambda conn=None: object())
    monkeypatch.setattr("gui.sidecar.osa_settings.get_model_pin", lambda: None)
    monkeypatch.setattr(api_osa, "_maybe_speak_reply", lambda reply: None)
    monkeypatch.setattr(llm, "discover_ollama", lambda force=False: {})


class TestSyncFastFail:
    def test_fresh_flag_blocks_cloud_turn_without_api_call(self, monkeypatch):
        from core import llm

        _base_patch(monkeypatch)
        monkeypatch.setattr(osa_agent, "pick_model", lambda msg, **k: "default")
        monkeypatch.setattr(llm, "resolve", lambda a: "claude-sonnet-4-6")
        monkeypatch.setattr(llm, "get_model_info", lambda m: _Info(is_local=False))

        def _boom(*a, **k):  # the whole point: no agent is ever built
            raise AssertionError("build_agent must not be called on a fast-fail")

        monkeypatch.setattr(osa_agent, "build_agent", _boom)
        osa_agent.mark_cloud_dead("billing")

        resp = _client().post(
            "/api/osa/chat",
            json={"message": "search the web for X", "thread_id": "osa-ff"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["error_kind"] == "billing"
        assert body["cloud_degraded"] is True
        assert "cloud brain" in body["reply"].lower()

    def test_expired_flag_lets_the_probe_through(self, monkeypatch):
        from core import llm

        _base_patch(monkeypatch)
        monkeypatch.setattr(osa_agent, "pick_model", lambda msg, **k: "default")
        monkeypatch.setattr(llm, "resolve", lambda a: "claude-sonnet-4-6")
        monkeypatch.setattr(llm, "get_model_info", lambda m: _Info(is_local=False))
        ok = _OkAgent()
        monkeypatch.setattr(osa_agent, "build_agent", lambda *a, **k: ok)

        osa_agent.mark_cloud_dead("billing")
        real = time.time()
        monkeypatch.setattr(
            osa_agent.time, "time",
            lambda: real + osa_agent.CLOUD_RETRY_TTL_SECONDS + 1,
        )
        resp = _client().post(
            "/api/osa/chat",
            json={"message": "search the web for X", "thread_id": "osa-probe"},
        )
        assert resp.status_code == 200
        assert ok.invoked == 1  # the attempt WAS the probe
        # ...and the successful cloud turn cleared the flag (note_cloud_ok).
        assert osa_agent.cloud_dead_status()["kind"] is None

    def test_manual_retry_phrase_clears_and_attempts(self, monkeypatch):
        from core import llm

        _base_patch(monkeypatch)
        monkeypatch.setattr(osa_agent, "pick_model", lambda msg, **k: "default")
        monkeypatch.setattr(llm, "resolve", lambda a: "claude-sonnet-4-6")
        monkeypatch.setattr(llm, "get_model_info", lambda m: _Info(is_local=False))
        ok = _OkAgent()
        monkeypatch.setattr(osa_agent, "build_agent", lambda *a, **k: ok)

        osa_agent.mark_cloud_dead("billing")  # fresh — would fast-fail
        resp = _client().post(
            "/api/osa/chat",
            json={"message": "try your cloud brain again", "thread_id": "osa-manual"},
        )
        assert resp.status_code == 200
        assert ok.invoked == 1
        assert osa_agent.cloud_dead_status()["kind"] is None


class TestSyncRescue:
    def _patch_rescue(self, monkeypatch, *, ollama_up=True):
        from core import llm

        _base_patch(monkeypatch)
        # The turn routes local-capable but ran on cloud (e.g. open router
        # ambiguity) — resolve maps aliases to distinct ids.
        monkeypatch.setattr(osa_agent, "pick_model", lambda msg, **k: "default")
        monkeypatch.setattr(osa_agent, "route_turn", lambda msg: "local")
        monkeypatch.setattr(
            llm, "resolve",
            lambda a: {"default": "claude-sonnet-4-6", "local": "fake-local:7b"}.get(a, a),
        )
        monkeypatch.setattr(
            llm, "get_model_info",
            lambda m: _Info(is_local=(m == "fake-local:7b")),
        )
        monkeypatch.setattr(llm, "ollama_up", lambda timeout=1.0: ollama_up)
        local_ok = _OkAgent("Noted, Sir.")

        def _build(model_id, **k):
            if model_id == "fake-local:7b":
                return local_ok
            return _RaisingAgent(RuntimeError(_BILLING))

        monkeypatch.setattr(osa_agent, "build_agent", _build)
        return local_ok

    def test_billing_on_local_capable_turn_rescues_and_announces(self, monkeypatch):
        local_ok = self._patch_rescue(monkeypatch)
        resp = _client().post(
            "/api/osa/chat",
            json={"message": "note that the deck is done", "thread_id": "osa-rescue"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert local_ok.invoked == 1
        assert body["model"] == "fake-local:7b"
        assert body["route"] == "local"
        assert body["cloud_degraded"] is True
        assert body["error_kind"] == "billing"
        # First arm ⇒ the one-time announcement precedes the local reply.
        assert "heads-up" in body["reply"].lower()
        assert "noted, sir" in body["reply"].lower()
        assert osa_agent.cloud_dead_status()["kind"] == "billing"

    def test_armed_flag_downgrades_local_capable_turn_preemptively(self, monkeypatch):
        """While degraded, a local-capable turn never touches the dead key —
        it runs local from the start (no error, no announcement, no rescue)."""
        local_ok = self._patch_rescue(monkeypatch)
        osa_agent.mark_cloud_dead("billing")  # already armed + fresh
        resp = _client().post(
            "/api/osa/chat",
            json={"message": "note that too", "thread_id": "osa-downgrade"},
        )
        body = resp.json()
        assert local_ok.invoked == 1
        assert body["model"] == "fake-local:7b"
        assert body["route"] == "local"
        assert "error_kind" not in body       # a NORMAL turn, not a failure
        assert "heads-up" not in body["reply"].lower()

    def test_rescue_unavailable_falls_back_to_friendly(self, monkeypatch):
        self._patch_rescue(monkeypatch, ollama_up=False)
        resp = _client().post(
            "/api/osa/chat",
            json={"message": "note this down", "thread_id": "osa-norescue"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["error_kind"] == "billing"
        assert "credits" in body["reply"].lower()
        assert osa_agent.cloud_dead_status()["kind"] == "billing"  # still armed

    def test_transient_error_does_not_arm(self, monkeypatch):
        from core import llm

        _base_patch(monkeypatch)
        monkeypatch.setattr(osa_agent, "pick_model", lambda msg, **k: "default")
        monkeypatch.setattr(llm, "resolve", lambda a: "claude-sonnet-4-6")
        monkeypatch.setattr(llm, "get_model_info", lambda m: _Info(is_local=False))
        monkeypatch.setattr(
            osa_agent, "build_agent",
            lambda *a, **k: _RaisingAgent(RuntimeError("Error code: 529 - overloaded_error")),
        )
        resp = _client().post(
            "/api/osa/chat",
            json={"message": "search the web for X", "thread_id": "osa-529"},
        )
        assert resp.status_code == 200
        assert resp.json()["error_kind"] == "overloaded"
        assert osa_agent.cloud_dead_status()["kind"] is None


# --------------------------------------------------------------------------- #
# State + WS wiring
# --------------------------------------------------------------------------- #
def test_osa_state_exposes_cloud_degraded(monkeypatch):
    from core import llm

    monkeypatch.setattr(llm, "ollama_up", lambda timeout=1.0: False)
    monkeypatch.setattr("gui.sidecar.osa_settings.get_model_pin", lambda: None)
    osa_agent.mark_cloud_dead("billing")
    resp = _client().get("/api/osa/state")
    body = resp.json()
    assert body["cloud_degraded"]["kind"] == "billing"
    assert body["cloud_degraded"]["fresh"] is True


def test_ws_handler_wires_the_fallback():
    """Source-level guard (same pattern as the graceful-errors suite): the WS
    path must arm the flag, attempt the rescue, fast-fail while fresh, and
    clear on success."""
    import inspect
    src = inspect.getsource(api_osa.osa_chat_ws)
    for needle in (
        "mark_cloud_dead(kind)",
        "_retry_turn_local",
        "cloud_dead_status()",
        "is_cloud_retry_request(message)",
        "note_cloud_ok()",
        "_CLOUD_STILL_DEAD_MSG",
    ):
        assert needle in src, f"WS handler missing {needle}"
