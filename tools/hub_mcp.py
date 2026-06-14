"""Hub MCP wrapper — FR-17, FR-18, FR-19.

Dual-mode module:
  • Import: plain Python functions callable from panels.py, hub_agent.py, etc.
  • MCP server: run as `python -m tools.hub_mcp` to start an stdio MCP server
    that LangGraph workflows reference via the tool protocol (TR-11).

Functional surface:
  FR-17 — list_hub_apps, start_hub_app, stop_hub_app, restart_hub_app
  FR-18 — get_app_manifest, build_agent_tool_registry, call_agent_tool
  FR-19 — list_hub_scripts, run_hub_script, build_script_tool_registry
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import requests
import yaml

log = logging.getLogger(__name__)

_SETTINGS = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "config" / "settings.yaml").read_text()
)["settings"]

HUB_URL = _SETTINGS.get("hub_url", "http://localhost:8085").rstrip("/")


# ============================================================ internal helpers
def _get_json(path: str, timeout: int = 4) -> Any:
    resp = requests.get(f"{HUB_URL}{path}", timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _post_json(path: str, body: dict | None = None, timeout: int = 15) -> Any:
    resp = requests.post(f"{HUB_URL}{path}", json=body or {}, timeout=timeout)
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        return {"ok": True}


def _normalise_app(raw: dict) -> dict:
    """Normalise a Hub card/app object into a stable shape.

    The Hub API has evolved over time; handle both nested-status and flat formats.
    """
    app_id = raw.get("id") or raw.get("app_id", "")
    name = raw.get("name") or raw.get("title", "unknown")

    status_obj = raw.get("status") or {}
    if isinstance(status_obj, dict):
        web = status_obj.get("web") or {}
        running = bool(web.get("running"))
        port = web.get("expected_port") or web.get("port") or raw.get("port")
        url = web.get("url")
    else:
        # flat format: status is a string like "running" / "stopped"
        running = str(status_obj).lower() == "running"
        port = raw.get("port")
        url = raw.get("url")

    # FR-18: agent capability block (None for apps that don't declare one)
    agent_block = raw.get("agent")

    return {
        "id": app_id,
        "name": name,
        "port": port,
        "running": running,
        "url": url,
        "agent": agent_block,
    }


# ============================================================ FR-17: list / start / stop
def list_hub_apps(state: dict | None = None) -> dict:
    """Return all Hub-registered apps with current status.

    Accepts an optional ``state`` kwarg so it can serve directly as a
    LangGraph workflow action without a wrapper lambda.
    """
    try:
        raw = _get_json("/api/cards")
    except Exception as exc:  # noqa: BLE001
        log.warning("Hub unreachable: %s", exc)
        return {"hub_up": False, "error": str(exc), "apps": []}

    # Handle {apps:[...]}, {cards:[...]}, and bare list
    if isinstance(raw, list):
        items = raw
    else:
        items = raw.get("apps") or raw.get("cards") or []

    apps = [_normalise_app(c) for c in items if isinstance(c, dict)]
    running_count = sum(1 for a in apps if a["running"])
    return {"hub_up": True, "apps": apps, "running_count": running_count}


def start_hub_app(app_id: str) -> dict:
    """Start a stopped Codehome app by its Hub app ID."""
    return _post_json(f"/api/cards/{app_id}/start")


def stop_hub_app(app_id: str) -> dict:
    """Stop a running Codehome app by its Hub app ID."""
    return _post_json(f"/api/cards/{app_id}/stop")


def restart_hub_app(app_id: str) -> dict:
    """Restart a Codehome app by its Hub app ID."""
    return _post_json(f"/api/cards/{app_id}/restart")


def hub_app_action(app_id: str, action: str) -> dict:
    """Dispatch start / stop / restart for a Hub app.

    Raises ValueError for unsupported actions so callers get a clean error.
    This is the single point of Hub control — panels.py and hub_agent.py
    both funnel through here (TR-11: Hub accessed as MCP tool, not direct REST).
    """
    if action not in ("start", "stop", "restart"):
        raise ValueError(f"Unsupported Hub action '{action}'")
    return _post_json(f"/api/cards/{app_id}/{action}")


def hub_status() -> dict:
    """Panel-friendly wrapper: list apps + response time, degrade gracefully.

    Used by gui/sidecar/panels.hub_status() so the panel routes through hub_mcp
    instead of making direct REST calls (Phase 6 acceptance criterion).
    """
    try:
        t0 = time.time()
        raw = _get_json("/api/cards")
        elapsed_ms = round((time.time() - t0) * 1000)
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc)}

    if isinstance(raw, list):
        items = raw
    else:
        items = raw.get("apps") or raw.get("cards") or []

    apps = [_normalise_app(c) for c in items if isinstance(c, dict)]
    apps_sorted = sorted(apps, key=lambda a: (not a["running"], a["name"] or ""))
    return {"available": True, "response_ms": elapsed_ms, "apps": apps_sorted}


# ============================================================ FR-18: agent-block manifests
def get_app_manifest(app_id: str) -> dict | None:
    """Return the 'agent' block for a Hub app, or None if not declared.

    Strategy:
      1. Try Hub API per-app detail endpoints (GET /api/apps/{id}, /api/cards/{id}).
      2. Fall back to reading app.json from ~/Codehome filesystem directly.
    """
    for endpoint in (f"/api/apps/{app_id}", f"/api/cards/{app_id}"):
        try:
            detail = _get_json(endpoint)
            agent_block = detail.get("agent")
            if agent_block:
                return agent_block
        except Exception:  # noqa: BLE001
            continue

    # Filesystem fallback: scan ~/Codehome for a matching app.json
    codehome = Path.home() / "Codehome"
    for app_json in codehome.rglob("app.json"):
        try:
            data = json.loads(app_json.read_text())
            if data.get("id") == app_id or app_json.parent.name == app_id:
                return data.get("agent")
        except Exception:  # noqa: BLE001
            continue
    return None


def _fetch_all_manifests() -> dict[str, dict | None]:
    """{app_id: agent_block_or_None} for every Hub-registered app."""
    result: dict[str, dict | None] = {}
    try:
        apps_data = list_hub_apps()
    except Exception:  # noqa: BLE001
        return result

    for app in apps_data.get("apps", []):
        app_id = app.get("id")
        if not app_id:
            continue
        # Agent block may already be embedded in the card listing
        if app.get("agent"):
            result[app_id] = app["agent"]
        else:
            result[app_id] = get_app_manifest(app_id)
    return result


def build_agent_tool_registry() -> dict[str, dict]:
    """FR-18: scan all Hub app 'agent' blocks; return a callable tool registry.

    An app.json with:
        "agent": {
            "api_base": "http://localhost:5100/api",
            "tools": [{"name": "get_draws", "method": "GET", "path": "/draws"}]
        }
    produces a tool named ``keno__get_draws`` in the registry dict.
    New Codehome apps appear automatically without manual registration.
    """
    registry: dict[str, dict] = {}
    for app_id, manifest in _fetch_all_manifests().items():
        if not manifest or "tools" not in manifest:
            continue
        api_base = (manifest.get("api_base") or "").rstrip("/")
        for tool_def in manifest.get("tools", []):
            tool_name = f"{app_id}__{tool_def['name']}"
            registry[tool_name] = {
                "type": "agent_tool",
                "app_id": app_id,
                "name": tool_def["name"],
                "description": tool_def.get("description", f"{tool_def['name']} from {app_id}"),
                "method": tool_def.get("method", "GET").upper(),
                "url": f"{api_base}{tool_def.get('path', '')}",
                "params": tool_def.get("params", {}),
            }
    return registry


def call_agent_tool(tool_name: str, registry: dict, **kwargs: Any) -> dict:
    """Call a dynamically registered agent-block tool by name."""
    if tool_name not in registry:
        raise KeyError(f"Unknown agent tool: {tool_name!r}")
    tool = registry[tool_name]
    url = tool["url"]
    method = tool["method"]
    try:
        if method == "GET":
            resp = requests.get(url, params=kwargs, timeout=10)
        else:
            resp = requests.request(method, url, json=kwargs, timeout=10)
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            return {"ok": True, "body": resp.text[:500]}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "tool": tool_name}


def hub_manifests() -> dict:
    """Return agent manifests for all Hub apps (used by /api/panels/hub/manifests).

    Scans ~/Codehome/**/app.json directly for 'agent' blocks — this is fast
    (just glob + JSON reads) and doesn't require the Hub API to return agent
    data. Falls back to card-listing data for apps with no app.json found.
    """
    # First: scan the filesystem for agent blocks in all app.json files.
    # This is the primary source since the Hub API doesn't expose agent blocks.
    codehome = Path.home() / "Codehome"
    fs_manifests: dict[str, dict] = {}
    if codehome.exists():
        for app_json in codehome.rglob("app.json"):
            try:
                data = json.loads(app_json.read_text())
                agent_block = data.get("agent")
                if agent_block:
                    app_id = data.get("id") or app_json.parent.name
                    fs_manifests[app_id] = agent_block
            except Exception:  # noqa: BLE001
                continue

    # Second: get the app list to know all registered app IDs.
    try:
        result = list_hub_apps()
        manifests: dict[str, dict | None] = {
            app["id"]: fs_manifests.get(app["id"]) or app.get("agent")
            for app in result.get("apps", [])
            if app.get("id")
        }
    except Exception:  # noqa: BLE001
        # Hub unreachable — return whatever filesystem scan found
        manifests = fs_manifests  # type: ignore[assignment]

    # Merge in any filesystem manifests not in the Hub card list
    for app_id, block in fs_manifests.items():
        manifests.setdefault(app_id, block)

    return {"available": True, "manifests": manifests}


# ============================================================ FR-19: scripts discovery
def list_hub_scripts() -> dict:
    """FR-19: return all Hub-registered scripts from GET /api/scripts."""
    try:
        raw = _get_json("/api/scripts")
    except Exception as exc:  # noqa: BLE001
        log.warning("Hub /api/scripts unavailable: %s", exc)
        return {"available": False, "error": str(exc), "scripts": []}

    scripts = raw if isinstance(raw, list) else raw.get("scripts", [])
    normalised = [
        {
            "id": s.get("id") or s.get("name", ""),
            "name": s.get("name", ""),
            "description": s.get("description", ""),
            "command": s.get("command", ""),
        }
        for s in scripts
        if isinstance(s, dict)
    ]
    return {"available": True, "scripts": normalised}


def run_hub_script(script_id: str, args: dict | None = None) -> dict:
    """FR-19: run a Hub script by ID via POST /api/scripts/{id}/run."""
    return _post_json(f"/api/scripts/{script_id}/run", args)


def build_script_tool_registry() -> dict[str, dict]:
    """FR-19: expose each Hub script as a named, callable agent tool.

    Each script becomes a tool named ``hub_script__{script_id}``.
    New scripts added to the Hub appear automatically on the next registry refresh.
    """
    result = list_hub_scripts()
    if not result.get("available"):
        return {}
    registry: dict[str, dict] = {}
    for script in result.get("scripts", []):
        script_id = script["id"]
        if not script_id:
            continue
        registry[f"hub_script__{script_id}"] = {
            "type": "hub_script",
            "script_id": script_id,
            "name": script["name"],
            "description": script.get("description") or f"Run Hub script: {script['name']}",
        }
    return registry


# ============================================================ workflow ACTIONS dict
# All Hub actions callable by name from hub_agent.ACTIONS (TR-11).
ACTIONS: dict[str, Any] = {
    "list_running_apps": list_hub_apps,           # backwards compat with morning-briefing
    "list_hub_apps": list_hub_apps,
    "start_hub_app": lambda state, app_id: start_hub_app(app_id),
    "stop_hub_app": lambda state, app_id: stop_hub_app(app_id),
    "restart_hub_app": lambda state, app_id: restart_hub_app(app_id),
    "list_hub_scripts": lambda state: list_hub_scripts(),
    "get_app_manifest": lambda state, app_id: get_app_manifest(app_id),
    "build_agent_tool_registry": lambda state: build_agent_tool_registry(),
}


# ============================================================ MCP server (python -m tools.hub_mcp)
def _serve_mcp() -> None:  # pragma: no cover
    """Start an stdio MCP server exposing all Hub tools.

    Register in config/tools.yaml:
        hub_mcp:
          command: python
          args: [-m, tools.hub_mcp]
    """
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    server = Server("agentic-os-hub-mcp")

    @server.list_tools()
    async def _list_tools():  # noqa: ANN202
        return [
            Tool(
                name="list_hub_apps",
                description="List all Hub-managed Codehome apps with current running status and ports.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="start_hub_app",
                description="Start a stopped Codehome app by its Hub app ID (e.g. 'keno').",
                inputSchema={
                    "type": "object",
                    "properties": {"app_id": {"type": "string"}},
                    "required": ["app_id"],
                },
            ),
            Tool(
                name="stop_hub_app",
                description="Stop a running Codehome app by its Hub app ID.",
                inputSchema={
                    "type": "object",
                    "properties": {"app_id": {"type": "string"}},
                    "required": ["app_id"],
                },
            ),
            Tool(
                name="restart_hub_app",
                description="Restart (stop then start) a Codehome app by its Hub app ID.",
                inputSchema={
                    "type": "object",
                    "properties": {"app_id": {"type": "string"}},
                    "required": ["app_id"],
                },
            ),
            Tool(
                name="list_hub_scripts",
                description="List all Hub-registered scripts available to run.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="run_hub_script",
                description="Run a Hub script by its script ID.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "script_id": {"type": "string"},
                        "args": {"type": "object", "additionalProperties": True},
                    },
                    "required": ["script_id"],
                },
            ),
            Tool(
                name="get_app_manifest",
                description=(
                    "Get the agent capability manifest for a Hub app "
                    "(the 'agent' block from its app.json, if declared)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {"app_id": {"type": "string"}},
                    "required": ["app_id"],
                },
            ),
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict):  # noqa: ANN202
        try:
            if name == "list_hub_apps":
                result = list_hub_apps()
            elif name == "start_hub_app":
                result = start_hub_app(arguments["app_id"])
            elif name == "stop_hub_app":
                result = stop_hub_app(arguments["app_id"])
            elif name == "restart_hub_app":
                result = restart_hub_app(arguments["app_id"])
            elif name == "list_hub_scripts":
                result = list_hub_scripts()
            elif name == "run_hub_script":
                result = run_hub_script(arguments["script_id"], arguments.get("args"))
            elif name == "get_app_manifest":
                result = {"manifest": get_app_manifest(arguments["app_id"])}
            else:
                result = {"error": f"Unknown tool: {name}"}
        except Exception as exc:  # noqa: BLE001
            result = {"error": str(exc)}
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    import asyncio

    asyncio.run(stdio_server(server))


if __name__ == "__main__":
    _serve_mcp()
