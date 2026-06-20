"""
Task management routes for AgenticOS.

Handles:
    GET    /api/tasks              — list tasks (filter by status/type/priority/project)
    POST   /api/tasks              — create a task
    GET    /api/tasks/stats        — summary counts by status/type
    GET    /api/tasks/{id}         — get a single task
    PATCH  /api/tasks/{id}         — update any fields
    DELETE /api/tasks/{id}         — delete a task
    POST   /api/tasks/{id}/status  — quick status transition (pending→in_progress→completed etc.)

Backed by MySQL (agenticos.tasks). Returns 503 if MySQL is unavailable.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gui.sidecar.routes import tasks_db

router = APIRouter()


def _require_db() -> None:
    if not tasks_db.is_available():
        raise HTTPException(503, "MySQL unavailable — check ~/.agentic-os/.env")


# ── request models ────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    type: str = "manual"           # manual | agent | project
    priority: str = "medium"       # low | medium | high | urgent
    project: str | None = None
    workflow: str | None = None
    tags: list[str] = []
    due_at: str | None = None      # ISO datetime string
    notes: str | None = None
    created_by: str = "user"


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    type: str | None = None
    status: str | None = None
    priority: str | None = None
    project: str | None = None
    workflow: str | None = None
    tags: list[str] | None = None
    due_at: str | None = None
    notes: str | None = None
    run_id: str | None = None


class StatusTransition(BaseModel):
    status: str   # pending | in_progress | completed | cancelled | failed


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("/api/tasks/stats")
def get_task_stats() -> dict:
    """Return summary counts — total, by status, by type, urgent pending."""
    _require_db()
    return {"stats": tasks_db.task_stats()}


@router.get("/api/tasks")
def list_tasks(
    status: str | None = None,
    type: str | None = None,
    priority: str | None = None,
    project: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List tasks with optional filters. Sorted by priority then creation date."""
    _require_db()
    tasks = tasks_db.list_tasks(
        status=status,
        type_=type,
        priority=priority,
        project=project,
        limit=limit,
        offset=offset,
    )
    return {"tasks": tasks, "count": len(tasks)}


@router.post("/api/tasks", status_code=201)
def create_task(body: TaskCreate) -> dict:
    """Create a new task. Returns the created task."""
    _require_db()
    valid_types = {"manual", "agent", "project"}
    valid_priorities = {"low", "medium", "high", "urgent"}
    if body.type not in valid_types:
        raise HTTPException(400, f"type must be one of {sorted(valid_types)}")
    if body.priority not in valid_priorities:
        raise HTTPException(400, f"priority must be one of {sorted(valid_priorities)}")

    task = tasks_db.create_task(
        title=body.title,
        description=body.description,
        type_=body.type,
        priority=body.priority,
        project=body.project,
        workflow=body.workflow,
        tags=body.tags,
        due_at=body.due_at,
        notes=body.notes,
        created_by=body.created_by,
    )
    return {"task": task}


@router.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    """Fetch a single task by ID."""
    _require_db()
    task = tasks_db.get_task(task_id)
    if not task:
        raise HTTPException(404, f"Task '{task_id}' not found")
    return {"task": task}


@router.patch("/api/tasks/{task_id}")
def update_task(task_id: str, body: TaskUpdate) -> dict:
    """Update any subset of task fields."""
    _require_db()
    if not tasks_db.get_task(task_id):
        raise HTTPException(404, f"Task '{task_id}' not found")

    updates = body.model_dump(exclude_none=True)
    task = tasks_db.update_task(task_id, updates)
    return {"task": task}


@router.post("/api/tasks/{task_id}/status")
def transition_status(task_id: str, body: StatusTransition) -> dict:
    """Quick status transition — just send {status: 'completed'} etc."""
    _require_db()
    valid = {"pending", "in_progress", "completed", "cancelled", "failed"}
    if body.status not in valid:
        raise HTTPException(400, f"status must be one of {sorted(valid)}")
    if not tasks_db.get_task(task_id):
        raise HTTPException(404, f"Task '{task_id}' not found")

    task = tasks_db.update_task(task_id, {"status": body.status})
    return {"task": task}


@router.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: str) -> None:
    """Delete a task permanently."""
    _require_db()
    if not tasks_db.delete_task(task_id):
        raise HTTPException(404, f"Task '{task_id}' not found")
