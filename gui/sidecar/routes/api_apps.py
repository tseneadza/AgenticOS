"""Native App Routes — Phase 9a/9b (FR-60/61).

Exposes the native app registry and process manager over REST alongside the
existing Hub-proxied panel routes. Both coexist during the parallel-run period.

Registry endpoints (9a):
    GET  /api/apps                      — list all discovered apps
    GET  /api/apps/manifests            — all agent blocks
    GET  /api/apps/scripts              — flat script list across all apps
    POST /api/apps/refresh              — force registry rescan
    GET  /api/apps/{app_id}             — single app detail

Lifecycle endpoints (9b, evolved in 13c — ONE launch system):
    GET  /api/apps/{app_id}/status      — live status (+ app_processes detail)
    POST /api/apps/{app_id}/start       — start app (launch-config plan when
                                          configured; legacy registry otherwise)
    POST /api/apps/{app_id}/stop        — stop app (process-group kill;
                                          returns killed_pids)
    POST /api/apps/{app_id}/restart     — restart app
    GET  /api/apps/{app_id}/logs        — tail app log file
    POST /api/apps/stop-all             — stop all running apps (constitution-gated)

Process endpoints (13c):
    GET  /api/apps/processes            — all DB-tracked running processes
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core import app_registry
from core.process_manager import manager

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/apps", tags=["apps"])


# ── helpers ────────────────────────────────────────────────────────────────────

def _running_count() -> int:
    """Count apps currently running per the native manager / port-probe."""
    return len(manager.running_ids())


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 9a — Registry
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("")
async def list_apps() -> dict:
    """Return all Codehome apps with live running status from native manager."""
    try:
        apps = app_registry.get_all()
        # Enrich each app entry with its live status
        statuses = manager.status_all()
        enriched = []
        for app in apps:
            s = statuses.get(app["id"], {})
            enriched.append({
                **app,
                "running": s.get("running", False),
                "pid": s.get("pid"),
                "port_live": s.get("port"),
                "url": s.get("url"),
                "managed": s.get("managed", True) if s.get("running") else False,
            })
        running_count = sum(1 for a in enriched if a["running"])
        return {
            "source": "native",
            "available": True,
            "apps": enriched,
            "total": len(enriched),
            "running_count": running_count,
        }
    except Exception as exc:
        log.exception("app list failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/manifests")
async def list_manifests() -> dict:
    """Return agent capability blocks for all discovered apps."""
    try:
        manifests = app_registry.get_manifests()
        return {"available": True, "source": "native", "manifests": manifests}
    except Exception as exc:
        log.exception("manifest scan failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/scripts")
async def list_scripts() -> dict:
    """Return a flat list of all scripts across all discovered apps."""
    try:
        scripts = app_registry.get_scripts()
        return {
            "available": True,
            "source": "native",
            "scripts": scripts,
            "total": len(scripts),
        }
    except Exception as exc:
        log.exception("scripts scan failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/refresh")
async def refresh_registry() -> dict:
    """Force an immediate re-scan of ~/Codehome (bypasses the 60s TTL cache)."""
    app_registry.invalidate_cache()
    apps = app_registry.get_all()
    return {
        "available": True,
        "source": "native",
        "refreshed": True,
        "total": len(apps),
    }


@router.post("/stop-all")
async def stop_all_apps() -> dict:
    """Stop all running apps.

    Constitution gate: hub_stop_all requires explicit approval (constitution.yaml).
    The route raises 403 until an approved=true query param is passed, matching
    the CLI interrupt pattern used in Phase 6.
    """
    from fastapi import Query
    from core.constitution import Constitution, ApprovalRequired
    _const = Constitution.load()
    try:
        _const.guard("hub_stop_all")
    except ApprovalRequired as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "approval_required",
                "action": exc.action,
                "description": exc.description,
                "hint": "Re-send with ?approved=true to confirm",
            },
        ) from exc
    log.warning("stop-all approved — stopping all native-managed apps")
    results = await manager.stop_all()
    return {
        "source": "native",
        "stopped": list(results.keys()),
        "statuses": results,
    }


@router.post("/stop-all-confirmed")
async def stop_all_apps_confirmed() -> dict:
    """Stop all running apps with pre-approved bypass (constitution approved=True)."""
    from core.constitution import Constitution
    Constitution.load().guard("hub_stop_all", approved=True)
    log.warning("stop-all-confirmed — stopping all native-managed apps")
    results = await manager.stop_all()
    return {
        "source": "native",
        "stopped": list(results.keys()),
        "statuses": results,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 13c — Process tracking  (fixed path — must precede /{app_id})
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/processes")
async def list_processes() -> dict:
    """All running processes across all apps (``app_processes``, pid-verified).

    Contract (PHASE13 doc §GET /api/apps/processes)::

        {"processes": [{"app_id", "pid", "port", "status"}, ...], "total": N}

    Degrades gracefully when MySQL is down (empty list, available=False).
    """
    try:
        from gui.sidecar import launch_config
        result = launch_config.list_all_processes()
        return {"available": True, "source": "native", **result}
    except Exception as exc:  # noqa: BLE001
        log.warning("GET /api/apps/processes degraded: %s", exc)
        return {"available": False, "source": "native",
                "processes": [], "total": 0, "error": str(exc)}


@router.get("/health")
async def list_health() -> dict:
    """Aggregated per-app HTTP health (Phase 13e — fixed path before /{app_id}).

    One DB query over running ``app_processes`` rows that carry a health
    signal; apps with no configured checks don't appear (their card keeps
    the process-state badge only). Degrades gracefully without MySQL.
    """
    try:
        from gui.sidecar import launch_config
        result = launch_config.list_all_health()
        return {"available": True, "source": "native", **result}
    except Exception as exc:  # noqa: BLE001
        log.warning("GET /api/apps/health degraded: %s", exc)
        return {"available": False, "source": "native",
                "apps": {}, "total": 0, "error": str(exc)}


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 9b — Lifecycle  (order matters: fixed paths before /{app_id})
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/{app_id}/status")
async def get_status(app_id: str) -> dict:
    """Return live running status for a single app."""
    _assert_exists(app_id)
    return manager.status(app_id)


@router.post("/{app_id}/start")
async def start_app(app_id: str) -> dict:
    """Start a Codehome app via the native process manager."""
    _assert_exists(app_id)
    result = await manager.start(app_id)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.post("/{app_id}/stop")
async def stop_app(app_id: str) -> dict:
    """Stop a running Codehome app."""
    _assert_exists(app_id)
    return await manager.stop(app_id)


@router.post("/{app_id}/restart")
async def restart_app(app_id: str) -> dict:
    """Restart a Codehome app (stop → start)."""
    _assert_exists(app_id)
    result = await manager.restart(app_id)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.get("/{app_id}/logs")
async def get_logs(app_id: str, lines: int = 100) -> dict:
    """Tail the app's log file (last N lines, default 100)."""
    _assert_exists(app_id)
    from pathlib import Path as _Path
    log_path = _Path.home() / ".agentic-os" / "logs" / f"{app_id}.log"
    if not log_path.exists():
        return {"app_id": app_id, "lines": [], "log_file": str(log_path), "exists": False}
    try:
        text = log_path.read_text(errors="replace")
        all_lines = text.splitlines()
        tail = all_lines[-lines:]
        return {
            "app_id": app_id,
            "log_file": str(log_path),
            "exists": True,
            "total_lines": len(all_lines),
            "lines": tail,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{app_id}/launch-plan")
async def get_launch_plan(app_id: str) -> dict:
    """Return the resolved launch-config plan for an app (Phase 13d).

    Thin read-only wrapper over ``launch_config.build_launch_command`` so the
    Projects GUI can show the expandable port/command detail. Degrades
    gracefully: apps with no ``app_commands`` rows (legacy-launch apps like
    ``agenticos``/``hub`` — locked decision: intentionally unconfigured) or a
    down MySQL return ``configured=False`` with a reason, never a 500.
    """
    _assert_exists(app_id)
    try:
        from gui.sidecar import launch_config
        steps = launch_config.build_launch_command(app_id)
        return {"available": True, "source": "native", "app_id": app_id,
                "configured": True, "steps": steps, "total": len(steps)}
    except (LookupError, ValueError) as exc:
        return {"available": True, "source": "native", "app_id": app_id,
                "configured": False, "steps": [], "total": 0,
                "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001 — MySQL down etc.
        log.warning("launch-plan(%s) degraded: %s", app_id, exc)
        return {"available": False, "source": "native", "app_id": app_id,
                "configured": False, "steps": [], "total": 0,
                "reason": str(exc)}


# Must be LAST so fixed sub-paths above match first
@router.get("/{app_id}")
async def get_app(app_id: str) -> dict:
    """Return a single app's registry detail plus live status."""
    entry = app_registry.get(app_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"App '{app_id}' not found in native registry",
        )
    status = manager.status(app_id)
    return {"available": True, "source": "native", "app": {**entry, **status}}


# ── internal ───────────────────────────────────────────────────────────────────

def _assert_exists(app_id: str) -> None:
    if app_registry.get(app_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"App '{app_id}' not found in native registry",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 9c — Script execution + info
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/scripts/info")
async def script_info(id: str) -> dict:
    """Return raw content of a script file so ScriptsExplorer can parse its header.

    Mirrors Hub's GET /api/scripts/info?id=<script_id>.
    id format: <app_id>/<script_name>  e.g. 'hub/start.sh' or just 'start.sh'
    """
    scripts = app_registry.get_scripts()
    match = None
    for s in scripts:
        slug = f"{s['app_id']}/{s['name']}"
        if id in (slug, s["name"], s.get("path", "")):
            match = s
            break
    if match is None:
        raise HTTPException(status_code=404, detail=f"Script '{id}' not found")
    script_path = Path(match["app_path"]) / match.get("path", match["name"])
    if not script_path.exists():
        return {"success": False, "error": f"Script file not found: {script_path}"}
    content = script_path.read_text(errors="replace")
    lines = content.splitlines()
    return {
        "success": True,
        "id": id,
        "name": match["name"],
        "app_id": match["app_id"],
        "path": str(script_path),
        "content": content,
        "line_count": len(lines),
        "examples": match.get("examples") or [],
        "parameters": match.get("parameters", ""),
    }


@router.post("/scripts/run")
async def run_script(body: dict) -> dict:
    """Execute a script from the native registry.

    Body: { app_id: str, script_id: str, args?: dict }
    Runs synchronously (up to 30s timeout) and returns stdout/stderr.
    """
    import asyncio, subprocess, shlex
    from pathlib import Path as _Path

    app_id = body.get("app_id", "")
    script_name = body.get("script_id", "")

    scripts = app_registry.get_scripts()
    match = next(
        (s for s in scripts if s["app_id"] == app_id and s["name"] == script_name),
        None,
    )
    if match is None:
        raise HTTPException(status_code=404, detail=f"Script '{app_id}/{script_name}' not found")

    script_path = _Path(match["app_path"]) / match.get("path", match["name"])
    if not script_path.exists():
        raise HTTPException(status_code=404, detail=f"Script file missing: {script_path}")

    # Determine how to invoke it
    ext = script_path.suffix.lower()
    if ext == ".py":
        # Use app's venv python if available
        app = app_registry.get(app_id)
        venv = app.get("venv") if app else None
        python = str(_Path(venv) / "bin" / "python3") if venv and (_Path(venv) / "bin" / "python3").exists() else "python3"
        cmd = [python, str(script_path)]
    elif ext in (".sh", ".bash", "") or not ext:
        cmd = ["bash", str(script_path)]
    else:
        cmd = [str(script_path)]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=match["app_path"],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            return {"ok": False, "exit_code": -1, "output": "Script timed out after 30s", "app_id": app_id, "script_id": script_name}
        text = stdout.decode(errors="replace")
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "output": text,
            "app_id": app_id,
            "script_id": script_name,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
