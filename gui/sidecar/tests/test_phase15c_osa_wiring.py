"""Phase 15c — OSA toolbox wiring for the System MCP fs + messages capabilities.

OSA now exposes the fs (read/list/search/write/append/move/delete) and messages
(read/search/list) capabilities as its own tools, bridged through
``_run_capability`` so gated ops raise ApprovalRequired → OSA's approval_fn →
retry with approved=True. Reads + scratch writes auto-run; destructive ops need
a 'yes'. Everything runs against tmp dirs — no real user files.

Inline authorship (spend-limit fallback, CLAUDE.md rule 5): this wiring does not
touch the security spine (_harness/_policy/constitution), so no security-verifier
gate; tests written in-session rather than via the test-author subagent.
"""
from __future__ import annotations

import os

import pytest

from core.constitution import Constitution, _merge_system_mcp
from tools.system import _harness
import agents.osa_agent as osa


@pytest.fixture()
def fs_env(tmp_path):
    root = tmp_path / "root"
    scratch = root / "scratch"
    scratch.mkdir(parents=True)
    (root / "note.txt").write_text("hello from Tony")
    c = Constitution()
    c.system_mcp = _merge_system_mcp(
        {"fs": {"allowed_roots": [str(root)], "scratch_root": str(scratch)}}
    )
    return root, scratch, c


@pytest.fixture(autouse=True)
def _inject(fs_env):
    _harness.set_constitution(fs_env[2])
    yield
    _harness.set_constitution(None)


def _tb(decision="yes"):
    return osa.OSAToolbox(approval_fn=lambda name, desc: decision)


NEW_TOOLS = {
    "read_file", "list_dir", "search_files", "write_file", "append_file",
    "move_file", "delete_file", "read_messages", "search_messages",
    "list_recent_chats",
}


def test_new_tools_are_bound():
    names = {t.name for t in osa.build_tools(_tb())}
    assert NEW_TOOLS <= names, f"missing: {NEW_TOOLS - names}"


def test_read_and_list_run(fs_env):
    root, *_ = fs_env
    assert '"ok": true' in _tb().read_file(str(root / "note.txt"))
    assert "note.txt" in _tb().list_dir(str(root))


def test_scratch_write_auto_runs(fs_env):
    _, scratch, _ = fs_env
    assert '"ok": true' in _tb().write_file(str(scratch / "s.txt"), "data")


def test_write_outside_scratch_needs_yes(fs_env):
    root, *_ = fs_env
    assert _tb("no").write_file(str(root / "n.txt"), "x").startswith("DENIED")
    assert '"ok": true' in _tb("yes").write_file(str(root / "n.txt"), "x")


def test_delete_needs_yes(fs_env):
    root, *_ = fs_env
    (root / "gone.txt").write_text("bye")
    assert _tb("no").delete_file(str(root / "gone.txt")).startswith("DENIED")
    assert '"ok": true' in _tb("yes").delete_file(str(root / "gone.txt"))


def test_outside_root_is_blocked(fs_env, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    # Outside allowed_roots is a hard deny approval can't override -> BLOCKED.
    assert _tb("yes").read_file(str(outside)).startswith("BLOCKED")
