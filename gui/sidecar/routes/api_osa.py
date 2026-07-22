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
WS   /api/osa/ws/chat — streaming OSA turn (2026-07-07 late): token deltas +
                        live tool events over one socket, with REAL mid-run
                        destructive-action confirms via LangGraph interrupt()
                        — the graph parks on the MySQL checkpointer until the
                        client resumes with Allow/Deny. The sync POST route
                        keeps the two-turn conversational confirm (it can't
                        block on a human; voice will use it in 14d).
GET  /api/osa/history — fold a checkpointed thread's messages back into UI
                        turns so the Agent view can restore a transcript
                        across app restarts.
GET  /api/osa/model   — OSA brain pin: pinned model (null = auto), mode, and
                        the pinnable choices — curated registry PLUS installed
                        Ollama models (``discovered: true``, 2026-07-07) — with
                        availability/reason (``may_not_fit_ram`` = pinnable
                        with a warning, not disabled).
POST /api/osa/model   — pin OSA's brain ({model: "<pinnable id>"|"auto"});
                        422 unknown, 409 unavailable-with-reason. Durable
                        (MySQL osa_settings) via gui.sidecar.osa_settings.

The OSA graph is a dedicated LangGraph ReAct agent (``agents/osa_agent.py``)
compiled with the MySQL checkpointer (``core.memory.get_checkpointer``) so a
conversation keyed by ``thread_id`` is durable across sidecar restarts. Model
routing is per turn: ``osa_agent.pick_model`` chooses the local Ollama model for
chit-chat/acks and Claude for reasoning or any tool-worthy turn (decision #6) —
unless Tony has pinned a brain (``osa_settings.get_model_pin``): a cloud pin
takes every turn; a local pin takes conversational turns while tool-worthy ones
still escalate to Claude (and the reply says so in one short clause).

Ollama is warmed on OSA's first use here (``osa_agent.warm_ollama`` —
best-effort, cached, non-blocking; decision #9). If it can't come up, local
turns fall back to Claude so the route never hard-fails.
"""
from __future__ import annotations

import logging
import time
import uuid

import asyncio
import threading

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
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

# The guardrail-escalation clause (locked decision #1). Kept in the DISPLAYED
# reply (the model badge reinforces it), but stripped from SPOKEN output
# (Tony, 2026-07-08) — hearing it on every escalated turn is noise.
_ESCALATION_CLAUSE = "Took Claude for that one."

# What the most recent chat turn actually ran on (2026-07-07) — the orb's
# status line shows runtime truth (pin vs escalated turn) from this.
_LAST_TURN: dict = {"model": None, "escalated": False}
_CONFIRM_TTL_SECONDS = 5 * 60

_AFFIRMATIVES = frozenset({
    "yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm",
    "confirmed", "do it", "go ahead", "go for it", "proceed", "affirmative",
    "yes sir", "yes please", "please do", "absolutely", "of course",
    "approve", "approved", "i approve", "approve it", "send it",
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
    "confirmed", "proceed", "affirmative", "absolutely", "approve", "approved",
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
    return any(
        norm == p or norm.startswith(p + " ") or norm.startswith(p + ",")
        for p in (
            "do it", "go ahead", "go for it", "please do", "of course",
            "i approve", "i confirm", "send it", "approve it",
        )
    )


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


def _heal_pending_interrupt(agent, config) -> str | None:
    """Resolve a parked interrupt on this thread before appending a new turn.

    Cross-path corruption guard (2026-07-21). The WS chat path gates a
    destructive tool via LangGraph ``interrupt()``, which parks an
    ``AIMessage`` carrying the tool call on the durable checkpointer with NO
    ``ToolMessage`` yet, awaiting ``Command(resume=...)``. Because typed (WS)
    and voice (sync POST) share ONE durable thread (the active-thread
    singleton, 2026-07-14), a new message that arrives on the OTHER path while
    that interrupt is still parked would append a ``HumanMessage`` on top of
    the dangling tool call — yielding a history with ``tool_calls`` and no
    matching ``ToolMessage``, which the LLM provider rejects
    (``INVALID_CHAT_HISTORY``). This clears the parked interrupt with a
    **fail-closed DENY** (resume-deny re-runs the tool's pre-guard code — which
    is side-effect-free — then the guard denies, so the parked action NEVER
    executes) so the incoming turn appends cleanly.

    Heals BOTH shapes the corruption can take:

    1. **Live interrupt** — a WS gated tool is parked awaiting a resume. Cleared
       with a fail-closed DENY (resume-deny re-runs only the tool's
       side-effect-free pre-guard code, then the guard denies, so the parked
       action NEVER executes).
    2. **Baked dangling tool call** — a prior crash already appended a
       ``HumanMessage`` on top of the dangling call (``.next`` points back at the
       agent, no live interrupt). The offending ``AIMessage`` is rewritten in
       place (same id ⇒ ``add_messages`` replaces it) with its ``tool_calls``
       stripped, so no orphaned ``tool_use`` remains.

    Best-effort + idempotent: a healthy thread costs one ``get_state`` read and
    returns ``None``. Bounded and non-raising — if it can't clear, the next turn
    simply retries. Returns a short description of what it healed, else ``None``.
    """
    healed: str | None = None
    try:
        from langchain_core.messages import AIMessage
        from langgraph.types import Command

        # (1) Resolve a LIVE interrupt (fail-closed deny), bounded.
        for _ in range(3):
            snap = agent.get_state(config)
            intr = None
            for task in getattr(snap, "tasks", None) or []:
                for i in getattr(task, "interrupts", None) or []:
                    intr = i
                    break
                if intr is not None:
                    break
            if intr is None:
                break  # no live interrupt to resume
            val = getattr(intr, "value", None)
            if healed is None and isinstance(val, dict):
                healed = val.get("description")
            agent.invoke(Command(resume="deny"), config=config)

        # (2) Strip any BAKED dangling tool call so the next turn validates.
        snap = agent.get_state(config)
        msgs = (getattr(snap, "values", None) or {}).get("messages", [])
        answered = {getattr(m, "tool_call_id", None) for m in msgs}
        fixes = [
            AIMessage(
                content=getattr(m, "content", "") or "(cancelled an unfinished action)",
                id=m.id,
            )
            for m in msgs
            if (getattr(m, "tool_calls", None) or [])
            and any(c.get("id") not in answered for c in m.tool_calls)
        ]
        if fixes:
            agent.update_state(config, {"messages": fixes})
            healed = healed or "cancelled an unfinished tool call"
    except Exception as exc:  # noqa: BLE001 — best-effort; a new turn will retry
        logger.warning("heal: could not clear parked/dangling tool state: %s", exc)
        return None
    if healed:
        logger.info("heal: cleared parked/dangling tool state (%s)", healed)
    return healed


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


def _scrub_reply(reply: str, brain_line: str | None, *, escalated: bool) -> str:
    """Post-process one finished OSA reply (shared by sync POST + WS routes).

    Echo scrub (2026-07-07): small local models sometimes parrot the injected
    brain-status suffix verbatim instead of answering — strip any echo of it;
    if nothing else remains, fall back to a plain ack. Then the escalation
    mention (locked decision #1): one short spoken clause, only when the model
    didn't already own up to it itself.
    """
    if reply:
        for frag in ((brain_line, brain_line.rstrip(".")) if brain_line else ()):
            reply = reply.replace(frag, "")
        if "Brain status for THIS turn" in reply:
            reply = reply.split("Brain status for THIS turn")[0]
        if "[Internal note" in reply:
            reply = reply.split("[Internal note")[0]
        reply = reply.strip()
        if not reply:
            reply = "Understood."
    if escalated and reply and "claude" not in reply.lower():
        reply = f"{reply.rstrip()} {_ESCALATION_CLAUSE}"
    return reply


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

    # Brain pin (2026-07-07): a pinned model overrides the per-turn router.
    # Cached read — no MySQL on the turn path; DB down ⇒ auto (never raises).
    from gui.sidecar import osa_settings

    pin = osa_settings.get_model_pin()

    # Decision #6: route this turn (pin-aware), honoring Ollama availability,
    # then resolve the alias/id to a concrete model id for the graph.
    chosen = osa_agent.pick_model(message, ollama_ready=ollama_ready, pin=pin)
    # Confirm-approval escalation (2026-07-12, live-found): a "yes" with a live
    # pending confirm RE-ISSUES the guarded tool. "yes" looks like chit-chat to
    # the router, so it lands local — but local 7B models thrash on the tool
    # retry. Force the cloud brain (unless a cloud model is explicitly pinned).
    if get_pending(thread_id) is not None and is_affirmative(message):
        chosen = pin if (pin and not osa_agent._pin_is_local(pin)) else "default"
    model_id = llm.resolve(chosen)
    # The route badge keys off local vs cloud of what the turn ACTUALLY used.
    # Discovered (uncurated) Ollama pins aren't in the registry — fall back to
    # the discovery cache so their badge stays honest (2026-07-07).
    _info = llm.get_model_info(model_id)
    if _info is None:
        _info = llm.discover_ollama().get(model_id)
    route = "local" if (_info is not None and _info.is_local) else "default"
    # A local pin that didn't get this turn (tool guardrail or Ollama down)
    # escalated to Claude — OSA mentions it in persona below. Only a LOCAL
    # pin can escalate; a cloud pin always gets its turns.
    escalated = bool(pin) and osa_agent._pin_is_local(pin) and chosen != pin

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

    # Brain introspection (2026-07-07): a per-turn system-prompt line telling
    # OSA its mode / pin / effective model, so "what's your brain?" is a
    # zero-tool factual answer instead of a guess.
    brain_line = osa_agent.brain_prompt_line(
        pin=pin, effective=model_id, escalated=escalated
    )

    conn = None
    try:
        conn = memory.checkpointer_conn()
        checkpointer = memory.get_checkpointer(conn)
        agent = osa_agent.build_agent(
            model_id, approval_fn=approval_fn, checkpointer=checkpointer,
            system_suffix=brain_line, voice_aware=_voice_is_on(),
        )
        config = {"configurable": {"thread_id": thread_id}}
        # Heal a parked interrupt left by a gated tool on the OTHER (WS) path
        # before appending this turn, else the shared thread yields a dangling
        # tool call → INVALID_CHAT_HISTORY (2026-07-21).
        _heal_pending_interrupt(agent, config)
        result = agent.invoke({"messages": [{"role": "user", "content": message}]}, config=config)
    except Exception as exc:  # noqa: BLE001 — surface as a 502, never crash the route
        logger.error("OSA chat failed: %s", exc, exc_info=True)
        raise HTTPException(502, f"OSA turn failed: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()

    messages = result.get("messages", []) if isinstance(result, dict) else []
    reply = _extract_text(getattr(messages[-1], "content", "")) if messages else ""

    reply = _scrub_reply(reply, brain_line, escalated=escalated)

    awaiting = turn_state["awaiting"]
    # Confirm-surfacing safety net (2026-07-07): Tony's live test showed the
    # model retrying a DENIED tool without ever asking him. If this turn
    # recorded a pending confirm and the reply doesn't already ask, append
    # the question deterministically — the confirm must never be invisible.
    if awaiting is not None and "yes" not in reply.lower():
        ask = f"Needs your OK, Sir: {awaiting['description']}. Just say yes."
        reply = f"{reply.rstrip()} {ask}" if reply.strip() else ask

    # Orb brain display (2026-07-07): remember what THIS turn actually ran on
    # so /api/osa/state can show runtime truth, not just the pin.
    _LAST_TURN.update(model=model_id, escalated=escalated)

    # Voice-OUT (2026-07-08): speak the reply aloud when voice + speak_replies
    # are on. Best-effort + non-blocking — the HTTP reply (captions) returns
    # immediately; a voiceless machine is simply silent.
    _maybe_speak_reply(reply)

    return {
        "reply": reply,
        "thread_id": thread_id,
        "model": model_id,
        "route": route,
        "pinned_model": pin,
        "escalated": escalated,
        "ollama_ready": ollama_ready,
        "tool_trace": _tool_trace(messages),
        "awaiting_confirm": awaiting is not None,
        "pending_action": awaiting,
        "confirmed": confirmed,
    }


def _voice_is_on() -> bool:
    """Whether voice-OUT is live per the Constitution (best-effort, never raises).

    Drives the voice-awareness prompt line (2026-07-09) in BOTH chat routes
    (dual-path rule) so OSA stops claiming "I'm text-only" mid voice-chat.
    Config unreadable ⇒ False — OSA never claims ears it can't prove.
    """
    try:
        from osa_voice.config import voice_config

        return bool(voice_config().get("enabled"))
    except Exception:  # noqa: BLE001 — voice is a garnish, never a dependency
        return False


def _maybe_speak_reply(reply: str) -> None:
    """Speak an OSA chat reply aloud if voice-OUT is enabled (best-effort).

    Guarded end-to-end: config read, dep probe, synth and playback all fail
    soft. The chat route never waits on or breaks over audio.
    """
    if not reply:
        return
    try:
        from osa_voice.config import voice_config

        cfg = voice_config()
        if not (cfg.get("enabled") and cfg.get("speak_replies")):
            return
        from osa_voice import get_service

        # Speak a clean version: drop the escalation clause (Tony, 2026-07-08)
        # — it stays in the displayed reply but shouldn't be read aloud.
        spoken = reply.replace(_ESCALATION_CLAUSE, "").strip()
        get_service().speak(spoken)  # non-blocking
    except Exception:  # noqa: BLE001 — voice is a garnish, never a dependency
        pass


class OSAActiveThread(BaseModel):
    """Request body for setting the UI's active OSA thread."""

    thread_id: str | None = None


@router.post("/api/osa/active-thread")
def osa_set_active_thread(body: OSAActiveThread) -> dict:
    """Record the on-screen chat's current thread so voice unifies with it.

    The chat UI POSTs its thread_id here whenever it mounts or mints/switches
    a conversation. The voice pipeline reads it (best-effort) so spoken turns
    land in the SAME transcript the user is viewing. Idempotent; empty clears.
    """
    from gui.sidecar.osa_active_thread import set_active_thread

    set_active_thread(body.thread_id)
    return {"thread_id": body.thread_id or None}


@router.get("/api/osa/active-thread")
def osa_get_active_thread() -> dict:
    """Return the UI's current active OSA thread_id (null when unset)."""
    from gui.sidecar.osa_active_thread import get_active_thread

    return {"thread_id": get_active_thread()}


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

    from gui.sidecar import osa_settings

    active = llm.active_model()
    info = llm.get_model_info(active)
    return {
        "ready": True,
        "active_model": active,
        "active_label": info.label if info else active,
        # Brain pin (2026-07-07): null = automatic per-turn routing. Cached
        # read — existing pollers get the pin without a second endpoint.
        "pinned_model": osa_settings.get_model_pin(),
        "pinned_label": (
            osa_agent._model_label(osa_settings.get_model_pin())
            if osa_settings.get_model_pin() else None
        ),
        # Orb brain display (2026-07-07): what the LAST chat turn actually
        # ran on — lets the orb show "Pinned: Qwen (ran Claude)" after a
        # guardrail escalation instead of pretending the pin ran.
        "last_turn_model": _LAST_TURN["model"],
        "last_turn_label": (
            osa_agent._model_label(_LAST_TURN["model"])
            if _LAST_TURN["model"] else None
        ),
        "last_turn_escalated": bool(_LAST_TURN["escalated"]),
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


class OSAModelPin(BaseModel):
    """Request body for pinning OSA's brain."""

    model: str


def _model_payload() -> dict:
    """Shared GET/POST response: the pin + every pinnable choice.

    Availability comes from ``llm.list_models`` WITHOUT the ensure-Ollama
    spawn (this must stay cheap — the rail fetches it on mount). Choices are
    the curated registry PLUS the installed-but-uncurated Ollama models
    (``discovered: true``, 2026-07-07) — the same pinnable set
    ``set_model_pin`` enforces. Tony's RAM rule: an installed model flagged
    ``too_large`` surfaces as ``available: true`` with reason
    ``may_not_fit_ram`` — a warning the picker shows as a title, never a
    disabled entry.
    """
    from core import llm
    from gui.sidecar import osa_settings

    pin = osa_settings.get_model_pin()
    listing = llm.list_models(ensure_ollama=False)
    registry_ids = {m.id for m in llm.registry()}
    choices = []
    for row in listing.get("models", []):
        discovered = row["id"] not in registry_ids
        if discovered and not (row.get("is_local") and row.get("installed")):
            continue  # only installed local models join the shelf dynamically
        available, reason = row["available"], row["reason"]
        if row.get("is_local") and row.get("installed") and reason == "too_large":
            available, reason = True, "may_not_fit_ram"
        choices.append({
            "id": row["id"],
            "label": row["label"],
            "is_local": row["is_local"],
            "available": available,
            "reason": reason,
            "discovered": discovered,
        })
    # Cloud escape hatch (2026-07-07): an uncurated claude-* pin isn't in the
    # choices — append it so the rail's <select> can still display it.
    if pin and all(c["id"] != pin for c in choices):
        choices.append({
            "id": pin,
            "label": f"{pin} (custom)",
            "is_local": False,
            "available": True,
            "reason": "uncurated_cloud",
            "discovered": False,
        })
    return {
        "pinned_model": pin,
        "mode": "pinned" if pin else "auto",
        "ollama_up": bool(listing.get("ollama_up")),
        "choices": choices,
    }


@router.get("/api/osa/model")
def osa_model_get() -> dict:
    """Return OSA's brain pin state + the valid pin choices.

    ``pinned_model`` is null when routing is automatic; ``choices`` lists the
    registry models AND the installed Ollama models (``discovered: true``)
    with per-model ``available`` + ``reason`` so a picker can disable dead
    brains with an explanation (``may_not_fit_ram`` stays enabled — it's a
    warning, not a block).
    """
    return _model_payload()


@router.post("/api/osa/model")
def osa_model_set(body: OSAModelPin) -> dict:
    """Pin OSA's brain to a pinnable model id, or ``"auto"`` to clear.

    The pin is durable (MySQL ``osa_settings``) and takes effect on the next
    turn — no restart. Returns the same payload as GET after the change.

    Raises:
        HTTPException: 422 when the id isn't 'auto' or a registry model
            (detail lists the valid brains); 409 when the model exists but
            can't run right now (detail carries the reason).
    """
    from gui.sidecar import osa_settings

    try:
        osa_settings.set_model_pin(body.model)
    except osa_settings.UnknownBrainError as exc:
        raise HTTPException(422, str(exc)) from exc
    except osa_settings.UnavailableBrainError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _model_payload()


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


class OSAGreeting(BaseModel):
    """Request body for the presence greeting (``pending`` = items awaiting Tony)."""

    pending: int = 0


@router.post("/api/osa/greeting")
def osa_greeting_route(body: OSAGreeting) -> dict:
    """Return OSA's time-of-day welcome-back line and speak it (best-effort).

    Called by the app on launch + on return-after-away (2026-07-09). Templated
    and cheap; the line is spoken via the shared voice hook when voice-OUT is
    on, and captioned on the orb by the caller.
    """
    from gui.sidecar import osa_greeting

    text = osa_greeting.greeting(pending=body.pending)
    _maybe_speak_reply(text)
    return {"text": text}


# --------------------------------------------------------------------------- #
# Streaming chat over WebSocket (2026-07-07 late) — tokens + live tool events
# + REAL mid-run destructive confirms via LangGraph interrupt().
#
# Protocol (all frames carry "type"):
#   inbound  first frame: {"message": str, "thread_id"?: str}   — a new turn
#            OR           {"resume": "approve"|"deny", "thread_id": str}
#                         — resume a checkpointed interrupt on a FRESH socket
#                         (the interrupt survives socket death: it's parked on
#                         the MySQL checkpointer).
#   inbound  after an "awaiting_confirm" frame: {"resume": "approve"|"deny"}.
#   outbound: start {thread_id, model, route, pinned_model, escalated}
#             token {delta}                     — reply text as it generates
#             tool_start {tool, args} / tool_end {tool, ok}
#             awaiting_confirm {action, description}
#             final {reply, thread_id, model, route, pinned_model, escalated,
#                    tool_trace, confirmed}     — AUTHORITATIVE reply (echo
#                    scrub + escalation clause run on the finished text, so
#                    the client must replace what it streamed)
#             error {error}
#
# The confirm mechanism is transport-appropriate: this WS path uses a real
# interrupt() inside the guarded tool (the ToolNode re-raises GraphInterrupt;
# on Command(resume=...) the tool re-runs from the top, the guard fires again,
# and interrupt() returns the resume decision to _guarded's approval_fn). The
# sync POST route keeps the two-turn conversational confirm because it cannot
# block on a human — and voice (14d) will ride that path ("just say yes").
# --------------------------------------------------------------------------- #

# Fresh-socket resume needs the interrupted turn's model/flags to rebuild an
# identical agent. Thread-keyed, TTL-bounded like _PENDING_CONFIRM.
_WS_TURN_STATE: dict[str, dict] = {}


def _ws_approval_fn(action_type: str, description: str) -> str:
    """WS-mode approval bridge: park the graph on a real LangGraph interrupt.

    First execution raises GraphInterrupt (the run checkpoints + pauses); on
    ``Command(resume=decision)`` the tool re-runs and ``interrupt()`` RETURNS
    the decision, which ``_guarded``'s ``_is_yes`` then evaluates. Pre-guard
    code re-executes on the re-run — all current tools only validate/read
    before the guard, so that replay is side-effect free.
    """
    from langgraph.types import interrupt

    decision = interrupt({"action": action_type, "description": description})
    return str(decision)


def _chunk_text(msg) -> str:
    """Streamable text of one message chunk (skips tool-call-only chunks)."""
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") in (None, "text"):
                parts.append(part.get("text", ""))
        return "".join(parts)
    return ""


async def _pump_stream(agent, payload, config, ws: WebSocket, trace: list) -> dict:
    """Run ONE agent.stream pass in a worker thread, forwarding frames.

    The MySQL checkpointer is sync, so the graph runs via the sync ``stream``
    iterator on a daemon thread that pumps an asyncio.Queue (same shape as the
    diagnostics WS). Returns ``{"interrupt": dict|None, "last_text": str,
    "error": str|None}`` — an interrupt means the graph is parked awaiting a
    resume; ``last_text`` is the last complete agent message (authoritative
    over accumulated tokens).
    """
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()
    stop = threading.Event()

    def worker() -> None:
        """Iterate the sync graph stream; push chunks to the async side."""
        try:
            for mode, chunk in agent.stream(
                payload, config=config, stream_mode=["updates", "messages"]
            ):
                if stop.is_set():
                    break
                loop.call_soon_threadsafe(q.put_nowait, ("chunk", mode, chunk))
        except Exception as exc:  # noqa: BLE001 — surfaced as an error frame
            loop.call_soon_threadsafe(q.put_nowait, ("error", None, exc))
        finally:
            loop.call_soon_threadsafe(q.put_nowait, ("done", None, None))

    threading.Thread(target=worker, daemon=True).start()
    outcome: dict = {"interrupt": None, "last_text": "", "error": None}
    try:
        while True:
            kind, mode, item = await q.get()
            if kind == "done":
                break
            if kind == "error":
                outcome["error"] = str(item)
                break
            if mode == "messages":
                # (message_chunk, metadata) — only the agent node's text is
                # reply tokens; tool output rides "updates" instead.
                msg, meta = item if isinstance(item, tuple) else (item, {})
                if (meta or {}).get("langgraph_node") != "agent":
                    continue
                delta = _chunk_text(msg)
                if delta:
                    await ws.send_json({"type": "token", "delta": delta})
            elif mode == "updates" and isinstance(item, dict):
                for node, update in item.items():
                    if node == "__interrupt__":
                        intr = update[0] if isinstance(update, (list, tuple)) and update else update
                        value = getattr(intr, "value", None)
                        outcome["interrupt"] = value if isinstance(value, dict) else {}
                        continue
                    if not isinstance(update, dict):
                        continue
                    for m in update.get("messages", []) or []:
                        calls = getattr(m, "tool_calls", None) or []
                        for call in calls:
                            entry = {"tool": call.get("name"), "args": call.get("args", {})}
                            trace.append(entry)
                            await ws.send_json({"type": "tool_start", **entry})
                        if m.__class__.__name__ == "ToolMessage":
                            text = _extract_text(getattr(m, "content", ""))
                            ok = not text.startswith(("ERROR", "BLOCKED"))
                            await ws.send_json({
                                "type": "tool_end",
                                "tool": getattr(m, "name", None),
                                "ok": ok,
                            })
                        elif not calls:
                            text = _extract_text(getattr(m, "content", ""))
                            if text:
                                outcome["last_text"] = text
    except (WebSocketDisconnect, RuntimeError):
        stop.set()
        raise
    return outcome


@router.websocket("/api/osa/ws/chat")
async def osa_chat_ws(ws: WebSocket) -> None:
    """Streaming OSA turn: tokens + tool events + interrupt-based confirms."""
    await ws.accept()
    conn = None
    try:
        req = await ws.receive_json()
        resume_val = req.get("resume")
        thread_id = req.get("thread_id")
        message = (req.get("message") or "").strip()

        from langgraph.types import Command

        from agents import osa_agent
        from core import llm, memory
        from gui.sidecar import osa_proactive, osa_settings

        if resume_val is None and not message:
            await ws.send_json({"type": "error", "error": "message is required"})
            return
        if resume_val is not None and not thread_id:
            await ws.send_json({"type": "error", "error": "thread_id is required to resume"})
            return

        osa_proactive.note_chat_turn()

        if resume_val is not None:
            # Fresh-socket resume: rebuild the interrupted turn's agent. State
            # missing (TTL/restart) ⇒ Claude — interrupts only happen on tool
            # turns, and tool turns always run cloud (the local-pin guardrail).
            st = _WS_TURN_STATE.get(thread_id) or {}
            if st and time.time() - st.get("ts", 0) > _CONFIRM_TTL_SECONDS:
                st = {}
            pin = st.get("pin") if st else osa_settings.get_model_pin()
            model_id = st.get("model_id") or llm.resolve("default")
            route = st.get("route", "default")
            escalated = bool(st.get("escalated", False))
            brain_line = st.get("brain_line") or osa_agent.brain_prompt_line(
                pin=pin, effective=model_id, escalated=escalated
            )
            payload = Command(resume=str(resume_val))
            confirmed = str(resume_val).strip().lower() in ("approve", "yes", "y")
        else:
            thread_id = thread_id or f"osa-{uuid.uuid4().hex[:10]}"
            ollama_ready = osa_agent.warm_ollama()
            pin = osa_settings.get_model_pin()
            chosen = osa_agent.pick_model(message, ollama_ready=ollama_ready, pin=pin)
            model_id = llm.resolve(chosen)
            _info = llm.get_model_info(model_id)
            if _info is None:
                _info = llm.discover_ollama().get(model_id)
            route = "local" if (_info is not None and _info.is_local) else "default"
            escalated = bool(pin) and osa_agent._pin_is_local(pin) and chosen != pin
            brain_line = osa_agent.brain_prompt_line(
                pin=pin, effective=model_id, escalated=escalated
            )
            payload = {"messages": [{"role": "user", "content": message}]}
            confirmed = False

        conn = memory.checkpointer_conn()
        checkpointer = memory.get_checkpointer(conn)
        agent = osa_agent.build_agent(
            model_id, approval_fn=_ws_approval_fn, checkpointer=checkpointer,
            system_suffix=brain_line, voice_aware=_voice_is_on(),
        )
        config = {"configurable": {"thread_id": thread_id}}
        await ws.send_json({
            "type": "start", "thread_id": thread_id, "model": model_id,
            "route": route, "pinned_model": pin, "escalated": escalated,
        })

        # A fresh message (not a resume) on a thread still parked on a prior
        # gated interrupt would append a dangling tool call → INVALID_CHAT_HISTORY.
        # Clear it first (fail-closed deny); run off the event loop (sync + may
        # do one LLM call). A real resume intentionally resolves the interrupt.
        if resume_val is None:
            await asyncio.get_running_loop().run_in_executor(
                None, _heal_pending_interrupt, agent, config
            )

        trace: list[dict] = []
        while True:
            outcome = await _pump_stream(agent, payload, config, ws, trace)
            if outcome["error"]:
                logger.error("OSA WS turn failed: %s", outcome["error"])
                await ws.send_json({"type": "error", "error": outcome["error"]})
                return
            if outcome["interrupt"] is not None:
                intr = outcome["interrupt"]
                _WS_TURN_STATE[thread_id] = {
                    "model_id": model_id, "route": route, "escalated": escalated,
                    "pin": pin, "brain_line": brain_line, "ts": time.time(),
                }
                await ws.send_json({
                    "type": "awaiting_confirm",
                    "action": intr.get("action"),
                    "description": intr.get("description"),
                })
                nxt = await ws.receive_json()
                decision = str(nxt.get("resume") or "deny").strip().lower()
                confirmed = confirmed or decision in ("approve", "yes", "y")
                payload = Command(resume=decision)
                continue
            reply = outcome["last_text"]
            break

        _WS_TURN_STATE.pop(thread_id, None)
        reply = _scrub_reply(reply, brain_line, escalated=escalated)
        _LAST_TURN.update(model=model_id, escalated=escalated)
        # Voice-OUT (2026-07-08): speak the streamed reply too. The app's
        # PRIMARY chat path is THIS WebSocket (the sync POST is only a
        # fallback), so without this hook the app stays silent even with
        # voice enabled. Best-effort + non-blocking, same as the POST route.
        _maybe_speak_reply(reply)
        await ws.send_json({
            "type": "final", "reply": reply, "thread_id": thread_id,
            "model": model_id, "route": route, "pinned_model": pin,
            "escalated": escalated, "tool_trace": trace, "confirmed": confirmed,
        })
    except WebSocketDisconnect:
        logger.info("OSA WS: client disconnected")
    except Exception as exc:  # noqa: BLE001 — surface as an error frame
        logger.error("OSA WS failed: %s", exc, exc_info=True)
        try:
            await ws.send_json({"type": "error", "error": str(exc)})
        except Exception:  # noqa: BLE001
            pass
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
# Transcript restore (2026-07-07 late) — fold a checkpointed thread back into
# UI turns so the Agent view survives an app restart.
# --------------------------------------------------------------------------- #
def _fold_history(messages: list) -> list[dict]:
    """Fold LangChain messages into UI turns.

    Each HumanMessage starts a turn; the AI/tool messages that follow belong
    to it. The LAST non-empty AI text in a turn wins (matches what the chat
    route returned at the time); tool calls become the turn's trace. Stored AI
    text is pre-scrub, so the light echo scrub runs again here.
    """
    turns: list[dict] = []
    current: dict | None = None
    for m in messages:
        kind = m.__class__.__name__
        if kind == "HumanMessage":
            current = {"user": _extract_text(getattr(m, "content", "")),
                       "text": "", "tools": []}
            turns.append(current)
            continue
        if current is None:
            continue
        calls = getattr(m, "tool_calls", None) or []
        for call in calls:
            current["tools"].append({
                "tool": call.get("name"), "args": call.get("args", {}),
            })
        if kind == "ToolMessage":
            continue
        if not calls:
            text = _extract_text(getattr(m, "content", ""))
            if text:
                current["text"] = _scrub_reply(text, None, escalated=False)
    return turns


@router.get("/api/osa/history")
def osa_history(thread_id: str) -> dict:
    """Return a checkpointed OSA thread folded into UI turns.

    Degrades rather than fails: MySQL unreachable ⇒ ``available: false``;
    an unknown thread ⇒ ``exists: false``. Both return empty ``turns`` so
    the Agent view can hydrate opportunistically on mount.
    """
    thread_id = (thread_id or "").strip()
    if not thread_id:
        raise HTTPException(400, "thread_id is required")

    from core import memory

    conn = None
    try:
        conn = memory.checkpointer_conn()
        saver = memory.get_checkpointer(conn)
        tup = saver.get_tuple({"configurable": {"thread_id": thread_id}})
    except Exception as exc:  # noqa: BLE001 — degrade, never 500 the mount path
        logger.warning("OSA history unavailable: %s", exc)
        return {"thread_id": thread_id, "exists": False, "available": False,
                "turns": []}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    if tup is None:
        return {"thread_id": thread_id, "exists": False, "available": True,
                "turns": []}
    checkpoint = getattr(tup, "checkpoint", None) or {}
    messages = (checkpoint.get("channel_values") or {}).get("messages", []) or []
    return {
        "thread_id": thread_id,
        "exists": True,
        "available": True,
        "turns": _fold_history(messages),
    }
