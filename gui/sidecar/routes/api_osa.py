"""OSA assistant API endpoints (Phase 14a — text MVP; 14e — proactive events).

POST /api/osa/chat    — run one OSA conversational turn; returns a spoken-style
                        reply + a compact tool trace. Body: {message, thread_id?}.
GET  /api/osa/state   — lightweight OSA readiness: active model, Ollama up/down,
                        whether Ollama has been warmed, the ready flag, and the
                        latest proactive event id (cheap news detection, 14e).
GET  /api/osa/events  — proactive ring-buffer messages (health transitions +
                        briefings) newer than an optional ``after`` cursor.
POST /api/osa/briefing — compose + announce a status briefing on demand
                        (always announced — an explicit ask beats quiet hours).

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
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


# --------------------------------------------------------------------------- #
# Destructive-action confirmation (Phase 14b) — conversational two-turn confirm.
#
# The sync chat route can't block waiting on a human, so a guarded destructive
# action (e.g. stop_app -> app_stop) is confirmed across two turns:
#   turn 1 (the request): the agent's approval_fn DENIES and records a pending
#           entry for this thread_id -> OSA asks Tony to confirm.
#   turn 2 (an affirmative WITH a live pending): the approval_fn APPROVES for
#           that turn and clears the pending entry -> the checkpointed history
#           replays the request so the model re-issues the tool and it proceeds.
# A negative clears the pending entry. A bare affirmative with no pending never
# approves anything. The store is in-process, thread-keyed, and TTL-bounded.
# --------------------------------------------------------------------------- #
_PENDING_CONFIRM: dict[str, dict] = {}
_CONFIRM_TTL_SECONDS = 5 * 60

_AFFIRMATIVES = frozenset({
    "yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm",
    "confirmed", "do it", "go ahead", "go for it", "proceed", "affirmative",
    "yes sir", "yes please", "please do", "absolutely", "of course",
})
_NEGATIVES = frozenset({
    "no", "n", "nope", "nah", "cancel", "stop", "don't", "dont",
    "never mind", "nevermind", "forget it", "abort", "negative", "no thanks",
})


def _normalize(message: str) -> str:
    """Lowercase + strip surrounding whitespace and trailing punctuation."""
    return (message or "").strip().lower().rstrip("!.?,").strip()


_AFFIRM_FIRST_WORDS = frozenset({
    "yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm",
    "confirmed", "proceed", "affirmative", "absolutely",
})
_NEG_FIRST_WORDS = frozenset({
    "no", "n", "nope", "nah", "cancel", "abort", "negative", "dont",
})


def _first_word(message: str) -> str:
    """First word of the normalized message, internal punctuation dropped."""
    parts = _normalize(message).replace(",", " ").replace(";", " ").split()
    return parts[0] if parts else ""


def is_affirmative(message: str) -> bool:
    """Whether a turn is a 'yes / confirm / go ahead' style affirmation.

    Matches an exact affirmative phrase, a leading affirmative word (so compound
    replies like 'yes, do it' or 'yeah go ahead' count), or a known affirmative
    phrase prefix. Word-boundary based, so 'yesterday' does NOT match.
    """
    norm = _normalize(message)
    if not norm:
        return False
    if norm in _AFFIRMATIVES:
        return True
    if _first_word(norm) in _AFFIRM_FIRST_WORDS:
        return True
    return any(norm.startswith(p) for p in (
        "do it", "go ahead", "go for it", "please do", "of course",
    ))


def is_negative(message: str) -> bool:
    """Whether a turn is a 'no / cancel' style refusal (leading-word aware)."""
    norm = _normalize(message)
    if not norm:
        return False
    if norm in _NEGATIVES:
        return True
    if _first_word(norm) in _NEG_FIRST_WORDS:
        return True
    return any(norm.startswith(p) for p in (
        "never mind", "nevermind", "forget it", "do not", "don't",
    ))


def record_pending(thread_id: str, action: str, description: str) -> None:
    """Record a pending destructive action awaiting confirmation for a thread."""
    _PENDING_CONFIRM[thread_id] = {
        "action": action,
        "description": description,
        "ts": time.time(),
    }


def get_pending(thread_id: str) -> dict | None:
    """Return the live pending-confirm for a thread, or None if absent/expired.

    Expired entries (older than the TTL) are pruned and treated as absent so a
    stale 'yes' can never approve a destructive action.
    """
    entry = _PENDING_CONFIRM.get(thread_id)
    if entry is None:
        return None
    if time.time() - entry.get("ts", 0) > _CONFIRM_TTL_SECONDS:
        _PENDING_CONFIRM.pop(thread_id, None)
        return None
    return entry


def clear_pending(thread_id: str) -> None:
    """Drop any pending-confirm for a thread (no-op if none)."""
    _PENDING_CONFIRM.pop(thread_id, None)


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
    from gui.sidecar import osa_proactive

    # Phase 14e: a chat turn is an activity signal — the proactive monitor's
    # quiet-hours check falls back to "chatted recently" when the HID idle
    # probe is unavailable.
    osa_proactive.note_chat_turn()

    thread_id = body.thread_id or f"osa-{uuid.uuid4().hex[:10]}"

    # Decision #9: warm Ollama once on first OSA use (best-effort, cached).
    ollama_ready = osa_agent.warm_ollama()

    # Decision #6: route this turn, honoring Ollama availability, then resolve
    # the alias to a concrete model id for the graph.
    alias = osa_agent.pick_model(message, ollama_ready=ollama_ready)
    model_id = llm.resolve(alias)

    # Phase 14b: destructive-action confirmation. Decide THIS turn's approval
    # policy up-front (the sync route can't block on a human):
    #   * A live pending-confirm + an affirmative turn => approve this turn.
    #   * A live pending-confirm + a negative turn      => clear + never approve.
    #   * Otherwise a guarded destructive action DENIES and records a pending
    #     entry so OSA asks Tony to confirm on the next turn.
    pending = get_pending(thread_id)
    confirmed = False
    turn_state = {"awaiting": None}  # captured by approval_fn on a fresh deny

    if pending is not None and is_affirmative(message):
        confirmed = True
        clear_pending(thread_id)

        def approval_fn(action_type: str, description: str) -> str:
            """Approve the confirmed destructive action for this turn only."""
            return "approve"
    else:
        if pending is not None and is_negative(message):
            clear_pending(thread_id)

        def approval_fn(action_type: str, description: str) -> str:
            """Deny + record a pending-confirm so OSA asks Tony to confirm."""
            record_pending(thread_id, action_type, description)
            turn_state["awaiting"] = {
                "action": action_type, "description": description,
            }
            return "deny"

    conn = None
    try:
        conn = memory.checkpointer_conn()
        checkpointer = memory.get_checkpointer(conn)
        agent = osa_agent.build_agent(
            model_id, approval_fn=approval_fn, checkpointer=checkpointer
        )
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

    awaiting = turn_state["awaiting"]
    return {
        "reply": reply,
        "thread_id": thread_id,
        "model": model_id,
        "route": alias,
        "ollama_ready": ollama_ready,
        "tool_trace": _tool_trace(messages),
        "awaiting_confirm": awaiting is not None,
        "pending_action": awaiting,
        "confirmed": confirmed,
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
    from gui.sidecar import osa_proactive

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
        # 14e: newest proactive event id — lets the orb's existing state poll
        # cheaply detect news without pulling the events list.
        "latest_event_id": osa_proactive.latest_id(),
    }


@router.get("/api/osa/events")
def osa_events(after: int | None = None) -> dict:
    """Return proactive messages from the in-memory ring buffer (Phase 14e).

    Args:
        after: Optional cursor — only messages with ``id > after`` are
            returned. Omit it to get everything still in the buffer (~50).

    Returns:
        ``{messages: [{id, ts, app_id, kind, text, announced}, ...],
        latest_id}`` — ``latest_id`` is the newest id ever recorded, suitable
        as the next ``after`` cursor even when ``messages`` is empty.
    """
    from gui.sidecar import osa_proactive

    return osa_proactive.get_messages(after=after)


@router.post("/api/osa/briefing")
def osa_briefing() -> dict:
    """Compose + record a status briefing on demand (14e follow-on).

    User-initiated (the rail's "Brief me" button), so it is ALWAYS announced —
    the quiet-hours/activity policy is for unsolicited speech, and an explicit
    ask is its own proof of activity. Also counts as an activity signal for
    the proactive monitor's chat-recency fallback.

    Returns:
        The recorded ring-buffer entry:
        ``{id, ts, app_id, kind: "briefing", text, announced: true}``.
    """
    from gui.sidecar import osa_proactive

    osa_proactive.note_chat_turn()
    return osa_proactive.post_briefing(force_announce=True)
