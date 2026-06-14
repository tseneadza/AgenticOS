# Feature Backlog — intake for next PRD batch (Phase 8+)

Status: **intake in progress** (Tony listing features 2026-06-14). Each item gets
fleshed out here, classified, and slotted into a phase. Priority + final PRD
wording assigned after the full list is captured. IDs are provisional (NF-n).

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
- **Type:** GUI/UX
- **Summary:** The left sidebar nav becomes a registry of named dashboards:
  - Rename **Dashboard → "SysOps"** (Overall System Operations).
  - **Merge Workflows + Events into one "Workflows" dashboard** with linked
    panels: a Workflows panel and an Events panel. Running a workflow creates
    its events; clicking a workflow highlights its corresponding events, and
    clicking an event highlights its source workflow (bidirectional linking).
    The standalone Events view goes away (becomes a panel here).
  - Add **placeholder dashboards** (registered in nav, non-functional stubs for
    now): **Web News**, **Scripts**, **Zsh Configuration Editor**,
    **Obsidian Viewer**.
- **Fits existing design:** aligns with FR-37 (registry-driven nav) and design
  principle #7 (new paradigm = new nav link). Builds on Phase 3 nav shell.
- **Open questions:** confirm name "SysOps" vs "Overall System Operations";
  what links a workflow↔event (run_id correlation?); should placeholders show a
  "coming soon" state.

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
- **Open questions:** should it only *run* existing workflows or also *author*
  new ones; text-only or voice too; default model on launch (local vs cloud).

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
