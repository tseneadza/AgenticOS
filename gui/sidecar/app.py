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


def _fetch_rss(url: str) -> list[dict]:
    """Fetch and parse an RSS/Atom feed. Returns list of {title, link, summary, published, domain}."""
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

    _rss_cache[url] = (now, items[:60])
    return items[:60]


# NOTE: GET /api/news/feeds is now served by routes/api_news.py (MySQL-backed,
# schema `AgenticOS`). The previous hardcoded catalogue + _NEWS_FEEDS list were
# migrated into news_db._SEED_FEEDS and are seeded into the DB on first run.


@app.post("/api/news/fetch")
def news_fetch(body: dict) -> dict:
    """Fetch one or more RSS feed URLs and return merged, deduplicated items.

    Body: { "urls": ["https://..."], "keywords": ["quantum", "llm", ...] }
    Returns filtered items sorted newest-first (best-effort; pub date parsing is fuzzy).
    """
    import re as _re

    urls = body.get("urls", [])
    keywords = [k.lower() for k in body.get("keywords", [])]

    if not urls:
        raise HTTPException(400, "urls list required")

    all_items = []
    seen_ids = set()
    errors = []

    for url in urls[:20]:  # cap to prevent abuse
        try:
            items = _fetch_rss(url)
            for item in items:
                if item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    all_items.append(item)
        except HTTPException as e:
            errors.append({"url": url, "error": e.detail})

    # keyword pre-filter (OR logic — keep if any keyword matches title/summary)
    if keywords:
        def _matches(item):
            text = (item["title"] + " " + item["summary"]).lower()
            return any(kw in text for kw in keywords)
        all_items = [i for i in all_items if _matches(i)]

    return {
        "items": all_items,
        "total": len(all_items),
        "errors": errors,
        "cached_until_s": _RSS_TTL,
    }


class NewsRankRequest(BaseModel):
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
