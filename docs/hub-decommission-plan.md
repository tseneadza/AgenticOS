# Hub Decommission Plan — Phase 9

> **✅ ACCOMPLISHED (audited 2026-07-21):** Phase 9 complete 2026-06-26 —
> Hub Go server retired. Historical record. See `docs/IDEA_LEDGER.md`.

**Status:** Architecture & design phase  
**Last updated:** 2026-06-18  
**Owner:** AgenticOS team

---

## Executive Summary

This document outlines the plan to absorb Hub responsibilities into AgenticOS and retire the external Hub service on `:8085`. The goal is to make AgenticOS the canonical owner of Codehome app management, enabling both the CLI and GUI to operate apps, access manifests, and manage workflows directly.

**Key changes:**
- Move app registry from Hub to native sidecar/GUI (scan `app.json` files)
- Migrate port assignment tracking to a centralized database (SQLite)
- Absorb manifest + script ingestion into AgenticOS tool registry
- Enable feature parity between CLI and GUI apps
- Retire external Hub process and dependencies

---

## Current State: Hub Architecture

### Hub responsibilities today

| Responsibility | Location | Port | Current consumer |
|---|---|---|---|
| **App registry** | Hub (Codehome) | 8085 | Manual config, external CLI |
| **Port assignments** | `hub/docs/PORT_ASSIGNMENTS.md` | — | Manual updates, hard-coded in app.json |
| **Tool manifests** | `/api/cards` | 8085 | `hub_agent.list_running_apps()` via REST proxy |
| **Script discovery** | `/api/scripts` (implied) | 8085 | External tooling |
| **Process supervision** | launchd (via `com.codehome.hub.plist`) | 8085 | macOS system |

### Port assignment system (current)

Hub maintains a static Markdown file: `~/Codehome/hub/docs/PORT_ASSIGNMENTS.md`

```
| App | Port | Purpose | Status |
|---|---|---|---|
| AgenticOS sidecar | 5130 | FastAPI panel data + workflows | running |
| Ollama | 11434 | Local LLM service | optional |
| Hub | 8085 | App registry + manifests | RETIRING |
...
```

**Problems:**
- Manual edits (human error, conflicts)
- No runtime collision detection
- Hard to sync across multiple apps
- No history or audit trail
- GUI and CLI have separate logic for port management

---

## Target State: Native Management

### New architecture

```
┌─────────────────────────────────────────────────────────┐
│ AgenticOS GUI (Tauri desktop app)                       │
│  ├─ Dashboard: SysOps (app status, logs)                │
│  ├─ Dashboard: Scripts (discovered + managed)           │
│  └─ API queries: /api/apps, /api/scripts, /api/manifest │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │ Sidecar (FastAPI @ 5130)    │
        │  ├─ App registry (scan)     │
        │  ├─ Process supervisor      │
        │  ├─ Port manager (DB)       │
        │  ├─ Tool manifest builder   │
        │  └─ Scripts discovery       │
        └──────────────┬───────────────┘
                       │
        ┌──────────────▼──────────────────────────────┐
        │ MySQL: app_registry database                │
        │ (host: localhost:3306 or from settings.yaml)│
        │  ├─ apps table                              │
        │  ├─ ports table                             │
        │  ├─ processes table                         │
        │  ├─ scripts table                           │
        │  └─ migrations (Alembic)                    │
        └─────────────────────────────────────────────┘
```

### Abolished

- `:8085` Hub process
- `hub/docs/PORT_ASSIGNMENTS.md` static file (data migrated to MySQL `ports` table)
- `tools/hub_mcp.py` REST proxy (contract moved in-process)
- `hub_agent.list_running_apps()` (replaced with native methods)
- External Hub dependencies in launchd
- Manual port assignment conflicts (replaced with MySQL UNIQUE constraint)

---

## Requirements Breakdown (FR-60 to FR-64)

### FR-60: Native App Registry

**Goal:** AgenticOS owns the canonical app list by scanning `app.json` files.

**Scope:**
- Scan `~/Codehome/**/app.json` recursively
- Parse schema: `{ id, name, port, agent_block? }`
- Expose via sidecar endpoint: `GET /api/apps`
- Cache with 5-second refresh (configurable)
- Return:
  ```json
  {
    "apps": [
      {
        "id": "example-app",
        "name": "Example App",
        "port": 3000,
        "agent_block": "tool definitions if present",
        "status": "running|stopped|error",
        "pid": 12345,
        "last_check": "2026-06-18T10:23:45Z"
      }
    ]
  }
  ```

**Sidecar code location:** `gui/sidecar/app_manager.py` (new)

---

### FR-61: Native Process Lifecycle Manager

**Goal:** Start, stop, restart, and health-check apps without Hub.

**Scope:**
- `POST /api/apps/{id}/start` — spawn process, track PID
- `POST /api/apps/{id}/stop` — graceful shutdown
- `POST /api/apps/{id}/restart` — stop + start
- `GET /api/apps/{id}/status` — running, logs, health
- `GET /api/apps/{id}/logs?lines=50` — tail logs (last 50 lines)
- Constitution guards: honor `hub_start`, `hub_stop_all`, etc.
- Track in database: PID, start time, status, error log

**Sidecar code location:** `gui/sidecar/process_manager.py` (new)

**Supervision strategy:**
- Spawn via `subprocess.Popen()` with stdout/stderr logging
- Park `Process` objects in an in-memory dict keyed by app ID
- Periodically poll PIDs to detect crashes
- On crash: log error, update DB status, emit AG-UI event
- `startup_hook` in settings: optional pre-start validation

---

### FR-62: Native Manifest + Scripts Ingestion

**Goal:** Replace Hub's `/api/cards` endpoint with native in-process tool registry.

**Scope:**
- Extract `agent_block` from each `app.json`
- Parse as tool definitions (follow existing `tool_registry` contract)
- Merge with built-in tools (filesystem, etc.)
- Expose via: `GET /api/tools/registry`
- Discover runnable scripts:
  - `app.json::scripts[]` array
  - or convention: `~/Codehome/<app>/scripts/` directory
  - return: `{ id, name, description, args?, env? }`
- Expose via: `GET /api/scripts`

**Sidecar code location:** `gui/sidecar/manifest_builder.py` (new)

**Tool registry contract:** unchanged (so Phase 10's agent is unaffected)

---

### FR-63: Scripts Dashboard Goes Live

**Goal:** Phase 8's Scripts placeholder becomes functional.

**Scope:**
- GUI queries `GET /api/scripts`
- List view with `run` button per script
- `POST /api/scripts/{id}/run` executes script
- Streams output to a terminal panel
- Shows exit code + duration

**GUI code location:** `gui/desktop/src/views/ScriptsDashboard.jsx` (update)

---

### FR-64: Decommission Path

**Goal:** Parallel-run validation, cutover, and cleanup.

**Steps:**
1. **Phase 9a (weeks 1–2):** Build native manager + DB layer in sidecar (FR-60, 61, 62)
2. **Phase 9b (week 3):** GUI scripts dashboard + validation harness (FR-63)
3. **Phase 9c (week 4):** Run native + Hub in parallel; compare outputs; cutover once validated
4. **Phase 9d:** Remove Hub code:
   - Delete `hub/` directory (or archive as `hub-retired/`)
   - Remove `com.codehome.hub.plist`
   - Update `agentic-gui.sh` to skip Hub
   - Delete `tools/hub_mcp.py`
   - Update `settings.yaml` (remove `hub_url: localhost:8085`)
   - Remove Hub from `PORT_ASSIGNMENTS.md` → `app_registry.db`

---

## Database Schema (MySQL)

### Connection Configuration

Add to `config/settings.yaml`:

```yaml
database:
  engine: mysql
  host: localhost
  port: 3306
  user: agentic_os
  password: ${DB_PASSWORD}  # or read from env var
  database: app_registry
  pool_size: 5
  max_overflow: 10
  echo: false  # set true for SQL debugging
```

Sidecar reads this at startup; connection pooling handled by SQLAlchemy.

### Schema (MySQL 8.0+)

#### Table: `apps`
```sql
CREATE TABLE apps (
  id VARCHAR(128) PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  path VARCHAR(512) NOT NULL UNIQUE COMMENT '~/Codehome/<app>',
  expected_port INT UNSIGNED,
  agent_block LONGTEXT COMMENT 'JSON-encoded tool definitions',
  last_scanned TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_last_scanned (last_scanned)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### Table: `ports`
```sql
CREATE TABLE ports (
  app_id VARCHAR(128) PRIMARY KEY,
  port INT UNSIGNED NOT NULL UNIQUE,
  assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  released_at TIMESTAMP NULL,
  status ENUM('allocated', 'running', 'crashed', 'released') DEFAULT 'allocated',
  FOREIGN KEY (app_id) REFERENCES apps(id) ON DELETE CASCADE,
  INDEX idx_port (port),
  INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### Table: `processes`
```sql
CREATE TABLE processes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  app_id VARCHAR(128) NOT NULL,
  pid INT UNSIGNED,
  started_at TIMESTAMP,
  stopped_at TIMESTAMP NULL,
  exit_code INT NULL,
  status ENUM('running', 'stopped', 'crashed', 'unknown') DEFAULT 'running',
  log_path VARCHAR(512),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (app_id) REFERENCES apps(id) ON DELETE CASCADE,
  INDEX idx_app_id_started (app_id, started_at DESC),
  INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### Table: `scripts`
```sql
CREATE TABLE scripts (
  id VARCHAR(128) PRIMARY KEY,
  app_id VARCHAR(128) NOT NULL,
  name VARCHAR(255) NOT NULL,
  description TEXT,
  path VARCHAR(512) NOT NULL COMMENT 'Full path to executable or shell script',
  args_schema LONGTEXT COMMENT 'JSON-encoded arg definitions',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (app_id) REFERENCES apps(id) ON DELETE CASCADE,
  UNIQUE KEY unique_app_script (app_id, id),
  INDEX idx_app_id (app_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### SQLAlchemy ORM Models

File: `gui/sidecar/models.py` (new)

```python
from sqlalchemy import Column, Integer, String, Text, Enum, ForeignKey, DateTime, LargeBinary, Index, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class App(Base):
    __tablename__ = 'apps'
    
    id = Column(String(128), primary_key=True)
    name = Column(String(255), nullable=False)
    path = Column(String(512), nullable=False, unique=True)
    expected_port = Column(Integer)
    agent_block = Column(Text)
    last_scanned = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    port = relationship("Port", back_populates="app", uselist=False, cascade="all, delete-orphan")
    processes = relationship("Process", back_populates="app", cascade="all, delete-orphan")
    scripts = relationship("Script", back_populates="app", cascade="all, delete-orphan")

class Port(Base):
    __tablename__ = 'ports'
    
    app_id = Column(String(128), ForeignKey('apps.id', ondelete='CASCADE'), primary_key=True)
    port = Column(Integer, nullable=False, unique=True)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    released_at = Column(DateTime)
    status = Column(Enum('allocated', 'running', 'crashed', 'released'), default='allocated')
    
    # Relationships
    app = relationship("App", back_populates="port")

class Process(Base):
    __tablename__ = 'processes'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    app_id = Column(String(128), ForeignKey('apps.id', ondelete='CASCADE'), nullable=False)
    pid = Column(Integer)
    started_at = Column(DateTime)
    stopped_at = Column(DateTime)
    exit_code = Column(Integer)
    status = Column(Enum('running', 'stopped', 'crashed', 'unknown'), default='running')
    log_path = Column(String(512))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    app = relationship("App", back_populates="processes")

class Script(Base):
    __tablename__ = 'scripts'
    
    id = Column(String(128), primary_key=True)
    app_id = Column(String(128), ForeignKey('apps.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    path = Column(String(512), nullable=False)
    args_schema = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    app = relationship("App", back_populates="scripts")
    
    __table_args__ = (
        UniqueConstraint('app_id', 'id', name='unique_app_script'),
    )
```

### Alembic Migrations

Initialize: `alembic init alembic` (in sidecar root)

Initial migration: `alembic revision --autogenerate -m "Initial schema"`

Sidecar startup:
```python
from alembic.config import Config
from alembic.command import upgrade

alembic_cfg = Config("alembic.ini")
upgrade(alembic_cfg, "head")  # Apply all pending migrations
```

**Rationale:**
- `apps`: immutable source of truth (scanned from `app.json`)
- `ports`: runtime assignment tracking with status; UNIQUE constraint prevents collisions
- `processes`: audit trail of every start/stop (useful for debugging); indexed by app + time
- `scripts`: discovered scripts with metadata; unique constraint per app
- MySQL indexes on status/timestamps for efficient queries during health checks

---

## MySQL Setup (Pre-Phase-9a)

**One-time setup** (before starting Phase 9a):

### Docker (recommended for dev/test)

```bash
docker run --name agentic-os-mysql \
  -e MYSQL_ROOT_PASSWORD=root \
  -e MYSQL_DATABASE=app_registry \
  -e MYSQL_USER=agentic_os \
  -e MYSQL_PASSWORD=your_password \
  -p 3306:3306 \
  -d mysql:8.0
```

Verify:
```bash
mysql -h 127.0.0.1 -u agentic_os -p app_registry -e "SELECT VERSION();"
```

### Or use existing MySQL instance

Create database and user:
```sql
CREATE DATABASE app_registry CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'agentic_os'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON app_registry.* TO 'agentic_os'@'localhost';
FLUSH PRIVILEGES;
```

### Update `config/settings.yaml`

```yaml
database:
  engine: mysql
  host: localhost
  port: 3306
  user: agentic_os
  password: ${DB_PASSWORD}  # or hardcode if dev-only
  database: app_registry
  pool_size: 5
  max_overflow: 10
  echo: false
```

Set env var:
```bash
export DB_PASSWORD=your_password
```

### Add dependencies to `requirements.txt`

```
SQLAlchemy>=2.0.0
PyMySQL>=1.1.0
alembic>=1.12.0
```

Install: `pip install -r requirements.txt`

---

## Implementation Phases (within Phase 9)

### Phase 9a: Core Infrastructure (2 weeks)

**Prerequisites:**
- MySQL server running (docker, local, or provided)
- Create `app_registry` database with user `agentic_os`
- Add connection details to `config/settings.yaml`

**Tasks:**
1. Create `gui/sidecar/models.py`:
   - SQLAlchemy ORM models (App, Port, Process, Script)
   - Base declarative + relationships
   - Indices for efficient queries

2. Create `alembic/` migration structure:
   - `alembic init alembic`
   - Initial migration: `alembic revision --autogenerate -m "Initial schema"`
   - Test migrations: `alembic upgrade head` (create tables)

3. Create `gui/sidecar/database.py`:
   - SQLAlchemy engine + session factory with pooling:
     ```python
     engine = create_engine(
       connection_string,
       pool_size=5,
       max_overflow=10,
       pool_recycle=3600,
       echo=settings.database.echo
     )
     SessionLocal = sessionmaker(bind=engine)
     ```
   - CRUD operations: `add_app()`, `allocate_port()`, `get_process()`, etc.
   - Atomic port allocation (check uniqueness before insert)
   - Error handling: catch `IntegrityError` on collisions, retry with next port

4. Create `gui/sidecar/app_manager.py`:
   - `scan_apps()` — walk `~/Codehome/**` for `app.json`
   - `get_app_registry()` — cached list with 5s refresh + DB sync
   - Populate/update `apps` table on scan
   - `GET /api/apps` endpoint
   - Graceful MySQL unavailability: return cached registry, log warning

5. Create `gui/sidecar/process_manager.py`:
   - `start_app(app_id)` → allocate port from DB, spawn, track PID, store in `processes` table
   - `stop_app(app_id)` → SIGTERM, wait, record `exit_code` + `stopped_at`
   - `restart_app(app_id)` → stop + start
   - Periodic health check loop: query `processes` table for status, detect zombies, update DB
   - `POST /api/apps/{id}/start|stop|restart`
   - `GET /api/apps/{id}/status`
   - Constitution guards for each action

6. Integrate into sidecar startup:
   - Run Alembic migrations on startup: `upgrade(alembic_cfg, "head")`
   - Initialize engine + session pool
   - Load app registry once at startup (scan + populate DB)
   - Start health-check loop (background task)
   - Expose all `GET /api/apps` endpoints

**Testing:** 
- Unit tests for app registry scanning
- Integration tests: MySQL connection, port allocation, collision detection
- Transaction isolation tests (simulate concurrent writes)

### Phase 9b: Manifest + Scripts (1 week)

**Tasks:**
1. Create `gui/sidecar/manifest_builder.py`:
   - Extract `agent_block` from app registry
   - Merge with built-in tools
   - `GET /api/tools/registry` endpoint
   - Ensure Phase 10 agent sees no breaking changes

2. Create `gui/sidecar/script_discovery.py`:
   - Scan for scripts in each app directory
   - Populate `scripts` table
   - `GET /api/scripts` endpoint
   - `POST /api/scripts/{id}/run` (stream output to terminal)

3. Update GUI dashboard (Phase 8 carryover):
   - Implement Scripts dashboard UI
   - List discovered scripts with `run` button
   - Terminal output stream integration

**Testing:** Integration tests for manifest parsing and script execution.

### Phase 9c: Validation + Cutover (1 week)

**Tasks:**
1. Parallel run validation:
   - Start both native manager + Hub in same session
   - Compare `GET /api/apps` outputs
   - Verify scripts discovery matches
   - Monitor process spawn/stop for divergence

2. Cutover checklist:
   - ✅ All FR-60-64 acceptance criteria met
   - ✅ No data loss during migration
   - ✅ Constitution guards functional
   - ✅ GUI and CLI feature parity tested

3. Update documentation:
   - Replace Hub references with native manager
   - Update PORT_ASSIGNMENTS.md → database migration guide
   - Update architecture.md

### Phase 9d: Cleanup (2–3 days)

**Tasks:**
1. Remove Hub code:
   - Delete Hub directory (or archive)
   - Remove launchd plist for Hub
   - Delete `tools/hub_mcp.py`

2. Remove Hub references:
   - `agentic-gui.sh` — remove Hub install/start/stop
   - `settings.yaml` — remove `hub_url` key
   - Workflows — remove any Hub-only steps

3. Final verification:
   - App startup/stop without Hub running
   - Scripts execute correctly
   - Port assignments persist across restarts

---

## Acceptance Criteria

| # | Criterion | FR |
|---|-----------|-----|
| 1 | App list, start/stop/restart, status all work with Hub stopped | 61 |
| 2 | Agent blocks + scripts register in `tool_registry` (contract unchanged) | 62 |
| 3 | Scripts dashboard runs a discovered script end-to-end | 63 |
| 4 | Constitution guards apply to lifecycle actions | 61 |
| 5 | Hub `:8085` retired; no remaining runtime dependency | 64 |
| **6** | **Port assignments tracked in database (no static file)** | **new** |
| **7** | **CLI and GUI have equivalent app management capabilities** | **new** |
| **8** | **No data loss; migration from static PORT_ASSIGNMENTS.md to DB** | **new** |

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| Port collisions on startup | Apps fail to start | MySQL UNIQUE constraint on `ports.port`, atomic allocation |
| Lost app state during migration | Downtime, manual recovery | Backup old PORT_ASSIGNMENTS.md, dual-write phase, MySQL backup before cutover |
| Manifest parsing breaks Phase 10 agent | Agent can't call tools | Contract compatibility testing before cutover |
| Scripts execution unsafe | Possible damage | Constitution guard on script args/execution |
| **MySQL unavailable** | App startup queues/retries, user blocked | Graceful degradation: fail fast with clear error; fallback to OS port check (limited) |
| **Connection pool exhaustion** | Hanging requests, deadlocks | Pool size tuned (5–10); max_overflow buffer; connection recycling (pool_recycle=3600s) |
| **Network latency to MySQL** | Port checks slow (ms per query) | Caching layer: keep port table in memory, sync async; pre-allocate ports at startup |
| **Multi-app concurrent writes to same app** | Race conditions, corrupted state | Transaction isolation + unique constraints; `ON DUPLICATE KEY UPDATE` for idempotence |

---

## Success Metrics

- ✅ Hub process no longer needed for app management
- ✅ Port assignments persisted in database (auditable, conflict-free)
- ✅ CLI and GUI feature-equivalent (both can start/stop/query apps)
- ✅ Phase 10 agent works without changes (tool registry contract stable)
- ✅ Scripts dashboard functional (discover and run scripts)

---

## Open Questions & Next Steps

1. **Port allocation strategy:** First-available vs. reserved-ranges per-app?
2. **Multi-user support:** Is port/app registry shared across users, or per-user?
3. **Logging:** Should app logs go to a central location or per-app directories?
4. **Health checks:** Liveness probe strategy (HTTP, TCP, process existence)?
5. **Rollback:** How to handle cutover if validation finds issues?

**Next session:** Session #5 focuses on detailed design of `app_manager.py`, `process_manager.py`, and the DB schema migrations. Start with Task #2 (Design hub decommission architecture).

---

## Connection Pooling & Error Handling

### Connection Pool Configuration

Sidecar uses SQLAlchemy connection pooling to avoid exhaustion:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(
    f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}",
    pool_size=5,           # Num connections kept open in pool
    max_overflow=10,       # Additional connections to create if pool full
    pool_recycle=3600,     # Recycle connections after 1 hour (avoid MySQL timeout)
    pool_pre_ping=True,    # Test connection before reusing (catch stale connections)
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

### Graceful MySQL Unavailability

If MySQL goes down during operation:

```python
def get_db():
    """Dependency for FastAPI endpoints; handles DB errors gracefully."""
    db = SessionLocal()
    try:
        yield db
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")
    finally:
        db.close()
```

Sidecar behavior:
1. On startup: fail fast if MySQL unreachable (migrations can't run)
2. At runtime: if DB query fails, log + return HTTP 503 (Service Unavailable)
3. CLI / GUI should show: "Port registry offline, app startup queued" + retry button
4. Fallback: OS-level port check (less reliable, but prevents total blockage)

### Transaction Safety

For concurrent app start-ups (e.g., GUI + CLI both starting apps):

```python
def allocate_port(app_id: str, session: Session) -> int:
    """Atomic port allocation; raises IntegrityError on collision."""
    with session.begin_nested():  # Savepoint for rollback on collision
        # Check if app already has a port
        existing = session.query(Port).filter(Port.app_id == app_id).first()
        if existing:
            return existing.port
        
        # Find next free port
        used_ports = {p.port for p in session.query(Port.port).all()}
        for candidate in range(5200, 6000):  # Ephemeral range
            if candidate not in used_ports:
                port = Port(app_id=app_id, port=candidate, status='allocated')
                session.add(port)
                session.commit()
                return candidate
        
        raise RuntimeError("No free ports available")
```

---

## Appendix: Current Hub API Surface

For reference, what the Hub currently exposes:

```
GET  /api/cards          → list running apps (tool manifests)
GET  /api/scripts        → list runnable scripts (implied)
GET  /api/status         → health check
POST /start/<app>        → start app
POST /stop/<app>         → stop app
```

All of these will be reimplemented as native sidecar endpoints.

---

*Document status: DRAFT for design review*  
*Prepared by: AgenticOS team*  
*Date: 2026-06-18*
