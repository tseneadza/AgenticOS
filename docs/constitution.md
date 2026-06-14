# The Agent Constitution

The safety model. Defined in `config/constitution.yaml`, enforced by
`core/constitution.py` at the tool-call boundary. **Enforcement, not
advisory** (PRD TR-07): a violation raises and halts the run — exit code 2.

## What is enforced, where

| Constraint | Config key | Enforced in | Behavior |
|------------|-----------|-------------|----------|
| Blocked operations | `blocked:` | `guard()` — substring match on the operation payload | Immediate `ConstitutionViolation`; run halts |
| Approval-gated action types | `approval_required:` | `guard()` — raises `ApprovalRequired` unless caller passes `approved=True` | Caller must obtain human approval first |
| Write allowlist | `write_allowlist:` | `guard_write_path()` on every `write_file` / `delete_file` | Writes outside listed roots halt the run |
| Token budget | `limits.max_tokens_per_workflow` | Orchestrator, after each step | Run halts when cumulative tokens exceed budget |
| File-write cap | `limits.max_files_written_per_run` | `filesystem_tool.write_file` counter | Run halts at the cap |
| Daily cost cap | `limits.max_cost_per_day_usd` | Two places: `briefing_agent` gates **before** each API call (today's spend already over cap → no call is made); orchestrator re-checks after any cost-incurring step | Run halts; free (template-mode) runs are never blocked |

## Current configuration (summary)

- **Blocked anywhere in a payload:** `rm -rf`, `DROP TABLE`, `mkfs`, `> /dev/`
- **Approval required:** `file_delete`, `email_send`, `api_call_external`
  (non-localhost), `git_push`, `hub_stop_all`
- **Write allowlist:** the Brain2 vault and `AgenticOS/data/`
- **Limits:** 100k tokens/workflow, 50 files written/run

The YAML is the source of truth — check `config/constitution.yaml` for
current values; this table is a convenience summary.

## How the pieces relate

Two distinct approval mechanisms exist, and they compose:

1. **Workflow-level HITL** (`requires_approval: true` on a step) — pauses
   the *whole step* via LangGraph `interrupt()` and asks the human y/N.
   Use for steps whose entire purpose is consequential (e.g. archiving
   originals after processing).
2. **Action-type gates** (`approval_required` in the constitution) — guard
   specific *operation categories* inside any action. An action calling
   `delete_file()` without `approved=True` raises `ApprovalRequired`
   regardless of what the workflow YAML says. Belt and suspenders: even a
   misconfigured workflow can't silently delete.

Localhost calls (the Codehome Hub) are deliberately *not* treated as
`api_call_external` — the gate is for leaving the machine.

## Modifying the constitution

Edit `config/constitution.yaml`; it's read fresh at each run. No code
changes needed for: new blocked patterns, new approval-gated action types,
changed limits, added allowlist roots.

Code changes ARE needed when introducing a brand-new *enforcement
mechanism* (e.g. per-domain network rules) — add it to
`core/constitution.py` and document it here.

When you change the constitution: update the summary above and add a
[CHANGELOG.md](CHANGELOG.md) entry. Constitution changes are exactly the
kind of thing future-you wants a dated record of.

## Known limitations (honest list)

- Substring matching for `blocked` is blunt — it can false-positive (a note
  *about* `rm -rf` being written to the vault would be blocked) and can be
  bypassed by obfuscation. Acceptable for Phase 1 where all code paths are
  first-party; revisit before agents execute arbitrary shell (Phase 3's
  Prempti-style intercept layer is the real answer).
- Cost figures come from the pricing table in `config/settings.yaml` — keep it
  in sync with https://www.anthropic.com/pricing. Unknown models are billed
  internally at the most expensive listed rates (conservative by design).
- `tools:` lists in workflow YAML are documentation, not a capability
  sandbox. Actions can technically import anything; the boundary is the
  guarded tool layer plus code review.
