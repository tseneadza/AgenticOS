"""Phase 11c — unit tests for the REST API + full async orchestration.

    * The REST shape tests (/templates, /subfolders) run a tiny FastAPI app
      that mounts ONLY ``api_projects.router`` — app.py's heavy startup hooks
      are never imported; they need no DB or network.
    * The /port-check + orchestration tests are DB-backed (Phase 13f — against
      the ``agenticos_test`` MySQL schema via the conftest fixtures, no more
      the
      agenticos_test MySQL schema) and skip cleanly when MySQL is down. GitHub creation is
      stubbed to None (no-token path), folders redirect to ``tmp_path``, and
      port allocation is made deterministic.

Run from the repo root using the repo venv:

    .venv/bin/python -m pytest gui/sidecar/tests/test_phase11c.py -v
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure the repo root is importable. tests/ -> sidecar -> gui -> ROOT
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gui.sidecar import project_manager as pm  # noqa: E402
from gui.sidecar.routes import api_projects  # noqa: E402


# ── test client (router-only, no app.py startup hooks) ────────────────────────

@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(api_projects.router)
    return TestClient(app)


# ── REST: /templates + /subfolders (no DB) ────────────────────────────────────

def test_list_templates_shape(client):
    resp = client.get("/api/projects/templates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == len(body["templates"])
    assert body["total"] >= 10
    for tpl in body["templates"]:
        assert set(tpl) == {"id", "name", "description", "icon", "category"}
    ids = {t["id"] for t in body["templates"]}
    assert {"fastapi", "react", "cli", "monorepo"} <= ids


def test_list_subfolders_shape(client, monkeypatch):
    monkeypatch.setattr(
        pm,
        "scan_codehome_structure",
        lambda: {"suggested": ["apps"], "all": ["apps", "tools"], "custom_available": True},
    )
    resp = client.get("/api/projects/subfolders")
    assert resp.status_code == 200
    body = resp.json()
    assert body["custom_available"] is True
    assert "apps" in body["all"]


# ── REST: /port-check (MySQL-backed ledger) ───────────────────────────────────

def test_port_check_free(client, monkeypatch, mysql_engine):
    from sqlalchemy.orm import sessionmaker

    from gui.sidecar import models  # noqa: F401  (registers Port on Base)

    # Phase 13f: bind to the ``agenticos_test`` MySQL schema (was in-memory
    # MySQL). Clear any existing ports rows first for determinism.
    Session = sessionmaker(bind=mysql_engine, future=True)
    _cleanup = Session()
    try:
        _cleanup.query(models.Port).delete()
        _cleanup.commit()
    finally:
        _cleanup.close()

    # Point the route's DB access at the MySQL sessionmaker + neutralise probe.
    import gui.sidecar.db as db_mod
    monkeypatch.setattr(db_mod, "SessionLocal", Session)
    monkeypatch.setattr(pm, "_port_in_use", lambda port: False)

    resp = client.get("/api/projects/port-check", params={"port": 5250})
    assert resp.status_code == 200
    body = resp.json()
    assert body["port"] == 5250
    assert body["available"] is True


# ── orchestration: create_project_full end-to-end (MySQL + no network) ─────────

def test_create_project_full(monkeypatch, tmp_path, db_session):
    from gui.sidecar import models  # noqa: F401  (registers Project + Port)
    import gui.sidecar.github_integration as gh

    # Folders land under tmp_path/<subfolder>/<name>.
    monkeypatch.setattr(pm, "_CODEHOME", tmp_path)

    # Deterministic port allocation: nothing reserved, nothing "in use" -> 5200.
    monkeypatch.setattr(pm, "_registry_ports", lambda: set())
    monkeypatch.setattr(pm, "_port_in_use", lambda port: False)

    # No-token GitHub path: create_project_full imports setup_repo lazily from
    # gui.sidecar.github_integration, so patch that module attribute.
    monkeypatch.setattr(gh, "setup_repo", lambda *a, **k: None)

    # Phase 13f: use the conftest ``db_session`` (agenticos_test MySQL schema)
    # for both allocate_port + Project registration (was in-memory SQLite).
    session = db_session

    events: list[tuple[str, str]] = []

    async def emit(step, status, message=None):
        events.append((step, status))

    try:
        result = asyncio.run(
            pm.create_project_full(
                name="my-app",
                template="monorepo",   # not python -> no venv/subprocess
                subfolder="apps",
                description="A test project",
                emit=emit,
                session=session,
            )
        )

        # ── result contract ──────────────────────────────────────────────────
        assert result["success"] is True
        assert result["port"] == 5200
        assert result["project_id"] == "my-app"
        assert result["github_url"] is None
        assert result["pushed"] is False
        assert any("github" in w.lower() for w in result["warnings"]), result["warnings"]

        # ── on-disk artefacts ────────────────────────────────────────────────
        project_dir = tmp_path / "apps" / "my-app"
        assert project_dir.is_dir()
        app_json = project_dir / "app.json"
        assert app_json.exists()
        parsed = json.loads(app_json.read_text())
        assert parsed["id"] == "my-app"
        assert (project_dir / "README.md").exists()
        assert (project_dir / ".git").is_dir()  # init_git_repo ran real git

        # ── ledger row present in the injected ledger session ────────────────
        row = session.query(models.Project).filter_by(id="my-app").first()
        assert row is not None
        assert row.port == 5200
        assert row.template == "monorepo"

        # ── emit protocol: stable step names for critical milestones ─────────
        assert ("folder", "complete") in events
        assert ("port", "complete") in events
        assert ("files", "complete") in events
        assert ("register", "complete") in events
        assert ("github", "warning") in events
        # monorepo is not a python template -> no venv step emitted.
        assert not any(step == "venv" for step, _ in events)
    finally:
        # db_session fixture owns the session lifecycle (wipe + close).
        pass
