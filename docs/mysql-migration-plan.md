# SQLite → MySQL migration plan

Goal: move **all** SQLite usage into the `AgenticOS` MySQL schema (the one the
tasks / news / keno systems already use), so the app has a single datastore.

## Inventory of SQLite usage

A repo sweep (`sqlite`, `state.db`, `SqliteSaver`, `sqlite3`) found SQLite in
five code files + requirements + docs. It splits into **two categories**:

| # | File | What | Category |
|---|------|------|----------|
| 1 | `core/memory.py` | `run_history` + `briefed_docs` tables; `_connect()`, `start_run`, `finish_run`, `cost_today`, `recent_runs`, `last_run_at`, `seen_doc_hashes`, `mark_docs_briefed` | **A — app data** |
| 2 | `gui/sidecar/panels.py` | `agent_activity()` queries `run_history` via `sqlite3.connect(memory.DB_PATH)` | **A — app data** |
| 3 | `core/orchestrator.py` | `SqliteSaver(conn)` for LangGraph checkpointing (`build_graph`, `run_workflow`) | **B — checkpointer** |
| 4 | `gui/sidecar/runner.py` | `SqliteSaver(conn)` for the GUI run executor | **B — checkpointer** |
| 5 | `gui/sidecar/app.py` | `/api/runs/{id}/steps` reads LangGraph's `writes` table directly with `sqlite3` + `ormsgpack` | **B — checkpointer (reader)** |
| 6 | `requirements.txt` | `langgraph-checkpoint-sqlite>=2.0` | dependency |
| 7 | `core/memory.py` | `checkpointer_conn()` — sqlite connection handed to the savers | bridge A↔B |

Already on MySQL (precedent to mirror): `gui/sidecar/routes/tasks_db.py`,
`routes/news_db.py`, and `panels.keno_telemetry()`.

### Category A — the app's own data (easy, unambiguous)
`run_history` (workflow run log + cost/token telemetry) and `briefed_docs`
(briefing dedupe). This is real business data and maps directly onto MySQL,
exactly like `tasks_db.py` / `news_db.py`.

### Category B — the LangGraph checkpointer (the hard part)
`SqliteSaver` persists per-run graph state for interrupt/resume (HITL). Docs
note `state.db` is *disposable* ("safe to delete at any time — recreated on
next run"). LangGraph ships official savers for **SQLite** and **Postgres**
only — there is **no first-party MySQL saver**.

**Good news:** a maintained community package exists —
[`langgraph-checkpoint-mysql`](https://pypi.org/project/langgraph-checkpoint-mysql/)
(`PyMySQLSaver` / `AIOMySQLSaver`), deliberately mirroring the official Postgres
saver. Requires **MySQL ≥ 8.0.19** (or MariaDB ≥ 10.7.1) and connections opened
with `autocommit=True` so `.setup()` can create the checkpoint tables.

## Decision needed: checkpointer approach

1. **Use `langgraph-checkpoint-mysql` (recommended).** True all-MySQL; small,
   well-scoped swap. Cost: a new dependency to track, MySQL ≥ 8.0.19 required,
   and the `/api/runs/{id}/steps` reader must be rewritten for the new tables.
2. **Keep SQLite only for the checkpointer.** Pragmatic — it's disposable
   run-scratch state, not business data — but does not satisfy "all in MySQL."
3. **Custom `BaseCheckpointSaver` on MySQL.** Maximum control, most effort/risk;
   not worth it given option 1 exists.

This plan assumes **option 1**. Confirm before Phase 3.

## Phased plan

### Phase 0 — prep
- Verify server: `SELECT VERSION();` must be ≥ 8.0.19 (the MySQL checkpointer
  requirement). The tasks/news schema is already on this server.
- Add deps to `requirements.txt`: `langgraph-checkpoint-mysql[pymysql]` (and
  `PyMySQL`); plan to drop `langgraph-checkpoint-sqlite` at the end.
- Reuse the existing `~/.agentic-os/.env` MySQL credentials + schema `AgenticOS`.

### Phase 1 — migrate `core/memory.py` (Category A)
- Reimplement the module against MySQL (mirror `tasks_db.py`: `_connect()`,
  `is_available()`, `ensure_schema()` with `CREATE TABLE IF NOT EXISTS`).
- Tables: `run_history` (run_id PK, workflow, started_at, finished_at, status,
  tokens_used, cost_usd, detail JSON) and `briefed_docs` (doc_hash PK, title,
  path, first_briefed_at). Use MySQL types (DOUBLE/BIGINT/JSON, `INSERT IGNORE`).
- **Keep the public function signatures identical** so callers
  (`orchestrator`, `runner`, briefing agent, `/api/runs`) need no changes.
- Timestamps: keep the existing `REAL`/epoch-seconds contract to avoid touching
  callers (or move to DATETIME + adapt `panels`/`cost_today` together).

### Phase 2 — `panels.agent_activity()` (Category A reader)
- Replace the direct `sqlite3.connect(memory.DB_PATH)` aggregate query with the
  MySQL equivalent (same columns), ideally via a new `memory.activity_stats()`
  helper so `panels.py` has no DB driver code (cleaner seam).

### Phase 3 — LangGraph checkpointer (Category B) — *after sign-off*
- `core/memory.py`: replace `checkpointer_conn()` with a MySQL connection
  factory (`pymysql.connect(..., autocommit=True)`), or expose a
  `get_checkpointer()` that returns a `PyMySQLSaver`.
- `core/orchestrator.py` + `gui/sidecar/runner.py`: swap
  `from langgraph.checkpoint.sqlite import SqliteSaver` → the MySQL saver; call
  `saver.setup()` once; update the `build_graph(..., checkpointer)` type hint.
- Checkpoint tables live in the same `AgenticOS` schema (prefixed by the saver).

### Phase 4 — rewrite `/api/runs/{id}/steps`
- It currently decodes the raw SQLite `writes` table with `ormsgpack`. Re-point
  it at the MySQL checkpoint tables and the saver's serialization. Verify a real
  run still decodes into clean steps for the Tool Call Visualizer.

### Phase 5 — cleanup + docs
- `requirements.txt`: remove `langgraph-checkpoint-sqlite`.
- Update `docs/state-and-memory.md`, `docs/architecture.md`, `README.md`,
  `.gitignore` (drop `data/state.db*`), and add a `CHANGELOG.md` entry.

### Phase 6 — data migration + verification
- One-time script to copy existing `run_history` / `briefed_docs` rows from
  `data/state.db` into MySQL (checkpoints are disposable — no need to migrate).
- Verify: run a workflow end-to-end (incl. an HITL interrupt + resume), check
  `/api/runs`, `agent_activity`, and the Run Visualizer; confirm
  `data/state.db` is no longer created.

## Risks & mitigations
- **MySQL version < 8.0.19** → checkpointer package won't work. Verify in Phase 0;
  fall back to decision option 2 for the checkpointer if needed.
- **Concurrency**: MySQL handles concurrent runs better than the single SQLite
  file (an upside), but ensure connections are opened/closed per call (mirror
  `tasks_db`) to avoid stale handles.
- **MySQL down** → today SQLite always works offline. After migration, runs need
  MySQL up. `memory.is_available()` + graceful messaging (like the news/tasks
  routes) mitigates; document the dependency.
- **`/api/runs/{id}/steps` coupling**: the only consumer of checkpoint internals;
  rewrite + test against a live run before removing SQLite.

## Verification checklist
- [ ] `SELECT VERSION()` ≥ 8.0.19
- [ ] `memory.py` MySQL-backed; signatures unchanged; `ensure_schema()` seeds tables
- [ ] `panels.agent_activity()` returns same shape from MySQL
- [ ] workflow run + HITL resume works on the MySQL checkpointer
- [ ] `/api/runs`, Run Visualizer, history all read from MySQL
- [ ] no new `data/state.db` created; docs + requirements updated
