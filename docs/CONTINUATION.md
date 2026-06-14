# Continuation note

**2026-06-14: Phase 10 (NF-3) sub-phases 10a + 10b — CODE COMPLETE; Mac
runtime smoke test pending.** Started NF-3 ahead of NF-4 per explicit request;
10a/10b depend only on NF-2 (done), not NF-4, so they're safe to land first.

## Current state

Roadmap phases 1–8 ✅. NF-3 / Phase 10 in progress:
- **10a (FR-52/53) code complete** — unified LLM layer + model registry.
- **10b (FR-54/55/57) code complete** — governing agent + Constitution/HITL +
  `/ws/agent` streaming (headless; no GUI). See CHANGELOG 2026-06-14.
- **10c (FR-56/58/59) not started** — Agent chat dashboard + safeguards +
  authoring.

## 10a — what landed (headless; no GUI)

Files touched:
- `core/llm.py` **(new)** — unified provider seam over Anthropic + Ollama via
  LangChain (lazy-imported). `ModelInfo` registry, `resolve()` alias→id,
  `active_model`/`set_active_model` session state, `is_available()`,
  `cost_usd()` (local=0; unknown cloud→most-expensive, conservative),
  `list_models()` (cloud + Ollama `/api/tags`), `get_chat_model()`,
  `complete()` (text + token + cost via `usage_metadata`).
- `agents/briefing_agent.py` — `compose_brief` routes through `core/llm.py`
  (single entry point); template fallback now keyed on `llm.is_available()`;
  removed local `_cost_usd`; dropped unused `import os`.
- `config/settings.yaml` — new `agent:` block (default_model = local
  `qwen2.5:7b-instruct`, `ollama_base_url`, 2 cloud + 2 local registry
  entries with `cost_per_mtok`); local pricing entries (0) + `local` alias.
- `gui/sidecar/app.py` — `GET /api/agent/models`, `POST /api/agent/model {id}`.
- `requirements.txt` — `langchain-core`, `langchain-anthropic`,
  `langchain-ollama`.

### Verified (sandbox)
`/tmp/test_llm_10a.py` (structural, no LangChain needed — it's lazy): registry
order, alias resolve + id passthrough, cost (cloud/local/unknown), active-model
get/set + KeyError, `list_models`/`is_available` with Ollama up/down ×
API-key present/absent, and briefing template fallback. All pass; `py_compile`
clean on the three changed `.py` files.

### ▶ Pending on the Mac (do these before signing off 10a + 10b)
1. `pip install -r requirements.txt` into `.venv` (Mac venv; sandbox has no
   Linux python for the Mac `.venv`, so langchain/ollama weren't installed
   there — note `langgraph` was already a dep and is what 10b's agent uses).
2. `ollama serve`; `ollama pull qwen2.5:7b-instruct` and `ollama pull
   llama3.1:8b`.
3. Register **:11434** in `~/Codehome/hub/docs/PORT_ASSIGNMENTS.md` (TR-10) —
   that file is outside this repo (not mounted), so it wasn't edited here.
4. `ruff check core/llm.py agents/briefing_agent.py agents/governor.py
   gui/sidecar/agent_runner.py gui/sidecar/app.py`.
5. **10a smoke:** start sidecar → `curl :5130/api/agent/models` shows cloud +
   installed locals with `active` = qwen; `POST /api/agent/model` switches;
   run morning-briefing with a local model → real brief, `mode: "ollama"`,
   `cost_usd: 0`.
6. **10b smoke:** `POST /api/agent/chat {"message":"list my workflows"}` (or a
   WS client on `/ws/agent`) → stream shows `RUN_STARTED` →
   `TEXT_MESSAGE_CONTENT` → `RUN_FINISHED`. Then a request that triggers
   `call_tool` → confirm an `APPROVAL_REQUIRED` event, that it appears in
   `GET /api/approvals`, and that `POST /api/approvals/{id}` with `approve`
   resumes the turn (and `deny` returns a `DENIED:` tool result). Watch the
   loop guard on small local models (`MAX_TOOL_ITERATIONS`).

## 10b — what landed (headless; no GUI)

New files:
- `agents/governor.py` — `GovernorToolbox` (7 guarded tools wrapping
  workflows / `tool_registry` / agent actions / read-only status) +
  `GOVERNOR_SYSTEM` prompt + `build_tools` (StructuredTools) + `build_agent`
  (lazy LangGraph `create_react_agent` over `llm.get_chat_model`). All
  side-effects pass `constitution.guard()`; `call_tool` = `api_call_external`
  (approval-required). Plain object → unit-testable without LangChain.
- `gui/sidecar/agent_runner.py` — `AgentRunner`: per-turn worker thread,
  streams `RUN_STARTED`/`TEXT_MESSAGE_CONTENT`/`TOOL_CALL_*`/`APPROVAL_REQUIRED`/
  `RUN_FINISHED`/`RUN_ERROR` over the `events` bus; token-stream with
  `invoke()` fallback; per-turn token+cost budget check (local = 0). **Agent
  approvals reuse the shared `runner.approvals` queue → resolved by the existing
  `POST /api/approvals/{id}`.**

Edited:
- `gui/sidecar/app.py` — `POST /api/agent/chat` (trigger → turn_id) and
  `WS /ws/agent` (inbound `{message,model?,session_id?}`; outbound AG-UI stream
  with history replay).

### Verified (sandbox; installed langgraph to exercise imports — no model call)
`/tmp/test_governor_10b.py`: guard pass/deny/block/approve + event hooks,
invalid-args + unknown-workflow guards, `build_tools` → 7 named+described tools,
`agent_runner` imports clean. `py_compile` clean on all changed files. (Full
`app.py` import needs the Mac venv: fastapi + macOS-only `iterm2`.)

### ▶ NEXT: 10c (FR-56/58/59) — Agent dashboard + safeguards + authoring
- **FR-56:** new "Agent" dashboard in the Phase 8 `VIEWS` registry
  (`gui/desktop/src/App.jsx`): chat transcript + input wired to `/ws/agent`,
  streamed assistant output, visible tool-call/step trace, inline approval
  prompts (resolve via `/api/approvals/{id}`), **model-selector dropdown**
  (`/api/agent/models` + `POST /api/agent/model`) with a clear local/cloud
  indicator. Add the View-menu entry in `src-tauri/src/lib.rs` (⌘7).
- **FR-58:** per-conversation "escalate to cloud" toggle (switch model mid-
  session); loop guard already in `agent_runner` (`MAX_TOOL_ITERATIONS`).
- **FR-59 (authoring):** add guarded `write_config`/`edit_workflow` tools —
  `guard_write_path()` (allowlist) **and** approval gate, timestamped backup +
  YAML validation before save; authoring defaults to requiring approval
  regardless of model. Full spec: `docs/PRD-addendum-phases-8-10.md` (Phase 10)
  + `docs/feature-backlog.md` (NF-3).

### Deferred / still open
- NF-4 / Phase 9 (Hub absorption, FR-60–64) still needs a detailed drill-down
  before build. NF-3's agent governs the Hub *better* once NF-4 lands, but 10a–c
  don't block on it (agent drives the Hub through the existing `tool_registry`
  proxy for now).

### Repo note
This workspace can edit files but **cannot push** (sandbox has no GitHub creds;
the mount blocks the file-deletes git needs). After edits, commit + push from
the Mac: `git add -A && git commit -m "…" && git push`. This session's changes
are unpushed.

## Key files
- `core/llm.py` — unified LLM layer (10a)
- `agents/governor.py` — governing agent + guarded toolbox (10b)
- `gui/sidecar/agent_runner.py` — agent turn runner + HITL bridge + streaming (10b)
- `docs/roadmap.md` — phase status (Phase 10 🟡 10a)
- `docs/CHANGELOG.md` — 2026-06-14 10a entry
- `docs/PRD-addendum-phases-8-10.md` / `docs/feature-backlog.md` — NF-3 spec
- `Brain2/01 - Projects/PRDs/Agentic OS - Full PRD.md` — Full PRD (not mounted)
