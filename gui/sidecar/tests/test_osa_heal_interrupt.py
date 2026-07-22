"""Heal-on-entry guard for the shared OSA thread (2026-07-21).

Regression cover for a cross-path checkpoint corruption. The WS chat path gates
a destructive tool via LangGraph ``interrupt()``, parking an ``AIMessage`` with a
tool call on the durable checkpointer and NO ``ToolMessage`` until a
``Command(resume=...)`` arrives. Typed (WS) and voice (sync POST) share ONE
durable thread (the active-thread singleton, 2026-07-14), so a NEW message on the
other path while that interrupt is parked would append a ``HumanMessage`` onto
the dangling tool call — a history with ``tool_calls`` and no matching
``ToolMessage`` that the provider rejects (``INVALID_CHAT_HISTORY``).

``api_osa._heal_pending_interrupt`` heals BOTH shapes before the new turn:
  1. a LIVE interrupt → fail-closed ``Command(resume="deny")``;
  2. a BAKED dangling call (a prior crash already appended the HumanMessage) →
     the offending ``AIMessage`` is rewritten in place with ``tool_calls`` stripped.

Hermetic — no MySQL, no live LLM: the agent is a fake exposing
``get_state`` / ``invoke`` / ``update_state``.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from gui.sidecar.routes import api_osa

_CFG = {"configurable": {"thread_id": "osa-heal"}}


# --------------------------------------------------------------------------- #
# Fakes — a compiled-graph stand-in.
# --------------------------------------------------------------------------- #
class _Intr:
    def __init__(self, value):
        self.value = value


class _Task:
    def __init__(self, interrupts):
        self.interrupts = interrupts


class _Snap:
    def __init__(self, next_, tasks, messages):
        self.next = next_
        self.tasks = tasks
        self.values = {"messages": messages}


def _call(id_, name="move_file"):
    return {"name": name, "args": {}, "id": id_, "type": "tool_call"}


class _FakeAgent:
    """Models both corruption shapes via mutable interrupt-count + message list."""

    def __init__(self, *, interrupts=0, messages=None, clears=True):
        self._interrupts = interrupts
        self._messages = list(messages or [])
        self._clears = clears
        self.resumes: list = []
        self.updates: list = []

    def _dangling(self):
        answered = {getattr(m, "tool_call_id", None) for m in self._messages}
        return any(
            (getattr(m, "tool_calls", None) or [])
            and any(c.get("id") not in answered for c in m.tool_calls)
            for m in self._messages
        )

    def get_state(self, config):
        tasks = [_Task([_Intr({"description": "Move OSA note to 00 - Raw"})])] if self._interrupts else []
        nxt = ("agent",) if (self._interrupts or self._dangling()) else ()
        return _Snap(nxt, tasks, list(self._messages))

    def invoke(self, payload, config=None):
        self.resumes.append(payload)
        if self._interrupts and self._clears:
            self._interrupts -= 1
        return {}

    def update_state(self, config, values):
        self.updates.append(values)
        repl = {m.id: m for m in values["messages"]}
        self._messages = [repl.get(getattr(m, "id", None), m) for m in self._messages]


# --------------------------------------------------------------------------- #
# Unit — the helper in isolation.
# --------------------------------------------------------------------------- #
class TestHealHelper:
    def test_healthy_thread_is_a_noop(self):
        agent = _FakeAgent(messages=[HumanMessage(content="hi", id="h1")])
        assert api_osa._heal_pending_interrupt(agent, _CFG) is None
        assert agent.resumes == []
        assert agent.updates == []

    def test_live_interrupt_is_resumed_with_deny(self):
        agent = _FakeAgent(interrupts=1)
        result = api_osa._heal_pending_interrupt(agent, _CFG)
        assert result == "Move OSA note to 00 - Raw"
        assert len(agent.resumes) == 1
        # FAIL-CLOSED: the parked action is DENIED, never executed.
        assert isinstance(agent.resumes[0], Command)
        assert agent.resumes[0].resume == "deny"

    def test_resume_is_bounded_when_interrupt_never_clears(self):
        agent = _FakeAgent(interrupts=1, clears=False)  # every get_state stays parked
        api_osa._heal_pending_interrupt(agent, _CFG)
        assert len(agent.resumes) == 3  # bounded at range(3), no infinite loop

    def test_baked_dangling_call_is_stripped_in_place(self):
        # AIMessage(move_file) with NO ToolMessage, then a HumanMessage on top —
        # exactly the persisted shape that throws INVALID_CHAT_HISTORY.
        msgs = [
            HumanMessage(content="move my notes", id="h1"),
            AIMessage(content="", tool_calls=[_call("call-abc")], id="ai1"),
            HumanMessage(content="mark them needs-processing", id="h2"),
        ]
        agent = _FakeAgent(messages=msgs)
        result = api_osa._heal_pending_interrupt(agent, _CFG)
        assert result == "cancelled an unfinished tool call"
        assert len(agent.updates) == 1
        # No resume happened (no live interrupt), just the in-place strip.
        assert agent.resumes == []
        # The offending AIMessage now carries no tool_calls → history validates.
        assert not agent._dangling()
        fixed = next(m for m in agent._messages if m.id == "ai1")
        assert not (getattr(fixed, "tool_calls", None) or [])

    def test_answered_tool_call_is_left_alone(self):
        # A properly-answered tool call is NOT dangling → no strip.
        msgs = [
            AIMessage(content="", tool_calls=[_call("call-ok")], id="ai1"),
            ToolMessage(content="done", tool_call_id="call-ok", id="t1"),
        ]
        agent = _FakeAgent(messages=msgs)
        assert api_osa._heal_pending_interrupt(agent, _CFG) is None
        assert agent.updates == []

    def test_get_state_failure_is_swallowed(self):
        class _Boom:
            def get_state(self, config):
                raise RuntimeError("checkpointer offline")

        assert api_osa._heal_pending_interrupt(_Boom(), _CFG) is None

    def test_missing_get_state_attr_is_safe(self):
        class _NoState:
            def invoke(self, *a, **k):  # pragma: no cover
                raise AssertionError("invoke must not run")

        assert api_osa._heal_pending_interrupt(_NoState(), _CFG) is None


# --------------------------------------------------------------------------- #
# Route — the sync POST path heals before it appends the new turn.
# --------------------------------------------------------------------------- #
class _RouteAgent:
    """Parked on a live interrupt; a resume clears it, then the real turn runs."""

    def __init__(self):
        self.parked = True
        self.payloads: list = []

    def get_state(self, config):
        tasks = [_Task([_Intr({"description": "Move note"})])] if self.parked else []
        return _Snap(("agent",) if self.parked else (), tasks, [])

    def invoke(self, payload, config=None):
        self.payloads.append(payload)
        if isinstance(payload, Command):
            self.parked = False
            return {}
        return {"messages": [AIMessage(content="Done, Sir.", id="r1")]}

    def update_state(self, config, values):  # pragma: no cover — no dangling msgs here
        pass


class TestSyncRouteHeals:
    def _patch(self, monkeypatch, agent):
        from agents import osa_agent as oa
        from core import llm, memory

        monkeypatch.setattr(oa, "warm_ollama", lambda: True)
        monkeypatch.setattr(oa, "pick_model", lambda msg, **k: "default")
        monkeypatch.setattr(llm, "resolve", lambda alias: "claude-sonnet-4-6")
        monkeypatch.setattr(memory, "checkpointer_conn", lambda: None)
        monkeypatch.setattr(memory, "get_checkpointer", lambda conn=None: object())
        # No brain pin ⇒ no escalation clause appended (hermetic reply).
        monkeypatch.setattr("gui.sidecar.osa_settings.get_model_pin", lambda: None)
        monkeypatch.setattr(oa, "build_agent", lambda model_id, approval_fn=None, **k: agent)
        monkeypatch.setattr(api_osa, "_maybe_speak_reply", lambda reply: None)

    def test_parked_thread_is_healed_then_the_turn_runs(self, monkeypatch):
        from fastapi.testclient import TestClient
        from gui.sidecar.app import app as fastapi_app

        agent = _RouteAgent()
        self._patch(monkeypatch, agent)

        resp = TestClient(fastapi_app).post(
            "/api/osa/chat",
            json={"message": "make both notes needs-processing", "thread_id": "osa-stuck"},
        )
        assert resp.status_code == 200
        assert resp.json()["reply"] == "Done, Sir."
        # Order matters: a resume-deny FIRST (heal), then the real user message.
        assert len(agent.payloads) == 2
        assert isinstance(agent.payloads[0], Command)
        assert agent.payloads[0].resume == "deny"
        assert agent.payloads[1] == {"messages": [{"role": "user", "content": "make both notes needs-processing"}]}
