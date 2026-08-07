# Kickoff Prompt — Codehome App Start/Stop: Verify, Fix, and Test Every App

> Paste this whole file as the opening message of a fresh **Claude Code** session
> in `~/Codehome/AgenticOS` (Claude Code so the `test-author` subagent is
> spawnable — see Process Rules). It is self-contained; assume the executing
> session has no prior context.

---

## 0. Goal

The **Codehome Hub** panel starts/stops individual Codehome apps via
`POST /api/apps/{id}/start|stop`. Some apps can't actually be started or stopped
through the panel. Make start/stop **work for every Codehome app**, and lock it
in with tests so regressions can't reappear.

Two things ship together:
1. **Fixes** so every app that *should* be panel-managed actually starts and stops.
2. **Tests** — a hermetic contract layer (always-on) + a live smoke layer
   (marker-gated) — that prove it and catch future breakage.

---

## 1. Required reading (do this first, cheaply)

Per repo convention, read before touching anything:
- `CLAUDE.md` — session-budget rule, **testing subagent rule**, DB rule
  (MySQL/SQLAlchemy only; tests use the `agenticos_test` schema), port rule,
  API-registration rule, docs-same-change rule.
- `docs/CONTINUATION.md` — read with `head`/`tail`/offset, it's large; check for
  any in-flight work before starting.
- `docs/GLOSSARY.md` — keep current if you introduce a term.
- The start/stop path you're working on:
  - `core/app_registry.py` — scans `~/Codehome/**/app.json`, `_parse_app_json`
    (drops manifests with no `id`), TTL cache, `get`/`get_all`/`get_manifests`.
  - `core/process_manager.py` — the singleton `manager`; `start` tries the
    MySQL launch-config plan (`_load_launch_steps` → `_launch_steps`) then falls
    back to the legacy `start_command` path (`_launch_legacy`); `stop` does
    process-group `SIGTERM→SIGKILL` + a DB orphan sweep; `status` is a TCP
    port-probe merged with `app_processes` rows.
  - `gui/sidecar/routes/api_apps.py` — the REST surface the panel calls
    (`/start`, `/stop`, `/restart`, `/status`, `/{id}/launch-plan`, list_apps).
  - `gui/sidecar/launch_config.py` — `build_launch_command`, `record_process`,
    `mark_process_stopped`, `get_app_status`.
  - `gui/sidecar/tests/test_phase13c.py` — the existing process-manager tests
    (synthetic `sleep`/`true`/`false` apps). Match these conventions and the
    `conftest.py` MySQL fixtures. **These do NOT test the real Codehome apps —
    that gap is what you're filling.**

---

## 2. Diagnosis already done (don't re-discover — verify, then act)

A scan of every `app.json` under `~/Codehome` (maxdepth 3) found **32 manifests**,
of which the registry only surfaces **28** (matches the panel's "Apps
registered: 28"). Confirmed defects, each a start/stop failure mode:

| # | Defect | Effect | Category |
|---|--------|--------|----------|
| 1 | **4 malformed `app.json`** (missing `id`) | `_parse_app_json` silently drops them → invisible in panel, never startable | manifest |
| 2 | **`hub` (Codehome Hub) has no `web.command`** | real `start()` → `"no start_command in app.json"`; shows "running" only because the retired external Go Hub is up on :8085 | manifest / policy |
| 3 | **Port 5130 collision**: `agenticos` **and** `brain-scanner` both claim 5130 | port-probe reports `brain-scanner` "running" whenever the sidecar is up (false positive); the two are indistinguishable by status | port / status |
| 4 | **`agenticos` = the sidecar itself** | start/stop from the panel is nonsensical/self-destructive | policy |
| 5 | **Present-but-broken commands** (bad entrypoint, missing venv/deps) | only fail on a *real* launch; static checks can't see them | runtime |

Re-run the scan yourself to get the current exact list (IDs, the 4 malformed
paths, ports) before editing — the tree may have changed:

```bash
cd ~/Codehome && find . -maxdepth 3 -name app.json \
  -not -path '*/node_modules/*' -not -path '*/.venv/*' -not -path '*/.git/*' \
  > /tmp/appjsons.txt
python3 - <<'PY'
import json
for p in (l.strip() for l in open('/tmp/appjsons.txt') if l.strip()):
    try: d=json.load(open(p))
    except Exception as e: print("MALFORMED", p, "->", str(e)[:60]); continue
    w=d.get('web') or {}
    print(d.get('id','<NO_ID>'), '|', d.get('name','?'), '| cmd=',
          'Y' if (w.get('command') or []) else 'N',
          '| port=', w.get('port') or w.get('expected_port') or '-',
          '| type=', d.get('type','web'), '|', p)
PY
```

---

## 3. Decisions locked with Tony (build to these — don't re-litigate)

**Test strategy — two layers:**
- **Hermetic contract tests (always-on, join the main suite).** No real
  launches. For the real registry, assert the launch/manifest *contract* holds.
- **Live smoke tests (opt-in, `@pytest.mark.live`).** Actually start → health →
  stop each manageable app. Excluded from the default suite so the ~707-green
  run stays fast and hermetic; run manually with `-m live`.

**Live success criterion — HTTP 200 with a fallback ladder:**
1. If the app declares a health-check URL (launch config `health_check.url`, or
   a manifest health path) → `GET` it, require **HTTP 200**.
2. Else `GET` the app root (`http://localhost:{port}/`) → require a served
   response (**2xx/3xx**; a connection-refused/5xx = fail).
3. Else (no HTTP surface, e.g. `type: cli`) → **TCP port open**.
4. Else → **process stays alive** for a few seconds.
Key off `type` + `expected_port`: `web`/`both` with a port → HTTP; otherwise the
lower rungs.

**Broken apps — FIX so they're start/stoppable, exempt only the un-manageable:**
- **Fix the 4 malformed manifests** (#1): give each a valid `id`, `name`, and a
  correct `web` block (command + port). If a directory isn't actually a runnable
  app, remove/relocate the stray `app.json` instead — decide per case, note why.
- **Resolve the 5130 collision** (#3): `brain-scanner` is a real app, not the
  sidecar — reassign it to a free port from `hub/docs/PORT_ASSIGNMENTS.md`,
  **register the new port there** (port rule), and update its `app.json`.
- **`hub`** (#2) and **`agenticos`** (#4): these two genuinely cannot be
  panel-started (retired external Hub / the running sidecar itself). Add them to
  a small, well-commented **exempt set** (see Task A) rather than faking a
  command. The `/{id}/launch-plan` route already treats `agenticos`/`hub` as
  intentionally unconfigured — align with that precedent.

---

## 4. Deliverables (tasks)

### Task A — Exemption policy + `manageable` flag  *(production code, main session)*
- Define a single canonical exempt set (e.g. `NON_MANAGEABLE_APP_IDS =
  {"agenticos", "hub"}`) in one obvious place (`core/app_registry.py` or
  `core/process_manager.py`), each entry with a one-line reason comment.
- Surface a boolean `manageable` on each app in `GET /api/apps` (list_apps) and
  `GET /api/apps/{id}`. `manageable = app_id not in NON_MANAGEABLE_APP_IDS`.
- Optionally have `start()`/`stop()` short-circuit exempt apps with a clear,
  structured error (not a crash) so an accidental call is safe.

### Task B — Fix manifests + ports  *(production code, main session)*
- Repair the 4 malformed `app.json` files (or remove stray ones) per §3.
- Reassign `brain-scanner`'s port off 5130; register it in
  `hub/docs/PORT_ASSIGNMENTS.md`; update the manifest.
- After edits: `app_registry.invalidate_cache()` semantics — confirm all
  intended apps now parse and register (count should rise from 28 toward 30+).

### Task C — Hermetic contract tests  *(delegate to `test-author` subagent)*
New file, e.g. `gui/sidecar/tests/test_codehome_app_contract.py`. Against the
**real registry** (`app_registry.scan()` / `get_all()`), assert:
- **No malformed manifests:** every `app.json` under `~/Codehome` (same
  scan/skip rules as `_find_app_jsons`) parses and has a non-empty `id`.
  (Regression guard for #1.)
- **Every manageable app has a resolvable launch definition:** either a
  non-empty `start_command` **or** a launch config, such that resolving the
  launch plan does **not** raise (`_resolve_command` for legacy;
  `build_launch_command` for configured). Exempt apps are skipped. (Guards #2.)
- **No duplicate `expected_port`** across registered apps. (Guards #3.)
- **`manageable` flag correctness:** exempt IDs → `False`, all others → `True`;
  the API echoes it.
- Prefer **parametrizing over the real app list** so a failure names the exact
  offending app. Keep it hermetic — **no subprocess launches in this file.**

### Task D — Live smoke tests  *(delegate to `test-author` subagent)*
New file, e.g. `gui/sidecar/tests/test_codehome_app_live.py`, every test
`@pytest.mark.live` (register the marker in `pytest.ini`/`pyproject.toml` and
add `-m "not live"` to the default run so the normal suite skips it).
- **Parametrize over every manageable app.** For each: `manager.start(id)` →
  poll the success ladder (§3) up to a per-app timeout → assert healthy →
  `finally: manager.stop(id)` → assert it actually died (pids gone, port freed).
- **Run sequentially** (no concurrency) to avoid port storms; always clean up in
  `finally` even on failure; free any squatted port.
- Emit a **per-app pass/fail summary** (the diagnostic Tony actually wants: which
  apps don't start). Per-app parametrization already gives per-app red/green.
- This layer is what catches #5 (present-but-broken commands / missing deps).

### Task E — Panel gating  *(optional follow-up; do only if budget allows)*
Locate the Hub panel component (the "CODEHOME HUB" view with the New Project /
start-stop controls — search `gui/desktop/src/` for the app list + start/stop
buttons) and **disable/hide start-stop for `manageable === false`** apps so the
UI stops offering dead buttons. Follow `docs/gui-frontend-conventions.md`
(theme tokens, no undefined CSS vars). If you touch/rename any route, update
`gui/desktop/src/components/HubApiExplorer.jsx` (API-registration rule).

---

## 5. Process rules (from `CLAUDE.md` — non-negotiable)

- **Test authorship is delegated to the `test-author` subagent** (Tasks C & D).
  It writes tests only, never production code, and reports suspicions instead of
  coding around them. If a subagent hits the spend limit or can't spawn on this
  surface, fall back to inline authoring and note it in the commit/CONTINUATION.
- **The subagent's green run is NOT verification.** You (supervising session)
  must (a) read the test diff and (b) independently re-run the **full** suite
  before commit.
- **`security-verifier` is NOT required here** — this work touches
  `app_registry.py`, `process_manager.py`, `api_apps.py`, and `app.json`
  manifests, none of which are the security spine (`_harness.py`, `_policy.py`,
  `core/constitution.py`, `constitution.yaml` approval blocks,
  `osa_system_mcp.py` dispatch). **If your solution ends up touching any of
  those, `security-verifier` becomes mandatory before commit.**
- **Docs in the same change:** update `docs/CHANGELOG.md` and `docs/roadmap.md`;
  add any new term to `docs/GLOSSARY.md` (and mirror to Brain2). If you change
  ports, `hub/docs/PORT_ASSIGNMENTS.md` must reflect it.
- **Commit AND push at session end** (Tony's standing rule). Never leave finished
  work uncommitted. Split into logical commits (fixes vs. tests) if cleaner.
- If you approach a session/usage limit, checkpoint to `docs/CONTINUATION.md`
  (what's done, in-progress file+line, exact next steps, verify commands) and
  leave the tree building.

---

## 6. Guardrails

- **MySQL only.** New tests run against `agenticos_test` via
  `gui/sidecar/tests/conftest.py` fixtures — never in-memory SQLite. Use a fresh
  non-singleton `_ProcessManager()` per test (see `fresh_manager` in
  test_phase13c.py) so shared `_procs` state doesn't leak.
- **Never start `agenticos`** in a live test — it's the sidecar you're running
  in. It's exempt; the parametrization must skip it.
- **Live tests must be hermetic in cleanup:** kill process groups, reap
  children, free ports in `finally`. No strays left after the run.
- **Don't touch TCC folders** (`~/Downloads`, `~/Desktop`, `~/Documents`) from
  the shell — repo, `~/Brain2`, `/tmp` are safe.
- **Verify edits persisted** — read a region back after editing a large file; a
  tool reporting success is not proof the change is on disk.

---

## 7. Definition of done

- [ ] Re-scan confirms **zero malformed manifests**; all intended apps register.
- [ ] `brain-scanner` on its own registered port; **no duplicate ports**.
- [ ] `manageable` flag on `/api/apps` + `/api/apps/{id}`; `agenticos`/`hub`
      exempt with reasons.
- [ ] **Hermetic contract test** (Task C) green and part of the default suite.
- [ ] **Live smoke test** (Task D) present, marker-gated, and its manual `-m live`
      run produces a per-app pass/fail table; every non-exempt app that *should*
      start does (fix or file any that don't).
- [ ] Full default suite re-run green by the supervising session (was ~707).
- [ ] Docs (CHANGELOG, roadmap, glossary, port ledger) updated in the same change.
- [ ] Committed **and pushed**.

---

## 8. First move

Read §1 files, re-run the §2 scan to get the current exact list of malformed
manifests + ports, then restate the plan (exempt set, the 4 manifests you'll
fix, brain-scanner's new port) back before editing. Then Task A → B → C → D
→ (E if budget), delegating C & D to `test-author`.
