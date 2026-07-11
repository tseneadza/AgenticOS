"""Phase 15c — iMessage READ domain: read_thread / search_messages / list_recent_chats.

Mirrors test_phase15b_fs_mcp.py. Everything runs against a hermetic pytest
tmp_path ``chat.db`` — the real ``~/Library/Messages/chat.db`` is NEVER touched.

Two critical regressions live here:

* **Denylist scoping** — terminal denylist patterns ("sudo", "rm -rf") must apply
  ONLY to ``macos.run_command``. A message search whose text merely contains
  "sudo" must be allowed, not falsely denied (design §4.1 / 15c note).
* **Config-not-caller db_path** — the reader's SQLite path comes ONLY from the
  Constitution; a client cannot repoint it with a ``db_path=`` kwarg.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from core.constitution import Constitution, _merge_system_mcp
from tools import osa_system_mcp
from tools.system import _harness, _policy, messages_mcp

# Distinct Apple-epoch nanosecond dates so ordering is deterministic.
_D1 = 700000000000000000  # oldest in the 1:1 thread
_D2 = 700000000000000001
_D3 = 700000000000000002  # newest in the 1:1 thread
_D_GROUP = 600000000000000000  # older than everything in chat 1
_CONTACT = "+15551234567"


# --------------------------------------------------------------------------- #
# Fixtures — a tmp_path chat.db + a constitution pointed at it
# --------------------------------------------------------------------------- #
def _build_chat_db(path) -> None:
    """Create a minimal chat.db mirroring the columns messages_mcp reads."""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE handle(ROWID INTEGER PRIMARY KEY, id TEXT);
        CREATE TABLE message(ROWID INTEGER PRIMARY KEY, text TEXT,
            attributedBody BLOB, is_from_me INT, handle_id INT, date INT,
            service TEXT);
        CREATE TABLE chat(ROWID INTEGER PRIMARY KEY, chat_identifier TEXT,
            display_name TEXT);
        CREATE TABLE chat_message_join(chat_id INT, message_id INT);
        """
    )
    conn.executemany(
        "INSERT INTO handle(ROWID, id) VALUES (?, ?)",
        [(1, _CONTACT), (2, "grouper")],
    )
    conn.executemany(
        "INSERT INTO message(ROWID, text, attributedBody, is_from_me, handle_id, date, service)"
        " VALUES (?,?,?,?,?,?,?)",
        [
            (1, "hey there", None, 0, 1, _D1, "iMessage"),
            (2, "run sudo please", None, 1, 1, _D2, "iMessage"),
            (3, "latest message", None, 0, 1, _D3, "SMS"),
            (4, "old group msg", None, 0, 2, _D_GROUP, "iMessage"),
        ],
    )
    conn.executemany(
        "INSERT INTO chat(ROWID, chat_identifier, display_name) VALUES (?,?,?)",
        [(1, _CONTACT, "Tony"), (2, "group1", "Group")],
    )
    conn.executemany(
        "INSERT INTO chat_message_join(chat_id, message_id) VALUES (?,?)",
        [(1, 1), (1, 2), (1, 3), (2, 4)],
    )
    conn.commit()
    conn.close()


@pytest.fixture()
def msg_env(tmp_path):
    """(db_path, constitution) — a hermetic chat.db and a matching Constitution."""
    db = tmp_path / "chat.db"
    _build_chat_db(db)
    c = Constitution()
    c.system_mcp = _merge_system_mcp({"messages": {"db_path": str(db), "max_limit": 50}})
    return db, c


@pytest.fixture(autouse=True)
def _inject(msg_env):
    """Pin the harness to the tmp-scoped constitution for every test."""
    _harness.set_constitution(msg_env[1])
    yield
    _harness.set_constitution(None)


# --------------------------------------------------------------------------- #
# 1. read_thread — newest-first + limit clamping
# --------------------------------------------------------------------------- #
class TestReadThread:
    def test_returns_contact_messages_newest_first(self, msg_env):
        out = messages_mcp.read_thread(_CONTACT)
        assert out["ok"] and out["contact"] == _CONTACT and out["count"] == 3
        texts = [m["text"] for m in out["messages"]]
        assert texts == ["latest message", "run sudo please", "hey there"]
        newest = out["messages"][0]
        assert newest["from_me"] is False
        assert newest["handle"] == _CONTACT
        assert newest["service"] == "SMS"

    def test_limit_one_returns_only_newest(self, msg_env):
        out = messages_mcp.read_thread(_CONTACT, limit=1)
        assert out["count"] == 1 and out["messages"][0]["text"] == "latest message"

    def test_cap_limit_clamps_to_max_limit(self, msg_env):
        # max_limit=50 in this fixture; garbage/over-max clamp, floor at 1.
        assert messages_mcp._cap_limit(999) == 50
        assert messages_mcp._cap_limit(0) == 1
        assert messages_mcp._cap_limit(-5) == 1
        assert messages_mcp._cap_limit("nonsense") == messages_mcp._DEFAULT_LIMIT

    def test_empty_contact_returns_error_not_raise(self, msg_env):
        assert messages_mcp.read_thread("") == {"ok": False, "error": "contact required"}
        assert messages_mcp.read_thread("   ") == {"ok": False, "error": "contact required"}


# --------------------------------------------------------------------------- #
# 3. search_messages — LIKE substring + denylist-scoping regression
# --------------------------------------------------------------------------- #
class TestSearchMessages:
    def test_like_substring_match(self, msg_env):
        out = messages_mcp.search_messages("latest")
        assert out["ok"] and out["query"] == "latest" and out["count"] == 1
        assert out["messages"][0]["text"] == "latest message"

    def test_empty_query_returns_error(self, msg_env):
        assert messages_mcp.search_messages("  ") == {"ok": False, "error": "query required"}

    def test_sudo_search_is_allowed_not_denied(self, msg_env):
        """A message search for 'sudo' must run — the terminal denylist is
        scoped to macos.run_command and must not touch message reads."""
        db, c = msg_env
        out = messages_mcp.search_messages("sudo")
        assert out["ok"] is True and out["count"] == 1
        assert "sudo" in out["messages"][0]["text"]

    def test_denylist_scoping_policy_regression(self, msg_env):
        """Same 'sudo' payload: allowed for the message search, denied for a
        real terminal command — proving the denylist no longer over-reaches."""
        _, c = msg_env
        allow = _policy.evaluate(
            name="messages.search_messages", effect="read", auto=True,
            payload="sudo", constitution=c,
        )
        deny = _policy.evaluate(
            name="macos.run_command", effect="read", auto=False,
            payload="sudo rm", constitution=c,
        )
        assert allow.decision == "allow"
        assert deny.decision == "deny"


# --------------------------------------------------------------------------- #
# 4. list_recent_chats — most-recent first, ISO 'last'
# --------------------------------------------------------------------------- #
class TestListRecentChats:
    def test_ordered_most_recent_first_with_iso_last(self, msg_env):
        out = messages_mcp.list_recent_chats()
        assert out["ok"] and out["count"] == 2
        chats = out["chats"]
        assert chats[0]["chat"] == _CONTACT and chats[0]["name"] == "Tony"
        assert chats[1]["chat"] == "group1"
        # 'last' is an ISO string produced via _apple_to_iso.
        assert isinstance(chats[0]["last"], str)
        assert chats[0]["last"] == messages_mcp._apple_to_iso(_D3)
        # Newest chat's last timestamp sorts after the older group chat's.
        assert chats[0]["last"] > chats[1]["last"]


# --------------------------------------------------------------------------- #
# 5. _apple_to_iso — epoch conversion
# --------------------------------------------------------------------------- #
class TestAppleToIso:
    def test_known_ns_value(self):
        # _D1 ns -> 700000000 s + apple epoch (978307200) = 1678307200 unix.
        assert messages_mcp._apple_to_iso(_D1) == "2023-03-08T20:26:40+00:00"

    def test_matches_reference_computation(self):
        secs = _D1 / 1_000_000_000 + messages_mcp._APPLE_EPOCH
        expected = datetime.fromtimestamp(secs, tz=timezone.utc).isoformat()
        assert messages_mcp._apple_to_iso(_D1) == expected

    def test_zero_and_none_are_none(self):
        assert messages_mcp._apple_to_iso(0) is None
        assert messages_mcp._apple_to_iso(None) is None


# --------------------------------------------------------------------------- #
# 6. _body_text — prefer text, best-effort recovery, empty fallback
# --------------------------------------------------------------------------- #
class TestBodyText:
    def test_text_present_returned_as_is(self):
        assert messages_mcp._body_text("hello", None) == "hello"
        assert messages_mcp._body_text("hello", b"ignored blob") == "hello"

    def test_recovers_printable_run_from_attributed_body(self):
        # Layout: <prefix> NSString <2 framing bytes> <printable run> <terminator>.
        # _body_text seeks "NSString", skips 2 framing bytes, then reads the run.
        blob = b"\x04\x0bstreamtyped" + b"NSString" + b"\x01\x94" + b"Hello world" + b"\x00"
        assert messages_mcp._body_text(None, blob) == "Hello world"

    def test_both_empty_returns_empty_string(self):
        assert messages_mcp._body_text(None, None) == ""
        assert messages_mcp._body_text("", None) == ""
        assert messages_mcp._body_text("", b"") == ""


# --------------------------------------------------------------------------- #
# 7. Config-not-caller db_path (security)
# --------------------------------------------------------------------------- #
class TestDbPathIsConfigOnly:
    def test_direct_call_rejects_db_path_kwarg(self, msg_env, tmp_path):
        """A client cannot repoint the reader: read_thread takes no db_path,
        so passing one raises TypeError rather than reading a foreign db."""
        attacker = tmp_path / "attacker.db"
        _build_chat_db(attacker)  # a real, readable db at a DIFFERENT path
        with pytest.raises(TypeError):
            messages_mcp.read_thread(contact=_CONTACT, db_path=str(attacker))

    def test_db_path_used_is_the_config_fixture(self, msg_env):
        db, _ = msg_env
        assert messages_mcp._db_path() == db
        # And a normal read really comes from that fixture db.
        assert messages_mcp.read_thread(_CONTACT)["count"] == 3

    def test_dispatch_drops_unknown_db_path_without_reading_it(self, msg_env, tmp_path):
        attacker = tmp_path / "attacker.db"
        _build_chat_db(attacker)
        out = osa_system_mcp.dispatch(
            "messages.read_thread", {"contact": _CONTACT, "db_path": str(attacker)}
        )
        # Unknown arg -> Bad arguments error; NOT a successful read of another db.
        assert "error" in out
        assert "messages" not in out


# --------------------------------------------------------------------------- #
# 8. kwargs-form dispatch regression + self-approval strip
# --------------------------------------------------------------------------- #
class TestDispatchKwargsForm:
    def test_dispatch_keyword_path_runs(self, msg_env):
        out = osa_system_mcp.dispatch("messages.read_thread", {"contact": _CONTACT})
        assert out.get("ok") is True and out["count"] == 3
        assert out["messages"][0]["text"] == "latest message"

    def test_dispatch_strips_client_approved_and_still_runs(self, msg_env):
        # Reads are auto, so they run regardless — assert no crash + normal result.
        out = osa_system_mcp.dispatch(
            "messages.read_thread", {"contact": _CONTACT, "approved": True}
        )
        assert out.get("ok") is True and out["count"] == 3

    def test_dispatch_search_keyword_path(self, msg_env):
        out = osa_system_mcp.dispatch("messages.search_messages", {"query": "sudo"})
        assert out.get("ok") is True and out["count"] == 1


# --------------------------------------------------------------------------- #
# 9. list_tools parity
# --------------------------------------------------------------------------- #
class TestToolListParity:
    MSG_TOOLS = {"messages.read_thread", "messages.search_messages",
                 "messages.list_recent_chats"}

    def test_all_three_present_with_input_schema(self):
        listed = {t["name"]: t for t in osa_system_mcp.build_tool_list()}
        assert self.MSG_TOOLS <= set(listed)
        for name in self.MSG_TOOLS:
            assert listed[name]["inputSchema"]  # never schema-less
            assert _harness.REGISTRY[name].schema
