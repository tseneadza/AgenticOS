# Continuation note

**2026-06-17 (2): Open issue #3 (small-model tool-calling) + Ollama model-list
overhaul. `core/llm.py` now auto-starts `ollama serve` when down, dynamically
discovers ALL pulled models (not just the 4 in settings.yaml), and RAM-gates
locals (available only if < half of total RAM; oversized → `too_large`, service
down → `ollama_off`). `GOVERNOR_SYSTEM` rewritten with a tool-first directive +
request→tool map. Sandbox-tested (stubbed tags/RAM); live `ollama serve` spawn +
GUI check Mac-pending. Issues #2 + #4 still open.**

**2026-06-17: Open issue #1 (Send-to-unavailable-model UX) FIXED in
`AgentView` — Send/textarea now gated on the active model's availability, with
auto-fallback to an available local model and an inline hint. Parse-verified;
live GUI check Mac-pending. Issues #2–#4 still open.**

**2026-06-14: Phase 10 (NF-3) 10a+10b+10c CODE COMPLETE. Live Mac smoke test
IN PROGRESS — Agent dashboard runs, model plumbing now works end-to-end. Four
issues queued for the next session (see "Open issues" below).**

## Current state

Roadmap phases 1–8 ✅. NF-3 / Phase 10 in progress:
- **10a (FR-52/53) code complete** — unified LLM layer + model registry.
- **10b (FR-54/55/57) code complete** — governing agent + Constitution/HITL +
  `/ws/agent` streaming (headless; no GUI).
- **10c (FR-56/58/59) code complete** — Agent chat dashboard + escalate toggle +
  authoring tools.

### Live smoke-test progress (this session)
- ✅ Sidecar serves the agent endpoints (after clearing a **stale sidecar** that
  was squatting :5130 — see gotchas). `/api/agent/models` returns the registry.
- ✅ Model dropdown populates; model switch + escalate-to-cloud toggle work
  (badge flips local↔cloud).
- ✅ **Local model path fixed:** sidecar was hitting Ollama on :11434 but the
  user runs Ollama on **:12434** (`OLLAMA_HOST`). Fixed in `core/llm.py` —
  `ollama_base_url()` now honors `OLLAMA_HOST`. Verified: sidecar resolves
  `http://127.0.0.1:12434` and sees `qwen2.5:7b-instruct` + `llama3.1:8b`.
- ⏳ Still to confirm in the GUI: a clean local reply, the tool-call trace, the
  approval round-trip, and an authoring round-trip (the 10c "Pending on the Mac"
  list below).

### ⚠️ Uncommitted (commit + push from the Mac)
- `core/llm.py` — OLLAMA_HOST support (FR-52 fix).
- `gui/desktop/src/App.jsx` + `gui/desktop/src/App.css` — issue #1 fix (Send
  gated on availability + auto-fallback + `.agent-hint`) **and** dynamic model
  list (size suffixes, reason-aware labels via `modelSuffix`/`modelHint`).
- `core/llm.py` — Ollama auto-start (`ensure_ollama_running`), dynamic discovery
  (`discover_ollama`), RAM gating (`total_ram_bytes`/`_ram_fit`), discovered-id
  resolution in `get_model_info`/`set_active_model`, **and** pinned cloud endpoint
  (`anthropic_base_url`/`_isolated_anthropic_env`, issue #2).
- `config/settings.yaml` — new `agent.anthropic_base_url` (issue #2).
- `gui/sidecar/app.py` — `/api/agent/models?start=` ensures Ollama + re-discovers.
- `agents/governor.py` — tool-first `GOVERNOR_SYSTEM` (issue #3).
- `scripts/diagnose_cloud.py` **(new)** — layered diagnostic for issue #2
  (sys.path fix + ANTHROPIC_BASE_URL warning).
- `docs/CHANGELOG.md` — entries for the OLLAMA_HOST fix, issue #1, issue #3 +
  the Ollama model-list overhaul.
- `docs/CONTINUATION.md`, `docs/roadmap.md`, `README.md` — this checkpoint.
```sh
cd ~/Codehome/AgenticOS && git add -A && \
  git commit -m "NF-3: OLLAMA_HOST + Agent Send-guard (#1) + dynamic Ollama discovery/auto-start/RAM gate + tool-first governor (#3)" && git push
```

### ▶ Open issues — START HERE next session (user-confirmed 2026-06-14)
1. ~~**Send to unavailable model (UX).**~~ ✅ FIXED 2026-06-17. `AgentView`
   derives `activeAvailable` from `activeInfo.available` and gates the Send
   button, `send()`, and the textarea on it; auto-falls-back once to the first
   available local model (never silently to cloud); shows an `.agent-hint`
   explaining the block. Parse-verified — confirm in the live GUI.
2. ~~**Cloud "Connection error".**~~ ✅ ROOT-CAUSED + FIXED 2026-06-17.
   `scripts/diagnose_cloud.py` revealed the shell exports
   `ANTHROPIC_BASE_URL=http://localhost:12434` + `ANTHROPIC_AUTH_TOKEN=ollama`
   (to route other tools through local Ollama). `ChatAnthropic()` inherited them,
   so "cloud" calls hit localhost:12434 → `404 model not found` (or
   `APIConnectionError` when Ollama was down). curl + httpx to the real API = 200,
   isolating it to SDK env inheritance. **Fix:** `core/llm.get_chat_model` now
   pins `base_url` (`anthropic_base_url()`, settable via
   `settings.agent.anthropic_base_url`) + passes the key explicitly, and builds
   the client inside `_isolated_anthropic_env()` (strips the two ambient vars for
   the build, restores after). ▶ Verify on the Mac: in the Agent view pick
   `claude-sonnet-4-6` and confirm a real reply + non-zero tokens/cost; rerun
   `scripts/diagnose_cloud.py` — section 6 (`core.llm.complete`) should now
   succeed.
3. ~~**Small-model tool-calling reliability (FR-58).**~~ ✅ ADDRESSED 2026-06-17.
   `GOVERNOR_SYSTEM` now has an explicit "use tools, do not guess" section + a
   request→tool map (list_workflows / run_workflow / list_tools / get_status /
   get_runs). Escalate-to-cloud stays as the fallback. ▶ Verify on the Mac: with
   qwen2.5-7B active, "list my workflows" now emits a `list_workflows` call (and
   the trace chips render) rather than prose. If still flaky, switch the default
   local to llama3.1:8b or lean on escalate.
   **Also shipped alongside (user request):** dynamic Ollama model list +
   auto-start + RAM gating (see CHANGELOG 2026-06-17). ▶ Mac verification:
   (a) quit Ollama, open the Agent view → sidecar should spawn `ollama serve` on
   :12434 and the dropdown should populate within a few seconds;
   (b) confirm every pulled model appears (not just the 4 configured), with sizes;
   (c) confirm any model needing ≥ half your RAM shows disabled `(too large)`.
   Note: a Finder-launched build needs `ollama` on PATH to auto-start — if it
   isn't, set `agent.ollama_base_url`/keep the menubar app running.
4. ~~**Commit message mislabel.**~~ ✅ NOTED 2026-06-17. History left unrewritten;
   a marker note at the top of the 10c CHANGELOG entry records that commit
   `0270602` = 10a + 10b + 10c (source of truth).

### Known gotchas (Mac runtime) — learned this session
- **Stale sidecar on :5130.** If `/api/agent/*` 404s but `/ws/agui` events flow,
  an old sidecar (pre-agent-endpoints) owns the port and the new one couldn't
  bind. Quit the app → `pkill -f gui.sidecar` → confirm `lsof -nP -iTCP:5130
  -sTCP:LISTEN` is empty → relaunch.
- **Ollama port via `OLLAMA_HOST`.** The user runs Ollama on :12434, not the
  :11434 default. `core/llm.ollama_base_url()` now honors `OLLAMA_HOST`; the
  sidecar must be launched from a shell where it's exported (dev mode inherits
  it; Finder-launched builds do not — then set `agent.ollama_base_url` in
  `config/settings.yaml`).
- The Mac `.venv` (Python 3.12) is the project interpreter; the Linux sandbox
  cannot run it. Verify imports with `./.venv/bin/python`.

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

## 10c — what landed (this session)

Files touched:
- `gui/desktop/src/App.jsx` — new `AgentView` + `buildTranscript()` +
  `ModelBadge`; appended `{ id: "agent", label: "Agent", component: AgentView,
  badge: "approvals" }` as the **last** `VIEWS` entry (keeps ⌘1–6 stable, Agent =
  ⌘7). Transcript is reconstructed from the shared AG-UI `feed` by filtering
  `run_id` prefix `agt-` (no second WebSocket); messages sent via `POST
  /api/agent/chat`. Inline approvals come from `ctx.approvals` filtered to
  `workflow` starting `agent:` and resolve via `ctx.decide`. Model dropdown +
  local/cloud badge + escalate checkbox drive `GET /api/agent/models` / `POST
  /api/agent/model`.
- `gui/desktop/src-tauri/src/lib.rs` — added `view-agent` MenuItem (`cmd+7`) to
  the View submenu; the existing generic `view-<id>` handler routes it.
- `gui/desktop/src/App.css` — `.agent-*` / `.trace-chip` styles (chat bubbles,
  tool-trace chips, inline approval, model bar, input).
- `agents/governor.py` — FR-59 authoring: `write_config` + `edit_workflow` +
  `_authoring_write` + `_save_with_backup`; added to `build_tools` (9 tools) and
  `GOVERNOR_SYSTEM`; new imports (`shutil`, `time`, `Path`, `yaml`, `CONFIG_DIR`).

### Verified (sandbox)
`/tmp`-style test (`outputs/test_governor_10c.py`, 23 checks): write_config
new-write (no backup) / overwrite (timestamped `.bak` with prior content) /
invalid-YAML-rejected-before-approval / denial-blocks-write / bad-extension /
outside-allowlist `BLOCKED` (no approval asked); edit_workflow preserve-others +
backup + bad-`definition_json`; `build_tools` exposes `write_config` +
`edit_workflow` = 9 tools. `py_compile` clean on all changed `.py`. esbuild JSX
transform of `App.jsx` bundles clean (56.6 kb). **No live model call** (sandbox
can't run the Mac `.venv`/Ollama).

### ▶ Pending on the Mac (before signing off 10c)
1. `npm run tauri dev` (or build) → open **Agent** view (⌘7). Confirm: model
   dropdown lists cloud + installed locals with the active one selected and a
   local/cloud badge; the **escalate-to-cloud** checkbox flips active model and
   the badge updates.
2. Send a message → confirm the user bubble + streamed assistant reply appear and
   the tool-trace chips show running→done as `TOOL_CALL_*` events arrive.
3. Trigger a tool that needs approval (e.g. ask it to `call_tool`) → confirm the
   inline Allow/Deny prompt appears in the transcript and resolving it (via the
   shared `/api/approvals/{id}`) resumes the turn.
4. **Authoring round-trip:** ask the agent to change a config value or add a tiny
   workflow → confirm it always asks for approval, writes a `*.bak` backup next
   to the edited file, and the saved YAML is valid. Confirm a write outside the
   `write_allowlist` returns `BLOCKED`.
5. `ruff check agents/governor.py gui/sidecar/app.py` (App.jsx/lib.rs unchanged
   contracts).

### ▶ NEXT (after 10c sign-off)
- **Phase 10 final sign-off:** run the Mac smoke items for 10a + 10b (see those
  sections above) and 10c (just above), then flip Phase 10 to ✅ in
  `docs/roadmap.md`.
- **NF-4 / Phase 9 (Hub absorption, FR-60–64):** still needs a detailed
  drill-down before build (see Deferred). This is the next build target.

### Deferred / still open
- NF-4 / Phase 9 (Hub absorption, FR-60–64) still needs a detailed drill-down
  before build. NF-3's agent governs the Hub *better* once NF-4 lands, but 10a–c
  don't block on it (agent drives the Hub through the existing `tool_registry`
  proxy for now).

### Repo note
This workspace can edit files but **cannot push** (sandbox has no GitHub creds;
the mount blocks the file-deletes git needs). This session's 10c changes are
unpushed. Commit + push from the Mac:

```sh
cd ~/Codehome/AgenticOS
git add -A
git commit -m "Phase 10 (NF-3) 10c: Agent dashboard (FR-56) + escalate toggle (FR-58) + authoring tools (FR-59)"
git push
```

(Optional sandbox artifact: `outputs/test_governor_10c.py` is the 10c authoring
unit test; copy it into `tests/` if you want it tracked.)

## Key files
- `core/llm.py` — unified LLM layer (10a)
- `agents/governor.py` — governing agent + guarded toolbox + authoring (10b/10c)
- `gui/sidecar/agent_runner.py` — agent turn runner + HITL bridge + streaming (10b)
- `gui/desktop/src/App.jsx` — `AgentView` Agent dashboard (10c, FR-56/58)
- `gui/desktop/src/App.css` — `.agent-*` chat styles (10c)
- `gui/desktop/src-tauri/src/lib.rs` — ⌘7 Agent View-menu entry (10c)
- `docs/roadmap.md` — phase status (Phase 10 🟡 10a)
- `docs/CHANGELOG.md` — 2026-06-14 10a entry
- `docs/PRD-addendum-phases-8-10.md` / `docs/feature-backlog.md` — NF-3 spec
- `Brain2/01 - Projects/PRDs/Agentic OS - Full PRD.md` — Full PRD (not mounted)
