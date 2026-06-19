# Continuation note

**2026-06-19 — Hub MCP Extended: 7 tools → 35 tools + Phase 2 Layout Planning**

## What was done this session

### 1. Hub API Audit Complete
Verified all 27 Hub REST endpoints against ENHANCEMENTS_PRD.md and FIXES_PRD.md.
Result: ✅ No missing endpoints. Hub API is production-ready for MCP wrapper.
Deliverable: `HUB_API_AUDIT.md` (filed in Brain2 deliverables).

### 2. GUI Wireframes: 3 Layout Alternatives
Created interactive wireframe comparison of 3 Agentic OS GUI layouts:
- **Alternative A: Sidebar-Focused** ⭐ (RECOMMENDED) — Agent status cards + tabbed content
- Alternative B: Dashboard Grid — 6-panel dashboard view
- Alternative C: Terminal-Primary — CLI-focused with large terminal
Recommendation: Use Alternative A for Phase 1; add B/C as secondary views in Phase 2+.
Deliverable: `gui-layout-alternatives.html` (interactive prototype).

### 3. SysOps Dashboard Created
Built persistent Cowork artifact showing live Agentic OS service status:
- Sidecar (:5130), Hub (:8085), app status
- launchd agent state + auto-restart status
- System health (CPU, memory, uptime)
- Usage telemetry (cost, workflows, tokens, success rate)
- Auto-refreshes every 30 seconds
Live in Cowork sidebar; ready for ongoing monitoring.

### 4. Hub MCP Extended: 7 → 35 Tools ⭐ (THIS SESSION)
Expanded `tools/hub_mcp.py` with 28 new tools covering all Hub endpoints:
- **Logs & Health:** `get_app_logs()`, `get_app_health()`
- **Analytics:** `get_app_analytics()`, `get_hub_analytics()`
- **Environment:** `get_app_env()`, `set_app_env()`, `delete_app_env()`
- **Tags & Filtering:** `list_tags()`, `filter_apps_by_tag()`
- **Favorites & Recent:** `get_favorite_apps()`, `get_recent_apps()`, `toggle_favorite()`
- **Details & Status:** `get_app_detail()`, `get_app_status()`, `get_app_scripts()`, `get_port_assignments()`
- **System:** `stop_all_apps()`, `refresh_app_discovery()`, registry builders
- **Dual-mode:** Works as Python imports (workflows) + MCP server (Tauri GUI)
- All functions in ACTIONS dict for LangGraph; all tools in MCP server
Deliverables: `hub_mcp.py` (extended), `HUB_MCP_EXTENDED.md`, `docs/hub-mcp-tools.md` (reference)

### 5. Documentation Updated
- Created `docs/hub-mcp-tools.md` — complete reference guide (35 tools, usage, error handling)
- Updated `docs/README.md` — added hub-mcp-tools link to doc map
- Updated `docs/CHANGELOG.md` — 2026-06-19 entry documenting all 28 new tools
- Updated Brain2 Agentic OS.md — progress log entry
- Updated Brain2 session continuation — documented work + Phase 2 next steps

## ▶ NEXT SESSION — START HERE

### Must do first
```bash
# 1. Confirm Hub MCP works (already dual-mode, no build needed)
cd ~/Codehome/AgenticOS
python -m tools.hub_mcp  # Should start stdio MCP server with 35 tools

# 2. Start Phase 2: Tauri GUI with Sidebar Layout
# First: Interview on display strategy (see "Phase 2 Layout Interview" below)
# Then: Build React components using sidebar-focused prototype as reference

# 3. Register Hub MCP in config/tools.yaml (when Phase 2 is ready)
# tools:
#   hub_mcp:
#     command: python
#     args: ["-m", "tools.hub_mcp"]

# 4. Commit this session's work
cd ~/Codehome/AgenticOS
git add tools/hub_mcp.py tools/HUB_MCP_EXTENDED.md docs/
git commit -m "Hub MCP extended (35 tools), docs updated, Phase 2 ready"
git push
```

### Phase 2 Layout Interview — Answer these before building GUI
1. **Sidebar Agent Cards** — Display quick stats? Favorite toggle? Recent apps below?
2. **Main Panel Tabs** — Keep current (Queue|Logs|Memory|Approvals)? Add new ones? Merge?
3. **Logs Display** — Separate "Diagnostics" tab (logs + health)? Or stay in Memory?
4. **Environment Variables** — Where to access (config tab, popup, sidebar)?
5. **Scripts & Favorites** — Dropdown on cards? Separate section? Filter bar?

### Carry-forward
- **All Phase 7 work** (expandable panels, menu bar, terminal) remains live and tested.
- **Phase 8+ feature backlog** unchanged (see roadmap.md).
- **Hub MCP is production-ready** — no further changes unless Phase 2 reveals gaps.

## Key files changed this session
- `tools/hub_mcp.py` — Extended with 28 new tools (7 → 35), MCP server updated
- `tools/HUB_MCP_EXTENDED.md` — Summary of new tools (NEW)
- `docs/hub-mcp-tools.md` — Complete reference guide (NEW)
- `docs/README.md` — Added hub-mcp-tools link
- `docs/CHANGELOG.md` — 2026-06-19 entry
- Brain2 `01 - Projects/Agentic OS.md` — Progress log updated
- Brain2 `07 - Claude Sessions/2026-06-18...Session.md` — Continuation notes

---

**2026-06-17 (4) — Process supervision + adaptive polling session.**

## What was done this session

### 1. Shutdown hang fixed (`core/socket_server.py`)
`serve()` was using `async with server: await server.serve_forever()` — on task
cancellation this called `wait_closed()`, which blocks until all active ZSH
connections close. Rewrote `serve()` to park on `asyncio.Future()` instead;
added `_active_writers` tracking + force-close in `finally`. Now cancellation
returns in milliseconds regardless of connected ZSH sessions.

### 2. Shutdown event fixed (`gui/sidecar/app.py`)
Renamed `_cleanup_pid_on_shutdown` → `_on_shutdown`. Now cancels all
background tasks (`shell_socket_task`, `hub_autostart_task`, `apscheduler`)
before cleaning the PID file. SIGTERM → clean exit → PID file gone, no hanging.

### 3. launchd process supervision (NEW)
Created `scripts/com.agentcos.sidecar.plist` and `scripts/com.agentcos.hub.plist`.
Both use `KeepAlive=true`, `RunAtLoad=true`, `ThrottleInterval=10`.
launchd now owns the sidecar and hub lifecycle: auto-start at login,
auto-restart on crash within 10 s.

### 4. `agentic-gui.sh` rewritten
New commands: `install` (one-time launchd bootstrap), `start`, `stop`
(launchctl bootout — stays down), `restart` (kickstart -k), `status`
(checks both launchd agent state AND live ports/curl). Hub added to status.
No more raw `nohup`/`pkill` for sidecar/hub — all via launchctl.

### 5. Hub auto-start bug fixed (`gui/desktop/src/App.jsx`)
`prevAvailable` pattern got stuck: after one failed start attempt `prevAvailable`
stayed `false`, so every subsequent `false→false` poll never retried.
Replaced with `lastStartAttempt` ref + 30 s cooldown: retries whenever hub is
offline and 30 s have elapsed, regardless of prior state.

### 6. Adaptive polling (`gui/desktop/src/App.jsx`)
`usePoll(path, ms)` upgraded to `usePoll(path, ms, fastMs=2000, key=0)`:
- Polls at `ms` when service is available (normal cadence).
- Drops to `fastMs` automatically when `available=false` (fast recovery detection).
- `key` param: increment to trigger an immediate extra tick (used for WebSocket
  event-driven refresh without restarting the interval).

All panels now use adaptive polling:
| Panel | Normal | Down |
|---|---|---|
| System Health | 2 s | 1 s |
| Agent Activity | 10 s | 2 s |
| Keno Telemetry | 30 s | 3 s |
| Hub | 5 s | 2 s |
| Hub Manifests | 60 s | 5 s |
| Terminal | 3 s | 2 s |
| Approvals | 15 s | 2 s |
| Workflows | 30 s | 2 s |

`AgentActivity` migrated from `refreshKey`-only to `usePoll` with `refreshKey`
as the `key` param (polling + event-driven refresh). Approvals/workflows now use
`usePoll` with `approvalKey`/`workflowsData` instead of one-shot loads.

## ▶ NEXT SESSION — START HERE

### Must do first
```bash
# 1. Install launchd agents (one-time)
~/Codehome/AgenticOS/scripts/agentic-gui.sh install

# 2. Rebuild frontend to pick up App.jsx changes
cd ~/Codehome/AgenticOS/gui/desktop && npm run build
# (or just relaunch tauri dev — it hot-reloads)

# 3. Commit this session's changes
cd ~/Codehome/AgenticOS
git add -A
git commit -m "Process supervision (launchd), clean shutdown, adaptive polling"
git push
```

### Carry-forward from previous sessions
- **Push `a07fa50`** (run_shell + native Edit menu) if not already pushed.
  `git log --oneline origin/main..HEAD` to check.
- **Phase 10c live verification** (see sections below) — the items from the
  previous continuation note still apply.
- **Phase 9 (Hub absorption, FR-60–64)** — next build target after 10c sign-off.

## Key files changed this session
- `core/socket_server.py` — shutdown fix (Future-based serve + writer tracking)
- `gui/sidecar/app.py` — `_on_shutdown` cancels tasks before PID cleanup
- `scripts/com.agentcos.sidecar.plist` — launchd sidecar supervisor (NEW)
- `scripts/com.agentcos.hub.plist` — launchd hub supervisor (NEW)
- `scripts/agentic-gui.sh` — rewritten to use launchctl
- `gui/desktop/src/App.jsx` — adaptive `usePoll`, hub auto-start fix,
  AgentActivity + approvals + workflows on polling

---
*(Prior session notes preserved below)*

**2026-06-17 (3) — LIVE-VERIFICATION SESSION. All four original open issues
CLOSED, plus several live-found fixes shipped. Three commits this session; two
pushed, one local pending push.**

- **Issues #1–#4: done.** #1 Send-guard, #2 cloud endpoint pinned
  (root cause: shell exports `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN` → Ollama),
  #3 tool-first prompt + dynamic Ollama discovery/auto-start/RAM-gating, #4 git
  history note. Probe on the Mac confirmed tools bind + emit `tool_calls` on BOTH
  qwen2.5-7B and claude-sonnet-4-6 (no capability/binding bug).
- **Live-found fixes shipped this session:**
  - **Persistent chat transcript** (`App.jsx`) — chat no longer "refreshes" each
    turn; agent turns accumulate in App state (`agentTurns` via `foldAgentEvent`),
    immune to the 200-event feed cap + survives view switches. ✅ confirmed live.
  - **Tool-manifest hardening** (`governor.py`) — injects the bound-tool roster
    into the system prompt so models never claim "no tools."
  - **Soul + Memory** (`core/soul.py`, `config/Soul.md`, `config/Memory.md`) —
    persistent agent identity ("Osa") + durable memory injected into all
    LLM-facing agents (governor + briefing); `remember` tool (automatic writes).
    Migrated Soul/Memory from YAML → Markdown.
  - **`run_shell` tool** (`governor.py` + `constitution.yaml`) — agent runs
    terminal commands inline in chat; allowlist-auto (read-only), approve-the-rest
    (HITL), blocked-patterns hard-refused, runs in `~`.
  - **Native Edit menu** (`src-tauri/src/lib.rs`) — fixes paste/copy/cut in Tauri
    text inputs (the Agent prompt box).
  - Diagnostics added: `scripts/diagnose_cloud.py`, `scripts/diagnose_tools.py`.
- **▶ NEXT SESSION — live checks (need sidecar restart + Tauri rebuild):**
  1. `run_shell`: ask Osa "what's in my home directory?" (auto-runs `ls`); a
     mutating command (e.g. "make a folder test") should prompt Allow/Deny.
  2. Edit menu: Cmd+V into the Agent prompt (needs `npm run tauri dev` rebuild).
  3. Soul/Memory: "what's your name?" → Osa; "remember that …" → appended to
     `config/Memory.md`.
  4. Push the pending local commit (see below), then `rm config/Soul.yaml
     config/Memory.yaml` leftovers if still present.
- **Phase 9 (Hub absorption) remains the last roadmap build** — not started.
