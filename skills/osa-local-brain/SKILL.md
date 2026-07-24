---
name: osa-local-brain
description: |
  Make OSA do real work on the LOCAL Ollama brain (not just the cloud/Claude brain) in AgenticOS. Use this skill whenever you touch OSA turn ROUTING (local vs cloud), the Ollama connection/port, which TOOLS a local model gets, model warming/preloading, local-turn LATENCY, or when OSA "can't do X" / "is out of credits" for a task it should handle offline. Covers the :12434 Ollama config + auto-start, the curated LOCAL_TOOL_NAMES subset (a 7B chokes on all 29 schemas), route_turn's menial-vs-web/heavy split, pick_model + local pins, the warm_ollama re-probe, and the startup preload. Read alongside osa-chat-dual-path (the two chat routes) and osa-sidecar-lifecycle (restart/verify).
compatibility: AgenticOS repo, agents/osa_agent.py + core/llm.py + gui/sidecar/app.py + config/settings.yaml
---

# OSA Local Brain (route + tool + warm the Ollama side)

## Overview

OSA has **two brains**: a **local** one (Ollama, `config/settings.yaml`
`agent.ollama_base_url`, currently `http://localhost:12434`) and a **cloud** one
(Claude via the Anthropic API). Per turn, `agents/osa_agent.py` decides which:

- `route_turn(message)` → `"local"` or `"default"` (cloud), by keyword.
- `pick_model(message, ollama_ready, pin)` → an alias or a pinned id, honoring the
  brain pin and the Ollama-down downgrade.
- `core.llm.resolve("local")` → the configured `default_model` (an Ollama id);
  `resolve("default")` → the cloud model.

**Design (2026-07-23, Tony's "Both"):** menial system tasks run LOCAL (work
offline / credit-free); web + heavy reasoning run CLOUD. Before this, every
tool-worthy turn forced cloud, so menial tasks died the moment credits ran out.

## Routing — the menial/heavy split

`route_turn` order matters:
1. chit-chat exact match → `local`
2. **`_HEAVY_HINTS`** (web/online/google/why/explain/research/analyze/run/delete/
   move/code…) → `default` — checked FIRST so "why is the app down" reasons on
   cloud rather than routing local off the "is "/"app" menial hint.
3. **`_MENIAL_HINTS`** (launch/start/stop/status/health/memory/remember/note/
   mail/message/text/app/project/time…) → `local`
4. `"?"` → `default`; very short → `local`; else `default`.

`pick_model`:
- **cloud pin** → that id every turn.
- **local pin** → keeps `local`-routed (menial + chit-chat) turns; only
  `default`-routed (web/heavy) turns escalate to cloud. Ollama down → `default`.
- **auto (no pin)** → `route_turn` result; `local` + Ollama down → `default`
  (never hard-fail).

When you change routing, update the matrices in `test_phase14a_osa.py::TestRouting`
and `test_osa_brain_switch.py::TestPickModelMatrix`, and the cases in
`test_osa_local_capability.py`.

## The curated local toolset (DO NOT hand a 7B all 29 tools)

`agents/osa_agent.py`:
- `LOCAL_TOOL_NAMES` — the ~19 menial tools a local model gets (notes, apps,
  status, remember, messages, mail, time). **Sharp/arbitrary tools stay
  CLOUD-only** (`run_command`, `delete_file`, `move_file`, `search_*`).
- `build_tools(toolbox, only=...)` filters by name.
- `build_agent` binds the subset when `_pin_is_local(model_id)`, else all 29.

**Why (measured):** qwen2.5:7b calls a tool in **~7s with 2 tools** but
**minutes / loops** with all 29 — the 29 schemas bloat the prompt and a 7B
mis-picks. Keep the local set small. Cover a new menial capability by adding its
tool to `LOCAL_TOOL_NAMES`; never add a destructive/arbitrary tool there.

## Warming: warm_ollama + startup preload

Two separate mechanisms — keep them straight:

1. **`osa_agent.warm_ollama()`** — is Ollama *up*? Success is STICKY, but a
   **not-ready result RE-PROBES** on the next call (cheap `llm.ollama_up()` first,
   spawn only if truly down). **Do NOT cache not-ready permanently** — the old
   code did, and a single transient first-probe failure (its 1s timeout losing to
   a cold sidecar right after restart) stranded EVERY local turn on the cloud
   brain for the whole process. Symptom: `pick_model` escalates every local turn
   to cloud even though `/api/osa/state` shows `ollama_up:true`.
2. **`core.llm.preload_model(id, keep_alive="30m")`** — loads the model into
   memory (empty-prompt `/api/generate`, `done_reason:"load"`). The
   `_ensure_ollama_up` startup hook (`gui/sidecar/app.py`) calls it for the
   effective local model (pin if local, else `resolve("local")`) so the FIRST
   real turn is warm.

**Latency reality:** local turns are ~90s COLD (model load) → ~20s warm
(`get_time`) → ~50s warm for a big tool output (`list_projects`, 28 rows). The
warm floor is the react loop on a small model. Levers: pin a faster model, trim
tool output, shrink `LOCAL_TOOL_NAMES`. Set expectations — local ≠ instant.

## Ollama connection + port

- `core.llm.ollama_base_url()` honors `OLLAMA_HOST` env FIRST, then
  `settings.yaml agent.ollama_base_url`, then `:11434`. The launchd sidecar's env
  has no `OLLAMA_HOST`, so settings wins → `:12434`.
- `core.llm.ensure_ollama_running()` spawns `ollama serve` bound to the configured
  port ONLY if nothing answers there (no-op when up). Called at startup by
  `_ensure_ollama_up` and lazily by `warm_ollama`.
- **Port ledger is in MySQL** (`ports` table, `SERVICE_PORTS` in
  `gui/sidecar/seed_port_ledger.py`) — 12434 is registered `ollama-local`. The old
  `hub/docs/PORT_ASSIGNMENTS.md` is a generated artifact, not the source of truth.

## Gotchas paid for (each cost real time)

1. **`requests` is imported INSIDE functions in `core/llm.py`, not module-level.**
   A new llm.py function that uses `requests` must `import requests` locally or it
   `NameError`s — and if that's inside a best-effort `try/except`, it silently
   returns False (preload "failed" with no clue). Same reason a test can't
   `monkeypatch.setattr("core.llm.requests.post", …)` — patch the library global
   (`monkeypatch.setattr(requests, "post", …)`) instead.
2. **Model-resolution tests couple to the LIVE Ollama model set.** Pointing at the
   richer :12434 instance made bare `"llama"` ambiguous and `"opus"` resolve (it
   has a `claude-opus-*` model), breaking `resolve_brain`/`switch_model` tests.
   Mock `core.llm.discover_ollama` (→ `{}`) or use an unambiguous registry-backed
   id so these tests are hermetic.
3. **A stray sidecar holding :5130 defeats `agentic-gui restart` silently** — the
   port-singleton means the launchd `kickstart` instance sees :5130 taken and
   exits, so OLD code keeps serving and your routing/tool changes look like they
   "didn't work." After ANY restart, confirm the :5130 owner's start time
   (`ps -eo pid,lstart,command | grep gui.sidecar`) and `pkill -9 -f "python -m
   gui.sidecar"` before relaunch. See osa-sidecar-lifecycle.

## Verify a local turn end-to-end (no cloud needed)

```bash
# menial task with cloud credits irrelevant — should route local + call a tool
curl -s -m180 localhost:5130/api/osa/chat -H 'Content-Type: application/json' \
  -d '{"message":"what time is it right now?","thread_id":"local-verify"}' \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["model"],d["route"],[t["tool"] for t in d["tool_trace"]],d["reply"][:80])'
# expect: <ollama id>  local  ['get_time']  "It's ...."
```
If it shows a cloud model / `route:default`, check (a) the pin
(`/api/osa/model`), (b) `route_turn` for that message, (c) `warm_ollama()` /
`ollama_up()`, (d) that the sidecar is actually running your code (stray PID).
