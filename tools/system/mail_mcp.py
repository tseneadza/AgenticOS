"""Mail capabilities — Phase 15d (design §5.4). AppleScript → Mail.app.

Transport decision (Tony, 2026-07-13): AppleScript, not IMAP — it reuses the
15c-hardened patterns (argv injection defense, ``open -ga`` pre-launch, TCC
Automation) and stores NO mail credentials anywhere.

Spike findings (2026-07-13) that shape this module:

* **Header reads are fast and reliable** — subject/sender/date/id via
  AppleScript return instantly, even iterating a mailbox.
* **Body fetch can BLOCK indefinitely** — ``content of <message>`` hung 40s+
  on every message tried (iCloud bodies not downloaded locally). So
  ``read_message`` returns headers ALWAYS and fetches the body in a SEPARATE
  ``osascript`` call behind a short timeout, degrading to a clean
  "body unavailable" note instead of hanging a read capability.
* **Disk ``.emlx`` fallback is blocked by FDA** (same pending grant as
  chat.db) — a 15e candidate, not built here.
* ``reply <msg> without opening window`` returns an outgoing message whose
  recipient Mail itself sets from the original sender — verified live via a
  construct→inspect→delete spike (no send).
* Mailbox indexing order is not guaranteed — ``list_recent`` compares the
  dates at both ends of the mailbox and walks from the newest end.

SECURITY (payload rule — see the osa-system-mcp skill):

* ``send_mail``'s FIRST parameter is the recipient address; the human
  confirms the REAL destination. Email-shaped handles only.
* ``reply``'s FIRST parameter is also the recipient address the human
  confirms — but Mail, not the caller, decides where a reply actually goes.
  The body therefore constructs the reply, reads back the address Mail set,
  and raises ``ConstitutionViolation`` on mismatch (the ``fs.move``
  secondary-path pattern): an approved call can never be redirected, and a
  stale/garbage ``to`` can never be rubber-stamped.
* The account name comes ONLY from config (``system_mcp.mail.account``) —
  an MCP client cannot repoint reads at another account (db_path precedent).
* User strings ride ``osascript`` ARGV (``on run argv`` after ``--``), never
  interpolated into script source (15c rule, applies to every script here).
* **Known residual risk (15d security review):** header fields (subject,
  sender) are attacker-controlled content from incoming mail. A subject
  containing a linefeed + field separators could forge a header row in
  list/search output — display deception only: the parser drops rows whose
  id isn't purely numeric, ``reply`` re-verifies the real recipient (a forged
  sender mismatches and is refused), and ``send_mail`` gates on the address
  the human actually sees. Never treat listed sender strings as verified
  identity.
"""
from __future__ import annotations

import re
import subprocess
import time

from core.constitution import ConstitutionViolation

from tools.system._harness import capability

_DEFAULT_LIMIT = 20
_HARD_MAX = 100
_LIST_TIMEOUT_S = 25
_SEND_TIMEOUT_S = 30
_COLD_SETTLE_SEND_S = 6.0     # cold-launch settle before an irreversible send
_DEFAULT_BODY_TIMEOUT_S = 10
_MAX_BODY_LEN = 8000          # chars of body returned to the model
_MAX_SEND_LEN = 20000         # chars of body accepted for send/reply

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_FIELD_SEP = "\x1f"           # unit separator — cannot appear in argv strings we emit


def _mail_cfg() -> dict:
    """The live ``system_mcp.mail`` block (honors the harness test seam)."""
    from tools.system import _harness

    c = _harness._constitution_override
    if c is None:
        from core.constitution import Constitution

        c = Constitution.load()
    return c.system_mcp.get("mail", {})


def _account() -> str:
    return str(_mail_cfg().get("account", "iCloud"))


def _default_mailbox() -> str:
    return str(_mail_cfg().get("default_mailbox", "INBOX"))


def _body_timeout() -> int:
    try:
        return max(2, int(_mail_cfg().get("body_timeout_s", _DEFAULT_BODY_TIMEOUT_S)))
    except (TypeError, ValueError):
        return _DEFAULT_BODY_TIMEOUT_S


def _cap_limit(limit) -> int:
    """Clamp a caller-supplied limit to [1, max_limit]; default on garbage."""
    hard = int(_mail_cfg().get("max_limit", _HARD_MAX))
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = _DEFAULT_LIMIT
    return max(1, min(n, hard))


def _osascript(script: str, args: list[str], timeout: int, cold_settle: float = 1.0):
    """Run one AppleScript with argv-delivered user data (15c pattern).

    Pre-launches Mail via ``open -ga`` — from a background context
    ``tell application`` can attach to a running app but not LAUNCH one
    (error -600, live-found 2026-07-12). ``cold_settle`` is the wait after a
    COLD launch only (no wait when Mail was already running — warm reads are
    instant). Sends pass a LONGER settle: live checkout 2026-07-13 showed a
    send fired into a freshly-launched, still-syncing Mail was delivered
    TWICE (autosaved draft replayed by iCloud sync) and left a draft behind;
    the same send against warm Mail was clean. Returns ``(proc, error_dict)``
    — exactly one truthy.
    """
    try:
        was_running = subprocess.run(
            ["pgrep", "-xq", "Mail"], capture_output=True, timeout=5
        ).returncode == 0
        pre = subprocess.run(["open", "-ga", "Mail"], capture_output=True, timeout=10)
        if pre.returncode == 0 and not was_running:
            time.sleep(cold_settle)
        proc = subprocess.run(
            ["osascript", "-e", script, "--", *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return proc, None
    except subprocess.TimeoutExpired:
        return None, {"ok": False, "error": f"osascript timed out after {timeout}s"}
    except FileNotFoundError:
        return None, {"ok": False, "error": "osascript not found — is this macOS?"}


def _script_error(proc, doing: str) -> dict:
    return {"ok": False,
            "error": f"{doing} failed ({(proc.stderr or '').strip() or f'rc={proc.returncode}'}) — "
                     "the host process may need Automation permission for Mail, "
                     "or the mailbox/account name is wrong (see mail.list_mailboxes)"}


def _parse_header_lines(stdout: str) -> list[dict]:
    """Parse ``id␟subject␟sender␟date`` lines emitted by the list/search scripts."""
    out = []
    for line in (stdout or "").splitlines():
        parts = line.split(_FIELD_SEP)
        # id must be purely numeric — drops rows forged via linefeeds inside a
        # hostile subject (see the residual-risk note in the module docstring).
        if len(parts) == 4 and parts[0].strip().isdigit():
            out.append({"id": parts[0].strip(), "subject": parts[1],
                        "sender": parts[2], "date": parts[3]})
    return out


# --------------------------------------------------------------------------- #
# AppleScript sources. User data arrives via argv ONLY. Field output uses the
# ASCII unit separator so subjects containing '|' can't corrupt parsing.
# --------------------------------------------------------------------------- #

# argv: 1=account. Emits "mailbox␟count" lines.
_MAILBOXES_SCRIPT = '''\
on run argv
    set theAccount to item 1 of argv
    set sep to (ASCII character 31)
    set out to ""
    tell application "Mail"
        repeat with mb in mailboxes of account theAccount
            set out to out & (name of mb) & sep & ((count of messages of mb) as text) & linefeed
        end repeat
    end tell
    return out
end run
'''

# argv: 1=mailbox, 2=account, 3=limit. Headers from the NEWEST end.
# Index order is not guaranteed, so compare the two end dates first.
_LIST_SCRIPT = '''\
on run argv
    set theMailbox to item 1 of argv
    set theAccount to item 2 of argv
    set maxN to (item 3 of argv) as integer
    set sep to (ASCII character 31)
    set out to ""
    tell application "Mail"
        set mb to mailbox theMailbox of account theAccount
        set total to count of messages of mb
        if total is 0 then return ""
        set n to maxN
        if total < n then set n to total
        set headNewest to true
        if total > 1 then
            if (date received of message 1 of mb) < (date received of message total of mb) then set headNewest to false
        end if
        repeat with k from 1 to n
            if headNewest then
                set i to k
            else
                set i to total - k + 1
            end if
            set m to message i of mb
            set out to out & (id of m as text) & sep & (subject of m) & sep & (sender of m) & sep & (date received of m as text) & linefeed
        end repeat
    end tell
    return out
end run
'''

# argv: 1=query, 2=mailbox, 3=account, 4=limit. Subject/sender match only —
# body search would require locally downloaded bodies (spike: not available).
_SEARCH_SCRIPT = '''\
on run argv
    set theQuery to item 1 of argv
    set theMailbox to item 2 of argv
    set theAccount to item 3 of argv
    set maxN to (item 4 of argv) as integer
    set sep to (ASCII character 31)
    set out to ""
    tell application "Mail"
        set mb to mailbox theMailbox of account theAccount
        set hits to (messages of mb whose subject contains theQuery or sender contains theQuery)
        set total to count of hits
        set n to maxN
        if total < n then set n to total
        repeat with i from 1 to n
            set m to item i of hits
            set out to out & (id of m as text) & sep & (subject of m) & sep & (sender of m) & sep & (date received of m as text) & linefeed
        end repeat
    end tell
    return out
end run
'''

# argv: 1=id, 2=mailbox, 3=account. Headers only — never touches the body.
_HEADERS_SCRIPT = '''\
on run argv
    set theId to (item 1 of argv) as integer
    set theMailbox to item 2 of argv
    set theAccount to item 3 of argv
    set sep to (ASCII character 31)
    tell application "Mail"
        set mb to mailbox theMailbox of account theAccount
        set m to first message of mb whose id = theId
        return (id of m as text) & sep & (subject of m) & sep & (sender of m) & sep & (date received of m as text) & sep & (read status of m as text)
    end tell
end run
'''

# argv: 1=id, 2=mailbox, 3=account, 4=max chars. The ONLY body toucher —
# runs behind its own short timeout because content fetch can block (spike).
_BODY_SCRIPT = '''\
on run argv
    set theId to (item 1 of argv) as integer
    set theMailbox to item 2 of argv
    set theAccount to item 3 of argv
    set maxC to (item 4 of argv) as integer
    tell application "Mail"
        set mb to mailbox theMailbox of account theAccount
        set m to first message of mb whose id = theId
        set b to content of m
        if (length of b) > maxC then set b to text 1 thru maxC of b
        return b
    end tell
end run
'''

# argv: 1=to, 2=subject, 3=body. Construction verified live (create→delete
# spike 2026-07-13); the send verb is live-verified in the 15d checkout.
_SEND_SCRIPT = '''\
on run argv
    set theTo to item 1 of argv
    set theSubject to item 2 of argv
    set theBody to item 3 of argv
    tell application "Mail"
        set msg to make new outgoing message with properties {subject:theSubject, content:theBody, visible:false}
        tell msg
            make new to recipient at end of to recipients with properties {address:theTo}
        end tell
        send msg
    end tell
    return "sent"
end run
'''

# argv: 1=id, 2=mailbox, 3=account, 4=body, 5=confirmed recipient.
# Mail sets the reply recipient itself; we read it back and REFUSE (delete
# the draft, no send) unless it equals the human-confirmed address. The
# guard's payload rule stays honest: what Tony approved is where it goes.
_REPLY_SCRIPT = '''\
on run argv
    set theId to (item 1 of argv) as integer
    set theMailbox to item 2 of argv
    set theAccount to item 3 of argv
    set theBody to item 4 of argv
    set confirmedTo to item 5 of argv
    tell application "Mail"
        set mb to mailbox theMailbox of account theAccount
        set m to first message of mb whose id = theId
        set r to reply m without opening window
        set actualTo to ""
        try
            set actualTo to (address of first to recipient of r)
        end try
        ignoring case
            if actualTo is not confirmedTo then
                delete r
                return "MISMATCH" & (ASCII character 31) & actualTo
            end if
        end ignoring
        set content of r to theBody
        send r
    end tell
    return "sent"
end run
'''


# --------------------------------------------------------------------------- #
# Read capabilities (auto — posture matches message reads; Tony, 2026-07-13)
# --------------------------------------------------------------------------- #

@capability(
    "mail.list_mailboxes",
    domain="mail",
    effect="read",
    auto=True,
    schema={"type": "object", "properties": {}},
)
def list_mailboxes() -> dict:
    """List the configured mail account's mailboxes with message counts."""
    acct = _account()
    proc, err = _osascript(_MAILBOXES_SCRIPT, [acct], _LIST_TIMEOUT_S)
    if err:
        return err
    if proc.returncode != 0:
        return _script_error(proc, "mailbox listing")
    boxes = []
    for line in (proc.stdout or "").splitlines():
        parts = line.split(_FIELD_SEP)
        if len(parts) == 2 and parts[0].strip():
            boxes.append({"mailbox": parts[0], "count": int(parts[1]) if parts[1].strip().isdigit() else 0})
    return {"ok": True, "account": acct, "count": len(boxes), "mailboxes": boxes}


@capability(
    "mail.list_recent",
    domain="mail",
    effect="read",
    auto=True,
    schema={
        "type": "object",
        "properties": {
            "mailbox": {"type": "string", "description": "Mailbox name (see mail.list_mailboxes). Default: the configured default mailbox."},
            "limit": {"type": "integer", "default": _DEFAULT_LIMIT},
        },
    },
)
def list_recent(mailbox: str = "", limit: int = _DEFAULT_LIMIT) -> dict:
    """List recent email headers (subject/sender/date) in a mailbox, newest first."""
    mb = (mailbox or "").strip() or _default_mailbox()
    acct = _account()
    proc, err = _osascript(_LIST_SCRIPT, [mb, acct, str(_cap_limit(limit))], _LIST_TIMEOUT_S)
    if err:
        return err
    if proc.returncode != 0:
        return _script_error(proc, "mail listing")
    msgs = _parse_header_lines(proc.stdout)
    return {"ok": True, "account": acct, "mailbox": mb, "count": len(msgs), "messages": msgs}


@capability(
    "mail.search_mail",
    domain="mail",
    effect="read",
    auto=True,
    schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Substring matched against subject OR sender (body search unavailable — bodies are not local)."},
            "mailbox": {"type": "string", "description": "Mailbox to search. Default: the configured default mailbox."},
            "limit": {"type": "integer", "default": _DEFAULT_LIMIT},
        },
        "required": ["query"],
    },
)
def search_mail(query: str, mailbox: str = "", limit: int = _DEFAULT_LIMIT) -> dict:
    """Search a mailbox by subject or sender substring (headers only)."""
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "query required"}
    mb = (mailbox or "").strip() or _default_mailbox()
    acct = _account()
    proc, err = _osascript(_SEARCH_SCRIPT, [query, mb, acct, str(_cap_limit(limit))], _LIST_TIMEOUT_S)
    if err:
        return err
    if proc.returncode != 0:
        return _script_error(proc, "mail search")
    msgs = _parse_header_lines(proc.stdout)
    return {"ok": True, "account": acct, "mailbox": mb, "query": query,
            "count": len(msgs), "messages": msgs}


@capability(
    "mail.read_message",
    domain="mail",
    effect="read",
    auto=True,
    schema={
        "type": "object",
        "properties": {
            "message_id": {"type": "integer", "description": "Message id from mail.list_recent / mail.search_mail."},
            "mailbox": {"type": "string", "description": "Mailbox containing the message. Default: the configured default mailbox."},
        },
        "required": ["message_id"],
    },
)
def read_message(message_id: int, mailbox: str = "") -> dict:
    """Read one email: headers always; body best-effort (may not be downloaded locally)."""
    try:
        mid = int(message_id)
    except (TypeError, ValueError):
        return {"ok": False, "error": "message_id must be an integer"}
    mb = (mailbox or "").strip() or _default_mailbox()
    acct = _account()

    proc, err = _osascript(_HEADERS_SCRIPT, [str(mid), mb, acct], _LIST_TIMEOUT_S)
    if err:
        return err
    if proc.returncode != 0:
        return _script_error(proc, f"reading message {mid}")
    parts = (proc.stdout or "").strip().split(_FIELD_SEP)
    if len(parts) != 5:
        return {"ok": False, "error": f"message {mid} not found in {mb}"}
    result = {"ok": True, "account": acct, "mailbox": mb, "id": parts[0],
              "subject": parts[1], "sender": parts[2], "date": parts[3],
              "read": parts[4] == "true"}

    # Body: separate call, short timeout — content fetch can block when the
    # body isn't downloaded locally (spike 2026-07-13). Headers never hang.
    bproc, berr = _osascript(_BODY_SCRIPT, [str(mid), mb, acct, str(_MAX_BODY_LEN)],
                             _body_timeout())
    if berr or bproc.returncode != 0:
        result["body"] = None
        result["body_note"] = ("body unavailable — not downloaded locally or fetch "
                               f"timed out after {_body_timeout()}s (headers are complete)")
    else:
        result["body"] = (bproc.stdout or "").strip()
    return result


# --------------------------------------------------------------------------- #
# Irreversible capabilities (gated always — design §5.4)
# --------------------------------------------------------------------------- #

@capability(
    "mail.send_mail",
    domain="mail",
    effect="irreversible",
    auto=False,
    schema={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email address (the human confirms THIS value)."},
            "subject": {"type": "string", "description": "Subject line."},
            "body": {"type": "string", "description": "Plain-text message body."},
        },
        "required": ["to", "subject", "body"],
    },
)
def send_mail(to: str, subject: str, body: str) -> dict:
    """Send an email from this Mac's Mail.app. Irreversible — always gated."""
    to = (to or "").strip()
    subject = (subject or "").strip()
    body = (body or "").strip()
    if not to:
        return {"ok": False, "error": "recipient address required"}
    if not _EMAIL_RE.match(to):
        return {"ok": False, "error": f"'{to}' is not an email address"}
    if not subject:
        return {"ok": False, "error": "subject required"}
    if not body:
        return {"ok": False, "error": "body required"}
    if len(body) > _MAX_SEND_LEN:
        return {"ok": False, "error": f"body too long ({len(body)} > {_MAX_SEND_LEN} chars)"}

    proc, err = _osascript(_SEND_SCRIPT, [to, subject, body], _SEND_TIMEOUT_S,
                           cold_settle=_COLD_SETTLE_SEND_S)
    if err:
        return err
    if proc.returncode != 0:
        return _script_error(proc, "mail send")
    return {"ok": True, "to": to, "subject": subject,
            "note": "handed to Mail.app for sending — delivery is not verified"}


@capability(
    "mail.reply",
    domain="mail",
    effect="irreversible",
    auto=False,
    schema={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "The original sender's email address — the human confirms THIS value; the send is refused if Mail's reply would go anywhere else."},
            "message_id": {"type": "integer", "description": "Id of the message being replied to (from mail.list_recent / mail.search_mail)."},
            "body": {"type": "string", "description": "Plain-text reply body."},
            "mailbox": {"type": "string", "description": "Mailbox containing the message. Default: the configured default mailbox."},
        },
        "required": ["to", "message_id", "body"],
    },
)
def reply(to: str, message_id: int, body: str, mailbox: str = "") -> dict:
    """Reply to an email (threaded). Irreversible — gated; recipient re-verified against the actual message."""
    to = (to or "").strip()
    body = (body or "").strip()
    if not to:
        return {"ok": False, "error": "recipient address required (the original sender)"}
    if not _EMAIL_RE.match(to):
        return {"ok": False, "error": f"'{to}' is not an email address"}
    try:
        mid = int(message_id)
    except (TypeError, ValueError):
        return {"ok": False, "error": "message_id must be an integer"}
    if not body:
        return {"ok": False, "error": "body required"}
    if len(body) > _MAX_SEND_LEN:
        return {"ok": False, "error": f"body too long ({len(body)} > {_MAX_SEND_LEN} chars)"}
    mb = (mailbox or "").strip() or _default_mailbox()
    acct = _account()

    proc, err = _osascript(_REPLY_SCRIPT, [str(mid), mb, acct, body, to], _SEND_TIMEOUT_S,
                           cold_settle=_COLD_SETTLE_SEND_S)
    if err:
        return err
    if proc.returncode != 0:
        return _script_error(proc, f"reply to message {mid}")
    out = (proc.stdout or "").strip()
    if out.startswith("MISMATCH"):
        actual = out.split(_FIELD_SEP, 1)[1] if _FIELD_SEP in out else "<unknown>"
        # fs.move pattern: a secondary path the guard can't see is enforced
        # in the body with a hard violation — approval cannot override it.
        raise ConstitutionViolation(
            f"reply refused: the approved recipient '{to}' does not match where "
            f"Mail would actually send this reply ('{actual}') — draft deleted, nothing sent"
        )
    return {"ok": True, "to": to, "replied_to_id": mid, "mailbox": mb,
            "note": "handed to Mail.app for sending — delivery is not verified"}
