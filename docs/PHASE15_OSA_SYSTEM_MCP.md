# Phase 15 — OSA System MCP (local machine management)

**Status:** ✅ DESIGN COMPLETE · ⏳ implementation not started
**Date:** 2026-07-10
**One-liner:** A dual-mode MCP server that gives OSA — and, over stdio, Claude
Desktop / Claude Code — governed access to this Mac: time, system info,
terminal execution, filesystem, iMessage, and mail. Every capability is
guarded at the capability layer, so the same governance applies no matter who
calls it.

> This executes the four-domain MCP architecture already sketched in
> `PHASE14_OSA_ASSISTANT.md` (macOS / messages / mail / fs under an
> `osa_system_mcp.py` aggregator). It is numbered **Phase 15** as a standalone
> feature, but it is functionally OSA's system-access layer — renumber to a
> Phase 14 sub-series if preferred.

---

## 1. Goals / non-goals

**Goals**
- OSA can answer "what time is it?", "how's the machine doing?", and run a
  terminal command — safely — on this Mac.
- The *same* capabilities are reachable by Claude Desktop / Claude Code via one
  stdio MCP server (the "dual exposure" from the Phase 14 design).
- All machine-mutating power is governed by the existing Constitution, with a
  single guard that both OSA and external clients pass through.
- Everything executes locally; nothing about a capability call leaves the Mac
  except (optionally) the LLM's *decision* to call it.

**Non-goals**
- No new HTTP surface. The server is stdio (like `tools/hub_mcp.py`), so
  `PORT_ASSIGNMENTS.md` / `HubApiExplorer` / api-registry do **not** apply.
- No cloud relay, no remote control. This is a local machine tool.
- Not a sandbox/VM. Governance is policy + HITL approval, not isolation.

---

## 2. Locked decisions (interview, 2026-07-10)

1. **Consumer = Both, via dual-mode.** One plain Python function per
   capability. Imported in-process by OSA *and* served over a single stdio MCP
   server for Claude Desktop / Code. Local-first by construction.
2. **Governance lives in the capability layer, not the OSA wrapper.** If the
   guard sat only in `osa_agent`, an external Claude client hitting the MCP
   server would bypass it. The guard wraps each capability function — the same
   place `tools/iterm2_tool.py` already runs its Constitution check — so every
   caller is equally gated. **One guard, both doors.**
3. **Safety model: start strict → migrate to effect-based.** Open on an
   allowlist (safe commands auto-run; everything else halts to HITL approval).
   Once the allowlist + classifier are trusted, flip to effect classification
   (read / mutate / irreversible). Mode is a config flag.
4. **Terminal substrate = per-command.** `run_command(cmd, surface=…)` where
   `surface="pane"` routes to the existing `iterm2_tool.py` (visible, abortable)
   and `surface="subprocess"` runs headless with captured output. Both paths
   pass the same guard first.
5. **Scope = full suite, sequenced.** macOS + terminal (15a) → filesystem (15b)
   → iMessage (15c) → mail (15d) → harden + effect-migration (15e). iMessage and
   mail are separate phases because they need on-device macOS permission grants.

---

## 3. Architecture

### 3.1 The two principles

**Dual-mode** (proven by `hub_mcp.py`): each capability is a module-level
function, so OSA can `import` it directly (no MCP needed for the in-process
path), while the *same* module runs as a stdio MCP server via
`python -m tools.osa_system_mcp`. OSA calling a tool is a Python call; Claude
Desktop calling it is an MCP `call_tool` — both land on the identical function.

**Capability-layer guard**: the guard is applied by the registration decorator,
so it is impossible to register a capability that isn't governed. This is the
load-bearing safety decision — it is what makes "Both" safe.

### 3.2 Directory layout

```
tools/
  osa_system_mcp.py       # aggregator: imports domains, builds ONE stdio server
  system/
    __init__.py
    _harness.py           # registry + guard + safety ladder + substrate selector
    _policy.py            # safety-mode logic (strict|effect), allow/deny lookup
    macos_mcp.py          # get_time, system_info, notify, clipboard, open_app, run_command
    fs_mcp.py             # read/list/search (auto) · write/move/delete (gated)
    messages_mcp.py       # iMessage read (chat.db) + send (AppleScript) — 15c
    mail_mcp.py           # mail read/send — 15d
```

`_harness.py` is the heart. The four domain files are just capabilities plugged
into it. This groups the domains into a subpackage rather than flat `tools/`
files — a deliberate departure from `hub_mcp.py`'s flat layout because there are
five files that share the harness; flip to flat if preferred.

### 3.3 The harness (`_harness.py`)

Replaces `hub_mcp.py`'s hand-maintained `call_tool` if/elif chain with a
decorator-driven registry. Sketch of the interfaces (final shapes settled in
15a against the real `mcp` SDK imports in `hub_mcp.py`):

```python
# effect class drives the safety ladder
Effect = Literal["read", "mutate", "irreversible"]

@dataclass
class Capability:
    name: str            # MCP tool name, e.g. "macos.run_command"
    domain: str          # "macos" | "fs" | "messages" | "mail"
    effect: Effect
    func: Callable
    schema: dict         # JSON schema for MCP list_tools

REGISTRY: dict[str, Capability] = {}

def capability(name, domain, effect, schema):
    """Register a capability AND wrap it in the Constitution guard."""
    def deco(func):
        guarded = _guard(name, effect, func)   # guard applied HERE = capability layer
        REGISTRY[name] = Capability(name, domain, effect, guarded, schema)
        return guarded                          # OSA imports the guarded version too
    return deco
```

- `_guard(name, effect, func)` — before calling `func`, ask `_policy.evaluate()`
  what to do with this call:
  - **allow** → run it.
  - **approve** → raise the Constitution's `ApprovalRequired` (routes to the
    existing HITL approval queue / OSA's two-turn confirm).
  - **deny** → raise `ConstitutionViolation` (blocked pattern — never runs).
- The aggregator's `call_tool` becomes a one-liner:
  `cap = REGISTRY[name]; return _wrap_json(cap.func(**arguments))`.
- `list_tools` is generated from `REGISTRY[*].schema` — no hand-maintained list.

### 3.4 Aggregator / stdio server (`osa_system_mcp.py`)

Imports the four domain modules (their `@capability` decorators self-register on
import), then stands up **one** stdio server using the same `mcp` SDK primitives
`hub_mcp.py` already uses (`Server`, `stdio_server`, `TextContent`). Run with:

```bash
cd ~/Codehome/AgenticOS && python -m tools.osa_system_mcp
```

> **15a task 0:** read `hub_mcp.py`'s server setup (top imports + `_serve_mcp`)
> and reuse it verbatim so the framework matches exactly.

---

## 4. Safety model (detail)

### 4.1 The ladder

| Mode | Read | Mutate | Irreversible | Default for unknown |
|------|------|--------|--------------|---------------------|
| **strict** (start) | allow if allowlisted, else approve | approve | approve | **approve** |
| **effect** (target) | allow | approve | approve (strong confirm) | approve |

Denylist patterns are **always deny** in both modes. The only difference is what
happens to the vast middle: strict mode makes you approve almost everything;
effect mode auto-runs reads and only stops you on writes. You migrate by
flipping `system_mcp.mode` once trust is earned.

### 4.2 Config lives in `config/constitution.yaml`

New block (versioned, auditable — the allowlist is *code review*, not a runtime
guess):

```yaml
system_mcp:
  mode: strict                     # strict | effect
  terminal:
    allowlist:                     # auto-run in strict mode (prefix/exact rules)
      - date
      - uptime
      - whoami
      - "pwd"
      - "ls"
      - "df"
      - "git status"
      - "git log"
    denylist_patterns:             # ALWAYS deny (both modes)
      - "rm -rf"
      - "sudo"
      - "dd "
      - "mkfs"
      - "curl | sh"
      - "> /dev/"
      - ":(){"
      - "chmod 777 /"
  fs:
    allowed_roots:                 # reads/writes scoped to these
      - ~/Codehome
      - ~/Brain2
    scratch_root: ~/Codehome/AgenticOS/data/osa_scratch  # writes here auto-run
approval_required:                 # existing list — add the gated capabilities
  - macos.run_command
  - fs.write_file
  - fs.delete
  - fs.move
  - messages.send_message
  - mail.send_mail
```

### 4.3 Terminal execution

`macos.run_command(command, surface="subprocess", cwd=None, timeout=60)`:

- **guard first**, always (capability layer). The allowlist/denylist/effect
  logic decides allow/approve/deny before either surface runs.
- `surface="subprocess"` → guarded `subprocess.run(...)`, capture
  stdout/stderr/returncode. **Open 15a question:** `shell=True` (needed for
  pipes/globs, larger injection surface) vs arg-list (safer, no shell features).
  Leaning `shell=True` on a personal machine *with* the guard + allowlist as the
  mitigation — flag for the 15a review.
- `surface="pane"` → delegates to `iterm2_tool.open_pane([command])` +
  `read_pane()`. Reuses the existing injector (already Constitution-gated;
  needs iTerm2 running). Visible, abortable.

---

## 5. Domains & capabilities

Effect class in parentheses drives the ladder. "auto" = runs in strict mode
without approval; "gated" = approval in strict mode (and mutate/irreversible in
effect mode).

### 5.1 `macos_mcp.py` (15a)
- `get_time()` (read) — auto. *The trivial one that proves the wiring.*
- `system_info()` (read) — auto. CPU/mem/disk/battery/uptime; reuse `panels.py`.
- `list_running_apps()` / `get_frontmost_app()` (read) — auto.
- `notify(title, body)` (mutate, benign) — auto. macOS notification.
- `clipboard_read()` (read) / `clipboard_write(text)` (mutate, benign) — auto.
- `open_app(name)` (mutate) — auto.
- `run_command(...)` (governed by §4.3) — allowlisted auto, else gated.

### 5.2 `fs_mcp.py` (15b)
- `read_file` / `list_dir` / `search` (read) — auto, scoped to `allowed_roots`.
- `write_file` / `append` (mutate) — gated (auto inside `scratch_root`).
- `move` (irreversible) / `delete` (irreversible) — gated, strong confirm.
- Builds on the existing `tools/filesystem_tool.py`.

### 5.3 `messages_mcp.py` (15c) — needs permissions
- `list_recent_chats` / `read_thread` / `search_messages` (read) — reads the
  Messages SQLite `chat.db` (read-only). **Requires Full Disk Access.**
- `send_message(to, text)` (irreversible) — gated. Via AppleScript to
  Messages.app. **Requires Automation permission.** Messages scripting is
  historically flaky — spike reliability in 15c before committing to it.

### 5.4 `mail_mcp.py` (15d) — needs permissions
- `list_recent` / `read_message` / `search` (read) — AppleScript to Mail.app
  (Automation permission) or IMAP. Decide the transport in 15d.
- `send_mail` / `reply` (irreversible) — gated, strong confirm.

---

## 6. Exposure

### 6.1 To OSA (in-process)
`agents/osa_agent.py` `OSAToolbox` imports a curated set from `REGISTRY` and
registers them as OSA tools. They are already guarded, so OSA's existing
`_guarded` plumbing and two-turn confirm compose cleanly. **Open question:**
does OSA get *all* capabilities or a curated subset (e.g. maybe not raw
`send_mail`)? Default: curate conservatively, widen on request.

### 6.2 To Claude Desktop / Claude Code (stdio MCP)
- **Claude Desktop:** add to its `mcpServers` config:
  ```json
  {
    "mcpServers": {
      "osa-system": {
        "command": "/Users/tonyseneadza/Codehome/AgenticOS/.venv/bin/python",
        "args": ["-m", "tools.osa_system_mcp"],
        "cwd": "/Users/tonyseneadza/Codehome/AgenticOS"
      }
    }
  }
  ```
- **Claude Code:** `claude mcp add osa-system -- <the same command>` or a
  project `.mcp.json`.

---

## 7. macOS permissions (TCC)

On-device, user-granted, **cannot be scripted around** (by design):
- **Full Disk Access** — the process reading `chat.db` (the `.venv` python, or
  the terminal/host launching it) must be granted FDA in
  System Settings → Privacy & Security → Full Disk Access.
- **Automation** — the first AppleScript to Messages/Mail triggers a per-app
  TCC prompt; approve once.

A step-by-step grant runbook is a 15e deliverable (mirror to Brain2).

---

## 8. Phase breakdown & checklist

- **15a — Scaffold + macOS-basics + terminal** *(the spine)*
  - [ ] Read `hub_mcp.py` server setup; build `_harness.py` (registry + guard)
        and `_policy.py` (strict mode + allow/deny lookup).
  - [ ] `osa_system_mcp.py` aggregator + stdio server.
  - [ ] `macos_mcp.py`: `get_time`, `system_info`, `run_command` (both surfaces).
  - [ ] `config/constitution.yaml` `system_mcp` block + `approval_required` adds.
  - [ ] Wire curated capabilities into OSA `OSAToolbox`.
  - [ ] Tests: allowlisted cmd runs; non-allowlisted → `ApprovalRequired`;
        denylisted → `ConstitutionViolation`; registry↔list_tools parity;
        subprocess + pane paths (iTerm2 mocked).
  - [ ] Glossary + CHANGELOG + roadmap same-change; `osa-system-mcp` skill.
- **15b — Filesystem** — `fs_mcp.py`, `allowed_roots`/`scratch_root`, read auto /
  write+delete gated; reuse `filesystem_tool.py`.
- **15c — iMessage** — `messages_mcp.py`; FDA grant; read from `chat.db`; send
  spike + gate.
- **15d — Mail** — `mail_mcp.py`; transport decision (AppleScript vs IMAP);
  read/send gated.
- **15e — Harden + migrate** — flip `mode: strict → effect`; build the
  read/mutate/irreversible classifier; permissions runbook; docs.

---

## 9. Testing strategy

Follow the voice-test pattern (headless, real deps mocked):
- Mock `subprocess`, AppleScript (`osascript`), and `chat.db` — never hit the
  real terminal, never send a real message/mail in a test.
- Guard tests are the core: prove allow / approve / deny for representative
  commands per mode.
- Registry test: every `REGISTRY` entry has a schema and appears in `list_tools`.
- Reuse `gui/sidecar/tests/conftest.py` fixtures where DB touch is involved
  (unlikely here — these are mostly pure/mocked).

---

## 10. Open questions / risks

1. `run_command` `shell=True` vs arg-list (§4.3) — resolve in 15a.
2. OSA gets all capabilities vs a curated subset (§6.1).
3. iMessage send reliability via AppleScript (§5.3) — spike in 15c.
4. Effect-classifier design for 15e (heuristic vs small-model call) — deferred.
5. FDA/Automation grants block 15c/15d until done on-device (§7).

---

## 11. Conventions that apply

- **stdio server → no port, no HTTP** ⇒ `PORT_ASSIGNMENTS.md`, `HubApiExplorer`,
  api-registry rule do **not** apply. (Revisit only if an HTTP status route is
  ever added.)
- Glossary / CHANGELOG / roadmap update in the **same change** as each build
  phase (CLAUDE.md rules).
- New skill `osa-system-mcp` documenting the harness + dual-mode + guard so
  future sessions don't reinvent it.
- Subagent vs inline build is Tony's call at build time (preference says
  subagents; recent CONTINUATION notes flag a spend limit → inline).

---

## 12. Verify (once 15a lands)

```bash
cd ~/Codehome/AgenticOS
# server starts and lists tools over stdio:
.venv/bin/python -m tools.osa_system_mcp   # (Ctrl-C to exit)
# unit tests:
.venv/bin/python -m pytest gui/sidecar/tests -q   # + new tools/system tests
# OSA can tell the time / run a safe command (via chat or /api/osa/chat)
```
```
