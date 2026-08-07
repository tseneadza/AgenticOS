# Phase: Codehome App-Launch Hardening — Kickoff

**Status:** in progress (kickoff). **Opened:** 2026-08-06.
**Origin:** [[2026-08-06 - Codehome App-Launch Hardening — Option D, Stop-Button Fix, Card Shuffler]]
**Live findings log:** `docs/CODEHOME_OPTION_D_WIP.md`.

## Why this phase exists
The Codehome panel could not reliably start or stop apps. The prior session
root-caused the whole chain and *implemented* the core fixes, but left them
uncommitted with 8 tests red. This phase finishes and hardens that work: get
the fixes committed on green, then verify the full 25-app fleet actually
launches and stops.

## What is already done (verified live, was uncommitted at kickoff)
| Change | File | State |
|--------|------|-------|
| **Option D** — a `start.sh` app launches via a single `bash start.sh` step instead of a parsed step list; the script self-manages venv/deps/child procs | `gui/sidecar/scripts/backfill_launch_config.py` | ✅ implemented + data re-backfilled (13 apps) |
| **Stop port-sweep** — `stop()` reaps orphaned port owners (`lsof`/`_kill_port`) the tracked-only stop missed | `core/process_manager.py` | ✅ implemented, live-verified |
| **Stop-button root cause** — `panel_hub_action` routed to the native process manager instead of proxying to the retired Hub Go server on :8085 (was 502) | `gui/sidecar/app.py` | ✅ implemented, live-verified |
| **Phase-13b test rewrite** — 8 tests re-authored for Option-D intent | `gui/sidecar/tests/test_phase13b.py` | ✅ green (2026-08-06) |

## Option D — the contract (what the tests now assert)
When an app ships a `start.sh`, `build_plan` emits **one** command:
`command="bash"`, `args=["start.sh"]`, `source="start.sh"`,
`working_directory="."`, `wait_for_port=bool(port_type)`. The backfill does
**not** parse the script, so for these apps there is:
- no interpreter/venv templating (venv is the script's own concern),
- no per-literal port allocation (only the app's `expected_port` ledger row),
- no script-internal port collision cross-check.

`parse_start_sh` still exists and is still unit-tested directly, but is no
longer wired into `build_plan`. **Debt:** it is now dead code in the plan path
— candidate for removal once Option D is proven across the fleet.

## TO FINISH (the phase backlog)
1. ✅ **Rewrite the 8 red Phase-13b tests** for Option-D intent. *(done)*
2. **`security-verifier`** on the backfill change — it shapes spawn argv.
3. **Live-verify the 13 `start.sh` apps**: start → health → stop each.
   Self-bootstrap does `pip`/`npm install` on first run; use a generous
   first-run `timeout_seconds` (exceeds the 30 s port-wait default).
   Apps: agentic, ai-voice, astro-physics-hub, battester, calculator,
   dreamcatcher, learner, mazegame, physics, queensgame, shuffle,
   startrek-facts, worldwise.
4. **Port reconciliation** — dreamcatcher (5111) and worldwise (5173/8000)
   hardcode ports and ignore `$PORT`; the ledger port must match the port the
   app actually binds, or `wait_for_port`/health-check must target the
   hardcoded port.
5. **12 registry apps** (no `start.sh`) — verify each launches; add venv/deps
   or fix the command as needed. blackjack, chem, keno, ufc, weather,
   solar-system, songtrans, template-app, igotyou/projmanager/taste-dees (npm),
   jupyter-notebook. Double-check `learner`'s start.sh (PORT present but was
   flagged missing).
6. **Suite green → CHANGELOG + roadmap + Brain2 → commit AND push.**

## Carried debt from the origin session
- **GUI/desktop launch mode.** shuffle (Card Shuffler) is a pure tkinter GUI
  app; its `wait_for_port=False` was set by a direct `app_commands` edit and a
  re-backfill would RESET it to `True` (because `expected_port` is set). Proper
  fix: mark GUI apps as portless in registration so the backfill emits
  `wait_for_port=False` (add a launch mode `"gui"`/`"desktop"` — no port, no
  health). Check mazegame and other games for the same shape.
- **`hub_mcp.hub_app_action` still proxies to :8085** — anything else using it
  (e.g. hub_agent) will also 502; migrate it to native.
- **Multi-port stop sweep** — the port-sweep reaps `expected_port` only; a
  multi-proc app (worldwise: frontend+backend) may leave the second port. Sweep
  all ledger ports for the app, not just `expected_port`.

## Acceptance criteria
- [ ] Full sidecar suite green *(except the pre-existing, unrelated
      `test_phase15d_mail_mcp.py` Mail-app env leaks)*.
- [ ] The 3 verified fixes + test rewrite committed and pushed.
- [ ] All 25 fleet apps: Start reaches a healthy state (or launches, for GUI
      apps) and Stop frees the port with no orphan survivors.
- [ ] Port ledger matches the port each app actually binds.
- [ ] CHANGELOG + roadmap updated; Brain2 progress log appended.

## Prereqs / environment
- MySQL up on :3306 (DMG install, `/usr/local/mysql`). Sidecar on :5130.
- Any Python change needs a **full sidecar restart** to load:
  `pkill -f "gui.sidecar"; lsof -ti:5130 | xargs kill -9; cd ~/Codehome/AgenticOS && .venv/bin/python -m gui.sidecar`.
