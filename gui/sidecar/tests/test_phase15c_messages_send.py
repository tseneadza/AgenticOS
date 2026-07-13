"""Phase 15c — iMessage SEND half: send_message + resolve_contact.

Mirrors test_phase15c_messages_mcp.py conventions. **No test ever runs a real
osascript** — subprocess.run is monkeypatched in every body-execution test, so
nothing is sent and Contacts.app never launches.

The regressions that live here:

* **KWARGS gating (payload rule)** — ``send_message(to=..., text=...)`` must be
  gated exactly like the positional form; the 15b harness bug made keyword
  calls invisible to policy.
* **Handles-only recipients** — a contact NAME must be rejected before any
  osascript runs: the guard's approval payload is the first param, so the
  human must always confirm the REAL handle, never an unresolved alias.
* **Argv-delivered user data** — message text/handles must ride osascript's
  argv, never be interpolated into the script source (AppleScript injection).
"""
from __future__ import annotations

import subprocess

import pytest

from core.constitution import ApprovalRequired, Constitution, _merge_system_mcp
from tools import osa_system_mcp
from tools.system import _harness, messages_mcp

_HANDLE = "+15551234567"
_EMAIL = "friend@example.com"
_TEXT = 'hello "world" \\ backslash'  # quote+backslash: injection canary


@pytest.fixture(autouse=True)
def _inject():
    """Pin the harness to a default (strict-mode) constitution per test."""
    c = Constitution()
    c.system_mcp = _merge_system_mcp({})
    _harness.set_constitution(c)
    yield
    _harness.set_constitution(None)


class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture()
def osascript_spy(monkeypatch):
    """Record every OSASCRIPT invocation; scriptable per-call results.

    ``open -ga <App>`` pre-launch calls (the -600 fix) are answered rc=0 and
    NOT recorded — assertions stay about osascript. time.sleep is stubbed so
    the cold-launch settle wait doesn't slow the suite.
    """
    calls = []
    results = []
    opens = []

    def fake_run(cmd, **kwargs):
        if cmd and cmd[0] == "open":
            opens.append(cmd)
            return _FakeProc()
        calls.append({"cmd": cmd, "kwargs": kwargs})
        if results:
            r = results.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        return _FakeProc()

    monkeypatch.setattr(messages_mcp.subprocess, "run", fake_run)
    monkeypatch.setattr(messages_mcp.time, "sleep", lambda *_: None)
    return calls, results


# --------------------------------------------------------------------------- #
# 1. Guard — send is gated in strict mode; kwargs regression
# --------------------------------------------------------------------------- #
class TestSendGuard:
    def test_positional_send_requires_approval(self, osascript_spy):
        calls, _ = osascript_spy
        with pytest.raises(ApprovalRequired):
            messages_mcp.send_message(_HANDLE, _TEXT)
        assert calls == []  # guard fired before any osascript

    def test_KWARGS_send_requires_approval(self, osascript_spy):
        """15b payload-rule regression: keyword form must be equally gated."""
        calls, _ = osascript_spy
        with pytest.raises(ApprovalRequired):
            messages_mcp.send_message(to=_HANDLE, text=_TEXT)
        assert calls == []

    def test_approval_payload_is_the_recipient(self):
        with pytest.raises(ApprovalRequired) as ei:
            messages_mcp.send_message(to=_HANDLE, text=_TEXT)
        assert _HANDLE in str(ei.value)

    def test_approved_call_runs(self, osascript_spy):
        calls, _ = osascript_spy
        out = messages_mcp.send_message(_HANDLE, "hi", approved=True)
        assert out["ok"] is True and len(calls) == 1

    def test_resolve_contact_is_auto_in_strict(self, osascript_spy):
        """Read capability — must run WITHOUT approval."""
        calls, results = osascript_spy
        results.append(_FakeProc(stdout="Mom|phone|+15550001111\n"))
        out = messages_mcp.resolve_contact("Mom")
        assert out["ok"] is True and len(calls) == 1


# --------------------------------------------------------------------------- #
# 2. Recipient validation — handles only, before any subprocess
# --------------------------------------------------------------------------- #
class TestRecipientValidation:
    @pytest.mark.parametrize("bad", ["Mom", "John Smith", "the group chat", "x@y"])
    def test_name_like_recipient_rejected_without_send(self, osascript_spy, bad):
        calls, _ = osascript_spy
        out = messages_mcp.send_message(bad, "hi", approved=True)
        assert out["ok"] is False and "resolve_contact" in out["error"]
        assert calls == []

    @pytest.mark.parametrize("good", [_HANDLE, "555-123-4567", "(555) 123 4567", _EMAIL])
    def test_handle_shapes_accepted(self, osascript_spy, good):
        out = messages_mcp.send_message(good, "hi", approved=True)
        assert out["ok"] is True

    def test_empty_recipient_and_text_rejected(self, osascript_spy):
        calls, _ = osascript_spy
        assert messages_mcp.send_message("", "hi", approved=True)["ok"] is False
        assert messages_mcp.send_message(_HANDLE, "  ", approved=True)["ok"] is False
        assert calls == []

    def test_oversized_text_rejected(self, osascript_spy):
        calls, _ = osascript_spy
        out = messages_mcp.send_message(_HANDLE, "x" * 5000, approved=True)
        assert out["ok"] is False and "too long" in out["error"]
        assert calls == []


# --------------------------------------------------------------------------- #
# 3. Send body — argv injection safety, SMS fallback, failure shapes
# --------------------------------------------------------------------------- #
class TestSendBody:
    def test_text_rides_argv_not_the_script(self, osascript_spy):
        """Injection defense: user text must NEVER appear in the -e script."""
        calls, _ = osascript_spy
        messages_mcp.send_message(_HANDLE, _TEXT, approved=True)
        cmd = calls[0]["cmd"]
        script = cmd[cmd.index("-e") + 1]
        assert _TEXT not in script
        assert "--" in cmd
        tail = cmd[cmd.index("--") + 1:]
        assert tail == [_HANDLE, _TEXT, "imessage"]

    def test_imessage_success_reports_service(self, osascript_spy):
        calls, _ = osascript_spy
        out = messages_mcp.send_message(_HANDLE, "hi", approved=True)
        assert out == {"ok": True, "to": _HANDLE, "service": "iMessage",
                       "note": "queued to Messages.app — delivery is not verified"}
        assert len(calls) == 1

    def test_sms_fallback_on_imessage_error(self, osascript_spy):
        calls, results = osascript_spy
        results.append(_FakeProc(returncode=1, stderr="Messages got an error"))
        results.append(_FakeProc(returncode=0))
        out = messages_mcp.send_message(_HANDLE, "hi", approved=True)
        assert out["ok"] is True and out["service"] == "SMS"
        assert len(calls) == 2
        assert calls[1]["cmd"][-1] == "sms"

    def test_both_services_fail_reports_both(self, osascript_spy):
        _, results = osascript_spy
        results.append(_FakeProc(returncode=1, stderr="no imsg"))
        results.append(_FakeProc(returncode=1, stderr="no sms"))
        out = messages_mcp.send_message(_HANDLE, "hi", approved=True)
        assert out["ok"] is False
        assert "no imsg" in out["error"] and "no sms" in out["error"]
        assert "Automation" in out["error"]

    def test_timeout_is_a_clean_error(self, osascript_spy):
        _, results = osascript_spy
        results.append(subprocess.TimeoutExpired(cmd="osascript", timeout=30))
        results.append(subprocess.TimeoutExpired(cmd="osascript", timeout=30))
        out = messages_mcp.send_message(_HANDLE, "hi", approved=True)
        assert out["ok"] is False and "timed out" in out["error"]

    def test_target_app_is_prelaunched(self, monkeypatch):
        """-600 regression (live-found 2026-07-12): 'tell application' can't
        LAUNCH an app from the sidecar's background context — each osascript
        must be preceded by an 'open -ga <App>' for its target app."""
        seq = []

        def fake_run(cmd, **kwargs):
            seq.append(cmd[0:3])
            return _FakeProc()

        monkeypatch.setattr(messages_mcp.subprocess, "run", fake_run)
        monkeypatch.setattr(messages_mcp.time, "sleep", lambda *_: None)
        messages_mcp.send_message(_HANDLE, "hi", approved=True)
        assert seq[0] == ["open", "-ga", "Messages"]
        assert seq[1][0] == "osascript"
        seq.clear()
        messages_mcp.resolve_contact("Mom")
        assert seq[0] == ["open", "-ga", "Contacts"]
        assert seq[1][0] == "osascript"


# --------------------------------------------------------------------------- #
# 4. resolve_contact body
# --------------------------------------------------------------------------- #
class TestResolveContact:
    def test_parses_pipe_lines(self, osascript_spy):
        _, results = osascript_spy
        results.append(_FakeProc(stdout=(
            "Mom|phone|+15550001111\n"
            "Mom|email|mom@example.com\n"
            "garbage line without pipes\n"
        )))
        out = messages_mcp.resolve_contact("Mom")
        assert out["ok"] is True and out["count"] == 2
        assert out["handles"][0] == {"name": "Mom", "kind": "phone", "handle": "+15550001111"}

    def test_name_rides_argv(self, osascript_spy):
        calls, results = osascript_spy
        results.append(_FakeProc(stdout=""))
        messages_mcp.resolve_contact('Mo"m')
        cmd = calls[0]["cmd"]
        script = cmd[cmd.index("-e") + 1]
        assert 'Mo"m' not in script and cmd[-1] == 'Mo"m'

    def test_no_matches_is_ok_zero(self, osascript_spy):
        _, results = osascript_spy
        results.append(_FakeProc(stdout=""))
        out = messages_mcp.resolve_contact("Nobody")
        assert out["ok"] is True and out["count"] == 0

    def test_osascript_failure_mentions_automation(self, osascript_spy):
        _, results = osascript_spy
        results.append(_FakeProc(returncode=1, stderr="not authorized"))
        out = messages_mcp.resolve_contact("Mom")
        assert out["ok"] is False and "Automation" in out["error"]

    def test_empty_name_rejected(self, osascript_spy):
        calls, _ = osascript_spy
        assert messages_mcp.resolve_contact("  ")["ok"] is False
        assert calls == []


# --------------------------------------------------------------------------- #
# 5. Dispatch parity — external clients cannot self-approve a send
# --------------------------------------------------------------------------- #
class TestDispatch:
    def test_dispatch_send_needs_approval(self, osascript_spy):
        calls, _ = osascript_spy
        out = osa_system_mcp.dispatch(
            "messages.send_message", {"to": _HANDLE, "text": "hi"}
        )
        assert out.get("needs_approval") is True and calls == []

    def test_dispatch_strips_client_approved(self, osascript_spy):
        """SECURITY: 'approved': true from an MCP client must NOT bypass."""
        calls, _ = osascript_spy
        out = osa_system_mcp.dispatch(
            "messages.send_message",
            {"to": _HANDLE, "text": "hi", "approved": True},
        )
        assert out.get("needs_approval") is True and calls == []

    def test_dispatch_resolve_contact_runs(self, osascript_spy):
        _, results = osascript_spy
        results.append(_FakeProc(stdout="Mom|phone|+15550001111\n"))
        out = osa_system_mcp.dispatch("messages.resolve_contact", {"name": "Mom"})
        assert out["ok"] is True and out["count"] == 1

    def test_both_tools_listed_with_schemas(self):
        tools = {t["name"]: t for t in osa_system_mcp.build_tool_list()}
        for name in ("messages.send_message", "messages.resolve_contact"):
            assert name in tools and tools[name]["inputSchema"].get("type") == "object"
