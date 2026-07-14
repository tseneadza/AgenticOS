# TCC Permissions Runbook — OSA System MCP

> **What this is.** A step-by-step guide to granting the macOS privacy
> permissions (TCC — Transparency, Consent, and Control) that unlock the
> filesystem- and app-backed capabilities of the OSA System MCP (Phase 15).
> These grants are **on-device and user-only** — they cannot be scripted
> around (by design). Do them once; verify with the commands below.
>
> **Mirror.** A copy lives at
> `~/Brain2/08 - Systems/Agentic OS/TCC_PERMISSIONS_RUNBOOK.md`. This
> `docs/` copy is authoritative.

## Who is "the process"?

TCC grants attach to the **executable that runs the code**, not to the repo.
For OSA the process is the project virtualenv Python:

```
/Users/tonyseneadza/Codehome/AgenticOS/.venv/bin/python
```

When OSA runs inside the sidecar, that same `.venv` Python is the process.
When Claude Desktop / Claude Code launch the stdio server
(`python -m tools.osa_system_mcp`), the **host app** (Claude Desktop, Terminal,
iTerm2, VS Code) is the process that must hold the grant. Grant the one you
actually launch from.

---

## 1. Full Disk Access (FDA)

**Unlocks:**
- **iMessage reads** — `messages.read_thread`, `messages.search_messages`,
  `messages.list_recent_chats` open `~/Library/Messages/chat.db` read-only.
- **Post-send delivery check** (15e) — `messages.send_message` confirms the
  row landed in `chat.db` (optional; the send never depends on it).
- **Mail `.emlx` body reads** (15e) — `mail.read_message` reads the message
  body straight off disk under `~/Library/Mail`, far faster than the
  AppleScript `content of <msg>` fetch (which hung 40s+ in the 15d spike).

**Without FDA:** every one of the above degrades cleanly — reads return a
clear "grant Full Disk Access" error, the delivery check returns
`{"checked": false}`, and mail body falls back to the AppleScript path. No
crash, no send failure.

**Grant steps:**
1. Open **System Settings → Privacy & Security → Full Disk Access**.
2. Click the **+** button (authenticate with Touch ID / password).
3. Navigate to and add the process executable:
   - For the sidecar/OSA path: press **⌘⇧G**, paste
     `/Users/tonyseneadza/Codehome/AgenticOS/.venv/bin/python`, add it.
   - For the Claude Desktop / Terminal / iTerm2 launch path: add that app
     from `/Applications` (or `/System/Applications/Utilities` for Terminal).
4. Ensure the new entry's toggle is **ON**.
5. **Fully quit and relaunch** the process (sidecar / Claude Desktop /
   terminal) — TCC changes only take effect on a fresh launch.

**Verify:**
```bash
cd ~/Codehome/AgenticOS
.venv/bin/python - <<'PY'
import sqlite3, pathlib
p = pathlib.Path("~/Library/Messages/chat.db").expanduser()
try:
    c = sqlite3.connect(f"file:{p}?mode=ro&immutable=1", uri=True)
    c.execute("SELECT COUNT(*) FROM message").fetchone()
    print("FDA OK — chat.db readable")
except Exception as e:
    print("FDA MISSING —", e)
PY
```
A clean `FDA OK` line means the grant is live. `unable to open database file`
means it isn't (re-check the toggle + relaunch).

---

## 2. Automation (Apple Events)

**Unlocks** (per-app; each first use triggers a one-time prompt):
- **Messages** — `messages.send_message` (AppleScript `send` to Messages.app).
- **Contacts** — `messages.resolve_contact` (name → phone/email handles).
- **Mail** — every `mail.*` capability (list/search/read headers, `send_mail`,
  `reply`) drives Mail.app over AppleScript.

**Without Automation:** the capability returns a clear
"the host process may need Automation permission for <App>" error — never a
crash. The gated sends (`send_message`, `send_mail`, `reply`) still require
HITL approval regardless; Automation only decides whether the *approved* call
can reach the app.

**Grant steps:**
1. The **first** AppleScript to each app pops a system dialog:
   *"<process> wants to control <App>."* Click **OK / Allow**.
2. If you dismissed it, re-enable under **System Settings → Privacy &
   Security → Automation** — expand the process (the `.venv` Python or the
   launching app) and toggle **Messages**, **Contacts**, **Mail** ON.
3. Automation grants are also relaunch-sensitive; restart the process after
   changing them.

**Verify** (read-only, no message/mail leaves the Mac):
```bash
cd ~/Codehome/AgenticOS
# Contacts automation (safe lookup):
.venv/bin/python -c "from tools.system import messages_mcp as m; print(m.resolve_contact('a'))"
# Mail automation (safe mailbox list):
.venv/bin/python -c "from tools.system import mail_mcp as m; print(m.list_mailboxes())"
```
`{"ok": true, ...}` (or a clean empty/`count` result) means Automation is
granted. An error mentioning Automation means the prompt was denied — re-grant
and relaunch.

---

## Config anchors (why a client can't repoint these)

The protected paths are **config, never caller arguments** (security rule,
15c/15d/15e):
- `system_mcp.messages.db_path` → `~/Library/Messages/chat.db`
- `system_mcp.mail.emlx_root` → `~/Library/Mail`
- `system_mcp.mail.account` / `default_mailbox`

An MCP client cannot pass a `db_path=` / `emlx_root=` to read another store —
the reader always uses the Constitution value.

---

## Quick reference

| Permission | Process to grant | Unlocks | Degrade if missing |
|---|---|---|---|
| Full Disk Access | `.venv/bin/python` (or launching app) | chat.db reads, delivery check, `.emlx` body reads | clean error / AppleScript body fallback |
| Automation → Messages | same | `send_message` | clean error (send still HITL-gated) |
| Automation → Contacts | same | `resolve_contact` | clean error |
| Automation → Mail | same | all `mail.*` | clean error |

**Golden rule:** grant → **quit & relaunch** the process → verify. TCC never
picks up a change without a fresh launch.
