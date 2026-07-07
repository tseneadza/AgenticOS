"""OSA's own punch list (2026-07-07 night) — the four to-dos it listed live.

1. Orb brain display — /api/osa/state now carries pinned_label +
   last_turn_{model,label,escalated} so the orb shows runtime truth.
2. Confirm surfacing — instructive DENIED (no silent retries) + the route's
   deterministic "Needs your OK, Sir" safety net when the model forgets
   to ask.
3. Hardware-aware pulls (Tony's reframe of "pull llama3.3") — the approval
   description carries the estimated download size and the RAM verdict.
4. llama3.2:latest curated into the registry with a clean label.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents import osa_agent
from gui.sidecar import osa_settings
from gui.sidecar.routes import api_osa


@pytest.fixture(autouse=True)
def _fresh():
    api_osa._PENDING_CONFIRM.clear()
    api_osa._LAST_TURN.update(model=None, escalated=False)
    yield
    api_osa._PENDING_CONFIRM.clear()
    api_osa._LAST_TURN.update(model=None, escalated=False)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. estimate_pull_size — manifest, heuristic, unknown
# ═══════════════════════════════════════════════════════════════════════════════

class TestEstimatePullSize:
    def test_manifest_layers_summed(self, monkeypatch):
        from core import llm

        class _Resp:
            ok = True

            def json(self):
                return {"layers": [{"size": 40_000_000_000},
                                   {"size": 2_500_000_000}]}

        import requests
        monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())
        assert llm.estimate_pull_size("llama3.3") == 42_500_000_000

    def test_heuristic_from_name_when_manifest_fails(self, monkeypatch):
        from core import llm

        import requests

        def _boom(*a, **k):
            raise OSError("offline")

        monkeypatch.setattr(requests, "get", _boom)
        size = llm.estimate_pull_size("llama3.1:8b")
        assert size == int(8 * 0.6e9)

    def test_unknown_when_nothing_works(self, monkeypatch):
        from core import llm

        import requests
        monkeypatch.setattr(
            requests, "get",
            lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
        assert llm.estimate_pull_size("mystery-model") is None


# ═══════════════════════════════════════════════════════════════════════════════
# 2 + 3. pull_model — informed confirm description + instructive DENIED
# ═══════════════════════════════════════════════════════════════════════════════

class TestHardwareAwareConfirm:
    def _capture_box(self):
        asked = {}

        def _deny(action, description):
            asked.update(action=action, description=description)
            return "deny"

        return osa_agent.OSAToolbox(approval_fn=_deny), asked

    def test_oversize_pull_confirm_carries_size_and_ram_verdict(
            self, monkeypatch):
        from core import llm

        monkeypatch.setattr(llm, "discover_ollama", lambda **k: {})
        monkeypatch.setattr(
            llm, "estimate_pull_size", lambda n, **k: 42_500_000_000)
        monkeypatch.setattr(llm, "total_ram_bytes", lambda: 16_000_000_000)
        box, asked = self._capture_box()
        out = box.pull_model("llama3.3")
        assert asked["action"] == "model_pull"
        assert "42.5GB" in asked["description"]
        assert "too big" in asked["description"]
        assert "16GB RAM" in asked["description"]
        # Instructive DENIED — the model must ask Tony, not retry.
        assert out.startswith("DENIED")
        assert "42.5GB" in out
        assert "Do NOT call this tool" in out

    def test_fitting_pull_has_size_but_no_ram_warning(self, monkeypatch):
        from core import llm

        monkeypatch.setattr(llm, "discover_ollama", lambda **k: {})
        monkeypatch.setattr(
            llm, "estimate_pull_size", lambda n, **k: 4_900_000_000)
        monkeypatch.setattr(llm, "total_ram_bytes", lambda: 16_000_000_000)
        box, asked = self._capture_box()
        box.pull_model("llama3.1:8b")
        assert "4.9GB" in asked["description"]
        assert "too big" not in asked["description"]

    def test_unknown_size_is_honest(self, monkeypatch):
        from core import llm

        monkeypatch.setattr(llm, "discover_ollama", lambda **k: {})
        monkeypatch.setattr(llm, "estimate_pull_size", lambda n, **k: None)
        box, asked = self._capture_box()
        box.pull_model("mystery3.9")
        assert "size unknown" in asked["description"]

    def test_approved_oversize_pull_still_runs(self, monkeypatch):
        # The verdict informs — it never blocks. Tony's yes is final.
        from core import llm

        monkeypatch.setattr(llm, "discover_ollama", lambda **k: {})
        monkeypatch.setattr(
            llm, "estimate_pull_size", lambda n, **k: 42_500_000_000)
        monkeypatch.setattr(llm, "total_ram_bytes", lambda: 16_000_000_000)
        monkeypatch.setattr(
            osa_agent, "_run_pull", lambda n: {"ok": True, "error": None})
        box = osa_agent.OSAToolbox(approval_fn=lambda a, d: "approve")
        out = box.pull_model("llama3.3")
        assert "Pulling llama3.3" in out
        osa_agent.reset_pull_state()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Route safety net — the confirm question is never invisible
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfirmSurfacing:
    def _client(self):
        from fastapi.testclient import TestClient
        from gui.sidecar.app import app as fastapi_app
        return TestClient(fastapi_app)

    def _wire(self, monkeypatch, reply_text):
        """14b-style fake agent: triggers approval_fn, replies without asking."""
        from agents import osa_agent as oa
        from core import llm, memory

        monkeypatch.setattr(oa, "warm_ollama", lambda: True)
        monkeypatch.setattr(oa, "pick_model", lambda msg, **k: "default")
        monkeypatch.setattr(llm, "resolve", lambda a: "claude-sonnet-4-6")
        monkeypatch.setattr(osa_settings, "get_model_pin", lambda **k: None)
        monkeypatch.setattr(memory, "checkpointer_conn", lambda: None)
        monkeypatch.setattr(memory, "get_checkpointer", lambda c=None: object())

        class _Msg:
            def __init__(self, content):
                self.content = content
                self.tool_calls = []

        class _FakeAgent:
            def __init__(self, approval_fn):
                self._approval_fn = approval_fn

            def invoke(self, payload, config=None):
                self._approval_fn(
                    "model_pull",
                    "Downloading llama3.3 (≈42.5GB) — too big to run well "
                    "in this machine's 16GB RAM")
                return {"messages": [_Msg(reply_text)]}

        monkeypatch.setattr(
            oa, "build_agent",
            lambda model_id, approval_fn=None, **k: _FakeAgent(approval_fn))

    def test_reply_without_ask_gets_the_safety_net(self, monkeypatch):
        self._wire(monkeypatch, "I tried to pull it. Took Claude for that one.")
        r = self._client().post(
            "/api/osa/chat", json={"message": "pull llama3.3"})
        data = r.json()
        assert data["awaiting_confirm"] is True
        assert "Needs your OK, Sir" in data["reply"]
        assert "42.5GB" in data["reply"]
        assert "Just say yes" in data["reply"]

    def test_reply_that_already_asks_is_untouched(self, monkeypatch):
        asking = "That's a 42.5GB download, Sir. Say yes and I'll start."
        self._wire(monkeypatch, asking)
        r = self._client().post(
            "/api/osa/chat", json={"message": "pull llama3.3"})
        data = r.json()
        assert data["awaiting_confirm"] is True
        assert "Needs your OK" not in data["reply"]
        assert data["reply"].startswith(asking)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Orb brain display — state carries pin label + last-turn runtime truth
# ═══════════════════════════════════════════════════════════════════════════════

class TestBrainDisplayState:
    def _client(self):
        from fastapi.testclient import TestClient
        from gui.sidecar.app import app as fastapi_app
        return TestClient(fastapi_app)

    def test_state_carries_pin_label_and_last_turn(self, monkeypatch):
        monkeypatch.setattr(
            osa_settings, "get_model_pin", lambda **k: "qwen2.5:7b-instruct")
        api_osa._LAST_TURN.update(
            model="claude-sonnet-4-6", escalated=True)
        s = self._client().get("/api/osa/state").json()
        assert s["pinned_model"] == "qwen2.5:7b-instruct"
        assert "Qwen" in s["pinned_label"]
        assert s["last_turn_model"] == "claude-sonnet-4-6"
        assert "Sonnet" in s["last_turn_label"]
        assert s["last_turn_escalated"] is True

    def test_state_null_fields_before_first_turn(self, monkeypatch):
        monkeypatch.setattr(osa_settings, "get_model_pin", lambda **k: None)
        s = self._client().get("/api/osa/state").json()
        assert s["pinned_label"] is None
        assert s["last_turn_model"] is None
        assert s["last_turn_label"] is None
        assert s["last_turn_escalated"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. llama3.2 curated
# ═══════════════════════════════════════════════════════════════════════════════

class TestLlama32Curated:
    def test_registry_has_llama32_with_clean_label(self):
        from core import llm

        by_id = {m.id: m for m in llm.registry()}
        assert "llama3.2:latest" in by_id
        assert by_id["llama3.2:latest"].label == "Llama 3.2 3B (local)"
        assert by_id["llama3.2:latest"].provider == "ollama"


# ═══════════════════════════════════════════════════════════════════════════════
# Echo scrub — small local models parroting the brain-status suffix
# ═══════════════════════════════════════════════════════════════════════════════

class TestBrainLineEchoScrub:
    def _client(self):
        from fastapi.testclient import TestClient
        from gui.sidecar.app import app as fastapi_app
        return TestClient(fastapi_app)

    def _wire(self, monkeypatch, reply_builder):
        from agents import osa_agent as oa
        from core import llm, memory

        monkeypatch.setattr(oa, "warm_ollama", lambda: True)
        monkeypatch.setattr(oa, "pick_model", lambda msg, **k: "local")
        monkeypatch.setattr(llm, "resolve", lambda a: "llama3.2:latest")
        monkeypatch.setattr(osa_settings, "get_model_pin", lambda **k: None)
        monkeypatch.setattr(memory, "checkpointer_conn", lambda: None)
        monkeypatch.setattr(memory, "get_checkpointer", lambda c=None: object())

        class _Msg:
            def __init__(self, content):
                self.content = content
                self.tool_calls = []

        captured = {}

        class _FakeAgent:
            def __init__(self, suffix):
                self._suffix = suffix

            def invoke(self, payload, config=None):
                return {"messages": [_Msg(reply_builder(self._suffix))]}

        def _build(model_id, approval_fn=None, system_suffix=None, **k):
            captured["suffix"] = system_suffix
            return _FakeAgent(system_suffix)

        monkeypatch.setattr(oa, "build_agent", _build)
        return captured

    def test_pure_echo_becomes_plain_ack(self, monkeypatch):
        self._wire(monkeypatch, lambda suffix: suffix)   # model parrots verbatim
        r = self._client().post("/api/osa/chat", json={"message": "no, skip it"})
        assert r.json()["reply"] == "Understood."

    def test_echo_around_real_answer_is_stripped(self, monkeypatch):
        self._wire(
            monkeypatch,
            lambda suffix: f"Standing down, Sir. {suffix}")
        reply = self._client().post(
            "/api/osa/chat", json={"message": "no"}).json()["reply"]
        assert reply == "Standing down, Sir."
        assert "Brain status" not in reply

    def test_suffix_is_marked_internal(self):
        line = osa_agent.brain_prompt_line(
            pin=None, effective="llama3.2:latest", escalated=False)
        assert line.startswith("[Internal note")
        assert "never repeat" in line
