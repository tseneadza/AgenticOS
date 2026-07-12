---
name: osa-system-mcp
description: >
  Architecture and rules for the OSA System MCP (Phase 15) — the dual-mode,
  Constitution-guarded capability layer that gives OSA and Claude Desktop/Code
  governed access to Tony's Mac. Consult BEFORE adding, modifying, or
  debugging any capability in tools/system/, the stdio server
  tools/osa_system_mcp.py, or the system_mcp block in constitution.yaml.
  Triggers: "add a capability", "system MCP", "run_command", "15b/15c/15d/15e
  build", "why was my command denied/blocked", "wire a tool into OSA".
---

# OSA System MCP — harness, guard, and dual-mode rules

Design doc: `docs/PHASE15_OSA_SYSTEM_MCP.md` (locked 2026-07-10). This skill
is the operational distillation.

## The two load-bearing principles

1. **Dual-mode.** Every capability is a plain module-level Python function.
   OSA imports it in-process; `python -m tools.osa_system_mcp` serves the
   SAME function over one stdio MCP server for Claude Desktop/Code. Never
   build a capability that only works through the server.
2. **One guard, both doors.** The Constitution guard is applied by the
   `@capability` registration decorator in `tools/system/_harness.py` — at
   the capability layer, NOT in OSA's wrapper. It is structurally impossible
   to register an unguarded capability. Never bypass this by exporting the
   raw (pre-decoration) function.

## Adding a capability (the whole recipe)

```python
from tools.system._harness import capability

@capability(
    "domain.verb",            # MCP tool name — dot convention
    domain="macos",           # macos | fs | messages | mail
    effect="read",            # read | mutate | irreversible
    auto=True,                # True ONLY for benign reads/mutates (design §5)
    schema={"type": "object", "properties": {...}},
)
def verb(...) -> dict:
    """First docstring line becomes the MCP tool description."""
```

- Import the domain module in `tools/osa_system_mcp.py` (self-registers) —
  it then appears in `list_tools` automatically. No dispatch table to edit.
- Gated capabilities (auto=False / mutate / irreversible) also need an
  `approval_required` entry in `config/constitution.yaml` ONLY if OSA's
  legacy `_guarded` path touches them — the harness guard itself reads the
  `system_mcp` block, not `approval_required`. (The `macos.run_command`
  entry there is documentation-of-intent + belt-and-suspenders.)
- Wire into OSA: add a thin `OSAToolbox` method calling the capability via
  `self._run_capability(name, payload, callable)` — it bridges
  `ApprovalRequired` to the two-turn confirm and retries with
  `approved=True`. Register in `build_tools` specs + map the phrasing in
  `OSA_SYSTEM`.

## Guard semantics (memorize)

| Policy decision | In-process behavior | Over MCP (dispatch) |
|---|---|---|
| allow | runs | runs |
| approve | raises `ApprovalRequired` (pass `approved=True` after HITL yes) | `{"needs_approval": true}` error — external clients CANNOT self-approve; `dispatch` strips any client-supplied `approved` arg |
| deny (denylist hit) | raises `ConstitutionViolation` — `approved=True` does NOT override | `{"blocked": true}` error |

Strict mode (current): `auto=True` capabilities run; `macos.run_command`
runs only if the command matches the terminal allowlist (exact or
word-boundary prefix — `ls -la` matches, `lsof` does NOT); everything else
approves. Effect mode is a 15e migration — flip `system_mcp.mode` only then.

## Config

`config/constitution.yaml` → `system_mcp:` block. Defaults live in
`core/constitution.py` `DEFAULT_SYSTEM_MCP` with a TWO-LEVEL merge — a
partial YAML block keeps the default denylist. The allowlist is code
review: edits are versioned, never guessed at runtime.

## Testing rules (from 15a)

- Never touch the real terminal destructively — approved-path tests use
  `echo`/`date` only; iTerm2 (`run_in_pane`/`last_pane_lines`) is mocked.
- Inject a hermetic Constitution via `_harness.set_constitution(...)` in an
  autouse fixture; clear it on teardown.
- Registry↔list_tools parity test guards against schema-less registration.
- Test the MCP self-approval strip (`approved: true` in dispatch arguments
  must NOT bypass the gate).

## Payload rule (learned 15b — security-critical)

The guard's policy payload is the capability's **first parameter** —
captured by name from the function signature at registration, so it is
extracted whether the call is positional OR keyword (`dispatch` calls
`func(**arguments)`). Consequences when adding a capability:

- **The first parameter must be the side-effect payload** (the command,
  the path, the recipient). Never bury it in a later arg — the policy
  won't see it.
- Multi-path capabilities must enforce SECONDARY paths in the body with
  the same resolver (`fs.move`'s destination is the template — raise
  `ConstitutionViolation` so approval can't smuggle data out).
- Every new domain's test file needs a kwargs-form regression test
  (call `cap(param=malicious)` and assert it's gated) — the original 15a
  harness only saw positional payloads and keyword calls bypassed root
  scoping entirely.
- fs scoping: paths symlink-resolve BEFORE the root check; outside
  `allowed_roots` = hard deny both modes; `scratch_root` writes auto-run.

## Gotchas (learned 15a)

- **`hub_mcp.py`'s `_serve_mcp` is a broken reference** — it passes the
  Server into `stdio_server(...)`, which is not the SDK's signature. Use
  the pattern in `tools/osa_system_mcp.py` (`stdio_server() as (r, w)` →
  `server.run(...)`). Do NOT copy hub_mcp's server block.
- The guard fires BEFORE the function body — an input-validation error
  message in the body is unreachable for gated payloads unless policy
  special-cases it (empty run_command is special-cased to allow).
- `shell=True` is a locked decision (Tony, 2026-07-11) — do not "fix" it to
  an arg-list; the guard + allowlist + denylist are the mitigation.

## Messages domain (15c — read-only)

`tools/system/messages_mcp.py` — `read_thread` / `search_messages` /
`list_recent_chats` read `chat.db` read-only (`effect=read`, `auto=True`). The
`db_path` is CONFIG (`system_mcp.messages.db_path`), NEVER a caller arg — an
MCP client cannot repoint the reader. Reading needs **Full Disk Access**.
`attributedBody` is decoded by a deserialization-free printable scan (never
`NSKeyedUnarchiver`). SEND (AppleScript) is deferred — spike its reliability
first (design flags it flaky).

- **Denylist scoping (15c):** the terminal denylist applies ONLY to
  `macos.run_command` — its patterns are shell fragments, so a message search
  for "sudo" is no longer falsely denied. fs safety is root-scoping, not the
  denylist.
- **Read posture (Tony, 2026-07-12):** message reads stay AUTO (no approval)
  even over stdio. If you add a MORE sensitive read domain, revisit whether it
  should gate to `approve` instead of inheriting this.

## Claude Desktop / Claude Code registration

```json
"osa-system": {
  "command": "/Users/tonyseneadza/Codehome/AgenticOS/.venv/bin/python",
  "args": ["-m", "tools.osa_system_mcp"],
  "cwd": "/Users/tonyseneadza/Codehome/AgenticOS"
}
```
Claude Code: `claude mcp add osa-system -- /Users/tonyseneadza/Codehome/AgenticOS/.venv/bin/python -m tools.osa_system_mcp` (run from the repo, or set cwd in `.mcp.json`).
