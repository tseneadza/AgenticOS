"""Phase 15b — filesystem domain: root-scoped policy, guard, capabilities, MCP door.

Mirrors test_phase15a_system_mcp.py. Everything runs against pytest tmp dirs —
no real user files are ever touched. The kwargs-payload regression class is
the critical one: dispatch() calls capabilities with ``func(**arguments)``,
and the original harness only saw positional payloads, so keyword calls
bypassed root scoping entirely. That hole is now closed at the harness layer
(first-parameter capture); these tests keep it closed.
"""
from __future__ import annotations

import pytest

from core.constitution import (
    ApprovalRequired,
    Constitution,
    ConstitutionViolation,
    _merge_system_mcp,
)
from tools import osa_system_mcp
from tools.system import _harness, _policy, fs_mcp


# --------------------------------------------------------------------------- #
# Fixtures — hermetic constitution rooted in tmp dirs
# --------------------------------------------------------------------------- #
@pytest.fixture()
def fs_env(tmp_path):
    """(root, scratch, outside) dirs + a constitution scoped to them."""
    root = tmp_path / "root"
    scratch = root / "scratch"
    outside = tmp_path / "outside"
    for d in (root, scratch, outside):
        d.mkdir()
    c = Constitution()
    c.system_mcp = _merge_system_mcp(
        {"fs": {"allowed_roots": [str(root)], "scratch_root": str(scratch)}}
    )
    return root, scratch, outside, c


@pytest.fixture(autouse=True)
def _inject(fs_env):
    """Pin the harness to the tmp-scoped constitution for every test."""
    _harness.set_constitution(fs_env[3])
    yield
    _harness.set_constitution(None)


def _eval(name, effect, auto, payload, constitution):
    return _policy.evaluate(
        name=name, effect=effect, auto=auto, payload=payload, constitution=constitution
    ).decision


# --------------------------------------------------------------------------- #
# Policy — pure decision logic (design §4.2)
# --------------------------------------------------------------------------- #
class TestFsPolicy:
    def test_read_inside_root_allows(self, fs_env):
        root, _, _, c = fs_env
        assert _eval("fs.read_file", "read", True, str(root / "a.txt"), c) == "allow"

    def test_read_outside_root_denies(self, fs_env):
        *_, outside, c = fs_env
        assert _eval("fs.read_file", "read", True, str(outside / "a.txt"), c) == "deny"

    def test_write_inside_scratch_allows(self, fs_env):
        _, scratch, _, c = fs_env
        assert _eval("fs.write_file", "mutate", False, str(scratch / "n.txt"), c) == "allow"

    def test_write_inside_root_not_scratch_approves(self, fs_env):
        root, _, _, c = fs_env
        assert _eval("fs.write_file", "mutate", False, str(root / "n.txt"), c) == "approve"

    def test_write_outside_root_denies(self, fs_env):
        *_, outside, c = fs_env
        assert _eval("fs.write_file", "mutate", False, str(outside / "n.txt"), c) == "deny"

    def test_delete_inside_root_approves(self, fs_env):
        root, _, _, c = fs_env
        assert _eval("fs.delete", "irreversible", False, str(root / "a.txt"), c) == "approve"

    def test_move_outside_root_denies(self, fs_env):
        *_, outside, c = fs_env
        assert _eval("fs.move", "irreversible", False, str(outside / "a"), c) == "deny"

    def test_empty_path_allows_through_to_body_error(self, fs_env):
        assert _eval("fs.read_file", "read", True, "", fs_env[3]) == "allow"

    def test_symlink_escape_is_outside(self, fs_env):
        root, _, outside, c = fs_env
        (root / "link").symlink_to(outside)
        assert _eval("fs.read_file", "read", True, str(root / "link" / "x"), c) == "deny"

    def test_effect_mode_still_root_scoped(self, fs_env):
        root, scratch, outside, _ = fs_env
        c = Constitution()
        c.system_mcp = _merge_system_mcp(
            {
                "mode": "effect",
                "fs": {"allowed_roots": [str(root)], "scratch_root": str(scratch)},
            }
        )
        assert _eval("fs.read_file", "read", True, str(outside / "a"), c) == "deny"
        assert _eval("fs.read_file", "read", True, str(root / "a"), c) == "allow"
        assert _eval("fs.delete", "irreversible", False, str(root / "a"), c) == "approve"


# --------------------------------------------------------------------------- #
# CRITICAL regression — keyword-arg calls must hit the same guard
# --------------------------------------------------------------------------- #
class TestKwargsPayloadRegression:
    def test_read_kwarg_outside_root_blocked(self, fs_env):
        *_, outside, _ = fs_env
        with pytest.raises(ConstitutionViolation):
            fs_mcp.read_file(path=str(outside / "secret.txt"))

    def test_read_positional_outside_root_blocked(self, fs_env):
        *_, outside, _ = fs_env
        with pytest.raises(ConstitutionViolation):
            fs_mcp.read_file(str(outside / "secret.txt"))

    def test_delete_kwarg_outside_root_blocked_even_approved(self, fs_env):
        *_, outside, _ = fs_env
        victim = outside / "keepme.txt"
        victim.write_text("still here")
        with pytest.raises(ConstitutionViolation):
            fs_mcp.delete(path=str(victim), approved=True)
        assert victim.exists()

    def test_write_kwarg_non_scratch_needs_approval(self, fs_env):
        root, *_ = fs_env
        with pytest.raises(ApprovalRequired):
            fs_mcp.write_file(path=str(root / "n.txt"), content="x")

    def test_run_command_kwarg_still_gated(self, fs_env):
        from tools.system import macos_mcp

        with pytest.raises(ApprovalRequired):
            macos_mcp.run_command(command="definitely-not-allowlisted --flag")

    def test_payload_of_prefers_first_param_kwarg(self):
        assert _harness._payload_of("fs.read_file", (), {"path": "/x"}, "path") == "/x"
        assert _harness._payload_of("fs.search", (), {"root": "/r", "pattern": "*"}, "root") == "/r"
        assert _harness._payload_of("x", ("/pos",), {}, "path") == "/pos"


# --------------------------------------------------------------------------- #
# Guarded capabilities — in-process door
# --------------------------------------------------------------------------- #
class TestFsCapabilities:
    def test_read_file(self, fs_env):
        root, *_ = fs_env
        f = root / "hello.txt"
        f.write_text("hi tony")
        out = fs_mcp.read_file(str(f))
        assert out["ok"] and out["content"] == "hi tony" and not out["truncated"]

    def test_read_file_missing(self, fs_env):
        root, *_ = fs_env
        out = fs_mcp.read_file(str(root / "nope.txt"))
        assert not out["ok"]

    def test_list_dir_and_search(self, fs_env):
        root, *_ = fs_env
        (root / "a.md").write_text("a")
        (root / "sub").mkdir()
        (root / "sub" / "b.md").write_text("b")
        listing = fs_mcp.list_dir(str(root))
        assert listing["ok"] and {e["name"] for e in listing["entries"]} >= {"a.md", "sub"}
        found = fs_mcp.search(str(root), "*.md")
        assert found["ok"] and len(found["matches"]) == 2

    def test_write_in_scratch_auto_runs(self, fs_env):
        _, scratch, *_ = fs_env
        out = fs_mcp.write_file(str(scratch / "note.txt"), "auto")
        assert out["ok"] and (scratch / "note.txt").read_text() == "auto"

    def test_write_elsewhere_needs_then_takes_approval(self, fs_env):
        root, *_ = fs_env
        target = root / "docs" / "n.txt"
        with pytest.raises(ApprovalRequired):
            fs_mcp.write_file(str(target), "gated")
        out = fs_mcp.write_file(str(target), "gated", approved=True)
        assert out["ok"] and target.read_text() == "gated"

    def test_append(self, fs_env):
        _, scratch, *_ = fs_env
        p = scratch / "log.txt"
        fs_mcp.append(str(p), "one")
        fs_mcp.append(str(p), "-two")
        assert p.read_text() == "one-two"

    def test_move_approved_inside_roots(self, fs_env):
        root, *_ = fs_env
        src = root / "old.txt"
        src.write_text("m")
        dst = root / "sub" / "new.txt"
        out = fs_mcp.move(str(src), str(dst), approved=True)
        assert out["ok"] and dst.read_text() == "m" and not src.exists()

    def test_move_dst_outside_roots_blocked_even_approved(self, fs_env):
        root, _, outside, _ = fs_env
        src = root / "stay.txt"
        src.write_text("s")
        with pytest.raises(ConstitutionViolation):
            fs_mcp.move(str(src), str(outside / "escaped.txt"), approved=True)
        assert src.exists() and not (outside / "escaped.txt").exists()

    def test_delete_refuses_non_empty_dir(self, fs_env):
        root, *_ = fs_env
        d = root / "full"
        d.mkdir()
        (d / "x").write_text("x")
        out = fs_mcp.delete(str(d), approved=True)
        assert not out["ok"] and d.exists()

    def test_delete_file_and_empty_dir(self, fs_env):
        root, *_ = fs_env
        f = root / "gone.txt"
        f.write_text("g")
        assert fs_mcp.delete(str(f), approved=True)["ok"] and not f.exists()
        d = root / "empty"
        d.mkdir()
        assert fs_mcp.delete(str(d), approved=True)["ok"] and not d.exists()


# --------------------------------------------------------------------------- #
# MCP door — dispatch + parity
# --------------------------------------------------------------------------- #
class TestMcpDoor:
    FS_TOOLS = {"fs.read_file", "fs.list_dir", "fs.search", "fs.write_file",
                "fs.append", "fs.move", "fs.delete"}

    def test_registry_and_tool_list_parity(self):
        listed = {t["name"] for t in osa_system_mcp.build_tool_list()}
        assert self.FS_TOOLS <= listed
        for name in self.FS_TOOLS:
            assert _harness.REGISTRY[name].schema  # never schema-less

    def test_dispatch_read_inside_root(self, fs_env):
        root, *_ = fs_env
        f = root / "d.txt"
        f.write_text("via mcp")
        out = osa_system_mcp.dispatch("fs.read_file", {"path": str(f)})
        assert out.get("ok") and out["content"] == "via mcp"

    def test_dispatch_outside_root_blocked(self, fs_env):
        *_, outside, _ = fs_env
        out = osa_system_mcp.dispatch("fs.read_file", {"path": str(outside / "s")})
        assert out.get("blocked") is True

    def test_dispatch_gated_write_needs_approval(self, fs_env):
        root, *_ = fs_env
        out = osa_system_mcp.dispatch(
            "fs.write_file", {"path": str(root / "n.txt"), "content": "x"}
        )
        assert out.get("needs_approval") is True
        assert not (root / "n.txt").exists()

    def test_dispatch_strips_self_approval(self, fs_env):
        root, *_ = fs_env
        victim = root / "keep.txt"
        victim.write_text("k")
        out = osa_system_mcp.dispatch(
            "fs.delete", {"path": str(victim), "approved": True}
        )
        assert out.get("needs_approval") is True
        assert victim.exists()

    def test_dispatch_scratch_write_auto_runs(self, fs_env):
        _, scratch, *_ = fs_env
        out = osa_system_mcp.dispatch(
            "fs.write_file", {"path": str(scratch / "mcp.txt"), "content": "ok"}
        )
        assert out.get("ok") and (scratch / "mcp.txt").read_text() == "ok"
