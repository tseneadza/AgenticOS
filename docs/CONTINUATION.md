# Continuation note

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
- `docs/CHANGELOG.md` — entry for the OLLAMA_HOST fix.
- `docs/CONTINUATION.md`, `docs/roadmap.md`, `README.md` — this checkpoint.
```sh
cd ~/Codehome/AgenticOS && git add -A && \
  git commit -m "NF-3: honor OLLAMA_HOST in core/llm; Phase 10 smoke-test docs" && git push
```

### ▶ Open issues — START HERE next session (user-confirmed 2026-06-14)
1. **Send to unavailable model (UX).** The Agent view let a message be sent
   while the active model was "not installed" (`AgentView` in
   `gui/desktop/src/App.jsx`: the `<option>` is `disabled` but the active model
   still defaulted to local-qwen and Send stayed enabled). Fix: disable Send (or
   auto-fall back to an available model) when `activeInfo.available` is false;
   surface a hint.
2. **Cloud "Connection error".** Selecting `claude-sonnet-4-6` returned the
   anthropic SDK's `APIConnectionError` ("Connection error.") even though the key
   is present (option not greyed). Not yet diagnosed. Repro/diagnostics:
   `curl https://api.anthropic.com/v1/models -H "x-api-key: $ANTHROPIC_API_KEY"
   -H "anthropic-version: 2023-06-01"` and a direct `llm.complete(... model=
   "claude-sonnet-4-6")` for the full traceback. Suspects: SSL/proxy, or the
   sidecar env differing from the shell. (Key IS in the sidecar env — the cloud
   option renders available.)
3. **Small-model tool-calling reliability (FR-58).** Qwen2.5-7B may answer in
   prose without invoking tools (e.g. `list_workflows`). Tune `GOVERNOR_SYSTEM`,
   prefer a stronger local tool-caller, or lean on escalate-to-cloud. Verify the
   tool-trace chips render when a tool *is* called.
4. **Commit message mislabel.** 10c landed inside commit `0270602` whose message
   reads "10a+10b". History understates 10c. Optional: a follow-up empty/marker
   commit or a note so the log is accurate.

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
