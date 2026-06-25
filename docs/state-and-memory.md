# State and Memory

All persistent state lives in **MySQL**, in the `AgenticOS` schema — the same
datastore the tasks/news/keno systems use. There is no SQLite file anymore;
`data/state.db` is retired. Connection config comes from `~/.agentic-os/.env`
(`MYSQL_HOST/USER/PASS/DB/PORT`), identical to `routes/tasks_db.py` and
`routes/news_db.py`.

Two kinds of state share the schema, in separate tables.

## 1. Run history (`run_history` table)

Written by `core/memory.py`, read by `agentic-os history` and `/api/runs`.
One row per run:

| Column | Meaning |
|--------|---------|
| `run_id` | 12-hex id, also used as the LangGraph thread id |
| `workflow` | Workflow name |
| `started_at` / `finished_at` | Unix timestamps (`DOUBLE`, epoch seconds) |
| `status` | `running` → `completed` \| `failed` \| `interrupted` |
| `tokens_used` | Cumulative Claude tokens for the run |
| `cost_usd` | Recorded run cost (USD), from the pricing table in `settings.yaml`; summed by `cost_today()` for the daily cap |
| `detail` | JSON: completed step ids, or the error/denial reason |

`briefed_docs` (briefing dedupe) lives alongside it. `core/memory.py` owns both
tables and self-bootstraps them via `ensure_schema()` on first use.

A run stuck at `running` means the process died before finishing — the
status is never falsely `completed`.

Inspect directly any time:

```bash
mysql -uroot AgenticOS -e \
  "SELECT FROM_UNIXTIME(started_at), workflow, status FROM run_history ORDER BY started_at DESC LIMIT 5;"
```

(or, without the `mysql` client, `./.venv/bin/python -c "from core import memory; print(memory.recent_runs(5))"`)

## 2. LangGraph checkpoints (`checkpoint_*` tables)

Managed entirely by [`langgraph-checkpoint-mysql`](https://pypi.org/project/langgraph-checkpoint-mysql/)'s
`PyMySQLSaver`. After every node, the full graph state is checkpointed under the
run's `thread_id` into `checkpoints`, `checkpoint_blobs`, and `checkpoint_writes`
(plus a `checkpoint_migrations` version table) — all in the `AgenticOS` schema.
`core/memory.get_checkpointer()` constructs the saver on an **autocommit**
PyMySQL connection (required so `saver.setup()` can create those tables) and runs
`setup()` once per process.

This is what makes human-in-the-loop work: when a step hits `interrupt()`, the
paused state is durable — the process could exit and a resume with the same
`thread_id` would continue from the pause point. The Tool Call Visualizer's
`/api/runs/{id}/steps` endpoint reads these checkpoints back through the saver's
public `list()` API (no raw-table decoding).

> **Requirement:** the MySQL checkpointer needs MySQL ≥ 8.0.19 (or MariaDB
> ≥ 10.7.1). The tasks/news schema already runs on this server.

The CLI resumes interrupts within the same process (prompt →
`Command(resume=...)`); the GUI runner resumes them over HTTP via the Approval
Queue. A cross-process `agentic-os resume <run_id>` is a natural future addition —
the persistence layer already supports it.

## What is deliberately NOT remembered yet

The PRD's longer-term memory features — an agent memory index ("don't
re-research things already in Brain2"), cross-run knowledge — remain out of
scope here. Memory answers exactly one question: *what ran, when, and how did it
end.* Brain2 itself is the knowledge layer; the Agentic OS reads it fresh each
run rather than caching it.

## Maintenance

- The `checkpoint_*` tables are disposable run-scratch state — safe to truncate
  at any time. You lose resumable interrupted runs, nothing else; new runs
  recreate the tables via `setup()`.
- `run_history` / `briefed_docs` are real data — don't truncate them unless you
  mean to discard run history and the briefing dedupe set.
- Runs now require MySQL to be up (previously SQLite always worked offline).
  The news/tasks routes degrade gracefully with 503s, but a workflow run needs
  the server — the dependency is real, so keep MySQL running.
