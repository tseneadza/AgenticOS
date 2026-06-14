# Usage Guide

How to set up and operate the Agentic OS from the command line.

## Setup (one time)

```bash
cd ~/Codehome/AgenticOS
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Add the alias to `~/.zshrc` so `agentic-os` works from anywhere:

```bash
alias agentic-os='~/Codehome/AgenticOS/.venv/bin/python ~/Codehome/AgenticOS/main.py'
```

### API key (optional, recommended)

Without `ANTHROPIC_API_KEY`, briefs are generated from a deterministic
template — useful for testing, costs nothing. With the key set, the
briefing agent composes the brief with Claude (model set in
`config/settings.yaml`).

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # add to ~/.zshrc, or source a .env
```

Note for scheduled runs (Phase 4): launchd jobs don't inherit your shell
environment. The key will need to be provided in the job's plist
`EnvironmentVariables` or read from a file — decide when wiring up
scheduling.

## Desktop GUI (Phase 2)

One command (alias in `~/.zshrc` → `scripts/agentic-gui.sh`):

```bash
agentic-gui            # kills any stale instances, starts sidecar + app
agentic-gui stop       # stop everything
agentic-gui status     # what's running
```

Start is always safe to rerun — it cleans up old processes (ports 5130 and
1420, plus the app binary) before launching. Logs land in `data/logs/`.

Manual equivalent, if you want the processes in your own terminals:

```bash
cd ~/Codehome/AgenticOS
./.venv/bin/python -m gui.sidecar      # sidecar on http://localhost:5130
cd gui/desktop && npm run tauri dev    # opens the Agentic OS window
```

The dashboard shows six panels: System Health, Agent Activity, Keno
Telemetry, Codehome Hub (with start/stop/restart), Approval Queue, and the
Terminal strip (live in Phase 3). Run workflows from the sidebar; steps
that require approval appear in the Approval Queue panel with Allow/Deny
buttons — the same HITL gate as the CLI prompt.

Useful endpoints while developing: `GET /api/health`, `GET /api/panels/*`,
`POST /api/workflows/{name}/run`, `ws://localhost:5130/ws/agui`.

Keno panel credentials come from env (`KENO_DB_HOST`, `KENO_DB_USER`,
`DP_PASSWORD`, `DB_NAME`) with the same defaults as `live_keno_fetcher.py`.

## Commands

### `agentic-os list`

Shows every workflow defined in `config/workflows.yaml`, with description
and schedule (schedules are informational until Phase 4 wires up launchd).

### `agentic-os run <workflow>`

Runs a workflow end-to-end. Example:

```bash
agentic-os run morning-briefing
```

What happens: each step in the workflow executes in order. Output is
printed per step. If a step is marked `requires_approval: true`, the run
**pauses** and prompts:

```
⏸  PAUSED — Approve step 'write_test_note' (brain2_agent.write_test_note)? [y/N]
>
```

Type `y` (or `yes` / `approve`) to continue; anything else denies the step
and halts the run. Try it safely with the demo workflow:

```bash
agentic-os run approval-demo
```

### `agentic-os history`

Shows the last 15 runs from the SQLite run log: timestamp, workflow,
status (`completed` / `failed` / `interrupted` / `running`), and tokens used.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Workflow completed |
| 2 | Halted by the constitution (blocked operation, budget exceeded, write outside allowlist) |
| 3 | A `requires_approval` step was denied by the user |

## The morning briefing

`agentic-os run morning-briefing` does four things:

1. **Reads Brain2** — project statuses from `01 - Projects/` frontmatter,
   count of unprocessed notes in `00 - Raw/`, open `- [ ]` tasks from `Tasks/`.
2. **Checks the Codehome Hub** — `GET localhost:8085/api/cards`. If the Hub
   is down, the brief just says so; the run doesn't fail.
3. **Composes the brief** — Claude API or template (see API key above).
4. **Writes it** to `Brain2/04 - Reflections/YYYY-MM-DD - Morning Briefing.md`.

Running it twice on the same day overwrites that day's brief.

## Troubleshooting

- **`Unknown workflow 'x'`** — check `agentic-os list`; the name must match
  a key under `workflows:` in `config/workflows.yaml`.
- **`⛔ HALTED by constitution`** — the run tripped a hard constraint. See
  [constitution.md](constitution.md) for what's enforced and how to adjust.
- **`Hub unreachable` in the brief** — the Codehome Hub isn't running on
  port 8085. Start it and re-run.
- **Brief says "template brief"** — `ANTHROPIC_API_KEY` isn't set in the
  shell that ran the command.
- **A run shows `running` forever in history** — the process was killed
  before it could record completion. Harmless; the run did not finish.
