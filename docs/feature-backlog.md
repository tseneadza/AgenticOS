# Feature Backlog — intake for next PRD batch (Phase 8+)

Status: **priorities LOCKED 2026-06-14.** Build order: NF-1 (✅ done) →
NF-2 (Phase 8) → NF-4 (Phase 9) → NF-3 (Phase 10). Detailed specs done for
NF-2 and NF-3; **NF-4 still needs a detailed drill-down before build.** PRD
update staged in `docs/PRD-addendum-phases-8-10.md`; `docs/roadmap.md` updated
to match. More features can still be appended as new NF-n items.

Legend — Type: `SETUP` (one-off action) · `GUI` · `AGENT` · `CORE/INTEGRATION`.

---

## NF-1 — Host the project in a GitHub repo named `AgenticOS`
- **Type:** SETUP (action, not a PRD feature)
- **Summary:** Initialize git (if needed) and push this repo to GitHub as
  `AgenticOS`. Establishes version control / backup / remote of record.
- **Open questions:** private vs public? push now or after the nav refactor?
  confirm GitHub account/owner.
- **Notes:** I can execute this directly via the GitHub connector once visibility
  is decided. Not a phase item — it's prerequisite plumbing.

## NF-2 — Nav becomes a list of *dashboards* (restructure + new dashboards)
- **Type:** GUI/UX · **Effort:** medium · **Proposed phase:** 8
- **Summary:** Turn the left sidebar from three fixed views into a registry of
  named **dashboards**. Rename the current dashboard, merge Workflows + Events
  into one linked dashboard, and register four placeholder dashboards.

### Current state (verified in code)
- `gui/desktop/src/App.jsx` already has a registry-driven nav (FR-37):
  `const VIEWS = [{id,label,component}, …]`, rendered in `<nav>`, active view
  persisted to `localStorage["agentic-os.activeView"]`.
- Today `VIEWS = [dashboard (6-panel grid), workflows (table), events (feed)]`.
- `WorkflowsView` lists workflow **definitions** from `/api/workflows` with a
  run button; derives "last event" by matching `feed` entries on `workflow`.
- `EventsView` renders the AG-UI `feed` (flat list of `{type, workflow, step,
  ts}`), auto-scrolling.
- **Correlation keys already exist:** `runner.py` publishes every event with
  `run_id=` *and* `workflow=` (RUN_STARTED, STEP_*, TOOL_CALL_*, APPROVAL_*,
  RUN_FINISHED, RUN_ERROR). `/api/runs?limit=` returns historical runs with
  `run_id`. The WS replays the last 50 events on connect. ⇒ Linking needs **no
  backend change**; the frontend just has to keep `run_id` and use it.

### Requirements (provisional FR numbers — continue from FR-45)
- **FR-46 — Dashboard registry:** generalize `VIEWS` into the single source of
  truth for the dashboard list (each entry: `id`, `label`, `component`,
  optional `badge`, optional `placeholder` flag). Nav renders it; adding a
  dashboard = adding a registry entry (design principle #7).
- **FR-47 — Rename Dashboard → "SysOps":** relabel the system-operations grid.
  Change the registry `id` to `sysops` (cleaner) **with a migration shim** for
  the persisted `activeView` value (`dashboard` → `sysops`) so existing installs
  don't open to a dead view. Keep the approvals nav-badge on this entry (the
  Approval Queue panel lives here).
- **FR-48 — Combined "Workflows" dashboard:** a new multi-panel view (reusing
  the Phase 7 `Panel` expand/collapse system) hosting:
  - a **Workflows panel** — workflow definitions from `/api/workflows`, each
    row expandable to its recent **runs** (run_id + status + time) sourced from
    `/api/runs`, with the run button.
  - an **Events panel** — the live AG-UI feed (the old `EventsView`), each line
    tagged with its `workflow` and `run_id`.
  The standalone **Events** nav entry is removed (it becomes this panel).
- **FR-49 — Bidirectional linking:** a selection model lifted to the Workflows
  dashboard (`selectedWorkflow` + `selectedRunId`):
  - Click a **workflow** → highlight all events whose `workflow` matches; dim
    the rest.
  - Click a specific **run** → highlight only that `run_id`'s events.
  - Click an **event** → select its `run_id`, highlight/scroll the matching
    workflow + run in the Workflows panel.
  - Clear selection to return to the unfiltered live feed. Highlight = visual
    only (no data refetch; all keys are already in `feed`).
- **FR-50 — Placeholder dashboards:** register four non-functional dashboards
  that render a shared "Coming soon" stub (title + one-line intended purpose):
  **Web News**, **Scripts**, **Zsh Configuration Editor**, **Obsidian Viewer**.
  (These map to later epics — Scripts ↔ Hub takeover NF-4; the others are new.)
- **FR-51 — Native menu / shortcut sync:** the Tauri menu bar (FR-45,
  `lib.rs`) hard-codes View shortcuts ⌘1–3 and `window.__agenticOsSetView`.
  Update the View submenu + shortcuts to match the new registry (ideally drive
  the menu from the same list so future dashboards stay in sync).

### Decisions (locked 2026-06-14)
1. Sidebar label: **"SysOps"** (expanded title / tooltip may read "Overall
   System Operations").
2. Workflows panel: **definitions, expandable to runs**; linking at both
   workflow-level (click workflow → all its events) and run-level (click run →
   that run's events). ⇒ FR-48/FR-49 as written.
3. Placeholders: **registered in nav**, each renders a **"Coming Soon"** stub
   when clicked. Non-functional this phase. (All four: Web News, Scripts, Zsh
   Configuration Editor, Obsidian Viewer.)
4. Nav order: SysOps, Workflows, Web News, Scripts, Zsh Config Editor,
   Obsidian Viewer.

### Effort / risk
- Mostly front-end. No new sidecar endpoints required (reuse `/api/workflows`,
  `/api/runs`, `/ws/agui`). Main work: combined view + selection/highlight
  state, registry generalization, view-id migration, and the `lib.rs` menu sync
  (small Rust change). Low risk; isolated to the GUI layer.

## NF-3 — Governing AI agent over the whole app (LangChain + local model)
- **Type:** AGENT (large / epic)
- **Summary:** A conversational agent that can do everything the app can do via
  natural language ("an AI agent that governs the application"). Built with
  LangChain, exposing the existing workflows + tool registry as its action
  surface. Runs a **local model** (Ollama or equivalent) with the ability to
  **switch the active model at runtime**.
- **Recommendation (to confirm):** surface it as its own nav dashboard ("Agent"
  / "Console"); reuse the existing LangGraph workflow + `tool_registry` as the
  agent's tools rather than a parallel command layer; route every action through
  the Constitution guard (same policy/budget enforcement as workflows); model
  selector in the dashboard header backed by an Ollama model list.
- **Hardware (confirmed):** MacBook Air M2, 2022, **16GB** unified memory,
  macOS Tahoe 26.5.
- **Model recommendation (for 16GB):** default local workhorse is a **7–8B**
  model at 4-bit (~5–6GB), with good tool-calling — Qwen2.5/Qwen3 8B or
  Llama 3.1 8B. A 14B is a stretch goal (~9GB, only with little else running).
  32B/70B are not feasible locally. **Hybrid model selector:** expose both local
  Ollama models and cloud models (Claude via existing `ANTHROPIC_API_KEY`) in
  the runtime switcher — local for routine commands, cloud for complex
  multi-step orchestration where small local models are unreliable.
### Current state (verified in code)
- **No LLM abstraction layer exists.** The only model call is
  `agents/briefing_agent.compose_brief`, which directly does
  `anthropic.Anthropic(...).messages.create(model=…)`. Model is chosen per
  workflow step via `state["model"]` alias → `settings.yaml > models` map
  (`default: claude-sonnet-4-6`, `fast: claude-haiku-…`). Cost computed from
  `settings.yaml > pricing`.
- **Deps:** `langgraph` + `anthropic` only. **No LangChain** packages yet, no
  Ollama.
- **Governance surface the agent must drive:**
  - 8 workflows (`config/workflows.yaml`): morning-briefing, process-raw-notes,
    research-learning-notes, save-session, hub-status, hub-scripts,
    hub-app-manifest, approval-demo — run via `runner.py` / `/api/workflows`.
  - In-process agent ACTIONS: `brain2_agent` (9), `briefing_agent` (1),
    `hub_agent` (Hub control) — see `orchestrator.AGENT_REGISTRY`.
  - `core/tool_registry.py` — dynamic Hub/app/script tools (`list_tools()`,
    `call(name, **kwargs)`).
- **Constitution (`config/constitution.yaml`) is real and enforceable:**
  approval_required = {file_delete, email_send, api_call_external, git_push,
  hub_stop_all}; blocked substrings (`rm -rf`, `DROP TABLE`, …); write_allowlist
  (Brain2, Codehome, data); limits (100k tok/workflow, **$5/day**, 50 files/run).
  `guard()` raises `ConstitutionViolation` / `ApprovalRequired`. The agent
  inherits all of this for free if its tools route through `guard()`.

### Requirements (provisional FR numbers — continue after NF-2's FR-51)
- **FR-52 — Unified LLM provider layer (`core/llm.py`):** one seam over cloud
  (Anthropic) + local (Ollama) chat models via LangChain (`ChatAnthropic`,
  `ChatOllama`). Refactor `briefing_agent` to call through it so there is a
  single LLM entry point. This is the foundation everything else builds on.
- **FR-53 — Model registry + runtime switch:** registry entries
  `{id, provider, label, context_window, supports_tools, cost_per_mtok|0}`.
  `GET /api/agent/models` lists configured cloud models + locally-installed
  Ollama models (Ollama `/api/tags`). `POST /api/agent/model {id}` sets the
  active model for subsequent turns (session state). Extend `settings.yaml`
  pricing so local models are cost 0 (they don't consume the daily cap).
- **FR-54 — Governing agent (`agents/governor.py`):** a LangChain tool-calling
  agent (LangGraph `create_react_agent` or equivalent). Tools wrap the surface
  above: `list_workflows` / `run_workflow`, the agent ACTIONS, `tool_registry`
  tools, and read-only status (`/api/panels/*`, `/api/runs`). System prompt
  describes the OS + safety rules. **Reuses existing capability — not a parallel
  command layer.**
- **FR-55 — Constitution + HITL for agent calls:** every agent tool call passes
  `constitution.guard(action_type, payload)` first; `ApprovalRequired` is
  emitted as an `APPROVAL_REQUIRED` AG-UI event and pauses the turn until the
  human approves (reuse the runner/approval-queue HITL pattern). Token/cost
  budgets apply to agent turns.
- **FR-56 — Agent chat dashboard (GUI):** a new dashboard registered in NF-2's
  nav registry: chat transcript + input, streamed assistant output, a visible
  tool-call/step trace, inline approval prompts, and a **model-selector dropdown
  in the header** (FR-53).
- **FR-57 — Agent streaming endpoint:** session-scoped agent runner (sibling of
  `runner.py`) streaming tokens + tool events over WS (`/ws/agent`) using the
  existing `events.py` bus conventions.
- **FR-58 — Small-local-model safeguards:** tight, well-described toolset;
  prefer native tool-calling models (Qwen2.5 7B / Llama 3.1 8B); cap tool-call
  iterations (loop guard); per-conversation "escalate to cloud" toggle.
  (Optional later: planner=cloud / executor=local split.)
- **FR-59 — Authoring scope (decision-gated):** v1 = **run/execute existing
  capability only**. Letting the agent *author/edit* `workflows.yaml` or config
  is a later iteration, gated behind write_allowlist + an explicit
  approval-required action.

### New dependencies / infra
- Add `langchain`, `langchain-anthropic`, `langchain-ollama` to requirements.
- **Ollama** installed locally as a separate service (`ollama serve`, default
  **:11434**) — register the port in `hub/docs/PORT_ASSIGNMENTS.md` (TR-10) and
  pull a starter model (see decisions). Sidecar treats Ollama as optional: if
  it's down, only cloud models are offered.

### Suggested sub-phasing (within Phase 10)
- **10a** — FR-52/53: LLM provider layer + model registry + model endpoints;
  refactor briefing to use it. (Foundational, testable headless.)
- **10b** — FR-54/55/57: governing agent + constitution/HITL + streaming
  endpoint. Test via endpoint/CLI before any UI.
- **10c** — FR-56/58: chat dashboard, model selector, approvals, safeguards.

### Decisions (locked 2026-06-14)
1. **Default model:** **local default, escalate to cloud.** Opens on the local
   Ollama model; cloud (Claude) is one toggle away. ⇒ makes FR-58's
   reliability safeguards + the escalate-to-cloud toggle first-class, not
   optional. Surface a clear indicator when running local vs cloud.
2. **Authoring scope:** **run + author from v1.** The agent may create/modify
   `workflows.yaml` and config. ⇒ FR-59 promoted into scope. Safeguards: all
   such writes go through `guard_write_path()` (write_allowlist) **and** an
   approval-required gate; keep timestamped backups of any config the agent
   edits so changes are revertible; validate YAML before save. Higher risk on a
   local model (hallucinated configs) — recommend authoring actions default to
   requiring approval regardless of model.
3. **Local models:** pull **both Qwen2.5-7B-Instruct and Llama 3.1 8B**, compare
   tool-calling reliability before standardizing. Registry lists both.
4. **Dashboard name:** **"Agent."**
5. Text-only for v1 (voice later).

### Effort / risk
- **Large.** Touches a new core layer (LLM), a new agent, sidecar streaming, and
  GUI. Risk concentrated in (a) local tool-calling reliability on 16GB and (b)
  HITL/approval integration. Mitigated by sub-phasing 10a→10c and the
  cloud-fallback toggle. Depends on NF-2 (nav home) and is stronger after NF-4
  (Hub absorbed → agent governs Hub natively through the same registry).

## NF-4 — Absorb the Hub; decommission the external Hub service
- **Type:** CORE/INTEGRATION (large / epic)
- **Summary:** Make AgenticOS the owner of Codehome app management instead of
  wrapping the external Hub on `:8085`. Native app registry + lifecycle
  (list/start/stop/restart), `app.json` manifest ingestion, script discovery/run
  — "but better" — so the standalone Hub can be retired.
- **Current state:** `tools/hub_mcp.py` proxies the Hub REST API (FR-17–19).
  Takeover means replacing that proxy with a first-class process/registry
  manager inside the sidecar.
- **Open questions:** incremental (absorb capability-by-capability, run both in
  parallel, then cut over) vs big-bang replacement; what does the Hub do today
  that this should improve on; does anything outside AgenticOS depend on the Hub
  API contract.

---

## Synthesis & proposed sequence (provisional — more features may come)

| ID | Feature | Type | Effort | Depends on | Proposed slot |
|----|---------|------|--------|------------|---------------|
| NF-1 | GitHub repo `AgenticOS` | SETUP | trivial | — | Do now (pre-phase) |
| NF-2 | Nav → dashboards + merge Workflows/Events + placeholders | GUI | medium | Phase 3 nav shell (done) | Phase 8 |
| NF-4 | Absorb Hub, decommission `:8085` | CORE | large | tool_registry (done) | Phase 9 |
| NF-3 | Governing LangChain agent + local/hybrid model | AGENT | large | NF-2 (nav home), NF-4 (complete action surface) | Phase 10 |

**Why this order:**
- **NF-1 first** — get version control / remote backup in place before larger
  refactors land. Cheap insurance.
- **NF-2 next** — it's the foundation: the dashboard registry creates the homes
  that NF-3 (Agent dashboard) and NF-4 (Codehome/Hub dashboard) plug into.
- **NF-4 before NF-3** — the governing agent is meant to "do everything the app
  can do." If the app absorbs the Hub *first*, the agent inherits native Hub
  control through the unified tool registry automatically, instead of being
  built against the soon-to-be-removed proxy and reworked later.
- **NF-3 last** — highest uncertainty (local-model tool-calling reliability) and
  it benefits most from everything else being in place and exposed as tools.
