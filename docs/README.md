# Agentic OS — Documentation

Documentation for the inner workings of the Agentic OS and how to use it.
The product spec lives in Brain2: `[[Agentic OS - Full PRD]]`. These docs
cover the *implementation* — what's actually built, how it works, and how
to operate and extend it.

## Doc Map

| Doc | Read it when you want to... |
|-----|------------------------------|
| [usage.md](usage.md) | Set up, run workflows, use the CLI day-to-day |
| [architecture.md](architecture.md) | Understand the system design, components, and data flow |
| [workflows.md](workflows.md) | Write or modify a workflow, or add a new agent action |
| [constitution.md](constitution.md) | Understand or tune the safety model (blocked ops, approvals, limits) |
| [state-and-memory.md](state-and-memory.md) | Understand SQLite state, checkpoints, and run recovery |
| [roadmap.md](roadmap.md) | See phase status and what's coming next |
| [CHANGELOG.md](CHANGELOG.md) | See what changed and when |

New here? Read [usage.md](usage.md) first, then [architecture.md](architecture.md).

## Documentation Policy

**Docs are updated in the same change that alters behavior.** A code or
config change isn't done until the affected doc is updated. Concretely:

1. **Every change** gets a dated entry in [CHANGELOG.md](CHANGELOG.md).
2. **New/changed workflow or agent action** → update [workflows.md](workflows.md).
3. **New constraint, limit, or approval gate** → update [constitution.md](constitution.md).
4. **New component, dependency, or data flow** → update [architecture.md](architecture.md).
5. **New CLI command or flag** → update [usage.md](usage.md).
6. **Phase milestone reached** → update [roadmap.md](roadmap.md) and the
   Progress Log in the Brain2 project note (`[[Agentic OS]]`).

Outdated docs are worse than no docs. If a doc and the code disagree, the
code is the truth — fix the doc immediately and note it in the changelog.
