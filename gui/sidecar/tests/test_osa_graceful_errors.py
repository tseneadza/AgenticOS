"""Graceful backend-error handling for OSA chat (2026-07-22).

A dead Anthropic key (400 "credit balance is too low"), a rate limit, an
overloaded API, or a down Ollama used to surface as a raw provider error — a 502
from the sync route or a raw ``error`` frame over WS. ``_classify_api_error`` maps
the common cases to an in-persona reply so OSA "speaks" the problem; unrecognized
errors still fall through to the raw path so real bugs stay visible.

Hermetic — no MySQL, no live LLM.
"""
from __future__ import annotations

import pytest

from gui.sidecar.routes import api_osa

# The exact string Anthropic returns when credits are exhausted.
_BILLING = (
    "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
    "'message': 'Your credit balance is too low to access the Anthropic API. "
    "Please go to Plans & Billing to upgrade or purchase credits.'}}"
)


class TestClassifier:
    @pytest.mark.parametrize("text,kind", [
        (_BILLING, "billing"),
        ("Your credit balance is too low", "billing"),
        ("authentication_error: invalid x-api-key", "auth"),
        ("Error code: 429 rate_limit_error: too many requests", "rate_limit"),
        ("Error code: 529 - overloaded_error", "overloaded"),
        ("HTTPConnectionPool(host='localhost', port=11434): Max retries", "local_down"),
    ])
    def test_known_errors_classify(self, text, kind):
        result = api_osa._classify_api_error(text)
        assert result is not None
        assert result[0] == kind
        assert result[1]  # a non-empty in-persona message

    def test_unknown_error_returns_none(self):
        assert api_osa._classify_api_error("KeyError: 'messages'") is None
        assert api_osa._classify_api_error(RuntimeError("boom")) is None

    def test_accepts_exception_or_string(self):
        assert api_osa._classify_api_error(RuntimeError(_BILLING))[0] == "billing"


# --------------------------------------------------------------------------- #
# Sync route — a recognized failure returns a friendly 200, not a 502.
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


class TestSyncRouteGracefulError:
    def _patch(self, monkeypatch, agent):
        from agents import osa_agent as oa
        from core import llm, memory

        monkeypatch.setattr(oa, "warm_ollama", lambda: True)
        monkeypatch.setattr(oa, "pick_model", lambda msg, **k: "default")
        monkeypatch.setattr(llm, "resolve", lambda alias: "claude-sonnet-4-6")
        monkeypatch.setattr(memory, "checkpointer_conn", lambda: None)
        monkeypatch.setattr(memory, "get_checkpointer", lambda conn=None: object())
        monkeypatch.setattr("gui.sidecar.osa_settings.get_model_pin", lambda: None)
        monkeypatch.setattr(oa, "build_agent", lambda model_id, approval_fn=None, **k: agent)
        monkeypatch.setattr(api_osa, "_maybe_speak_reply", lambda reply: None)

    def _client(self):
        from fastapi.testclient import TestClient
        from gui.sidecar.app import app as fastapi_app
        return TestClient(fastapi_app)

    def test_billing_error_becomes_friendly_200(self, monkeypatch):
        self._patch(monkeypatch, _RaisingAgent(RuntimeError(_BILLING)))
        resp = self._client().post(
            "/api/osa/chat",
            json={"message": "search the web for X", "thread_id": "osa-billing"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["error_kind"] == "billing"
        assert "credits" in body["reply"].lower()
        assert body["tool_trace"] == []

    def test_unknown_error_still_502(self, monkeypatch):
        self._patch(monkeypatch, _RaisingAgent(KeyError("messages")))
        resp = self._client().post(
            "/api/osa/chat",
            json={"message": "hi", "thread_id": "osa-bug"},
        )
        assert resp.status_code == 502


def test_ws_handler_wires_the_classifier():
    """Source-level guard: the WS path must route errors through the classifier
    (a full WS integration test needs a live graph + checkpointer)."""
    import inspect
    src = inspect.getsource(api_osa.osa_chat_ws)
    assert "_classify_api_error(outcome[\"error\"])" in src
