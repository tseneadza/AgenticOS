"""Phase 14a tests — OSA agent (text MVP): routing, toolbox, warm-on-init, routes.

Everything here exercises OSA *without* a live LLM: the ``OSAToolbox`` methods
are called directly (they're plain guarded Python), routing is a pure function,
Ollama warming is tested by patching ``core.llm.ensure_ollama_running`` (up,
down, binary-missing), and the FastAPI routes are driven with the agent build +
checkpointer patched so no model or MySQL checkpointer is needed.

Mirrors the governor/13e conventions: guard-path assertions, monkeypatched
adapters, and TestClient route checks.
"""
from __future__ import annotations

import pytest

from agents import osa_agent
from core.constitution import ApprovalRequired, Constitution, ConstitutionViolation


@pytest.fixture(autouse=True)
def _reset_warm_cache():
    """Each test starts with a cold Ollama warm cache."""
    osa_agent.reset_ollama_warm_cache()
    yield
    osa_agent.reset_ollama_warm_cache()


# ═══════════════════════════════════════════════════════════════════════════════
# Turn routing (decision #6 / §4.3) — pure classifier
# ═══════════════════════════════════════════════════════════════════════════════

class TestRouting:
    @pytest.mark.parametrize("msg", [
        "hi", "hey OSA", "thanks", "ok", "never mind", "good morning",
        "yes", "cool", "you there?",
    ])
    def test_chitchat_routes_local(self, msg):
        assert osa_agent.route_turn(msg) == "local"

    @pytest.mark.parametrize("msg", [
        "launch worldwise",
        "stop the keno app",
        "is dreamcatcher running?",
        "how's my memory?",
        "what's the system health",
        "remember that I prefer dark mode",
        "why did the sidecar restart",
        "list my running apps",
    ])
    def test_control_and_questions_route_default(self, msg):
        assert osa_agent.route_turn(msg) == "default"

    def test_empty_routes_local(self):
        assert osa_agent.route_turn("") == "local"
        assert osa_agent.route_turn("   ") == "local"

    def test_longer_ambiguous_defaults_to_cloud(self):
        # No tool signal, not chit-chat, more than 3 words → default (safe).
        assert osa_agent.route_turn("tell me a long story about dragons") == "default"

    def test_pick_model_local_downgrades_when_ollama_down(self):
        # A chit-chat turn wants local, but with Ollama down it must fall back.
        assert osa_agent.pick_model("hey", ollama_ready=True) == "local"
        assert osa_agent.pick_model("hey", ollama_ready=False) == "default"

    def test_pick_model_default_unaffected_by_ollama(self):
        assert osa_agent.pick_model("launch worldwise", ollama_ready=False) == "default"
        assert osa_agent.pick_model("launch worldwise", ollama_ready=True) == "default"


# ═══════════════════════════════════════════════════════════════════════════════
# Ollama ensure-on-OSA-init (decision #9): best-effort, cached, never raises
# ═══════════════════════════════════════════════════════════════════════════════

class TestWarmOllama:
    def test_up(self, monkeypatch):
        calls = {"n": 0}

        def _fake(*a, **k):
            calls["n"] += 1
            return {"up": True, "started": False}

        monkeypatch.setattr("core.llm.ensure_ollama_running", _fake)
        assert osa_agent.warm_ollama() is True
        # Cached: a second call does NOT re-spawn.
        assert osa_agent.warm_ollama() is True
        assert calls["n"] == 1

    def test_down_falls_back_never_raises(self, monkeypatch):
        monkeypatch.setattr(
            "core.llm.ensure_ollama_running",
            lambda *a, **k: {"up": False, "started": True,
                             "error": "ollama did not become ready in time"},
        )
        assert osa_agent.warm_ollama() is False
        # And a local-routed turn downgrades to Claude when warm said not-ready.
        assert osa_agent.pick_model("hey", ollama_ready=osa_agent.warm_ollama()) == "default"

    def test_binary_missing_never_raises(self, monkeypatch):
        monkeypatch.setattr(
            "core.llm.ensure_ollama_running",
            lambda *a, **k: {"up": False, "started": False,
                             "error": "ollama binary not found on PATH"},
        )
        assert osa_agent.warm_ollama() is False

    def test_exception_is_swallowed(self, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("spawn exploded")

        monkeypatch.setattr("core.llm.ensure_ollama_running", _boom)
        # Must never propagate — OSA never hard-fails on warming.
        assert osa_agent.warm_ollama() is False


# ═══════════════════════════════════════════════════════════════════════════════
# OSAToolbox — guarded, string-returning tools (no LLM needed)
# ═══════════════════════════════════════════════════════════════════════════════

def _permissive_constitution() -> Constitution:
    """A constitution that blocks nothing and requires no approval."""
    return Constitution(approval_required={}, limits={}, blocked=[], write_allowlist=[])


class TestToolbox:
    def test_system_health_returns_json_string(self, monkeypatch):
        from gui.sidecar import panels

        monkeypatch.setattr(panels, "system_health", lambda: {
            "cpu_percent": 12.5,
            "ram": {"percent": 73, "used_gb": 12.6, "total_gb": 17.2},
            "disks": [{"mount": "/", "percent": 40, "free_gb": 300}],
        })
        tb = osa_agent.OSAToolbox(constitution=_permissive_constitution())
        out = tb.system_health()
        assert '"ram_percent": 73' in out
        assert '"cpu_percent": 12.5' in out
        assert '"disk_percent": 40' in out

    def test_app_status_returns_running(self, monkeypatch):
        import core.process_manager as pm

        class _FakeMgr:
            def status(self, app_id, **k):
                return {"app_id": app_id, "running": True, "pid": 4242,
                        "port": 5173, "url": "http://localhost:5173", "error": None}

        monkeypatch.setattr(pm, "manager", _FakeMgr())
        tb = osa_agent.OSAToolbox(constitution=_permissive_constitution())
        out = tb.app_status("worldwise")
        assert '"running": true' in out
        assert '"port": 5173' in out

    def test_app_status_requires_id(self):
        tb = osa_agent.OSAToolbox(constitution=_permissive_constitution())
        assert tb.app_status("") == "ERROR: app_id required."

    def test_start_app_calls_manager(self, monkeypatch):
        import core.process_manager as pm

        class _FakeMgr:
            async def start(self, app_id):
                return {"app_id": app_id, "running": True, "pid": 9,
                        "port": 5173, "url": "http://localhost:5173", "error": None}

        monkeypatch.setattr(pm, "manager", _FakeMgr())
        tb = osa_agent.OSAToolbox(constitution=_permissive_constitution())
        out = tb.start_app("worldwise")
        assert '"running": true' in out
        assert '"app_id": "worldwise"' in out

    def test_stop_app_calls_manager(self, monkeypatch):
        import core.process_manager as pm

        class _FakeMgr:
            async def stop(self, app_id):
                return {"app_id": app_id, "running": False,
                        "killed_pids": [9], "error": None}

        monkeypatch.setattr(pm, "manager", _FakeMgr())
        tb = osa_agent.OSAToolbox(constitution=_permissive_constitution())
        out = tb.stop_app("worldwise")
        assert '"running": false' in out
        assert "9" in out

    def test_start_app_blocked_by_constitution(self):
        # 'app_start' payload contains a blocked substring → BLOCKED, no launch.
        con = Constitution(approval_required={}, limits={},
                           blocked=["worldwise"], write_allowlist=[])
        tb = osa_agent.OSAToolbox(constitution=con)
        out = tb.start_app("worldwise")
        assert out.startswith("BLOCKED:")

    def test_stop_app_approval_denied(self, monkeypatch):
        import core.process_manager as pm

        class _FakeMgr:
            async def stop(self, app_id):  # pragma: no cover — must NOT run
                raise AssertionError("stop should not run when approval denied")

        monkeypatch.setattr(pm, "manager", _FakeMgr())
        con = Constitution(approval_required={"app_stop": "Stopping an app"},
                           limits={}, blocked=[], write_allowlist=[])
        tb = osa_agent.OSAToolbox(
            constitution=con, approval_fn=lambda a, d: "deny")
        out = tb.stop_app("worldwise")
        assert out.startswith("DENIED:")

    def test_stop_app_approval_granted_runs(self, monkeypatch):
        import core.process_manager as pm

        class _FakeMgr:
            async def stop(self, app_id):
                return {"app_id": app_id, "running": False,
                        "killed_pids": [9], "error": None}

        monkeypatch.setattr(pm, "manager", _FakeMgr())
        con = Constitution(approval_required={"app_stop": "Stopping an app"},
                           limits={}, blocked=[], write_allowlist=[])
        seen = {}

        def _approve(action, desc):
            seen["action"] = action
            return "yes"

        tb = osa_agent.OSAToolbox(constitution=con, approval_fn=_approve)
        out = tb.stop_app("worldwise")
        assert seen["action"] == "app_stop"
        assert '"running": false' in out

    def test_remember_appends(self, tmp_path, monkeypatch):
        import core.soul as soul

        mem = tmp_path / "Memory.md"
        monkeypatch.setattr(soul, "memory_path", lambda: mem)
        monkeypatch.setattr(soul, "_CONFIG", tmp_path)
        tb = osa_agent.OSAToolbox(constitution=_permissive_constitution())
        out = tb.remember("Tony prefers terse status-first replies")
        assert out.startswith("Saved to memory:")
        assert "status-first" in mem.read_text()
        assert "(osa)" in mem.read_text()

    def test_event_fn_fires_on_tool_run(self, monkeypatch):
        from gui.sidecar import panels

        monkeypatch.setattr(panels, "system_health",
                            lambda: {"cpu_percent": 1, "ram": {}, "disks": []})
        events = []
        tb = osa_agent.OSAToolbox(
            constitution=_permissive_constitution(),
            event_fn=lambda phase, tool, info: events.append((phase, tool)),
        )
        tb.system_health()
        assert ("start", "system_health") in events
        assert ("end", "system_health") in events


# ═══════════════════════════════════════════════════════════════════════════════
# Routes — TestClient with the agent + checkpointer patched (no LLM / no MySQL)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoutes:
    def _client(self):
        from fastapi.testclient import TestClient
        from gui.sidecar.app import app as fastapi_app
        return TestClient(fastapi_app)

    def test_state_shape(self, monkeypatch):
        from core import llm
        monkeypatch.setattr(llm, "ollama_up", lambda *a, **k: True)
        body = self._client().get("/api/osa/state").json()
        assert body["ready"] is True
        assert body["ollama_up"] is True
        assert "active_model" in body
        assert body["soul"] == "Soul_OSA.md"

    def test_chat_requires_message(self):
        r = self._client().post("/api/osa/chat", json={"message": "   "})
        assert r.status_code == 400

    def test_chat_runs_patched_agent(self, monkeypatch):
        from agents import osa_agent as oa
        from core import llm, memory

        # No Ollama warming, deterministic route + resolve.
        monkeypatch.setattr(oa, "warm_ollama", lambda: True)
        monkeypatch.setattr(oa, "pick_model", lambda msg, **k: "local")
        monkeypatch.setattr(llm, "resolve", lambda alias: "qwen2.5:7b-instruct")

        # No real MySQL checkpointer.
        monkeypatch.setattr(memory, "checkpointer_conn", lambda: None)
        monkeypatch.setattr(memory, "get_checkpointer", lambda conn=None: object())

        class _FakeMsg:
            def __init__(self, content):
                self.content = content
                self.tool_calls = []

        class _FakeAgent:
            def invoke(self, payload, config=None):
                # thread_id must be threaded through for durable checkpointing.
                assert config["configurable"]["thread_id"]
                return {"messages": [_FakeMsg("RAM's at 73%. Nothing alarming.")]}

        monkeypatch.setattr(oa, "build_agent",
                            lambda model_id, **k: _FakeAgent())

        r = self._client().post("/api/osa/chat", json={"message": "how's my memory?"})
        assert r.status_code == 200
        data = r.json()
        assert data["reply"] == "RAM's at 73%. Nothing alarming."
        assert data["model"] == "qwen2.5:7b-instruct"
        assert data["route"] == "local"
        assert data["thread_id"].startswith("osa-")

    def test_chat_preserves_thread_id(self, monkeypatch):
        from agents import osa_agent as oa
        from core import llm, memory

        monkeypatch.setattr(oa, "warm_ollama", lambda: False)
        monkeypatch.setattr(oa, "pick_model", lambda msg, **k: "default")
        monkeypatch.setattr(llm, "resolve", lambda alias: "claude-sonnet-4-6")
        monkeypatch.setattr(memory, "checkpointer_conn", lambda: None)
        monkeypatch.setattr(memory, "get_checkpointer", lambda conn=None: object())

        class _FakeMsg:
            content = "Understood, Sir."
            tool_calls = []

        class _FakeAgent:
            def invoke(self, payload, config=None):
                return {"messages": [_FakeMsg()]}

        monkeypatch.setattr(oa, "build_agent", lambda model_id, **k: _FakeAgent())

        r = self._client().post(
            "/api/osa/chat",
            json={"message": "launch worldwise", "thread_id": "osa-keepme"})
        assert r.json()["thread_id"] == "osa-keepme"

    def test_chat_graph_failure_is_502(self, monkeypatch):
        from agents import osa_agent as oa
        from core import llm, memory

        monkeypatch.setattr(oa, "warm_ollama", lambda: True)
        monkeypatch.setattr(oa, "pick_model", lambda msg, **k: "default")
        monkeypatch.setattr(llm, "resolve", lambda alias: "claude-sonnet-4-6")
        monkeypatch.setattr(memory, "checkpointer_conn", lambda: None)
        monkeypatch.setattr(memory, "get_checkpointer", lambda conn=None: object())

        def _boom(model_id, **k):
            raise RuntimeError("model unavailable")

        monkeypatch.setattr(oa, "build_agent", _boom)
        r = self._client().post("/api/osa/chat", json={"message": "hello there friend"})
        assert r.status_code == 502


# ═══════════════════════════════════════════════════════════════════════════════
# Soul fork — governor/briefing keep the plain shared soul; OSA loads the sharp one
# ═══════════════════════════════════════════════════════════════════════════════

class TestSoulFork:
    def test_default_soul_is_plain_shared(self):
        from core import soul
        # No-arg (governor/briefing) resolves the shared Soul.md.
        assert soul.soul_path().name == "Soul.md"
        preamble = soul.identity_preamble()
        assert preamble  # non-empty
        assert "Soul (identity)" in preamble

    def test_osa_soul_loads_forked_file(self):
        from core import soul
        p = soul.soul_path(soul_name="Soul_OSA.md")
        assert p.name == "Soul_OSA.md"
        assert p.exists(), "Soul_OSA.md fork must exist"
        text = soul.load_soul("Soul_OSA.md")
        # The sharp persona mentions the wake word + spoken/HUD framing.
        assert "OSA" in text

    def test_osa_and_shared_souls_differ(self):
        from core import soul
        assert soul.load_soul() != soul.load_soul("Soul_OSA.md")

    def test_osa_preamble_uses_forked_soul(self):
        from core import soul
        osa_pre = soul.identity_preamble(soul_name="Soul_OSA.md")
        plain_pre = soul.identity_preamble()
        assert osa_pre and plain_pre
        assert osa_pre != plain_pre
