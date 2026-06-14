"""SQLite-backed memory: workflow run history + LangGraph checkpoints.

LangGraph's SqliteSaver handles per-run recoverable state (FR-05).
This module adds a simple run-history table so `agentic-os history`
can answer "what did you do and when".
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "state.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS run_history (
    run_id      TEXT PRIMARY KEY,
    workflow    TEXT NOT NULL,
    started_at  REAL NOT NULL,
    finished_at REAL,
    status      TEXT NOT NULL,          -- running | completed | failed | interrupted
    tokens_used INTEGER DEFAULT 0,
    cost_usd    REAL DEFAULT 0,
    detail      TEXT                    -- JSON blob: step outputs summary / error
);
"""


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_SCHEMA)
    try:  # migrate pre-cost databases
        conn.execute("ALTER TABLE run_history ADD COLUMN cost_usd REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # column already exists
    return conn


def start_run(workflow: str) -> str:
    run_id = uuid.uuid4().hex[:12]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO run_history (run_id, workflow, started_at, status) VALUES (?,?,?,?)",
            (run_id, workflow, time.time(), "running"),
        )
    return run_id


def finish_run(
    run_id: str,
    status: str,
    tokens_used: int = 0,
    cost_usd: float = 0.0,
    detail: dict | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE run_history SET finished_at=?, status=?, tokens_used=?, cost_usd=?, detail=? WHERE run_id=?",
            (time.time(), status, tokens_used, cost_usd, json.dumps(detail or {}), run_id),
        )


def cost_today() -> float:
    """Total recorded cost (USD) of runs started since local midnight."""
    import datetime as dt

    midnight = dt.datetime.combine(dt.date.today(), dt.time.min).timestamp()
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM run_history WHERE started_at >= ?",
            (midnight,),
        ).fetchone()
    return float(row[0])


def recent_runs(limit: int = 10) -> list[dict]:
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM run_history ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def checkpointer_conn() -> sqlite3.Connection:
    """Connection for LangGraph's SqliteSaver (separate table namespace)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH, check_same_thread=False)
