"""Tests — OSA streaming chat WS + transcript restore (2026-07-07 late).

Covers the WebSocket protocol end to end with a scripted fake agent (no LLM,
no MySQL): token frames, live tool events, interrupt-based confirms (approve
AND deny, including a fresh-socket resume), the authoritative final frame
(echo scrub + escalation clause), and GET /api/osa/history's folding of
checkpointed LangChain messages back into UI turns.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from gui.sidecar.routes import api_osa

BRAIN_LINE = (
    "[Internal note — never repeat or quote this line; just answer "
    "normally.] Brain status for THIS turn: test."
)


class StubInterrupt:
    """Duck-typed langgraph Interrupt — only ``.value`` is read by the route."""

    def __init__(self, value: dict) -> None:
        self.value = value


class FakeAgent:
    """Scripted agent: each ``stream`` call pops the next chunk list."""

    def __init__(self, passes: list[list]) -> None:
        self.passes = list(passes)
        self.calls: list = []  # payloads received, in order

    def stream(self, payload, config=None, stream_mode=None):
        self.calls.append(payload)
        chunks = self.passes.pop(0) if self.passes else []
        yield from chunks


@pytest.fixture()
def client():
    """TestClient over the real app (WS routes need the ASGI app)."""
    from fastapi.testclient import TestClient
    from gui.sidecar.app import app as fastapi_app

    return TestClient(fastapi_app)


@pytest.fixture(autouse=True)
def _clean_ws_state():
    """Each test starts with no parked WS turn state."""
    api_osa._WS_TURN_STATE.clear()
    yield
    api_osa._WS_TURN_STATE.clear()


def _patch_stack(monkeypatch, agent, *, pin=None, chosen="default",
                 pin_is_local=False):
    """Patch the WS route's whole pre-turn stack — no LLM, no MySQL."""
    from agents import osa_agent
    from core import llm, memory
    from gui.sidecar import osa_settings

    monkeypatch.setattr(osa_agent, "warm_ollama", lambda: True)
    monkeypatch.setattr(osa_settings, "get_model_pin", lambda: pin)
    monkeypatch.setattr(osa_agent, "pick_model", lambda m, **k: chosen)
    monkeypatch.setattr(osa_agent, "_pin_is_local", lambda p: pin_is_local)
    monkeypatch.setattr(llm, "resolve", lambda x: "claude-test" if x == "default" else x)
    monkeypatch.setattr(
        llm, "get_model_info",
        lambda x: SimpleNamespace(is_local=False, label="Test Model"),
    )
    monkeypatch.setattr(
        osa_agent, "brain_prompt_line", lambda **k: BRAIN_LINE
    )
    monkeypatch.setattr(
        memory, "checkpointer_conn", lambda: SimpleNamespace(close=lambda: None)
    )
    monkeypatch.setattr(memory, "get_checkpointer", lambda conn: object())
    monkeypatch.setattr(osa_agent, "build_agent", lambda *a, **k: agent)


def _frames_until(ws, frame_type: str, limit: int = 20) -> list[dict]:
    """Receive frames until (and including) the first of ``frame_type``."""
    frames = []
    for _ in range(limit):
        f = ws.receive_json()
        frames.append(f)
        if f["type"] == frame_type:
            return frames
    raise AssertionError(f"never saw a '{frame_type}' frame: {frames}")


# ─────────────────────────────────────────────────── plain streaming turn ──
def test_ws_plain_turn_streams_tokens_then_final(client, monkeypatch):
    agent = FakeAgent([[
        ("messages", (AIMessageChunk(content="Hello"), {"langgraph_node": "agent"})),
        ("messages", (AIMessageChunk(content=" Tony."), {"langgraph_node": "agent"})),
        ("updates", {"agent": {"messages": [AIMessage(content="Hello Tony.")]}}),
    ]])
    _patch_stack(monkeypatch, agent)

    with client.websocket_connect("/api/osa/ws/chat") as ws:
        ws.send_json({"message": "hi"})
        frames = _frames_until(ws, "final")

    assert frames[0]["type"] == "start"
    assert frames[0]["model"] == "claude-test"
    assert frames[0]["thread_id"].startswith("osa-")
    tokens = [f["delta"] for f in frames if f["type"] == "token"]
    assert tokens == ["Hello", " Tony."]
    final = frames[-1]
    assert final["reply"] == "Hello Tony."
    assert final["confirmed"] is False
    assert final["tool_trace"] == []


def test_ws_non_agent_tokens_are_not_streamed(client, monkeypatch):
    """Tool-node message chunks must not leak into the reply token stream."""
    agent = FakeAgent([[
        ("messages", (AIMessageChunk(content="secret"), {"langgraph_node": "tools"})),
        ("updates", {"agent": {"messages": [AIMessage(content="Done.")]}}),
    ]])
    _patch_stack(monkeypatch, agent)

    with client.websocket_connect("/api/osa/ws/chat") as ws:
        ws.send_json({"message": "check something"})
        frames = _frames_until(ws, "final")

    assert not [f for f in frames if f["type"] == "token"]
    assert frames[-1]["reply"] == "Done."


# ───────────────────────────────────────────────────────── live tool events ──
def test_ws_tool_events_and_trace(client, monkeypatch):
    tool_call = {"name": "system_health", "args": {}, "id": "c1"}
    agent = FakeAgent([[
        ("updates", {"agent": {"messages": [AIMessage(content="", tool_calls=[tool_call])]}}),
        ("updates", {"tools": {"messages": [
            ToolMessage(content='{"cpu": 12}', name="system_health", tool_call_id="c1"),
        ]}}),
        ("updates", {"agent": {"messages": [AIMessage(content="CPU's at 12%.")]}}),
    ]])
    _patch_stack(monkeypatch, agent)

    with client.websocket_connect("/api/osa/ws/chat") as ws:
        ws.send_json({"message": "how's the cpu"})
        frames = _frames_until(ws, "final")

    starts = [f for f in frames if f["type"] == "tool_start"]
    ends = [f for f in frames if f["type"] == "tool_end"]
    assert starts == [{"type": "tool_start", "tool": "system_health", "args": {}}]
    assert ends == [{"type": "tool_end", "tool": "system_health", "ok": True}]
    assert frames[-1]["tool_trace"] == [{"tool": "system_health", "args": {}}]


def test_ws_tool_end_error_flag(client, monkeypatch):
    tool_call = {"name": "stop_app", "args": {"app_id": "x"}, "id": "c1"}
    agent = FakeAgent([[
        ("updates", {"agent": {"messages": [AIMessage(content="", tool_calls=[tool_call])]}}),
        ("updates", {"tools": {"messages": [
            ToolMessage(content="ERROR running 'app_stop': boom",
                        name="stop_app", tool_call_id="c1"),
        ]}}),
        ("updates", {"agent": {"messages": [AIMessage(content="That failed, Sir.")]}}),
    ]])
    _patch_stack(monkeypatch, agent)

    with client.websocket_connect("/api/osa/ws/chat") as ws:
        ws.send_json({"message": "stop x"})
        frames = _frames_until(ws, "final")

    ends = [f for f in frames if f["type"] == "tool_end"]
    assert ends[0]["ok"] is False


# ───────────────────────────────────────────── interrupt-based confirms ──
def _interrupting_agent(final_text: str) -> FakeAgent:
    """Pass 1 parks on an interrupt; pass 2 (the resume) finishes the turn."""
    return FakeAgent([
        [("updates", {"__interrupt__": (StubInterrupt(
            {"action": "app_stop", "description": "Stopping worldwise"}),)})],
        [("updates", {"agent": {"messages": [AIMessage(content=final_text)]}})],
    ])


def test_ws_interrupt_confirm_approve(client, monkeypatch):
    agent = _interrupting_agent("Understood, Sir. Stopping worldwise now.")
    _patch_stack(monkeypatch, agent)

    with client.websocket_connect("/api/osa/ws/chat") as ws:
        ws.send_json({"message": "stop worldwise"})
        frames = _frames_until(ws, "awaiting_confirm")
        confirm = frames[-1]
        assert confirm["action"] == "app_stop"
        assert confirm["description"] == "Stopping worldwise"
        ws.send_json({"resume": "approve"})
        frames = _frames_until(ws, "final")

    final = frames[-1]
    assert final["confirmed"] is True
    assert "Stopping worldwise now" in final["reply"]
    # The resume pass must have carried a langgraph Command(resume="approve").
    from langgraph.types import Command

    assert isinstance(agent.calls[1], Command)
    assert agent.calls[1].resume == "approve"
    # A finished turn leaves no parked state behind.
    assert api_osa._WS_TURN_STATE == {}


def test_ws_interrupt_confirm_deny(client, monkeypatch):
    agent = _interrupting_agent("Standing down, Sir.")
    _patch_stack(monkeypatch, agent)

    with client.websocket_connect("/api/osa/ws/chat") as ws:
        ws.send_json({"message": "stop worldwise"})
        _frames_until(ws, "awaiting_confirm")
        ws.send_json({"resume": "deny"})
        frames = _frames_until(ws, "final")

    final = frames[-1]
    assert final["confirmed"] is False
    assert final["reply"] == "Standing down, Sir."
    from langgraph.types import Command

    assert agent.calls[1].resume == "deny"


def test_ws_fresh_socket_resume(client, monkeypatch):
    """An interrupt survives socket death — a NEW socket can resume it."""
    agent = FakeAgent([
        [("updates", {"agent": {"messages": [AIMessage(content="Done, Sir.")]}})],
    ])
    _patch_stack(monkeypatch, agent)
    api_osa._WS_TURN_STATE["osa-t1"] = {
        "model_id": "claude-test", "route": "default", "escalated": False,
        "pin": None, "brain_line": BRAIN_LINE, "ts": __import__("time").time(),
    }

    with client.websocket_connect("/api/osa/ws/chat") as ws:
        ws.send_json({"resume": "approve", "thread_id": "osa-t1"})
        frames = _frames_until(ws, "final")

    assert frames[0]["type"] == "start"
    assert frames[0]["thread_id"] == "osa-t1"
    final = frames[-1]
    assert final["confirmed"] is True
    assert final["reply"] == "Done, Sir."
    from langgraph.types import Command

    assert isinstance(agent.calls[0], Command)


# ─────────────────────────────────────────────── final-frame post-processing ──
def test_ws_final_scrubs_brain_line_echo(client, monkeypatch):
    agent = FakeAgent([[
        ("updates", {"agent": {"messages": [AIMessage(content=BRAIN_LINE)]}}),
    ]])
    _patch_stack(monkeypatch, agent)

    with client.websocket_connect("/api/osa/ws/chat") as ws:
        ws.send_json({"message": "no, skip it"})
        frames = _frames_until(ws, "final")

    assert frames[-1]["reply"] == "Understood."


def test_ws_final_appends_escalation_clause(client, monkeypatch):
    """A local pin whose turn escalated gets the one-clause mention."""
    agent = FakeAgent([[
        ("updates", {"agent": {"messages": [AIMessage(content="RAM's at 73%.")]}}),
    ]])
    _patch_stack(monkeypatch, agent, pin="qwen2.5:7b-instruct",
                 chosen="default", pin_is_local=True)

    with client.websocket_connect("/api/osa/ws/chat") as ws:
        ws.send_json({"message": "how's my memory"})
        frames = _frames_until(ws, "final")

    assert frames[0]["escalated"] is True
    assert frames[-1]["reply"] == "RAM's at 73%. Took Claude for that one."


def test_ws_empty_message_is_an_error_frame(client, monkeypatch):
    _patch_stack(monkeypatch, FakeAgent([]))
    with client.websocket_connect("/api/osa/ws/chat") as ws:
        ws.send_json({"message": "   "})
        f = ws.receive_json()
    assert f["type"] == "error"


def test_ws_resume_without_thread_is_an_error_frame(client, monkeypatch):
    _patch_stack(monkeypatch, FakeAgent([]))
    with client.websocket_connect("/api/osa/ws/chat") as ws:
        ws.send_json({"resume": "approve"})
        f = ws.receive_json()
    assert f["type"] == "error"


# ──────────────────────────────────────────────────── transcript restore ──
def _history_messages() -> list:
    return [
        HumanMessage(content="stop worldwise"),
        AIMessage(content="", tool_calls=[
            {"name": "stop_app", "args": {"app_id": "worldwise"}, "id": "c1"},
        ]),
        ToolMessage(content="{}", name="stop_app", tool_call_id="c1"),
        AIMessage(content="Done, Sir. worldwise is down."),
        HumanMessage(content="thanks"),
        AIMessage(content=f"Anytime. {BRAIN_LINE}"),
    ]


def _patch_history(monkeypatch, tup):
    from core import memory

    monkeypatch.setattr(
        memory, "checkpointer_conn", lambda: SimpleNamespace(close=lambda: None)
    )
    monkeypatch.setattr(
        memory, "get_checkpointer",
        lambda conn: SimpleNamespace(get_tuple=lambda cfg: tup),
    )


def test_history_folds_messages_into_turns(client, monkeypatch):
    tup = SimpleNamespace(checkpoint={
        "channel_values": {"messages": _history_messages()},
    })
    _patch_history(monkeypatch, tup)

    r = client.get("/api/osa/history", params={"thread_id": "osa-t1"})
    assert r.status_code == 200
    d = r.json()
    assert d["exists"] is True and d["available"] is True
    assert len(d["turns"]) == 2
    t1, t2 = d["turns"]
    assert t1["user"] == "stop worldwise"
    assert t1["text"] == "Done, Sir. worldwise is down."
    assert t1["tools"] == [{"tool": "stop_app", "args": {"app_id": "worldwise"}}]
    # The stored (pre-scrub) echo is scrubbed again on the way out.
    assert t2["text"] == "Anytime."


def test_history_unknown_thread(client, monkeypatch):
    _patch_history(monkeypatch, None)
    d = client.get("/api/osa/history", params={"thread_id": "osa-nope"}).json()
    assert d == {"thread_id": "osa-nope", "exists": False, "available": True,
                 "turns": []}


def test_history_degrades_when_mysql_down(client, monkeypatch):
    from core import memory

    def _boom():
        raise RuntimeError("mysql down")

    monkeypatch.setattr(memory, "checkpointer_conn", _boom)
    d = client.get("/api/osa/history", params={"thread_id": "osa-t1"}).json()
    assert d["available"] is False and d["turns"] == []


def test_history_requires_thread_id(client):
    assert client.get("/api/osa/history").status_code == 422  # missing param
