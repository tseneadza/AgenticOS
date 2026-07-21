# PRD Addendum — Phases 8–10 (staged 2026-06-14)

> **✅ ACCOMPLISHED (audited 2026-07-21):** Phases 8, 9, 10 all shipped
> (2026-06-14 → 2026-07-01). Historical record. See `docs/IDEA_LEDGER.md`.

> **Status: STAGED for paste-in.** The canonical Full PRD lives at
> `Brain2/01 - Projects/PRDs/Agentic OS - Full PRD.md`, which is not accessible
> from this workspace. Paste these phase sections into that PRD and keep
> `docs/roadmap.md` in sync (it has been updated to match).
>
> Phases 1–7 are complete. This addendum defines the next batch from
> `docs/feature-backlog.md`. **FR numbers are stable identifiers, not a strict
> sequence** — Phase 9's FRs (FR-60–64) are numbered after Phase 10's
> (FR-52–59) only because NF-3 was specced before NF-4. Renumber on paste-in if
> you prefer phase-ordered FRs.

## Locked priority & build order

| Order | Phase | Feature | Type | Effort |
|-------|-------|---------|------|--------|
| 0 | — (done) | NF-1 Host on GitHub (`tseneadza/AgenticOS`, public) | Setup | ✅ complete |
| 1 | **Phase 8** | NF-2 Dashboard workspace (nav → dashboards) | GUI | Medium |
| 2 | **Phase 9** | NF-4 Hub absorption / decommission | Core | Large |
| 3 | **Phase 10** | NF-3 Governing agent (LangChain + local/hybrid) | Agent | Large |

**Rationale:** Phase 8 first — it generalizes the nav registry and creates the
dashboard "homes" the later epics plug into (Agent dashboard, live Scripts
dashboard), and it's low-risk/front-end-only. Phase 9 before Phase 10 — once the
app natively owns Hub capability, the Phase 10 agent governs it through the
unified tool registry for free instead of being built against the
soon-to-be-removed proxy. Phase 10 last — highest uncertainty (local-model
tool-calling on 16GB) and it benefits from everything else already being exposed
as tools.

> Flip Phase 9/10 only if the agent is wanted before the Hub takeover; the
> dependency cost is reworking the agent's Hub tools after absorption.

---

## Phase 8 — Dashboard Workspace (NF-2)

**Goal:** Turn the sidebar from three fixed views into a registry of named
**dashboards**; rename the system view, merge Workflows + Events into one linked
dashboard, and register four placeholder dashboards. Front-end-only — no new
sidecar endpoints (reuses `/api/workflows`, `/api/runs`, `/ws/agui`). Events
already carry `run_id` + `workflow`, so linking is pure highlight logic.

**Requirements**

- **FR-46 — Dashboard registry.** Generalize the `VIEWS` array into the single
  source of truth for the dashboard list. Entry: `{id, label, component,
  badge?, placeholder?}`. Nav renders it; adding a dashboard = adding an entry
  (design principle #7: new paradigm = new nav link).
- **FR-47 — Rename Dashboard → "SysOps".** Relabel the system-operations grid;
  change registry `id` to `sysops` with a migration shim for the persisted
  `localStorage["agentic-os.activeView"]` value (`dashboard` → `sysops`). Keep
  the approvals nav-badge on this entry.
- **FR-48 — Combined "Workflows" dashboard.** A multi-panel view (reuses the
  Phase 7 expand/collapse `Panel`) hosting a **Workflows panel** (definitions
  from `/api/workflows`, each row expandable to its recent **runs** from
  `/api/runs`, with run button) and an **Events panel** (the AG-UI feed, each
  line tagged with `workflow` + `run_id`). The standalone Events nav entry is
  removed.
- **FR-49 — Bidirectional linking.** Shared selection (`selectedWorkflow` +
  `selectedRunId`): click a workflow → highlight all its events; click a run →
  highlight only that run's events; click an event → select its run and
  highlight the matching workflow/run; clear → unfiltered live feed. Visual
  only, no refetch.
- **FR-50 — Placeholder dashboards.** Register **Web News, Scripts, Zsh
  Configuration Editor, Obsidian Viewer**; each renders a shared **"Coming
  Soon"** stub when clicked. Non-functional this phase.
- **FR-51 — Native menu / shortcut sync.** Update the Tauri menu bar (`lib.rs`,
  FR-45) View submenu + ⌘-number shortcuts to match the new registry; ideally
  drive the menu from the same list so future dashboards stay in sync.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | Sidebar lists dashboards from the registry: SysOps, Workflows, Web News, Scripts, Zsh Config Editor, Obsidian Viewer |
| 2 | "SysOps" shows the former six-panel grid; old persisted `dashboard` view migrates without a dead screen |
| 3 | Workflows dashboard shows linked Workflows + Events panels; standalone Events nav entry gone |
| 4 | Clicking a workflow highlights its events; clicking a run highlights that run's events; clicking an event highlights its workflow/run |
| 5 | Each placeholder opens a "Coming Soon" stub |
| 6 | Native menu View items + shortcuts match the registry |

---

## Phase 9 — Hub Absorption & Decommission (NF-4)

**Goal:** Make AgenticOS the owner of Codehome app management instead of
wrapping the external Hub on `:8085`, then retire the Hub. Replaces the
`tools/hub_mcp.py` REST proxy with a first-class registry + process manager in
the sidecar.

> **Provisional — needs a detailed drill-down before build** (we specced NF-2
> and NF-3 in depth but not NF-4). FRs below capture known scope and may be
> refined.

**Requirements (provisional)**

- **FR-60 — Native app registry.** Own the source of truth for Codehome apps:
  scan `~/Codehome/**/app.json`, parse metadata (id, name, expected port,
  agent block), expose as the canonical app list (no Hub round-trip).
- **FR-61 — Native process lifecycle manager.** start / stop / restart / status
  for apps without the external Hub: spawn + supervise processes, track
  ports/PIDs, health-check, surface logs. Honors `constitution.guard`
  (`hub_stop_all` approval, etc.).
- **FR-62 — Native manifest + scripts ingestion.** Agent blocks → `tool_registry`
  and script discovery/run handled in-process, replacing the `hub_mcp` proxy
  path (keep the same tool-registry contract so Phase 10 is unaffected).
- **FR-63 — "Scripts" dashboard goes live.** The Phase 8 Scripts placeholder
  becomes a functional dashboard over native script discovery/run; the Codehome
  Hub panel reads from the native manager.
- **FR-64 — Decommission path.** Parallel-run validation (native manager vs Hub)
  → cut over → retire external Hub on `:8085`; update `settings.yaml`
  (`hub_url`), `hub/docs/PORT_ASSIGNMENTS.md`, and remove proxy code.

**Acceptance criteria (provisional)**

| # | Criterion |
|---|-----------|
| 1 | App list, start/stop/restart, status all work with the external Hub stopped |
| 2 | Agent blocks + scripts still register in `tool_registry` (contract unchanged) |
| 3 | Scripts dashboard runs a discovered script end-to-end |
| 4 | Constitution guards apply to lifecycle actions |
| 5 | Hub `:8085` retired; no remaining runtime dependency on it |

---

## Phase 10 — Governing Agent (NF-3)

**Goal:** A conversational agent that can operate the whole app via natural
language, built on a new unified LLM provider layer, defaulting to a local
Ollama model with one-toggle cloud escalation, and able to run **and author**
workflows/config under Constitution enforcement.

**Locked decisions:** local-default + escalate-to-cloud · run **and** author
(gated by write-allowlist + approval, with config backups + YAML validation) ·
pull both Qwen2.5-7B-Instruct and Llama 3.1 8B to compare · dashboard named
"Agent" · text-only v1.

**Requirements**

- **FR-52 — Unified LLM provider layer (`core/llm.py`).** One seam over cloud
  (Anthropic) + local (Ollama) chat models via LangChain (`ChatAnthropic`,
  `ChatOllama`). Refactor `briefing_agent` to call through it (single LLM entry
  point).
- **FR-53 — Model registry + runtime switch.** Entries `{id, provider, label,
  context_window, supports_tools, cost_per_mtok|0}`. `GET /api/agent/models`
  (configured cloud + installed Ollama via `/api/tags`); `POST /api/agent/model`
  sets the active model. Local models priced 0 so they don't consume the daily
  cap.
- **FR-54 — Governing agent (`agents/governor.py`).** LangChain tool-calling
  agent (LangGraph `create_react_agent` or equivalent); tools wrap
  `list_workflows`/`run_workflow`, the agent ACTIONS, `tool_registry` tools, and
  read-only status. Reuses existing capability, not a parallel command layer.
- **FR-55 — Constitution + HITL for agent calls.** Every tool call passes
  `constitution.guard()`; `ApprovalRequired` → `APPROVAL_REQUIRED` AG-UI event
  pausing the turn until approved (reuse runner/approval-queue HITL). Token/cost
  budgets apply.
- **FR-56 — Agent chat dashboard.** New "Agent" dashboard (Phase 8 registry):
  transcript + input, streamed output, visible tool-call trace, inline approval
  prompts, **model-selector dropdown** + clear local/cloud indicator.
- **FR-57 — Agent streaming endpoint.** Session-scoped agent runner (sibling of
  `runner.py`) streaming tokens + tool events over `/ws/agent` via the
  `events.py` bus.
- **FR-58 — Small-local-model safeguards.** Tight, well-described toolset;
  tool-call iteration cap (loop guard); per-conversation escalate-to-cloud
  toggle; native tool-calling models preferred.
- **FR-59 — Authoring (run + author).** Agent may create/modify `workflows.yaml`
  and config; all writes pass `guard_write_path()` (allowlist) **and** an
  approval gate, with timestamped backups + YAML validation before save.
  Authoring defaults to requiring approval regardless of active model.

**New dependencies / infra:** `langchain`, `langchain-anthropic`,
`langchain-ollama`; **Ollama** local service (`:11434`, register in
PORT_ASSIGNMENTS); pull Qwen2.5-7B-Instruct + Llama 3.1 8B. Sidecar treats
Ollama as optional (cloud-only if it's down).

**Suggested sub-phasing:** 10a FR-52/53 (LLM layer + model endpoints) → 10b
FR-54/55/57 (agent + guard/HITL + streaming, headless) → 10c FR-56/58/59 (chat
dashboard, safeguards, authoring).

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | `core/llm.py` serves both Anthropic and Ollama; briefing agent uses it |
| 2 | Model list shows cloud + installed local models; switching changes the model used for the next turn |
| 3 | Agent runs a workflow and calls a registry tool from a natural-language request |
| 4 | An approval-required action pauses the turn and resolves via the approval UI |
| 5 | Daily cost cap respected; local turns cost 0 |
| 6 | Agent authors/edits a workflow only after approval, with a backup written and YAML validated |
| 7 | "Agent" dashboard streams output, shows tool calls, and indicates local vs cloud |
