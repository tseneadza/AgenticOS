"""Project Creation Routes — Phase 11c (REST API + WebSocket streaming).

Ties together the Phase 11a scaffolding helpers (template_registry +
project_manager) and the Phase 11b GitHub/git flow behind a small REST surface
plus a streaming WebSocket that drives the full ``create_project_full``
orchestration and relays live progress events to the GUI.

REST endpoints:
    GET  /api/projects                  — list scaffolded projects (DB ledger)
    GET  /api/projects/templates        — the 10 built-in templates
    GET  /api/projects/subfolders       — ~/Codehome bucket discovery
    GET  /api/projects/port-check       — is a given port free? (ledger + probe)

WebSocket:
    WS   /api/projects/ws/create        — run create_project_full, stream events

WS message protocol
-------------------
Inbound (first frame, JSON): {
    "name": str, "template": str, "subfolder": str,
    "description"?: str, "custom_port"?: int, "private"?: bool (default True)
}
Outbound frames (JSON):
    progress: {"step": str, "status": str, "message": str | None}
    success:  {"step": "complete", "status": "success", "result": {...}}
    error:    {"step": "error", "status": "failed", "error": str}

The emitted ``step`` names are the stable set documented in
``project_manager.create_project_full``:
    validate, folder, port, files, venv, github, git, register
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from gui.sidecar import project_manager
from gui.sidecar.template_registry import TEMPLATES

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ═══════════════════════════════════════════════════════════════════════════════
# REST — fixed paths (no parametrized routes here, so ordering is not sensitive)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("")
async def list_projects() -> dict:
    """Return every scaffolded project recorded in the ledger.

    If the DB is unreachable this degrades gracefully to an empty list with
    ``available=False`` rather than raising — the apps remain discoverable via
    their on-disk ``app.json`` regardless of the ledger's health.
    """
    from gui.sidecar.db import SessionLocal
    from gui.sidecar.models import Project

    try:
        session = SessionLocal()
    except Exception as exc:  # noqa: BLE001
        log.warning("list_projects: could not open session: %s", exc)
        return {"projects": [], "total": 0, "available": False}

    try:
        rows = session.query(Project).order_by(Project.created_at.desc()).all()
        projects = [
            {
                "id": p.id,
                "name": p.name,
                "template": p.template,
                "subfolder": p.subfolder,
                "port": p.port,
                "path": p.path,
                "github_repo_url": p.github_repo_url,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in rows
        ]
        return {"projects": projects, "total": len(projects), "available": True}
    except Exception as exc:  # noqa: BLE001
        log.warning("list_projects: query failed: %s", exc)
        return {"projects": [], "total": 0, "available": False}
    finally:
        try:
            session.close()
        except Exception:  # noqa: BLE001
            pass


@router.get("/templates")
async def list_templates() -> dict:
    """Return the built-in project templates (id + display metadata)."""
    templates = [
        {
            "id": tpl_id,
            "name": tpl.get("name", tpl_id),
            "description": tpl.get("description", ""),
            "icon": tpl.get("icon", "📦"),
            "category": tpl.get("category", "other"),
        }
        for tpl_id, tpl in TEMPLATES.items()
    ]
    return {"templates": templates, "total": len(templates)}


@router.get("/subfolders")
async def list_subfolders() -> dict:
    """Return the ~/Codehome subfolder discovery (suggested + all + custom)."""
    return project_manager.scan_codehome_structure()


@router.get("/port-check")
async def port_check(port: int) -> dict:
    """Report whether *port* is free (not in the ledger and not in use).

    Available = no ``Port`` row claims it AND a quick TCP probe finds nothing
    listening. DB errors degrade to a probe-only answer.
    """
    ledger_taken = False
    try:
        from gui.sidecar.db import SessionLocal
        from gui.sidecar.models import Port

        session = SessionLocal()
        try:
            ledger_taken = (
                session.query(Port).filter(Port.port == port).first() is not None
            )
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("port_check: ledger lookup failed: %s", exc)

    in_use = project_manager._port_in_use(port)
    return {"port": port, "available": not (ledger_taken or in_use)}


# ═══════════════════════════════════════════════════════════════════════════════
# WebSocket — streaming project creation
# ═══════════════════════════════════════════════════════════════════════════════

@router.websocket("/ws/create")
async def ws_create(ws: WebSocket) -> None:
    """Run the full scaffolding flow, streaming live progress to the client.

    Inbound first frame carries the creation params; each orchestration step
    emits a progress frame. On success a ``complete`` frame carries the result;
    on failure an ``error`` frame carries the message. The socket is always
    closed in ``finally``.
    """
    await ws.accept()

    async def emit(step: str, status: str, message: str | None = None) -> None:
        await ws.send_json({"step": step, "status": status, "message": message})

    try:
        data = await ws.receive_json()

        result = await project_manager.create_project_full(
            name=data.get("name"),
            template=data.get("template"),
            subfolder=data.get("subfolder"),
            description=data.get("description"),
            custom_port=data.get("custom_port"),
            private=data.get("private", True),
            emit=emit,
        )
        await ws.send_json(
            {"step": "complete", "status": "success", "result": result}
        )
    except WebSocketDisconnect:
        log.info("ws_create: client disconnected")
    except Exception as exc:  # noqa: BLE001
        log.warning("ws_create: creation failed: %s", exc)
        try:
            await ws.send_json(
                {"step": "error", "status": "failed", "error": str(exc)}
            )
        except Exception:  # noqa: BLE001
            pass
    finally:
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass
