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

# Phase 9d: Hub decommissioned. HUB_URL kept for the small set of functions
# (analytics, env vars, tags, favorites) that still make Hub HTTP calls.
# Those are non-load-bearing for the native stack; they degrade gracefully
# if Hub is absent. The core functions (list, start, stop, manifests,
# scripts) all read from core/app_registry + core/process_manager instead.
HUB_URL = _SETTINGS.get("hub_url", "http://localhost:8085").rstrip("/")


# ============================================================ internal helpers
def _get_json(path: str, timeout: int = 4) -> Any:
    """Send a GET request to the Hub API and return the parsed JSON response.

    Args:
        path: API endpoint path (e.g. "/api/cards").
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON response body.

    Raises:
        requests.HTTPError: If the Hub returns a non-2xx status.
    """
    resp = requests.get(f"{HUB_URL}{path}", timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _post_json(path: str, body: dict | None = None, timeout: int = 15) -> Any:
    """Send a POST request to the Hub API and return the parsed JSON response.

    Args:
        path: API endpoint path (e.g. "/api/cards/{id}/start").
        body: Optional JSON body to send with the request.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON response body, or ``{"ok": True}`` if the response has no JSON.

    Raises:
        requests.HTTPError: If the Hub returns a non-2xx status.
    """
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
    """Return all Codehome apps with current running status.

    Phase 9c: primary source is the native app_registry + process_manager.
    Falls back to Hub HTTP if the native scan fails (parallel-run safety net).
    Accepts an optional ``state`` kwarg so it can serve directly as a
    LangGraph workflow action without a wrapper lambda.
    """
    try:
        from core import app_registry
        from core.process_manager import manager
        apps_raw = app_registry.get_all()
        statuses = manager.status_all()
        apps = []
        for a in apps_raw:
            s = statuses.get(a["id"], {})
            apps.append({
                "id": a["id"],
                "name": a["name"],
                "port": a.get("expected_port"),
                "running": s.get("running", False),
                "url": s.get("url"),
                "agent": a.get("agent"),
            })
        running_count = sum(1 for a in apps if a["running"])
        return {"hub_up": True, "native": True, "apps": apps, "running_count": running_count}
    except Exception as exc:  # noqa: BLE001
        log.warning("Native registry failed, falling back to Hub: %s", exc)
    # Hub fallback
    try:
        raw = _get_json("/api/cards")
    except Exception as exc2:  # noqa: BLE001
        log.warning("Hub also unreachable: %s", exc2)
        return {"hub_up": False, "native": False, "error": str(exc2), "apps": []}
    if isinstance(raw, list):
        items = raw
    else:
        items = raw.get("apps") or raw.get("cards") or []
    apps = [_normalise_app(c) for c in items if isinstance(c, dict)]
    running_count = sum(1 for a in apps if a["running"])
    return {"hub_up": True, "native": False, "apps": apps, "running_count": running_count}


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

    Phase 9c: sources from native registry/process_manager first.
    Used by gui/sidecar/panels.hub_status() so the panel routes through hub_mcp
    instead of making direct REST calls (Phase 6 acceptance criterion).
    """
    try:
        t0 = time.time()
        result = list_hub_apps()
        elapsed_ms = round((time.time() - t0) * 1000)
        if not result.get("hub_up"):
            return {"available": False, "error": result.get("error", "unknown")}
        apps = result.get("apps", [])
        apps_sorted = sorted(apps, key=lambda a: (not a["running"], a["name"] or ""))
        return {
            "available": True,
            "native": result.get("native", False),
            "response_ms": elapsed_ms,
            "apps": apps_sorted,
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc)}


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
    """{app_id: agent_block_or_None} -- Phase 9c: read from native registry."""
    try:
        from core import app_registry
        return app_registry.get_manifests()
    except Exception as exc:  # noqa: BLE001
        log.warning("Native manifest scan failed, falling back to Hub: %s", exc)
    result: dict[str, dict | None] = {}
    try:
        apps_data = list_hub_apps()
    except Exception:  # noqa: BLE001
        return result
    for app in apps_data.get("apps", []):
        app_id = app.get("id")
        if not app_id:
            continue
        result[app_id] = app.get("agent") or get_app_manifest(app_id)
    return result


def build_agent_tool_registry() -> dict[str, dict]:
    """FR-18: scan all app agent blocks; return a callable tool registry.

    Phase 9c: reads from native app_registry (no Hub round-trip).
    Contract unchanged -- callers see the same {tool_name: tool_def} dict.
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
    """Return agent manifests for all apps (used by /api/panels/hub/manifests).

    Phase 9c: delegates to native app_registry -- no Hub round-trip.
    """
    try:
        from core import app_registry
        manifests = app_registry.get_manifests()
        return {"available": True, "native": True, "manifests": manifests}
    except Exception as exc:  # noqa: BLE001
        log.warning("Native manifest scan failed: %s", exc)
        return {"available": False, "error": str(exc), "manifests": {}}


# ============================================================ App Details & Status
def get_app_detail(app_id: str) -> dict:
    """Get full details for a specific app from GET /api/cards/{id}."""
    try:
        return _get_json(f"/api/cards/{app_id}")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "app_id": app_id}


def get_app_status(app_id: str) -> dict:
    """Get current status for an app from GET /api/cards/{id}/status."""
    try:
        return _get_json(f"/api/cards/{app_id}/status")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "app_id": app_id}


def get_app_scripts(app_id: str) -> dict:
    """Get scripts available for a specific app from GET /api/cards/{id}/scripts."""
    try:
        scripts = _get_json(f"/api/cards/{app_id}/scripts")
        items = scripts if isinstance(scripts, list) else scripts.get("scripts", [])
        return {"available": True, "app_id": app_id, "scripts": items}
    except Exception as exc:  # noqa: BLE001
        log.warning("Hub /api/cards/%s/scripts unavailable: %s", app_id, exc)
        return {"available": False, "app_id": app_id, "error": str(exc), "scripts": []}


def get_port_assignments() -> dict:
    """Get all port assignments from GET /api/ports."""
    try:
        data = _get_json("/api/ports")
        ports = data if isinstance(data, list) else data.get("ports", [])
        return {"available": True, "ports": ports}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc), "ports": []}


# ============================================================ Logs & Health
def get_app_logs(app_id: str, limit: int = 100) -> dict:
    """Get application logs from GET /api/cards/{id}/logs."""
    try:
        logs = _get_json(f"/api/cards/{app_id}/logs?limit={limit}")
        items = logs if isinstance(logs, list) else logs.get("logs", [])
        return {"available": True, "app_id": app_id, "logs": items}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "app_id": app_id, "error": str(exc), "logs": []}


def get_app_health(app_id: str) -> dict:
    """Get health status for an app from GET /api/cards/{id}/health."""
    try:
        return _get_json(f"/api/cards/{app_id}/health")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "app_id": app_id}


# ============================================================ Analytics
def get_app_analytics(app_id: str) -> dict:
    """Get analytics for a specific app from GET /api/cards/{id}/analytics."""
    try:
        return _get_json(f"/api/cards/{app_id}/analytics")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "app_id": app_id}


def get_hub_analytics() -> dict:
    """Get overall Hub analytics from GET /api/analytics."""
    try:
        return _get_json("/api/analytics")
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc)}


# ============================================================ Environment Variables
def get_app_env(app_id: str) -> dict:
    """Get environment variables for an app from GET /api/cards/{id}/env."""
    try:
        data = _get_json(f"/api/cards/{app_id}/env")
        env = data if isinstance(data, dict) else data.get("env", {})
        return {"available": True, "app_id": app_id, "env": env}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "app_id": app_id, "error": str(exc), "env": {}}


def set_app_env(app_id: str, key: str, value: str) -> dict:
    """Set an environment variable for an app via POST /api/cards/{id}/env."""
    return _post_json(f"/api/cards/{app_id}/env", {key: value})


def delete_app_env(app_id: str, key: str) -> dict:
    """Delete an environment variable via DELETE /api/cards/{id}/env/{key}."""
    try:
        resp = requests.delete(f"{HUB_URL}/api/cards/{app_id}/env/{key}", timeout=10)
        resp.raise_for_status()
        return {"ok": True, "app_id": app_id, "key": key}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "app_id": app_id, "key": key}


# ============================================================ Tags & Filtering
def list_tags() -> dict:
    """Get all available tags from GET /api/tags."""
    try:
        tags = _get_json("/api/tags")
        items = tags if isinstance(tags, list) else tags.get("tags", [])
        return {"available": True, "tags": items}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc), "tags": []}


def filter_apps_by_tag(tag: str) -> dict:
    """Get apps filtered by a specific tag via GET /api/cards?tag=<tag>."""
    try:
        raw = _get_json(f"/api/cards?tag={tag}")
        items = raw if isinstance(raw, list) else raw.get("apps") or raw.get("cards", [])
        apps = [_normalise_app(c) for c in items if isinstance(c, dict)]
        return {"available": True, "tag": tag, "apps": apps}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "tag": tag, "error": str(exc), "apps": []}


# ============================================================ Favorites & Recent
def get_favorite_apps() -> dict:
    """Get user's favorite apps from GET /api/cards/favorites."""
    try:
        raw = _get_json("/api/cards/favorites")
        items = raw if isinstance(raw, list) else raw.get("apps") or raw.get("cards", [])
        apps = [_normalise_app(c) for c in items if isinstance(c, dict)]
        return {"available": True, "apps": apps}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc), "apps": []}


def get_recent_apps() -> dict:
    """Get recently used apps from GET /api/cards/recent."""
    try:
        raw = _get_json("/api/cards/recent")
        items = raw if isinstance(raw, list) else raw.get("apps") or raw.get("cards", [])
        apps = [_normalise_app(c) for c in items if isinstance(c, dict)]
        return {"available": True, "apps": apps}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc), "apps": []}


def toggle_favorite(app_id: str, is_favorite: bool) -> dict:
    """Add or remove an app from favorites."""
    try:
        if is_favorite:
            return _post_json(f"/api/cards/{app_id}/favorite")
        else:
            resp = requests.delete(f"{HUB_URL}/api/cards/{app_id}/favorite", timeout=10)
            resp.raise_for_status()
            return {"ok": True, "app_id": app_id, "is_favorite": False}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "app_id": app_id}


# ============================================================ System Operations
def refresh_app_discovery() -> dict:
    """Trigger app discovery refresh via POST /api/discover."""
    return _post_json("/api/discover")


def stop_all_apps() -> dict:
    """Emergency stop all running apps via POST /api/stop-all."""
    return _post_json("/api/stop-all")


# ============================================================ FR-19: scripts discovery
def list_hub_scripts() -> dict:
    """FR-19: return all Codehome scripts.

    Phase 9c: reads from native app_registry (no Hub round-trip).
    """
    try:
        from core import app_registry
        scripts = app_registry.get_scripts()
        return {"available": True, "native": True, "scripts": scripts}
    except Exception as exc:  # noqa: BLE001
        log.warning("Native script scan failed, falling back to Hub: %s", exc)
    try:
        raw = _get_json("/api/scripts")
    except Exception as exc2:  # noqa: BLE001
        log.warning("Hub /api/scripts unavailable: %s", exc2)
        return {"available": False, "error": str(exc2), "scripts": []}
    scripts_raw = raw if isinstance(raw, list) else raw.get("scripts", [])
    normalised = [
        {
            "id": s.get("id") or s.get("name", ""),
            "name": s.get("name", ""),
            "app_id": s.get("app_id", ""),
            "app_name": s.get("app_name", ""),
            "app_path": s.get("app_path", ""),
            "description": s.get("description", ""),
            "command": s.get("command", ""),
        }
        for s in scripts_raw
        if isinstance(s, dict)
    ]
    return {"available": True, "native": False, "scripts": normalised}


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
        script_id = script.get("id") or script.get("name") or ""
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
    # Backwards compatibility
    "list_running_apps": list_hub_apps,
    # Core app control
    "list_hub_apps": list_hub_apps,
    "start_hub_app": lambda state, app_id: start_hub_app(app_id),
    "stop_hub_app": lambda state, app_id: stop_hub_app(app_id),
    "restart_hub_app": lambda state, app_id: restart_hub_app(app_id),
    "stop_all_apps": lambda state: stop_all_apps(),
    # App details
    "get_app_detail": lambda state, app_id: get_app_detail(app_id),
    "get_app_status": lambda state, app_id: get_app_status(app_id),
    "get_app_scripts": lambda state, app_id: get_app_scripts(app_id),
    "get_port_assignments": lambda state: get_port_assignments(),
    # Logs & diagnostics
    "get_app_logs": lambda state, app_id, limit=100: get_app_logs(app_id, limit),
    "get_app_health": lambda state, app_id: get_app_health(app_id),
    # Analytics
    "get_app_analytics": lambda state, app_id: get_app_analytics(app_id),
    "get_hub_analytics": lambda state: get_hub_analytics(),
    # Environment
    "get_app_env": lambda state, app_id: get_app_env(app_id),
    "set_app_env": lambda state, app_id, key, value: set_app_env(app_id, key, value),
    "delete_app_env": lambda state, app_id, key: delete_app_env(app_id, key),
    # Tags & filtering
    "list_tags": lambda state: list_tags(),
    "filter_apps_by_tag": lambda state, tag: filter_apps_by_tag(tag),
    # Favorites & recent
    "get_favorite_apps": lambda state: get_favorite_apps(),
    "get_recent_apps": lambda state: get_recent_apps(),
    "toggle_favorite": lambda state, app_id, is_favorite: toggle_favorite(app_id, is_favorite),
    # Scripts
    "list_hub_scripts": lambda state: list_hub_scripts(),
    "run_hub_script": lambda state, script_id, args=None: run_hub_script(script_id, args),
    # Manifests & registries
    "get_app_manifest": lambda state, app_id: get_app_manifest(app_id),
    "build_agent_tool_registry": lambda state: build_agent_tool_registry(),
    "build_script_tool_registry": lambda state: build_script_tool_registry(),
    # System
    "refresh_app_discovery": lambda state: refresh_app_discovery(),
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
        """Return the list of MCP tool definitions for all Hub operations."""
        return [
            # ── App Control
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
                name="stop_all_apps",
                description="Emergency stop all running apps at once.",
                inputSchema={"type": "object", "properties": {}},
            ),
            # ── App Details & Status
            Tool(
                name="get_app_detail",
                description="Get full details for a specific app (manifest, config, metadata).",
                inputSchema={
                    "type": "object",
                    "properties": {"app_id": {"type": "string"}},
                    "required": ["app_id"],
                },
            ),
            Tool(
                name="get_app_status",
                description="Get current running status of an app (PID, port, URL).",
                inputSchema={
                    "type": "object",
                    "properties": {"app_id": {"type": "string"}},
                    "required": ["app_id"],
                },
            ),
            Tool(
                name="get_app_scripts",
                description="Get scripts available for a specific app.",
                inputSchema={
                    "type": "object",
                    "properties": {"app_id": {"type": "string"}},
                    "required": ["app_id"],
                },
            ),
            Tool(
                name="get_port_assignments",
                description="Get all port assignments for Hub apps and reserved system ports.",
                inputSchema={"type": "object", "properties": {}},
            ),
            # ── Logs & Health
            Tool(
                name="get_app_logs",
                description="Get recent logs for an app (default 100 lines).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_id": {"type": "string"},
                        "limit": {"type": "integer", "default": 100},
                    },
                    "required": ["app_id"],
                },
            ),
            Tool(
                name="get_app_health",
                description="Get health status for an app (healthy, failure count, last check).",
                inputSchema={
                    "type": "object",
                    "properties": {"app_id": {"type": "string"}},
                    "required": ["app_id"],
                },
            ),
            # ── Analytics
            Tool(
                name="get_app_analytics",
                description="Get usage analytics for a specific app (start count, runtime, last used).",
                inputSchema={
                    "type": "object",
                    "properties": {"app_id": {"type": "string"}},
                    "required": ["app_id"],
                },
            ),
            Tool(
                name="get_hub_analytics",
                description="Get overall Hub analytics (total workflows, tokens, cost, success rate).",
                inputSchema={"type": "object", "properties": {}},
            ),
            # ── Environment Variables
            Tool(
                name="get_app_env",
                description="Get all environment variables for an app.",
                inputSchema={
                    "type": "object",
                    "properties": {"app_id": {"type": "string"}},
                    "required": ["app_id"],
                },
            ),
            Tool(
                name="set_app_env",
                description="Set an environment variable for an app.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_id": {"type": "string"},
                        "key": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "required": ["app_id", "key", "value"],
                },
            ),
            Tool(
                name="delete_app_env",
                description="Delete an environment variable from an app.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_id": {"type": "string"},
                        "key": {"type": "string"},
                    },
                    "required": ["app_id", "key"],
                },
            ),
            # ── Tags & Filtering
            Tool(
                name="list_tags",
                description="Get all available tags across all apps.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="filter_apps_by_tag",
                description="Get apps filtered by a specific tag.",
                inputSchema={
                    "type": "object",
                    "properties": {"tag": {"type": "string"}},
                    "required": ["tag"],
                },
            ),
            # ── Favorites & Recent
            Tool(
                name="get_favorite_apps",
                description="Get user's favorite apps.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="get_recent_apps",
                description="Get recently used apps.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="toggle_favorite",
                description="Add an app to favorites or remove it.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_id": {"type": "string"},
                        "is_favorite": {"type": "boolean"},
                    },
                    "required": ["app_id", "is_favorite"],
                },
            ),
            # ── Scripts
            Tool(
                name="list_hub_scripts",
                description="List all Hub-registered scripts available to run.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="run_hub_script",
                description="Run a Hub script by its script ID with optional arguments.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "script_id": {"type": "string"},
                        "args": {"type": "object", "additionalProperties": True},
                    },
                    "required": ["script_id"],
                },
            ),
            # ── Manifests
            Tool(
                name="get_app_manifest",
                description="Get the agent capability manifest for a Hub app.",
                inputSchema={
                    "type": "object",
                    "properties": {"app_id": {"type": "string"}},
                    "required": ["app_id"],
                },
            ),
            Tool(
                name="build_agent_tool_registry",
                description="Build a registry of tools from all apps' agent blocks.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="build_script_tool_registry",
                description="Build a registry of all Hub scripts as callable tools.",
                inputSchema={"type": "object", "properties": {}},
            ),
            # ── System
            Tool(
                name="refresh_app_discovery",
                description="Trigger a manual app discovery refresh to find new apps.",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict):  # noqa: ANN202
        """Dispatch an MCP tool call to the corresponding Hub function."""
        try:
            # ── App Control
            if name == "list_hub_apps":
                result = list_hub_apps()
            elif name == "start_hub_app":
                result = start_hub_app(arguments["app_id"])
            elif name == "stop_hub_app":
                result = stop_hub_app(arguments["app_id"])
            elif name == "restart_hub_app":
                result = restart_hub_app(arguments["app_id"])
            elif name == "stop_all_apps":
                result = stop_all_apps()
            # ── App Details
            elif name == "get_app_detail":
                result = get_app_detail(arguments["app_id"])
            elif name == "get_app_status":
                result = get_app_status(arguments["app_id"])
            elif name == "get_app_scripts":
                result = get_app_scripts(arguments["app_id"])
            elif name == "get_port_assignments":
                result = get_port_assignments()
            # ── Logs & Health
            elif name == "get_app_logs":
                result = get_app_logs(arguments["app_id"], arguments.get("limit", 100))
            elif name == "get_app_health":
                result = get_app_health(arguments["app_id"])
            # ── Analytics
            elif name == "get_app_analytics":
                result = get_app_analytics(arguments["app_id"])
            elif name == "get_hub_analytics":
                result = get_hub_analytics()
            # ── Environment
            elif name == "get_app_env":
                result = get_app_env(arguments["app_id"])
            elif name == "set_app_env":
                result = set_app_env(arguments["app_id"], arguments["key"], arguments["value"])
            elif name == "delete_app_env":
                result = delete_app_env(arguments["app_id"], arguments["key"])
            # ── Tags & Filtering
            elif name == "list_tags":
                result = list_tags()
            elif name == "filter_apps_by_tag":
                result = filter_apps_by_tag(arguments["tag"])
            # ── Favorites & Recent
            elif name == "get_favorite_apps":
                result = get_favorite_apps()
            elif name == "get_recent_apps":
                result = get_recent_apps()
            elif name == "toggle_favorite":
                result = toggle_favorite(arguments["app_id"], arguments["is_favorite"])
            # ── Scripts
            elif name == "list_hub_scripts":
                result = list_hub_scripts()
            elif name == "run_hub_script":
                result = run_hub_script(arguments["script_id"], arguments.get("args"))
            # ── Manifests
            elif name == "get_app_manifest":
                result = {"manifest": get_app_manifest(arguments["app_id"])}
            elif name == "build_agent_tool_registry":
                result = {"registry": build_agent_tool_registry()}
            elif name == "build_script_tool_registry":
                result = {"registry": build_script_tool_registry()}
            # ── System
            elif name == "refresh_app_discovery":
                result = refresh_app_discovery()
            else:
                result = {"error": f"Unknown tool: {name}"}
        except Exception as exc:  # noqa: BLE001
            result = {"error": str(exc)}
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    import asyncio

    async def _main() -> None:
        """Run the MCP stdio server until the client disconnects."""
        async with stdio_server(server):
            # stdio_server manages I/O; just keep running until stdin closes
            try:
                # Block until stdin closes (MCP client disconnects)
                await asyncio.Event().wait()
            except KeyboardInterrupt:
                pass

    asyncio.run(_main())


if __name__ == "__main__":
    _serve_mcp()
