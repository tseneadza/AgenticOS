# Agentic OS — agent instructions

## Session-budget rule (cost control)

Tony works on this project across Claude session windows to stay within
plan limits ("do the work when it's free"). All agents working in this
repo must follow this cycle:

1. **Work normally** while session capacity is available.
2. **Checkpoint before stopping.** If you are close to a session/usage
   limit (or asked to wrap up), stop starting new work and write a
   continuation note to `docs/CONTINUATION.md` containing: what was
   completed, what is in progress (file + line specifics), exact next
   steps, and any commands needed to verify.
3. **Never leave the repo broken** at a checkpoint — finish or revert the
   in-flight edit so the GUI builds and workflows run.
4. **On resume** (new session after reset), read `docs/CONTINUATION.md`
   first, do the work, then clear or update the note.
5. Prefer cheap verification (targeted greps, single builds) over broad
   re-exploration to conserve budget.

## Project conventions

- Phase numbering follows the **renumbered PRD** (`Brain2/01 - Projects/
  PRDs/Agentic OS - Full PRD.md`): 1 Core Orchestration, 2 Tauri GUI,
  3 GUI Navigation Shell (FR-36–39), 4 Shell Integration, 5 Brain2
  Workflow Agents, 6 Codehome Deep Integration. `docs/roadmap.md` must
  match this numbering.
- Docs policy: documentation updates land in the same change that alters
  behavior (`docs/CHANGELOG.md`, `docs/roadmap.md`).
- GUI design principle #7: **new paradigm = new nav link** — never add
  another always-on dashboard panel for a new interaction paradigm.
- Sidecar port 5130 is registered in `hub/docs/PORT_ASSIGNMENTS.md`
  (TR-10); register any new port before use.
