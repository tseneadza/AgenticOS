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

## Phase 9 — Hub Absorption & Decommission (NF-4) ✅ COMPLETE (2026-06-26)

| Acceptance criterion | FR | Status |
|----------------------|----|--------|
| Native app registry from `~/Codehome/**/app.json` | FR-60 | ✅ `core/app_registry.py` + `GET /api/apps` |
| Native start/stop/restart/status (no external Hub) | FR-61 | ✅ `core/process_manager.py` + lifecycle routes |
| Agent blocks + scripts register natively (tool-registry contract unchanged) | FR-62 | ✅ `hub_mcp.py` internals swapped to native registry |
| Scripts dashboard live | FR-63 | ✅ `ScriptsExplorer.jsx` repointed to sidecar |
| Hub `:8085` decommissioned | FR-64 | ✅ `hub_autostart: false`; PORT_ASSIGNMENTS retired; cutover 9/9 |

**Phase 9 complete — 2026-06-26.** Hub Go server retired. AgenticOS owns all
Codehome app management natively. `hub_mcp.py` MCP surface preserved unchanged.

## Phase 10 — Governing Agent (NF-3) ✅ COMPLETE (2026-07-01)

LangChain governing agent on unified LLM layer; local-default + cloud escalation;
run **and** author under Constitution enforcement. All three sub-phases complete:
**10a (LLM layer) ✅ + 10b (agent + HITL + streaming) ✅ + 10c (Agent dashboard
+ escalate toggle + authoring) ✅.** Smoke test verified 2026-07-01: Agent dashboard
live, model registry discovered 22 models (3 Anthropic + 19 Ollama), streaming
endpoint operational, Constitution guards integrated.

| Acceptance criterion | FR | Status |
|----------------------|----|--------|
| `core/llm.py` serves Anthropic + Ollama via LangChain | FR-52 | ✅ |
| Model registry (22 models) + runtime switch (GET/POST endpoints) | FR-53 | ✅ |
| Governing agent (LangGraph) runs workflows + calls registry tools | FR-54 | ✅ |
| Constitution guard + HITL approvals on agent calls | FR-55 | ✅ |
| Agent chat dashboard (AgentView) with model selector + local/cloud indicator ⌘7 | FR-56 | ✅ |
| Agent streaming endpoint `/ws/agent` (WebSocket + events) | FR-57 | ✅ |
| Small-local-model safeguards (10-call loop guard + escalate-to-cloud toggle) | FR-58 | ✅ |
| Authoring workflows with approval + timestamped backup + YAML validation | FR-59 | ✅ |

## Phase 11 — Project Creation Scaffolding (NF-5) ✅ COMPLETE (2026-07-01)

Interactive drawer (from SysOps ▸ Codehome Hub) to scaffold new Codehome
projects end-to-end: create folder, venv, starter files, allocate port, create
GitHub repo, git init. Shipped as 11a–11d; backend green at 48 pytest tests,
`vite build` clean.

| Acceptance criterion | Feature | Status |
|----------------------|---------|--------|
| Project creation form in SysOps drawer panel | UI | ✅ `ProjectCreationDrawer.jsx` |
| 10 templates (FastAPI, Django, React, Next.js, Svelte, Astro, Node, Full-Stack, CLI, Monorepo) | Templates | ✅ `template_registry.py` |
| Auto-scan Codehome for subfolder structure (ledger-based) | Discovery | ✅ `scan_codehome_structure` |
| Create folder structure + Python venv (template-aware) | Scaffolding | ✅ `project_manager.py` |
| Auto-detect next free port (no collisions via DB) | Port allocation | ✅ `allocate_port` + `ports` table |
| Generate starter files per template (README, .gitignore, pyproject, app.json) | Files | ✅ `generate_files` |
| Create GitHub repo via API (lenient: warn if token missing) | GitHub integration | ✅ `github_integration.py` |
| git init + initial commit (best-effort; degrade gracefully) | Git init | ✅ `init_git_repo` |
| Register project in `projects` table + auto-discover into `apps` | Registration | ✅ `create_project_full` |
| Stream progress updates via WebSocket (real-time feedback to user) | Streaming | ✅ `WS /api/projects/ws/create` |

**Shipped (2026-07-01):** 11a foundation modules, 11b GitHub/git, 11c REST +
WebSocket orchestration (`create_project_full`), 11d GUI drawer. See
`docs/CONTINUATION.md` for the detailed per-sub-phase record.

**Remaining:** on-device visual check of the drawer (`npm run tauri dev`).

## Phase 12 — Self-Diagnostics Dashboard (hidden) ✅ COMPLETE (2026-07-01)

A hidden self-diagnostics overlay: one place to answer "is AgenticOS healthy
right now?" — live system self-checks plus on-demand execution of the real test
suites. Revealed by a secret gesture (triple-tap the bottom-right corner), not
present in the nav or menu. Also reachable via the `#diag` URL-hash escape hatch.

| Acceptance criterion | Feature | Status |
|----------------------|---------|--------|
| Live system self-checks (sidecar, MySQL, model registry, port ledger, constitution guards, workflows) | Self-checks | ✅ `run_system_checks` |
| Backend pytest + frontend vitest run on demand, streamed | Test runners | ✅ `WS /api/diagnostics/ws/run` |
| Cached-on-open + live-refresh | Cache | ✅ `GET /cached` + `~/.agentic-os/diagnostics_cache.json` |
| Hidden reveal (triple-tap corner; `#diag` fallback), not in nav | Hidden UI | ✅ `CornerReveal` + `SelfDiagnosticsView.jsx` |
| Endpoints registered in the API Explorer (api-registry rule) | Registry | ✅ Diagnostics (Sidecar) group |

**Backend:** `gui/sidecar/routes/api_diagnostics.py` (`GET /system`,
`GET /cached`, `WS /ws/run`), 12 pytest tests. **Frontend:**
`SelfDiagnosticsView.jsx` (overlay) + `CornerReveal` in `App.jsx`, 5 vitest tests.

**Also this session:** fixed the pre-existing frontend test-suite breakage —
188 failing tests were test rot (inline-style assertions on components
refactored to CSS classes) plus three real product bugs the suite had been
quietly flagging, all now fixed: `EnvironmentPanel.jsx` undefined
`setHasUnsavedChanges` (reset-handler crash), `HubApiExplorer.jsx`
case-sensitive filter, and `LogsExplorer.jsx` broken search highlighting
(collapsed-to-string + control-byte `split`; rewritten to `highlightParts` with
a real regression test). Suite now 25 files / 574 tests green; backend 76.

**Remaining:** on-device visual check of the reveal gesture (`npm run tauri dev`).


## Phase 13 — Data-Driven App Launch System ✅ CLOSED 2026-07-03 (13a ✅ 2026-07-02, 13b–13f ✅ 2026-07-03)

Replace fragile start.sh launches with database-driven launch configuration.
Design: `docs/PHASE13_DATA_DRIVEN_LAUNCH_SYSTEM.md` (see its "Locked
Decisions" amendments). Architecture: the data layer (`launch_config.py`)
feeds the ONE execution engine (`core/process_manager.py`) — no parallel
launch system.

| Sub-phase | Scope | Status |
|-----------|-------|--------|
| 13a | Schema (4 new tables + 2 columns), migrations, config layer, MySQL-backed tests | ✅ 2026-07-02 (109 pytest green) |
| 13b | Backfill: ports from registry/ledger; start.sh parsed for commands only; collisions logged | ✅ 2026-07-03 (`gui/sidecar/scripts/backfill_launch_config.py`, dry-run default + `--apply`; 19 tests) |
| 13c | Extend process_manager for multi-step launches; evolve `/api/apps/*` routes; startup reconcile sweep; API Explorer registration | ✅ 2026-07-03 (process-group kill, app_processes persistence, `GET /api/apps/processes`; 12 tests, suite 141 green) |
| 13d | ProjectsView.jsx — card grid, Start/Stop, status polling (new nav link, principle #7) | ✅ 2026-07-03 (Projects nav + ⌘8; `GET /api/apps/{id}/launch-plan`; 7 vitest + 4 pytest; suites 581/145 green) |
| 13e | Integration testing (fake-app fixture: launch → port wait → health → stop) | ✅ 2026-07-03 (e2e + hard-kill + collision tests; PLUS active health polling: sidecar 10s poller, `GET /api/apps/health`, GUI health chip, probe-verified seeder — 5 endpoints seeded; suites 155/584 green) |
| 13f | SQLAlchemy consolidation: migrate news_db/tasks_db off raw mysql.connector; convert legacy SQLite-bound tests to the MySQL fixture | ✅ 2026-07-03 (full ORM models NewsCategory/NewsFeed/Task; news_db + tasks_db rewritten on the ORM with identical public API; db.py `CREATE DATABASE`/ping via server-level SQLAlchemy engine — `mysql.connector` fully retired; 11a/11c converted to the `agenticos_test` fixtures; suite 155 green) |

**✅ Already done (2026-06-24, commit `2e4ae4a`):** the LangGraph checkpointer
runs on MySQL — `core/memory.py` uses `langgraph-checkpoint-mysql`'s `PyMySQLSaver`,
the `checkpoint*` tables live in the `agenticos` schema, and `data/state.db` is
retired (only a stale `data/state.db.bak` remains). This was the last SQLite
holdout, so no checkpointer phase remains.


## Phase 14 — OSA (voice-driven ambient assistant) 🟩 CORE SHIPPED (14a–14f + presence, 2026-07-07 → 07-11)

JARVIS-analog assistant over the existing machinery. Design:
`docs/PHASE14_OSA_ASSISTANT.md`. Shipped across July 7–11 sessions: text MVP +
tools + destructive confirms (14a/14b), reactor orb + right rail (14c), voice
OUT + IN with wake word and conversation mode (14d), proactive monitoring +
briefing + HUD presence (14e), orb state words/alert/system drivers (14f),
WebSocket streaming chat with mid-run interrupt confirms, brain switching v2,
and the presence/greeting polish. Detail lives in `docs/CHANGELOG.md` — this
section added retroactively 2026-07-11 (the phase outgrew its roadmap entry).


## Phase 15 — OSA System MCP (local machine management) ✅ COMPLETE 2026-07-14

Dual-mode MCP giving OSA — and Claude Desktop/Code over stdio — governed
access to this Mac. Design: `docs/PHASE15_OSA_SYSTEM_MCP.md` (locked
2026-07-10). One guard, both doors: the Constitution guard is applied at the
capability layer by the registration decorator.

| Sub-phase | Scope | Status |
|-----------|-------|--------|
| 15a | Spine: `_harness.py` registry+guard, `_policy.py` strict ladder, `macos_mcp.py` (get_time / system_info / run_command both surfaces), `osa_system_mcp.py` stdio server, constitution `system_mcp` block, OSA wiring, tests | ✅ 2026-07-11 (33 tests; suite 570 green; stdio end-to-end verified; MCP self-approval hole closed) |
| 15b | Filesystem: `fs_mcp.py`, `allowed_roots`/`scratch_root`, read auto / write+delete gated | ✅ 2026-07-11 (32 tests; suite 602 green; harness kwargs-payload hole found+closed — dispatch keyword calls now hit the same guard) |
| 15c | iMessage: `messages_mcp.py` — chat.db reads (needs FDA) + AppleScript send spike | ✅ COMPLETE 2026-07-12 — READ (22 tests) + SEND (29 tests: `send_message` gated/irreversible, handles-only, iMessage→SMS fallback, argv injection defense; `resolve_contact` read/auto). Spike validated live; suite 659; security review PASS. OSA wired — 23 tools |
| 15d | Mail: `mail_mcp.py` — transport decision (AppleScript vs IMAP), read/send gated | ✅ 2026-07-13 — AppleScript transport (Tony); 6 capabilities (4 reads auto, send_mail+reply gated); reply recipient re-check (approval can't redirect); body fetch best-effort behind timeout (spike: blocks when not local); 36 tests; suite 707 green; OSA 29 tools. Live-verified: send + threaded reply delivered once each, mismatch refused live; cold-launch double-send found+fixed (pgrep warm check + 6s send settle) |
| 15e | Harden: effect-mode migration, classifier, permissions runbook | ✅ 2026-07-14 — flipped `system_mcp.mode: strict → effect` LIVE; fail-closed `run_command` effect classifier (`_policy.classify_command`, no model call) auto-runs provably read-only commands, gates everything else (ladder: denylist→allowlist→classifier→approve); strict unchanged. FDA-optional items wired + degrade cleanly: chat.db post-send delivery check, Mail `.emlx` disk body fallback (config-anchored `mail.emlx_root`). `docs/TCC_PERMISSIONS_RUNBOOK.md` (Brain2-mirrored). Broad-except audit: GraphBubbleUp re-raise intact, no interrupt-path swallowers. Suite 797 green. Flagged: allowlist prefix-chaining gap (`ls && rm x`) predates 15e — owner's call to tighten |


## Phase 16 — Brain Scanner (Obsidian vault viewer) 🟧 IN PROGRESS (16a–16c built 2026-07-15)

Turns the dead FR-50 "Obsidian Viewer" placeholder into a working in-app
viewer/editor for the Brain2 vault (`~/Brain2`), **renamed "Brain Scanner."**
Three panes: a folder/file **tree** (left), a rotating 3D node-**orb** of the
vault that freezes + highlights the selected note (center, the "idiot lights"
ambience), and a **reader/editor** with new-note creation (right). Design:
`docs/PHASE16_BRAIN_SCANNER.md` (locked 2026-07-15; Fable 5 review
approve-with-changes, fixes folded in). Locked calls: **Canvas-2D orb, no new
dep** (Graphify dropped — it's a code→graph pipeline, wrong direction); **real
`[[wikilink]]`+`#tag` edges** (tags as nodes); **direct vault save** scoped hard
to `~/Brain2` (mandatory `.bak` + mtime-409, no delete, no overwrite-on-create);
built via subagents.

| Sub-phase | Scope | Status |
|-----------|-------|--------|
| 16a | Backend vault API `api_vault.py`: tree / note read / graph parse (wikilink+tag, code-block & frontmatter aware), config `vault_root` (test-injectable), in-memory cache w/ mtime+count invalidation; register app.py + HubApiExplorer; pytest | ✅ 2026-07-15 (24 pytest; test-author findings fixed: hex-tag filter, symlink scope in tree/graph, hidden-note 503 gate) |
| 16b | Frontend `BrainScannerView` + `VaultTree` + `NoteReader` read mode; rename placeholder → Brain Scanner (VIEWS + `VIEW_KEY` migration + lib.rs menu/⌘, Rust rebuild); vitest | ✅ 2026-07-15 (verified live against the real vault via Vite dev; ⚠️ lib.rs menu label needs a Rust rebuild to appear; no Hud.jsx exists — nav derives from VIEWS) |
| 16c | `BrainOrb` Canvas-2D rotating node cloud, Obsidian-graph behavior (revised w/ Tony 2026-07-16): full collection w/ always-visible wikilink edges, uniform hash-shuffled sphere, notes-only (no hollow tag dots); selection swaps in a LOCAL-graph orb (selected doc centered + linked docs orbiting w/ labels, click-to-recenter, empty-click deselect); theme tokens via `getComputedStyle`; on-device visual pass in DoD; vitest tripwire | 🟧 built + revised + verified in browser — **on-device Tauri visual pass by Tony still pending (DoD)** |
| 16d | Edit + create: PUT/POST scoped writes (`.bak`, mtime-409, `.md`-only) + reader edit/new flow; `security-verifier` REQUIRED; pytest + vitest | 🟨 planned |
| 16e | Polish: wikilink click-to-open, legend/folder-filter, hover tooltip, empty/error states, theme pass | 🟨 planned |
| 16f | **Semantic connections (vector DB)** — drill into a note-cluster and surface semantic-similarity edges to related docs, layered onto the orb/graph beyond explicit `[[wikilinks]]`+`#tags`. Proper FastAPI router (NOT Flask), deliberate `chromadb`-or-alt dependency decision, embeddings/backfill design, orb UI. `security-verifier` on any new write/index path; pytest + vitest | 🅿 PARKED — idea only (Tony 2026-07-21). ⚠️ An unattended-run `api_chroma.py` (Flask, unwired, crash-looped the sidecar) was backed out + deleted 2026-07-21; build this from scratch, do NOT resurrect that file |
