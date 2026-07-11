"""Phase 15a — OSA System MCP: harness, policy, capabilities, aggregator, OSA wiring.

Headless per the voice-test pattern (design §9): iTerm2 is mocked; the only
real subprocess calls are harmless ``echo``/``date`` runs. The guard tests
are the core — allow / approve / deny per mode, and the two doors (OSA
in-process + MCP dispatch) proven equally gated.
"""
from __future__ import annotations

import pytest

from core.constitution import (
    ApprovalRequired,
    Constitution,
    ConstitutionViolation,
    DEFAULT_SYSTEM_MCP,
    _merge_system_mcp,
)
from tools import osa_system_mcp
from tools.system import _harness, _policy, macos_mcp


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture()
def strict_constitution() -> Constitution:
    """A Constitution with the default (strict) system_mcp block, no YAML."""
    return Constitution()


@pytest.fixture()
def effect_constitution() -> Constitution:
    """A Constitution flipped to effect mode."""
    c = Constitution()
    c.system_mcp = _merge_system_mcp({"mode": "effect"})
    return c


@pytest.fixture(autouse=True)
def _inject_constitution(strict_constitution):
    """Pin the harness to a hermetic Constitution for every test."""
    _harness.set_constitution(strict_constitution)
    yield
    _harness.set_constitution(None)


# --------------------------------------------------------------------------- #
# Policy (pure decision logic)
# --------------------------------------------------------------------------- #
class TestPolicy:
    def _run_cmd(self, payload: str, constitution: Constitution) -> str:
        return _policy.evaluate(
            name="macos.run_command",
            effect="mutate",
            auto=False,
            payload=payload,
            constitution=constitution,
        ).decision

    def test_allowlisted_exact(self, strict_constitution):
        assert self._run_cmd("date", strict_constitution) == "allow"

    def test_allowlisted_prefix_word_boundary(self, strict_constitution):
        assert self._run_cmd("ls -la /tmp", strict_constitution) == "allow"
        # 'lsof' must NOT ride the 'ls' prefix — word boundary required.
        assert self._run_cmd("lsof -i :5130", strict_constitution) == "approve"

    def test_allowlisted_multiword(self, strict_constitution):
        assert self._run_cmd("git status", strict_constitution) == "allow"
        assert self._run_cmd("git push origin main", strict_constitution) == "approve"

    def test_non_allowlisted_approves(self, strict_constitution):
        assert self._run_cmd("echo hi", strict_constitution) == "approve"

    def test_denylist_always_denies(self, strict_constitution, effect_constitution):
        for c in (strict_constitution, effect_constitution):
            assert self._run_cmd("sudo rm -rf /", c) == "deny"
            assert self._run_cmd("echo hi > /dev/null", c) == "deny"

    def test_strict_auto_vs_gated(self, strict_constitution):
        auto = _policy.evaluate(
            name="macos.get_time", effect="read", auto=True,
            constitution=strict_constitution,
        )
        gated = _policy.evaluate(
            name="fs.write_file", effect="mutate", auto=False,
            payload="/tmp/x", constitution=strict_constitution,
        )
        assert auto.decision == "allow"
        assert gated.decision == "approve"

    def test_effect_mode_reads_allow_mutates_approve(self, effect_constitution):
        read = _policy.evaluate(
            name="fs.read_file", effect="read", auto=False,
            payload="/tmp/x", constitution=effect_constitution,
        )
        mut = _policy.evaluate(
            name="fs.write_file", effect="mutate", auto=False,
            payload="/tmp/x", constitution=effect_constitution,
        )
        assert read.decision == "allow"
        assert mut.decision == "approve"

    def test_effect_mode_run_command_still_allowlist_governed(self, effect_constitution):
        assert self._run_cmd("date", effect_constitution) == "allow"
        assert self._run_cmd("echo hi", effect_constitution) == "approve"


# --------------------------------------------------------------------------- #
# Constitution config merge
# --------------------------------------------------------------------------- #
class TestConstitutionMerge:
    def test_defaults_when_block_absent(self):
        c = Constitution()
        assert c.system_mcp["mode"] == "strict"
        assert "rm -rf" in c.system_mcp["terminal"]["denylist_patterns"]

    def test_partial_block_keeps_default_denylist(self):
        merged = _merge_system_mcp({"terminal": {"allowlist": ["date"]}})
        assert merged["terminal"]["allowlist"] == ["date"]
        assert merged["terminal"]["denylist_patterns"] == (
            DEFAULT_SYSTEM_MCP["terminal"]["denylist_patterns"]
        )

    def test_real_yaml_loads_strict(self):
        c = Constitution.load()
        assert c.system_mcp["mode"] in ("strict", "effect")
        assert c.system_mcp["terminal"]["allowlist"]
        assert "macos.run_command" in c.approval_required


# --------------------------------------------------------------------------- #
# Capabilities through the guard (the in-process door)
# --------------------------------------------------------------------------- #
class TestGuardedCapabilities:
    def test_get_time_runs_auto(self):
        out = macos_mcp.get_time()
        assert "iso" in out and "unix" in out

    def test_system_info_runs_auto(self):
        out = macos_mcp.system_info()
        assert "hostname" in out and "os" in out

    def test_run_command_allowlisted_runs(self):
        out = macos_mcp.run_command("date")
        assert out["ok"] is True and out["returncode"] == 0

    def test_run_command_non_allowlisted_raises_approval(self):
        with pytest.raises(ApprovalRequired):
            macos_mcp.run_command("echo hello-15a")

    def test_run_command_approved_runs(self):
        out = macos_mcp.run_command("echo hello-15a", approved=True)
        assert out["ok"] is True
        assert "hello-15a" in out["stdout"]

    def test_run_command_denylisted_blocks_even_approved(self):
        with pytest.raises(ConstitutionViolation):
            macos_mcp.run_command("sudo whoami", approved=True)

    def test_run_command_pane_surface(self, monkeypatch):
        from tools import iterm2_tool

        monkeypatch.setattr(iterm2_tool, "run_in_pane", lambda cmds, approved=False: "sess-1")
        monkeypatch.setattr(iterm2_tool, "last_pane_lines", lambda n=15: ["out line"])
        monkeypatch.setattr(macos_mcp.time, "sleep", lambda s: None)
        out = macos_mcp.run_command("date", surface="pane")
        assert out["ok"] is True
        assert out["session_id"] == "sess-1"
        assert out["output_tail"] == ["out line"]

    def test_empty_command(self):
        out = macos_mcp.run_command("   ")
        assert out["ok"] is False


# --------------------------------------------------------------------------- #
# Registry + aggregator (the MCP door)
# --------------------------------------------------------------------------- #
class TestAggregator:
    def test_registry_list_tools_parity(self):
        tools = osa_system_mcp.build_tool_list()
        names = {t["name"] for t in tools}
        assert names == set(_harness.REGISTRY)
        for t in tools:
            assert t["inputSchema"].get("type") == "object"
            assert t["description"]

    def test_expected_15a_capabilities_registered(self):
        for name in ("macos.get_time", "macos.system_info", "macos.run_command"):
            assert name in _harness.REGISTRY

    def test_dispatch_read(self):
        out = osa_system_mcp.dispatch("macos.get_time")
        assert "iso" in out

    def test_dispatch_unknown(self):
        out = osa_system_mcp.dispatch("nope.nothing")
        assert "error" in out and "known" in out

    def test_dispatch_gated_returns_needs_approval(self):
        out = osa_system_mcp.dispatch("macos.run_command", {"command": "echo x"})
        assert out.get("needs_approval") is True

    def test_dispatch_denylisted_returns_blocked(self):
        out = osa_system_mcp.dispatch("macos.run_command", {"command": "sudo x"})
        assert out.get("blocked") is True

    def test_dispatch_strips_client_self_approval(self):
        """SECURITY: an external client passing approved=true must NOT bypass."""
        out = osa_system_mcp.dispatch(
            "macos.run_command", {"command": "echo x", "approved": True}
        )
        assert out.get("needs_approval") is True

    def test_dispatch_bad_arguments(self):
        out = osa_system_mcp.dispatch("macos.run_command", {"bogus_arg": 1})
        assert "error" in out


# --------------------------------------------------------------------------- #
# OSA toolbox wiring (approval bridge composition)
# --------------------------------------------------------------------------- #
class TestOSAWiring:
    def _toolbox(self, decision: str):
        from agents.osa_agent import OSAToolbox

        return OSAToolbox(
            constitution=Constitution(),
            approval_fn=lambda action, desc: decision,
        )

    def test_get_time_tool(self):
        out = self._toolbox("deny").get_time()
        assert "iso" in out

    def test_allowlisted_command_needs_no_approval(self):
        out = self._toolbox("deny").run_command("date")
        assert '"ok": true' in out

    def test_gated_command_denied(self):
        out = self._toolbox("deny").run_command("echo hi")
        assert out.startswith("DENIED:")
        assert "macos.run_command" in out

    def test_gated_command_approved_runs(self):
        out = self._toolbox("yes").run_command("echo hi-osa")
        assert "hi-osa" in out

    def test_denylisted_blocked_despite_approval(self):
        out = self._toolbox("yes").run_command("sudo whoami")
        assert out.startswith("BLOCKED:")

    def test_tools_registered_in_build_tools(self):
        from agents.osa_agent import build_tools

        names = {t.name for t in build_tools(self._toolbox("deny"))}
        assert {"get_time", "run_command"} <= names
