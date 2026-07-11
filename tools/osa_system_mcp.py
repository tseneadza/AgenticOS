"""OSA System MCP — stdio server aggregator (Phase 15a, design §3.4).

ONE stdio MCP server exposing every capability in the system registry to
Claude Desktop / Claude Code. Run with:

    cd ~/Codehome/AgenticOS && .venv/bin/python -m tools.osa_system_mcp

Claude Desktop (``mcpServers`` config) / Claude Code (``claude mcp add``):
    command: /Users/tonyseneadza/Codehome/AgenticOS/.venv/bin/python
    args:    ["-m", "tools.osa_system_mcp"]
    cwd:     /Users/tonyseneadza/Codehome/AgenticOS

Dispatch is registry-driven (no if/elif chain — see ``_harness.REGISTRY``);
``list_tools`` is generated from the registered schemas, so a new
``@capability`` appears here automatically.

Approval semantics over MCP (15a decision): external clients get NO
``approved`` escape hatch — a capability the policy gates comes back as a
structured ``needs_approval`` error naming the Constitution as the reason.
Routing external approvals through the sidecar HITL queue is a 15b/15e
question (design §10).

NOTE on the SDK pattern: ``hub_mcp.py``'s ``_serve_mcp`` passes the Server to
``stdio_server(...)`` — that is NOT this SDK's signature (it takes optional
stdin/stdout and yields (read, write) streams for ``server.run``). That code
path was never exercised. This module uses the correct pattern; found
2026-07-11 during the 15a build.
"""
from __future__ import annotations

import json

from core.constitution import ApprovalRequired, ConstitutionViolation

# Importing domain modules self-registers their capabilities (15b–15d domains
# join this import list as they land).
from tools.system import macos_mcp  # noqa: F401
from tools.system import fs_mcp  # noqa: F401  (Phase 15b — filesystem domain)
from tools.system._harness import REGISTRY

SERVER_NAME = "osa-system-mcp"


def build_tool_list() -> list[dict]:
    """MCP tool definitions generated from the capability registry.

    Returned as plain dicts (name/description/inputSchema) so tests can
    assert registry↔list_tools parity without the mcp SDK; ``_serve_mcp``
    wraps them in ``mcp.types.Tool``.
    """
    return [
        {
            "name": cap.name,
            "description": f"[{cap.effect}] {cap.description}",
            "inputSchema": cap.schema,
        }
        for cap in sorted(REGISTRY.values(), key=lambda c: c.name)
    ]


def dispatch(name: str, arguments: dict | None = None) -> dict:
    """Run one capability by name; never raises — errors become dicts.

    ApprovalRequired → ``{"error", "needs_approval": True}`` (the external
    client cannot self-approve); ConstitutionViolation → ``{"error",
    "blocked": True}``. Anything else is the capability's own return value.
    """
    arguments = dict(arguments or {})
    # SECURITY: never let an external client self-approve — the guarded
    # wrapper accepts ``approved=`` for in-process HITL callers only.
    arguments.pop("approved", None)
    cap = REGISTRY.get(name)
    if cap is None:
        return {"error": f"Unknown tool: {name}", "known": sorted(REGISTRY)}
    try:
        result = cap.func(**arguments)
        return result if isinstance(result, dict) else {"result": result}
    except ApprovalRequired as ar:
        return {
            "error": f"'{name}' requires human approval and cannot run over MCP: {ar.description}",
            "needs_approval": True,
        }
    except ConstitutionViolation as cv:
        return {"error": str(cv), "blocked": True}
    except TypeError as te:  # bad/missing arguments from the client
        return {"error": f"Bad arguments for '{name}': {te}"}
    except Exception as exc:  # noqa: BLE001 — a tool error must not kill the server
        return {"error": str(exc)}


# ============================================================ stdio server
def _serve_mcp() -> None:  # pragma: no cover — needs a live MCP client
    """Start the stdio MCP server (correct SDK pattern — see module note)."""
    import asyncio

    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    server = Server(SERVER_NAME)

    @server.list_tools()
    async def _list_tools():  # noqa: ANN202
        return [Tool(**t) for t in build_tool_list()]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict):  # noqa: ANN202
        result = dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    async def _main() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )

    asyncio.run(_main())


if __name__ == "__main__":
    _serve_mcp()
