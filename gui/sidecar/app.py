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


@app.on_event("startup")
async def _attach_loop() -> None:
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
    """Auto-start the Codehome Hub if it is not already up.

    Runs as a background task so a slow Hub start does not block the sidecar
    from accepting requests.  The same logic as POST /api/panels/hub/start —
    kept in sync intentionally so both paths behave identically.
    """
    import logging
    import socket
    import subprocess

    _log = logging.getLogger("agentcos.hub_autostart")

    def _hub_alive() -> bool:
        try:
            with socket.create_connection(("127.0.0.1", 8085), timeout=0.4):
                return True
        except OSError:
            return False

    async def _run() -> None:
        if _hub_alive():
            _log.info("Hub already running — skipping auto-start")
            return

        home = Path.home()
        hub_bin = home / "Codehome" / "hub" / "hub_server"
        if not hub_bin.exists():
            _log.warning("Hub binary not found at %s — cannot auto-start", hub_bin)
            return

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
            _log.warning("Hub was down — auto-started hub_server (log: %s)", log_path)
        except Exception as exc:  # noqa: BLE001
            _log.error("Hub auto-start failed: %s", exc)

    task = asyncio.create_task(_run(), name="hub-autostart")
    app.state.hub_autostart_task = task  # prevent GC


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
        if not wf_stats[run["workflow"]]["last_run"] or run.get("finished_at", 0) > wf_stats[run["workflow"]]["last_run"]:
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
    if name not in orchestrator.load_workflows():
        raise HTTPException(404, f"Unknown workflow '{name}'")
    run_id = runner.start(name)
    return {"run_id": run_id, "workflow": name}


@app.get("/api/runs")
def runs(limit: int = 20) -> dict:
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
    decision: str  # "approve" | "deny" (any y/yes/approve string approves)


@app.get("/api/approvals")
def approvals() -> dict:
    return {"approvals": runner.pending_approvals()}


@app.post("/api/approvals/{approval_id}")
def decide(approval_id: str, body: Decision) -> dict:
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
    id: str


@app.post("/api/agent/model")
def agent_set_model(body: ModelSelect) -> dict:
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
    message: str
    model: str | None = None
    session_id: str = "default"


@app.post("/api/agent/chat")
def agent_chat(body: AgentChat) -> dict:
    from gui.sidecar.agent_runner import agent_runner

    turn_id = agent_runner.start_turn(
        body.message, model=body.model, session_id=body.session_id
    )
    return {"turn_id": turn_id, "session_id": body.session_id}


# ------------------------------------------------------------- panels
@app.get("/api/panels/system")
def panel_system() -> dict:
    return panels.system_health()


@app.get("/api/panels/activity")
def panel_activity() -> dict:
    return panels.agent_activity()


@app.get("/api/panels/keno")
def panel_keno() -> dict:
    return panels.keno_telemetry()


@app.get("/api/panels/hub")
def panel_hub() -> dict:
    return panels.hub_status()


@app.post("/api/panels/hub/{app_id}/{action}")
def panel_hub_action(app_id: str, action: str) -> dict:
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
    return panels.iterm_strip(lines=limit)


# FR-18: agent capability manifests for all Hub apps (polled at low frequency)
@app.get("/api/panels/hub/manifests")
def panel_hub_manifests() -> dict:
    return panels.hub_manifests()


# FR-19: Hub scripts discovery
@app.get("/api/panels/hub/scripts")
def panel_hub_scripts() -> dict:
    return panels.hub_scripts()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "port": SIDECAR_PORT}


# ------------------------------------------------------------- Terminal WS
@app.websocket("/ws/terminal")
async def ws_terminal(ws: WebSocket) -> None:
    """FR-33 expanded: full interactive PTY session via xterm.js."""
    await terminal_handler.handle(ws)


# ------------------------------------------------------------- AG-UI WS
@app.websocket("/ws/agui")
async def agui_stream(ws: WebSocket) -> None:
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

    Reads the `writes` table from SQLite, decodes ormsgpack values, and returns
    a list of steps in execution order.  Used by the Tool Call Visualizer GUI panel.
    """
    import sqlite3
    import ormsgpack
    import json as _json
    from pathlib import Path as _Path

    db_path = _Path(__file__).resolve().parents[2] / "data" / "state.db"
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    rows = con.execute(
        "SELECT task_id, channel, type, value FROM writes WHERE thread_id=? ORDER BY rowid",
        (run_id,),
    ).fetchall()
    con.close()

    if not rows:
        raise HTTPException(404, f"No steps found for run_id={run_id!r}")

    # Group by task_id so each task becomes one step object
    from collections import OrderedDict
    tasks: OrderedDict[str, dict] = OrderedDict()

    for row in rows:
        tid = row["task_id"]
        channel = row["channel"]
        typ = row["type"]
        raw = row["value"]

        if tid not in tasks:
            tasks[tid] = {"task_id": tid, "channels": {}}

        if typ == "msgpack" and raw and len(raw) > 1:
            try:
                data = ormsgpack.unpackb(raw)
                tasks[tid]["channels"][channel] = data
            except Exception:
                tasks[tid]["channels"][channel] = f"<decode error: {raw[:40]!r}>"
        elif typ == "null":
            # branch routing edge — record the branch target
            tasks[tid]["channels"][channel] = None

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
