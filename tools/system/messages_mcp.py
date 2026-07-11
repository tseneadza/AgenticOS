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
