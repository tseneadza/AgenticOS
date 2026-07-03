# Phase 13: Data-Driven App Launch System

**Status:** 13a SHIPPED 2026-07-02 — see Locked Decisions below  
**Date Created:** 2026-07-02  
**Implementation Partner:** Fable 5  
**Priority:** HIGH — foundational for Projects view and port management

---

## 🔒 Locked Decisions — Amendments (2026-07-02, with Tony)

These supersede the corresponding sections below. The original design was
written greenfield; implementation reconciled it against Phases 9/11/12.

1. **ONE launch system.** Phase 13 EXTENDS `core/process_manager.py` (Phase 9)
   and evolves the existing `/api/apps/{app_id}/start|stop|status` routes in
   `routes/api_apps.py`. The parallel `POST /api/apps/launch/{app_id}` surface
   specified below is NOT built — those routes already exist with different
   semantics. `launch_config.py` owns the data half; `process_manager` owns
   execution.
2. **Python, not SQL stored procedures.** All 5 "procedures" are Python
   functions in `gui/sidecar/launch_config.py` with the exact JSON contracts
   below (SQL procs can't do live TCP probes / pid checks, and §§3–5 were
   already specified as sidecar logic).
3. **Backfill ports come from the live registry/ledger** (`app_registry` →
   `ports` table, reconciled 2026-07-02, 0 conflicts). `start.sh` is parsed
   for **commands only** (steps, cwd, env); port mismatches are logged to
   `port_collision_log`, never inserted.
4. **MySQL everywhere; SQLAlchemy is the only DB access layer.** Tests run
   against a real `agenticos_test` schema (`tests/conftest.py`), not SQLite.
   Legacy raw-connector modules (`news_db`, `tasks_db`) + legacy SQLite-bound
   tests migrate in **Phase 13f**. LangGraph MySQL checkpointer = separate
   future phase.
5. **Schema deviations** (see `models.py` docstring): no MySQL ENUMs
   (String columns validated in `launch_config` constants); `ports.port`
   stays the PK (no surrogate id — avoids destructive migration of 28 live
   rows); no DB-level FK `ports.app_id → projects.id` (ledger holds service
   ports — agenticos-sidecar :5130, dreamcatcher-backend :5111 — with no
   projects row); `child_pids` is informational only — cleanup uses
   process-group kill (`start_new_session=True` + `os.killpg`), not child-PID
   chasing.
6. **Migrations:** `CREATE TABLE IF NOT EXISTS` silently no-ops on the
   pre-existing `projects`/`ports` tables — `gui/sidecar/migrations.py`
   (`ensure_phase13_schema`, wired into `db.init_db()`) applies idempotent,
   inspect-first ALTERs. Applied to the live schema 2026-07-02: 0 warnings.
7. **Stale-state hygiene:** `reconcile_stale_processes()` sweeps orphaned
   'running' rows at sidecar startup (wiring lands in 13c).

### 13b amendments (2026-07-03, with Tony)

8. **port_type semantics:** `frontend` = the port a user opens in a browser,
   even if FastAPI/Flask serves the UI from it (single-port apps like keno,
   weather → `frontend`); `backend` = an API-only port behind a separate
   frontend (worldwise's uvicorn :8000); `api` = headless services with no
   browser UI (agenticos-sidecar :5130, dreamcatcher-backend :5111 — no
   projects/registry row, left as `api`). Backfill inference: a ledger row
   whose port equals the owning app's registry `expected_port` is the
   browser-facing port → `frontend`; app_ids not in the registry keep `api`.
9. **No-start.sh apps** get ONE `app_commands` step from the registry's
   `start_command` (the app.json `web.command` list), working_directory =
   app root, port_type = the app's browser-facing port type.
10. **start.sh-only ports** (in the script but in no ledger row) are
    allocated on `--apply` through the ONE allocator —
    `project_manager.allocate_port(app_id, preferred_port=<literal>)` — then
    stamped with their port_type. If the preferred port is unavailable the
    allocator picks another; the mismatch is logged to `port_collision_log`
    (phase='backfill') and the command is templated with the port-type
    variable so it resolves to the ALLOCATED port. Ports owned by ANOTHER
    app are logged as collisions and left literal — never inserted, never
    templated.

---

## 🎯 Executive Summary

**Vision:** Replace fragile shell scripts (start.sh) with a **database-driven launch system**. 

All app launch configuration lives in the database. A set of **stored procedures** determines what to run, where, with what ports, and how to clean up. The **sidecar API** and **Projects GUI** call these procedures to orchestrate launches.

**Benefits:**
- ✅ Port management is data-driven (no collisions, deterministic)
- ✅ Launch logic is queryable and audit-able
- ✅ No more fragile shell script parsing
- ✅ Health checks are integrated
- ✅ Process state is tracked in the database

---

## 🏗️ Complete Architecture

### Data Layer (MySQL)

```
┌──────────────────────────────────────────────────────────────┐
│ DATABASE (agenticos schema)                                  │
├──────────────────────────────────────────────────────────────┤
│ projects                 - app metadata, paths, venv          │
│ ports                    - port allocations (by type)         │
│ app_commands             - launch steps (command + args)      │
│ app_processes            - active processes (pid, status)     │
│ app_health_checks        - optional health endpoints          │
│ port_collision_log       - logged collisions during backfill  │
└──────────────────────────────────────────────────────────────┘
```

### Logic Layer (Stored Procedures)

```
allocate_ports(app_id, num_ports)
  → Assigns free ports; logs/fails on collision

build_launch_command(app_id)
  → Returns JSON array of launch steps

launch_app(app_id)
  → Orchestrates startup; inserts into app_processes

stop_app(app_id)
  → Graceful shutdown; hard kill if needed

get_app_status(app_id)
  → Returns running status + process health
```

### API Layer (Sidecar)

```
POST   /api/apps/launch/{app_id}
POST   /api/apps/{app_id}/stop
GET    /api/apps/{app_id}/status
GET    /api/apps/processes
GET    /api/apps/health-check/{app_id}
```

### Presentation Layer (GUI)

```
Projects nav link → Projects view → Card grid + expanded detail
  ↓
Start button → POST /api/apps/launch/{app_id}
Stop button → POST /api/apps/{app_id}/stop
Status badge → GET /api/apps/{app_id}/status (polling)
Port details → Click to expand (collapsed by default)
```

---

## 📊 Database Schema (DDL)

### 1. `projects` table

**Purpose:** App metadata, extends Phase 11a.

```sql
CREATE TABLE IF NOT EXISTS projects (
  id VARCHAR(128) PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  description TEXT,
  path VARCHAR(512) NOT NULL UNIQUE,
  subfolder VARCHAR(128),
  template VARCHAR(128),
  port INT UNSIGNED,  -- "main" port (for single-port apps)
  github_repo_url VARCHAR(512),
  venv_path VARCHAR(512),  -- absolute path to venv, e.g., /Users/.../app/.venv
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  created_by VARCHAR(255) DEFAULT 'osa',
  INDEX idx_subfolder (subfolder),
  INDEX idx_template (template),
  INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Notes:**
- `venv_path`: Absolute path to Python venv (if applicable). Set at creation time for Phase 11a projects.
- `port`: The "primary" port from app.json (for backward compat). Actual ports live in `ports` table.

---

### 2. `ports` table

**Purpose:** Track all port allocations by type (frontend, backend, api, etc.).

```sql
CREATE TABLE IF NOT EXISTS ports (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  port INT UNSIGNED NOT NULL UNIQUE,
  app_id VARCHAR(128) NOT NULL,
  port_type ENUM('frontend', 'backend', 'api', 'admin', 'other') DEFAULT 'api',
  status ENUM('allocated', 'reserved', 'available') DEFAULT 'allocated',
  allocated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (app_id) REFERENCES projects(id) ON DELETE CASCADE,
  INDEX idx_app_id (app_id),
  INDEX idx_port_type (port_type),
  INDEX idx_status (status),
  UNIQUE KEY uk_app_port_type (app_id, port_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Notes:**
- `port`: The actual port number (e.g., 5173, 8000). Unique across all apps.
- `app_id`: Which app owns this port.
- `port_type`: Categorizes the port (frontend, backend, api, admin, other).
- `UK (app_id, port_type)`: Ensures max one port per app per type.
- `status`: 'allocated' = in use; 'reserved' = claimed but not yet used; 'available' = free.

**Example data:**
```
port=5173, app_id=worldwise, port_type=frontend, status=allocated
port=8000, app_id=worldwise, port_type=backend, status=allocated
port=5100, app_id=keno, port_type=api, status=allocated
port=3000, app_id=projmanager, port_type=frontend, status=allocated
```

---

### 3. `app_commands` table

**Purpose:** Launch steps for each app, structured as (command, args, cwd).

```sql
CREATE TABLE IF NOT EXISTS app_commands (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  app_id VARCHAR(128) NOT NULL,
  step_order INT NOT NULL,  -- 1, 2, 3, ...
  command VARCHAR(255) NOT NULL,  -- e.g., "uvicorn", "npm", "python"
  args JSON,  -- ["main:app", "--port", "{backend_port}", "--reload"]
  working_directory VARCHAR(512),  -- relative to app root, e.g., "backend", "frontend"
  port_type ENUM('frontend', 'backend', 'api', 'admin', 'other'),  -- nullable
  port_variable_name VARCHAR(128),  -- e.g., "backend_port", "frontend_port" (for templating)
  environment_json JSON,  -- {"PYTHONPATH": "{app_path}/backend", "DEBUG": "false"}
  wait_for_completion BOOLEAN DEFAULT FALSE,  -- block until this step finishes
  wait_for_port BOOLEAN DEFAULT FALSE,  -- poll port until listening
  wait_for_port_timeout_seconds INT DEFAULT 30,
  health_check_enabled BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (app_id) REFERENCES projects(id) ON DELETE CASCADE,
  INDEX idx_app_id (app_id),
  INDEX idx_step_order (app_id, step_order),
  UNIQUE KEY uk_app_step (app_id, step_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Notes:**
- `args`: JSON array of command arguments. Supports templating: `{app_path}`, `{backend_port}`, `{frontend_port}`, `{venv_path}`.
- `working_directory`: Relative to `projects.path`. E.g., for worldwise: "backend" → `/Users/.../worldwise/backend`.
- `port_type`: If this step launches a service on a port, what type is it?
- `port_variable_name`: For templating. E.g., `{backend_port}` in args → resolved from ports table where app_id=worldwise AND port_type=backend.
- `environment_json`: Env vars passed to subprocess. Also supports templating.
- `wait_for_completion`: If TRUE, block until this step's process exits before moving to next step. (E.g., database migrations.)
- `wait_for_port`: If TRUE, poll the port until it's listening (up to `wait_for_port_timeout_seconds`).

**Example data (worldwise):**
```
app_id=worldwise, step_order=1
  command: "uvicorn"
  args: ["backend.app.main:app", "--reload", "--port", "{backend_port}"]
  working_directory: "."
  port_type: "backend"
  port_variable_name: "backend_port"
  environment_json: {"PYTHONPATH": "{app_path}/backend"}
  wait_for_completion: false
  wait_for_port: true

app_id=worldwise, step_order=2
  command: "npm"
  args: ["run", "dev", "--", "--port", "{frontend_port}"]
  working_directory: "web"
  port_type: "frontend"
  port_variable_name: "frontend_port"
  wait_for_completion: false
  wait_for_port: true
```

---

### 4. `app_processes` table

**Purpose:** Track running processes for each app.

```sql
CREATE TABLE IF NOT EXISTS app_processes (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  app_id VARCHAR(128) NOT NULL,
  pid INT NOT NULL,
  process_type ENUM('frontend', 'backend', 'api', 'admin', 'migration', 'other') DEFAULT 'other',
  port INT UNSIGNED,  -- which port this process listens on (if applicable)
  started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  stopped_at TIMESTAMP NULL,
  status ENUM('running', 'stopped', 'error') DEFAULT 'running',
  exit_code INT,
  error_message TEXT,
  log_path VARCHAR(512),  -- path to log file, if applicable
  child_pids JSON,  -- array of child process IDs (for cleanup)
  health_check_url VARCHAR(255),  -- optional health endpoint for this process
  last_health_check TIMESTAMP NULL,
  is_healthy BOOLEAN DEFAULT TRUE,
  FOREIGN KEY (app_id) REFERENCES projects(id) ON DELETE CASCADE,
  INDEX idx_app_id (app_id),
  INDEX idx_pid (pid),
  INDEX idx_status (status),
  INDEX idx_started_at (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Notes:**
- `pid`: The process ID of the launched process.
- `process_type`: 'frontend', 'backend', 'api', 'migration', 'other'.
- `port`: Which port this process uses (if any).
- `child_pids`: JSON array of child PIDs. When stopping, we kill all children explicitly.
- `health_check_url`: Optional URL to poll for health (e.g., `http://localhost:5173/health`).
- `last_health_check`: Last time we polled the health endpoint.
- `is_healthy`: Boolean indicating last health check result.

---

### 5. `app_health_checks` table

**Purpose:** Optional health check configuration per app/port.

```sql
CREATE TABLE IF NOT EXISTS app_health_checks (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  app_id VARCHAR(128) NOT NULL,
  port INT UNSIGNED NOT NULL,
  endpoint VARCHAR(255) DEFAULT '/health',  -- e.g., "/health", "/api/health", "/"
  method ENUM('GET', 'POST') DEFAULT 'GET',
  expected_status_code INT DEFAULT 200,
  timeout_seconds INT DEFAULT 5,
  interval_seconds INT DEFAULT 10,  -- how often to poll
  enabled BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (app_id) REFERENCES projects(id) ON DELETE CASCADE,
  INDEX idx_app_id (app_id),
  INDEX idx_port (port),
  UNIQUE KEY uk_app_port (app_id, port)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Notes:**
- **Optional table.** Apps without health checks just use port polling.
- If a health check is configured, sidecar polls it every `interval_seconds`.
- If response matches `expected_status_code`, mark as healthy.

**Example:**
```
app_id=worldwise, port=8000, endpoint="/docs", expected_status_code=200
app_id=keno, port=5100, endpoint="/api/health", expected_status_code=200
```

---

### 6. `port_collision_log` table

**Purpose:** Log collisions discovered during backfill or runtime.

```sql
CREATE TABLE IF NOT EXISTS port_collision_log (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  port INT UNSIGNED NOT NULL,
  app_id_1 VARCHAR(128),
  app_id_2 VARCHAR(128),
  discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  phase VARCHAR(50),  -- "backfill", "allocation", "runtime"
  notes TEXT,
  resolved BOOLEAN DEFAULT FALSE,
  resolved_at TIMESTAMP NULL,
  resolution_note TEXT,
  INDEX idx_port (port),
  INDEX idx_discovered_at (discovered_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Notes:**
- If during backfill we find port 5173 claimed by both worldwise and another app, log it here.
- You review and manually resolve.
- Mark `resolved=TRUE` once fixed.

---

## 🔧 Stored Procedures

### Procedure 1: `allocate_ports(app_id, num_ports, port_types_json)`

**Purpose:** Allocate free ports for a new app. Fail if collision.

**Input:**
```sql
app_id: 'new-project'
num_ports: 2
port_types_json: '["backend", "frontend"]'
```

**Output:**
```json
{
  "success": true,
  "ports": {
    "backend": 5200,
    "frontend": 5201
  }
}
```

**Logic:**
1. Parse `port_types_json` into array.
2. For each type, find next available port (scan 5000-6999).
3. Check no collision in `ports` table or live TCP probes.
4. Insert into `ports` table.
5. Return allocated ports as JSON.

**Failure case:**
- If port range exhausted, fail with error.
- If any port is already allocated, log to `port_collision_log` and fail.

---

### Procedure 2: `build_launch_command(app_id, OUT result_json)`

**Purpose:** Build the complete launch configuration for an app.

**Input:**
```sql
app_id: 'worldwise'
```

**Output (stored in `result_json`):**
```json
[
  {
    "step": 1,
    "command": "uvicorn",
    "args": ["backend.app.main:app", "--reload", "--port", "8000"],
    "cwd": "/Users/tonyseneadza/Codehome/worldwise/backend",
    "env": {
      "PYTHONPATH": "/Users/tonyseneadza/Codehome/worldwise/backend"
    },
    "venv": "/Users/tonyseneadza/Codehome/worldwise/.venv",
    "port_type": "backend",
    "port": 8000,
    "wait_for_completion": false,
    "wait_for_port": true,
    "timeout_seconds": 30
  },
  {
    "step": 2,
    "command": "npm",
    "args": ["run", "dev", "--", "--port", "5173"],
    "cwd": "/Users/tonyseneadza/Codehome/worldwise/web",
    "env": {},
    "venv": null,
    "port_type": "frontend",
    "port": 5173,
    "wait_for_completion": false,
    "wait_for_port": true,
    "timeout_seconds": 30
  }
]
```

**Logic:**
1. Query `app_commands` for app_id, sorted by step_order.
2. For each row, resolve template variables:
   - `{app_path}` → projects.path
   - `{backend_port}` → ports.port WHERE app_id=? AND port_type='backend'
   - `{frontend_port}` → ports.port WHERE app_id=? AND port_type='frontend'
   - `{venv_path}` → projects.venv_path
3. Resolve `cwd` (relative to app root) to absolute path.
4. Get health check config from `app_health_checks` if it exists.
5. Return as JSON array.

---

### Procedure 3: `launch_app(app_id, OUT result_json)`

**Purpose:** Execute the launch command for an app (conceptual; actual execution happens in sidecar).

**Input:**
```sql
app_id: 'worldwise'
```

**Output:**
```json
{
  "success": true,
  "processes": [
    { "pid": 12345, "port": 8000, "port_type": "backend" },
    { "pid": 12346, "port": 5173, "port_type": "frontend" }
  ]
}
```

**Logic (in sidecar, not SQL):**
1. Call `build_launch_command('worldwise')` → get JSON steps.
2. For each step:
   - Set cwd to step.cwd.
   - Activate venv if provided.
   - Spawn subprocess with step.command + step.args + step.env.
   - Capture pid.
   - If wait_for_completion, wait for process.
   - If wait_for_port, poll port until listening (with timeout).
3. Insert into `app_processes` for each launched process.
4. Return success + pids.

---

### Procedure 4: `stop_app(app_id, hard_kill_after_seconds INT)`

**Purpose:** Stop all processes for an app gracefully, then hard-kill if needed.

**Input:**
```sql
app_id: 'worldwise'
hard_kill_after_seconds: 5
```

**Output:**
```json
{
  "success": true,
  "killed_pids": [12345, 12346],
  "exit_codes": [0, 0]
}
```

**Logic (in sidecar):**
1. Query `app_processes` WHERE app_id=? AND status='running'.
2. For each process:
   - Send SIGTERM.
   - Wait `hard_kill_after_seconds`.
   - If still alive, send SIGKILL.
   - Kill all child_pids explicitly (from JSON array).
3. Update `app_processes`: set status='stopped', exit_code, stopped_at.
4. Return success + pids.

---

### Procedure 5: `get_app_status(app_id, OUT result_json)`

**Purpose:** Get the current status of an app (all running processes, ports, health).

**Input:**
```sql
app_id: 'worldwise'
```

**Output:**
```json
{
  "app_id": "worldwise",
  "running": true,
  "processes": [
    {
      "pid": 12345,
      "port_type": "backend",
      "port": 8000,
      "status": "running",
      "started_at": "2026-07-02T10:30:00Z",
      "is_healthy": true,
      "last_health_check": "2026-07-02T10:30:15Z"
    },
    {
      "pid": 12346,
      "port_type": "frontend",
      "port": 5173,
      "status": "running",
      "started_at": "2026-07-02T10:30:05Z",
      "is_healthy": true
    }
  ],
  "ports": [8000, 5173]
}
```

**Logic:**
1. Query `app_processes` WHERE app_id=? AND (status='running' OR stopped_at > NOW() - 5 mins).
2. For each, check if pid is alive (Linux: `/proc/{pid}` exists; macOS: `ps -p {pid}`).
3. If no, update status='stopped'.
4. Query health checks if configured; include latest result.
5. Return consolidated status.

---

## 🔄 Backfill Process (Python Script)

**File:** `gui/sidecar/scripts/backfill_launch_config.py`

**Goal:** Parse all 27 existing projects, extract launch commands from start.sh, populate database cleanly.

**Process:**

1. **Discover all projects** from `projects` table (from Phase 11d backfill).

2. **For each project:**
   - Check if start.sh exists.
   - Parse it to extract:
     - All `uvicorn main:app --port 8000` → backend port 8000
     - All `npm run dev -- --port 5173` → frontend port 5173
     - All working directories (cd frontend, cd backend, etc.)
     - All env vars (export DEBUG=true, etc.)

3. **Create app_commands rows** (draft):
   ```
   INSERT INTO app_commands (app_id, step_order, command, args, working_directory, port_type, environment_json)
   ```

4. **Create ports rows** (draft):
   ```
   INSERT INTO ports (port, app_id, port_type, status)
   ```

5. **Log collisions** to `port_collision_log`:
   - If port 5173 claimed by multiple apps, log and SKIP (don't insert).

6. **Output a summary:**
   ```
   ✅ Successfully populated:
     - app_commands: 45 rows (e.g., 2 steps for worldwise, 1 for keno)
     - ports: 35 rows (27 apps × 1–2 ports each)
   
   ⚠️ Collisions found:
     - Port 5173: claimed by [worldwise, other-app]
     - Action: You must manually resolve these before proceeding.
   
   ❓ Edge cases:
     - igotyou: no start.sh found (manual entry needed?)
   ```

7. **You review and approve:**
   - Check summary.
   - Manually fix collisions.
   - Run script again with `--apply` flag to commit to DB.

---

## 🌐 Sidecar API Endpoints

### `POST /api/apps/launch/{app_id}`

**Description:** Launch an app (start all processes).

**Request:**
```json
POST /api/apps/launch/worldwise
```

**Response (success):**
```json
{
  "success": true,
  "app_id": "worldwise",
  "processes": [
    { "pid": 12345, "port": 8000, "port_type": "backend" },
    { "pid": 12346, "port": 5173, "port_type": "frontend" }
  ],
  "message": "App launched successfully"
}
```

**Response (error):**
```json
{
  "success": false,
  "error": "Port 5173 is already in use",
  "code": "PORT_IN_USE"
}
```

---

### `POST /api/apps/{app_id}/stop`

**Description:** Stop an app (graceful, then hard kill).

**Request:**
```json
POST /api/apps/worldwise/stop
```

**Response:**
```json
{
  "success": true,
  "app_id": "worldwise",
  "killed_pids": [12345, 12346],
  "exit_codes": [0, 0]
}
```

---

### `GET /api/apps/{app_id}/status`

**Description:** Get current running status.

**Response:**
```json
{
  "app_id": "worldwise",
  "running": true,
  "processes": [
    {
      "pid": 12345,
      "port_type": "backend",
      "port": 8000,
      "status": "running",
      "is_healthy": true
    },
    {
      "pid": 12346,
      "port_type": "frontend",
      "port": 5173,
      "status": "running",
      "is_healthy": true
    }
  ]
}
```

---

### `GET /api/apps/processes`

**Description:** Get all running processes across all apps.

**Response:**
```json
{
  "processes": [
    { "app_id": "worldwise", "pid": 12345, "port": 8000, "status": "running" },
    { "app_id": "worldwise", "pid": 12346, "port": 5173, "status": "running" },
    { "app_id": "keno", "pid": 12347, "port": 5100, "status": "running" }
  ],
  "total": 3
}
```

---

## 🎨 Projects GUI Component

### Component: `ProjectsView.jsx`

**Features:**
1. **Card grid** (hybrid view):
   - Each project as a card showing: name, description, template, status badge
   - Click to expand → shows ports, commands, health
2. **Collapsed detail** (click to expand):
   - Ports section: `Backend: 8000 | Frontend: 5173`
   - Launch commands: show the actual step-by-step (from `build_launch_command`)
   - Health checks: show if configured + last check time
3. **Start/Stop buttons:**
   - Start → `POST /api/apps/launch/{app_id}`
   - Stop → `POST /api/apps/{app_id}/stop`
   - Disabled while operation in progress
4. **Status badge:**
   - Green: running (all processes alive)
   - Yellow: partial (some processes down)
   - Red: stopped
   - Gray: error
5. **Health indicator:**
   - Polling via WebSocket or `/api/apps/{app_id}/status` every 5s
   - Show health check status per process

---

## 📋 Implementation Checklist (for Fable 5)

### Phase 13a: Schema & Procedures ✅ SHIPPED 2026-07-02
- [x] Schema: 4 new tables + `projects.venv_path` + `ports.port_type` + UK (models.py + migrations.py; applied live)
- [x] 5 procedures as Python (`launch_config.py`) with the doc's JSON contracts
- [x] Unit tests — 20 new, MySQL-backed (`test_phase13a.py`); full suite 109 green

### Phase 13b: Backfill Script ✅ SHIPPED 2026-07-03
- [x] Write `backfill_launch_config.py` (`gui/sidecar/scripts/`; dry-run
      default, `--apply` commits; summary per §Backfill Process step 6)
- [x] Parse existing projects' start.sh (commands/cwd/env/background;
      registry `start_command` fallback for apps without start.sh)
- [x] Log collisions (`port_collision_log`, phase='backfill'; exit 0 —
      collisions are logged by design)
- [x] Test on a few projects first (19 MySQL-backed tests in
      `test_phase13b.py` drive the plan/apply core with injected registry
      entries + start.sh content; live dry-run review is the run step)

### Phase 13c: Sidecar API
- [ ] Implement 4 endpoints (`launch`, `stop`, `status`, `processes`)
- [ ] Integrate with subprocess spawning
- [ ] Add port polling + health check logic

### Phase 13d: Projects GUI
- [ ] Build `ProjectsView.jsx`
- [ ] Add Start/Stop buttons wired to API
- [ ] Implement status polling
- [ ] Add expanded port/command detail

### Phase 13e: Integration & Testing
- [ ] End-to-end test (create project → launch → check health)
- [ ] Test collision detection
- [ ] Test graceful shutdown + hard kill

---

## 🚨 Known Risks & Mitigation

| Risk | Mitigation |
|------|-----------|
| Port range exhausted (5000–6999) | Scan 4000–9000 if needed; log error clearly |
| Child process orphaning | Explicitly kill all child_pids from JSON array |
| Health check spam | Poll only every 10s; short timeout (5s) |
| Template variable clash (e.g., `{backend_port}` in string literal) | Use a distinctive prefix like `__AGENTIC_BACKEND_PORT__` instead |
| start.sh parsing is fragile | Warn in output; flag edge cases; manual review required |
| Existing projects without health checks | Fall back to port polling (always works) |

---

## ✅ Success Criteria

- [x] Schema designed (this doc)
- [ ] Procedures implemented & tested
- [ ] Backfill script runs cleanly (0 collisions on existing 27 projects)
- [ ] API endpoints working (launch/stop/status)
- [ ] GUI component built + wired
- [ ] End-to-end test passing (create project → launch → health check → stop)

---

## 📝 Notes for Fable 5

1. **Start with schema:** Get it into MySQL first. Test procedures individually.
2. **Backfill carefully:** Run on a copy DB first. Review collision log.
3. **API first:** Get launch/stop/status working in sidecar before touching GUI.
4. **GUI last:** Once API is solid, wiring the GUI buttons is straightforward.
5. **Test health checks:** Use a real HTTP request library; don't just assume ports.
6. **Document edge cases:** If a project's start.sh doesn't fit the pattern, document it.

---

**Status:** Ready for Fable 5 to build  
**Next Session:** Phase 13 Implementation with Fable 5
