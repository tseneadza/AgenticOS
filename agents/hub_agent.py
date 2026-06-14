"""Hub agent — Codehome Hub control via hub_mcp (FR-17–19, TR-11).

All Hub REST calls are routed through tools/hub_mcp.py so the tool protocol
stays consistent (TR-11: Hub API accessed as MCP tool, not direct REST from
workflow code).

ACTIONS is the dispatch table consumed by core/orchestrator.py.
"""
from __future__ import annotations

# Import all Hub functions from hub_mcp — the single source of truth for Hub I/O.
from tools.hub_mcp import (
    ACTIONS,
    build_agent_tool_registry,
    get_app_manifest,
    hub_app_action,
    list_hub_apps,
    list_hub_scripts,
    run_hub_script,
    start_hub_app,
    stop_hub_app,
    restart_hub_app,
)

__all__ = [
    "ACTIONS",
    "build_agent_tool_registry",
    "get_app_manifest",
    "hub_app_action",
    "list_hub_apps",
    "list_hub_scripts",
    "run_hub_script",
    "start_hub_app",
    "stop_hub_app",
    "restart_hub_app",
]
