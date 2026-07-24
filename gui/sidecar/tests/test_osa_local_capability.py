"""OSA local-brain capability (2026-07-23).

Tony wants OSA to do menial things on the local Ollama brain — create notes,
start/stop apps, status, remember, messages, mail — without the cloud brain (so
they work offline / credit-free). Two pieces covered here:

  * a curated ``LOCAL_TOOL_NAMES`` subset bound to LOCAL models (a 7B mis-picks
    and slows to a crawl with all 29 schemas; measured ~7s for a 2-tool call);
  * ``route_turn`` sends menial system tasks to ``local`` and web/heavy/sharp
    turns to ``default`` (cloud).

Hermetic — no Ollama, no live LLM.
"""
from __future__ import annotations

import pytest

from agents import osa_agent


class TestLocalToolset:
    def test_subset_is_smaller_than_full(self):
        full = osa_agent.build_tools(osa_agent.OSAToolbox(approval_fn=lambda a, d: "deny"))
        subset = osa_agent.build_tools(
            osa_agent.OSAToolbox(approval_fn=lambda a, d: "deny"),
            only=osa_agent.LOCAL_TOOL_NAMES,
        )
        assert len(subset) < len(full)
        assert {t.name for t in subset} == set(osa_agent.LOCAL_TOOL_NAMES)

    def test_menial_tools_present(self):
        # The things Tony named must be reachable locally.
        for name in ("write_file", "append_file", "start_app", "stop_app",
                     "system_health", "remember", "send_message", "send_mail",
                     "read_email", "read_messages", "get_time", "list_projects"):
            assert name in osa_agent.LOCAL_TOOL_NAMES

    def test_sharp_tools_excluded_from_local(self):
        # Arbitrary/destructive tools stay CLOUD-only.
        for name in ("run_command", "delete_file", "move_file", "search_files"):
            assert name not in osa_agent.LOCAL_TOOL_NAMES

    def test_build_agent_binds_subset_for_local_full_for_cloud(self, monkeypatch):
        import langgraph.prebuilt as lp
        captured = {}

        def _spy_tools(tb, only=None):
            captured["only"] = only
            return []

        monkeypatch.setattr(osa_agent, "build_tools", _spy_tools)
        monkeypatch.setattr("core.llm.get_chat_model", lambda mid: object())
        monkeypatch.setattr(lp, "create_react_agent", lambda model, tools, **k: object())

        monkeypatch.setattr(osa_agent, "_pin_is_local", lambda mid: True)
        osa_agent.build_agent("qwen2.5:7b-instruct")
        assert captured["only"] == osa_agent.LOCAL_TOOL_NAMES

        monkeypatch.setattr(osa_agent, "_pin_is_local", lambda mid: False)
        osa_agent.build_agent("claude-sonnet-4-6")
        assert captured["only"] is None


class TestRouting:
    @pytest.mark.parametrize("msg", [
        "create a note about the meeting", "start worldwise", "stop the hub app",
        "what's the system status", "how's my memory", "remember that I like tea",
        "text Tony hello", "send an email to Sarah", "read my latest mail",
        "what time is it", "list my projects",
    ])
    def test_menial_tasks_route_local(self, msg):
        assert osa_agent.route_turn(msg) == "local"

    @pytest.mark.parametrize("msg", [
        "search the web for quantum news", "look up the latest on Mars",
        "explain why the orbit precesses", "analyze this failure",
        "run rm -rf on the temp dir", "delete the old logs",
        "research the Nemesis hypothesis",
    ])
    def test_web_and_heavy_route_cloud(self, msg):
        assert osa_agent.route_turn(msg) == "default"

    def test_chitchat_and_empty_still_local(self):
        assert osa_agent.route_turn("hey") == "local"
        assert osa_agent.route_turn("") == "local"

    def test_heavy_beats_menial_when_both_present(self):
        # "why is the app down" has a menial hint ("is ", "app") but should reason
        # on cloud because of the heavy "why".
        assert osa_agent.route_turn("why is the app down") == "default"


class TestWarmReprobe:
    """A transient not-ready must not strand local turns on the cloud forever."""

    def test_not_ready_reprobes_and_recovers(self, monkeypatch):
        osa_agent.reset_ollama_warm_cache()
        ups = iter([False, True])  # first probe down, next probe up
        monkeypatch.setattr("core.llm.ollama_up", lambda *a, **k: next(ups))
        monkeypatch.setattr("core.llm.ensure_ollama_running", lambda *a, **k: {"up": False})
        assert osa_agent.warm_ollama() is False   # first turn: down, spawn fails
        assert osa_agent.warm_ollama() is True     # next turn: re-probe, now up
        osa_agent.reset_ollama_warm_cache()

    def test_ready_is_sticky_no_reprobe(self, monkeypatch):
        osa_agent.reset_ollama_warm_cache()
        probes = {"n": 0}

        def _up(*a, **k):
            probes["n"] += 1
            return True

        monkeypatch.setattr("core.llm.ollama_up", _up)
        assert osa_agent.warm_ollama() is True
        assert osa_agent.warm_ollama() is True
        assert probes["n"] == 1  # second call returned the sticky True without probing
        osa_agent.reset_ollama_warm_cache()
