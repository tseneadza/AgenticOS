"""Phase 13d tests — Projects GUI backend surface.

The GUI work itself is covered by vitest (ProjectsView.test.jsx); this file
covers the one new sidecar endpoint added for the view:

    GET /api/apps/{app_id}/launch-plan

  * configured=True with resolved steps when app_commands rows exist
  * configured=False + reason for legacy-launch apps (no app_commands —
    locked decision: agenticos/hub intentionally stay unconfigured)
  * available=False degradation when the DB layer raises (MySQL down)
  * 404 for apps unknown to the registry

Runs against the real MySQL ``agenticos_test`` schema (conftest.py) per the
MySQL-everywhere testing rule.
"""
from __future__ import annotations

import pytest

from gui.sidecar.models import AppCommand, Port, Project


@pytest.fixture()
def patched_sessionlocal(mysql_engine, monkeypatch):
    """Point launch_config's default sessions at the agenticos_test schema."""
    from sqlalchemy.orm import sessionmaker
    import gui.sidecar.db as db
    monkeypatch.setattr(
        db, "SessionLocal",
        sessionmaker(bind=mysql_engine, autoflush=False, future=True),
    )


def _registry_stub(app_id, tmp_path):
    entry = {"id": app_id, "app_path": str(tmp_path),
             "start_command": ["sleep", "1"],
             "expected_port": None, "venv": None}
    return lambda aid: entry if aid == app_id else None


class TestLaunchPlanRoute:
    def test_configured_plan_returned(
            self, db_session, patched_sessionlocal, monkeypatch, tmp_path):
        from fastapi.testclient import TestClient
        from core import app_registry
        from gui.sidecar.app import app as fastapi_app

        app_id = "plan-app"
        monkeypatch.setattr(app_registry, "get", _registry_stub(app_id, tmp_path))

        db_session.add(Project(id=app_id, name=app_id, path=str(tmp_path),
                               template="imported", created_by="discovered"))
        db_session.add(Port(port=5555, app_id=app_id, port_type="frontend"))
        db_session.add(AppCommand(
            app_id=app_id, step_order=1, command="npm",
            args=["run", "dev", "--", "--port", "{frontend_port}"],
            working_directory=None, port_type="frontend",  # None → app root
        ))
        db_session.commit()

        body = TestClient(fastapi_app).get(
            f"/api/apps/{app_id}/launch-plan").json()
        assert body["available"] is True
        assert body["configured"] is True
        assert body["total"] == 1
        step = body["steps"][0]
        assert step["command"] == "npm"
        assert "5555" in " ".join(step["args"])
        assert step["cwd"] == str(tmp_path)
        assert step["port"] == 5555

    def test_unconfigured_app_degrades_to_reason(
            self, db_session, patched_sessionlocal, monkeypatch, tmp_path):
        """Legacy-launch apps (no app_commands) get configured=False, not 500."""
        from fastapi.testclient import TestClient
        from core import app_registry
        from gui.sidecar.app import app as fastapi_app

        app_id = "legacy-app"
        monkeypatch.setattr(app_registry, "get", _registry_stub(app_id, tmp_path))
        db_session.add(Project(id=app_id, name=app_id, path=str(tmp_path),
                               template="imported", created_by="discovered"))
        db_session.commit()

        r = TestClient(fastapi_app).get(f"/api/apps/{app_id}/launch-plan")
        assert r.status_code == 200
        body = r.json()
        assert body["available"] is True
        assert body["configured"] is False
        assert body["steps"] == [] and body["total"] == 0
        assert "app_commands" in body["reason"]

    def test_db_down_degrades_available_false(self, monkeypatch, tmp_path):
        from fastapi.testclient import TestClient
        from core import app_registry
        from gui.sidecar import launch_config
        from gui.sidecar.app import app as fastapi_app

        app_id = "down-app"
        monkeypatch.setattr(app_registry, "get", _registry_stub(app_id, tmp_path))

        def _boom(aid, session=None):
            raise RuntimeError("MySQL down")
        monkeypatch.setattr(launch_config, "build_launch_command", _boom)

        r = TestClient(fastapi_app).get(f"/api/apps/{app_id}/launch-plan")
        assert r.status_code == 200
        body = r.json()
        assert body["available"] is False
        assert body["configured"] is False and body["steps"] == []

    def test_unknown_app_is_404(self, monkeypatch):
        from fastapi.testclient import TestClient
        from core import app_registry
        from gui.sidecar.app import app as fastapi_app

        monkeypatch.setattr(app_registry, "get", lambda aid: None)
        r = TestClient(fastapi_app).get("/api/apps/nope/launch-plan")
        assert r.status_code == 404
