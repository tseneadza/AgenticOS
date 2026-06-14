# State and Memory

All persistent state lives in one SQLite file: `data/state.db`
(gitignored). Two kinds of state share it, in separate tables.

## 1. Run history (`run_history` table)

Written by `core/memory.py`, read by `agentic-os history`. One row per run:

| Column | Meaning |
|--------|---------|
| `run_id` | 12-hex id, also used as the LangGraph thread id |
| `workflow` | Workflow name |
| `started_at` / `finished_at` | Unix timestamps |
| `status` | `running` → `completed` \| `failed` \| `interrupted` |
| `tokens_used` | Cumulative Claude tokens for the run |
| `cost_usd` | Recorded run cost (USD), from the pricing table in `settings.yaml`; summed by `cost_today()` for the daily cap |
| `detail` | JSON: completed step ids, or the error/denial reason |

A run stuck at `running` means the process died before finishing — the
status is never falsely `completed`.

Inspect directly any time:

```bash
sqlite3 ~/Codehome/AgenticOS/data/state.db \
  "SELECT datetime(started_at,'unixepoch','localtime'), workflow, status FROM run_history ORDER BY started_at DESC LIMIT 5;"
```

## 2. LangGraph checkpoints (`checkpoints` tables)

Managed entirely by `langgraph-checkpoint-sqlite`'s `SqliteSaver`. After
every node, the full graph state is checkpointed under the run's
`thread_id`. This is what makes human-in-the-loop work: when a step hits
`interrupt()`, the paused state is durable — the process could exit and a
resume with the same `thread_id` would continue from the pause point.

Phase 1's CLI resumes interrupts within the same process (prompt → 
`Command(resume=...)`). A future `agentic-os resume <run_id>` command for
cross-process resume is a natural Phase 2+ addition — the persistence
layer already supports it.

## What is deliberately NOT remembered yet

The PRD's longer-term memory features — an agent memory index ("don't
re-research things already in Brain2"), cross-run knowledge — are **Phase 4**
scope. Phase 1 memory answers exactly one question: *what ran, when, and
how did it end.* Brain2 itself is the knowledge layer; the Agentic OS reads
it fresh each run rather than caching it.

## Maintenance

- Safe to delete `data/state.db` at any time — it's recreated on next run.
  You lose history and any resumable interrupted runs, nothing else.
- The DB stays small (KBs per run). No rotation needed at Phase 1 scale.
