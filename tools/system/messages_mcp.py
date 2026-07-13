"""iMessage capabilities — Phase 15c (design §5.3), READ half.

Read-only access to the macOS Messages store (``chat.db``): list recent
conversations, read a thread with one contact, and search message text. All
three are ``read`` capabilities (auto in strict mode, like the fs reads).

SECURITY: the database path comes ONLY from the Constitution
(``system_mcp.messages.db_path``) — it is NEVER a capability parameter, so an
MCP client cannot repoint the reader at another SQLite file. The DB is opened
read-only + immutable (no locks taken, so a running Messages.app can't block
the read). Reading ``chat.db`` requires Full Disk Access for the process (the
``.venv`` python / the sidecar); without it SQLite raises "unable to open
database file", surfaced here as a clean, actionable error — never a crash.

NOT here yet (deliberate): the AppleScript SEND half (design flags Messages
scripting as flaky — spike before building) and OSA-toolbox wiring (the
"which capabilities does OSA get" curated-subset question, design §10 — the
same open item as the fs domain).

chat.db notes:
- ``message.date`` is nanoseconds since the Apple epoch (2001-01-01 UTC).
- On modern macOS ``message.text`` is often NULL and the body lives in the
  ``attributedBody`` typedstream blob; ``_body_text`` returns ``text`` when
  present and otherwise makes a best-effort recovery, marking what it can't
  recover. (Test fixtures populate ``text``, so that path is live-only.)
- ``immutable=1`` may miss messages still in an un-checkpointed WAL — an
  acceptable trade for a lock-free "recent activity" read.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tools.system._harness import capability

_APPLE_EPOCH = 978307200          # seconds from 1970-01-01 to 2001-01-01 UTC
_DEFAULT_LIMIT = 20
_HARD_MAX = 200


def _messages_cfg() -> dict:
    """The live ``system_mcp.messages`` block (honors the harness test seam)."""
    from tools.system import _harness

    c = _harness._constitution_override
    if c is None:
        from core.constitution import Constitution

        c = Constitution.load()
    return c.system_mcp.get("messages", {})


def _db_path() -> Path:
    return Path(_messages_cfg().get("db_path", "~/Library/Messages/chat.db")).expanduser()


def _cap_limit(limit) -> int:
    """Clamp a caller-supplied limit to [1, max_limit]; default on garbage."""
    hard = int(_messages_cfg().get("max_limit", _HARD_MAX))
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = _DEFAULT_LIMIT
    return max(1, min(n, hard))


def _connect() -> sqlite3.Connection:
    """Open chat.db read-only + immutable.

    Raises ``FileNotFoundError`` when the DB is absent and
    ``sqlite3.OperationalError`` when it can't be opened/read (Full Disk
    Access missing) — callers translate both into clean result dicts.
    """
    path = _db_path()
    if not path.exists():
        raise FileNotFoundError(str(path))
    conn = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _apple_to_iso(date_ns) -> str | None:
    """Apple-epoch nanoseconds → ISO-8601 UTC string (None on bad input)."""
    if not date_ns:
        return None
    try:
        secs = int(date_ns) / 1_000_000_000 + _APPLE_EPOCH
        return datetime.fromtimestamp(secs, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _body_text(text, attributed_body) -> str:
    """Best-effort message body: prefer ``text``; else recover a printable run
    from the ``attributedBody`` typedstream blob; else a clear marker."""
    if text:
        return text
    if not attributed_body:
        return ""
    try:
        raw = bytes(attributed_body)
        marker = raw.find(b"NSString")
        seg = raw[marker:] if marker != -1 else raw
        out = bytearray()
        started = False
        for b in seg[10:]:                        # skip the class-name framing
            if 32 <= b < 127 or b >= 0xC2:        # ascii printable or utf-8 lead
                out.append(b)
                started = True
            elif started:
                break
        recovered = out.decode("utf-8", "ignore").strip()
        if len(recovered) >= 2:
            return recovered
    except Exception:                             # noqa: BLE001 — never crash a read
        pass
    return "[unrecovered message body]"


def _row_to_msg(row: sqlite3.Row) -> dict:
    return {
        "from_me": bool(row["is_from_me"]),
        "handle": row["handle"],
        "text": _body_text(row["text"], row["attributedBody"]),
        "date": _apple_to_iso(row["date"]),
        "service": row["service"],
    }


_MSG_COLS = "m.text, m.attributedBody, m.is_from_me, m.date, m.service, h.id AS handle"

_THREAD_SQL = f"""
    SELECT {_MSG_COLS}
    FROM message m
    LEFT JOIN handle h ON m.handle_id = h.ROWID
    WHERE m.handle_id IN (SELECT ROWID FROM handle WHERE id = ?)
    ORDER BY m.date DESC
    LIMIT ?
"""

_SEARCH_SQL = f"""
    SELECT {_MSG_COLS}
    FROM message m
    LEFT JOIN handle h ON m.handle_id = h.ROWID
    WHERE m.text LIKE ?
    ORDER BY m.date DESC
    LIMIT ?
"""

_RECENT_SQL = """
    SELECT c.chat_identifier AS chat, c.display_name AS name, MAX(m.date) AS last
    FROM chat c
    JOIN chat_message_join cmj ON cmj.chat_id = c.ROWID
    JOIN message m ON m.ROWID = cmj.message_id
    GROUP BY c.ROWID
    ORDER BY last DESC
    LIMIT ?
"""


def _read(sql: str, params: tuple):
    """Run one read query; return ``(rows, error_dict)`` — exactly one truthy."""
    try:
        conn = _connect()
    except FileNotFoundError as e:
        return None, {"ok": False, "error": f"chat.db not found at {e} — is this macOS Messages?"}
    except sqlite3.Error as e:
        return None, {"ok": False, "error": f"cannot open chat.db ({e}) — grant Full Disk Access to this process"}
    try:
        return conn.execute(sql, params).fetchall(), None
    except sqlite3.Error as e:
        return None, {"ok": False, "error": f"chat.db read failed ({e}) — Full Disk Access may be missing"}
    finally:
        conn.close()


@capability(
    "messages.read_thread",
    domain="messages",
    effect="read",
    auto=True,
    schema={
        "type": "object",
        "properties": {
            "contact": {"type": "string", "description": "Conversation handle: phone (+15551234567) or email."},
            "limit": {"type": "integer", "default": _DEFAULT_LIMIT},
        },
        "required": ["contact"],
    },
)
def read_thread(contact: str, limit: int = _DEFAULT_LIMIT) -> dict:
    """Read recent messages exchanged with one contact (handle), newest first."""
    if not (contact or "").strip():
        return {"ok": False, "error": "contact required"}
    rows, err = _read(_THREAD_SQL, (contact.strip(), _cap_limit(limit)))
    if err:
        return err
    return {"ok": True, "contact": contact.strip(), "count": len(rows),
            "messages": [_row_to_msg(r) for r in rows]}


@capability(
    "messages.search_messages",
    domain="messages",
    effect="read",
    auto=True,
    schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Substring to match in message text."},
            "limit": {"type": "integer", "default": _DEFAULT_LIMIT},
        },
        "required": ["query"],
    },
)
def search_messages(query: str, limit: int = _DEFAULT_LIMIT) -> dict:
    """Search message text for a substring, newest matches first (text column only)."""
    if not (query or "").strip():
        return {"ok": False, "error": "query required"}
    rows, err = _read(_SEARCH_SQL, (f"%{query.strip()}%", _cap_limit(limit)))
    if err:
        return err
    return {"ok": True, "query": query.strip(), "count": len(rows),
            "messages": [_row_to_msg(r) for r in rows]}


@capability(
    "messages.list_recent_chats",
    domain="messages",
    effect="read",
    auto=True,
    schema={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": _DEFAULT_LIMIT},
        },
    },
)
def list_recent_chats(limit: int = _DEFAULT_LIMIT) -> dict:
    """List the most recently active conversations, newest first."""
    rows, err = _read(_RECENT_SQL, (_cap_limit(limit),))
    if err:
        return err
    return {"ok": True, "count": len(rows),
            "chats": [{"chat": r["chat"], "name": r["name"], "last": _apple_to_iso(r["last"])} for r in rows]}


# --------------------------------------------------------------------------- #
# SEND half — 15c (spike-validated live 2026-07-12)
#
# Spike findings that shape this code:
#   * The modern ``participant <handle> of <account>`` + ``send`` AppleScript
#     syntax works reliably; the legacy ``buddy of service`` form is avoided.
#   * Participant resolution is LAZY — a garbage handle "resolves" without
#     error, so AppleScript will NOT validate recipients for us. We validate
#     the handle shape ourselves and treat send-time errors as failure.
#   * Both an iMessage and an SMS account are enabled on this Mac (Text
#     Message Forwarding), so iMessage-then-SMS fallback is viable.
#
# SECURITY:
#   * ``send_message`` accepts RAW HANDLES ONLY (phone/email). Contact names
#     are rejected with a pointer to ``resolve_contact`` — the guard's
#     approval payload is the FIRST parameter, so the human must always be
#     confirming the REAL target, never an unresolved alias.
#   * User text/handles are passed to ``osascript`` as ARGV (``on run argv``),
#     never interpolated into the script source — AppleScript injection via
#     quotes in the message text is structurally impossible.
#   * Delivery is NOT verified (Messages hands off asynchronously); a success
#     result means "queued to Messages.app", and says so.
# --------------------------------------------------------------------------- #
import re
import subprocess
import time

_SEND_TIMEOUT_S = 30
_RESOLVE_TIMEOUT_S = 20
_MAX_TEXT_LEN = 4000

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[\d\s().-]{7,20}$")

# argv: 1=handle, 2=text, 3=service ("imessage" | "sms")
_SEND_SCRIPT = '''\
on run argv
    set theHandle to item 1 of argv
    set theText to item 2 of argv
    set theService to item 3 of argv
    tell application "Messages"
        if theService is "sms" then
            set acc to 1st account whose service type = SMS and enabled = true
        else
            set acc to 1st account whose service type = iMessage and enabled = true
        end if
        set p to participant theHandle of acc
        send theText to p
    end tell
    return "sent"
end run
'''

# argv: 1=name fragment. Emits "name|kind|handle" lines (max 10 people).
_RESOLVE_SCRIPT = '''\
on run argv
    set theName to item 1 of argv
    set out to ""
    tell application "Contacts"
        set matches to (every person whose name contains theName)
        if (count of matches) > 10 then set matches to items 1 thru 10 of matches
        repeat with p in matches
            set nm to name of p
            repeat with ph in phones of p
                set out to out & nm & "|phone|" & (value of ph) & linefeed
            end repeat
            repeat with em in emails of p
                set out to out & nm & "|email|" & (value of em) & linefeed
            end repeat
        end repeat
    end tell
    return out
end run
'''


def _is_handle(to: str) -> bool:
    """Whether ``to`` is a raw messaging handle: an email or a phone number."""
    return bool(_EMAIL_RE.match(to) or _PHONE_RE.match(to))


def _osascript(script: str, args: list[str], timeout: int, app: str | None = None):
    """Run one AppleScript with argv-delivered user data.

    Returns ``(completed_process, error_dict)`` — exactly one is truthy.
    User strings ride argv (after ``--``) so they can never alter the script.

    ``app``: the target application to pre-launch via ``open -ga`` (background,
    no focus steal). Needed because ``tell application`` can ATTACH to a
    running app from the sidecar's background context but cannot LAUNCH one —
    it fails with ``-600 Application isn't running`` (live-found 2026-07-12
    when Contacts wasn't open). ``open`` goes through LaunchServices and works
    from background contexts; a short settle wait follows a cold launch.
    """
    try:
        if app:
            pre = subprocess.run(["open", "-ga", app], capture_output=True, timeout=10)
            if pre.returncode == 0:
                # Attach can still race a cold launch; a brief settle is cheap.
                time.sleep(1.0)
        proc = subprocess.run(
            ["osascript", "-e", script, "--", *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return proc, None
    except subprocess.TimeoutExpired:
        return None, {"ok": False, "error": f"osascript timed out after {timeout}s"}
    except FileNotFoundError:
        return None, {"ok": False, "error": "osascript not found — is this macOS?"}


@capability(
    "messages.resolve_contact",
    domain="messages",
    effect="read",
    auto=True,
    schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Contact name (or fragment) to look up in Contacts.app."},
        },
        "required": ["name"],
    },
)
def resolve_contact(name: str) -> dict:
    """Resolve a contact name to phone/email handles via Contacts.app (read-only)."""
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "name required"}
    proc, err = _osascript(_RESOLVE_SCRIPT, [name], _RESOLVE_TIMEOUT_S, app="Contacts")
    if err:
        return err
    if proc.returncode != 0:
        return {"ok": False,
                "error": f"Contacts lookup failed ({(proc.stderr or '').strip()}) — "
                         "the host process may need Automation permission for Contacts"}
    handles = []
    for line in (proc.stdout or "").splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3 and parts[2].strip():
            handles.append({"name": parts[0], "kind": parts[1], "handle": parts[2].strip()})
    return {"ok": True, "query": name, "count": len(handles), "handles": handles}


@capability(
    "messages.send_message",
    domain="messages",
    effect="irreversible",
    auto=False,
    schema={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient handle: phone (+15551234567) or email. Names are rejected — resolve_contact first."},
            "text": {"type": "string", "description": "Message body to send."},
        },
        "required": ["to", "text"],
    },
)
def send_message(to: str, text: str) -> dict:
    """Send an iMessage (SMS fallback) from this Mac. Irreversible — always gated."""
    to = (to or "").strip()
    text = (text or "").strip()
    if not to:
        return {"ok": False, "error": "recipient handle required"}
    if not text:
        return {"ok": False, "error": "message text required"}
    if len(text) > _MAX_TEXT_LEN:
        return {"ok": False, "error": f"message too long ({len(text)} > {_MAX_TEXT_LEN} chars)"}
    if not _is_handle(to):
        return {"ok": False,
                "error": f"'{to}' is not a phone/email handle — use resolve_contact "
                         "to look the person up, then send to the returned handle"}

    # iMessage first, SMS fallback (spike: both accounts enabled on this Mac).
    attempts = []
    for service in ("imessage", "sms"):
        proc, err = _osascript(_SEND_SCRIPT, [to, text, service], _SEND_TIMEOUT_S, app="Messages")
        if err:
            attempts.append(f"{service}: {err['error']}")
            continue
        if proc.returncode == 0:
            return {"ok": True, "to": to,
                    "service": "iMessage" if service == "imessage" else "SMS",
                    "note": "queued to Messages.app — delivery is not verified"}
        attempts.append(f"{service}: {(proc.stderr or '').strip() or f'rc={proc.returncode}'}")
    return {"ok": False,
            "error": "send failed on both services — " + "; ".join(attempts)
                     + ". The host process may need Automation permission for Messages."}
