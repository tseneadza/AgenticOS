"""Native Process Manager — Phase 9b (FR-61) + Phase 13c (execution layer).

Owns the full lifecycle of Codehome apps: start, stop, restart, status.
Replaces Hub's internal/manager/manager.go for all operations that previously
required the external Hub on :8085.

Phase 13c (ONE launch system — PHASE13 doc §Locked Decisions #1):
  • ``start`` first asks ``gui.sidecar.launch_config.build_launch_command``
    for a data-driven, multi-step launch plan (app_commands rows). Apps with
    no launch config (or MySQL down) fall back to the legacy registry
    single-command path — one system, graceful degradation.
  • Every spawn uses ``start_new_session=True`` so the child owns its process
    GROUP; stop uses ``os.killpg`` (SIGTERM → grace → SIGKILL) instead of
    child-PID chasing (doc §Locked Decisions #5).
  • Launched processes are persisted to ``app_processes`` via
    ``launch_config.record_process`` / ``mark_process_stopped`` (best-effort:
    a missing DB never blocks a launch).
  • ``stop`` also sweeps DB-known running pids the in-memory table lost
    (e.g. after a sidecar restart) so orphans are actually killed.

Design mirrors the Go implementation so the parallel-run comparison is
apples-to-apples:
  • asyncio.create_subprocess_exec — runs in the sidecar's event loop, no deps
  • SIGTERM → 5-second grace → SIGKILL (same as Hub)
  • Port-probe health check via TCP connect (same as Hub, IPv4 explicit)
  • venv python rewriting (same logic as Hub's shouldRewriteWithVenvPython)
  • Per-app logfile at ~/.agentic-os/logs/<app_id>.log (all steps append)

Constitution guards:
  • stop_all  → requires approval (hub_stop_all gate, same as Phase 6)
  • start/stop/restart individual app → no approval needed (same as Hub)

Public API (all async unless noted):
    start(app_id)       -> ProcessStatus
    stop(app_id)        -> ProcessStatus (adds "killed_pids")
    restart(app_id)     -> ProcessStatus
    status(app_id)      -> ProcessStatus  (sync; merges app_processes rows)
    status_all()        -> dict[str, ProcessStatus]  (sync; in-memory only)
    running_ids()       -> list[str]
    stop_all()          -> dict[str, ProcessStatus]   (approval-gated)

ProcessStatus dict shape — the Phase 9 keys are stable; 13c ADDS keys:
    {
        "app_id":     str,
        "running":    bool,
        "pid":        int | None,      # primary process (first with a port)
        "port":       int | None,
        "url":        str | None,
        "started_at": str | None,      # ISO-8601
        "log_file":   str | None,
        "error":      str | None,
        "processes":  [ {pid, port, port_type, status, started_at}, ... ],
        # stop() responses additionally carry:
        "killed_pids": [int, ...],
    }
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import time
from dataclasses import dataclass
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
_COMPLETION_WAIT_MAX = 300.0     # cap for wait_for_completion steps


# ── data structures ───────────────────────────────────────────────────────────
@dataclass
class _ProcEntry:
    """Internal record for one managed process (an app may own several)."""
    app_id: str
    process: asyncio.subprocess.Process
    pid: int
    port: Optional[int]
    started_at: datetime
    log_file: Optional[str]
    port_type: Optional[str] = None


def _entry_dict(e: _ProcEntry) -> dict:
    return {
        "pid": e.pid,
        "port": e.port,
        "port_type": e.port_type,
        "status": "running" if e.process.returncode is None else "stopped",
        "started_at": e.started_at.isoformat(),
    }


def _make_status(app_id: str, entries: Optional[list[_ProcEntry]] = None,
                 error: str = "", log_file: Optional[str] = None) -> dict:
    """Build a ProcessStatus dict from the app's live proc entries."""
    live = [e for e in (entries or []) if e.process.returncode is None]
    if not live:
        return {
            "app_id": app_id,
            "running": False,
            "pid": None,
            "port": None,
            "url": None,
            "started_at": None,
            "log_file": log_file,
            "error": error or None,
            "processes": [],
        }
    primary = next((e for e in live if e.port), live[0])
    port = primary.port
    return {
        "app_id": app_id,
        "running": True,
        "pid": primary.pid,
        "port": port,
        "url": f"http://localhost:{port}" if port else None,
        "started_at": min(e.started_at for e in live).isoformat(),
        "log_file": primary.log_file,
        "error": None,
        "processes": [_entry_dict(e) for e in live],
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


def _signal_group(pid: int, sig: int) -> bool:
    """Send *sig* to the process GROUP led by *pid* (start_new_session=True
    makes pid == pgid). Falls back to a single-pid kill. Returns True if
    something received the signal."""
    try:
        os.killpg(pid, sig)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        try:
            os.kill(pid, sig)
            return True
        except OSError:
            return False


def _pid_alive(pid: int) -> bool:
    """Signal-0 probe (mirrors launch_config._pid_alive)."""
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _apply_venv_rewrite(command: list[str], venv: str | None) -> list[str]:
    """Substitute venv python where appropriate.

    Mirrors Hub's shouldRewriteWithVenvPython:
      - entry-point is python/python3 → swap with venv python3
      - entry-point is a .py file     → prepend venv python3
      - shell scripts / other binaries → leave untouched
    """
    if not command or not venv:
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


def _resolve_command(entry: dict) -> list[str]:
    """Build the final command list for a legacy registry entry."""
    command: list[str] = list(entry.get("start_command") or [])
    if not command:
        raise ValueError(f"App '{entry['id']}' has no start_command in app.json")
    return _apply_venv_rewrite(command, entry.get("venv"))


def _open_log(app_id: str) -> tuple[Path, int]:
    """Open (or create) the per-app log file; return (path, fd)."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _LOG_DIR / f"{app_id}.log"
    fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    return log_path, fd


# ── app_processes persistence (best-effort — DB down never blocks a launch) ──

def _db_record(app_id: str, pid: int, *, process_type: str | None,
               port: int | None, log_path: str | None,
               health_check_url: str | None = None) -> None:
    try:
        from gui.sidecar import launch_config
        ptype = process_type if process_type in launch_config.PROCESS_TYPES else "other"
        launch_config.record_process(
            app_id, pid, process_type=ptype, port=port,
            log_path=log_path, health_check_url=health_check_url,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("app_processes record failed (%s pid=%d): %s", app_id, pid, exc)


def _db_mark_stopped(pid: int, *, exit_code: int | None = None,
                     error_message: str | None = None) -> None:
    try:
        from gui.sidecar import launch_config
        launch_config.mark_process_stopped(
            pid, exit_code=exit_code, error_message=error_message,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("app_processes mark-stopped failed (pid=%d): %s", pid, exc)


def _load_launch_steps(app_id: str) -> list[dict] | None:
    """Fetch the data-driven launch plan; None → fall back to legacy path.

    Raises ValueError only for a BROKEN config (unresolved template variable)
    — that's a real error the caller should surface, not silently bypass.
    """
    try:
        from gui.sidecar import launch_config
        return launch_config.build_launch_command(app_id)
    except LookupError:
        return None                      # no project row / no app_commands
    except ValueError:
        raise                            # broken config — fail loudly
    except Exception as exc:  # noqa: BLE001
        log.warning("launch config unavailable for %s (%s) — legacy path",
                    app_id, exc)
        return None


# ── manager singleton ──────────────────────────────────────────────────────────
class _ProcessManager:
    """Singleton that owns all managed Codehome app processes."""

    def __init__(self) -> None:
        self._procs: dict[str, list[_ProcEntry]] = {}  # app_id → entries
        self._starting: set[str] = set()               # apps mid-launch
        self._lock = asyncio.Lock()                    # protects both

    # ── internal ────────────────────────────────────────────────────────────

    def _live_entries(self, app_id: str) -> list[_ProcEntry]:
        """Prune dead entries; return the still-running ones."""
        entries = self._procs.get(app_id, [])
        live = [e for e in entries if e.process.returncode is None]
        if live:
            self._procs[app_id] = live
        elif app_id in self._procs:
            del self._procs[app_id]
        return live

    async def _spawn(self, app_id: str, cmd: list[str], cwd: str,
                     env: dict) -> tuple[asyncio.subprocess.Process, str]:
        """Spawn one process-group leader logging to the app's log file."""
        log_path, log_fd = _open_log(app_id)
        log.info("start(%s): %s (cwd=%s, log=%s)", app_id, cmd, cwd, log_path)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                env=env,
                stdout=log_fd,
                stderr=log_fd,
                start_new_session=True,  # own process group → killpg works
            )
        finally:
            try:
                os.close(log_fd)   # fd duped by subprocess
            except OSError:
                pass
        return proc, str(log_path)

    async def _abort_entries(self, entries: list[_ProcEntry]) -> None:
        """Kill already-started steps after a later step failed."""
        for e in entries:
            _signal_group(e.pid, signal.SIGTERM)
        await asyncio.sleep(0.3)
        for e in entries:
            if e.process.returncode is None:
                _signal_group(e.pid, signal.SIGKILL)
            _db_mark_stopped(e.pid, error_message="aborted: sibling step failed")

    # ── launch paths ────────────────────────────────────────────────────────

    async def _launch_steps(self, app_id: str, steps: list[dict]) -> dict:
        """Phase 13c: execute a data-driven multi-step launch plan."""
        entries: list[_ProcEntry] = []
        log_file: str | None = None

        for step in steps:
            cmd = _apply_venv_rewrite(
                [step["command"], *step.get("args", [])], step.get("venv"))
            env = {**os.environ, **step.get("env", {})}
            port = step.get("port")
            if port and "PORT" not in step.get("env", {}):
                env["PORT"] = str(port)

            # Free a squatted port before binding a port-bearing step
            if port and _port_in_use(port):
                log.warning("start(%s) step %s: port %d in use — freeing",
                            app_id, step["step"], port)
                _kill_port(port)
                if _port_in_use(port):
                    await self._abort_entries(entries)
                    return _make_status(
                        app_id,
                        error=f"Port {port} still in use after attempted kill")

            try:
                proc, log_file = await self._spawn(
                    app_id, cmd, step["cwd"], env)
            except Exception as exc:  # noqa: BLE001
                await self._abort_entries(entries)
                return _make_status(
                    app_id, error=f"Spawn failed (step {step['step']}): {exc}")

            hc_url = (step.get("health_check") or {}).get("url")

            if step.get("wait_for_completion"):
                # Transient step (migration etc.) — record, wait, mark stopped.
                _db_record(app_id, proc.pid, process_type=step.get("port_type"),
                           port=port, log_path=log_file, health_check_url=hc_url)
                timeout = min(
                    float(step.get("timeout_seconds") or _COMPLETION_WAIT_MAX),
                    _COMPLETION_WAIT_MAX)
                try:
                    rc = await asyncio.wait_for(proc.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    _signal_group(proc.pid, signal.SIGKILL)
                    _db_mark_stopped(proc.pid, error_message="completion timeout")
                    await self._abort_entries(entries)
                    return _make_status(
                        app_id,
                        error=f"Step {step['step']} timed out after {timeout:.0f}s")
                _db_mark_stopped(proc.pid, exit_code=rc)
                if rc != 0:
                    await self._abort_entries(entries)
                    return _make_status(
                        app_id,
                        error=f"Step {step['step']} exited with code {rc} — "
                              f"check {log_file}")
                continue

            # Long-running step — brief immediate-death check
            await asyncio.sleep(0.5)
            if proc.returncode is not None:
                await self._abort_entries(entries)
                return _make_status(
                    app_id,
                    error=f"Step {step['step']} exited immediately "
                          f"(code {proc.returncode}) — check {log_file}")

            _db_record(app_id, proc.pid, process_type=step.get("port_type"),
                       port=port, log_path=log_file, health_check_url=hc_url)
            entries.append(_ProcEntry(
                app_id=app_id, process=proc, pid=proc.pid, port=port,
                started_at=datetime.now(timezone.utc), log_file=log_file,
                port_type=step.get("port_type"),
            ))

            if step.get("wait_for_port") and port:
                deadline = time.monotonic() + float(
                    step.get("timeout_seconds") or _PORT_WAIT_MAX)
                while time.monotonic() < deadline:
                    if proc.returncode is not None:
                        _db_mark_stopped(
                            proc.pid, exit_code=proc.returncode,
                            error_message=f"exited waiting for port {port}")
                        entries.pop()  # it's dead — not a live entry
                        await self._abort_entries(entries)
                        return _make_status(
                            app_id,
                            error=f"Step {step['step']} exited while waiting "
                                  f"for port {port}")
                    if _port_in_use(port):
                        break
                    await asyncio.sleep(_PORT_WAIT_STEP)
                else:
                    log.warning(
                        "start(%s) step %s: port %d not listening after "
                        "timeout (process still running)",
                        app_id, step["step"], port)

        if not entries:
            return _make_status(
                app_id, log_file=log_file,
                error="Launch config contained no long-running steps")

        async with self._lock:
            self._procs[app_id] = entries
        log.info("start(%s): up via launch config (%d process(es): %s)",
                 app_id, len(entries), [e.pid for e in entries])
        return _make_status(app_id, entries)

    async def _launch_legacy(self, app_id: str) -> dict:
        """Phase 9 path: single registry command + expected_port."""
        app = app_registry.get(app_id)
        if app is None:
            return _make_status(app_id, error=f"App '{app_id}' not found in registry")

        port: int | None = app.get("expected_port")

        if port and _port_in_use(port):
            log.warning("start(%s): port %d in use — attempting to free", app_id, port)
            _kill_port(port)
            if _port_in_use(port):
                return _make_status(
                    app_id, error=f"Port {port} still in use after attempted kill")

        try:
            cmd = _resolve_command(app)
        except ValueError as exc:
            return _make_status(app_id, error=str(exc))

        env = {**os.environ}
        if port:
            env["PORT"] = str(port)

        try:
            proc, log_file = await self._spawn(app_id, cmd, app["app_path"], env)
        except Exception as exc:  # noqa: BLE001
            return _make_status(app_id, error=f"Spawn failed: {exc}")

        await asyncio.sleep(0.5)
        if proc.returncode is not None:
            return _make_status(
                app_id,
                error=f"Process exited immediately (code {proc.returncode}) "
                      f"— check {log_file}")

        entry = _ProcEntry(
            app_id=app_id, process=proc, pid=proc.pid, port=port,
            started_at=datetime.now(timezone.utc), log_file=log_file,
        )
        _db_record(app_id, proc.pid, process_type=None, port=port,
                   log_path=log_file)
        async with self._lock:
            self._procs[app_id] = [entry]

        if port:
            deadline = time.monotonic() + _PORT_WAIT_MAX
            while time.monotonic() < deadline:
                if proc.returncode is not None:
                    _db_mark_stopped(proc.pid, exit_code=proc.returncode,
                                     error_message=f"exited waiting for port {port}")
                    return _make_status(
                        app_id, error=f"Process exited while waiting for port {port}")
                if _port_in_use(port):
                    break
                await asyncio.sleep(_PORT_WAIT_STEP)
            else:
                log.warning(
                    "start(%s): port %d not listening after %.0fs "
                    "(process still running)", app_id, port, _PORT_WAIT_MAX)

        log.info("start(%s): up (pid=%d, port=%s)", app_id, proc.pid, port)
        return _make_status(app_id, [entry])

    # ── public lifecycle ────────────────────────────────────────────────────

    async def start(self, app_id: str) -> dict:
        """Start an app. Launch-config plan when configured, legacy otherwise.

        No-ops if already running; returns current status.
        """
        async with self._lock:
            live = self._live_entries(app_id)
            if live:
                log.info("start(%s): already running (pids=%s)",
                         app_id, [e.pid for e in live])
                return _make_status(app_id, live)
            if app_id in self._starting:
                return _make_status(app_id, error="start already in progress")
            self._starting.add(app_id)

        try:
            try:
                steps = _load_launch_steps(app_id)
            except ValueError as exc:
                return _make_status(app_id, error=f"Launch config error: {exc}")
            if steps:
                return await self._launch_steps(app_id, steps)
            return await self._launch_legacy(app_id)
        finally:
            async with self._lock:
                self._starting.discard(app_id)

    async def stop(self, app_id: str) -> dict:
        """Stop a running app: process-group SIGTERM → grace → SIGKILL.

        Also sweeps DB-known running pids the in-memory table doesn't hold
        (e.g. launched before a sidecar restart).
        """
        async with self._lock:
            entries = self._procs.pop(app_id, [])

        killed_pids: list[int] = []
        log_file = entries[0].log_file if entries else None

        live = [e for e in entries if e.process.returncode is None]
        for e in live:
            log.info("stop(%s): SIGTERM group pgid=%d", app_id, e.pid)
            _signal_group(e.pid, signal.SIGTERM)

        for e in live:
            try:
                await asyncio.wait_for(e.process.wait(),
                                       timeout=_STOP_GRACE_SECONDS)
            except asyncio.TimeoutError:
                log.warning("stop(%s): grace expired — SIGKILL group %d",
                            app_id, e.pid)
                _signal_group(e.pid, signal.SIGKILL)
                await asyncio.sleep(0.2)
            _db_mark_stopped(e.pid, exit_code=e.process.returncode)
            killed_pids.append(e.pid)

        # DB sweep: kill running rows we don't hold in memory (orphans from a
        # previous sidecar life). get_app_status pid-verifies rows for us.
        try:
            from gui.sidecar import launch_config
            db_status = launch_config.get_app_status(app_id)
            for p in db_status.get("processes", []):
                pid = p.get("pid")
                if (p.get("status") == "running" and pid
                        and pid not in killed_pids):
                    log.info("stop(%s): SIGTERM orphan group pgid=%d", app_id, pid)
                    _signal_group(pid, signal.SIGTERM)
                    deadline = time.monotonic() + _STOP_GRACE_SECONDS
                    while time.monotonic() < deadline and _pid_alive(pid):
                        await asyncio.sleep(0.2)
                    if _pid_alive(pid):
                        _signal_group(pid, signal.SIGKILL)
                        await asyncio.sleep(0.2)
                    _db_mark_stopped(pid)
                    killed_pids.append(pid)
        except Exception as exc:  # noqa: BLE001
            log.debug("stop(%s): DB orphan sweep skipped: %s", app_id, exc)

        log.info("stop(%s): stopped (killed_pids=%s)", app_id, killed_pids)
        result = _make_status(app_id, log_file=log_file)
        result["killed_pids"] = killed_pids
        return result

    async def restart(self, app_id: str) -> dict:
        """Stop then start an app."""
        await self.stop(app_id)
        return await self.start(app_id)

    def status(self, app_id: str, *, include_db: bool = True) -> dict:
        """Synchronous status query — safe to call from non-async contexts.

        With ``include_db`` (default) the ``app_processes`` view is merged in:
        DB rows are pid-verified by ``launch_config.get_app_status`` and can
        mark an app running even when this sidecar didn't launch it.
        """
        entries = self._live_entries(app_id)
        base = _make_status(app_id, entries)

        if include_db:
            try:
                from gui.sidecar import launch_config
                db_status = launch_config.get_app_status(app_id)
                if db_status["processes"]:
                    base["processes"] = db_status["processes"]
                db_running = [p for p in db_status["processes"]
                              if p["status"] == "running"]
                if db_running and not base["running"]:
                    primary = next((p for p in db_running if p.get("port")),
                                   db_running[0])
                    base.update({
                        "running": True,
                        "pid": primary.get("pid"),
                        "port": primary.get("port"),
                        "url": (f"http://localhost:{primary['port']}"
                                if primary.get("port") else None),
                        "started_at": primary.get("started_at"),
                    })
            except Exception as exc:  # noqa: BLE001
                log.debug("status(%s): DB merge skipped: %s", app_id, exc)

        # Fall back to port-probe for apps not started by us (Hub-era shim)
        if not base["running"]:
            app = app_registry.get(app_id)
            port = app.get("expected_port") if app else None
            if port and _port_in_use(port):
                return {
                    **base,
                    "running": True,
                    "port": port,
                    "url": f"http://localhost:{port}",
                    "managed": False,  # not started by native manager
                }
        return base

    def status_all(self) -> dict[str, dict]:
        """ProcessStatus for every registry app (in-memory + port-probe only —
        the hot path stays DB-free; per-app detail uses ``status``)."""
        result: dict[str, dict] = {}
        for app in app_registry.get_all():
            result[app["id"]] = self.status(app["id"], include_db=False)
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
