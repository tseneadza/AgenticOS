# Agentic OS — Personal Agentic Orchestration Layer

A locally-running orchestration layer that executes multi-step agent
workflows against the Brain2 vault, the Codehome Hub, and the Claude API —
config-driven, constitution-constrained, with human-in-the-loop approval
gates. Product spec: `[[Agentic OS - Full PRD]]` in Brain2.

**Status: Phase 2 (Tauri Desktop GUI) core complete** — see
[docs/roadmap.md](docs/roadmap.md).

```bash
# Desktop GUI (Phase 2)
./.venv/bin/python -m gui.sidecar          # FastAPI sidecar on :5130
cd gui/desktop && npm run tauri dev        # Tauri v2 + React app
```

## Quick start

```bash
cd ~/Codehome/AgenticOS
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# optional — AI-composed briefs instead of template mode:
export ANTHROPIC_API_KEY=sk-ant-...

./.venv/bin/python main.py run morning-briefing
```

The brief lands in `Brain2/04 - Reflections/YYYY-MM-DD - Morning Briefing.md`.

Recommended alias for `~/.zshrc`:

```bash
alias agentic-os='~/Codehome/AgenticOS/.venv/bin/python ~/Codehome/AgenticOS/main.py'
```

```bash
agentic-os list        # available workflows
agentic-os run <name>  # execute a workflow
agentic-os history     # recent runs
```

## Documentation

Full docs live in [`docs/`](docs/README.md):

- [Usage guide](docs/usage.md) — setup, CLI, the morning briefing, troubleshooting
- [Architecture](docs/architecture.md) — components, data flow, key decisions
- [Workflows reference](docs/workflows.md) — YAML format, adding workflows and agent actions
- [Constitution](docs/constitution.md) — the safety model and how to tune it
- [State & memory](docs/state-and-memory.md) — SQLite, checkpoints, recovery
- [Roadmap](docs/roadmap.md) — phase status • [Changelog](docs/CHANGELOG.md) — what changed, when

**Documentation policy:** docs are updated in the same change that alters
behavior, with a dated [CHANGELOG.md](docs/CHANGELOG.md) entry. Details in
[docs/README.md](docs/README.md).

## Layout

```
main.py                  CLI entry point
config/                  workflows.yaml · constitution.yaml · settings.yaml
core/                    orchestrator · constitution enforcement · memory
agents/                  brain2 · hub · briefing
tools/                   guarded filesystem ops (MCP stdio client)
gui/sidecar/             FastAPI sidecar — panels API + AG-UI WebSocket (:5130)
gui/desktop/             Tauri v2 + React dashboard (six panels)
docs/                    documentation (start at docs/README.md)
data/                    state.db (gitignored)
gui/mockups/             design mockups that informed the Phase 2 GUI
```
