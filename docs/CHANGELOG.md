## 2026-06-14 — Phase 8 (NF-2) Dashboard Workspace ✅ COMPLETE

- **FR-46 Dashboard registry:** `VIEWS` in `gui/desktop/src/App.jsx` is now the
  single source of truth (`{id,label,component,badge?,placeholder?,purpose?}`);
  nav and the native menu derive from it.
- **FR-47 SysOps rename:** former "Dashboard" 6-panel grid → `SysOpsView`
  (id `sysops`, keeps the approvals badge). Migration shim on
  `localStorage["agentic-os.activeView"]`: `dashboard`→`sysops`,
  `events`→`workflows`, so existing installs don't open to a dead view.
- **FR-48 Combined Workflows dashboard:** new `WorkflowsDashboard` reuses the
  Phase 7 `Panel` expand/collapse — a Workflows panel (definitions, each row
  expandable to recent runs from `/api/runs`, with run button) + an Events panel
  (the AG-UI feed, each line tagged with `workflow` + short `run_id`). Standalone
  Events nav entry removed. Front-end-only — no sidecar changes.
- **FR-49 Bidirectional linking:** `selectedWorkflow`/`selectedRunId` lifted to
  the dashboard. Click workflow → highlight its events; click run → highlight
  that run's events; click event → select its run + scroll the matching workflow
  row into view; clear → unfiltered live feed. Highlight is visual only (no
  refetch; keys already in `feed`).
- **FR-50 Placeholders:** Web News, Scripts, Zsh Config Editor, Obsidian Viewer
  registered, each rendering a shared `ComingSoon` stub (title + purpose).
- **FR-51 Menu sync:** `src-tauri/src/lib.rs` View submenu lists the six
  dashboards (⌘1–6) + Reload (⌘R); handler is generic (`view-<id>` → registry id)
  so future dashboards only need a registry + menu-item pair.
- Verified: `App.jsx` passes an esbuild JSX transform; new highlight/stub styles
  added to `App.css`.

## 2026-06-14 — Next batch scoped: priorities locked, PRD staged (Phases 8–10)

- New feature intake captured in `docs/feature-backlog.md` (NF-1…NF-4).
- **NF-1** (host on GitHub) ✅ done — public repo `tseneadza/AgenticOS`.
- Priorities **locked**: NF-2 → Phase 8, NF-4 → Phase 9, NF-3 → Phase 10.
- Detailed specs written for **NF-2** (FR-46–51) and **NF-3** (FR-52–59);
  **NF-4** (FR-60–64) staged provisionally, pending a detailed drill-down.
- PRD update **staged** in `docs/PRD-addendum-phases-8-10.md` (paste into the
  Brain2 Full PRD — vault not accessible from this workspace).
- `docs/roadmap.md` extended with Planned Phases 8–10. Planning/docs only — no
  behavior change.

## 2026-06-14 — Phases 4, 5, 6 signed off ✅ COMPLETE

- **Phase 4 — Shell Integration:** verification checklist passed (ZSH plugin
  installed + shell reloaded, sidecar launched, `cd` into a Codehome project
  surfaced `cd` events and the Brain2 context log in the Tauri terminal strip).
- **Phase 5 — Brain2 Workflow Agents:** verification checklist passed
  (`core.scheduler install` loaded the launchd plists, `process-raw-notes`
  classified and moved a raw note, `save-session` wrote a report to
  `04 - Reflections/`).
- **Phase 6 — Codehome Deep Integration:** verification checklist passed
  (`hub-status` returned the live app list, an `app.json` `"agent"` block
  surfaced in the manifest endpoint, `tools.hub_mcp` stdio server started clean).
- `docs/roadmap.md` markers flipped from 🟩 IMPLEMENTED to ✅ COMPLETE (dated
  2026-06-14), signed off by Tony. No code changes — verification/sign-off only.

## 2026-06-13 — Phase 7: Expandable Panels + Native Menu Bar + Interactive Terminal

### Phase 7 — Expandable Panels (FR-40–44)

- **Panel expand/collapse (FR-40–41):** Double-click any panel title bar to expand it to the full
  dashboard content area. `Escape` or double-clicking again collapses back to the grid. Only one
  panel can be expanded at a time. A smooth 150ms CSS animation (`@keyframes panel-expand`)
  handles the transition. Implementation: `.panel.expanded` uses `position: absolute; inset: 0;
  z-index: 10` within the `.grid { position: relative }` container so the native sidebar stays
  visible. `.grid.has-expanded { overflow: hidden }` prevents scroll bleed.
- **Two-layout data contracts (FR-42):** Each panel exposes a `condensed` view (grid default) and
  an `expanded` view with richer data. No new backend endpoints — expanded views re-use the same
  polling endpoints, just render more of the response.
- **Expanded layout per panel (FR-43):**
  - *System Health* — two-column stat grid + per-core CPU bar chart (8 cores visualised). Requires
    `cpu_per_core` field added to `panels.iterm_strip()` via `psutil.cpu_percent(percpu=True)`.
    Top-10 process table (bumped from 5).
  - *Agent Activity* — full run history table with cost, duration, status columns.
  - *Keno Telemetry* — sparkline-style gap coverage + last 20 draws table.
  - *Codehome Hub* — full app table with agent-manifest inline rows + scripts list.
  - *Approval Queue* — card layout with full action description and approve/deny buttons.
  - *Terminal* — full xterm.js interactive PTY (see below).
- **localStorage persistence (FR-44):** `localStorage["agentic-os.expandedPanel"]` stores the
  last-expanded panel; app reopens in that state. `Escape` always resets.
- CSS additions: `.exp-grid-2`, `.exp-col`, `.exp-section-title`, `.core-bars`, `.core-bar-wrap`,
  `.bar.inline-bar`, and expanded-view overrides for each panel. Terminal override:
  `.panel.expanded .panel-body:has(.term-xterm) { padding: 0; overflow: hidden }`.

### Native App Menu Bar (FR-45)

- **Tauri v2 native menu** (`src-tauri/src/lib.rs`): Full macOS app menu bar with five submenus:
  - *Agentic OS* — About, Preferences (⌘,), Services, separator, Hide/Hide Others/Show All,
    separator, Quit (⌘Q).
  - *File* — New Run (⌘N), Close Window (⌘W).
  - *View* — Dashboard (⌘1), Workflows (⌘2), Events (⌘3), separator, Reload (⌘R).
  - *Agent* — Run Morning Briefing, separator, Restart Sidecar.
  - *Window* — Minimize (⌘M), Zoom, standard Window items.
- **Menu → React routing:** Menu item events call `window.eval("window.__agenticOsSetView(viewId)")`
  from Rust. React exposes `window.__agenticOsSetView` in a `useEffect` in `App.jsx` that calls
  `setView()` — no `@tauri-apps/api` npm package required.
- **Restart Sidecar:** kills the running sidecar process, waits 600ms, then re-spawns it —
  equivalent to the CLI `agentic-gui restart`.
- Uses local variable binding pattern throughout (`let quit = PredefinedMenuItem::quit(app, None)?;`
  etc.) to satisfy Rust borrow checker lifetime requirements with Tauri v2's menu API.

### Interactive Terminal — xterm.js + PTY (FR-33 enhanced)

- **`gui/sidecar/terminal.py`** (new): Async PTY WebSocket handler at `/ws/terminal`.
  - Spawns `$SHELL -l` in a pseudo-terminal using `pty.openpty()` +
    `asyncio.create_subprocess_exec` with `slave_fd` as stdin/stdout/stderr, `preexec_fn=os.setsid`
    for proper session handling.
  - `asyncio.StreamReader` + `loop.add_reader(master_fd)` for non-blocking PTY reads without
    threading.
  - Binary WebSocket frames = keystroke bytes (PTY → WS and WS → PTY). JSON text frames with
    `{"type":"resize","cols":N,"rows":N}` → `fcntl.ioctl(fd, TIOCSWINSZ, ...)` for live resize.
  - `TERM=xterm-256color`, `COLORTERM=truecolor` set in child env; oh-my-posh and full-colour
    prompts render correctly.
  - Graceful cleanup: `loop.remove_reader`, close `master_fd`, `proc.kill()`, `proc.wait()`.
- **`gui/sidecar/app.py`**: Added `@app.websocket("/ws/terminal")` route delegating to
  `terminal_handler.handle(ws)`.
- **`App.jsx` — `TerminalStrip` component (rewritten)**:
  - Condensed view: same read-only strip of last N lines from `/api/panels/terminal`.
  - Expanded view: dynamically imports `@xterm/xterm` + `@xterm/addon-fit` (code-split by Vite,
    ~329KB loaded only on first expand). Opens an xterm.js terminal, connects via
    `WebSocket("ws://localhost:5130/ws/terminal")`, maps `onData` → WS binary send. `ResizeObserver`
    calls `fitAddon.fit()` and sends a JSON resize frame on every container size change.
  - Session-end banner written to terminal on WS close.
  - Cleanup on collapse: `ResizeObserver.disconnect()`, `ws.close()`, `term.dispose()`.
- **xterm.js deps added**: `@xterm/xterm@6.0.0`, `@xterm/addon-fit@0.11.0` in `package.json`.
  `import "@xterm/xterm/css/xterm.css"` in `App.jsx`.

### Sidecar enhancements

- **`panels.py`**: `system_health()` now returns `cpu_per_core: [float, ...]` — one value per
  logical CPU via `psutil.cpu_percent(percpu=True)`. Top-processes list bumped from 5 → 10.
  `/api/panels/terminal` passes `limit` query param through to `iterm_strip(lines=limit)`.

# Changelog

All notable changes to the Agentic OS. Newest first.

## 2026-06-13 — Phase 6: Codehome Deep Integration (FR-17–19)

- **Hub MCP wrapper (FR-17):** `tools/hub_mcp.py` — dual-mode module: plain
  Python functions importable by any module, plus a stdio MCP server
  (`python -m tools.hub_mcp`) for LangGraph tool-protocol use (TR-11).
  Exposes `list_hub_apps`, `start_hub_app`, `stop_hub_app`, `restart_hub_app`,
  `hub_app_action`, and `hub_status`. Normalises both flat and nested Hub API
  response shapes transparently.
- **Agent-block auto-registration (FR-18):** `get_app_manifest(app_id)` fetches
  the `"agent"` block from a Codehome app's `app.json` — tries Hub API endpoints
  first, falls back to `~/Codehome/**/app.json` filesystem scan.
  `build_agent_tool_registry()` scans all Hub apps and returns a callable tool dict;
  new apps appear automatically without manual registration.
  `hub_manifests()` (fast path) returns embedded manifest data from the card listing.
- **Scripts discovery (FR-19):** `list_hub_scripts()` queries `GET /api/scripts`;
  `build_script_tool_registry()` wraps each script as a `hub_script__<id>` tool.
  New Hub scripts appear in the registry on next `ToolRegistry.refresh()` call.
- **`core/tool_registry.py`:** `ToolRegistry` singleton aggregates script tools
  (FR-19), agent-block tools (FR-18), and static `config/tools.yaml` entries
  (highest priority). Refreshes at most once per 60s. `call(tool_name)` dispatches
  to the right backend. Module-level `get_registry()` returns the shared instance.
- **`agents/hub_agent.py`:** Simplified to re-export everything from `hub_mcp`
  — no direct `requests` calls remain in workflow code (TR-11 fully closed).
- **`gui/sidecar/panels.py`:** `hub_status()` and `hub_app_action()` now delegate
  to `hub_mcp`. New `hub_manifests()` and `hub_scripts()` panel functions added.
  Removed orphaned `HUB_URL` variable (no longer needed at panel level).
- **`gui/sidecar/app.py`:** Two new endpoints: `GET /api/panels/hub/manifests`
  (agent capability data, slow-poll) and `GET /api/panels/hub/scripts`.
- **`gui/desktop/src/App.jsx`:** HubPanel now fetches manifests at 60s interval.
  Added "Agent" column: apps with an agent block show a `✦ N` badge (N = tool count);
  clicking expands an inline manifest row showing `api_base` and all declared tools.
- **`config/workflows.yaml`:** Added `hub-status`, `hub-scripts`, and
  `hub-app-manifest` workflows for programmatic Hub introspection.

## 2026-06-13 — Phase 5: Brain2 Workflow Agents (FR-13–16)

- **`process-raw-notes` workflow (FR-13):** Two new `brain2_agent` actions —
  `scan_raw_notes` lists `.md` files in `00 - Raw/`; `process_each_raw_note`
  classifies each note by keyword heuristic (project/task/learning/reflection/
  resource/reference), adds YAML frontmatter if missing, writes to the target
  vault folder, and archives the original in `06 - Archive/processed-raw/`.
  Scheduled 9pm daily via launchd/APScheduler.
- **`research-learning-notes` workflow (FR-14):** `scan_learning_notes` finds
  notes in `02 - Learning/` with `status: processing`; `research_each_learning_note`
  updates frontmatter to `status: researched` and appends a `## Claude's Analysis`
  stub (full LLM research runs via `briefing_agent` in a follow-on step).
  Scheduled 10pm daily.
- **`save-session` workflow (FR-15):** `collect_session_summary` reads recent
  run history and active Brain2 projects; `write_session_report` writes a dated
  session report with workflow costs and a Next Day Focus template to
  `04 - Reflections/`. Manual trigger only.
- **`core/scheduler.py` (FR-16):** launchd plist generator — reads `workflows.yaml`
  schedules, converts 5-field cron to `StartCalendarInterval`, injects
  `ANTHROPIC_API_KEY` from env or `~/.agentic-os/env.yaml` (chmod 600),
  loads plists via `launchctl`. CLI: `python -m core.scheduler install|uninstall|list`.
  APScheduler in-process fallback wired to sidecar startup for dev-mode scheduling.
- `config/workflows.yaml` — added `process-raw-notes`, `research-learning-notes`,
  `save-session` workflow definitions.

## 2026-06-13 — Phase 4: Shell Integration (FR-08–12)

- **iTerm2 Python API wrapper (FR-08, TR-08):** `tools/iterm2_tool.py` —
  `open_pane(commands)` opens a vertical split pane via `async_split_pane`
  and injects commands via `async_inject`; `read_pane()` returns last N
  lines of output. AppleScript cookie acquired once on first use, cached
  for the process lifetime. Sync wrappers (`run_in_pane`, `last_pane_lines`)
  for non-async workflow nodes.
- **ZSH plugin (FR-09, TR-09):** `shell/agentic-os.plugin.zsh` — registers
  `preexec`, `precmd`, and `chpwd` hooks. Each hook serialises a JSON event
  and sends it to the Unix socket via `socat` in one-shot mode (naturally
  reconnects on next event if the server restarts). Shell helpers: `aos-on`,
  `aos-off`, `aos-status`. Install: copy to
  `~/.oh-my-zsh/custom/plugins/agentic-os/` and add to `plugins=()`.
- **Unix socket server (FR-10, TR-09):** `core/socket_server.py` — asyncio
  server on `~/.agentic-os/shell.sock` (chmod 600). Maintains a 200-event
  ring buffer consumed by the terminal strip panel. Auto-started as a
  background task in the FastAPI sidecar (`app.py` startup event).
- **Directory-change Brain2 context (FR-11):** `agents/shell_agent.py` —
  `chpwd` events trigger a project map lookup (scans Brain2 `01 - Projects/`
  for `codehome_dir` / `dir` frontmatter). On match: logs project name,
  status, and linked-note count; emits a `context` event into the ring buffer.
- **Policy intercept (FR-12):** `open_pane` calls `constitution.guard(
  "shell_command", cmd)` for each command before `async_inject`. Blocked
  commands raise `ConstitutionViolation`; approval-gated ones raise
  `ApprovalRequired` (surfaced via the existing approval queue).
- **Terminal strip wired (FR-33):** `panels.iterm_strip` reads the socket
  ring buffer first; falls back to `~/.agentic-os/shell.log` for
  compatibility. Shows `$ cmd`, `← exit N`, `cd path`, and context events.
- `iterm2>=2.6` added to `requirements.txt`.

## 2026-06-12 — Phase 3: GUI Navigation Shell (FR-36–39)

- **Nav-only sidebar (FR-36)**: Workflows list and Event feed removed from
  the sidebar; it now holds brand, nav links, and sidecar status only.
  Approval-count badge shown on the Dashboard link.
- **View registry (FR-37)**: `VIEWS` array in `App.jsx` drives nav entries
  and routing — new paradigm = new nav link (design principle #7), never
  another always-on dashboard panel.
- **Workflows & Events views (FR-38)**: `WorkflowsView` — table with
  description, last run event, and run button; `EventsView` — full
  AG-UI feed (last 200 events) with auto-scroll.
- **Persisted active view (FR-39)**: stored in
  `localStorage["agentic-os.activeView"]`, validated against the registry;
  Dashboard remains the default. Brand bumped to v0.3.
- Dashboard's six Phase 2 panels are unchanged. Nav/view styles appended
  to `App.css`. Also: `CLAUDE.md` added (session-budget rule, conventions);
  `roadmap.md` renumbered to match the renumbered PRD (Shell→4, Brain2→5,
  Codehome→6).

## 2026-06-12 — Phase 2 punch list: production app

- **Sidecar auto-start/stop**: the Tauri app now spawns the venv sidecar on
  launch (skipped if :5130 is already serving, e.g. started by `agentic-gui`)
  and SIGKILLs it on exit. Spawns the venv python rather than a frozen
  binary — documented deviation from a bundled external binary.
- **App icon** (agent-graph motif) generated for all targets via `tauri icon`.
- **Production build**: `Agentic OS.app` (8.3 MB) + DMG via `npm run tauri
  build`; installed to `/Applications`. Verified: cold launch auto-starts
  sidecar; quit kills it, no zombies.
- `agentic-gui` hardening: uvicorn can hang in graceful shutdown when a
  WebSocket client was attached — kill_all now escalates to SIGKILL by
  process pattern, and patterns are self-exclusion-safe (`gui[.]sidecar`).
- Remaining from punch list: `text_delta` / `tool_call` event granularity
  (needs agent instrumentation).

## 2026-06-12 — `agentic-gui` launcher

- `scripts/agentic-gui.sh` (+ `agentic-gui` alias in `~/.zshrc`): one-command
  start/stop/status for the GUI. Start always kills stale processes first
  (by port 5130/1420 and by process name) so reruns never collide.
  Logs to `data/logs/{sidecar,tauri}.log`.

## 2026-06-12 — Phase 2: Tauri Desktop GUI + sidecar (initial build)

- **FastAPI sidecar** (`gui/sidecar/`, port 5130 — registered in
  `hub/docs/PORT_ASSIGNMENTS.md` per TR-10): REST endpoints for the six
  dashboard panels, workflow run/history/approval APIs, and an
  AG-UI-format WebSocket event stream at `/ws/agui` (FR-21).
- **Threaded workflow runner** with programmatic HITL: interrupts park on
  an approval queue resolved via `POST /api/approvals/{id}` instead of
  CLI `input()`; emits RUN_STARTED / STEP_FINISHED / APPROVAL_REQUIRED /
  APPROVAL_RESOLVED / RUN_FINISHED / RUN_ERROR events.
- **Tauri v2 + React desktop app** (`gui/desktop/`, FR-20) — Focused
  Sidebar layout with six panels: System Health (FR-28, psutil, 2s poll),
  Agent Activity (FR-29, run_history), Keno Telemetry (FR-30, MySQL),
  Codehome Hub with start/stop/restart (FR-31, 5s poll), Approval Queue
  (FR-32), Terminal strip (FR-33, stub until Phase 3).
- **TR-03 closed**: `tools/filesystem_tool.py` now delegates to a real MCP
  stdio client (`@modelcontextprotocol/server-filesystem` via npx, `mcp`
  Python SDK). Constitution guards remain client-side. New
  `settings.filesystem_backend` ("mcp" default, "direct" fallback).
  Residual deviation: `delete_file` stays direct (server has no delete tool).
- **FR-22**: Obsidian Dataview dashboard note added at
  `Brain2/01 - Projects/Agentic OS - Dashboard.md`.
- New deps: `mcp`, `fastapi`, `uvicorn`, `psutil`, `mysql-connector-python`.
  Rust toolchain (rustup, minimal profile) installed for Tauri builds.

## 2026-06-11 — Daily cost cap enforcement

- `limits.max_cost_per_day_usd` is now enforced (was declared-only):
  pre-spend gate in `briefing_agent` before any API call, plus a post-step
  re-check in the orchestrator. Free template-mode runs are never blocked.
- Per-model pricing table added to `config/settings.yaml` (Sonnet 4.6
  $3/$15, Haiku 4.5 $1/$5 per MTok); unknown models billed at the most
  expensive listed rates.
- `run_history` gained a `cost_usd` column (auto-migrated); new
  `memory.cost_today()`; `agentic-os history` shows per-run cost and
  today's total spend.

## 2026-06-11 — Documentation suite

- Added `docs/`: usage guide, architecture, workflows reference,
  constitution reference, state & memory, roadmap, this changelog.
- Established the documentation policy: docs update in the same change
  that alters behavior.

## 2026-06-11 — Phase 1: Core Orchestration (initial build)

- LangGraph-based orchestrator building graphs from `config/workflows.yaml`.
- Workflows: `morning-briefing` (vault scan → Hub check → brief → write to
  `04 - Reflections/`), `approval-demo` (HITL demonstration).
- Agents: `brain2_agent`, `hub_agent`, `briefing_agent` (Claude API with
  template fallback when `ANTHROPIC_API_KEY` is unset).
- Agent constitution (`config/constitution.yaml`) enforced at the tool-call
  boundary: blocked patterns, approval-gated action types, write allowlist,
  token budget, file-write cap. Daily cost cap declared, not yet enforced.
- Human-in-the-loop interrupts via LangGraph `interrupt()` for
  `requires_approval: true` steps.
- SQLite state (`data/state.db`): LangGraph checkpoints + run history;
  `agentic-os history` command.
- CLI: `run`, `list`, `history`. Exit codes: 2 = constitution halt,
  3 = approval denied.
- Verified end-to-end on 2026-06-11 against the live Brain2 vault.
