"""Phase 17a — TOOL_SPECS registry + generated Self prompt.

Docs: PHASE17_OSA_SELF_MODEL.md §5.1 and §7 (Sub-phase 17a row).

These tests pin four properties per the design:

1. **Registry ↔ toolbox parity.** Every bound tool has a spec and vice versa
   (no silent drift). Every ``method`` on a spec exists on OSAToolbox.
2. **LOCAL flag consistency.** ``spec.local`` is truthful — matches
   ``LOCAL_TOOL_NAMES`` exactly.
3. **Phrase preservation.** The battle-tuned prompt phrasings from the retired
   OSA_SYSTEM mapping paragraph (iMessage handle-confirm, mail address-confirm,
   full-claude-id switching, arming-pattern call-first) still appear in the
   rendered cloud prompt. §6.1 regression trap.
4. **Local prompt is clean.** A local pin's rendered prompt names NO
   cloud-only tools — the 07-23 hallucinated-capability fix.

Plus one soft consistency check (spec.guard vs the Constitution's
approval_required list) — the Constitution stays authority; a divergence here
is a spec typo, not a policy change.
"""
from __future__ import annotations

import pytest

from agents import osa_agent as osa
from agents.osa_agent import TOOL_SPECS, LOCAL_TOOL_NAMES, OSAToolbox
from agents.osa_agent import render_tool_map, _prompt_with_tool_manifest


# ── 1. parity ────────────────────────────────────────────────────────────────


def test_every_spec_method_exists_on_toolbox():
    tb = OSAToolbox()
    for spec in TOOL_SPECS:
        assert hasattr(tb, spec.method), f"OSAToolbox missing {spec.method}"


def test_registry_and_build_tools_are_bijective():
    tb = OSAToolbox()
    bound = {t.name for t in osa.build_tools(tb)}
    specs = {s.name for s in TOOL_SPECS}
    assert bound == specs, (
        f"registry↔toolbox drift; "
        f"only in build_tools: {sorted(bound - specs)}, "
        f"only in TOOL_SPECS: {sorted(specs - bound)}"
    )


def test_spec_names_unique():
    names = [s.name for s in TOOL_SPECS]
    assert len(names) == len(set(names))


# ── 2. local-flag consistency ────────────────────────────────────────────────


def test_local_flag_matches_LOCAL_TOOL_NAMES():
    from_specs = {s.name for s in TOOL_SPECS if s.local}
    assert from_specs == LOCAL_TOOL_NAMES, (
        f"spec.local ≠ LOCAL_TOOL_NAMES; "
        f"only in specs: {sorted(from_specs - LOCAL_TOOL_NAMES)}, "
        f"only in LOCAL_TOOL_NAMES: {sorted(LOCAL_TOOL_NAMES - from_specs)}"
    )


# ── 3. phrase-preservation snapshot ──────────────────────────────────────────


PRESERVED_PHRASES = [
    # iMessage handle-confirm
    "must show the actual handle, never just the name",
    # mail address-confirm
    "must show the actual address",
    # full-claude-id switching (rendered from switch_model.usage_note)
    "guessing one",
    # arming pattern (still in OSA_SYSTEM prose, must not be lost)
    "ALWAYS CALL THE TOOL",
    "DENIED",
    # BLOCKED honesty rule
    "BLOCKED",
]


def _cloud_prompt() -> str:
    tb = OSAToolbox()
    return _prompt_with_tool_manifest(osa.build_tools(tb, only=None))


def test_all_battle_tuned_phrases_survive_in_cloud_prompt():
    prompt = _cloud_prompt()
    missing = [p for p in PRESERVED_PHRASES if p not in prompt]
    assert not missing, f"regressed phrases: {missing}"


def test_cloud_prompt_includes_generated_mapping_and_roster():
    prompt = _cloud_prompt()
    assert "How to map requests to tools" in prompt
    assert "Never claim you have no tools" in prompt
    # roster names all bound tools
    for spec in TOOL_SPECS:
        assert f"- {spec.name}:" in prompt or f"- {spec.name}\n" in prompt


# ── 4. local prompt hides cloud-only tools ───────────────────────────────────


def test_local_prompt_names_no_cloud_only_tools():
    """The generated mapping + roster must not name cloud-only tools.

    OSA_SYSTEM prose may still name them (the "don't route around your
    guard" clause deliberately cites run_command/rm as an example — that
    is behavioral guidance, not capability advertisement). We slice the
    generated sections and only check those.
    """
    tb = OSAToolbox()
    local_tools = osa.build_tools(tb, only=LOCAL_TOOL_NAMES)
    prompt = _prompt_with_tool_manifest(local_tools)
    generated = prompt.split("How to map requests to tools:", 1)[1]
    cloud_only = {s.name for s in TOOL_SPECS if not s.local}
    leaks = sorted(n for n in cloud_only if n in generated)
    assert not leaks, f"generated sections mention cloud-only tools: {leaks}"


def test_render_tool_map_filters_to_bound_subset():
    text = render_tool_map(TOOL_SPECS, only=LOCAL_TOOL_NAMES)
    assert "run_command" not in text
    assert "delete_file" not in text
    assert "move_file" not in text
    assert "send_message" in text  # a local tool WITH an approval note


# ── 5. guard-vs-Constitution soft consistency ────────────────────────────────


def test_spec_guard_kinds_are_valid():
    for s in TOOL_SPECS:
        assert s.guard in {"free", "approval", "blocked-able"}, s


def test_approval_tools_align_with_constitution_intent():
    """Every send_/delete_/move_ tool must be marked 'approval' at minimum.

    The Constitution's approval_required list is the enforcement authority; this
    test only catches spec typos (a shell tool marked 'free' would be wrong).
    """
    for s in TOOL_SPECS:
        if s.name in {"send_message", "send_mail", "reply_mail",
                      "delete_file", "move_file", "run_command"}:
            assert s.guard == "approval", (s.name, s.guard)
