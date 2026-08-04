"""Attention brief (docs/OSA_ATTENTION_MODEL.md Phase B v1, 2026-08-04).

"Brief me" and the scheduled briefing now compose a profile-ranked attention
brief via core.llm, with compose_briefing() as the always-composable fallback.
These tests pin: the LLM path, every fallback path, profile seeding, dev-state
parsing, and post_briefing wiring. No network, no tokens - core.llm is
monkeypatched throughout.
"""
from __future__ import annotations

# Pre-warm numpy: compose_briefing()'s health probe can kick off a worker
# thread that lazily imports numpy; if a later test file's pytest.approx runs
# while that import is mid-flight it sees a partially initialized module
# (observed with test_phase14e_proactive's ioreg parse). Importing eagerly at
# collection time makes these tests hermetic (same precedent as 07-23).
import numpy  # noqa: F401

from gui.sidecar import osa_proactive as op


class _Result:
    def __init__(self, text: str):
        self.text = text
        self.tokens_used = 1
        self.cost_usd = 0.0
        self.provider = "anthropic"
        self.model = "test-model"


def test_fallback_when_model_unavailable(monkeypatch):
    from core import llm
    monkeypatch.setattr(llm, "resolve", lambda a: "claude-test")
    monkeypatch.setattr(llm, "is_available", lambda m: False)
    assert op.compose_attention_briefing() == op.compose_briefing()


def test_llm_composed_brief(monkeypatch, tmp_path):
    from core import llm, memory
    monkeypatch.setattr(op, "_PROFILE_PATH", tmp_path / "attention_profile.md")
    monkeypatch.setattr(llm, "resolve", lambda a: "claude-test")
    monkeypatch.setattr(llm, "is_available", lambda m: True)
    monkeypatch.setattr(memory, "cost_today", lambda: 0.0)
    captured = {}

    def fake_complete(messages, system=None, model=None, max_tokens=None):
        captured["system"] = system
        captured["user"] = messages[0]["content"]
        return _Result("Morning Tony, here is what matters.")

    monkeypatch.setattr(llm, "complete", fake_complete)
    text = op.compose_attention_briefing()
    assert text == "Morning Tony, here is what matters."
    # Context carries the three sources.
    assert "attention_profile" in captured["user"]
    assert "dev_state" in captured["user"]
    assert "system" in captured["user"]
    # Debauchery + flexibility clauses ride in the system prompt.
    assert "not safe for work" in captured["system"]
    assert "Behavior overrides" in captured["system"]


def test_empty_llm_reply_falls_back(monkeypatch, tmp_path):
    from core import llm, memory
    monkeypatch.setattr(op, "_PROFILE_PATH", tmp_path / "attention_profile.md")
    monkeypatch.setattr(llm, "resolve", lambda a: "claude-test")
    monkeypatch.setattr(llm, "is_available", lambda m: True)
    monkeypatch.setattr(memory, "cost_today", lambda: 0.0)
    monkeypatch.setattr(llm, "complete",
                        lambda *a, **k: _Result("   "))
    assert op.compose_attention_briefing() == op.compose_briefing()


def test_llm_error_falls_back(monkeypatch):
    from core import llm

    def boom(m):
        raise RuntimeError("boom")

    monkeypatch.setattr(llm, "resolve", lambda a: "claude-test")
    monkeypatch.setattr(llm, "is_available", boom)
    assert op.compose_attention_briefing() == op.compose_briefing()


def test_profile_seeds_default(monkeypatch, tmp_path):
    path = tmp_path / "attention_profile.md"
    monkeypatch.setattr(op, "_PROFILE_PATH", path)
    text = op._attention_profile()
    assert "Attention Profile" in text
    assert path.exists()
    # Second read returns the (possibly edited) file, not the default.
    path.write_text("# Edited by Tony\n")
    assert op._attention_profile() == "# Edited by Tony\n"


def test_dev_state_parses_top_session(monkeypatch, tmp_path):
    f = tmp_path / "CONTINUATION.md"
    f.write_text(
        "# SESSION X - TITLE\n\nintro\n\n## NEXT - the thing\ndo the thing\n\n"
        "## Human items\n- item one\n\n## Gotchas\nnoise\n\n---\n\n# old\n"
    )
    monkeypatch.setattr(op, "_CONTINUATION_PATH", f)
    d = op._dev_state()
    assert d["latest_session"].endswith("TITLE")
    assert any("NEXT" in k for k in d)
    assert any("Human" in k for k in d)
    assert not any("Gotchas" in k for k in d)


def test_dev_state_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(op, "_CONTINUATION_PATH", tmp_path / "nope.md")
    assert op._dev_state() == {}


def test_post_briefing_uses_attention_brief(monkeypatch):
    monkeypatch.setattr(op, "compose_attention_briefing",
                        lambda: "the attention brief")
    monkeypatch.setattr(op, "should_announce", lambda *a, **k: False)
    entry = op.post_briefing()
    assert entry["text"] == "the attention brief"
    assert entry["kind"] == "briefing"
    assert entry["announced"] is False
