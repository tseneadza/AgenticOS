"""OSA assistant API endpoints (Phase 14a — text MVP).

POST /api/osa/chat   — run one OSA conversational turn; returns a spoken-style
                       reply + a compact tool trace. Body: {message, thread_id?}.
GET  /api/osa/state  — lightweight OSA readiness: active model, Ollama up/down,
                       whether Ollama has been warmed, and the ready flag.

The OSA graph is a dedicated LangGraph ReAct agent (``agents/osa_agent.py``)
compiled with the MySQL checkpointer (``core.memory.get_checkpointer``) so a
conversation keyed by ``thread_id`` is durable across sidecar restarts. Model
routing is per turn: ``osa_agent.pick_model`` chooses the local Ollama model for
chit-chat/acks and Claude for reasoning or any tool-worthy turn (decision #6).

Ollama is warmed on OSA's first use here (``osa_agent.warm_ollama`` —
best-effort, cached, non-blocking; decision #9). If it can't come up, local
turns fall back to Claude so the route never hard-fails.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class OSAChat(BaseModel):
    """Request body for an OSA chat turn."""

    message: str
    thread_id: str | None = None


def _extract_text(content) -> str:
    """Flatten LangChain message content (str or list of parts) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content) if content is not None else ""


def _tool_trace(messages: list) -> list[dict]:
    """Summarize any tool calls in the message list for the reply's trace."""
    trace: list[dict] = []
    for m in messages:
        for call in getattr(m, "tool_calls", None) or []:
            trace.append({
                "tool": call.get("name"),
                "args": call.get("args", {}),
            })
    return trace


@router.post("/api/osa/chat")
def osa_chat(body: OSAChat) -> dict:
    """Run one OSA turn and return a spoken-style reply (+ tool trace).

    Warms Ollama on first use (best-effort), routes the turn to a local or
    cloud model, runs the checkpointed OSA graph under ``thread_id``, and
    returns OSA's final text.

    Args:
        body: ``{message, thread_id?}``. A fresh ``thread_id`` is minted when
            omitted so each new conversation is durable + isolated.

    Raises:
        HTTPException: 400 on empty message; 502 if the graph run fails.
    """
    message = (body.message or "").strip()
    if not message:
        raise HTTPException(400, "message is required")

    from agents import osa_agent
    from core import llm, memory

    thread_id = body.thread_id or f"osa-{uuid.uuid4().hex[:10]}"

    # Decision #9: warm Ollama once on first OSA use (best-effort, cached).
    ollama_ready = osa_agent.warm_ollama()

    # Decision #6: route this turn, honoring Ollama availability, then resolve
    # the alias to a concrete model id for the graph.
    alias = osa_agent.pick_model(message, ollama_ready=ollama_ready)
    model_id = llm.resolve(alias)

    conn = None
    try:
        conn = memory.checkpointer_conn()
        checkpointer = memory.get_checkpointer(conn)
        agent = osa_agent.build_agent(model_id, checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        result = agent.invoke({"messages": [{"role": "user", "content": message}]}, config=config)
    except Exception as exc:  # noqa: BLE001 — surface as a 502, never crash the route
        logger.error("OSA chat failed: %s", exc, exc_info=True)
        raise HTTPException(502, f"OSA turn failed: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()

    messages = result.get("messages", []) if isinstance(result, dict) else []
    reply = _extract_text(getattr(messages[-1], "content", "")) if messages else ""

    return {
        "reply": reply,
        "thread_id": thread_id,
        "model": model_id,
        "route": alias,
        "ollama_ready": ollama_ready,
        "tool_trace": _tool_trace(messages),
    }


@router.get("/api/osa/state")
def osa_state() -> dict:
    """Return lightweight OSA state: active model, Ollama status, ready flag.

    Read-only and cheap — does NOT spawn Ollama (that's done lazily on the first
    chat turn). ``ollama_warmed`` reflects whether ``warm_ollama`` has run this
    process; ``ollama_up`` is a live liveness probe.
    """
    from agents import osa_agent
    from core import llm

    try:
        up = llm.ollama_up()
    except Exception:  # noqa: BLE001
        up = False

    active = llm.active_model()
    info = llm.get_model_info(active)
    return {
        "ready": True,
        "active_model": active,
        "active_label": info.label if info else active,
        "ollama_up": up,
        "ollama_warmed": osa_agent._warm_done,
        "soul": osa_agent.OSA_SOUL_NAME,
    }
