# Continuation note

**2026-06-19 (Continuation 2) — Phase 2 Layout Decisions + 3-Sprint Implementation Plan Approved**

## What was done this session

### 1. Phase 2 Layout Interview — All 5 Questions Answered ✅
Reviewed mockup HTML (dashboard.html) and layout alternatives (Alternative A: Sidebar-Focused) and decisively answered:
- **Sidebar agent cards:** Status indicator 🟢/🔴 + cost display + [★ Favorites ▼] dropdown for workflow launch
- **Main panel tabs:** Keep Queue|Logs|Memory|Approvals; add **Environment tab** (LLM model selector, API keys, feature flags)
- **Logs display:** Logs stay in Logs tab; add **collapsible Diagnostics sidebar panel** (CPU/RAM/Net metrics)
- **Environment variables:** Integrated into **Environment tab** (self-contained config UI, no YAML editing)
- **Scripts & Favorites:** Sidebar Favorites dropdown + dedicated **Scripts view** (workflow launcher with scheduling + cost metrics)

### 2. Comprehensive Phase 2 Implementation Plan Created ✅
**File:** `docs/PHASE_2_IMPLEMENTATION_PLAN.md` (3-sprint roadmap, 6 weeks, ~2 weeks per sprint)

**Scope:**
- Sprint 1 (Weeks 1-2): Environment tab (LLM config, flags) + Diagnostics sidebar (collapse/expand, localStorage)
- Sprint 2 (Weeks 3-4): Scripts view (workflow launcher) + Hub MCP integration (all 35 tools) + Favorites dropdown
- Sprint 3 (Weeks 5-6): Integration tests (>80% coverage) + Documentation + PR review

**Deliverables:**
- 12 new files (React components, FastAPI routes, tests)
- 6 modified files (existing components, sidecar)
- 5 new API endpoints
- Complete API reference + data flow diagrams

### 3. Layout Decisions Document Created ✅
**File:** `docs/PHASE_2_LAYOUT_DECISIONS.md` (detailed Q&A, mockups, rationale, acceptance criteria)

**For each decision:**
- Design mockup (ASCII diagram)
- Rationale (why this approach)
- Component breakdown (files to create/modify)
- Acceptance criteria (verification)

### 4. Documentation Updated ✅
- **CHANGELOG.md:** Added Phase 2 overview entry (top of file)
- **BRAIN2_SUMMARY.md:** Created summary for copying into Brain2 project note
- **README in docs/:** References to new Phase 2 documents

## ▶ NEXT SESSION — START HERE

### Session Setup
```bash
# Verify setup
cd ~/Codehome/AgenticOS
git status
cat docs/PHASE_2_LAYOUT_DECISIONS.md  # Review decisions
cat docs/PHASE_2_IMPLEMENTATION_PLAN.md  # Review plan
```

### Ready to Start Sprint 1 (Environment Tab + Diagnostics)
1. Create branch: `git checkout -b phase2-gui-sprint1`
2. Start with Environment tab (`gui/desktop/src/components/Dashboard/Tabs/Environment.jsx`)
3. Add config backend routes (`gui/sidecar/routes/api_config.py`)
4. Build Diagnostics sidebar panel (`gui/desktop/src/components/Sidebar/DiagnosticsPanel.jsx`)
5. Test localStorage persistence
6. Update CHANGELOG.md with progress
7. Commit weekly: `git add -A && git commit -m "Phase 2 Sprint 1: Environment tab + Diagnostics panel"`

### Files to Read First
1. `PHASE_2_LAYOUT_DECISIONS.md` — Design decisions + acceptance criteria
2. `PHASE_2_IMPLEMENTATION_PLAN.md` — Detailed breakdown + file manifest
3. `gui/mockups/dashboard.html` — Current design reference
4. `gui/desktop/src/App.jsx` — View registry pattern
5. `gui/sidecar/app.py` — Route mounting pattern

### Key Decision Points (Sprint 1)
- Config file location: `~/.agentic-os/config.yaml` ✅ (per PHASE_2_IMPLEMENTATION_PLAN.md)
- Config schema validation: URL format + LLM connection test ✅
- localStorage keys: `agentic-os.diagExpanded`, `agentic-os.favorites` ✅
- Diagnostics polling: `usePoll(2s)` for real-time updates ✅
- HITL approval: For API key changes only (PUT /api/config with sensitive data) ✅

### Carry-forward
- **Main branch:** Hub MCP (35 tools) locked in, production-ready ✅
- **Phase 2+ decisions:** Layout complete, ready to build ✅
- **Phase 7 work:** Launchd, adaptive polling, terminal all live ✅
- **Phase 8 work:** Dashboard workspace complete ✅
- **Phase 9 work:** Hub Absorption (depends on Phase 2 Hub panel) — queued ✅
- **Phase 10 work:** Governing Agent + Authoring (depends on Phase 2 Scripts view) — queued ✅

---

**2026-06-19 (Continuation) — Phase 2 Branch Created + Session Continuity Skill Built**

## What was done this session

### 1. Committed Hub MCP Work to Main
- ✅ Pushed Hub MCP extension commit to main branch (`git commit -m "Hub MCP Extended: 35 tools + comprehensive documentation"`)
- Commit includes: `tools/hub_mcp.py` (28 new tools), `docs/hub-mcp-tools.md`, documentation updates
- Main branch now has stable, production-ready Hub MCP (35 tools, dual-mode)

### 2. Created phase2-gui-sidebar Branch
- ✅ `git checkout -b phase2-gui-sidebar` — safe branch for GUI experimentation
- Phase 2 work isolated from main; can reset/redo without affecting Hub MCP
- Ready for Tauri React sidebar-focused layout implementation

### 3. Set Up Case-by-Case Git Authorization
- Discussed computer-use MCP for on-demand git operations
- Pattern: User asks → I call `request_access` for Terminal → User approves → I execute git commands
- More secure than blanket credentials; less friction than manual Terminal switching
- Ready for next push/branch operations

### 4. Built session-continuity Skill
- ✅ Created skill for automatic session start/end management
- **At session start:** Reads CONTINUATION.md, shows last session's work, asks "Tony, are you ready to continue work on the Osa app?"
- **At session end:** Summarizes accomplishments, updates CONTINUATION.md with dated entry, prompts for git commit
- Maintains single source of truth; seamless session → session handoff
- Skill saved to outputs folder, ready to move to skills directory

### 5. Phase 2 Roadmap Clarified
- Phase 2 = Tauri GUI build using sidebar-focused layout (Alternative A)
- Hub MCP tools available for display in sidebar panels
- Next decision: layout interview questions on displaying logs/health/analytics/env/scripts

## ▶ NEXT SESSION — START HERE

### Session Continuity is Now Active
```bash
# When starting Osa work in the next session:
# I will automatically read CONTINUATION.md and ask:
# "Tony, are you ready to continue work on the Osa app?"

# At session end, I will update CONTINUATION.md with:
# - What was accomplished
# - Files changed
# - Pending tasks
# - Next session action items
```

### For Phase 2 GUI Build
1. **Option A: Conduct layout interview first** (30 min)
   - Decide where logs, health, analytics, env vars, scripts should live in sidebar
   - Design tabbed layout for main panel
   - Then start React component build

2. **Option B: Start building immediately** (using Alternative A prototype as reference)
   - `gui/desktop/src/components/Panels/` for new sidebar panels
   - Connect to Hub MCP tools via sidecar API
   - Test with npm run tauri dev

### Files to Reference
- `Brain2/01 - Projects/Agentic OS.md` — Full project context
- `Codehome/AgenticOS/docs/hub-mcp-tools.md` — Available Hub MCP tools
- `Codehome/AgenticOS/gui/desktop/` — Tauri React project structure
- `Brain2/01 - Projects/Deliverables/gui-layout-alternatives.html` — Sidebar prototype

## Key files changed this session
- None in AgenticOS repo (all work was in previous session)
- Session-continuity skill created (in outputs folder)
- CONTINUATION.md updated with this entry

## Carry-forward
- **Main branch:** Hub MCP locked in, fully documented, production-ready ✅
- **phase2-gui-sidebar branch:** Ready for Phase 2 GUI work
- **Phase 7 work:** All features remain live (launchd, adaptive polling, terminal)
- **Phase 8+ backlog:** Unchanged (see roadmap.md)
- **Session management:** Automated via session-continuity skill

---

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

---

**2026-06-19 (01:16:51) — phase2-gui-sprint2 Branch Created**

## Branch Info
- **Branch:** phase2-gui-sprint2
- **Created:** 2026-06-19 01:16:51
- **Base:** main (63d7ed2)
- **Phase:** 2

## Session Setup ✅
- [x] Branch created and checked out
- [x] Documentation updated
- [x] Environment ready
- [ ] Tests verified (run: npm test && pytest)
- [ ] Ready to start work

## Ready-to-Start Checklist
Before starting work on this branch:

```bash
# 1. Verify branch
git branch -v
git log --oneline -1

# 2. Pull latest from main (optional)
git pull origin main

# 3. Run tests
npm run lint
npm test
pytest

# 4. Read documentation
cat docs/CONTINUATION.md
```

## Next Steps
1. Review previous CONTINUATION.md entries for context
2. Check PHASE_2_LAYOUT_DECISIONS.md for design decisions
3. Read PHASE_2_IMPLEMENTATION_PLAN.md for task breakdown
4. Start with first pending task from task tracking system

## Key Documentation
- `docs/PHASE_2_LAYOUT_DECISIONS.md` — Design decisions
- `docs/PHASE_2_IMPLEMENTATION_PLAN.md` — Implementation breakdown
- `docs/CHANGELOG.md` — Project history
- `docs/roadmap.md` — Phase status

---


---

**2026-06-19 (01:17:44) — phase2-gui-sprint2 Branch Created**

## Branch Info
- **Branch:** phase2-gui-sprint2
- **Created:** 2026-06-19 01:17:44
- **Base:** phase2-gui-sprint2 (f4b562f)
- **Phase:** 2

## Session Setup ✅
- [x] Branch created and checked out
- [x] Documentation updated
- [x] Environment ready
- [ ] Tests verified (run: npm test && pytest)
- [ ] Ready to start work

## Ready-to-Start Checklist
Before starting work on this branch:

```bash
# 1. Verify branch
git branch -v
git log --oneline -1

# 2. Pull latest from main (optional)
git pull origin main

# 3. Run tests
npm run lint
npm test
pytest

# 4. Read documentation
cat docs/CONTINUATION.md
```

## Next Steps
1. Review previous CONTINUATION.md entries for context
2. Check PHASE_2_LAYOUT_DECISIONS.md for design decisions
3. Read PHASE_2_IMPLEMENTATION_PLAN.md for task breakdown
4. Start with first pending task from task tracking system

## Key Documentation
- `docs/PHASE_2_LAYOUT_DECISIONS.md` — Design decisions
- `docs/PHASE_2_IMPLEMENTATION_PLAN.md` — Implementation breakdown
- `docs/CHANGELOG.md` — Project history
- `docs/roadmap.md` — Phase status

---


---

**2026-06-19 — Hub API Explorer Shipped + Scripts View Decision**

## What was done this session

### 1. Hub API Explorer built and wired into the GUI ✅
New nav panel (`hub-api` slot) built as a self-contained React component.

**Component:** `gui/desktop/src/components/HubApiExplorer.jsx`  
**Wired into:** `gui/desktop/src/App.jsx` — import + VIEWS entry between "Obsidian Viewer" and "Agent"

Features:
- All 30 Hub endpoints listed and grouped (Cards, Logs & Env, Scripts, Analytics, Discovery, Jupyter, System)
- Explorer tab: click endpoint → param inputs + ▶ Run button + live curl preview
- Call Log tab: running history of all requests (method, path, status, latency, timestamp)
- Hub health dot polling `GET /health` every 5s (green/yellow/red)
- Fully theme-consistent using existing CSS variables

### 2. Scripts View Design Decision ✅
Agreed: the **Scripts view** (currently a placeholder in VIEWS) will use the **same pattern as Hub API Explorer** — a browseable, runnable list panel with a detail/run pane on the right.

Specifically:
- Left panel: list of all Hub-registered scripts, grouped (by card or category)
- Right panel: script detail — description, params/args input, ▶ Run button, output stream
- Backend: already available via `GET /api/scripts`, `GET /api/cards/{id}/scripts`, `POST /api/scripts/run`
- The Scripts placeholder in VIEWS (`id: "scripts"`) is ready to be replaced with a real component

**Session note filed:** `Brain2/01 - Projects/Agentic OS/Deliverables/HUB_API_EXPLORER_SESSION.md`

## ▶ NEXT SESSION — START HERE

### Immediate next task: Scripts View
Replace the `scripts` placeholder in VIEWS with a real `ScriptsExplorer` component modelled on `HubApiExplorer.jsx`.

```bash
# Files to create/modify:
# 1. NEW: gui/desktop/src/components/ScriptsExplorer.jsx
#    - Fetch /api/scripts and /api/cards/{id}/scripts on mount
#    - Left panel: grouped script list (by card)
#    - Right panel: script detail + args input + Run + output stream
#    - POST to /api/scripts/run to execute

# 2. MODIFY: gui/desktop/src/App.jsx
#    - Import ScriptsExplorer
#    - Replace placeholder { id:"scripts", placeholder:true } with { id:"scripts", component: ScriptsExplorer }

# Key difference from HubApiExplorer:
# - Endpoints are static (defined in the file)
# - Scripts are DYNAMIC (fetched live from the Hub at runtime)
# - Output should stream if possible (SSE or poll)
```

### Also planned (in order)
1. **ScriptsExplorer** — as above (next build)
2. **Auto-gen script** — `hub/scripts/gen_api_explorer.py` to generate the ENDPOINTS array in HubApiExplorer.jsx from `hub/cmd/server/main.go` route registrations
3. **Tool Call Visualizer** — live feed of Hub API calls made during workflow runs, shown as a timeline under the active LangGraph node

### Adding new Hub API endpoints
All Hub endpoints live in the `ENDPOINTS` array at the top of `HubApiExplorer.jsx`.
One object per route — no other file changes needed:
```js
{ group:"Cards", method:"POST", path:"/cards/{id}/clone", desc:"Clone a card", params:[
  { name:"id",   _in:"path", type:"string", required:true },
  { name:"body", _in:"body", type:"json",   required:false, hint:'{"name":"my-clone"}' },
]},
```
New group name = new collapsible section, automatically.

## Key files changed this session
- `gui/desktop/src/components/HubApiExplorer.jsx` — NEW
- `gui/desktop/src/App.jsx` — import + VIEWS entry added
- `Brain2/01 - Projects/Agentic OS/Deliverables/HUB_API_EXPLORER_SESSION.md` — NEW session note
- `docs/CONTINUATION.md` — this entry
