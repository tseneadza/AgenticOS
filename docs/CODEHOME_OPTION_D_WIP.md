# Codehome App-Launch — Option D (WIP handoff)

**State:** Option D core IMPLEMENTED + PROVEN LIVE, NOT yet committed (8 tests red).
Finish in Claude Code (test-author + security-verifier available there).

## What Option D is
Launch the 13 apps that ship a `start.sh` by **running the script directly**
(`bash start.sh`) instead of parsing it into granular steps; keep the registry
command for the 12 that have no `start.sh`. The scripts self-bootstrap
(venv + deps) and manage their own child procs; `process_manager` already
injects `PORT`, waits for the port, and group-kills on stop
(`start_new_session=True` + `os.killpg`).

## Code change (DONE, in working tree — uncommitted)
`gui/sidecar/scripts/backfill_launch_config.py`, in `build_plan` per-app loop:
when `start.sh` exists, route through
`_plan_from_registry(app, project, ["bash","start.sh"], intended)`, set
`cp.source="start.sh"`, note "Option D", `continue` — instead of
`parse_start_sh` + `_plan_from_steps`. Backup at `/tmp/backfill.bak.py`.

## Data (DONE)
Deleted + re-backfilled the 13 start.sh apps → each now one `bash start.sh`
step. (agentic, ai-voice, astro-physics-hub, battester, calculator,
dreamcatcher, learner, mazegame, physics, queensgame, shuffle, startrek-facts,
worldwise.)

## Proven
`calculator` via `bash start.sh`: POST start → `:8094/docs` HTTP 200 →
POST stop → `:8094` free (clean process-group kill). Full chain works.

## TO FINISH (Claude Code)
1. **Rewrite 8 Phase 13b tests** (they assert the removed parse behavior):
   in `gui/sidecar/tests/test_phase13b.py` — TestTemplating
   (worldwise multi-step, venv templating, source-activate cases),
   TestCollisions (foreign-port literal), TestApplyEndToEnd
   (extra-port alloc, preferred-port retemplate, second_run_inserts_zero=2).
   New intent: a start.sh app yields ONE `bash start.sh` step; multi-step
   port-allocation premises are gone — repurpose or drop. Use `test-author`.
2. **`security-verifier`** on the backfill change (it shapes spawn argv).
3. **Verify the 13 live**: start → health → stop each (non-blocking, generous
   first-run timeout since self-bootstrap does pip/npm install on first run).
   NOTE first-run install may exceed the 30s port-wait default — consider a
   generous `timeout_seconds` for start.sh steps.
4. **Port reconciliation**: dreamcatcher (5111) and worldwise (5173/8000)
   HARDCODE ports and ignore `$PORT` → ledger port must match the port the app
   actually binds, or wait_for_port/health-check target the hardcoded port.
5. **12 registry apps** (blackjack `python3 app.py`, chem, keno, ufc, weather,
   solar-system, songtrans, template-app, igotyou/projmanager/taste-dees=npm,
   jupyter-notebook): verify each launches; add venv/deps or fix command as
   needed. `learner` has PORT in start.sh but was flagged missing earlier —
   double-check its start.sh.
6. Full suite green → update CONTINUATION.md + CHANGELOG → commit AND push.

## Prereq
MySQL must stay up (`:3306`, DMG install /usr/local/mysql). Sidecar :5130.

## BUG (found via calculator Stop) — Stop can't reap untracked orphans
`process_manager.stop_app` only kills processes it TRACKS. If a start.sh child
outlives its `bash start.sh` parent (reparented to PID 1) or the sidecar
restarts and loses in-memory tracking, the app keeps serving its port but shows
`pid: None, managed: False, running: True` (running is inferred from a live
port probe). Stop then returns `killed_pids: []` and the orphan survives.

**Fix:** in stop_app, when there is no tracked pid/pgid but the app's port is
live (`port_live` / port probe), reap the port owner:
`lsof -ti:<port>` → SIGTERM group → grace → SIGKILL. (process_manager already
has orphan-group handling for the pidfile case ~L577-583; extend it to the
port-probe case.) Security-adjacent — run `security-verifier`. Add a test:
untracked process on the port → stop_app kills it.

Interim manual clear: `lsof -ti:<port> | xargs kill`.

## UPDATE — Stop port-sweep fix IMPLEMENTED (uncommitted)
`core/process_manager.py` `stop()`: after the in-memory + DB pid sweeps, added
a port sweep — `app_registry.get(app_id)["expected_port"]`; if `_port_in_use`,
call `_kill_port(port)` (existing trusted helper). Backup: /tmp/process_manager.bak.py.
- Syntax-validated (ast.parse). NOT yet live-verified: requires a **sidecar
  restart** (app relaunch) to load; the running sidecar still has old stop().
- After restart, verify: start calculator → relaunch sidecar (orphans it) →
  Stop → :8094 freed. Also test a multi-proc app (worldwise: frontend+backend
  ports) — expected_port only covers one; may need to sweep all ledger ports
  for the app, not just expected_port.
- security-verifier + unit test (untracked proc on port → stop reaps) before commit.

## VERIFIED — Stop port-sweep works (live, on 22:05 source sidecar)
Test: start calculator (Option D) → kill parent (orphan on :8094,
managed:False/pid:None) → Stop → :8094 FREED. Also: planted untracked
http.server on :8094 → Stop reaped it. Fix confirmed functional.
Polish added: port-sweep now captures orphan pids (lsof) and appends to
killed_pids so the API/UI reflect the reap (was []). Needs next sidecar
restart to load; the already-running sidecar reaps correctly regardless.
Remaining: multi-port apps (worldwise) — sweep ALL ledger ports for the app,
not just expected_port.

## ROOT CAUSE of "Stop button doesn't work" — WRONG ENDPOINT (fixed + verified)
The UI HubPanel (App.jsx:400, `post('/api/panels/hub/{id}/{action}')`) — NOT
ProjectsView — is what's rendered. Its Stop hit `/api/panels/hub/{id}/stop` →
`panels.hub_app_action` → `hub_mcp.hub_app_action` → `_post_json('/api/cards/
{id}/{action}')`, i.e. it proxied to the RETIRED Hub Go server on :8085. Dead
server → 502 Bad Gateway on every stop. (The panel also auto-launches the hub
binary via /api/panels/hub/start, causing the flapping/"respawn".)
My /api/apps/{id}/stop port-sweep fix was on the correct-but-unused path.

FIX (app.py `panel_hub_action`): made it `async` and route to the native
`core.process_manager.manager` .start/.stop/.restart — same as
/api/apps/{id}/{action}. Now the Hub panel and Projects panel share one
system. Verified live: start+stop via /api/panels/hub/calculator/* → 200,
:8094 freed, stays stopped, no respawn.

NOTE: sidecar was restarted from shell (sane PATH) to load app.py +
process_manager edits and verify. All fixes live in source, so they persist on
the next Tauri app relaunch (canonical env). Three uncommitted changes now:
backfill_launch_config.py (Option D), process_manager.py (stop port-sweep),
app.py (panel_hub_action native routing). Backups: /tmp/*.bak.py.
Follow-up: hub_mcp.hub_app_action still proxies to :8085 — anything else using
it (hub_agent) will 502 too; migrate it to native as well.

## shuffle (Card Shuffler) — GUI app + broken venv (fixed)
Two issues: (1) venv corrupted by a Homebrew python@3.12 upgrade
(_posixsubprocess missing → pip crashed → start.sh exit 1). Fixed:
rm -rf Cards/shuffle/venv && python3 -m venv venv && pip install pillow.
(2) shuffle.py is a pure tkinter GUI app (5 tkinter refs, 0 web-server), but
registered type:both expected_port:5108 → plan had wait_for_port:True on a port
it never binds → 30s timeout → "not starting". Fixed: set app_commands
wait_for_port=False for shuffle (verified: /api/panels/hub/shuffle/start → 200,
running, GUI launches; stop clean).

CAVEATS / PATTERN (address in finish):
- The wait_for_port=False was a direct app_commands edit. A re-backfill of
  shuffle would RESET it to True (expected_port is set). Proper fix: mark GUI
  apps as portless in their app.json/registration so the backfill emits
  wait_for_port=False (add a launch mode: "gui"/"desktop" — no port, no health).
- Other apps may be GUI too (check mazegame and any 'games'). Same treatment.
- start.sh runs `pip install` every start (no stamp) — slow-ish but works.
