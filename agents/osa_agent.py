"""OSA agent — the JARVIS-style assistant brain (Phase 14a, text MVP).

OSA is a dedicated, conversational LangGraph agent that operates AgenticOS in
short, spoken-style turns. It mirrors ``agents/governor.py`` in shape (a plain,
LangChain-free ``OSAToolbox`` of guarded string-returning tools + a lazily
constructed ``create_react_agent``) but is tuned for OSA's needs:

* **Voice-shaped output** — a concise, status-first system instruction on top of
  the sharp OSA persona (``config/Soul_OSA.md`` via ``core.soul``). No markdown
  or code dumps; say the useful thing and stop.
* **Model routing (decision #6 / §4.3)** — a cheap, pure ``route_turn``
  classifier picks alias ``local`` (Ollama) for chit-chat / acks / greetings and
  ``default`` (Claude) for reasoning and ANY tool-worthy turn. It is a small
  heuristic function so it is trivially unit-testable.
* **Ollama ensure-on-OSA-init (decision #9)** — ``warm_ollama()`` calls
  ``core.llm.ensure_ollama_running()`` at most once per process (best-effort,
  cached). If Ollama can't come up, ``pick_model`` downgrades ``local`` turns to
  ``default`` (Claude) so OSA never hard-fails.
* **Durable threads** — the graph is compiled with the MySQL checkpointer
  (``core.memory.get_checkpointer``) and run under a ``thread_id`` so a
  conversation survives sidecar restarts.

Safety mirrors the governor: every side-effectful tool passes
``constitution.guard`` first via ``OSAToolbox._guarded`` (BLOCKED on violation,
human approval bridged through ``approval_fn`` on ApprovalRequired). The toolbox
is a plain object so it is fully unit-testable without LangChain; ``build_agent``
does the lazy LangGraph construction.
"""
from __future__ import annotations

import json
import re
import threading
from typing import Any, Callable

from core.constitution import (
    ApprovalRequired,
    Constitution,
    ConstitutionViolation,
)

# The forked, sharp OSA persona (governor/briefing keep the plain shared soul).
OSA_SOUL_NAME = "Soul_OSA.md"

# Type of the human-approval bridge: (action_type, description) -> decision str.
ApprovalFn = Callable[[str, str], str]
# Optional tool-event sink: (phase, tool_name, info) -> None. phase in
# {"start", "end", "error"}. Lets the runner stream TOOL_CALL_* events.
EventFn = Callable[[str, str, dict], None]


OSA_SYSTEM = (
    "You are OSA, operating the user's Agentic OS out loud. Your replies are "
    "SPOKEN — assume they're read aloud through a speaker.\n\n"
    "Output rules (non-negotiable):\n"
    "- Be spoken-style: short sentences, no markdown, no bullet lists, no code "
    "blocks, no tables. Say the useful thing, then stop.\n"
    "- Status-first: lead with the number or the fact; explain only if it's "
    "wanted. E.g. 'RAM's at 73%. Nothing alarming.'\n"
    "- Crisp on commands: action plus result, tersely. 'Understood, Sir. "
    "Launching worldwise.'\n"
    "- Never fabricate a status, number, or result. If you don't know, say so, "
    "then use a tool to find out.\n\n"
    "How to act:\n"
    "- You have NO knowledge of the live system except what tools return. For "
    "any question about app status, system health, or to control an app, call "
    "the matching tool FIRST and answer from its result.\n"
    "- Map requests to tools, e.g.: 'is X running' / 'status of X' -> "
    "app_status; 'how's my memory' / 'system health' -> system_health; 'launch "
    "X' / 'start X' -> start_app; 'stop X' / 'shut down X' -> stop_app; "
    "'remember that ...' -> remember.\n"
    "- Side-effectful actions pass a safety guard. If a tool returns 'DENIED' "
    "or 'BLOCKED', respect it and tell the user plainly rather than retrying.\n"
    "- For pure chit-chat, a greeting, or an acknowledgement, just answer — no "
    "tool needed."
)


# --------------------------------------------------------------------------- #
# Ollama ensure-on-OSA-init (decision #9): best-effort, cached, non-fatal.
# --------------------------------------------------------------------------- #
_warm_lock = threading.Lock()
_warm_done = False
_ollama_ready = False


def warm_ollama() -> bool:
    """Ensure Ollama is up for OSA's local turns — once per process.

    Best-effort and cached: the first call spawns ``ollama serve`` via
    ``core.llm.ensure_ollama_running`` (detached, short wait); later calls
    return the cached result without re-spawning. Never raises — if Ollama's
    binary is missing or it won't come up, this returns ``False`` and OSA routes
    local turns to Claude instead (see ``pick_model``).

    Returns:
        True if Ollama is up (already-running or just-started), else False.
    """
    global _warm_done, _ollama_ready
    with _warm_lock:
        if _warm_done:
            return _ollama_ready
        try:
            from core import llm

            result = llm.ensure_ollama_running()
            _ollama_ready = bool(result.get("up"))
        except Exception:  # noqa: BLE001 — never let warming break a turn
            _ollama_ready = False
        _warm_done = True
        return _ollama_ready


def reset_ollama_warm_cache() -> None:
    """Reset the one-shot warm cache. Test-only helper."""
    global _warm_done, _ollama_ready
    with _warm_lock:
        _warm_done = False
        _ollama_ready = False


# --------------------------------------------------------------------------- #
# Turn routing (decision #6 / §4.3) — cheap, pure, unit-testable.
# --------------------------------------------------------------------------- #
# Words/phrases that signal a control or monitoring turn → Claude + tools.
_TOOL_HINTS = (
    "launch", "start", "stop", "shut down", "shutdown", "restart", "kill",
    "run ", "status", "health", "memory", "ram", "cpu", "disk", "how's",
    "hows", "how is", "is ", "are ", "which ", "list ", "show ", "check ",
    "remember", "delete", "remove", "why", "explain", "diagnose", "fix",
)
# Short conversational turns that a local model handles fine → Ollama.
_CHITCHAT = frozenset({
    "hi", "hey", "hello", "yo", "sup", "thanks", "thank you", "thx", "ok",
    "okay", "k", "cool", "nice", "great", "got it", "never mind", "nevermind",
    "cancel", "stop it", "good morning", "good night", "goodnight", "morning",
    "night", "bye", "goodbye", "yes", "no", "yep", "nope", "sure", "hey osa",
    "osa", "you there", "you up",
})


def route_turn(message: str) -> str:
    """Classify a turn → an LLM alias: ``"local"`` or ``"default"``.

    Heuristics (fast, no LLM): a very short greeting/ack routes to ``local``
    (Ollama — instant, private, $0). Anything that looks like a question,
    command, or tool-worthy request routes to ``default`` (Claude — reliable
    reasoning + tool use). Ambiguous longer text defaults to ``default`` so we
    never send a real task to the weaker model.

    Args:
        message: The user's turn text.

    Returns:
        ``"local"`` for chit-chat/acks, ``"default"`` otherwise.
    """
    text = (message or "").strip().lower()
    if not text:
        return "local"
    # Normalize trailing punctuation for the chit-chat exact match.
    stripped = text.rstrip("!.?,")
    if stripped in _CHITCHAT:
        return "local"
    if any(hint in text for hint in _TOOL_HINTS):
        return "default"
    if "?" in text:
        return "default"
    # Very short, no tool signal, not a question → treat as banter (local).
    if len(text.split()) <= 3:
        return "local"
    return "default"


def pick_model(message: str, *, ollama_ready: bool | None = None) -> str:
    """Resolve a turn to a concrete alias, honoring Ollama availability.

    Combines ``route_turn`` with the ensure-on-init state: if a turn would go
    to ``local`` but Ollama isn't up, it falls back to ``default`` (Claude) so
    OSA never hard-fails on a cold/absent local model (decision #9 / §10).

    Args:
        message: The user's turn text.
        ollama_ready: Whether Ollama is up. ``None`` uses the cached warm state.

    Returns:
        ``"local"`` or ``"default"``.
    """
    alias = route_turn(message)
    if alias == "local":
        ready = _ollama_ready if ollama_ready is None else ollama_ready
        if not ready:
            return "default"
    return alias


def _is_yes(decision: str | None) -> bool:
    """Check whether a human approval decision string is affirmative."""
    return str(decision).strip().lower() in ("y", "yes", "approve", "approved", "ok")


def _default_deny(action_type: str, description: str) -> str:  # pragma: no cover
    """Default approval function that always denies."""
    return "deny"


def _noop_event(phase: str, tool: str, info: dict) -> None:  # pragma: no cover
    """No-op event sink used when no event callback is provided."""
    return None


class OSAToolbox:
    """OSA's control/monitoring/memory tools as guarded Python methods.

    Each method returns a *string* (JSON or a short human-readable status)
    because that's what a tool-calling LLM consumes. Thin adapters over existing
    capability (``core.process_manager``, ``gui.sidecar.panels``, ``core.soul``)
    — OSA invents no new capability. Side-effectful methods pass
    ``constitution.guard`` first via ``_guarded`` (mirrors ``GovernorToolbox``).
    The class is LangChain-free so it is fully unit-testable on its own.
    """

    def __init__(
        self,
        constitution: Constitution | None = None,
        approval_fn: ApprovalFn = _default_deny,
        event_fn: EventFn = _noop_event,
    ) -> None:
        """Initialize the toolbox with constitution, approval, and event hooks.

        Args:
            constitution: Constitution for guard checks. Loaded if not provided.
            approval_fn: Callback invoked when a tool needs human approval.
            event_fn: Callback for tool lifecycle events (start/end/error).
        """
        self.constitution = constitution or Constitution.load()
        self.approval_fn = approval_fn
        self.event_fn = event_fn

    # ------------------------------------------------------------------ guard
    def _guarded(self, action_type: str, payload: str, do: Callable[[], Any]) -> str:
        """Run ``do`` only after the Constitution clears ``action_type``.

        Blocked -> 'BLOCKED: ...'. Approval needed -> ask the human via
        approval_fn; on yes, re-guard with approved=True and proceed; on no,
        'DENIED: ...'. (Mirrors ``GovernorToolbox._guarded``.)
        """
        try:
            self.constitution.guard(action_type, payload)
        except ConstitutionViolation as cv:
            return f"BLOCKED: {cv}"
        except ApprovalRequired as ar:
            decision = self.approval_fn(action_type, ar.description or payload)
            if not _is_yes(decision):
                return f"DENIED: human did not approve '{action_type}'."
            try:
                self.constitution.guard(action_type, payload, approved=True)
            except ConstitutionViolation as cv:
                return f"BLOCKED: {cv}"
        return self._run(action_type, payload, do)

    def _run(self, action_type: str, payload: str, do: Callable[[], Any]) -> str:
        """Execute ``do``, emit lifecycle events, and return a string result."""
        self.event_fn("start", action_type, {"payload": payload})
        try:
            result = do()
            text = result if isinstance(result, str) else json.dumps(result, default=str)
            self.event_fn("end", action_type, {"ok": True})
            return text
        except Exception as exc:  # noqa: BLE001 — surface to the model, don't crash the turn
            self.event_fn("error", action_type, {"error": str(exc)})
            return f"ERROR running '{action_type}': {exc}"

    # ------------------------------------------------------------ monitoring
    def system_health(self) -> str:
        """Report live system health — CPU, RAM, disk. Read-only.

        Use for 'how's my memory', 'system status', 'how's the machine'. Returns
        a compact JSON snapshot the model should summarize aloud, status-first.
        """
        from gui.sidecar import panels

        def _do() -> dict:
            """Collect a trimmed system-health snapshot for spoken summary."""
            h = panels.system_health()
            ram = h.get("ram", {}) or {}
            disks = h.get("disks", []) or []
            root = next((d for d in disks if d.get("mount") == "/"), None) or (
                disks[0] if disks else {}
            )
            return {
                "cpu_percent": h.get("cpu_percent"),
                "ram_percent": ram.get("percent"),
                "ram_used_gb": ram.get("used_gb"),
                "ram_total_gb": ram.get("total_gb"),
                "disk_mount": root.get("mount"),
                "disk_percent": root.get("percent"),
                "disk_free_gb": root.get("free_gb"),
            }

        return self._run("system_health", "", _do)

    def app_status(self, app_id: str) -> str:
        """Report whether an app is running (+ pid/port). Read-only.

        Use for 'is X running', 'status of X'. ``app_id`` is the app's registry
        id (e.g. 'worldwise'). Returns a compact JSON status.
        """
        app_id = (app_id or "").strip()
        if not app_id:
            return "ERROR: app_id required."

        def _do() -> dict:
            """Query the process manager for this app's status."""
            from core.process_manager import manager

            s = manager.status(app_id)
            return {
                "app_id": s.get("app_id"),
                "running": s.get("running"),
                "pid": s.get("pid"),
                "port": s.get("port"),
                "url": s.get("url"),
                "error": s.get("error"),
            }

        return self._run("app_status", app_id, _do)

    # ------------------------------------------------------------- control
    def start_app(self, app_id: str) -> str:
        """Launch an app by its registry id (e.g. 'worldwise'). Guarded.

        Use for 'launch X', 'start X'. Starting an app passes the Constitution
        guard (app_start gate); returns the resulting running status or a
        BLOCKED/DENIED message.
        """
        app_id = (app_id or "").strip()
        if not app_id:
            return "ERROR: app_id required."

        def _do() -> dict:
            """Start the app via the process manager (async run to completion)."""
            return _run_coro(_manager_start(app_id))

        return self._guarded("app_start", app_id, _do)

    def stop_app(self, app_id: str) -> str:
        """Stop a running app by its registry id. Guarded.

        Use for 'stop X', 'shut down X'. Stopping passes the Constitution guard
        (app_stop gate); returns the stopped status (with killed_pids) or a
        BLOCKED/DENIED message.
        """
        app_id = (app_id or "").strip()
        if not app_id:
            return "ERROR: app_id required."

        def _do() -> dict:
            """Stop the app via the process manager (async run to completion)."""
            return _run_coro(_manager_stop(app_id))

        return self._guarded("app_stop", app_id, _do)

    # -------------------------------------------------------------- memory
    def remember(self, note: str) -> str:
        """Save a durable fact, preference, or context to long-term memory.

        Appends to config/Memory.md so it survives across sessions and models.
        Append-only, no approval needed; returns a short confirmation. Use this
        whenever the user tells you something worth remembering.
        """
        from core import soul

        return soul.remember(note, source="osa")


# --------------------------------------------------------------------------- #
# Async process-manager adapters (start/stop are coroutines).
# --------------------------------------------------------------------------- #
async def _manager_start(app_id: str) -> dict:
    """Await the process manager's start for ``app_id`` and trim the status."""
    from core.process_manager import manager

    s = await manager.start(app_id)
    return {
        "app_id": s.get("app_id"), "running": s.get("running"),
        "pid": s.get("pid"), "port": s.get("port"),
        "url": s.get("url"), "error": s.get("error"),
    }


async def _manager_stop(app_id: str) -> dict:
    """Await the process manager's stop for ``app_id`` and trim the status."""
    from core.process_manager import manager

    s = await manager.stop(app_id)
    return {
        "app_id": s.get("app_id"), "running": s.get("running"),
        "killed_pids": s.get("killed_pids", []), "error": s.get("error"),
    }


def _run_coro(coro):
    """Run an async coroutine to completion from a sync tool method.

    OSA tools run on the agent's worker thread (no event loop), so a plain
    ``asyncio.run`` is correct here. If a loop is somehow already running on
    this thread, fall back to a dedicated thread so we never deadlock.
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        return asyncio.run(coro)

    result: dict = {}

    def _worker() -> None:
        """Run the coroutine on a fresh loop in its own thread."""
        result["value"] = asyncio.run(coro)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join()
    return result.get("value")


# --------------------------------------------------------------------------- #
# LangGraph ReAct agent construction (lazy — keeps this module import-light).
# --------------------------------------------------------------------------- #
def build_tools(toolbox: OSAToolbox) -> list:
    """Wrap an OSAToolbox's methods as LangChain StructuredTools."""
    from langchain_core.tools import StructuredTool

    specs = [
        (toolbox.system_health, "system_health"),
        (toolbox.app_status, "app_status"),
        (toolbox.start_app, "start_app"),
        (toolbox.stop_app, "stop_app"),
        (toolbox.remember, "remember"),
    ]
    return [
        StructuredTool.from_function(func=fn, name=name, description=(fn.__doc__ or name).strip())
        for fn, name in specs
    ]


def _prompt_with_tool_manifest(tools: list) -> str:
    """OSA_SYSTEM + an explicit roster of the bound tools.

    Naming the tools in the system prompt (in addition to binding them) makes it
    far less likely a small model claims it "has no tools".
    """
    lines = []
    for t in tools:
        desc = (getattr(t, "description", "") or "").strip()
        first = desc.splitlines()[0].strip() if desc else ""
        lines.append(f"- {t.name}: {first}" if first else f"- {t.name}")
    roster = "\n".join(lines)
    return (
        f"{OSA_SYSTEM}\n\n"
        "You DO have tools available — the following are bound and callable "
        "RIGHT NOW. Never claim you have no tools; call the matching one:\n"
        f"{roster}"
    )


def build_agent(
    model_id: str | None = None,
    *,
    toolbox: OSAToolbox | None = None,
    constitution: Constitution | None = None,
    approval_fn: ApprovalFn = _default_deny,
    event_fn: EventFn = _noop_event,
    checkpointer: Any | None = None,
):
    """Build a compiled LangGraph ReAct OSA agent over the toolbox.

    ``model_id`` is a concrete model id (or alias-resolved id) — callers usually
    pass the result of ``pick_model`` through ``core.llm.resolve``. Pass a
    ``checkpointer`` (a ``PyMySQLSaver`` from ``core.memory.get_checkpointer``)
    to make threads durable; omit it for a stateless agent (unit tests). All
    heavy imports are local so the toolbox stays testable without LangChain.
    """
    from langgraph.prebuilt import create_react_agent

    from core import llm, soul

    toolbox = toolbox or OSAToolbox(
        constitution=constitution, approval_fn=approval_fn, event_fn=event_fn
    )
    model = llm.get_chat_model(model_id)
    tools = build_tools(toolbox)
    prompt = _prompt_with_tool_manifest(tools)
    preamble = soul.identity_preamble(soul_name=OSA_SOUL_NAME)
    if preamble:
        prompt = f"{preamble}\n\n{prompt}"
    kwargs: dict[str, Any] = {"prompt": prompt}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
    return create_react_agent(model, tools, **kwargs)
