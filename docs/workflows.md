# Workflows Reference

How to read, write, and extend workflows. Workflows live in
`config/workflows.yaml`; adding one there makes it immediately runnable —
no Python changes for workflows that compose existing agent actions.

## Anatomy of a workflow

```yaml
workflows:
  my-workflow:                      # name used in: agentic-os run my-workflow
    description: "One-line summary shown by `agentic-os list`"
    trigger:
      schedule: "0 7 * * 1-5"       # cron syntax — informational until Phase 4
      manual: true                  # runnable via the CLI
    steps:
      - id: unique_step_id          # key for this step's output in state
        agent: brain2_agent         # must exist in AGENT_REGISTRY
        action: read_focus_and_queue  # must exist in that agent's ACTIONS dict
        tools: [filesystem]         # documentation of intent (not enforced yet)
        model: default              # optional — model alias for AI steps
        inputs: [other_step_id]     # documentation of data deps (steps run in order)
        requires_approval: false    # true = pause for human y/N before executing
```

### Field reference

| Field | Required | Effect |
|-------|----------|--------|
| `id` | yes | Step's key in `state["outputs"]`. Later steps read prior output via `state["outputs"]["<id>"]`. |
| `agent` | yes | Module name in `core/orchestrator.AGENT_REGISTRY`. Unknown name fails fast at graph build with a clear error. |
| `action` | yes | Function name in that agent's `ACTIONS` dict. |
| `model` | no | Alias resolved through `config/settings.yaml` → `models:` (`default`, `fast`). Only used by AI-calling actions. |
| `requires_approval` | no | `true` pauses the run with a CLI prompt before the step executes. Denial halts the run (exit code 3). |
| `tools`, `inputs` | no | Currently documentation. Steps execute strictly in listed order, so data dependencies are satisfied by ordering. |
| `trigger.schedule` | no | Cron string. Stored but not acted on until Phase 4 (launchd wiring). |

## Existing workflows

### `morning-briefing`
`read_vault` → `check_hub` → `generate_brief` → `write_brief`.
Output: `Brain2/04 - Reflections/YYYY-MM-DD - Morning Briefing.md`.

### `approval-demo`
`read_vault` → `write_test_note` (approval-gated). Exists to exercise the
HITL pause; writes a throwaway note to `Brain2/06 - Archive/`.

## Existing agent actions

| Agent | Action | Reads | Writes/Calls |
|-------|--------|-------|--------------|
| `brain2_agent` | `read_focus_and_queue` | `01 - Projects/` frontmatter, `00 - Raw/` listing, `Tasks/` checkboxes | — |
| `brain2_agent` | `write_to_reflections` | `outputs.generate_brief.brief` | `04 - Reflections/<date> - Morning Briefing.md` |
| `brain2_agent` | `write_test_note` | — | `06 - Archive/agentic-os-approval-test.md` |
| `hub_agent` | `list_running_apps` | — | `GET localhost:8085/api/cards` (3s timeout, degrades gracefully) |
| `briefing_agent` | `compose_brief` | `outputs.read_vault`, `outputs.check_hub` | Claude API (or template fallback) |

## Adding a new agent action

1. Write a plain function in the relevant `agents/` module:

```python
def my_action(state: dict) -> dict:
    prior = state["outputs"]["some_earlier_step"]   # read upstream output
    ...
    return {"whatever": "you produced", "tokens_used": 0}
```

Contract: takes the state dict, returns a JSON-serializable dict. If it
spends Claude tokens, include `tokens_used` so the budget check works.
All disk writes must go through `tools.filesystem_tool.write_file`.

2. Register it in that module's `ACTIONS` dict.

3. Reference it from a workflow step. Done — the orchestrator picks it up
through `AGENT_REGISTRY`.

For a whole new agent module: create `agents/<name>_agent.py` with an
`ACTIONS` dict, then add one line to `AGENT_REGISTRY` in
`core/orchestrator.py`.

## Conventions

- Step ids are `snake_case`; workflow names are `kebab-case`.
- Keep actions side-effect-light: one action, one responsibility.
- Anything that writes outside the vault, deletes, emails, or calls a
  non-localhost API must route through the constitution's approval gates —
  see [constitution.md](constitution.md).
- **After adding/changing a workflow or action, update this doc** (tables
  above) and add a [CHANGELOG.md](CHANGELOG.md) entry.
