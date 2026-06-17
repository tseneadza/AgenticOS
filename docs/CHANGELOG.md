## 2026-06-17 — Soul + Memory: persistent agent identity & memory across sessions/models

- **Idea.** Keep the agent's identity ("Osa") and durable memory intact across
  sessions AND across whichever model is active (local/cloud), via two
  human-editable Markdown files.
- **Files.** `config/Soul.md` (identity: name, who it serves, personality, voice,
  memory policy — migrated from the old `Soul.yaml`) and `config/Memory.md`
  (durable facts, append-only Log). The old `.yaml` versions are superseded; the
  loader prefers `.md` and falls back to `.yaml`, so they're harmless until
  deleted (the sandbox mount can't unlink them — `rm config/Soul.yaml
  config/Memory.yaml` on the Mac).
- **Loader (`core/soul.py`, new).** `load_soul()` / `load_memory()` /
  `identity_preamble()` compose a Soul+Memory block; `remember(note)` appends a
  timestamped line to `Memory.md` (append-only, bounded to that file, scaffolds
  the header on first write). Loaded fresh each turn ⇒ model-agnostic, survives
  restarts.
- **Injection (all LLM-facing agents).** `governor.build_agent` prepends the
  preamble to the system prompt (order: identity → governor system → tool
  roster), and `briefing_agent.compose_brief` prepends it to its system. The
  other agents (brain2/shell/hub) are deterministic and don't prompt a model.
- **Memory writes = automatic (per decision).** New `remember` tool on the
  governor toolbox (10 tools now) writes memory WITHOUT an approval gate — the
  agent persists facts on its own; bounded to `Memory.md`.
- Verified (sandbox): `.md`-preferred resolution, preamble merge, `remember`
  append + fresh-file scaffold + empty-note rejection + `.yaml` fallback, and the
  real `Soul.md`/`Memory.md` rendering into the composed governor prompt in the
  right order. `py_compile` clean. Live GUI check Mac-pending (restart sidecar).

## 2026-06-17 — Phase 10 Agent: "no tools available" — probe + prompt hardening (live-verification finding)

- Reported on a **local** model: the agent said it had no tools. Wiring is
  actually correct (`build_agent` → `create_react_agent(model, tools,
  prompt=...)`, which binds tools; `prompt=` is right for the installed
  langgraph 1.2.4). Prime suspect: a small local model answering in prose / not
  emitting tool calls.
- **Diagnose (`scripts/diagnose_tools.py`, new).** Binds the real governor tools
  to a given model (active by default; takes a model id arg) and prints the
  decisive signal — whether the BOUND model emits `tool_calls` for "list my
  workflows" / "system status", whether `bind_tools` attaches, whether Ollama's
  `/api/show` advertises a `tools` capability for that model, and a full
  `create_react_agent` turn. Interpretation guide included (local-empty +
  cloud-emits ⇒ capability gap; empty everywhere / TypeError ⇒ binding/version).
- **Harden (`agents/governor.py`).** `build_agent` now injects an explicit tool
  manifest (name + one-line description of every bound tool) into the system
  prompt via `_prompt_with_tool_manifest`, telling the model it DOES have tools
  and to never claim otherwise. Helps regardless of the probe outcome; verified
  formatting in isolation.
- **Result (probe run on the Mac 2026-06-17):** tools work end-to-end on BOTH
  models. qwen2.5-7B — Ollama advertises `['completion','tools']`, `bind_tools`
  attaches, and the bound model emits the correct `tool_calls`
  (`list_workflows`/`get_status`); the full `create_react_agent` turn invoked
  `list_workflows` and answered correctly. claude-sonnet-4-6 — identical (also
  reconfirms the issue-#2 cloud fix). So there is **no capability gap and no
  binding bug**; the GUI "no tools" was the pre-hardening prose behavior / a
  stale sidecar. Fix = the injected tool manifest + restarting the sidecar to
  load it. The optional local-tool fallback / auto-escalate are **not needed**.

## 2026-06-17 — Phase 10 Agent fix: persistent chat transcript (live-verification finding)

- **Bug.** The Agent chat "refreshed" after each Q&A round — earlier turns
  vanished. Root cause: `AgentView` re-derived the whole transcript every render
  from the global AG-UI `feed`, which is capped at the last 200 events
  (`slice(-200)`) and shared with workflow events. Replies stream **one
  `TEXT_MESSAGE_CONTENT` event per token**, so a single answer overran the window
  and evicted the `RUN_STARTED` markers that anchor each turn — `buildTranscript`
  could no longer reconstruct them, so prior turns (and sometimes the current one)
  disappeared.
- **Fix (`gui/desktop/src/App.jsx`).** Replaced the per-render `buildTranscript`
  with an incremental `foldAgentEvent(acc, evt)` that accumulates turns into
  **persistent App-level state** (`agentTurns`, fed as events arrive in the shared
  `connectAgui` handler, keyed by the unique `agt-<uuid>` run_id). `AgentView`
  now reads `ctx.agentTurns` instead of folding the sliced feed. The log is no
  longer subject to the 200-event cap and now also survives switching away from
  and back to the Agent view. The global `feed` (Workflows/SysOps) is unchanged.
- Verified: a 300-token reply across two turns retains **both** turns (user text,
  tool chips, status, tokens) and ignores non-`agt-` workflow events;
  `@babel/parser` parse clean. Backend already assigns a unique run_id per turn
  and includes `message`/`model` in `RUN_STARTED`, so user bubbles + model badge
  populate.

## 2026-06-17 — Phase 10: fix cloud "Connection error" — pin the Anthropic endpoint (Open issue #2)

- **Root cause (diagnosed, not guessed).** `scripts/diagnose_cloud.py` showed the
  shell exports `ANTHROPIC_BASE_URL=http://localhost:12434` and
  `ANTHROPIC_AUTH_TOKEN=ollama` (to route *other* tools through local Ollama).
  `ChatAnthropic()` was built with no explicit `base_url`/`api_key`, so the
  anthropic SDK read those ambient vars and sent "cloud" requests to
  **localhost:12434** — returning `404 model 'claude-sonnet-4-6' not found` when
  Ollama was up, and the original `APIConnectionError` when it wasn't. Direct
  curl + httpx to the real API returned 200, isolating it to SDK env inheritance.
- **Fix (`core/llm.py`).** The cloud path is now self-contained: `get_chat_model`
  pins `base_url` (new `anthropic_base_url()`, configurable via
  `settings.agent.anthropic_base_url`, default `https://api.anthropic.com`) and
  passes `ANTHROPIC_API_KEY` explicitly, and constructs the client inside
  `_isolated_anthropic_env()` — a context manager that strips
  `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN` for the duration of the build and
  restores them immediately after, so Claude Code / the user's shell are
  unaffected. Local (Ollama) routing is unchanged.
- **`config/settings.yaml`.** New `agent.anthropic_base_url` (documented; only
  change to intentionally front Anthropic with a gateway).
- **`scripts/diagnose_cloud.py`.** Added repo-root to `sys.path` (section 6 now
  runs) and an explicit warning when `ANTHROPIC_BASE_URL` is set.
- Verified (sandbox, fake `langchain_anthropic`): client pinned to the official
  URL with the key passed; ambient `ANTHROPIC_*` stripped during construction and
  restored after. `py_compile` clean. Live cloud reply in the GUI is Mac-pending.

## 2026-06-17 — Phase 10: dynamic Ollama discovery + auto-start + RAM gating; governor tool-first prompt (Open issue #3)

- **Auto-start Ollama (`core/llm.ensure_ollama_running`).** `GET /api/agent/models`
  now brings the service up before listing: if `/api/tags` doesn't answer, the
  sidecar spawns `ollama serve` (detached, new session) and waits up to 8s. The
  child inherits `OLLAMA_HOST` (and we derive `host:port` from `ollama_base_url()`
  when it's unset), so it binds the user's custom port (:12434). Binary located
  via PATH + Homebrew/`/usr/local`/Ollama.app fallbacks. Pass `?start=false` for
  a cheap read-only poll.
- **Dynamic model discovery (`discover_ollama`).** The dropdown now reflects
  *every* pulled model from `/api/tags`, not just the four configured in
  settings.yaml. Curated models keep their labels/metadata; others are added
  with sensible defaults (local ⇒ cost 0). 5s TTL cache. `get_model_info` /
  `set_active_model` resolve discovered ids too (force a re-discover on miss), so
  a just-pulled model is selectable and runnable; `cost_usd` correctly returns 0
  for discovered locals (no cloud-price fallback).
- **RAM comfort gating.** Each local model carries `size_bytes` / `ram_required_bytes`
  / `fits`; a model is `available` only if it needs **< half** of total RAM
  (`total_ram_bytes()` via psutil → `sysctl hw.memsize` → `/proc/meminfo`).
  Oversized models show disabled with a `too_large` reason + size. When Ollama is
  offline, locals report `ollama_off` (authoritative liveness check, so a stale
  discovery cache never looks runnable).
- **Frontend (`App.jsx`/`App.css`).** Dropdown options gain size suffixes and
  reason-aware labels (`(Ollama offline)` / `(not installed)` / `(too large · N GB)`
  / `(no API key)`); the issue-#1 hint and auto-fallback reuse the same
  `available` flag, so they now also respect RAM fit and liveness.
- **Issue #3 — governor tool-first prompt (`agents/governor.GOVERNOR_SYSTEM`).**
  Added an explicit "use tools, do not guess" section with a request→tool map, to
  stop small local models (qwen2.5-7B) answering in prose instead of calling
  `list_workflows`/`get_status`/etc. Escalate-to-cloud remains the fallback.
- Verified (sandbox, stubbed `/api/tags` + RAM): RAM gate at 16/8 GB, discovered-
  model select + zero local cost, Ollama-down → `ollama_off`, `OLLAMA_HOST=:12434`
  resolution. `py_compile` + `@babel/parser` clean. Live GUI + real `ollama serve`
  spawn are Mac-pending.

## 2026-06-17 — Phase 10 Agent UX fix: guard Send against unavailable models (Open issue #1)

- `AgentView` (`gui/desktop/src/App.jsx`) no longer lets a message be sent while
  the active model is unavailable. The default model can be a local model that
  isn't installed (or a cloud model with no API key); previously the dropdown
  `<option>` was disabled but the active model still defaulted to it and **Send
  stayed enabled**, so a click went to a dead model.
  - Derived `activeAvailable` from `activeInfo.available`; Send button, the
    `send()` handler, and the textarea are all gated on it (textarea also dims
    while unavailable).
  - Auto-fallback: when the active model is unavailable, fall back **once** to
    the first available *local* model. We never silently jump to a cloud model
    (would incur cost) — instead the user escalates explicitly.
  - Surfaced a `.agent-hint` line explaining *why* it's blocked and what to do
    ("…isn't installed — pull it with Ollama" / "No API key… set ANTHROPIC_API_KEY").
  - Verified: `@babel/parser` parse of `App.jsx` clean. Live GUI check Mac-pending.

## 2026-06-14 — NF-3 fix: honor OLLAMA_HOST in the LLM layer

- `core/llm.ollama_base_url()` now reads the standard `OLLAMA_HOST` env var
  first (normalizing bare-port / host:port / URL forms, mapping 0.0.0.0→
  127.0.0.1), falling back to `settings.yaml > agent.ollama_base_url` then the
  :11434 default. Fixes the sidecar looking at :11434 while the user's Ollama
  (and pulled models) run on a custom port — local models showed "not
  installed" and chat 404'd. Found during the 10c Mac smoke test.

## 2026-06-14 — Phase 10 (NF-3) sub-phase 10c — Agent dashboard + authoring 🟡 IN PROGRESS

> **Git-history note (Open issue #4):** the 10c code actually landed inside commit
> `0270602`, whose message reads "10a+10b" — the log understates it. History is
> left unrewritten; this note is the source of truth: **commit `0270602` = 10a +
> 10b + 10c.**

Put a GUI on the 10a/10b governing agent and added self-authoring tools. Code
complete + sandbox-verified; live model run is Mac-pending (needs LangChain +
Ollama/cloud).

- **FR-56 Agent dashboard (`gui/desktop/src/App.jsx`):** new `AgentView`
  registered as the seventh entry in the Phase 8 `VIEWS` registry — a **nav link,
  not an always-on panel** (GUI principle #7). It renders a chat transcript +
  input, a streamed assistant reply, a per-step tool-call trace
  (`TOOL_CALL_START`/`END` chips with running/done/error state), inline approval
  prompts (Allow/Deny → `POST /api/approvals/{id}` via `ctx.decide`), and a
  model-selector dropdown (`GET /api/agent/models` + `POST /api/agent/model`)
  with a clear local/cloud badge. The transcript is reconstructed from the shared
  AG-UI feed by filtering `run_id`s that start with `agt-`; messages are sent via
  `POST /api/agent/chat`, whose output streams back over that same feed (no
  second socket). Native View-menu entry **⌘7** added in `src-tauri/src/lib.rs`
  via the existing generic `view-<id>` pattern; styles in `App.css`.
- **FR-58 Escalate to cloud:** a per-conversation toggle in the agent bar that
  switches the active model between the first available local and cloud model
  mid-session (same model endpoints). The ReAct loop guard
  (`MAX_TOOL_ITERATIONS`) already lives in `agent_runner.py`.
- **FR-59 Authoring (`agents/governor.py`):** two new guarded tools —
  `write_config(filename, content)` (writes a YAML file into the OS config dir)
  and `edit_workflow(name, definition_json)` (adds/replaces one workflow in
  `config/workflows.yaml`, preserving the rest). Both go through
  `_authoring_write`: (1) `constitution.guard_write_path()` allowlist check →
  `BLOCKED`; (2) blocked-substring guard; (3) **always require human approval,
  regardless of the active model or the `approval_required` config**; (4) YAML is
  validated *before* approval is requested; (5) a timestamped `.bak` backup of any
  existing file is written before saving. Registered in `build_tools` (now 9
  tools) and described in `GOVERNOR_SYSTEM`.
- **Verified (sandbox):** `py_compile` clean on the changed `.py`; esbuild JSX
  transform of `App.jsx` bundles clean; 23 unit checks pass for the authoring
  tools (new-write/backup/overwrite, invalid-YAML rejection without approval,
  denial blocks write, bad extension, outside-allowlist `BLOCKED`,
  `edit_workflow` preserve + backup + bad-input paths, `build_tools` exposes both
  new tools = 9 total). **Mac-pending:** live agent turn driving the dashboard
  (stream + tool trace + approval round-trip), and an authoring round-trip
  (`write_config`/`edit_workflow` approval → backup → save) end-to-end.

## 2026-06-14 — Phase 10 (NF-3) sub-phase 10b — governing agent (headless) 🟡 IN PROGRESS

Built the governing agent + HITL + streaming endpoint on top of 10a. Headless
(no GUI yet — that's 10c). Live agent run is Mac-pending (needs LangChain +
a model).

- **FR-54 Governing agent (`agents/governor.py`):** `GovernorToolbox` exposes
  seven guarded tools wrapping existing capability — `list_workflows`,
  `run_workflow` (via the threaded runner, so it keeps its own step approvals),
  `list_tools`/`call_tool` (dynamic `tool_registry`), `list_agent_actions`,
  `get_status`, `get_runs`. `build_agent()` lazily builds a LangGraph
  `create_react_agent` over `llm.get_chat_model()` + these tools with the
  `GOVERNOR_SYSTEM` prompt. The toolbox is a plain object (no LangChain at
  import) so it's fully unit-testable.
- **FR-55 Constitution + HITL:** all side-effectful tool calls route through
  `GovernorToolbox._guarded` → `constitution.guard(action_type, payload)`.
  `ConstitutionViolation` → `BLOCKED:`; `ApprovalRequired` → bridged to a human
  via an injected `approval_fn`, then re-guarded `approved=True`. `call_tool` is
  classed as `api_call_external` (approval-required). Per-turn token + cloud-cost
  budgets enforced after the turn (local = 0).
- **FR-57 Agent runner + streaming (`gui/sidecar/agent_runner.py`):**
  session-scoped `AgentRunner` runs each turn on a worker thread and streams
  `RUN_STARTED` / `TEXT_MESSAGE_CONTENT` / `TOOL_CALL_START`/`END` /
  `APPROVAL_REQUIRED` / `RUN_FINISHED`/`RUN_ERROR` over the `events.py` bus.
  Token streaming via `stream_mode="messages"` with an `invoke()` fallback.
  **HITL is unified with workflows:** agent approvals are parked in the shared
  `runner.approvals` queue and resolved by the existing `POST /api/approvals/{id}`.
- **FR-57 endpoints (`gui/sidecar/app.py`):** `POST /api/agent/chat` (headless
  trigger → `turn_id`) and `WS /ws/agent` (inbound `{message, model?,
  session_id?}` starts a turn; outbound the AG-UI event stream with history
  replay).
- **Verified (sandbox, langgraph installed; no model call):** toolbox
  guard/deny/block/approve + event hooks, invalid-args + unknown-workflow paths,
  `build_tools` → 7 named/described StructuredTools, `agent_runner` imports
  clean, `py_compile` clean on all changed files. **Mac-pending:** live turn via
  a local model (tool call + approval round-trip over `/ws/agent`); confirm
  agent approvals appear in `/api/approvals`. Next: **10c** (Agent dashboard).

## 2026-06-14 — Phase 10 (NF-3) sub-phase 10a — unified LLM layer 🟡 IN PROGRESS

Started NF-3 with sub-phase **10a** (foundational, depends only on NF-2 which is
done — NOT on NF-4). Headless LLM provider layer + model registry; no GUI yet.

- **FR-52 Unified LLM provider layer (`core/llm.py`):** one seam over cloud
  (Anthropic) + local (Ollama) via LangChain (`ChatAnthropic`/`ChatOllama`,
  lazy-imported so the module loads without the packages). Model registry
  (`ModelInfo`), alias→id `resolve()` (`default`/`fast`/`local`), active-model
  session state (`active_model`/`set_active_model`), `is_available()`
  (cloud=API key, local=Ollama tag), `cost_usd()` (local priced 0; unknown
  cloud → most-expensive rate, conservative), and `complete()` returning text +
  token + cost accounting via `usage_metadata`.
- **FR-52 briefing refactor:** `agents/briefing_agent.compose_brief` now routes
  through `core/llm.py` — single LLM entry point. Template fallback now triggers
  on `llm.is_available(model)` (covers both no-API-key cloud and Ollama-down
  local), not just a bare API-key check. Removed the agent's local `_cost_usd`
  (moved to `llm.cost_usd`).
- **FR-53 Model registry + runtime switch:** `config/settings.yaml > agent`
  (default_model = local `qwen2.5:7b-instruct`, `ollama_base_url`, model
  registry of 2 cloud + 2 local with `cost_per_mtok`). Added local pricing
  entries (0) + a `local` alias. New endpoints in `gui/sidecar/app.py`:
  `GET /api/agent/models` (cloud + installed Ollama, `active`/`installed`/
  `available` flags) and `POST /api/agent/model {id}` (sets active model).
- **Deps:** `langchain-core`, `langchain-anthropic`, `langchain-ollama` added to
  `requirements.txt` (not yet `pip install`-ed on the Mac venv).
- **Verified (sandbox, no LangChain needed — lazy):** registry/resolve/cost/
  active-model/`list_models`/`is_available` + briefing template fallback all
  pass; `py_compile` clean on all three files.
- **Pending on the Mac:** `pip install -r requirements.txt`; `ollama serve` +
  pull `qwen2.5:7b-instruct` & `llama3.1:8b`; register **:11434** in
  `~/Codehome/hub/docs/PORT_ASSIGNMENTS.md` (TR-10); ruff; live briefing via a
  local model + `/api/agent/models` smoke test. Next: **10b** (FR-54/55/57).

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
