"""Run history + briefing memory.

App data — the workflow `run_history` log (cost/token telemetry) and the
`briefed_docs` dedupe set — lives in **MySQL** (schema `AgenticOS`, the same
datastore as the tasks/news systems). See docs/mysql-migration-plan.md.

The LangGraph checkpointer is ALSO MySQL now (Phase 3 of that plan): it uses
`langgraph-checkpoint-mysql`'s `PyMySQLSaver`, whose `checkpoint_*` tables live
in the same `AgenticOS` schema. No SQLite remains — `data/state.db` is no longer
created or read.

MySQL connection config comes from ~/.agentic-os/.env
(MYSQL_HOST/USER/PASS/DB/PORT) — identical to tasks_db.py / news_db.py.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

# Load ~/.agentic-os/.env — never raises if the file is absent.
load_dotenv(Path.home() / ".agentic-os" / ".env", override=False)

# ── MySQL connection config ───────────────────────────────────────────────────
_DB_NAME = os.getenv("MYSQL_DB", "AgenticOS")
_CFG = {
    "host":     os.getenv("MYSQL_HOST", "localhost"),
    "user":     os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASS", ""),
    "database": _DB_NAME,
    "port":     int(os.getenv("MYSQL_PORT", "3306")),
}

_SCHEMA_READY = False


def _connect(use_db: bool = True):
    """New mysql.connector connection (use_db=False omits the database — needed
    to CREATE DATABASE before it exists)."""
    import mysql.connector  # type: ignore

    cfg = dict(_CFG)
    if not use_db:
        cfg.pop("database", None)
    return mysql.connector.connect(**cfg)


_RUN_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS run_history (
    run_id      VARCHAR(64)  PRIMARY KEY,
    workflow    VARCHAR(255) NOT NULL,
    started_at  DOUBLE       NOT NULL,
    finished_at DOUBLE       NULL,
    status      VARCHAR(32)  NOT NULL,
    tokens_used BIGINT       DEFAULT 0,
    cost_usd    DOUBLE       DEFAULT 0,
    detail      LONGTEXT,
    INDEX idx_run_history_workflow (workflow),
    INDEX idx_run_history_started (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

_BRIEFED_DOCS_DDL = """
CREATE TABLE IF NOT EXISTS briefed_docs (
    doc_hash         VARCHAR(64) PRIMARY KEY,
    title            TEXT,
    path             TEXT,
    first_briefed_at DOUBLE NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def ensure_schema() -> None:
    """Create the database + run_history/briefed_docs tables. Idempotent + cheap."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    conn = _connect(use_db=False)
    try:
        cur = conn.cursor()
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{_DB_NAME}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        conn.commit()
    finally:
        conn.close()
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(_RUN_HISTORY_DDL)
        cur.execute(_BRIEFED_DOCS_DDL)
        conn.commit()
    finally:
        conn.close()
    _SCHEMA_READY = True


def _db():
    """Ensure schema once, then return a fresh MySQL connection."""
    ensure_schema()
    return _connect()


# ── run history ───────────────────────────────────────────────────────────────

def start_run(workflow: str) -> str:
    run_id = uuid.uuid4().hex[:12]
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO run_history (run_id, workflow, started_at, status) VALUES (%s,%s,%s,%s)",
            (run_id, workflow, time.time(), "running"),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def finish_run(
    run_id: str,
    status: str,
    tokens_used: int = 0,
    cost_usd: float = 0.0,
    detail: dict | None = None,
) -> None:
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE run_history SET finished_at=%s, status=%s, tokens_used=%s, "
            "cost_usd=%s, detail=%s WHERE run_id=%s",
            (time.time(), status, tokens_used, cost_usd, json.dumps(detail or {}), run_id),
        )
        conn.commit()
    finally:
        conn.close()


def cost_today() -> float:
    """Total recorded cost (USD) of runs started since local midnight."""
    midnight = _dt.datetime.combine(_dt.date.today(), _dt.time.min).timestamp()
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM run_history WHERE started_at >= %s",
            (midnight,),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    return float(row[0]) if row and row[0] is not None else 0.0


def recent_runs(limit: int = 10) -> list[dict]:
    conn = _db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM run_history ORDER BY started_at DESC LIMIT %s", (int(limit),)
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def last_run_at(
    workflow: str, statuses: tuple[str, ...] = ("completed",)
) -> float | None:
    """started_at of the most recent run of *workflow* in one of *statuses*.

    The "recent docs" watermark — defaults to completed runs only so a
    failed/interrupted brief doesn't advance the window past content the user
    never saw. Returns None on a cold start.
    """
    placeholders = ",".join(["%s"] * len(statuses))
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT MAX(started_at) FROM run_history "
            f"WHERE workflow = %s AND status IN ({placeholders})",
            (workflow, *statuses),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    return float(row[0]) if row and row[0] is not None else None


def activity_stats() -> dict:
    """Aggregate run telemetry for panels.agent_activity().

    Returns a dict with: cost_today, cost_month, runs_today, tokens_total,
    avg_duration_s, completed, finished (raw aggregates; the panel rounds/derives).
    Replaces the old direct-SQLite query that lived in panels.py.
    """
    today = _dt.date.today()
    midnight = _dt.datetime.combine(today, _dt.time.min).timestamp()
    month_start = _dt.datetime(today.year, today.month, 1).timestamp()
    conn = _db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN started_at >= %s THEN cost_usd END), 0)  AS cost_today,
                 COALESCE(SUM(CASE WHEN started_at >= %s THEN cost_usd END), 0)  AS cost_month,
                 SUM(CASE WHEN started_at >= %s THEN 1 ELSE 0 END)               AS runs_today,
                 COALESCE(SUM(tokens_used), 0)                                   AS tokens_total,
                 AVG(CASE WHEN finished_at IS NOT NULL
                          THEN finished_at - started_at END)                     AS avg_duration_s,
                 SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END)           AS completed,
                 SUM(CASE WHEN status IN ('completed','failed','interrupted')
                          THEN 1 ELSE 0 END)                                     AS finished
               FROM run_history""",
            (midnight, month_start, midnight),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    return row or {}


# ── briefing dedupe ───────────────────────────────────────────────────────────

def seen_doc_hashes() -> set[str]:
    """All content hashes already surfaced in a prior (successful) briefing."""
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT doc_hash FROM briefed_docs")
        rows = cur.fetchall()
    finally:
        conn.close()
    return {r[0] for r in rows}


def mark_docs_briefed(docs: list[dict]) -> int:
    """Record docs as surfaced so they don't reappear as "new" if they later move.

    Each doc needs a 'hash'; docs without one (or already recorded) are ignored.
    Returns the count inserted.
    """
    rows = [
        (d["hash"], d.get("title", ""), d.get("path", ""), time.time())
        for d in docs
        if d.get("hash")
    ]
    if not rows:
        return 0
    conn = _db()
    try:
        cur = conn.cursor()
        cur.executemany(
            "INSERT IGNORE INTO briefed_docs "
            "(doc_hash, title, path, first_briefed_at) VALUES (%s,%s,%s,%s)",
            rows,
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ── LangGraph checkpointer (MySQL via langgraph-checkpoint-mysql — Phase 3) ───

_CHECKPOINTER_SETUP_DONE = False

# The MySQL checkpointer's internal queries build JSON_TABLE columns declared as
# `CHARACTER SET utf8mb4`, which resolve to utf8mb4's *default* collation
# (utf8mb4_0900_ai_ci on MySQL 8/9). Our `AgenticOS` database default is
# utf8mb4_unicode_ci (set in the tasks/news era), so `setup()` creates the
# checkpoint_* tables with unicode_ci and MySQL then refuses to compare those
# columns against the 0900 literals — error 1267 "Illegal mix of collations".
# Normalizing the checkpoint tables to 0900_ai_ci makes the saver's comparisons
# line up. (langgraph-checkpoint-mysql / langgraph#6003.)
_CHECKPOINT_COLLATION = "utf8mb4_0900_ai_ci"
_CHECKPOINT_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")


def _normalize_checkpoint_collation(conn) -> None:
    """Convert the checkpoint_* tables to utf8mb4_0900_ai_ci (idempotent).

    Only VARCHAR/TEXT columns are recollated; JSON, BLOB and BINARY columns are
    untouched by CONVERT TO CHARACTER SET. Safe to run on every fresh process.
    """
    cur = conn.cursor()
    for table in _CHECKPOINT_TABLES:
        try:
            cur.execute(
                f"ALTER TABLE `{table}` CONVERT TO CHARACTER SET utf8mb4 "
                f"COLLATE {_CHECKPOINT_COLLATION}"
            )
        except Exception:  # noqa: BLE001 — table absent/already correct: harmless
            pass


def checkpointer_conn():
    """Fresh autocommit PyMySQL connection for LangGraph's MySQL saver.

    `autocommit=True` is REQUIRED by langgraph-checkpoint-mysql so that
    `PyMySQLSaver.setup()` persists the `checkpoint_*` tables. The caller owns
    the connection and must close it when the run ends.
    """
    import pymysql  # lazy import — only needed when a workflow actually runs

    ensure_schema()  # guarantee the AgenticOS database exists first
    return pymysql.connect(
        host=_CFG["host"],
        user=_CFG["user"],
        password=_CFG["password"],
        database=_CFG["database"],
        port=_CFG["port"],
        autocommit=True,
    )


def get_checkpointer(conn=None):
    """Return a `PyMySQLSaver` for LangGraph checkpointing.

    Pass an existing autocommit connection (from `checkpointer_conn()`), or omit
    it to open a fresh one — in that case the caller closes `saver.conn` when
    done. `setup()` (which creates the `checkpoint_*` tables in the AgenticOS
    schema) runs once per process; it is idempotent and version-tracked.
    """
    from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver

    global _CHECKPOINTER_SETUP_DONE
    if conn is None:
        conn = checkpointer_conn()
    saver = PyMySQLSaver(conn)
    if not _CHECKPOINTER_SETUP_DONE:
        saver.setup()
        _normalize_checkpoint_collation(conn)
        _CHECKPOINTER_SETUP_DONE = True
    return saver
