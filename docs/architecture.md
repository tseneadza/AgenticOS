# Architecture

How the Agentic OS is put together and why. Spec context:
`[[Agentic OS - Full PRD]]` and `[[Agentic OS - Research + Architecture]]`
in Brain2.

## Context and goals

Phase 1 proves the core loop: a config-driven workflow engine that executes
multi-step agent tasks against real tools (Brain2 vault, Codehome Hub,
Claude API), with hard safety constraints enforced at runtime and human
approval gates for consequential actions. Everything runs locally; the only
network calls are localhost (Hub) and the Claude API.

## High-level design

```
                       ┌──────────────────────────────┐
  agentic-os run X ──▶ │ main.py (CLI)                │
                       └──────────────┬───────────────┘
                                      │
                       ┌──────────────▼───────────────┐
                       │ core/orchestrator.py         │
                       │  workflows.yaml ─▶ LangGraph │
                       │  graph (one node per step)   │
                       └───┬──────────┬───────────────┘
              checkpoints  │          │ per-node
              + run log    │          │ execution
                ┌──────────▼───┐  ┌───▼──────────────────────────┐
                │ core/memory  │  │ agents/                      │
                │ SQLite       │  │  brain2 │ hub │ briefing     │
                │ (state.db)   │  └───┬─────────┬────────┬───────┘
                └──────────────┘      │         │        │
                                ┌─────▼───┐ ┌───▼────┐ ┌─▼─────────┐
                                │ tools/  │ │ Hub    │ │ Claude    │
                                │ fs_tool │ │ :8085  │ │ API       │
                                └────┬────┘ └────────┘ └───────────┘
                                     │  every write passes through
                              ┌──────▼──────────────┐
                              │ core/constitution   │ ◀── constitution.yaml
                              │ guard() boundary    │
                              └──────┬──────────────┘
                                     ▼
                              Brain2 vault (allowlisted roots only)
```

## Components

**`main.py`** — argparse CLI. Three commands (`run`, `list`, `history`).
Maps constitution violations to exit code 2 and user denials to exit code 3.

**`core/orchestrator.py`** — the heart. Loads `config/workflows.yaml`,
builds a linear `StateGraph` with one node per step, compiles it with a
SQLite checkpointer, and runs it. Steps marked `requires_approval: true`
call LangGraph's `interrupt()`; the CLI loop catches `__interrupt__` in
the result, prompts the user, and resumes with `Command(resume=...)`.
`AGENT_REGISTRY` maps agent names in YAML to each agent module's
`ACTIONS` dict — adding an action means adding a function to that dict,
nothing more.

**`core/constitution.py`** — runtime enforcement of `config/constitution.yaml`
(see [constitution.md](constitution.md)). Not advisory: raises exceptions
that halt the run.

**`core/memory.py`** — SQLite access (see
[state-and-memory.md](state-and-memory.md)). Run history table + the
connection used by LangGraph's `SqliteSaver` checkpointer.

**`agents/*`** — plain Python functions with signature
`action(state: dict) -> dict`. They receive prior step outputs under
`state["outputs"][<step_id>]` and return a dict that becomes their own
step's output. No classes, no framework coupling.

**`tools/filesystem_tool.py`** — the only path to disk writes. As of
Phase 2 (TR-03 closed) it delegates to a real MCP stdio client speaking to
`@modelcontextprotocol/server-filesystem` (spawned via npx with roots from
`settings.vault_path` + the constitution write_allowlist). Constitution
guards stay client-side in this module — the MCP server is transport, not
the safety boundary. `settings.filesystem_backend: "direct"` restores the
Phase 1 direct ops for npx-hostile environments (launchd). Residual
deviation: `delete_file` remains direct (the server exposes no delete tool).

**`gui/sidecar/`** — FastAPI app on port 5130 (TR-10): panel data
endpoints (`/api/panels/*`), workflow run/history/approval APIs, and the
AG-UI WebSocket stream (`/ws/agui`). `runner.py` executes workflows in
worker threads and parks `requires_approval` interrupts on an approval
queue resolved over HTTP — the GUI equivalent of the CLI's input() loop.

**`gui/desktop/`** — Tauri v2 + React app (Focused Sidebar layout) with
the six dashboard panels (FR-28–33, FR-40–45). Includes: native macOS app menu
bar (`src-tauri/src/lib.rs`; File / View / Agent / Window submenus; menu events
bridge to React via `window.__agenticOsSetView`); expandable panel system
(double-click title bar → full-frame overlay; Phase 7 FR-40–44); fully
interactive terminal panel (xterm.js + PTY WebSocket at `/ws/terminal`;
FR-33 enhanced). Dev: `npm run tauri dev` (sidecar must be running:
`./.venv/bin/python -m gui.sidecar`).

## Workflow state

Graph state is a `TypedDict` with two reduced channels:

- `outputs: dict` — merged across nodes (`{step_id: result}`), so every
  step can read every prior step's output.
- `tokens_used: int` — summed across nodes; checked against the
  constitution's per-workflow token budget after each step.

## Key decisions and trade-offs

| Decision | Why | Trade-off |
|----------|-----|-----------|
| LangGraph as engine | Native interrupt/resume (HITL), SQLite checkpointing, no framework lock-in beyond graph wiring | Dependency on a fast-moving library; pin versions |
| Linear graphs only (Phase 1) | Every current workflow is sequential; simpler to reason about | Parallel branches (e.g. research subagents) deferred to Phase 4 |
| Direct file ops, MCP-shaped seam | Avoids npx/PATH fragility under launchd during MVP; known deviation from PRD TR-03 | Must swap in real MCP client in Phase 2 (`tools/filesystem_tool.py` only) |
| Template fallback for briefs | Pipeline testable end-to-end with zero token spend | Two code paths in briefing agent to maintain |
| Single SQLite file for all state | No infrastructure; portable; matches TR-05 | Concurrent runs would contend; fine for a single-user CLI |
| Constitution as data (YAML) | New constraint = config edit, no code change (TR-06/07) | Substring matching for blocked ops is blunt; revisit if false positives appear |

## Integration points

- **Brain2 vault** (`/Users/tonyseneadza/Brain2`) — read freely, write only
  through the guarded tool into allowlisted roots.
- **Codehome Hub** (`localhost:8085/api/cards`) — read-only in Phase 1.
  Start/stop controls arrive with the Hub MCP wrapper (Phase 5).
- **Claude API** — only from `agents/briefing_agent.py`; model aliases
  resolved from `config/settings.yaml`.

## What changes in upcoming phases

Phases 1–7 are complete as of 2026-06-13. The desktop GUI now includes a
native macOS menu bar, expandable dashboard panels, and a fully interactive
PTY terminal. See [roadmap.md](roadmap.md) for phase-by-phase status.

Phase 8 targets (tentative): Settings panel (FR-35), HTMX browser
dashboard fallback (FR-34), finer-grained `text_delta` / `tool_call`
AG-UI event granularity (needs agent instrumentation).
