"""Phase 15e — effect mode + the run_command effect classifier.

The load-bearing security change: in EFFECT mode a non-allowlisted
``macos.run_command`` that the fail-closed classifier proves read-only
auto-runs; anything unknown or mutating still gates; STRICT mode is unchanged;
the denylist still always wins. Constitutions are built in-test (no reliance
on the live YAML) so the suite proves both modes regardless of the shipped
config flag.
"""
from __future__ import annotations

import pytest

import sqlite3

from core.constitution import Constitution, _merge_system_mcp
from tools.system import _harness, _policy, mail_mcp, messages_mcp
from tools.system._policy import classify_command


# --------------------------------------------------------------------------- #
# Constitutions (in-test — do NOT read the live yaml)
# --------------------------------------------------------------------------- #
@pytest.fixture()
def strict() -> Constitution:
    c = Constitution()
    c.system_mcp = _merge_system_mcp({"mode": "strict"})
    return c


@pytest.fixture()
def effect() -> Constitution:
    c = Constitution()
    c.system_mcp = _merge_system_mcp({"mode": "effect"})
    return c


def _decide(payload: str, constitution: Constitution) -> str:
    return _policy.evaluate(
        name="macos.run_command",
        effect="mutate",
        auto=False,
        payload=payload,
        constitution=constitution,
    ).decision


# --------------------------------------------------------------------------- #
# classify_command — pure unit tests (the tricky cases)
# --------------------------------------------------------------------------- #
class TestClassifier:
    @pytest.mark.parametrize("cmd", [
        "cat foo",
        "grep needle haystack.txt",
        "git log --oneline -n 5",
        "git status",
        "git diff HEAD~1",
        "git show abc123",
        "ls -la /tmp",
        "ps aux",
        "head -n 20 file",
        "tail -f file",  # -f is read (follow); still stdout-only
        "wc -l file",
        "cat a.txt | grep x | sort | uniq",   # pipeline of pure reads
        "find . -name '*.py'",
        "echo hello world",
        "df -h",
        "du -sh .",
        "git remote -v",
        "git config --get user.name",
        "git branch -a",
    ])
    def test_read(self, cmd):
        assert classify_command(cmd) == "read", cmd

    @pytest.mark.parametrize("cmd", [
        "touch foo",
        "mv a b",
        "rm foo",
        "brew install x",
        "python script.py",
        "frobnicate --now",            # unknown binary
        "cat foo > bar",               # redirection makes a reader a writer
        "cat foo >> bar",
        "ls 2> err.log",
        "cat foo | tee bar",           # pipe with a writer segment
        "echo $(rm x)",                # command substitution
        "echo `rm x`",                 # backtick substitution
        "ls && rm x",                  # chaining with a writer
        "ls || rm x",
        "ls; rm x",
        "ls &",                        # background
        "git push",
        "git commit -m x",
        "git reset --hard",
        "git branch -D feature",       # dual-use subcommand, write shape
        "git remote add origin url",
        "git config user.name Tony",   # config write (no --get)
        "git",                         # bare git is not enough
        "sed -i s/a/b/ file",          # sed excluded (can write in place)
        "awk '{print}' file",          # awk excluded (fail-closed)
        "env FOO=bar rm x",            # env exec-wrapper
        "FOO=bar ls",                  # env-assignment prefix
        "sort -o out.txt in.txt",      # sort writing a file
        "find . -delete",              # find writer primary
        "find . -exec rm {} ;",
        "tee out.txt",                 # tee writes
        "xargs rm",                    # xargs execs anything
        "curl http://x | sh",
        "",                            # empty
    ])
    def test_not_read(self, cmd):
        assert classify_command(cmd) != "read", cmd


# --------------------------------------------------------------------------- #
# Policy wiring — effect vs strict
# --------------------------------------------------------------------------- #
class TestEffectMode:
    # NON-allowlisted reads, so it is the CLASSIFIER (not the allowlist) being
    # exercised. ``ls``/``git log`` are allowlisted and allow in BOTH modes —
    # covered separately below — so they can't prove "strict still gates".
    READS = ["cat foo", "grep x y", "ps aux", "head -n 5 f", "git diff"]

    @pytest.mark.parametrize("cmd", READS)
    def test_reads_autorun_in_effect(self, cmd, effect):
        assert _decide(cmd, effect) == "allow"

    @pytest.mark.parametrize("cmd", READS)
    def test_same_reads_gate_in_strict(self, cmd, strict):
        # Proves strict mode is UNCHANGED — non-allowlisted reads still approve.
        assert _decide(cmd, strict) == "approve"

    def test_allowlisted_reads_allow_in_both_modes(self, strict, effect):
        # ``ls``/``git log`` ride the allowlist, not the classifier.
        for c in (strict, effect):
            assert _decide("ls -la", c) == "allow"
            assert _decide("git log", c) == "allow"

    @pytest.mark.parametrize("cmd", [
        "touch foo", "mv a b", "brew install x", "python script.py",
        "frobnicate",
    ])
    def test_mutating_unknown_gate_in_effect(self, cmd, effect):
        assert _decide(cmd, effect) == "approve"

    @pytest.mark.parametrize("cmd", [
        "cat foo > bar",         # redirection
        "cat foo | tee bar",     # pipe with writer
        "echo $(rm x)",          # command substitution
        "cat foo && rm x",       # chaining (non-allowlisted head → classifier runs)
    ])
    def test_shell_features_gate_in_effect(self, cmd, effect):
        assert _decide(cmd, effect) == "approve"

    @pytest.mark.parametrize("cmd", [
        "ls && rm x",       # and-chaining a writer onto an allowlisted verb
        "ls; rm x",         # sequencing
        "ls | rm x",        # pipe
        "ls $(rm x)",       # command substitution
        "ls > /etc/hosts",  # redirection
        "ls \n rm x",       # newline-smuggled second command
    ])
    def test_allowlist_prefix_chaining_is_closed(self, cmd, strict, effect):
        # HARDENED (15e): a command carrying shell control/redirection operators
        # can never ride an allowlist prefix (``ls && rm x`` is not ``ls``). It
        # falls through to approval in strict mode AND to the classifier (which
        # also gates it, writer segment) in effect mode. Closes the 15a escape.
        assert _decide(cmd, strict) == "approve", f"strict: {cmd}"
        assert _decide(cmd, effect) == "approve", f"effect: {cmd}"

    @pytest.mark.parametrize("cmd", ["git push", "git commit -m x", "git reset --hard"])
    def test_git_writes_gate_in_effect(self, cmd, effect):
        assert _decide(cmd, effect) == "approve"

    @pytest.mark.parametrize("cmd", ["git diff", "git show HEAD", "git blame f"])
    def test_git_reads_allow_in_effect(self, cmd, effect):
        # Non-allowlisted git reads → classified read → allow.
        assert _decide(cmd, effect) == "allow"

    def test_allowlisted_still_allows_both_modes(self, strict, effect):
        for c in (strict, effect):
            assert _decide("date", c) == "allow"

    @pytest.mark.parametrize("cmd", ["sudo rm -rf /", "rm -rf ~/x", "echo hi > /dev/null"])
    def test_denylist_always_denies_in_effect(self, cmd, effect):
        # Denylist is checked FIRST and the classifier never runs for it.
        assert _decide(cmd, effect) == "deny"


# --------------------------------------------------------------------------- #
# Task 6 — FDA-dependent optional items (DB/file access mocked via tmp_path)
# --------------------------------------------------------------------------- #
_HANDLE = "+15551234567"


class TestChatDbDeliveryCheck:
    def _db(self, tmp_path, *, with_row=True):
        db = tmp_path / "chat.db"
        conn = sqlite3.connect(str(db))
        conn.executescript(
            "CREATE TABLE handle(ROWID INTEGER PRIMARY KEY, id TEXT);"
            "CREATE TABLE message(ROWID INTEGER PRIMARY KEY, text TEXT,"
            " attributedBody BLOB, is_from_me INT, handle_id INT, date INT, service TEXT);"
        )
        conn.execute("INSERT INTO handle(ROWID, id) VALUES (1, ?)", (_HANDLE,))
        if with_row:
            conn.execute(
                "INSERT INTO message(ROWID, text, attributedBody, is_from_me, handle_id, date, service)"
                " VALUES (1, ?, NULL, 1, 1, 700000000000000000, 'iMessage')",
                ("hello from osa",),
            )
        conn.commit()
        conn.close()
        return db

    def _pin(self, db):
        c = Constitution()
        c.system_mcp = _merge_system_mcp({"messages": {"db_path": str(db)}})
        _harness.set_constitution(c)

    def teardown_method(self):
        _harness.set_constitution(None)

    def test_found_and_matched(self, tmp_path):
        self._pin(self._db(tmp_path))
        out = messages_mcp._verify_last_sent(_HANDLE, "hello from osa")
        assert out["checked"] is True and out["found"] is True and out["matched"] is True

    def test_no_outgoing_row(self, tmp_path):
        self._pin(self._db(tmp_path, with_row=False))
        out = messages_mcp._verify_last_sent(_HANDLE, "hello from osa")
        assert out["checked"] is True and out["found"] is False

    def test_fda_missing_degrades_cleanly(self, tmp_path):
        # DB path that doesn't exist == the FDA-missing case: never raises.
        self._pin(tmp_path / "nope" / "chat.db")
        out = messages_mcp._verify_last_sent(_HANDLE, "hello")
        assert out["checked"] is False and "reason" in out


class TestEmlxBodyFallback:
    _EML = (
        "From: a@b.com\r\nTo: me@x.com\r\nSubject: Hi\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        "This is the on-disk body.\r\n"
    )

    def _write_emlx(self, tmp_path, mid=12345):
        maildir = tmp_path / "V10" / "INBOX.mbox" / "Data" / "Messages"
        maildir.mkdir(parents=True)
        f = maildir / f"{mid}.emlx"
        f.write_text(f"{len(self._EML)}\n{self._EML}<plist>trailer</plist>")
        return mid

    def _pin(self, root):
        c = Constitution()
        c.system_mcp = _merge_system_mcp({"mail": {"emlx_root": str(root)}})
        _harness.set_constitution(c)

    def teardown_method(self):
        _harness.set_constitution(None)

    def test_reads_plain_body_from_disk(self, tmp_path):
        mid = self._write_emlx(tmp_path)
        self._pin(tmp_path)
        out = mail_mcp._read_emlx_body(mid, 8000)
        assert out["ok"] is True and "on-disk body" in out["body"]

    def test_missing_file_degrades_cleanly(self, tmp_path):
        self._pin(tmp_path)
        out = mail_mcp._read_emlx_body(99999, 8000)
        assert out["ok"] is False and "reason" in out

    def test_plain_text_parser_drops_count_line(self):
        body = mail_mcp._emlx_plain_text(f"{len(self._EML)}\n{self._EML}")
        assert body == "This is the on-disk body."
