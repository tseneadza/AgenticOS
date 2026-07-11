"""OSA System MCP capability package — Phase 15 (design: PHASE15_OSA_SYSTEM_MCP.md).

Domains plug capabilities into ``_harness.py``'s guarded registry:
  * ``macos_mcp``    — time, system info, terminal execution (15a)
  * ``fs_mcp``       — filesystem read/write/move/delete (15b)
  * ``messages_mcp`` — iMessage read/send (15c)
  * ``mail_mcp``     — mail read/send (15d)

Importing a domain module self-registers its capabilities. OSA imports the
guarded functions directly; ``tools/osa_system_mcp.py`` serves the same
registry over stdio MCP for Claude Desktop / Claude Code.
"""
