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
  `OSA_SYSTEM`. As of 2026-07-12 the FULL fs + messages set is wired into OSA
  (21 tools). The two-turn confirm has real model-behavior pitfalls — read
  `osa-gated-confirm` BEFORE touching destructive-tool wiring or the confirm flow.

## Guard semantics (memorize)

| Policy decision | In-process behavior | Over MCP (dispatch) |
|---|---|---|
| allow | runs | runs |
| approve | raises `ApprovalRequired` (pass `approved=True` after HITL yes) | `{"needs_approval": true}` error — external clients CANNOT self-approve; `dispatch` strips any client-supplied `approved` arg |
| deny (denylist hit) | raises `ConstitutionViolation` — `approved=True` does NOT override | `{"blocked": true}` error |

Strict mode: `auto=True` capabilities run; `macos.run_command` runs only if
the command matches the terminal allowlist (exact or word-boundary prefix —
`ls -la` matches, `lsof` does NOT); everything else approves.

**Effect mode (LIVE since 15e, `system_mcp.mode: effect`).** Reads auto-run;
mutate/irreversible gate. For `macos.run_command` the ladder is: denylist
(always deny, wins first) → allowlist (allow) → **effect classifier** →
approve. Strict mode NEVER consults the classifier (its non-allowlisted path
still approves), so strict behavior is unchanged.

### Effect classifier (`_policy.classify_command`, 15e)

A PURE, fail-closed heuristic — **no model call**. Returns `"read"` ONLY when
every pipeline segment's leading token is a code-reviewed read-only binary
(`READ_ONLY_VERBS`) or a read-only `git` subcommand, AND no mutating shell
feature is present. Everything else → `"unknown"` → gate. The bias is
deliberate: over-gating a read (needs approval) is fine; auto-running a
mutate is not.

- **Gate triggers (any → not read):** redirection (`>` `>>` `2>` `&>` `<`),
  command/process substitution (`$(` backtick), background `&`, chaining
  (`;` `&&` `||`) or a pipe where any segment isn't a read verb,
  env-assignment prefix (`FOO=bar cmd`), unbalanced quotes.
- **Deliberately EXCLUDED from the read set (fail-closed):** `sed`/`awk`
  (`-i`/`system()` can write), `tee`, `xargs`, network tools; `env` with
  args, `find` with `-exec`/`-delete`, `sort -o`, and non-read `git`
  subcommands are rejected per-verb.
- **git is subcommand-aware:** a bare `git` is not read; `status/log/diff/
  show/blame/...` are read; `config` needs `--get`/`--list`; `branch` reads
  only when listing (no operand/write flag); `remote` only bare/`show`.
- **Known gap (flagged 15e):** the allowlist prefix match runs BEFORE the
  classifier, so `ls && rm x` rides the `ls` prefix and allows in BOTH modes.
  Tightening it is a strict-mode behavior change → owner's call, not yet done.

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

## Messages domain (15c — COMPLETE: reads + send)

`tools/system/messages_mcp.py` — `read_thread` / `search_messages` /
`list_recent_chats` read `chat.db` read-only (`effect=read`, `auto=True`). The
`db_path` is CONFIG (`system_mcp.messages.db_path`), NEVER a caller arg — an
MCP client cannot repoint the reader. Reading needs **Full Disk Access**.
`attributedBody` is decoded by a deserialization-free printable scan (never
`NSKeyedUnarchiver`).

**SEND (shipped 2026-07-12, spike-validated live first):**

- `messages.send_message(to, text)` — `effect=irreversible`, gated always.
  First param = the recipient (payload rule). iMessage-first, SMS fallback.
  Success means "queued to Messages.app" — delivery is async and NOT verified.
- `messages.resolve_contact(name)` — read/auto; Contacts.app lookup, name →
  handles (max 10 people). Needs Automation permission for Contacts.
- **Handles-only rule:** `send_message` REJECTS contact names (points to
  `resolve_contact`). Reason: the guard's approval payload is the FIRST param,
  so the human must confirm the REAL handle — never an unresolved alias.
  Resolution is deliberately a separate read capability, not a body step.
- **AppleScript injection defense:** user strings ride `osascript` ARGV
  (`on run argv`, invoked as `osascript -e SCRIPT -- <args>`), never
  interpolated into script source. Verified live: `--` is consumed by option
  parsing; quotes and `-e` inside the text are inert. Keep this pattern for
  ALL AppleScript capabilities (15d mail included).
- **Pre-launch rule (-600, live-found 2026-07-12):** from the sidecar's
  background context, `tell application` can ATTACH to a running app but
  cannot LAUNCH one (`error -600: Application isn't running`). Every
  AppleScript capability must pre-launch its target app first — `_osascript`
  takes `app="Messages"|"Contacts"|…` and runs `open -ga <App>` (background,
  LaunchServices, works from background contexts) with a 1s settle. Reuse
  the parameter for every new AppleScript domain; never call `osascript`
  bare against an app that might be closed.
- **Spike findings (design §5.3 answered):** the modern
  `participant <handle> of <account>` + `send` syntax is reliable; the legacy
  `buddy of service` form is avoided. Participant resolution is LAZY — a
  garbage handle "resolves" without error, so AppleScript will NOT validate
  recipients; validate handle shape yourself and treat send-time errors as
  failure. Both iMessage and SMS accounts are enabled on this Mac (Text
  Message Forwarding), making the fallback real.

- **Denylist scoping (15c):** the terminal denylist applies ONLY to
  `macos.run_command` — its patterns are shell fragments, so a message search
  for "sudo" is no longer falsely denied. fs safety is root-scoping, not the
  denylist.
- **Read posture (Tony, 2026-07-12):** message reads stay AUTO (no approval)
  even over stdio. `resolve_contact` inherits this posture (external clients
  can enumerate contacts without approval) — flagged in the 15c security
  review; revisit BOTH together if the posture ever tightens.

## Mail domain (15d — COMPLETE: reads + send/reply)

`tools/system/mail_mcp.py` — AppleScript → Mail.app (transport locked by Tony
2026-07-13; no IMAP, no stored credentials). Reuses the 15c rules verbatim:
argv-after-`--`, `open -ga Mail` pre-launch, account is CONFIG
(`system_mcp.mail.account`) never a caller arg.

- **Reads (auto, matching the messages posture):** `list_mailboxes`,
  `list_recent`, `search_mail` (subject/sender only), `read_message`.
- **Spike law (2026-07-13): headers are fast; `content of <message>` can
  BLOCK indefinitely** when bodies aren't downloaded locally (iCloud
  optimize-storage). `read_message` therefore makes TWO osascript calls —
  headers (reliable) then body behind `mail.body_timeout_s` — and returns
  headers + `body_note` on timeout. Never fold body fetch into a header
  script; never raise the body timeout to "fix" missing bodies. The disk
  `.emlx` path is an FDA-blocked 15e candidate.
- **Mailbox index order is NOT guaranteed** — `list_recent` compares the
  dates at both ends and walks from the newest end. Don't assume message 1
  is newest.
- **Sends (irreversible, gated):** `send_mail(to, subject, body)` — first
  param is the recipient (payload rule), email-shape validated.
  `reply(to, message_id, body)` — first param is the sender address the
  human confirms; the script constructs the reply (`reply m without opening
  window` — Mail sets the recipient itself), reads back the ACTUAL
  recipient, and on mismatch deletes the draft and returns a MISMATCH
  marker the capability turns into `ConstitutionViolation`. Approval can
  never redirect a reply. Fail-closed: an unreadable recipient counts as a
  mismatch.
- **Field protocol:** list/search scripts emit `id␟subject␟sender␟date`
  using the ASCII unit separator (0x1f). Header fields are ATTACKER
  CONTROLLED (incoming mail); the parser drops rows with non-numeric ids
  (linefeed-forgery defense) and listed senders are never verified identity
  — the reply re-check and the send confirm are the real backstops.
- **Cold-launch settle rule (live-found 2026-07-13):** a send fired into a
  freshly-launched, still-syncing Mail was DELIVERED TWICE (+ draft residue);
  warm Mail was clean. `_osascript` pgrep-checks Mail first — warm calls
  never sleep, cold launches settle 1s (reads) / `_COLD_SETTLE_SEND_S`=6s
  (sends). Never remove the pgrep check or shrink the send settle; extend
  this rule to any future AppleScript domain that performs irreversible acts.
- Both send paths have WS GraphInterrupt-propagation tests
  (`test_phase15d_mail_mcp.py`) — keep them when touching the toolbox bridge.

## Claude Desktop / Claude Code registration

```json
"osa-system": {
  "command": "/Users/tonyseneadza/Codehome/AgenticOS/.venv/bin/python",
  "args": ["-m", "tools.osa_system_mcp"],
  "cwd": "/Users/tonyseneadza/Codehome/AgenticOS"
}
```
Claude Code: `claude mcp add osa-system -- /Users/tonyseneadza/Codehome/AgenticOS/.venv/bin/python -m tools.osa_system_mcp` (run from the repo, or set cwd in `.mcp.json`).
