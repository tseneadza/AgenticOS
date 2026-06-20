"""
MySQL-backed task store for AgenticOS.

Reads connection config from ~/.agentic-os/.env (never committed to git).
Falls back gracefully if MySQL is unavailable so the sidecar still starts.

Connection env vars:
    MYSQL_HOST  (default: localhost)
    MYSQL_USER  (default: root)
    MYSQL_PASS  (default: "")
    MYSQL_DB    (default: agenticos)
    MYSQL_PORT  (default: 3306)
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env from ~/.agentic-os/.env — never raises if file is absent
load_dotenv(Path.home() / ".agentic-os" / ".env", override=False)

_log = logging.getLogger("agentcos.tasks_db")

# ── connection config ─────────────────────────────────────────────────────────
_CFG = {
    "host":     os.getenv("MYSQL_HOST", "localhost"),
    "user":     os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASS", ""),
    "database": os.getenv("MYSQL_DB",   "agenticos"),
    "port":     int(os.getenv("MYSQL_PORT", "3306")),
}

_AVAILABLE: bool | None = None   # None = not yet checked


def _connect():
    """Return a new mysql.connector connection. Raises on failure."""
    import mysql.connector  # type: ignore
    return mysql.connector.connect(**_CFG)


def is_available() -> bool:
    """True if MySQL is reachable. Result is cached after first check."""
    global _AVAILABLE
    if _AVAILABLE is not None:
        return _AVAILABLE
    try:
        conn = _connect()
        conn.close()
        _AVAILABLE = True
    except Exception as exc:
        _log.warning("MySQL unavailable — tasks disabled: %s", exc)
        _AVAILABLE = False
    return _AVAILABLE


def _gen_id() -> str:
    return uuid.uuid4().hex[:12]


def _row_to_dict(cursor, row: tuple) -> dict:
    cols = [d[0] for d in cursor.description]
    d = dict(zip(cols, row))
    # Deserialise JSON tags stored as string (mysql-connector returns str)
    if isinstance(d.get("tags"), str):
        try:
            d["tags"] = json.loads(d["tags"])
        except Exception:
            d["tags"] = []
    # Serialise datetimes to ISO strings
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


# ── public API ────────────────────────────────────────────────────────────────

def list_tasks(
    status: str | None = None,
    type_: str | None = None,
    priority: str | None = None,
    project: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    conn = _connect()
    try:
        cur = conn.cursor()
        where, params = [], []
        if status:
            where.append("status = %s");   params.append(status)
        if type_:
            where.append("type = %s");     params.append(type_)
        if priority:
            where.append("priority = %s"); params.append(priority)
        if project:
            where.append("project = %s");  params.append(project)
        sql = "SELECT * FROM tasks"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY FIELD(priority,'urgent','high','medium','low'), created_at DESC"
        sql += " LIMIT %s OFFSET %s"
        params += [limit, offset]
        cur.execute(sql, params)
        return [_row_to_dict(cur, r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_task(task_id: str) -> dict | None:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
        row = cur.fetchone()
        return _row_to_dict(cur, row) if row else None
    finally:
        conn.close()


def create_task(
    title: str,
    *,
    description: str | None = None,
    type_: str = "manual",
    priority: str = "medium",
    project: str | None = None,
    workflow: str | None = None,
    tags: list[str] | None = None,
    due_at: str | None = None,
    notes: str | None = None,
    created_by: str = "user",
) -> dict:
    task_id = _gen_id()
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO tasks
               (id, title, description, type, priority, project, workflow,
                tags, due_at, notes, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                task_id, title, description, type_, priority,
                project, workflow,
                json.dumps(tags or []),
                due_at, notes, created_by,
            ),
        )
        conn.commit()
        return get_task(task_id)
    finally:
        conn.close()


def update_task(task_id: str, updates: dict) -> dict | None:
    """Patch any subset of task fields."""
    allowed = {
        "title", "description", "type", "status", "priority",
        "project", "workflow", "tags", "due_at", "notes",
        "started_at", "completed_at", "run_id",
    }
    fields = {k: v for k, v in updates.items() if k in allowed}
    if not fields:
        return get_task(task_id)

    # Auto-stamp started_at / completed_at on status transitions
    if fields.get("status") == "in_progress" and "started_at" not in fields:
        fields["started_at"] = datetime.utcnow().isoformat()
    if fields.get("status") in ("completed", "cancelled", "failed") and "completed_at" not in fields:
        fields["completed_at"] = datetime.utcnow().isoformat()

    # Serialise tags
    if "tags" in fields and isinstance(fields["tags"], list):
        fields["tags"] = json.dumps(fields["tags"])

    conn = _connect()
    try:
        cur = conn.cursor()
        set_clause = ", ".join(f"{k} = %s" for k in fields)
        values = list(fields.values()) + [task_id]
        cur.execute(f"UPDATE tasks SET {set_clause} WHERE id = %s", values)
        conn.commit()
        return get_task(task_id)
    finally:
        conn.close()


def delete_task(task_id: str) -> bool:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def task_stats() -> dict:
    """Summary counts by status and type."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*)                                              AS total,
                SUM(status='pending')                                AS pending,
                SUM(status='in_progress')                            AS in_progress,
                SUM(status='completed')                              AS completed,
                SUM(status='cancelled')                              AS cancelled,
                SUM(status='failed')                                 AS failed,
                SUM(`type`='manual')                                 AS manual_count,
                SUM(`type`='agent')                                  AS agent_count,
                SUM(`type`='project')                                AS project_count,
                SUM(priority='urgent' AND status='pending')          AS urgent_pending
            FROM tasks
        """)
        row = cur.fetchone()
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))
    finally:
        conn.close()
