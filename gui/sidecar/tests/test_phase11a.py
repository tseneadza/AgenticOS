"""Phase 11a — unit tests for Project Creation Scaffolding.

    * template_registry is pure (no DB / FS / network) and imported directly.
    * project_manager.allocate_port is exercised against the ``agenticos_test``
      MySQL schema (via the conftest ``db_session`` fixture; Phase 13f — no
      more in-memory SQLite), with the app_registry lookup and TCP probe
      monkeypatched out. These DB-backed tests skip cleanly when MySQL is down.

Run from the repo root using the repo venv:

    .venv/bin/python -m pytest gui/sidecar/tests/test_phase11a.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure the repo root is importable (so ``gui.sidecar.*`` / ``core.*`` resolve)
# regardless of the pytest invocation directory. tests/ -> sidecar -> gui -> ROOT
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gui.sidecar import template_registry as tr  # noqa: E402
from gui.sidecar import project_manager as pm  # noqa: E402

# tomllib is stdlib on 3.11+; guard so 3.10 still runs the rest of the suite.
try:
    import tomllib  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore


# ── template_registry tests ───────────────────────────────────────────────────

@pytest.mark.parametrize("template", ["fastapi", "react", "cli"])
def test_generate_files_no_residual_tokens(template):
    files = tr.generate_files(
        template, "my-project", "A test project", 5200
    )
    assert files, f"{template} produced no files"
    for rel_path, content in files.items():
        assert "{{" not in content, f"{template}:{rel_path} has dangling '{{{{'"
        assert "}}" not in content, f"{template}:{rel_path} has dangling '}}}}'"


@pytest.mark.parametrize("template", ["fastapi", "react"])
def test_app_json_web_block_present(template):
    files = tr.generate_files(template, "my-project", "desc", 5250)
    assert "app.json" in files
    app = json.loads(files["app.json"])
    assert "web" in app, f"{template} app.json should have a web block"
    assert app["web"]["port"] == 5250


def test_app_json_cli_has_no_web_block():
    files = tr.generate_files("cli", "my-tool", "desc", 5300)
    app = json.loads(files["app.json"])
    assert "web" not in app, "cli app.json must not have a web block"
    assert app["type"] == "cli"


def test_generate_pyproject_toml_valid():
    out = tr.generate_pyproject_toml(
        "my-project", "A test project", ["fastapi", "uvicorn"],
    )
    # No dangling version operator like 'fastapi>=' with nothing after it.
    assert '">="' not in out, "pyproject.toml has a dangling '>=' dependency"
    if tomllib is not None:
        parsed = tomllib.loads(out)
        assert parsed["project"]["name"] == "my-project"
        assert "fastapi" in parsed["project"]["dependencies"]


# ── validate_project_name tests ───────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "a",
    "app",
    "my-project",
    "my-cool-app-2",
    "abc123",
    "x" * 64,
])
def test_validate_project_name_valid(name):
    assert pm.validate_project_name(name) is True


@pytest.mark.parametrize("name", [
    "",                 # empty
    "1project",         # starts with digit
    "-project",         # leading hyphen
    "project-",         # trailing hyphen
    "my--project",      # double hyphen
    "My-Project",       # uppercase
    "my_project",       # underscore
    "my project",       # space
    "proj.ect",         # dot
    "x" * 65,           # too long
    "café",             # non-ascii
])
def test_validate_project_name_invalid(name):
    assert pm.validate_project_name(name) is False


# ── scan_codehome_structure tests ─────────────────────────────────────────────

def test_scan_codehome_structure_from_ledger(ledger_session):
    """Subfolders are self-curated from the projects ledger (not the filesystem)."""
    from gui.sidecar.models import Project

    # Fresh ledger: no project folders yet, but root + custom always offered.
    empty = pm.scan_codehome_structure(session=ledger_session)
    assert empty["all"] == []
    assert empty["suggested"] == []
    assert empty["custom_available"] is True
    assert empty["root_available"] is True

    # Once projects exist, their distinct subfolders surface (root "" excluded).
    ledger_session.add_all([
        Project(id="a", name="a", path="/x/a", subfolder="The Sciences", template="cli", port=5201),
        Project(id="b", name="b", path="/x/b", subfolder="Games", template="cli", port=5202),
        Project(id="c", name="c", path="/x/c", subfolder="Games", template="cli", port=5203),
        Project(id="d", name="d", path="/x/d", subfolder="", template="cli", port=5204),  # root
    ])
    ledger_session.commit()

    res = pm.scan_codehome_structure(session=ledger_session)
    assert set(res["all"]) == {"Games", "The Sciences"}
    assert res["all"] == sorted(res["all"], key=str.lower)  # sorted, case-insensitive
    assert res["root_available"] is True


def test_scan_codehome_structure_db_unavailable(monkeypatch):
    """A DB failure degrades to an empty list; root + custom stay available."""
    import gui.sidecar.db as db

    def _boom():
        raise RuntimeError("no db")

    monkeypatch.setattr(db, "SessionLocal", _boom)
    res = pm.scan_codehome_structure()
    assert res["all"] == []
    assert res["suggested"] == []
    assert res["custom_available"] is True
    assert res["root_available"] is True


# ── allocate_port tests (agenticos_test MySQL ledger) ─────────────────────────

@pytest.fixture()
def ledger_session(db_session, monkeypatch):
    """A SQLAlchemy session on the ``agenticos_test`` MySQL schema.

    Phase 13f: converted off in-memory SQLite to the conftest ``db_session``
    fixture (which wipes every table after each test, so the ledger starts
    clean). Skips cleanly when MySQL is down. app_registry.get_all and
    pm._port_in_use are neutralised so allocation is deterministic.

    Renamed from ``sqlite_session`` in the 2026-07-19 all-MySQL sweep.
    """
    # Neutralise external influences on the unavailable-port set.
    from core import app_registry
    monkeypatch.setattr(app_registry, "get_all", lambda: [])
    monkeypatch.setattr(pm, "_port_in_use", lambda port: False)

    yield db_session


def test_allocate_port_sequential(ledger_session):
    first = pm.allocate_port("app-a", session=ledger_session)
    second = pm.allocate_port("app-b", session=ledger_session)
    assert first == 5200
    assert second == 5201


def test_allocate_port_preferred_free(ledger_session):
    port = pm.allocate_port("app-x", preferred_port=5432, session=ledger_session)
    assert port == 5432


def test_allocate_port_preferred_taken_falls_back(ledger_session):
    # Claim 5200 first, then request it as a preferred port — should fall back.
    pm.allocate_port("app-a", preferred_port=5200, session=ledger_session)
    port = pm.allocate_port("app-b", preferred_port=5200, session=ledger_session)
    assert port == 5201


def test_allocate_port_skips_registry_ports(ledger_session, monkeypatch):
    from core import app_registry
    monkeypatch.setattr(
        app_registry, "get_all",
        lambda: [{"id": "other", "expected_port": 5200}],
    )
    port = pm.allocate_port("app-a", session=ledger_session)
    assert port == 5201  # 5200 reserved by the registry
