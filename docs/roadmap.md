# Roadmap & Phase Status

Implementation status against the PRD's six phases (renumbered
2026-06-12: GUI Navigation Shell inserted as Phase 3). Full spec:
`[[Agentic OS - Full PRD]]` in Brain2. Update this doc when a phase
milestone lands.

## Phase 1 — Core Orchestration ✅ COMPLETE (2026-06-11)

| Acceptance criterion | Status |
|----------------------|--------|
| LangGraph executes a 3+ step workflow | ✅ `morning-briefing` (4 steps) |
| Filesystem tool reads Brain2 and writes output | ✅ brief written to `04 - Reflections/` |
| `workflows.yaml` defines workflows — no hardcoded logic | ✅ |
| Constitution halts blocked actions | ✅ tested (blocked patterns, allowlist, budgets) |
| HITL interrupt pauses `requires_approval` nodes for CLI input | ✅ `approval-demo` |
| SQLite checkpointer enables recoverable runs | ✅ |

Known deviations: direct file ops behind an MCP-shaped seam (TR-03,
documented in [architecture.md](architecture.md)). The daily cost cap gap
was closed 2026-06-11 — see [constitution.md](constitution.md).

## Phase 2 — Tauri Desktop GUI 🟩 CORE COMPLETE (2026-06-12)

| Acceptance criterion | Status |
|----------------------|--------|
| Port registered before use (TR-10) | ✅ 5130 in `hub/docs/PORT_ASSIGNMENTS.md` |
| TR-03 deviation closed (real MCP client) | ✅ `filesystem_backend: mcp` — verified read/write/list + guards |
| FastAPI sidecar runs as GUI backend (FR-20) | ✅ `gui/sidecar/`, REST + WS on 5130 |
| AG-UI event stream (FR-21) | ✅ `/ws/agui` — verified full HITL cycle over WS |
| Tauri v2 + React desktop app (FR-20) | ✅ `gui/desktop/`, launches via `npm run tauri dev` |
| Six dashboard panels (FR-28–33) | ✅ all live; Terminal strip stubbed until Phase 4 |
| Dataview dashboard note (FR-22) | ✅ `01 - Projects/Agentic OS - Dashboard.md` |

Punch list status (2026-06-12, second pass): ✅ sidecar auto-start/stop
with the app (spawns venv python; not a frozen binary — documented
deviation), ✅ app icon, ✅ production build — `Agentic OS.app` in
`/Applications` (8.3 MB). Remaining: finer-grained `text_delta` /
`tool_call` events (needs agent instrumentation).

## Phase 3 — GUI Navigation Shell ✅ COMPLETE (2026-06-12)

| Acceptance criterion | Status |
|----------------------|--------|
| Sidebar is navigation-only (FR-36) | ✅ Workflows list + Event feed removed; nav links + conn status |
| Registry-driven nav entries (FR-37) | ✅ `VIEWS` registry in `App.jsx` — new paradigm = new nav link |
| Workflows and Events are their own views (FR-38) | ✅ `WorkflowsView` (table + run), `EventsView` (full feed, auto-scroll) |
| Dashboard default + persisted active view (FR-39) | ✅ `localStorage["agentic-os.activeView"]`, validated against registry |

Verified 2026-06-12: app launched v0.3, all three views functional.

## Phase 4 — Shell Integration ✅ COMPLETE (2026-06-14)

| Acceptance criterion | Status |
|----------------------|--------|
| iTerm2 split pane + inject (FR-08) | ✅ `tools/iterm2_tool.py` — `open_pane(commands)`, `read_pane()`, sync wrappers |
| ZSH plugin preexec/precmd/chpwd (FR-09) | ✅ `shell/agentic-os.plugin.zsh` — socat one-shot IPC, reconnect-safe, `aos-on/off/status` helpers |
| Unix socket server (FR-10) | ✅ `core/socket_server.py` — `~/.agentic-os/shell.sock` chmod 600, ring buffer, sidecar startup task |
| Directory-change Brain2 context (FR-11) | ✅ `agents/shell_agent.py` — chpwd → project map → note count + status surfaced in log |
| Policy intercept before inject (FR-12) | ✅ `iterm2_tool.open_pane` calls `constitution.guard("shell_command")` before each `async_inject` |
| Terminal strip wired to live data (FR-33) | ✅ `panels.iterm_strip` now reads socket ring buffer; logfile fallback retained |

Verified 2026-06-14: ZSH plugin installed and shell reloaded, sidecar
launched, `cd` into a Codehome project dir surfaced `cd` events and the
Brain2 context log in the Tauri terminal strip. Signed off by Tony.

## Phase 5 — Brain2 Workflow Agents ✅ COMPLETE (2026-06-14)

| Acceptance criterion | Status |
|----------------------|--------|
| `process-raw-notes` workflow (FR-13) | ✅ `workflows.yaml` + `scan_raw_notes` / `process_each_raw_note` actions; classifies by keyword heuristic, adds frontmatter, archives original |
| `research-learning-notes` workflow (FR-14) | ✅ `scan_learning_notes` / `research_each_learning_note`; finds `status: processing` notes, stubs Claude's Analysis, marks `status: researched` |
| `save-session` workflow (FR-15) | ✅ `collect_session_summary` / `write_session_report`; writes dated session report + Next Day Focus template to `04 - Reflections/` |
| Scheduling via launchd + APScheduler (FR-16) | ✅ `core/scheduler.py` — launchd plist generator/installer; APScheduler in-process fallback wired to sidecar startup |

Verified 2026-06-14: `python -m core.scheduler install` generated and
loaded the plists, `agentic-os run process-raw-notes` classified and
moved a raw note, and `agentic-os run save-session` wrote a session
report to `04 - Reflections/`. Signed off by Tony.

Open question resolved: `ANTHROPIC_API_KEY` delivered via plist `EnvironmentVariables`
key; persisted to `~/.agentic-os/env.yaml` (chmod 600) on `scheduler install`.

## Phase 6 — Codehome Deep Integration ✅ COMPLETE (2026-06-14)

| Acceptance criterion | Status |
|----------------------|--------|
| Hub MCP wrapper (list/start/stop/restart as MCP tools) (FR-17) | ✅ `tools/hub_mcp.py` — dual-mode: importable Python + stdio MCP server |
| `app.json` agent-block auto-registration (FR-18) | ✅ `get_app_manifest`, `build_agent_tool_registry` — Hub API + filesystem fallback |
| Scripts discovery as dynamic tool registry (FR-19) | ✅ `list_hub_scripts`, `build_script_tool_registry` — new scripts appear without manual registration |
| Hub panel shows agent capability manifest per app (FR-18) | ✅ `✦ N` badge in Hub table + expandable manifest row; polled via `/api/panels/hub/manifests` |
| Start/stop controls call through hub_mcp, not direct REST (TR-11) | ✅ `panels.hub_status/hub_app_action` delegate to `hub_mcp`; `hub_agent.py` re-exports from `hub_mcp` |

New endpoints: `GET /api/panels/hub/manifests`, `GET /api/panels/hub/scripts`.
New workflows: `hub-status`, `hub-scripts`, `hub-app-manifest`.

Verified 2026-06-14: `agentic-os run hub-status` returned the live app
list, an `"agent"` block added to a Codehome `app.json` surfaced in the
manifest endpoint (✦ 1 badge), and `python -m tools.hub_mcp` started the
stdio server without error. Signed off by Tony.

## Phase 7 — Expandable Panels + Menu Bar + Terminal ✅ COMPLETE (2026-06-13)

| Acceptance criterion | Status |
|----------------------|--------|
| Double-click any panel title bar to expand to full dashboard frame (FR-40) | ✅ `position: absolute; inset: 0` overlay within `position: relative` grid; 150ms CSS animation |
| Escape / double-click title collapses back to grid; only one expanded at a time (FR-40) | ✅ `Escape` keydown listener + `toggle()` callback |
| Each panel has distinct condensed and expanded data layouts (FR-42) | ✅ All six panels implement both; no new backend routes required |
| Expanded per-panel specs: System Health per-core bars, Hub manifest rows, full run history, etc. (FR-43) | ✅ `exp-grid-2` / `exp-col` CSS layout; per-core bars via `cpu_per_core` sidecar field |
| `localStorage` persists last-expanded panel across restarts (FR-44) | ✅ `localStorage["agentic-os.expandedPanel"]` read on mount, updated on toggle |
| Native Tauri app menu bar (FR-45) | ✅ `lib.rs` — File / View (⌘1–3, ⌘R) / Agent / Window submenus; menu events route to React via `window.__agenticOsSetView` |
| Terminal panel is a fully interactive PTY (FR-33 enhanced) | ✅ `terminal.py` async PTY handler; xterm.js frontend; resize frames; oh-my-posh renders correctly |
| Per-core CPU data in sidecar | ✅ `psutil.cpu_percent(percpu=True)` in `system_health()` |

---

# Planned — Phases 8–10 (priorities locked 2026-06-14)

Next batch from `docs/feature-backlog.md`. Full spec staged in
`docs/PRD-addendum-phases-8-10.md` (paste into the Brain2 Full PRD). Build order:
**Phase 8 → 9 → 10.**

## Phase 8 — Dashboard Workspace (NF-2) ✅ COMPLETE (2026-06-14)

Sidebar becomes a registry of dashboards; merge Workflows + Events into one
linked dashboard; add placeholder dashboards. Front-end-only (no new sidecar
endpoints; events already carry `run_id` + `workflow`).

| Acceptance criterion | FR | Status |
|----------------------|----|--------|
| Registry-driven dashboard list in sidebar | FR-46 | ✅ `VIEWS` registry drives nav + native menu |
| Dashboard → "SysOps" rename + persisted-view migration | FR-47 | ✅ `dashboard`/`events` → `sysops`/`workflows` shim |
| Combined Workflows dashboard (Workflows + Events panels); standalone Events removed | FR-48 | ✅ `WorkflowsDashboard` (runs from `/api/runs`) |
| Bidirectional workflow↔run↔event highlighting | FR-49 | ✅ `selWf`/`selRun` selection + highlight CSS |
| Placeholders (Web News, Scripts, Zsh Config Editor, Obsidian Viewer) → "Coming Soon" | FR-50 | ✅ shared `ComingSoon` stub |
| Native menu / shortcuts synced to registry | FR-51 | ✅ ⌘1–6 + generic `view-*` handler in `lib.rs` |

## Phase 9 — Hub Absorption & Decommission (NF-4) 🔲 PLANNED (spec provisional)

AgenticOS natively owns Codehome app management; external Hub on `:8085`
retired. **Needs a detailed drill-down before build.**

| Acceptance criterion | FR |
|----------------------|----|
| Native app registry from `~/Codehome/**/app.json` | FR-60 |
| Native start/stop/restart/status (no external Hub) | FR-61 |
| Agent blocks + scripts register natively (tool-registry contract unchanged) | FR-62 |
| Scripts dashboard live | FR-63 |
| Hub `:8085` decommissioned | FR-64 |

## Phase 10 — Governing Agent (NF-3) 🟡 IN PROGRESS (10a/10b/10c)

LangChain governing agent on a new unified LLM layer; local-default + cloud
escalation; run **and** author under Constitution enforcement. Sub-phases
**10a (LLM layer) ✅ + 10b (agent + HITL + streaming) ✅ + 10c (Agent dashboard
+ escalate toggle + authoring) ✅ code complete** — all Mac smoke tests pending
(live model run + GUI smoke).

| Acceptance criterion | FR |
|----------------------|----|
| `core/llm.py` serves Anthropic + Ollama; briefing uses it ✅ | FR-52 |
| Model registry + runtime switch (cloud + local) ✅ | FR-53 |
| Governing agent runs workflows + calls registry tools ✅ | FR-54 |
| Constitution guard + HITL approvals on agent calls ✅ | FR-55 |
| "Agent" chat dashboard with model selector + local/cloud indicator ✅ (⌘7; Mac GUI smoke pending) | FR-56 |
| Agent streaming endpoint `/ws/agent` ✅ | FR-57 |
| Small-local-model safeguards (loop guard ✅ + escalate toggle ✅) | FR-58 |
| Authoring with approval + config backup + YAML validation ✅ | FR-59 |

