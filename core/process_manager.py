"""Native Process Manager — Phase 9b (FR-61).

Owns the full lifecycle of Codehome apps: start, stop, restart, status.
Replaces Hub's internal/manager/manager.go for all operations that previously
required the external Hub on :8085.

Design mirrors the Go implementation so the parallel-run comparison is
apples-to-apples:
  • asyncio.create_subprocess_exec — runs in the sidecar's event loop, no deps
  • SIGTERM → 5-second grace → SIGKILL (same as Hub)
  • Port-probe health check via TCP connect (same as Hub, IPv4 explicit)
  • venv python rewriting (same logic as Hub's shouldRewriteWithVenvPython)
  • Per-app logfile at ~/.agentic-os/logs/<app_id>.log

Constitution guards:
  • stop_all  → requires approval (hub_stop_all gate, same as Phase 6)
  • start/stop/restart individual app → no approval needed (same as Hub)

Public API (all async):
    start(app_id)       -> ProcessStatus
    stop(app_id)        -> ProcessStatus
    restart(app_id)     -> ProcessStatus
    status(app_id)      -> ProcessStatus
    status_all()        -> dict[str, ProcessStatus]
    running_ids()       -> list[str]
    stop_all()          -> dict[str, ProcessStatus]   (approval-gated)

ProcessStatus dict shape (stable across all 9x sub-phases):
    {
        "app_id":     str,
        "running":    bool,
        "pid":        int | None,
        "port":       int | None,
        "url":        str | None,
        "started_at": str | None,   # ISO-8601
        "log_file":   str | None,
        "error":      str | None,
    }
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core import app_registry

log = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────
_LOG_DIR = Path.home() / ".agentic-os" / "logs"
_STOP_GRACE_SECONDS = 5          # SIGTERM → SIGKILL timeout (mirrors Hub)
_PORT_WAIT_STEP = 0.5            # seconds between port-probe polls
_PORT_WAIT_MAX = 30.0            # max seconds to wait for port to open


# ── data structures ───────────────────────────────────────────────────────────
@dataclass
class _ProcEntry:
    """Internal record for a managed process."""
    app_id: str
    process: asyncio.subprocess.Process
    pid: int
    port: Optional[int]
    started_at: datetime
    log_file: Optional[str]
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


def _make_status(app_id: str, entry: Optional[_ProcEntry] = None,
                 error: str = "") -> dict:
    """Build a ProcessStatus dict from an optional live proc entry."""
    if entry is None or entry.process.returncode is not None:
        return {
            "app_id": app_id,
            "running": False,
            "pid": None,
            "port": None,
            "url": None,
            "started_at": None,
            "log_file": entry.log_file if entry else None,
            "error": error or None,
        }
    port = entry.port
    return {
        "app_id": app_id,
        "running": True,
        "pid": entry.pid,
        "port": port,
        "url": f"http://localhost:{port}" if port else None,
        "started_at": entry.started_at.isoformat(),
        "log_file": entry.log_file,
        "error": None,
    }


# ── helpers ────────────────────────────────────────────────────────────────────
def _port_in_use(port: int) -> bool:
    """TCP probe on 127.0.0.1 — mirrors Hub's isPortInUse (IPv4 explicit)."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _kill_port(port: int) -> None:
    """Best-effort: kill whatever is holding the port (lsof + kill -9)."""
    import subprocess
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=5
        )
        pids = result.stdout.strip().split()
        for pid_str in pids:
            try:
                os.kill(int(pid_str), signal.SIGKILL)
            except (ProcessLookupError, ValueError):
                pass
        if pids:
            time.sleep(0.2)  # let OS release the port
    except Exception as exc:  # noqa: BLE001
        log.debug("_kill_port(%d) error: %s", port, exc)


def _resolve_command(entry: dict) -> list[str]:
    """Build the final command list, substituting venv python where appropriate.

    Mirrors Hub's shouldRewriteWithVenvPython:
      - entry-point is python/python3 → swap with venv python3
      - entry-point is a .py file     → prepend venv python3
      - shell scripts / other binaries → leave untouched
    """
    command: list[str] = list(entry.get("start_command") or [])
    if not command:
        raise ValueError(f"App '{entry['id']}' has no start_command in app.json")

    venv: str | None = entry.get("venv")
    if not venv:
        return command

    venv_python = Path(venv) / "bin" / "python3"
    if not venv_python.exists():
        return command

    first = command[0]
    base = Path(first).name
    if base in ("python", "python3"):
        return [str(venv_python)] + command[1:]
    if first.endswith(".py"):
        return [str(venv_python)] + command
    return command


def _open_log(app_id: str) -> tuple[Path, int]:
    """Open (or create) the per-app log file; return (path, fd)."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _LOG_DIR / f"{app_id}.log"
    fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    return log_path, fd


# ── manager singleton ──────────────────────────────────────────────────────────
class _ProcessManager:
    """Singleton that owns all managed Codehome app processes."""

    def __init__(self) -> None:
        self._procs: dict[str, _ProcEntry] = {}   # app_id → _ProcEntry
        self._lock = asyncio.Lock()                # protects _procs dict

    # ── public lifecycle ────────────────────────────────────────────────────

    async def start(self, app_id: str) -> dict:
        """Start an app. No-ops if already running; returns current status."""
        async with self._lock:
            # Already tracked and still alive?
            entry = self._procs.get(app_id)
            if entry and entry.process.returncode is None:
                log.info("start(%s): already running (pid=%d)", app_id, entry.pid)
                return _make_status(app_id, entry)

            # Look up the registry
            app = app_registry.get(app_id)
            if app is None:
                return _make_status(app_id, error=f"App '{app_id}' not found in registry")

            port: int | None = app.get("expected_port")

            # Free the port if something is squatting on it
            if port and _port_in_use(port):
                log.warning("start(%s): port %d in use — attempting to free", app_id, port)
                _kill_port(port)
                if _port_in_use(port):
                    return _make_status(
                        app_id,
                        error=f"Port {port} still in use after attempted kill"
                    )

            # Resolve command (venv rewrite)
            try:
                cmd = _resolve_command(app)
            except ValueError as exc:
                return _make_status(app_id, error=str(exc))

            # Open log file
            log_path, log_fd = _open_log(app_id)
            log.info("start(%s): %s (log: %s)", app_id, cmd, log_path)

            # Build env: inherit + inject PORT
            env = {**os.environ}
            if port:
                env["PORT"] = str(port)

            # Spawn process
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=app["app_path"],
                    env=env,
                    stdout=log_fd,
                    stderr=log_fd,
                    start_new_session=True,  # detach from sidecar's signal group
                )
            except Exception as exc:  # noqa: BLE001
                os.close(log_fd)
                return _make_status(app_id, error=f"Spawn failed: {exc}")
            finally:
                # fd duped by subprocess; safe to close our handle
                try:
                    os.close(log_fd)
                except OSError:
                    pass

            # Brief check — did it die immediately?
            await asyncio.sleep(0.5)
            if proc.returncode is not None:
                return _make_status(
                    app_id,
                    error=f"Process exited immediately (code {proc.returncode}) — check {log_path}"
                )

            entry = _ProcEntry(
                app_id=app_id,
                process=proc,
                pid=proc.pid,
                port=port,
                started_at=datetime.now(timezone.utc),
                log_file=str(log_path),
            )
            self._procs[app_id] = entry

        # Wait for port to open (outside the dict lock so other ops don't block)
        if port:
            deadline = time.monotonic() + _PORT_WAIT_MAX
            while time.monotonic() < deadline:
                if entry.process.returncode is not None:
                    return _make_status(
                        app_id, error=f"Process exited while waiting for port {port}"
                    )
                if _port_in_use(port):
                    break
                await asyncio.sleep(_PORT_WAIT_STEP)
            else:
                log.warning(
                    "start(%s): port %d not listening after %.0fs (process still running)",
                    app_id, port, _PORT_WAIT_MAX
                )

        log.info("start(%s): up (pid=%d, port=%s)", app_id, entry.pid, port)
        return _make_status(app_id, entry)

    async def stop(self, app_id: str) -> dict:
        """Stop a running app: SIGTERM → grace → SIGKILL."""
        async with self._lock:
            entry = self._procs.get(app_id)
            if entry is None or entry.process.returncode is not None:
                # Already stopped — clean up stale entry if any
                self._procs.pop(app_id, None)
                return _make_status(app_id)

        # Outside the dict lock for the wait
        proc = entry.process
        log.info("stop(%s): SIGTERM pid=%d", app_id, entry.pid)
        try:
            proc.terminate()   # SIGTERM
        except ProcessLookupError:
            pass

        try:
            await asyncio.wait_for(proc.wait(), timeout=_STOP_GRACE_SECONDS)
        except asyncio.TimeoutError:
            log.warning("stop(%s): grace period expired — SIGKILL", app_id)
            try:
                proc.kill()    # SIGKILL
            except ProcessLookupError:
                pass
            await asyncio.sleep(0.2)

        async with self._lock:
            self._procs.pop(app_id, None)

        log.info("stop(%s): stopped", app_id)
        return _make_status(app_id, log_file=entry.log_file)

    async def restart(self, app_id: str) -> dict:
        """Stop then start an app."""
        await self.stop(app_id)
        return await self.start(app_id)

    def status(self, app_id: str) -> dict:
        """Synchronous status query — safe to call from non-async contexts."""
        entry = self._procs.get(app_id)

        # Check if the process died since last check
        if entry and entry.process.returncode is not None:
            self._procs.pop(app_id, None)
            entry = None

        # Fall back to port-probe for apps not started by us (e.g. Hub-managed)
        if entry is None:
            app = app_registry.get(app_id)
            port = app.get("expected_port") if app else None
            if port and _port_in_use(port):
                # Running, but not owned by us — return partial status
                return {
                    "app_id": app_id,
                    "running": True,
                    "pid": None,
                    "port": port,
                    "url": f"http://localhost:{port}",
                    "started_at": None,
                    "log_file": None,
                    "error": None,
                    "managed": False,  # not started by native manager
                }

        return _make_status(app_id, entry)

    def status_all(self) -> dict[str, dict]:
        """Return ProcessStatus for every app in the registry."""
        result: dict[str, dict] = {}
        for app in app_registry.get_all():
            result[app["id"]] = self.status(app["id"])
        return result

    def running_ids(self) -> list[str]:
        """IDs of apps currently running (owned by this manager or port-alive)."""
        return [
            app_id for app_id, s in self.status_all().items() if s["running"]
        ]

    async def stop_all(self) -> dict[str, dict]:
        """Stop every running app. Constitution gate applied at the route layer."""
        ids = list(self._procs.keys())
        results: dict[str, dict] = {}
        for app_id in ids:
            results[app_id] = await self.stop(app_id)
        return results


# Module-level singleton — imported by api_apps.py
manager = _ProcessManager()
