# Session Continuation — Phase 11a Foundation SHIPPED ✅

**Last Updated:** 2026-07-01 (Phase 11a Implementation Session)
**Status:** ✅ Phase 10 SHIPPED / Phase 11 DESIGN LOCKED / **Phase 11a foundation modules BUILT (tests unrun)**

---

## ✅ Phase 11a — Foundation Modules Implemented

Built via subagents this session. Files match the existing codebase conventions
(filesystem-scanned app registry, `web.port` app.json schema) — the earlier
draft stubs in `PROJECT_CREATION_PLAN.md` were reconciled against reality before
building. Design decisions confirmed with Tony: **SQLAlchemy** data layer, a
dedicated **`ports`** table, and a **`projects`** table.

### Files created

1. **`gui/sidecar/db.py`** — SQLAlchemy layer that COEXISTS with the legacy
   `mysql.connector` code (legacy untouched, no Alembic). Reads the same
   `~/.agentic-os/.env` MYSQL_* vars as `news_db`/`tasks_db`.
   - Exports: `Base`, `engine`, `SessionLocal`, `get_session()`, `init_db()`,
     `is_available()`.
   - `init_db()` self-bootstraps: `CREATE DATABASE IF NOT EXISTS` → import models
     → `Base.metadata.create_all(engine)`. Guarded so a missing/unreachable
     MySQL only logs a warning (never blocks sidecar startup). Import-safe with
     no live DB (unit tests bind models to in-memory SQLite).

2. **`gui/sidecar/models.py`** — `from gui.sidecar.db import Base`.
   - `Project` (table `projects`): id PK, name, description, path (unique),
     subfolder, template, port, github_repo_url, created_at, created_by='osa';
     indexes on subfolder/template/created_at.
   - `Port` (table `ports`): port PK (autoincrement=False — the value IS the
     port), app_id (indexed), status='allocated', allocated_at.

3. **`gui/sidecar/template_registry.py`** — pure, side-effect-free. 10 templates:
   `fastapi, django, react, nextjs, svelte, astro, node-express, fullstack, cli,
   monorepo`.
   - Exports: `TEMPLATES`, `PYTHON_TEMPLATES={fastapi,django,cli}`,
     `NODE_TEMPLATES`, `render()`, `get_template()`,
     `generate_pyproject_toml()`, `generate_app_json()`, `generate_files()`.
   - **Corrections applied vs. draft plan:** (a) `generate_app_json` emits the
     nested `web` block (`web.command`/`web.port`/`web.venv`) that
     `core/app_registry.py::_parse_app_json` actually reads — NOT a flat
     top-level `port`; (b) templating uses `{{PLACEHOLDER}}` + `str.replace`
     (NOT `str.format`, which crashes on literal `{}` in JSON/JS/JSX);
     (c) pyproject deps are bare PEP 508 names — the invalid `"fastapi>="`
     dangling-operator bug is gone.
   - `fullstack` is intentionally excluded from `PYTHON_TEMPLATES` (its python
     backend lives under `backend/`, breaking the venv-at-root assumption);
     `generate_files` writes `backend/pyproject.toml` for it.

4. **`gui/sidecar/project_manager.py`** — side-effectful foundation helpers.
   - `validate_project_name(name)` — slug regex.
   - `scan_codehome_structure()` — suggested/all/custom_available.
   - `create_project_folder(subfolder, name)` — raises FileExistsError on
     non-empty target.
   - `create_venv(project_path, template)` — python templates only; `uv venv` +
     `uv pip install -e .` with stdlib `venv` fallback; best-effort (logs +
     returns None on failure, never raises).
   - `allocate_port(app_id, preferred_port=None, session=None)` — DB-backed via
     `Port`; unavailable set = ledger rows ∪ registry `expected_port`s ∪ live TCP
     probes; honours a free preferred port else scans 5200–5999; IntegrityError
     retry; RuntimeError on exhaustion.

5. **`gui/sidecar/tests/test_phase11a.py`** — pytest, no live MySQL needed
   (allocate_port test binds to in-memory SQLite; app_registry + `_port_in_use`
   monkeypatched). Covers template token-residue, app.json web-block/port,
   pyproject validity, name validation, codehome scan, and port allocation.

### ⚠️ NOT YET DONE — next session must do this first

**Run the test suite on the Mac** (could not execute from the assistant sandbox):

```bash
cd /Users/tonyseneadza/Codehome/AgenticOS
.venv/bin/python -m pytest gui/sidecar/tests/test_phase11a.py -v
```

If SQLAlchemy / mysql-connector aren't in the repo `.venv`, install them first
(`uv pip install sqlalchemy mysql-connector-python` or the repo's usual flow).
Fix any failures before proceeding to 11b.

---

## 🚀 Subsequent Phases (unchanged)

**Phase 11b (Week 2):** `github_integration.py` (GitHub API client, token
validation) + git init/commit/remote.

**Phase 11c (Week 3):** `routes/api_projects.py` (templates/subfolders/port-check
endpoints + `POST /create` WebSocket streaming) + full `create_project_full`
orchestration (lenient error handling) + Project-row registration. **Remember
the API registration rule** — add every new endpoint to
`gui/desktop/src/components/HubApiExplorer.jsx` in the same change.

**Phase 11d (Week 4):** `ProjectCreationDrawer.jsx` + SysOps CODEHOME HUB trigger
+ end-to-end testing.

---

## 📄 Key Documents

- **`docs/PROJECT_CREATION_PLAN.md`** — master plan (note: its Phase 1 code stubs
  predate the reconciliation above; the shipped 11a modules are the source of
  truth for interfaces).
- **`docs/roadmap.md`** — Phase 11 status.
- **`docs/CONTINUATION.md`** — this file.

---

## 🎯 Session Status

✅ Phase 11a foundation modules written + cross-verified for interface alignment.
⚠️ Tests not yet executed (sandbox can't reach the repo's python) — run them
first next session.

---

## 🚀 Quick Start

```bash
cd /Users/tonyseneadza/Codehome/AgenticOS

# Check status
git status

# Run Phase 11a tests
.venv/bin/python -m pytest gui/sidecar/tests/test_phase11a.py -v

# Start dev
python -m gui.sidecar &
cd gui/desktop && npm run tauri dev
```
