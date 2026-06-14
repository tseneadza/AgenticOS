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
    workflows = orchestrator.load_workflows()
    return {
        "workflows": [
            {
                "name": name,
                "description": wf.get("description", ""),
                "schedule": wf.get("schedule"),
                "steps": [s["id"] for s in wf.get("steps", [])],
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


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=SIDECAR_PORT, log_level="info")


if __name__ == "__main__":
    main()
