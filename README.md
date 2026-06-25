# Agentic OS — Personal Agentic Orchestration Layer

A locally-running orchestration layer that executes multi-step agent
workflows against the Brain2 vault, the Codehome Hub, and the Claude API —
config-driven, constitution-constrained, with human-in-the-loop approval
gates. Product spec: `[[Agentic OS - Full PRD]]` in Brain2.

**Status: Phases 1–8 complete; Phase 10 (governing agent) code-complete and in
live smoke test.** Core orchestration, Tauri desktop GUI, navigation shell,
shell integration, Brain2 workflow agents, Codehome Hub integration, expandable
panels + native menu bar, and the dashboard workspace are all in place. Phase 10
adds a unified local/cloud LLM layer and a natural-language **governing agent**
that operates the OS through guarded tools (see the Agent dashboard below).
Phase 9 (Hub absorption) is the remaining build. See
[docs/roadmap.md](docs/roadmap.md).

```bash
# Desktop app (sidecar auto-starts with the app)
cd gui/desktop && npm run tauri dev        # Tauri v2 + React app
# or run the sidecar on its own:
./.venv/bin/python -m gui.sidecar          # FastAPI sidecar on :5130
```

## What it does

- **Orchestrates workflows** — LangGraph executes multi-step, config-driven
  workflows (`config/workflows.yaml`) with MySQL checkpointing
  (`langgraph-checkpoint-mysql`) for recoverable runs.
- **Stays within guardrails** — every action passes through the Constitution
  (`config/constitution.yaml`): blocked-pattern checks, allowlists, and
  token/cost budgets, with human-in-the-loop approval gates.
- **Works your Brain2 vault** — agents process raw notes, research learning
  notes, compose the morning briefing, and write session reports back into
  the vault.
- **Manages Codehome apps** — wraps the Codehome Hub as MCP tools and surfaces
  each app's agent-capability manifest and scripts.
- **Integrates with your shell** — a ZSH plugin streams directory changes and
  command context over a Unix socket; iTerm2 panes can be driven (and
  policy-checked) by agents.
- **Ships a desktop dashboard** — a Tauri v2 + React app with a registry of
  named dashboards, expandable panels, an interactive PTY terminal, and a
  native macOS menu bar.
- **Talks to a governing agent** — a unified LLM layer (`core/llm.py`) over
  cloud (Anthropic) and local (Ollama) models with a runtime model switch, and
  a LangChain/LangGraph governing agent (`agents/governor.py`) that runs
  workflows, calls registry tools, and authors config — every action routed
  through the same Constitution guard + approval queue.

## Desktop dashboards

The sidebar is a registry of dashboards (adding one = adding a registry entry;
the native View menu and ⌘1–6 shortcuts stay in sync):

- **SysOps** — the system-operations grid: System Health, Agent Activity, Keno
  Telemetry, Codehome Hub, Approval Queue, and an interactive Terminal. Any
  panel double-clicks to expand to the full frame.
- **Workflows** — a combined dashboard linking a Workflows panel (definitions,
  each expandable to its recent runs) and the live AG-UI Events feed. Click a
  workflow, run, or event to highlight the matching events across both panels.
- **Agent** — the governing-agent console (⌘7): chat the agent that operates the
  OS, with a model selector (local/cloud) + escalate-to-cloud toggle, a live
  tool-call trace, and inline approval prompts.
- **Web News · Scripts · Zsh Config Editor · Obsidian Viewer** — registered
  placeholders ("Coming Soon") that map to upcoming epics.

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

### Scheduling

`core/scheduler.py` generates and installs launchd plists (with an in-process
APScheduler fallback) so workflows like the morning briefing run on a schedule:

```bash
./.venv/bin/python -m core.scheduler install
```

## Documentation

Full docs live in [`docs/`](docs/README.md):

- [Usage guide](docs/usage.md) — setup, CLI, the morning briefing, troubleshooting
- [Architecture](docs/architecture.md) — components, data flow, key decisions
- [Workflows reference](docs/workflows.md) — YAML format, adding workflows and agent actions
- [Constitution](docs/constitution.md) — the safety model and how to tune it
- [State & memory](docs/state-and-memory.md) — MySQL (AgenticOS schema), checkpoints, recovery
- [Roadmap](docs/roadmap.md) — phase status • [Changelog](docs/CHANGELOG.md) — what changed, when

**Documentation policy:** docs are updated in the same change that alters
behavior, with a dated [CHANGELOG.md](docs/CHANGELOG.md) entry. Details in
[docs/README.md](docs/README.md).

## Layout

```
main.py                  CLI entry point
config/                  workflows.yaml · constitution.yaml · settings.yaml
core/                    orchestrator · constitution · memory · scheduler · socket server · tool registry · llm (unified provider layer)
agents/                  brain2 · briefing · hub · shell · governor (governing agent)
tools/                   guarded filesystem (MCP client) · hub_mcp · iterm2
shell/                   agentic-os.plugin.zsh — ZSH integration plugin
scripts/                 helper scripts (e.g. agentic-gui.sh)
gui/sidecar/             FastAPI sidecar — panels API, AG-UI WebSocket, PTY terminal, agent runner + /ws/agent (:5130)
gui/desktop/             Tauri v2 + React app — dashboard registry, expandable panels, native menu
gui/mockups/             design mockups that informed the GUI
docs/                    documentation (start at docs/README.md)
data/                    logs (run/checkpoint state lives in MySQL, schema AgenticOS)
```
