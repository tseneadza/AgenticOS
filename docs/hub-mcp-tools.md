# Hub MCP Tools Reference

Complete reference for the 35 Hub integration tools exposed via the MCP server at `tools/hub_mcp.py`.

See also: `[[HUB_API_AUDIT.md]]` (endpoint verification) and the Brain2 deliverables folder.

## Overview

The Hub MCP module (`tools/hub_mcp.py`) wraps all **27 Hub REST endpoints** into a comprehensive tool registry for workflows and the GUI. The module is dual-mode:

- **Import mode:** Call functions directly from Python (workflows, agents)
- **MCP server mode:** Run as stdio MCP server for external clients (Tauri GUI, future integrations)

All functions are registered in the `ACTIONS` dict for LangGraph workflows and as MCP tools for the server.

## Tool Categories

### 🎮 App Control (5 tools)

**`list_hub_apps()`**  
List all Hub-registered apps with current status.  
Returns: `{"hub_up": bool, "apps": [...], "running_count": int}`

**`start_hub_app(app_id: str)`**  
Start a stopped app by ID.  
Returns: response from Hub API

**`stop_hub_app(app_id: str)`**  
Stop a running app by ID.  
Returns: response from Hub API

**`restart_hub_app(app_id: str)`**  
Restart an app (stop then start).  
Returns: response from Hub API

**`stop_all_apps()`**  
Emergency stop all running apps.  
Returns: response from Hub API

---

### 📋 App Details & Status (4 tools)

**`get_app_detail(app_id: str)`**  
Get full app metadata (name, description, config, type, port, etc.).  
Returns: app dict from Hub

**`get_app_status(app_id: str)`**  
Get current runtime status (PID, port, URL, process state).  
Returns: status object

**`get_app_scripts(app_id: str)`**  
Get scripts available for a specific app.  
Returns: `{"available": bool, "app_id": str, "scripts": [...]}`

**`get_port_assignments()`**  
Get all app ports and reserved system ports.  
Returns: `{"available": bool, "ports": [...]}`

---

### 📊 Logs & Health (2 tools)

**`get_app_logs(app_id: str, limit: int = 100)`**  
Get recent logs for an app.  
Returns: `{"available": bool, "app_id": str, "logs": [...]}`

**`get_app_health(app_id: str)`**  
Get health status (healthy bool, last check, failure count, message).  
Returns: health status object

---

### 📈 Analytics (2 tools)

**`get_app_analytics(app_id: str)`**  
Get usage analytics: start count, total runtime, last used timestamp, current session state.  
Returns: analytics dict

**`get_hub_analytics()`**  
Get overall Hub analytics: total workflows run, tokens used, cost today, success rate.  
Returns: `{"available": bool, ...analytics...}` or error

---

### ⚙️ Environment Variables (3 tools)

**`get_app_env(app_id: str)`**  
Get all environment variables for an app.  
Returns: `{"available": bool, "app_id": str, "env": {...}}`

**`set_app_env(app_id: str, key: str, value: str)`**  
Set an environment variable for an app.  
Returns: response from Hub API

**`delete_app_env(app_id: str, key: str)`**  
Delete an environment variable.  
Returns: `{"ok": bool, ...}` or error

---

### 🏷️ Tags & Filtering (2 tools)

**`list_tags()`**  
Get all tags across all apps.  
Returns: `{"available": bool, "tags": [...]}`

**`filter_apps_by_tag(tag: str)`**  
Get apps filtered by a specific tag.  
Returns: `{"available": bool, "tag": str, "apps": [...]}`

---

### ⭐ Favorites & Recent (3 tools)

**`get_favorite_apps()`**  
Get apps marked as favorites by the user.  
Returns: `{"available": bool, "apps": [...]}`

**`get_recent_apps()`**  
Get apps sorted by last-used timestamp (most recent first).  
Returns: `{"available": bool, "apps": [...]}`

**`toggle_favorite(app_id: str, is_favorite: bool)`**  
Add app to favorites (is_favorite=true) or remove it (is_favorite=false).  
Returns: response from Hub API

---

### 🔧 Scripts (2 tools)

**`list_hub_scripts()`**  
List all Hub-registered scripts (across all apps).  
Returns: `{"available": bool, "scripts": [...]}`

**`run_hub_script(script_id: str, args: dict = None)`**  
Run a Hub script by ID with optional arguments.  
Returns: script execution result

---

### 📦 Manifests & Registries (3 tools)

**`get_app_manifest(app_id: str)`**  
Get the agent capability manifest (the 'agent' block from app.json).  
Returns: `{"manifest": {...}}` or error

**`build_agent_tool_registry()`**  
Build a registry of tools from all apps' agent blocks. Apps declare tools via:  
```json
{
  "agent": {
    "api_base": "http://localhost:5100/api",
    "tools": [{"name": "get_draws", "method": "GET", "path": "/draws"}]
  }
}
```
Tools appear as `{app_id}__{tool_name}` in the registry.  
Returns: `{"registry": {...}}`

**`build_script_tool_registry()`**  
Build a registry of all Hub scripts as callable tools. Scripts appear as `hub_script__{script_id}` in the registry.  
Returns: `{"registry": {...}}`

---

### 🔄 System Operations (2 tools)

**`refresh_app_discovery()`**  
Trigger a manual rescan of ~/Codehome for new or deleted apps.  
Returns: response from Hub API (updated app list)

**`hub_status()` (panel helper)**  
Panel-friendly wrapper: list apps + response time, degrade gracefully.  
Returns: `{"available": bool, "response_ms": int, "apps": [...]}`  
*(Used by GUI panels; not exposed as MCP tool, only for internal use)*

---

## Usage

### In LangGraph Workflows

```python
from tools.hub_mcp import ACTIONS

# In a workflow node
def my_node(state: dict) -> dict:
    # List all apps
    result = ACTIONS["list_hub_apps"](state)
    
    # Get logs for an app
    logs = ACTIONS["get_app_logs"](state, app_id="weather", limit=50)
    
    # Set an environment variable
    ACTIONS["set_app_env"](state, app_id="keno", key="API_KEY", value="secret")
    
    return {"output": result}
```

### As Python Imports

```python
from tools.hub_mcp import (
    list_hub_apps,
    start_hub_app,
    get_app_logs,
    set_app_env,
)

# Direct calls (no state parameter needed for imports)
apps = list_hub_apps()
logs = get_app_logs("weather", limit=100)
start_hub_app("keno")
```

### Via MCP Server

Register in `config/tools.yaml`:

```yaml
tools:
  hub_mcp:
    command: python
    args: ["-m", "tools.hub_mcp"]
```

Then start:

```bash
cd ~/Codehome/AgenticOS
python -m tools.hub_mcp
```

The server exposes all 35 tools via stdio for external clients (Tauri GUI, Claude).

---

## Error Handling

All functions degrade gracefully:

- **Network errors** → `{"error": "message"}`
- **Unavailable endpoints** → `{"available": False, "error": "..."}`
- **Missing data** → Returns empty lists/dicts with `available: false`

Example:

```python
result = get_app_logs("nonexistent_app")
# Returns: {
#   "available": False,
#   "app_id": "nonexistent_app",
#   "error": "404 Not Found",
#   "logs": []
# }
```

---

## Coverage

| Category | Tools | Status |
|----------|-------|--------|
| App Control | 5 | ✅ Complete |
| Details & Status | 4 | ✅ Complete |
| Logs & Health | 2 | ✅ Complete |
| Analytics | 2 | ✅ Complete |
| Environment | 3 | ✅ Complete |
| Tags & Filtering | 2 | ✅ Complete |
| Favorites & Recent | 3 | ✅ Complete |
| Scripts | 2 | ✅ Complete |
| Manifests & Registries | 3 | ✅ Complete |
| System Operations | 2 | ✅ Complete |
| **Total** | **35** | **✅ Complete** |

All 27 Hub REST endpoints are covered.

---

## Implementation Notes

- **Dual-mode:** Same code works as imports and MCP server
- **Graceful degradation:** Hub unreachable? Functions still return structured errors
- **Version handling:** Normalizes both nested and flat API response formats
- **Dynamic discovery:** New Hub apps/scripts appear automatically without code changes
- **No polling:** All calls are request-response; no background watchers

---

See: `tools/hub_mcp.py` for implementation details
