"""Phase 14b tests — OSA new tools + destructive-action confirmation.

Two layers, both LLM-free:

* **Toolbox** — the new read-only tools (``apps_health``, ``list_projects``)
  are called directly with their underlying data sources patched, and the
  ``app_stop`` guard is exercised through the constitution (denied vs approved).
* **Confirm flow** — the affirmative/negative + pending-store helpers are unit
  tested directly, and the two-turn confirm is driven through the FastAPI
  ``/api/osa/chat`` route with the agent + checkpointer patched (no live LLM or
  MySQL): the destructive request records a pending + sets ``awaiting_confirm``,
  a following affirmative approves + clears, a bare affirmative with no pending
  never approves, and a negative clears.

Mirrors the Phase 14a style (``test_phase14a_osa.py``): guard-path assertions,
monkeypatched adapters, and TestClient route checks.
"""
from __future__ import annotations

import pytest

from agents import osa_agent
from core.constitution import Constitution
from gui.sidecar.routes import api_osa


def _permissive_constitution() -> Constitution:
    """A constitution that blocks nothing and requires no approval."""
    return Constitution(approval_required={}, limits={}, blocked=[], write_allowlist=[])


@pytest.fixture(autouse=True)
def _clean_pending():
    """Every test starts (and ends) with an empty pending-confirm store."""
    api_osa._PENDING_CONFIRM.clear()
    yield
    api_osa._PENDING_CONFIRM.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# New read-only tools — apps_health / list_projects
# ═══════════════════════════════════════════════════════════════════════════════

class TestNewTools:
    def test_apps_health_summarizes(self, monkeypatch):
        from gui.sidecar import launch_config

        monkeypatch.setattr(launch_config, "list_all_health", lambda: {
            "apps": {
                "worldwise": {"healthy": True,
                              "ports": [{"port": 5173, "is_healthy": True,
                                         "last_health_check": "now"}]},
                "keno": {"healthy": False,
                         "ports": [{"port": 8080, "is_healthy": False,
                                    "last_health_check": "now"}]},
            },
            "total": 2,
        })
        tb = osa_agent.OSAToolbox(constitution=_permissive_constitution())
        out = tb.apps_health()
        import json as _json
        parsed = _json.loads(out)
        assert parsed["total"] == 2
        assert parsed["apps"]["worldwise"]["healthy"] is True
        assert parsed["apps"]["keno"]["healthy"] is False
        assert parsed["unhealthy"] == ["keno"]

    def test_apps_health_empty(self, monkeypatch):
        from gui.sidecar import launch_config

        monkeypatch.setattr(launch_config, "list_all_health",
                            lambda: {"apps": {}, "total": 0})
        tb = osa_agent.OSAToolbox(constitution=_permissive_constitution())
        out = tb.apps_health()
        assert '"total": 0' in out
        assert '"unhealthy": []' in out

    def test_list_projects_returns_compact_list(self, monkeypatch):
        import gui.sidecar.routes.api_osa  # noqa: F401 — ensure module importable

        class _Proj:
            def __init__(self, name, template, subfolder, port):
                self.name = name
                self.template = template
                self.subfolder = subfolder
                self.port = port
                self.created_at = None

        class _Query:
            def __init__(self, rows):
                self._rows = rows

            def order_by(self, *a, **k):
                return self

            def all(self):
                return self._rows

        class _Session:
            def __init__(self, rows):
                self._rows = rows

            def query(self, *a, **k):
                return _Query(self._rows)

            def close(self):
                pass

        rows = [_Proj("worldwise", "vite-react", "apps", 5173)]
        import gui.sidecar.db as db
        monkeypatch.setattr(db, "SessionLocal", lambda: _Session(rows))

        tb = osa_agent.OSAToolbox(constitution=_permissive_constitution())
        out = tb.list_projects()
        assert '"total": 1' in out
        assert '"worldwise"' in out
        assert '"vite-react"' in out
        assert '"port": 5173' in out

    def test_list_projects_degrades_when_db_down(self, monkeypatch):
        import gui.sidecar.db as db

        def _boom():
            raise RuntimeError("db down")

        monkeypatch.setattr(db, "SessionLocal", _boom)
        tb = osa_agent.OSAToolbox(constitution=_permissive_constitution())
        out = tb.list_projects()
        assert '"available": false' in out
        assert '"total": 0' in out

    def test_apps_health_and_list_projects_registered(self):
        # Both new tools must be bound so the model can call them.
        tb = osa_agent.OSAToolbox(constitution=_permissive_constitution())
        names = {t.name for t in osa_agent.build_tools(tb)}
        assert "apps_health" in names
        assert "list_projects" in names


# ═══════════════════════════════════════════════════════════════════════════════
# app_stop is now approval-required — DENIED on deny, runs on approve
# ═══════════════════════════════════════════════════════════════════════════════

class TestAppStopGuard:
    def test_app_stop_in_live_constitution(self):
        # The real constitution now gates app_stop behind approval.
        con = Constitution.load()
        assert "app_stop" in con.approval_required

    def test_stop_app_denied_when_not_approved(self, monkeypatch):
        import core.process_manager as pm

        class _FakeMgr:
            async def stop(self, app_id):  # pragma: no cover — must NOT run
                raise AssertionError("stop must not run when denied")

        monkeypatch.setattr(pm, "manager", _FakeMgr())
        con = Constitution.load()  # app_stop now approval-required
        tb = osa_agent.OSAToolbox(constitution=con, approval_fn=lambda a, d: "deny")
        out = tb.stop_app("worldwise")
        assert out.startswith("DENIED:")

    def test_stop_app_runs_when_approved(self, monkeypatch):
        import core.process_manager as pm

        class _FakeMgr:
            async def stop(self, app_id):
                return {"app_id": app_id, "running": False,
                        "killed_pids": [9], "error": None}

        monkeypatch.setattr(pm, "manager", _FakeMgr())
        con = Constitution.load()
        tb = osa_agent.OSAToolbox(constitution=con, approval_fn=lambda a, d: "approve")
        out = tb.stop_app("worldwise")
        assert '"running": false' in out


# ═══════════════════════════════════════════════════════════════════════════════
# Confirm-flow helpers — pure, unit-testable
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfirmHelpers:
    @pytest.mark.parametrize("msg", [
        "yes", "Yes", "yes sir", "confirm", "do it", "go ahead", "yep",
        "sure", "proceed", "Confirmed!",
    ])
    def test_affirmatives(self, msg):
        assert api_osa.is_affirmative(msg)

    @pytest.mark.parametrize("msg", [
        "no", "cancel", "nope", "never mind", "abort", "No thanks",
    ])
    def test_negatives(self, msg):
        assert api_osa.is_negative(msg)

    def test_command_is_neither(self):
        assert not api_osa.is_affirmative("stop worldwise")
        assert not api_osa.is_negative("stop worldwise")
        assert not api_osa.is_affirmative("how's my memory?")

    def test_pending_store_roundtrip(self):
        assert api_osa.get_pending("t1") is None
        api_osa.record_pending("t1", "app_stop", "Stopping a running app")
        entry = api_osa.get_pending("t1")
        assert entry and entry["action"] == "app_stop"
        api_osa.clear_pending("t1")
        assert api_osa.get_pending("t1") is None

    def test_pending_expires(self, monkeypatch):
        api_osa.record_pending("t2", "app_stop", "Stopping a running app")
        # Fast-forward past the TTL.
        entry = api_osa._PENDING_CONFIRM["t2"]
        entry["ts"] -= api_osa._CONFIRM_TTL_SECONDS + 1
        assert api_osa.get_pending("t2") is None
        # Pruned as a side effect.
        assert "t2" not in api_osa._PENDING_CONFIRM


# ═══════════════════════════════════════════════════════════════════════════════
# Confirm flow through the route — agent + checkpointer patched (no LLM/MySQL)
# ═══════════════════════════════════════════════════════════════════════════════

class _FakeMsg:
    def __init__(self, content):
        self.content = content
        self.tool_calls = []


def _patch_route(monkeypatch, *, capture: dict, calls_tool=True):
    """Patch the OSA route's deps; the fake agent invokes the approval_fn.

    ``capture`` records the approval decision the route handed the agent so
    tests can assert deny-vs-approve without a real guarded tool. When
    ``calls_tool`` is False the fake model just acknowledges (as it would on a
    'no'/'cancel' turn) and never issues the guarded action.
    """
    from agents import osa_agent as oa
    from core import llm, memory

    monkeypatch.setattr(oa, "warm_ollama", lambda: True)
    monkeypatch.setattr(oa, "pick_model", lambda msg, **k: "default")
    monkeypatch.setattr(llm, "resolve", lambda alias: "claude-sonnet-4-6")
    monkeypatch.setattr(memory, "checkpointer_conn", lambda: None)
    monkeypatch.setattr(memory, "get_checkpointer", lambda conn=None: object())

    class _FakeAgent:
        def __init__(self, approval_fn):
            self._approval_fn = approval_fn

        def invoke(self, payload, config=None):
            if not calls_tool:
                # Model acknowledges a cancel; no guarded action is issued.
                return {"messages": [_FakeMsg("Understood, Sir. Standing down.")]}
            # Simulate the model issuing the guarded destructive action:
            # call the approval_fn exactly as OSAToolbox._guarded would.
            decision = self._approval_fn("app_stop", "Stopping a running app")
            capture["decision"] = decision
            if str(decision).lower() in ("approve", "yes", "y", "ok", "approved"):
                return {"messages": [_FakeMsg("Understood, Sir. Stopping worldwise.")]}
            return {"messages": [_FakeMsg("That will stop worldwise — confirm?")]}

    monkeypatch.setattr(
        oa, "build_agent",
        lambda model_id, approval_fn=None, **k: _FakeAgent(approval_fn),
    )


def _client():
    from fastapi.testclient import TestClient
    from gui.sidecar.app import app as fastapi_app
    return TestClient(fastapi_app)


class TestConfirmRoute:
    def test_destructive_request_awaits_confirm(self, monkeypatch):
        capture: dict = {}
        _patch_route(monkeypatch, capture=capture)

        r = _client().post(
            "/api/osa/chat",
            json={"message": "stop worldwise", "thread_id": "osa-conf1"})
        assert r.status_code == 200
        data = r.json()
        assert capture["decision"] == "deny"
        assert data["awaiting_confirm"] is True
        assert data["confirmed"] is False
        assert data["pending_action"]["action"] == "app_stop"
        # A pending entry was recorded for this thread.
        assert api_osa.get_pending("osa-conf1") is not None

    def test_affirmative_with_pending_confirms(self, monkeypatch):
        capture: dict = {}
        _patch_route(monkeypatch, capture=capture)
        # Seed a live pending as though turn 1 already ran.
        api_osa.record_pending("osa-conf2", "app_stop", "Stopping a running app")

        r = _client().post(
            "/api/osa/chat",
            json={"message": "yes sir", "thread_id": "osa-conf2"})
        data = r.json()
        assert capture["decision"] == "approve"
        assert data["confirmed"] is True
        assert data["awaiting_confirm"] is False
        # Pending cleared after confirmation.
        assert api_osa.get_pending("osa-conf2") is None

    def test_bare_affirmative_without_pending_does_not_approve(self, monkeypatch):
        capture: dict = {}
        _patch_route(monkeypatch, capture=capture)

        # No pending for this thread — a bare "yes" must NOT approve.
        r = _client().post(
            "/api/osa/chat",
            json={"message": "yes", "thread_id": "osa-nopending"})
        data = r.json()
        assert capture["decision"] == "deny"
        assert data["confirmed"] is False

    def test_negative_clears_pending(self, monkeypatch):
        capture: dict = {}
        _patch_route(monkeypatch, capture=capture, calls_tool=False)
        api_osa.record_pending("osa-conf3", "app_stop", "Stopping a running app")

        r = _client().post(
            "/api/osa/chat",
            json={"message": "cancel", "thread_id": "osa-conf3"})
        data = r.json()
        assert data["confirmed"] is False
        # Cancelling drops the pending entry.
        assert api_osa.get_pending("osa-conf3") is None
