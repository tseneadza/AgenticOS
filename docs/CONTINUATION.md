# Session Continuation — Phase 11 COMPLETE ✅ (11a–11d shipped)

**Last Updated:** 2026-07-01 (Phase 11a–11d Implementation Session)
**Status:** ✅ Phase 10 SHIPPED / **Phase 11 (Project Creation Scaffolding) COMPLETE — 11a+11b+11c backend GREEN (48 tests), 11d GUI drawer built + `vite build` clean.**

---

## ✅ Phase 11d — Project Creation GUI SHIPPED

The drawer that makes the whole feature usable.

### Files
- **`gui/desktop/src/components/ProjectCreationDrawer.jsx`** (new) — right-side
  drawer. Loads `/api/projects/templates` + `/subfolders` on open; form (name
  with live slug validation mirroring the backend regex, template, subfolder,
  description, optional custom port, private checkbox); on submit opens
  `ws://localhost:5130/api/projects/ws/create`, streams the step events
  (validate→…→register) into a live checklist, then renders the result (path,
  port, GitHub link + pushed state, warnings) or an error. Theme tokens only;
  hover/transition/keyframe CSS in a scoped injected `pcd-*` stylesheet per the
  frontend conventions.
- **`gui/desktop/src/App.jsx`** (edited) — import the drawer; `SysOpsView` owns
  `showNewProject` state, renders a `＋ New Project` trigger pinned to the top of
  the **Codehome Hub** panel body, and mounts `<ProjectCreationDrawer>`.

### Verification
- `npm run build` (vite) compiles clean — 68 modules, no errors.
- Frontend `vitest` suite has **pre-existing** breakage (19 files / 188 tests)
  UNRELATED to this work: verified identical failed/passed counts with these
  changes stashed. This work adds zero new failures. (Separate cleanup task if
  desired — looks like a jsdom/RTL environment issue in the integration tests.)
- Still needs an on-device visual check: `cd gui/desktop && npm run tauri dev`
  (sidecar must be running on :5130 — `python -m gui.sidecar`). Open SysOps →
  Codehome Hub → ＋ New Project.

### ➡️ Optional follow-ups (Phase 12+)
- Fix the pre-existing frontend test-suite environment breakage.
- Custom templates from Git repos; org-scoped GitHub repos; edit-after-create.
- Consider a projects list view (the `GET /api/projects` ledger endpoint exists).

---

## ✅ Phase 11c — REST API + WebSocket streaming + orchestration SHIPPED

The full end-to-end scaffolding flow now exists behind the sidecar API.

### Files
- **`gui/sidecar/routes/api_projects.py`** (new) — `APIRouter(prefix="/api/projects")`:
  `GET /` (list ledger), `GET /templates`, `GET /subfolders`, `GET /port-check`,
  and `WS /ws/create` (streams `create_project_full`). DB-touching endpoints
  degrade gracefully if MySQL is down.
- **`gui/sidecar/project_manager.py`** (extended) — `async create_project_full(...)`:
  a lenient state machine tying folder + port + files + venv + github + git + DB
  registration. Critical steps (validate/folder/port/files/register) raise+abort;
  optional steps (venv/github/git) warn and continue. Subprocess/filesystem work
  is offloaded via `asyncio.to_thread`; **DB work runs inline on the event-loop
  thread** (a SQLAlchemy Session is not thread-safe — do NOT wrap allocate_port/
  register in to_thread). Best-effort `app_registry.invalidate_cache()` at the end.
- **`gui/sidecar/app.py`** (edited) — `include_router(api_projects.router)` +
  `_ensure_projects_schema` startup hook calling `db.init_db()`.
- **`gui/desktop/src/components/HubApiExplorer.jsx`** (edited) — added a
  "Projects (Sidecar)" group registering the 4 REST endpoints (API-registry rule).
- **`gui/sidecar/tests/test_phase11c.py`** (new) — TestClient for the GET
  endpoints + a full `create_project_full` orchestration test (tmp dir, sqlite
  session, mocked GitHub, real git).

### WS `/api/projects/ws/create` protocol
- Inbound first frame: `{name, template, subfolder, description?, custom_port?, private?=true}`.
- Outbound: progress `{step, status, message}`; success `{step:"complete", status:"success", result:{...}}`; error `{step:"error", status:"failed", error}`.
- Stable emit step names (in order): `validate, folder, port, files, venv, github, git, register`.

**Test status:** `48 passed` (30×11a + 14×11b + 4×11c). `py_compile` + import
smoke-test of app.py/api_projects.py clean. Run:
```bash
cd /Users/tonyseneadza/Codehome/AgenticOS
.venv/bin/python -m pytest gui/sidecar/tests/test_phase11a.py gui/sidecar/tests/test_phase11b.py gui/sidecar/tests/test_phase11c.py -v
```

### ➡️ Next: Phase 11d (GUI)
`ProjectCreationDrawer.jsx` (form → `ws://localhost:5130/api/projects/ws/create`,
stream progress), trigger button in SysOps CODEHOME HUB, end-to-end test. Follow
the GUI conventions (theme tokens in `gui/desktop/src/theme.css`; new paradigm =
drawer, not a new always-on panel).

---

## ✅ Phase 11b — GitHub + git integration SHIPPED

Decisions (locked with Tony): new repos default **private**; **best-effort
auto-push** of the initial commit; token resolved from `~/.agentic-os/config.yaml`
`github.token` FIRST, then `gh auth token` fallback (machine is already `gh`-authed
as `tseneadza`); remotes use **HTTPS** (SSH config currently broken by a bad
`usekeychain` line; gh credential helper handles HTTPS).

### Files
- **`gui/sidecar/github_integration.py`** (new) — `get_github_token()`,
  `GitHubError`, `GitHubClient` (`get_auth_user`, `check_token_valid`,
  `create_repo(private=True)` via synchronous `httpx.Client`), and
  `setup_repo(...)` best-effort orchestration entry point. Token never logged
  or persisted.
- **`gui/sidecar/project_manager.py`** (extended) — added `_git(args, cwd)`
  (check=False runner) and `init_git_repo(project_path, remote_url=None, *,
  push=False, default_branch="main")` returning
  `{initialized, committed, remote_added, pushed, warnings}`; never raises. All
  Phase 11a functions preserved.
- **`gui/sidecar/tests/test_phase11b.py`** (new) — 14 tests, no network / no gh /
  no real token (httpx + subprocess monkeypatched; `init_git_repo` uses real git
  in a tmp dir, push never tested).

**Test status:** `44 passed` (30 × 11a + 14 × 11b). Run:
```bash
cd /Users/tonyseneadza/Codehome/AgenticOS
.venv/bin/python -m pytest gui/sidecar/tests/test_phase11a.py gui/sidecar/tests/test_phase11b.py -v
```

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
