"""Dynamic tool registry — FR-18, FR-19.

Aggregates tools from three sources (in precedence order):
  1. Static tools from config/tools.yaml (highest priority — never overridden)
  2. Hub app 'agent' blocks (FR-18): auto-registers per-app API endpoints as tools
  3. Hub scripts (FR-19): each script becomes a callable tool

The registry is a module-level singleton refreshed at most once per TTL.
Workflow nodes and the sidecar can call ``get_registry()`` to get the
shared instance.

Usage:
    from core.tool_registry import get_registry

    reg = get_registry()
    reg.refresh()                        # no-op if < TTL since last refresh
    tools = reg.list_tools()             # list of {name, description, ...}
    result = reg.call("keno__get_draws") # calls app's /draws endpoint
    result = reg.call("hub_script__sync-keno")  # runs Hub script
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


class ToolRegistry:
    """Aggregated tool registry: Hub agent blocks + Hub scripts + static tools."""

    # Refresh no more than once every 60s to avoid hammering the Hub
    REFRESH_TTL: int = 60

    def __init__(self) -> None:
        self._registry: dict[str, dict] = {}
        self._last_refresh: float = 0.0
        self._static_tools: dict[str, dict] = self._load_static()

    # ----------------------------------------------------------------- static tools
    def _load_static(self) -> dict[str, dict]:
        """Load static tool definitions from config/tools.yaml (if the file exists)."""
        tools_yaml = Path(__file__).resolve().parent.parent / "config" / "tools.yaml"
        if not tools_yaml.exists():
            return {}
        try:
            data = yaml.safe_load(tools_yaml.read_text()) or {}
            return data.get("tools", {})
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to load config/tools.yaml: %s", exc)
            return {}

    # ----------------------------------------------------------------- refresh
    def refresh(self, force: bool = False) -> None:
        """Rebuild the registry from the Hub.

        No-ops if called within REFRESH_TTL seconds of the last refresh,
        unless force=True. Safe to call from any thread/async context.
        """
        now = time.time()
        if not force and (now - self._last_refresh) < self.REFRESH_TTL:
            return

        # Import here to avoid circular import at module load time
        from tools import hub_mcp  # noqa: PLC0415

        registry: dict[str, dict] = {}

        # FR-19: Hub scripts (lower priority than agent-block tools)
        try:
            script_tools = hub_mcp.build_script_tool_registry()
            registry.update(script_tools)
            log.debug("Script tools loaded: %d", len(script_tools))
        except Exception as exc:  # noqa: BLE001
            log.warning("Script tool registry unavailable: %s", exc)

        # FR-18: App agent blocks (override scripts with same name if any)
        try:
            agent_tools = hub_mcp.build_agent_tool_registry()
            registry.update(agent_tools)
            log.debug("Agent tools loaded: %d", len(agent_tools))
        except Exception as exc:  # noqa: BLE001
            log.warning("Agent tool registry unavailable: %s", exc)

        # Static tools always win — prevents Hub from shadowing hardcoded tools
        registry.update(self._static_tools)

        self._registry = registry
        self._last_refresh = now

        dynamic_count = len(registry) - len(self._static_tools)
        log.info(
            "Tool registry refreshed: %d dynamic + %d static = %d total",
            dynamic_count,
            len(self._static_tools),
            len(registry),
        )

    # ----------------------------------------------------------------- query
    def list_tools(self) -> list[dict]:
        """Return all registered tools as a list of metadata dicts."""
        self.refresh()
        return [{"name": k, **v} for k, v in self._registry.items()]

    def get(self, tool_name: str) -> dict | None:
        """Return tool metadata dict for a given name, or None if not registered."""
        self.refresh()
        return self._registry.get(tool_name)

    def has_agent_tools(self) -> bool:
        """True if at least one app has declared an agent capability block."""
        self.refresh()
        return any(v.get("type") == "agent_tool" for v in self._registry.values())

    def apps_with_agents(self) -> list[str]:
        """Return a sorted list of app IDs that have agent blocks registered."""
        self.refresh()
        seen: set[str] = set()
        result: list[str] = []
        for meta in self._registry.values():
            if meta.get("type") == "agent_tool":
                app_id = meta.get("app_id", "")
                if app_id and app_id not in seen:
                    seen.add(app_id)
                    result.append(app_id)
        return sorted(result)

    def tool_count_by_app(self) -> dict[str, int]:
        """Return {app_id: tool_count} for all apps that have agent tools."""
        self.refresh()
        counts: dict[str, int] = {}
        for meta in self._registry.values():
            if meta.get("type") == "agent_tool":
                app_id = meta.get("app_id", "")
                if app_id:
                    counts[app_id] = counts.get(app_id, 0) + 1
        return counts

    # ----------------------------------------------------------------- call
    def call(self, tool_name: str, **kwargs: Any) -> dict:
        """Execute a registered tool by name.

        Dispatch rules:
          hub_script__*  → hub_mcp.run_hub_script
          agent_tool     → hub_mcp.call_agent_tool (REST to app's API)
          static/other   → raises NotImplementedError (metadata-only stubs)
        """
        self.refresh()
        tool = self._registry.get(tool_name)
        if tool is None:
            raise KeyError(f"Tool {tool_name!r} not in registry (call refresh() first)")

        from tools import hub_mcp  # noqa: PLC0415

        tool_type = tool.get("type")
        if tool_type == "hub_script":
            return hub_mcp.run_hub_script(tool["script_id"], kwargs or None)
        elif tool.get("url"):
            return hub_mcp.call_agent_tool(tool_name, self._registry, **kwargs)
        else:
            raise NotImplementedError(
                f"Tool {tool_name!r} has no call implementation (static metadata-only stub)"
            )

    # ----------------------------------------------------------------- dunder helpers
    def __len__(self) -> int:
        return len(self._registry)

    def __contains__(self, item: str) -> bool:
        self.refresh()
        return item in self._registry

    def __repr__(self) -> str:
        return (
            f"<ToolRegistry tools={len(self._registry)} "
            f"last_refresh={self._last_refresh:.0f}>"
        )


# ----------------------------------------------------------------- module singleton
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """Return the shared module-level ToolRegistry instance (created on first call)."""
    global _registry  # noqa: PLW0603
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
