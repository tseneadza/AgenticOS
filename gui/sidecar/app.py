"""FastAPI sidecar app (FR-20/21).

Run:  ./.venv/bin/python -m gui.sidecar          (port from settings.yaml)
The Tauri app spawns this as a sidecar process; in dev, run it manually.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core import orchestrator
from gui.sidecar import panels
from gui.sidecar import terminal as terminal_handler
from gui.sidecar.events import bus
from gui.sidecar.runner import runner
from gui.sidecar.routes import api_config
from gui.sidecar.routes import api_tasks
from gui.sidecar.routes import api_news
from gui.sidecar.routes import api_runs
from gui.sidecar.routes import api_apps  # Phase 9a: native app registry
from gui.sidecar.routes import api_agent  # Phase 10: agent model registry
from gui.sidecar.routes import api_projects  # Phase 11c: project creation
from gui.sidecar.routes import api_diagnostics  # Phase 12: self-diagnostics dashboard

_SETTINGS = yaml.safe_load(
    (Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml").read_text()
)["settings"]

SIDECAR_PORT = int(_SETTINGS.get("sidecar_port", 5130))

app = FastAPI(title="AgenticOS Sidecar", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    # Tauri webview origins + Vite dev server
    allow_origins=[
        "tauri://localhost",
        "http://tauri.localhost",
        "http://localhost:1420",
        "http://localhost:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include route handlers
app.include_router(api_config.router)
app.include_router(api_tasks.router)
app.include_router(api_news.router)
app.include_router(api_runs.router)
app.include_router(api_apps.router)  # Phase 9a: native app registry (parallel to Hub)
app.include_router(api_agent.router)  # Phase 10: agent LLM model registry + switching
app.include_router(api_projects.router)  # Phase 11c: project scaffolding
app.include_router(api_diagnostics.router)  # Phase 12: self-diagnostics dashboard


@app.on_event("startup")
async def _ensure_news_schema() -> None:
    """Self-bootstrap the AgenticOS news schema (database + tables + seed).

    Best-effort: if MySQL is down the news routes return 503 and the view
    falls back to its built-in defaults, so a missing DB never blocks startup.
    """
    import logging
    try:
        from gui.sidecar.routes import news_db
        if news_db.is_available():
            news_db.ensure_schema()
    except Exception:  # noqa: BLE001
        logging.getLogger("agentcos.news_db").warning(
            "News schema bootstrap skipped", exc_info=True
        )


@app.on_event("startup")
async def _ensure_projects_schema() -> None:
    """Self-bootstrap the SQLAlchemy schema (projects + ports) — Phase 11c.

    Best-effort: if MySQL is down the projects routes degrade gracefully
    (empty ledger, available=False) so a missing DB never blocks startup.
    """
    import logging
    try:
        from gui.sidecar import db
        db.init_db()
    except Exception:  # noqa: BLE001
        logging.getLogger("agentcos.projects_db").warning(
            "Projects schema bootstrap skipped", exc_info=True
        )


@app.on_event("startup")
async def _reconcile_stale_processes() -> None:
    """Phase 13c: sweep orphaned 'running' app_processes rows at startup.

    A sidecar crash/restart leaves rows whose pids are dead — this puts the
    table back in sync with reality. Best-effort: MySQL down never blocks
    startup.
    """
    import logging
    _log = logging.getLogger("agenticos.launch")
    try:
        from gui.sidecar import launch_config
        result = launch_config.reconcile_stale_processes()
        if result["swept"]:
            _log.warning("reconciled %d stale app_processes row(s): %s",
                         len(result["swept"]), result["swept"])
        else:
            _log.info("app_processes reconcile: %d row(s) checked, all live",
                      result["checked"])
    except Exception:  # noqa: BLE001
        _log.warning("app_processes reconcile skipped", exc_info=True)


@app.on_event("startup")
async def _start_health_poller() -> None:
    """Phase 13e: background HTTP health polling for tracked processes.

    Every 10s, ``launch_config.run_health_checks()`` probes the configured
    endpoint of each running ``app_processes`` row (per-row
    ``interval_seconds`` due-ness is respected inside). Runs in a worker
    thread — its own DB session, blocking httpx probes off the event loop.
    Best-effort: MySQL down or probe errors never kill the loop. The task
    handle lives on app.state so it isn't garbage-collected.
    """
    import logging
    _log = logging.getLogger("agenticos.health")

    async def _loop() -> None:
        while True:
            await asyncio.sleep(10)
            try:
                from gui.sidecar import launch_config
                summary = await asyncio.to_thread(launch_config.run_health_checks)
                if summary.get("transitions"):
                    _log.warning("health: %s", summary["transitions"])
            except Exception:  # noqa: BLE001 — keep polling regardless
                _log.debug("health poll skipped", exc_info=True)

    app.state.health_poller = asyncio.create_task(_loop())


@app.on_event("startup")
async def _attach_loop() -> None:
    """Bind the running asyncio event loop to the AG-UI event bus."""
    bus.attach_loop(asyncio.get_running_loop())


@app.on_event("startup")
async def _start_shell_socket() -> None:
    """FR-10: start the Unix socket server as a background task so the ZSH
    plugin can connect and stream shell events to the shell agent.

    The task is stored on app.state so it is not garbage-collected while
    the event loop is running (a destroyed pending task can segfault uvicorn).
    """
    import logging, traceback, sys
    _log = logging.getLogger("agentcos.shell_socket")
    root = Path(__file__).resolve().parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from core.socket_server import get_server
        from agents.shell_agent import ShellAgent
        server = get_server()
        agent = ShellAgent()
        server.add_handler(agent.handle_event)
        task = asyncio.create_task(server.serve(), name="shell-socket-server")
        app.state.shell_socket_task = task  # keep reference — prevents GC + segfault
        _log.warning("Shell socket server started OK")  # WARNING so it shows at default log level
    except Exception:
        _log.warning(
            "Shell socket server FAILED TO START:\n%s",
            traceback.format_exc(),
        )


@app.on_event("startup")
async def _ensure_hub_running() -> None:
    """Phase 9d: Hub decommissioned — this startup hook is now a no-op.

    Kept in place so git history shows the deliberate removal decision.
    The native app_registry + process_manager replaced all Hub functionality.
    Set hub_autostart: true in settings.yaml to re-enable if needed.
    """
    import logging
    _log = logging.getLogger("agentcos.hub_autostart")
    if _SETTINGS.get("hub_autostart", False):
        # Legacy path — only runs if explicitly re-enabled
        import socket, subprocess
        def _hub_alive() -> bool:
            try:
                with socket.create_connection(("127.0.0.1", 8085), timeout=0.4):
                    return True
            except OSError:
                return False
        async def _run() -> None:
            if _hub_alive():
                return
            home = Path.home()
            hub_bin = home / "Codehome" / "hub" / "hub_server"
            if not hub_bin.exists():
                return
            log_path = home / "Codehome" / "hub" / "hub.log"
            log_fh = open(log_path, "a")
            subprocess.Popen(
                [str(hub_bin)], cwd=str(home / "Codehome" / "hub"),
                stdout=log_fh, stderr=log_fh, start_new_session=True,
            )
        task = asyncio.create_task(_run(), name="hub-autostart")
        app.state.hub_autostart_task = task
    else:
        _log.info("Hub autostart disabled (Phase 9d) — native stack active")
        app.state.hub_autostart_task = None


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    """Clean shutdown: cancel background tasks then remove the PID file.

    The shell socket server and hub-autostart tasks run forever, so uvicorn's
    "Waiting for background tasks" phase hangs unless we cancel them here.
    Cancelling is safe — the ZSH plugin reconnects automatically, and the hub
    is already running as an independent process.
    """
    import os
    import logging

    _log = logging.getLogger("agentcos.shutdown")

    # Cancel every long-running background task we own.
    for attr in ("shell_socket_task", "hub_autostart_task", "apscheduler"):
        task = getattr(app.state, attr, None)
        if task is None:
            continue
        if hasattr(task, "cancel"):          # asyncio.Task
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        elif hasattr(task, "shutdown"):      # APScheduler
            try:
                task.shutdown(wait=False)
            except Exception:
                pass

    # Belt-and-suspenders PID cleanup (atexit also fires, but may be delayed
    # if the process lingers in the "waiting for tasks" phase).
    pid_file = Path.home() / ".agentic-os" / "sidecar.pid"
    try:
        if pid_file.exists() and pid_file.read_text().strip() == str(os.getpid()):
            pid_file.unlink()
            _log.info("PID file removed on shutdown.")
    except OSError:
        pass


@app.on_event("startup")
async def _start_scheduler() -> None:
    """FR-16: start APScheduler as an in-process fallback for scheduled workflows.

    launchd plists are the primary scheduler (install via `python -m core.scheduler install`).
    APScheduler fires workflows directly when the sidecar is already running,
    providing redundancy and a development-mode scheduler without launchd.
    """
    try:
        from core.scheduler import start_apscheduler
        sched = start_apscheduler(runner)
        if sched is not None:
            app.state.apscheduler = sched  # keep reference
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "APScheduler failed to start; scheduled workflows require launchd.",
            exc_info=True,
        )


# ------------------------------------------------------------- workflows
@app.get("/api/workflows")
def list_workflows() -> dict:
    """Return all workflows with metadata: name, description, schedule, steps, cost, run count, last run."""
    from core import memory

    workflows = orchestrator.load_workflows()
    all_runs = memory.recent_runs(limit=1000)

    # Build per-workflow statistics
    wf_stats = {}
    for run in all_runs:
        if run["workflow"] not in wf_stats:
            wf_stats[run["workflow"]] = {
                "cost_total": 0,
                "run_count": 0,
                "last_run": run.get("finished_at") or run.get("started_at"),
            }
        wf_stats[run["workflow"]]["cost_total"] += run.get("cost_usd", 0)
        wf_stats[run["workflow"]]["run_count"] += 1
        if not wf_stats[run["workflow"]]["last_run"] or (run.get("finished_at") or 0) > (wf_stats[run["workflow"]]["last_run"] or 0):
            wf_stats[run["workflow"]]["last_run"] = run.get("finished_at") or run.get("started_at")

    return {
        "workflows": [
            {
                "name": name,
                "description": wf.get("description", ""),
                "schedule": wf.get("schedule"),
                "steps": [s["id"] for s in wf.get("steps", [])],
                "costAvg": wf_stats.get(name, {}).get("cost_total", 0) / max(wf_stats.get(name, {}).get("run_count", 1), 1),
                "runCount": wf_stats.get(name, {}).get("run_count", 0),
                "lastRun": wf_stats.get(name, {}).get("last_run"),
            }
            for name, wf in workflows.items()
        ]
    }


@app.post("/api/workflows/{name}/run")
def run_workflow(name: str) -> dict:
    """Start a workflow run in the background and return the run ID.

    Args:
        name: Name of the workflow to execute.

    Raises:
        HTTPException: 404 if the workflow name is not found.
    """
    if name not in orchestrator.load_workflows():
        raise HTTPException(404, f"Unknown workflow '{name}'")
    run_id = runner.start(name)
    return {"run_id": run_id, "workflow": name}


@app.get("/api/runs")
def runs(limit: int = 20) -> dict:
    """Return recent workflow runs and currently active runs.

    Args:
        limit: Maximum number of historical runs to return.
    """
    from core import memory

    return {"runs": memory.recent_runs(limit=limit), "active": [
        {
            "run_id": h.run_id,
            "workflow": h.workflow,
            "status": h.status,
            "started_at": h.started_at,
        }
        for h in runner.runs.values()
        if h.status in ("running", "waiting_approval")
    ]}


# ------------------------------------------------------------- approvals
class Decision(BaseModel):
    """Request body for approving or denying a pending approval."""

    decision: str  # "approve" | "deny" (any y/yes/approve string approves)


@app.get("/api/approvals")
def approvals() -> dict:
    """Return all pending HITL approval requests."""
    return {"approvals": runner.pending_approvals()}


@app.post("/api/approvals/{approval_id}")
def decide(approval_id: str, body: Decision) -> dict:
    """Resolve a pending approval with an approve or deny decision.

    Args:
        approval_id: ID of the pending approval to resolve.
        body: Decision payload containing the approve/deny string.
    """
    if not runner.resolve_approval(approval_id, body.decision):
        raise HTTPException(404, "No such pending approval")
    return {"ok": True}


# ------------------------------------------------------------- agent models
# Phase 10 / NF-3 (FR-53): model registry + runtime switch over the unified
# LLM provider layer (core/llm.py). Lists configured cloud models + locally
# installed Ollama models; POST switches the active model for later turns.
@app.get("/api/agent/models")
def agent_models(start: bool = True) -> dict:
    """List models. By default (`start=true`) tries to bring Ollama up first and
    re-discovers pulled models; pass `?start=false` for a cheap read-only poll."""
    from core import llm

    return llm.list_models(ensure_ollama=start)


class ModelSelect(BaseModel):
    """Request body for selecting an active LLM model."""

    id: str


@app.post("/api/agent/model")
def agent_set_model(body: ModelSelect) -> dict:
    """Switch the active LLM model for subsequent agent turns.

    Args:
        body: Contains the model ID to activate.

    Raises:
        HTTPException: 404 if the model ID is unknown.
    """
    from core import llm

    try:
        info = llm.set_active_model(body.id)
    except KeyError as exc:
        raise HTTPException(404, f"Unknown model '{body.id}'") from exc
    return {
        "active": info.id,
        "provider": info.provider,
        "label": info.label,
        "is_local": info.is_local,
        "available": llm.is_available(info.id),
    }


# FR-54/57: start a governing-agent turn. Output streams over the AG-UI bus
# (/ws/agui) and the dedicated /ws/agent feed; this POST is the headless trigger.
class AgentChat(BaseModel):
    """Request body for starting a governing-agent chat turn."""

    message: str
    model: str | None = None
    session_id: str = "default"


@app.post("/api/agent/chat")
def agent_chat(body: AgentChat) -> dict:
    """Start a governing-agent turn via HTTP (headless trigger).

    Args:
        body: Chat message, optional model override, and session ID.
    """
    from gui.sidecar.agent_runner import agent_runner

    turn_id = agent_runner.start_turn(
        body.message, model=body.model, session_id=body.session_id
    )
    return {"turn_id": turn_id, "session_id": body.session_id}


# ------------------------------------------------------------- panels
@app.get("/api/panels/system")
def panel_system() -> dict:
    """Return system health metrics (CPU, RAM, disk, network)."""
    return panels.system_health()


@app.get("/api/panels/activity")
def panel_activity() -> dict:
    """Return agent activity stats (cost, tokens, run history)."""
    return panels.agent_activity()


@app.get("/api/panels/keno")
def panel_keno() -> dict:
    """Return Keno data pipeline telemetry (draw counts, sync status)."""
    return panels.keno_telemetry()


@app.get("/api/panels/hub")
def panel_hub() -> dict:
    """Return Codehome Hub status and registered app information."""
    return panels.hub_status()


@app.post("/api/panels/hub/{app_id}/{action}")
def panel_hub_action(app_id: str, action: str) -> dict:
    """Execute a start/stop/restart action on a Hub-managed app.

    Args:
        app_id: Identifier of the Hub application.
        action: Action to perform (start, stop, restart).
    """
    try:
        return panels.hub_app_action(app_id, action)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Hub action failed: {exc}") from exc


@app.post("/api/panels/hub/start")
def panel_hub_start() -> dict:
    """Start the Codehome Hub server if it is not already running."""
    import socket
    import subprocess
    from pathlib import Path

    def _hub_alive() -> bool:
        """Check if the Hub is accepting connections on port 8085."""
        try:
            with socket.create_connection(("127.0.0.1", 8085), timeout=0.4):
                return True
        except OSError:
            return False

    if _hub_alive():
        return {"ok": True, "started": False, "msg": "Hub already running"}

    home = Path.home()
    hub_bin = home / "Codehome" / "hub" / "hub_server"
    if not hub_bin.exists():
        raise HTTPException(503, f"Hub binary not found at {hub_bin}")

    log_path = home / "Codehome" / "hub" / "hub.log"
    try:
        log_fh = open(log_path, "a")  # noqa: WPS515, SIM115
        subprocess.Popen(
            [str(hub_bin)],
            cwd=str(home / "Codehome" / "hub"),
            stdout=log_fh,
            stderr=log_fh,
            start_new_session=True,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Failed to start hub: {exc}") from exc

    return {"ok": True, "started": True, "msg": "Hub starting"}


@app.get("/api/panels/terminal")
def panel_terminal(limit: int = 15) -> dict:
    """Return the last N lines of agent terminal output.

    Args:
        limit: Maximum number of terminal lines to return.
    """
    return panels.iterm_strip(lines=limit)


# FR-18: agent capability manifests for all Hub apps (polled at low frequency)
@app.get("/api/panels/hub/manifests")
def panel_hub_manifests() -> dict:
    """Return agent capability manifests for all Hub-registered apps."""
    return panels.hub_manifests()


# FR-19: Hub scripts discovery
@app.get("/api/panels/hub/scripts")
def panel_hub_scripts() -> dict:
    """Return all Hub-registered scripts for display and tool registry."""
    return panels.hub_scripts()


@app.get("/api/health")
def health() -> dict:
    """Return a simple health check with the sidecar port."""
    return {"ok": True, "port": SIDECAR_PORT}


# ------------------------------------------------------------- Terminal WS
@app.websocket("/ws/terminal")
async def ws_terminal(ws: WebSocket) -> None:
    """FR-33 expanded: full interactive PTY session via xterm.js."""
    await terminal_handler.handle(ws)


# ------------------------------------------------------------- AG-UI WS
@app.websocket("/ws/agui")
async def agui_stream(ws: WebSocket) -> None:
    """AG-UI event stream WebSocket for live workflow and agent updates."""
    await ws.accept()
    # replay recent history so a freshly-opened GUI isn't blank
    for event in bus.history[-50:]:
        await ws.send_json(event)
    q = bus.subscribe()
    try:
        while True:
            event = await q.get()
            await ws.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(q)


# --------------------------------------------------------- Governing agent WS
@app.websocket("/ws/agent")
async def ws_agent(ws: WebSocket) -> None:
    """FR-57: governing-agent stream.

    Inbound: ``{"message": str, "model"?: str, "session_id"?: str}`` starts a
    turn. Outbound: AG-UI events (RUN_STARTED, TEXT_MESSAGE_CONTENT,
    TOOL_CALL_START/END, APPROVAL_REQUIRED, RUN_FINISHED/RUN_ERROR) for this and
    other activity, replayed from recent history on connect.
    """
    from gui.sidecar.agent_runner import agent_runner

    await ws.accept()
    for event in bus.history[-50:]:
        await ws.send_json(event)
    q = bus.subscribe()

    async def _forward() -> None:
        """Forward events from the bus queue to the WebSocket client."""
        while True:
            await ws.send_json(await q.get())

    forward_task = asyncio.create_task(_forward())
    try:
        while True:
            msg = await ws.receive_json()
            text = (msg or {}).get("message", "").strip()
            if text:
                agent_runner.start_turn(
                    text,
                    model=(msg or {}).get("model"),
                    session_id=(msg or {}).get("session_id", "default"),
                )
    except WebSocketDisconnect:
        pass
    finally:
        forward_task.cancel()
        bus.unsubscribe(q)


def main() -> None:  # noqa: C901
    """Start the sidecar uvicorn server with PID-file management and zombie detection."""
    import atexit
    import logging
    import os
    import signal
    import socket
    import time
    import uvicorn

    _log = logging.getLogger("agentcos.main")
    logging.basicConfig(level=logging.INFO)

    my_pid = os.getpid()
    pid_dir = Path.home() / ".agentic-os"
    pid_dir.mkdir(parents=True, exist_ok=True)
    pid_file = pid_dir / "sidecar.pid"

    # ------------------------------------------------------------------ helpers
    def _port_alive(port: int) -> bool:
        """Check if a TCP port is accepting connections on localhost."""
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            return False

    def _process_alive(pid: int) -> bool:
        """True if process exists AND we can signal it (catches PermissionError)."""
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but belongs to another user — treat as not ours.
            return False

    def _wait_port_free(port: int, timeout: float = 3.0, interval: float = 0.25) -> bool:
        """Poll until port is free or timeout expires. Returns True if port is free."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not _port_alive(port):
                return True
            time.sleep(interval)
        return False

    def _safe_cleanup() -> None:
        """Remove PID file only if it still names our PID — guards against races."""
        try:
            if pid_file.exists() and pid_file.read_text().strip() == str(my_pid):
                pid_file.unlink()
        except OSError:
            pass

    # ------------------------------------------------------------------ zombie / duplicate check
    old_pid: int | None = None
    if pid_file.exists():
        try:
            old_pid = int(pid_file.read_text().strip())
        except (ValueError, OSError):
            pid_file.unlink(missing_ok=True)

    if old_pid and old_pid != my_pid:
        if _process_alive(old_pid):
            if _port_alive(SIDECAR_PORT):
                # Healthy duplicate — stand down.
                _log.info(
                    "Sidecar already running (PID %d) on :%d — exiting.",
                    old_pid, SIDECAR_PORT,
                )
                return
            else:
                # Zombie: alive but not serving — evict it and wait for the port.
                _log.warning(
                    "Evicting zombie sidecar PID %d (alive but not on :%d).",
                    old_pid, SIDECAR_PORT,
                )
                try:
                    os.kill(old_pid, signal.SIGKILL)
                except OSError:
                    pass
                if not _wait_port_free(SIDECAR_PORT, timeout=3.0):
                    _log.error(
                        "Port %d still in use after evicting zombie — cannot start.",
                        SIDECAR_PORT,
                    )
                    return
        # Stale PID file (process is dead) — fall through and overwrite.
        pid_file.unlink(missing_ok=True)

    # ------------------------------------------------------------------ fallback port check
    # Catches the case where a sidecar that predates PID-file support is running
    # (no PID file but port is live), or a non-clean start where two processes
    # race and neither has written a file yet.
    if _port_alive(SIDECAR_PORT):
        _log.info(
            "Port %d is live without a PID file — another sidecar is running, exiting.",
            SIDECAR_PORT,
        )
        return

    # ------------------------------------------------------------------ write PID + cleanup hooks
    pid_file.write_text(str(my_pid))

    # Belt-and-suspenders: atexit covers SIGTERM/normal exit; the explicit
    # SIGTERM handler ensures sys.exit() (and therefore atexit) is called even
    # if something else intercepts the signal before uvicorn's handler fires.
    atexit.register(_safe_cleanup)

    _original_sigterm = signal.getsignal(signal.SIGTERM)

    def _sigterm_handler(signum: int, frame: object) -> None:  # noqa: ANN001
        """Handle SIGTERM by cleaning up the PID file before re-raising."""
        _safe_cleanup()
        # Restore and re-raise so uvicorn (and anything else upstream) still sees it.
        signal.signal(signal.SIGTERM, _original_sigterm)
        os.kill(my_pid, signal.SIGTERM)

    signal.signal(signal.SIGTERM, _sigterm_handler)

    uvicorn.run(app, host="127.0.0.1", port=SIDECAR_PORT, log_level="info")


if __name__ == "__main__":
    main()


# ------------------------------------------------------------- run steps (FR-TCV)
@app.get("/api/runs/{run_id}/steps")
def run_steps(run_id: str) -> dict:
    """Return decoded step timeline for a given run_id (= thread_id in LangGraph).

    Reads the run's checkpoint writes from MySQL via the langgraph-checkpoint-mysql
    saver's public `list()` API (which returns already-deserialized
    `(task_id, channel, value)` writes), then returns a list of steps in
    execution order.  Used by the Tool Call Visualizer GUI panel.
    """
    from collections import OrderedDict

    from core import memory

    # Pull every checkpoint for this thread, then walk them oldest-first so the
    # writes accumulate in execution order. `pending_writes` is a list of
    # (task_id, channel, value) tuples, already deserialized by the saver — no
    # manual blob/ormsgpack decoding needed (that was the SQLite-era approach).
    conn = memory.checkpointer_conn()
    try:
        saver = memory.get_checkpointer(conn)
        config = {"configurable": {"thread_id": run_id}}
        tuples = list(saver.list(config))
    finally:
        conn.close()

    if not tuples:
        raise HTTPException(404, f"No steps found for run_id={run_id!r}")

    # Group by task_id so each task becomes one step object
    tasks: OrderedDict[str, dict] = OrderedDict()

    for ct in reversed(tuples):  # reversed(): newest-first -> execution order
        for tid, channel, value in (ct.pending_writes or []):
            task = tasks.setdefault(tid, {"task_id": tid, "channels": {}})
            task["channels"][channel] = value

    # Flatten into a clean step list
    steps = []
    for task in tasks.values():
        channels = task["channels"]

        # Derive step name from 'outputs' dict key or branch edge
        step_name = None
        output_data = None
        branch_to = None
        tokens = None
        cost = None

        if "outputs" in channels and isinstance(channels["outputs"], dict):
            keys = list(channels["outputs"].keys())
            step_name = keys[0] if keys else "unknown"
            output_data = channels["outputs"].get(step_name)

        if "tokens_used" in channels:
            tokens = channels["tokens_used"]

        if "cost_usd" in channels:
            cost = channels["cost_usd"]

        for ch in channels:
            if ch.startswith("branch:to:"):
                branch_to = ch.replace("branch:to:", "")

        steps.append({
            "task_id": task["task_id"],
            "step": step_name,
            "branch_to": branch_to,
            "tokens": tokens,
            "cost_usd": cost,
            "output": output_data,
        })

    return {"run_id": run_id, "steps": steps}


# ------------------------------------------------------------- Web News RSS (FR-WN)
import xml.etree.ElementTree as _ET
import hashlib as _hashlib
import time as _time
from urllib.request import urlopen as _urlopen, Request as _Request

# In-memory cache: url -> (fetched_at, items[])
_rss_cache: dict = {}
_RSS_TTL = 900  # 15 minutes

# ---- article sunset (FR-WN aging) ------------------------------------------
# Articles older than max_age_days are dropped at fetch time. STRICT policy
# (decision 2026-07-02): items with a missing or unparseable published date
# are ALSO dropped — a stale-but-undated article must not slip through.
_DEFAULT_MAX_AGE_DAYS = 7

from datetime import datetime as _dt, timedelta as _td, timezone as _tz
from email.utils import parsedate_to_datetime as _parsedate


def _parse_pub_date(raw: str):
    """Parse an RSS (RFC 2822) or Atom (ISO 8601) date string.

    Returns an aware UTC datetime, or None if the string is empty or
    unparseable. Naive datetimes are assumed to be UTC.
    """
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    # RFC 2822 — "Tue, 30 Jun 2026 14:05:00 GMT" (RSS 2.0 pubDate)
    try:
        d = _parsedate(raw)
        if d is not None:
            return d if d.tzinfo else d.replace(tzinfo=_tz.utc)
    except Exception:
        pass
    # ISO 8601 — "2026-06-30T14:05:00Z" (Atom published/updated, dc:date)
    try:
        d = _dt.fromisoformat(raw.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=_tz.utc)
    except Exception:
        return None

# Namespaces / patterns used for image extraction
import re as _re_img
_MEDIA_NS = "http://search.yahoo.com/mrss/"
_ATOM_NS = "http://www.w3.org/2005/Atom"
_CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
_IMG_RE = _re_img.compile(r'<img[^>]+src=["\']([^"\']+)["\']', _re_img.I)


def _extract_image(el, raw_html: str = "") -> str:
    """Best-effort image URL for an RSS/Atom <item>/<entry> element.

    Checks Media RSS (media:content / media:thumbnail), RSS <enclosure>,
    Atom enclosure <link>, then falls back to the first <img> embedded in
    content:encoded / description HTML.
    """
    # Media RSS: <media:content url=.. /> or <media:thumbnail url=.. />
    for tag in (f"{{{_MEDIA_NS}}}content", f"{{{_MEDIA_NS}}}thumbnail"):
        for node in el.findall(tag):
            url = node.get("url")
            typ = node.get("type", "")
            medium = node.get("medium", "")
            if url and (medium == "image" or typ.startswith("image") or not typ):
                return url
    # RSS 2.0 enclosure
    for enc in el.findall("enclosure"):
        if enc.get("type", "").startswith("image") and enc.get("url"):
            return enc.get("url")
    # Atom enclosure link
    for link_el in el.findall(f"{{{_ATOM_NS}}}link"):
        if link_el.get("rel") == "enclosure" and link_el.get("type", "").startswith("image") and link_el.get("href"):
            return link_el.get("href")
    # Fallback: first <img> inside embedded HTML
    if raw_html:
        m = _IMG_RE.search(raw_html)
        if m:
            return m.group(1)
    return ""



# ---- og:image fallback enrichment (FR-WN images) --------------------------
# Many feeds (e.g. ScienceDaily) ship no image in their RSS. When an item has
# no feed-level image, fetch the article page once and pull its og:image /
# twitter:image. Results are cached (positive + negative). arXiv is skipped
# because its og:image is just the arXiv logo (noise on every card).
import concurrent.futures as _futures
from urllib.parse import urljoin as _urljoin, urlparse as _urlparse

_og_cache: dict = {}
_OG_TTL = 6 * 3600
_OG_SKIP_HOSTS = ("arxiv.org",)
_OG_LOGO_HINTS = ("logo", "/static/", "default-", "placeholder", "sprite", "favicon")
_OG_MAX_PER_FEED = 30
_OG_RE = _re_img.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|og:image:url|og:image:secure_url|twitter:image|twitter:image:src)["\'][^>]+content=["\']([^"\']+)'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|og:image:url|og:image:secure_url|twitter:image|twitter:image:src)["\']',
    _re_img.I,
)

def _og_image(article_url: str) -> str:
    """Return an article page's og:image (absolute URL) or "". Cached for _OG_TTL."""
    if not article_url:
        return ""
    host = (_urlparse(article_url).hostname or "").replace("www.", "")
    if any(host == h or host.endswith("." + h) for h in _OG_SKIP_HOSTS):
        return ""
    now = _time.time()
    hit = _og_cache.get(article_url)
    if hit and now - hit[0] < _OG_TTL:
        return hit[1]
    img = ""
    try:
        req = _Request(article_url, headers={"User-Agent": "Mozilla/5.0 AgenticOS RSS Reader"})
        with _urlopen(req, timeout=6) as resp:
            html = resp.read(200_000).decode("utf-8", "replace")  # <head> is enough
        m = _OG_RE.search(html)
        if m:
            cand = _urljoin(article_url, (m.group(1) or m.group(2) or "").strip())
            low = cand.lower()
            if cand.startswith("http") and not any(h in low for h in _OG_LOGO_HINTS):
                img = cand
    except Exception:
        img = ""
    _og_cache[article_url] = (now, img)
    return img

def _enrich_images(items: list) -> None:
    """Fill missing item['image'] via og:image, in parallel. Mutates in place."""
    todo = [it for it in items if not it.get("image") and it.get("link")][:_OG_MAX_PER_FEED]
    if not todo:
        return
    try:
        with _futures.ThreadPoolExecutor(max_workers=12) as ex:
            results = list(ex.map(lambda i: _og_image(i["link"]), todo))
        for it, img in zip(todo, results):
            if img:
                it["image"] = img
    except Exception:
        pass


def _fetch_rss(url: str) -> list[dict]:
    """Fetch and parse an RSS/Atom feed. Returns list of {title, link, summary, published, domain}."""
    # Normalise: add https:// if scheme is missing (guards against bare-hostname URLs
    # stored by users who omit the protocol when adding feeds in the Settings panel).
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url

    now = _time.time()
    if url in _rss_cache:
        cached_at, items = _rss_cache[url]
        if now - cached_at < _RSS_TTL:
            return items

    try:
        req = _Request(url, headers={"User-Agent": "AgenticOS/1.0 RSS Reader"})
        with _urlopen(req, timeout=8) as resp:
            raw = resp.read()
        root = _ET.fromstring(raw)
    except Exception as e:
        raise HTTPException(502, f"RSS fetch failed for {url}: {e}")

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "dc": "http://purl.org/dc/elements/1.1/",
        "content": "http://purl.org/rss/1.0/modules/content/",
    }

    items = []
    domain = url.split("/")[2].replace("www.", "")

    # RSS 2.0
    for item in root.findall(".//item"):
        def _t(tag, el=item):
            """Extract stripped text from an XML sub-element by tag name."""
            node = el.find(tag)
            return node.text.strip() if node is not None and node.text else ""

        title = _t("title")
        link = _t("link") or _t("guid")
        # Capture raw HTML (content:encoded preferred, else description) for image scraping
        _content_node = item.find(f"{{{_CONTENT_NS}}}encoded")
        _desc_node = item.find("description")
        raw_html = (
            (_content_node.text if _content_node is not None and _content_node.text else "")
            or (_desc_node.text if _desc_node is not None and _desc_node.text else "")
        )
        summary = _t("description") or _t("dc:description", ) or ""
        # strip HTML tags cheaply
        import re as _re
        summary = _re.sub(r"<[^>]+>", "", summary).strip()[:2000]
        image = _extract_image(item, raw_html)
        pub = _t("pubDate") or _t("dc:date")

        if title and link:
            items.append({
                "id": _hashlib.md5(link.encode()).hexdigest()[:12],
                "title": title,
                "link": link,
                "summary": summary,
                "image": image,
                "published": pub,
                "domain": domain,
            })

    # Atom
    if not items:
        for entry in root.findall("atom:entry", ns):
            def _ta(tag, el=entry):
                """Extract stripped text from an Atom entry sub-element by tag name."""
                node = el.find(tag, ns)
                return node.text.strip() if node is not None and node.text else ""
            title = _ta("atom:title")
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            _content_el = entry.find("atom:content", ns)
            raw_html = _content_el.text if _content_el is not None and _content_el.text else ""
            summary = _ta("atom:summary") or _ta("atom:content")
            import re as _re
            summary = _re.sub(r"<[^>]+>", "", summary).strip()[:2000]
            image = _extract_image(entry, raw_html)
            pub = _ta("atom:published") or _ta("atom:updated")
            if title and link:
                items.append({
                    "id": _hashlib.md5(link.encode()).hexdigest()[:12],
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "image": image,
                    "published": pub,
                    "domain": domain,
                })

    items = items[:60]
    _enrich_images(items)
    _rss_cache[url] = (now, items)
    return items


# NOTE: GET /api/news/feeds is now served by routes/api_news.py (MySQL-backed,
# schema `AgenticOS`). The previous hardcoded catalogue + _NEWS_FEEDS list were
# migrated into news_db._SEED_FEEDS and are seeded into the DB on first run.


@app.post("/api/news/fetch")
def news_fetch(body: dict) -> dict:
    """Fetch one or more RSS feed URLs and return merged, deduplicated items.

    Body: { "urls": ["https://..."], "keywords": ["quantum", "llm", ...],
            "feed_map": {"url": {"domain": ..., "label": ...}} (optional),
            "max_age_days": 7 (optional; <=0 disables the age filter) }
    Items older than max_age_days (default 7) are dropped, INCLUDING items
    whose published date is missing or unparseable (strict sunset policy).
    Returns filtered items sorted newest-first (best-effort; pub date parsing is fuzzy).
    Each item includes `feed_url` so the frontend can enrich domain/label without
    ambiguity when multiple feeds share the same hostname.
    """
    import re as _re

    urls = body.get("urls", [])
    keywords = [k.lower() for k in body.get("keywords", [])]
    feed_map = body.get("feed_map", {})  # url -> {domain, label}

    if not urls:
        raise HTTPException(400, "urls list required")

    all_items = []
    seen_ids = set()
    errors = []

    for url in urls[:40]:  # cap to prevent abuse
        try:
            items = _fetch_rss(url)
            for item in items:
                if item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    # Tag each item with its source feed URL so the frontend can
                    # do unambiguous enrichment even when feeds share a hostname.
                    enriched_item = dict(item)
                    enriched_item["feed_url"] = url
                    if url in feed_map:
                        enriched_item["domain_label"] = feed_map[url].get("domain", item["domain"])
                        enriched_item["source_label"] = feed_map[url].get("label", item["domain"])
                    all_items.append(enriched_item)
        except HTTPException as e:
            errors.append({"url": url, "error": e.detail})

    # sunset filter: drop items older than max_age_days; strict — undated or
    # unparseable-date items are dropped too. max_age_days <= 0 disables.
    try:
        max_age_days = int(body.get("max_age_days", _DEFAULT_MAX_AGE_DAYS))
    except (TypeError, ValueError):
        max_age_days = _DEFAULT_MAX_AGE_DAYS
    dropped_old = 0
    if max_age_days > 0:
        cutoff = _dt.now(_tz.utc) - _td(days=max_age_days)

        def _fresh(item):
            """True if the item has a parseable date on/after the cutoff."""
            d = _parse_pub_date(item.get("published", ""))
            return d is not None and d >= cutoff

        before = len(all_items)
        all_items = [i for i in all_items if _fresh(i)]
        dropped_old = before - len(all_items)

    # keyword pre-filter (OR logic — keep if any keyword matches title/summary)
    if keywords:
        def _matches(item):
            """Return True if any keyword appears in the item's title or summary."""
            text = (item["title"] + " " + item["summary"]).lower()
            return any(kw in text for kw in keywords)
        all_items = [i for i in all_items if _matches(i)]

    return {
        "items": all_items,
        "total": len(all_items),
        "errors": errors,
        "dropped_old": dropped_old,
        "max_age_days": max_age_days,
        "cached_until_s": _RSS_TTL,
    }


class NewsRankRequest(BaseModel):
    """Request body for LLM-powered article relevance ranking."""

    articles: list[dict]            # [{title, domain_label?}, ...] (order preserved)
    domains: list[str] = []
    keywords: list[str] = []
    model: str | None = None        # override; defaults to the app's active model


@app.post("/api/news/rank")
def news_rank(body: NewsRankRequest) -> dict:
    """Score fetched articles 0-10 for relevance using the app's active LLM.

    Runs through core.llm.complete() — the SAME unified provider layer the
    governing agent uses — so ranking honors whatever model is selected in the
    GUI (local Ollama or cloud). Returns a `scores` array aligned to the posted
    article order, plus the model/provider/cost used.
    """
    import json as _json
    import re as _re
    from core import llm

    articles = body.articles[:40]  # cap for cost/latency
    if not articles:
        return {"scores": [], "model": llm.active_model()}

    domains = ", ".join(body.domains) or "general science and technology"
    keywords = ", ".join(body.keywords) or "(none specified)"
    listing = "\n".join(
        f"{i + 1}. [{a.get('domain_label') or a.get('domain') or ''}] {a.get('title', '')}"
        for i, a in enumerate(articles)
    )
    prompt = (
        "You are a science news ranker. Score each article 0-10 for how "
        "interesting and significant it is to a researcher interested in: "
        + domains + ".\n\nKeywords of particular interest: " + keywords + ".\n\n"
        "Respond ONLY with a JSON array, one object per article in the same "
        'order: [{"score": 8, "reasoning": "one short sentence why"}, ...]\n\n'
        "Articles:\n" + listing + "\n\nRespond with only the JSON array."
    )

    try:
        result = llm.complete(
            [{"role": "user", "content": prompt}],
            model=body.model,
            max_tokens=2000,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"LLM call failed: {exc}") from exc

    text = result.text or ""
    cleaned = _re.sub(r"```(?:json)?", "", text).strip()
    match = _re.search(r"\[.*\]", cleaned, _re.S)
    payload = match.group(0) if match else cleaned
    try:
        scores = _json.loads(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            502, f"Model did not return valid JSON ({result.model}): {text[:200]}"
        ) from exc

    return {
        "scores": scores,
        "model": result.model,
        "provider": result.provider,
        "cost_usd": result.cost_usd,
        "tokens": result.tokens_used,
    }


# Feed catalogue now lives in MySQL (schema `AgenticOS`, table news_feeds),
# seeded from news_db._SEED_FEEDS. Managed via routes/api_news.py.
