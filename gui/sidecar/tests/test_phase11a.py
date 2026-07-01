"""Phase 11a — unit tests for Project Creation Scaffolding.

These tests are self-contained and MUST NOT require a live MySQL server:
    * template_registry is pure (no DB / FS / network) and imported directly.
    * project_manager.allocate_port is exercised against an in-memory SQLite
      engine, with the app_registry lookup and TCP probe monkeypatched out.

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

def test_scan_codehome_structure_shape(monkeypatch, tmp_path):
    home = tmp_path
    codehome = home / "Codehome"
    (codehome / "apps").mkdir(parents=True)
    (codehome / "tools").mkdir()
    (codehome / "misc").mkdir()
    (codehome / ".git").mkdir()          # hidden — skipped
    (codehome / "node_modules").mkdir()  # noise — skipped
    (codehome / "readme.txt").write_text("not a dir")

    monkeypatch.setattr(pm.Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(pm, "_CODEHOME", codehome)

    result = pm.scan_codehome_structure()
    assert result["custom_available"] is True
    assert set(result["suggested"]) == {"apps", "tools"}
    assert "misc" in result["all"]
    assert ".git" not in result["all"]
    assert "node_modules" not in result["all"]
    assert "readme.txt" not in result["all"]


def test_scan_codehome_structure_missing(monkeypatch, tmp_path):
    codehome = tmp_path / "Codehome"  # does not exist
    monkeypatch.setattr(pm, "_CODEHOME", codehome)

    result = pm.scan_codehome_structure()
    assert result["all"] == []
    assert result["suggested"] == ["apps"]  # fallback
    assert result["custom_available"] is True


# ── allocate_port tests (in-memory SQLite) ────────────────────────────────────

@pytest.fixture()
def sqlite_session(monkeypatch):
    """A SQLAlchemy session bound to a fresh in-memory SQLite DB.

    The ``ports`` table is materialised from the real Port model, so this never
    touches MySQL. app_registry.get_all and pm._port_in_use are neutralised.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from gui.sidecar.db import Base
    from gui.sidecar import models  # noqa: F401  (registers Port on Base)

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    # Neutralise external influences on the unavailable-port set.
    from core import app_registry
    monkeypatch.setattr(app_registry, "get_all", lambda: [])
    monkeypatch.setattr(pm, "_port_in_use", lambda port: False)

    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_allocate_port_sequential(sqlite_session):
    first = pm.allocate_port("app-a", session=sqlite_session)
    second = pm.allocate_port("app-b", session=sqlite_session)
    assert first == 5200
    assert second == 5201


def test_allocate_port_preferred_free(sqlite_session):
    port = pm.allocate_port("app-x", preferred_port=5432, session=sqlite_session)
    assert port == 5432


def test_allocate_port_preferred_taken_falls_back(sqlite_session):
    # Claim 5200 first, then request it as a preferred port — should fall back.
    pm.allocate_port("app-a", preferred_port=5200, session=sqlite_session)
    port = pm.allocate_port("app-b", preferred_port=5200, session=sqlite_session)
    assert port == 5201


def test_allocate_port_skips_registry_ports(sqlite_session, monkeypatch):
    from core import app_registry
    monkeypatch.setattr(
        app_registry, "get_all",
        lambda: [{"id": "other", "expected_port": 5200}],
    )
    port = pm.allocate_port("app-a", session=sqlite_session)
    assert port == 5201  # 5200 reserved by the registry
