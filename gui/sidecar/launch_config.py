"""Phase 13a — Data-Driven App Launch System: configuration + status layer.

Implements the five "stored procedures" from
``docs/PHASE13_DATA_DRIVEN_LAUNCH_SYSTEM.md`` as plain Python functions with
the doc's exact JSON contracts (decision locked with Tony 2026-07-02: Python,
not MySQL procs, so the in-memory-SQLite test pattern keeps working and live
TCP probes / pid checks are possible).

Division of labour with ``core/process_manager.py`` (Phase 9):
    * THIS module owns the DATA half — reading launch config from the DB,
      resolving template variables, allocating typed ports, and the
      ``app_processes`` bookkeeping (record / mark-stopped / reconcile).
    * ``process_manager`` owns the EXECUTION half — spawning subprocesses,
      SIGTERM→grace→SIGKILL, port polling. Phase 13c extends it to consume
      ``build_launch_command()`` for multi-step apps and to persist via the
      bookkeeping helpers here. There is ONE launch system, not two.

Public API:
    allocate_ports(app_id, port_types, session=None)      -> dict
    build_launch_command(app_id, session=None)            -> list[dict]
    get_app_status(app_id, session=None)                  -> dict
    record_process(...)                                   -> AppProcess
    mark_process_stopped(pid, ...)                        -> bool
    reconcile_stale_processes(session=None)               -> dict
    list_all_processes(session=None)                      -> dict
    log_collision(port, app_id_1, app_id_2, phase, ...)   -> None

Template variables resolved by ``build_launch_command`` (in ``command``,
``args`` items, and ``environment_json`` values):
    {app_path}        -> projects.path
    {venv_path}       -> projects.venv_path
    {<type>_port}     -> ports.port WHERE app_id=? AND port_type=<type>
                         (e.g. {backend_port}, {frontend_port})
Unresolved template-shaped tokens raise ``ValueError`` — we fail loudly
rather than launch a broken command.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ── valid value sets (Python-level validation instead of MySQL ENUMs) ─────────
PORT_TYPES: tuple[str, ...] = ("frontend", "backend", "api", "admin", "other")
PROCESS_TYPES: tuple[str, ...] = (
    "frontend", "backend", "api", "admin", "migration", "other"
)
PROCESS_STATUSES: tuple[str, ...] = ("running", "stopped", "error")

#: How long a stopped process stays visible in ``get_app_status``.
_RECENT_STOP_WINDOW = timedelta(minutes=5)

#: Matches template tokens we know how to resolve — used to detect leftovers.
_TEMPLATE_TOKEN_RE = re.compile(r"\{(app_path|venv_path|[a-z][a-z0-9_]*_port)\}")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _pid_alive(pid: int) -> bool:
    """True if *pid* refers to a live process (signal-0 probe)."""
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:   # alive, owned by someone else
        return True
    except OSError:
        return False


def _session_scope(session):
    """Return (session, owns) — creating one from SessionLocal if needed."""
    from gui.sidecar.db import SessionLocal
    if session is not None:
        return session, False
    return SessionLocal(), True


# ── procedure 1: allocate_ports ───────────────────────────────────────────────

def allocate_ports(app_id: str, port_types: list[str], session=None) -> dict:
    """Allocate (or return existing) typed ports for *app_id*.

    Contract (doc §Procedure 1)::

        {"success": true, "ports": {"backend": 5200, "frontend": 5201}}
        {"success": false, "error": "...", "ports": {...partial...}}

    Idempotent: a port already allocated to (app_id, port_type) is returned
    as-is rather than re-allocated. New allocations reuse the ONE existing
    allocator (``project_manager.allocate_port`` — ledger ∪ registry ∪ live
    TCP probes) and then stamp the row's ``port_type``.
    """
    from gui.sidecar.models import Port
    from gui.sidecar.project_manager import allocate_port

    invalid = [t for t in port_types if t not in PORT_TYPES]
    if invalid:
        return {"success": False,
                "error": f"invalid port_type(s): {invalid}", "ports": {}}
    if len(set(port_types)) != len(port_types):
        return {"success": False,
                "error": "duplicate port_type in request", "ports": {}}

    session, owns = _session_scope(session)
    allocated: dict[str, int] = {}
    try:
        for port_type in port_types:
            existing = (
                session.query(Port)
                .filter_by(app_id=app_id, port_type=port_type)
                .one_or_none()
            )
            if existing is not None:
                allocated[port_type] = existing.port
                continue
            try:
                port = allocate_port(app_id, session=session)
            except RuntimeError as exc:
                return {"success": False, "error": str(exc), "ports": allocated}
            row = session.query(Port).filter_by(port=port).one()
            row.port_type = port_type
            session.commit()
            allocated[port_type] = port
        return {"success": True, "ports": allocated}
    finally:
        if owns:
            session.close()


# ── procedure 2: build_launch_command ─────────────────────────────────────────

def _resolve(value: str, variables: dict[str, str]) -> str:
    """Substitute known template variables in *value*; raise on leftovers."""
    out = value
    for key, val in variables.items():
        out = out.replace("{" + key + "}", val)
    leftover = _TEMPLATE_TOKEN_RE.search(out)
    if leftover:
        raise ValueError(
            f"unresolved template variable {leftover.group(0)!r} in {value!r} "
            f"(known: {sorted(variables)})"
        )
    return out


def build_launch_command(app_id: str, session=None) -> list[dict]:
    """Build the fully-resolved launch steps for *app_id*.

    Contract (doc §Procedure 2): a JSON-ready list of step dicts::

        [{"step", "command", "args", "cwd", "env", "venv", "port_type",
          "port", "wait_for_completion", "wait_for_port", "timeout_seconds",
          "health_check"?}, ...]

    Raises:
        LookupError:  unknown app_id, or no app_commands configured.
        ValueError:   unresolved template variable in command/args/env.
    """
    from gui.sidecar.models import AppCommand, AppHealthCheck, Port, Project

    session, owns = _session_scope(session)
    try:
        project = session.get(Project, app_id)
        if project is None:
            raise LookupError(f"unknown app_id: {app_id!r}")

        commands = (
            session.query(AppCommand)
            .filter_by(app_id=app_id)
            .order_by(AppCommand.step_order)
            .all()
        )
        if not commands:
            raise LookupError(f"no app_commands configured for {app_id!r}")

        ports = {
            row.port_type: row.port
            for row in session.query(Port).filter_by(app_id=app_id).all()
        }
        health = {
            hc.port: hc
            for hc in session.query(AppHealthCheck)
            .filter_by(app_id=app_id, enabled=True)
            .all()
        }

        variables: dict[str, str] = {"app_path": project.path or ""}
        if project.venv_path:
            variables["venv_path"] = project.venv_path
        for port_type, port in ports.items():
            variables[f"{port_type}_port"] = str(port)

        steps: list[dict] = []
        for cmd in commands:
            cwd = Path(project.path)
            wd = (cmd.working_directory or "").strip()
            if wd and wd != ".":
                cwd = cwd / wd

            env = {
                key: _resolve(str(val), variables)
                for key, val in (cmd.environment_json or {}).items()
            }
            port = ports.get(cmd.port_type) if cmd.port_type else None

            step: dict = {
                "step": cmd.step_order,
                "command": _resolve(cmd.command, variables),
                "args": [_resolve(str(a), variables) for a in (cmd.args or [])],
                "cwd": str(cwd),
                "env": env,
                "venv": project.venv_path,
                "port_type": cmd.port_type,
                "port": port,
                "wait_for_completion": bool(cmd.wait_for_completion),
                "wait_for_port": bool(cmd.wait_for_port),
                "timeout_seconds": int(cmd.wait_for_port_timeout_seconds or 30),
            }
            if cmd.health_check_enabled and port is not None and port in health:
                hc = health[port]
                step["health_check"] = {
                    "url": f"http://localhost:{port}{hc.endpoint}",
                    "method": hc.method,
                    "expected_status_code": hc.expected_status_code,
                    "timeout_seconds": hc.timeout_seconds,
                    "interval_seconds": hc.interval_seconds,
                }
            steps.append(step)
        return steps
    finally:
        if owns:
            session.close()


# ── procedure 5 (+ helpers used by 3/4 in process_manager) ────────────────────

def get_app_status(app_id: str, session=None) -> dict:
    """Live status for one app (doc §Procedure 5).

    Verifies every 'running' row against a real pid probe — dead rows are
    marked stopped in place. Recently-stopped rows (< 5 min) stay visible.
    """
    from gui.sidecar.models import AppProcess

    session, owns = _session_scope(session)
    try:
        cutoff = _utcnow() - _RECENT_STOP_WINDOW
        rows = (
            session.query(AppProcess)
            .filter(AppProcess.app_id == app_id)
            .order_by(AppProcess.started_at)
            .all()
        )

        processes: list[dict] = []
        dirty = False
        for row in rows:
            if row.status == "running" and not _pid_alive(row.pid):
                row.status = "stopped"
                row.stopped_at = _utcnow()
                dirty = True
            stopped_at = row.stopped_at
            if stopped_at is not None and stopped_at.tzinfo is None:
                stopped_at = stopped_at.replace(tzinfo=timezone.utc)
            if row.status != "running" and (
                stopped_at is None or stopped_at < cutoff
            ):
                continue  # old history — not part of "current" status
            processes.append({
                "pid": row.pid,
                "port_type": row.process_type,
                "port": row.port,
                "status": row.status,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "is_healthy": bool(row.is_healthy),
                "last_health_check": (
                    row.last_health_check.isoformat()
                    if row.last_health_check else None
                ),
            })
        if dirty:
            session.commit()

        running = [p for p in processes if p["status"] == "running"]
        return {
            "app_id": app_id,
            "running": bool(running),
            "processes": processes,
            "ports": sorted({p["port"] for p in running if p["port"]}),
        }
    finally:
        if owns:
            session.close()


def record_process(
    app_id: str,
    pid: int,
    *,
    process_type: str = "other",
    port: int | None = None,
    log_path: str | None = None,
    health_check_url: str | None = None,
    session=None,
):
    """Insert an ``app_processes`` row for a freshly-launched process."""
    from gui.sidecar.models import AppProcess

    if process_type not in PROCESS_TYPES:
        raise ValueError(f"invalid process_type: {process_type!r}")

    session, owns = _session_scope(session)
    try:
        row = AppProcess(
            app_id=app_id, pid=pid, process_type=process_type, port=port,
            log_path=log_path, health_check_url=health_check_url,
            status="running",
        )
        session.add(row)
        session.commit()
        return row
    finally:
        if owns:
            session.close()


def mark_process_stopped(
    pid: int,
    *,
    exit_code: int | None = None,
    error_message: str | None = None,
    session=None,
) -> bool:
    """Mark the newest 'running' row for *pid* as stopped/errored."""
    from gui.sidecar.models import AppProcess

    session, owns = _session_scope(session)
    try:
        row = (
            session.query(AppProcess)
            .filter_by(pid=pid, status="running")
            .order_by(AppProcess.started_at.desc())
            .first()
        )
        if row is None:
            return False
        row.status = "error" if error_message else "stopped"
        row.stopped_at = _utcnow()
        row.exit_code = exit_code
        row.error_message = error_message
        session.commit()
        return True
    finally:
        if owns:
            session.close()


def reconcile_stale_processes(session=None) -> dict:
    """Startup sweep: mark every 'running' row whose pid is dead as stopped.

    A sidecar crash/restart leaves orphaned 'running' rows behind — this puts
    the table back in sync with reality. Intended to be called once at
    sidecar startup (wired in Phase 13c).
    """
    from gui.sidecar.models import AppProcess

    session, owns = _session_scope(session)
    try:
        rows = session.query(AppProcess).filter_by(status="running").all()
        swept = []
        for row in rows:
            if not _pid_alive(row.pid):
                row.status = "stopped"
                row.stopped_at = _utcnow()
                row.error_message = row.error_message or "reconciled: pid not alive"
                swept.append({"app_id": row.app_id, "pid": row.pid})
        if swept:
            session.commit()
        return {"checked": len(rows), "swept": swept}
    finally:
        if owns:
            session.close()


def list_all_processes(session=None) -> dict:
    """All live processes across all apps (backs GET /api/apps/processes)."""
    from gui.sidecar.models import AppProcess

    session, owns = _session_scope(session)
    try:
        rows = (
            session.query(AppProcess)
            .filter_by(status="running")
            .order_by(AppProcess.app_id, AppProcess.started_at)
            .all()
        )
        processes = []
        dirty = False
        for row in rows:
            if not _pid_alive(row.pid):
                row.status = "stopped"
                row.stopped_at = _utcnow()
                dirty = True
                continue
            processes.append({
                "app_id": row.app_id,
                "pid": row.pid,
                "port": row.port,
                "status": row.status,
            })
        if dirty:
            session.commit()
        return {"processes": processes, "total": len(processes)}
    finally:
        if owns:
            session.close()


def log_collision(
    port: int,
    app_id_1: str | None,
    app_id_2: str | None,
    phase: str,
    notes: str | None = None,
    session=None,
) -> None:
    """Append a row to ``port_collision_log`` (used by 13b backfill + runtime)."""
    from gui.sidecar.models import PortCollisionLog

    session, owns = _session_scope(session)
    try:
        session.add(PortCollisionLog(
            port=port, app_id_1=app_id_1, app_id_2=app_id_2,
            phase=phase, notes=notes,
        ))
        session.commit()
    finally:
        if owns:
            session.close()
