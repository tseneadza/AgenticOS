"""
SQLAlchemy-backed task store for AgenticOS.

As of Phase 13f this store runs entirely on the shared SQLAlchemy ORM layer
(``gui.sidecar.db`` + ``gui.sidecar.models.Task``); no raw ``mysql.connector``
code remains. Connection config is read from ~/.agentic-os/.env (never
committed) by ``gui.sidecar.db``; it falls back gracefully when MySQL is
unavailable so the sidecar still starts.

Public API (signatures + return shapes are stable — routes/api_tasks.py depends
on them): is_available, list_tasks, get_task, create_task, update_task,
delete_task, task_stats.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import case, func

from gui.sidecar import db as _db
from gui.sidecar.db import get_session
from gui.sidecar.models import Task

_log = logging.getLogger("agentcos.tasks_db")

# Columns on the Task model (used to build full task dicts).
_TASK_COLUMNS = (
    "id", "title", "description", "type", "status", "priority",
    "project", "workflow", "run_id", "tags", "due_at", "started_at",
    "completed_at", "created_at", "updated_at", "created_by", "notes",
)


def is_available() -> bool:
    """True if MySQL is reachable (delegates to gui.sidecar.db)."""
    return _db.is_available()


def _gen_id() -> str:
    """Generate a short random ID for a new task."""
    return uuid.uuid4().hex[:12]


def _task_to_dict(t: Task) -> dict:
    """Convert a Task row to a dict, normalising tags + datetimes.

    ``tags`` is a JSON column (SQLAlchemy returns a Python list), but guard
    for a raw string just in case; datetimes are ISO-formatted.
    """
    d = {col: getattr(t, col) for col in _TASK_COLUMNS}
    tags = d.get("tags")
    if isinstance(tags, str):
        import json
        try:
            d["tags"] = json.loads(tags)
        except Exception:
            d["tags"] = []
    elif tags is None:
        d["tags"] = []
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
    """Query tasks with optional filters, sorted by priority then creation date.

    Args:
        status: Filter by task status (e.g., 'pending', 'completed').
        type_: Filter by task type (e.g., 'manual', 'agent').
        priority: Filter by priority level.
        project: Filter by project name.
        limit: Maximum number of tasks to return.
        offset: Number of tasks to skip for pagination.

    Returns:
        A list of task dictionaries.
    """
    s = get_session()
    try:
        q = s.query(Task)
        if status:
            q = q.filter(Task.status == status)
        if type_:
            q = q.filter(Task.type == type_)
        if priority:
            q = q.filter(Task.priority == priority)
        if project:
            q = q.filter(Task.project == project)
        q = q.order_by(
            func.field(Task.priority, "urgent", "high", "medium", "low"),
            Task.created_at.desc(),
        ).limit(limit).offset(offset)
        return [_task_to_dict(t) for t in q.all()]
    finally:
        s.close()


def get_task(task_id: str) -> dict | None:
    """Fetch a single task by its ID.

    Args:
        task_id: The unique task identifier.

    Returns:
        The task as a dictionary, or None if not found.
    """
    s = get_session()
    try:
        t = s.get(Task, task_id)
        return _task_to_dict(t) if t else None
    finally:
        s.close()


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
    """Insert a new task into the database and return it.

    Args:
        title: Task title (required).
        description: Optional detailed description.
        type_: Task type ('manual', 'agent', or 'project').
        priority: Priority level ('low', 'medium', 'high', 'urgent').
        project: Optional project name.
        workflow: Optional associated workflow name.
        tags: Optional list of string tags.
        due_at: Optional ISO datetime string for the due date.
        notes: Optional free-form notes.
        created_by: Creator identifier (defaults to 'user').

    Returns:
        The newly created task as a dictionary.
    """
    task_id = _gen_id()
    s = get_session()
    try:
        s.add(Task(
            id=task_id,
            title=title,
            description=description,
            type=type_,
            priority=priority,
            project=project,
            workflow=workflow,
            tags=tags or [],
            due_at=due_at,
            notes=notes,
            created_by=created_by,
        ))
        s.commit()
    finally:
        s.close()
    return get_task(task_id)


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

    s = get_session()
    try:
        t = s.get(Task, task_id)
        if t is None:
            return None
        for k, v in fields.items():
            setattr(t, k, v)
        s.commit()
    finally:
        s.close()
    return get_task(task_id)


def delete_task(task_id: str) -> bool:
    """Delete a task by its ID.

    Args:
        task_id: The unique task identifier.

    Returns:
        True if the task was deleted, False if not found.
    """
    s = get_session()
    try:
        deleted = s.query(Task).filter(Task.id == task_id).delete()
        s.commit()
        return deleted > 0
    finally:
        s.close()


def task_stats() -> dict:
    """Summary counts by status and type."""
    def _sum(expr):
        return func.sum(case((expr, 1), else_=0))

    s = get_session()
    try:
        row = s.query(
            func.count().label("total"),
            _sum(Task.status == "pending").label("pending"),
            _sum(Task.status == "in_progress").label("in_progress"),
            _sum(Task.status == "completed").label("completed"),
            _sum(Task.status == "cancelled").label("cancelled"),
            _sum(Task.status == "failed").label("failed"),
            _sum(Task.type == "manual").label("manual_count"),
            _sum(Task.type == "agent").label("agent_count"),
            _sum(Task.type == "project").label("project_count"),
            _sum((Task.priority == "urgent") & (Task.status == "pending")).label("urgent_pending"),
        ).one()
        keys = (
            "total", "pending", "in_progress", "completed", "cancelled",
            "failed", "manual_count", "agent_count", "project_count",
            "urgent_pending",
        )
        # Cast to int (JSON-serialisable; sums come back as Decimal/None).
        return {k: int(getattr(row, k) or 0) for k in keys}
    finally:
        s.close()
