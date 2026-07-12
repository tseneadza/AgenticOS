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
    "app_status; 'how's my memory' / 'system health' -> system_health; 'which "
    "apps are up' / 'are my apps healthy' -> apps_health; 'what projects do I "
    "have' / 'list my projects' -> list_projects; 'launch X' / 'start X' -> "
    "start_app; 'stop X' / 'shut down X' -> stop_app; 'what time is it' / "
    "'what's the date' -> get_time; 'run <command>' / any terminal request "
    "-> run_command; 'remember that ...' -> "
    "remember; 'switch to Sonnet' / 'use your local brain' / 'back to auto' "
    "-> switch_model; 'pull llama3.3' / 'download a model' / 'add a new local "
    "model' -> pull_model. Files (inside ~/Codehome and ~/Brain2): 'read <file>' -> read_file; 'list <dir>' -> list_dir; 'find <files>' -> search_files; 'save/write to <file>' -> write_file; 'append to <file>' -> append_file; 'move/rename <file>' -> move_file; 'delete <file>' -> delete_file. Messages (iMessage, needs Full Disk Access): 'read my messages with <person>' -> read_messages; 'search messages for <text>' -> search_messages; 'recent chats' / 'who have I messaged' -> list_recent_chats. Any full claude-* id (e.g. 'claude-opus-4-8') is "
    "switchable even if not on the shelf; a bare cloud family name you don't "
    "recognize -> ask Tony for the full id rather than guessing one.\n"
    "- Your own brain is stated in the 'Brain status' line at the end of this "
    "prompt. When asked what model/brain you are running on, answer from that "
    "line directly — no tool call needed (switch_model with 'status' works "
    "too).\n"
    "- Destructive or irreversible actions (delete, move, overwrite) pass a "
    "safety guard. ALWAYS CALL THE TOOL to attempt the action FIRST — do NOT "
    "ask for permission before calling it. The guard either runs it or returns "
    "'DENIED', and that DENIED is the ONLY signal that Tony's OK is needed: then "
    "say plainly what you're about to do and ask him to confirm. When he replies "
    "'yes', call the SAME tool again and it proceeds. Never ask for confirmation "
    "WITHOUT first calling the tool — a bare ask arms nothing, so his 'yes' can "
    "approve nothing. If a tool returns 'BLOCKED', respect it and explain. NEVER "
    "accomplish a denied or blocked action by another route (run_command, rm, "
    "etc.) — working around your own safety guard is forbidden.\n"
    "- For pure chit-chat, a greeting, or an acknowledgement, just answer — no "
    "tool needed."
)


# Voice-awareness line (2026-07-09) — appended to the system prompt ONLY when
# voice-OUT is live, so OSA stops telling Tony "I'm text-only, no microphone"
# mid voice-chat (found live 2026-07-08). Kept short and factual; the routes
# compute the flag from the Constitution's voice block and pass it through
# build_agent(voice_aware=...). When voice is OFF this line is absent, so OSA
# never claims ears it doesn't have.
VOICE_AWARENESS_LINE = (
    "Voice is ON: your replies are spoken aloud through a speaker, and Tony "
    "can talk to you by microphone (push-to-talk or the 'Osa' wake word). You "
    "are NOT text-only — never say you have no voice, no microphone, or that "
    "you can't hear or speak. If a turn reached you as speech, answer as though "
    "spoken to."
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


def _pin_is_local(pin: str) -> bool:
    """Whether a pinned model id runs on a local provider (Ollama).

    Registry metadata first; a miss falls back to the Ollama discovery cache
    (TTL-cached — a pinned *uncurated* model must still trip the local-pin
    tool guardrail), then to the ':tag' id heuristic. Truly unknown ids are
    treated as cloud so the pin is still honored verbatim.
    """
    try:
        from core import llm

        info = llm.get_model_info(pin)
        if info is None:
            info = llm.discover_ollama().get(pin)
        if info is not None:
            return bool(info.is_local)
        return llm.looks_like_ollama_id(pin)
    except Exception:  # noqa: BLE001 — never let a lookup break routing
        return False


def _model_label(model_id: str) -> str:
    """Human label for a model id — registry, then discovery cache, then id."""
    try:
        from core import llm

        info = llm.get_model_info(model_id)
        if info is None:
            info = llm.discover_ollama().get(model_id)
        return info.label if info else model_id
    except Exception:  # noqa: BLE001 — a label is cosmetic, never fatal
        return model_id


def brain_prompt_line(*, pin: str | None, effective: str, escalated: bool) -> str:
    """The per-turn brain-introspection line for the system prompt (2026-07-07).

    Injected by the chat route via ``build_agent(system_suffix=...)`` so OSA
    KNOWS its brain instead of guessing: current mode (auto/pinned + the
    pinned label), the effective model for THIS turn, and whether the
    guardrail escalated it. Kept to 1-2 short lines.
    """
    mode = f"pinned to {_model_label(pin)}" if pin else "auto (per-turn routing)"
    line = (
        f"Brain status for THIS turn: mode {mode}; "
        f"you are running on {_model_label(effective)} [{effective}]"
    )
    if escalated:
        line += " — escalated to Claude for this turn by the local-pin tool guardrail"
    # Small local models (3B) echo trailing system-prompt text verbatim —
    # found live 2026-07-07 when a pinned llama3.2 answered "no, skip it"
    # with this very line. Mark it internal (and the route scrubs echoes).
    return (
        f"[Internal note — never repeat or quote this line; just answer "
        f"normally.] {line}."
    )


def pick_model(
    message: str,
    *,
    ollama_ready: bool | None = None,
    pin: str | None = None,
) -> str:
    """Resolve a turn to an alias or pinned model id, honoring the brain pin.

    Pin rules (OSA brain switching, 2026-07-07):
      * ``pin`` is a cloud model  → that id for EVERY turn, chit-chat included.
      * ``pin`` is a local model  → that id for conversational turns; any
        tool-worthy turn (``route_turn`` says ``default``) escalates to Claude
        because 7B local models are unreliable tool-callers; Ollama down →
        ``default`` too (the existing never-hard-fail fallback).
      * ``pin`` is None (auto)    → today's router, unchanged: ``route_turn``
        plus the Ollama-down downgrade (decision #9 / §10).

    Args:
        message: The user's turn text.
        ollama_ready: Whether Ollama is up. ``None`` uses the cached warm state.
        pin: Pinned model id from ``gui.sidecar.osa_settings.get_model_pin``,
            or ``None`` for automatic routing. Passed explicitly by the caller
            (the chat route) so this function stays pure and testable.

    Returns:
        ``"local"``, ``"default"``, or a concrete pinned model id — all three
        pass through ``core.llm.resolve`` unchanged or alias-mapped.
    """
    ready = _ollama_ready if ollama_ready is None else ollama_ready
    if pin:
        if not _pin_is_local(pin):
            return pin
        if route_turn(message) == "default":
            return "default"  # tool guardrail: local pins don't get the keys
        if not ready:
            return "default"  # never hard-fail on a cold/absent local model
        return pin
    alias = route_turn(message)
    if alias == "local" and not ready:
        return "default"
    return alias


# --------------------------------------------------------------------------- #
# Model pulls (2026-07-07) — approval-gated, background, announced on landing.
# --------------------------------------------------------------------------- #
# switch_model status-intent tokens ("what's your brain" → facts, no change).
_BRAIN_STATUS_TOKENS = frozenset({"status", "current", "query", "which", "now"})

# A plausible Ollama model ref: name[/name][:tag] — anything else is refused
# before the approval gate so Tony is never asked to confirm garbage.
_OLLAMA_REF_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)?"
    r"(?::[A-Za-z0-9._-]+)?$"
)

_pull_lock = threading.Lock()
_pulls_in_flight: set[str] = set()


def reset_pull_state() -> None:
    """Clear the in-flight pull registry. Test-only helper."""
    with _pull_lock:
        _pulls_in_flight.clear()


def pulls_in_flight() -> list[str]:
    """Names of the pulls currently running (sorted copy)."""
    with _pull_lock:
        return sorted(_pulls_in_flight)


def _run_pull(name: str) -> dict:
    """Run one blocking pull via ``core.llm.pull_ollama_model`` (test seam)."""
    from core import llm

    return llm.pull_ollama_model(name)


def _pull_worker(name: str) -> None:
    """Background body of one pull: run, deregister, announce the outcome.

    Success and failure BOTH land in the proactive ring buffer
    (``osa_proactive.post_model_event``) so the orb/rail/HUD surface the news;
    a nonexistent model errors cleanly out of Ollama and arrives here as a
    failure. Never raises — it's a daemon thread with nobody above it.
    """
    try:
        result = _run_pull(name)
    except Exception as exc:  # noqa: BLE001 — a crashed pull is a failed pull
        result = {"ok": False, "error": str(exc)}
    ok = bool(result.get("ok"))
    # Announce BEFORE deregistering — once the name leaves the in-flight set,
    # observers (tests, a duplicate ask) must already be able to see the
    # outcome in the ring buffer. A duplicate ask during the announce gets an
    # honest "already pulling"; the reverse order had a gap with neither.
    try:
        from gui.sidecar import osa_proactive

        osa_proactive.post_model_event(name, ok=ok, error=result.get("error"))
    except Exception:  # noqa: BLE001 — the pull already finished; stay quiet
        pass
    with _pull_lock:
        _pulls_in_flight.discard(name)


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
    def _guarded(
        self, action_type: str, payload: str, do: Callable[[], Any],
        describe: str | None = None,
    ) -> str:
        """Run ``do`` only after the Constitution clears ``action_type``.

        Blocked -> 'BLOCKED: ...'. Approval needed -> ask the human via
        approval_fn; on yes, re-guard with approved=True and proceed; on no,
        'DENIED: ...'. (Mirrors ``GovernorToolbox._guarded``.)

        ``describe`` overrides the Constitution's static action description
        for the approval ask (2026-07-07) — pull_model uses it to carry the
        size/RAM verdict into the pending-confirm so Tony's confirm question
        is informed ("≈42.5GB — too big for your 16GB RAM").
        """
        try:
            self.constitution.guard(action_type, payload)
        except ConstitutionViolation as cv:
            return f"BLOCKED: {cv}"
        except ApprovalRequired as ar:
            description = describe or ar.description or payload
            decision = self.approval_fn(action_type, description)
            if not _is_yes(decision):
                # Instructive DENIED (2026-07-07): Tony's live test showed the
                # model RETRYING a denied tool instead of asking him. Tell it
                # exactly what to do next.
                return (
                    f"DENIED: '{action_type}' needs Tony's OK first — "
                    f"{description}. Tell him what you want to do and ask him "
                    "to confirm (a plain 'yes' works). Do NOT call this tool "
                    "again until he answers."
                )
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

    def _run_capability(
        self, cap_name: str, payload: str, call: Callable[..., Any]
    ) -> str:
        """Run a Phase-15 GUARDED capability, bridging its guard to approval_fn.

        System-MCP capabilities carry their own capability-layer guard (the
        harness applied it at registration), so unlike ``_guarded`` we don't
        pre-check the Constitution — we call, catch the guard's exceptions,
        and on approval retry with ``approved=True``. Denies (denylist hits)
        can never be overridden.
        """
        self.event_fn("start", cap_name, {"payload": payload})
        try:
            try:
                result = call()
            except ApprovalRequired as ar:
                decision = self.approval_fn(cap_name, ar.description)
                if not _is_yes(decision):
                    self.event_fn("end", cap_name, {"ok": False, "denied": True})
                    return (
                        f"DENIED: '{cap_name}' needs Tony's OK first — "
                        f"{ar.description}. Tell him what you want to do and "
                        "ask him to confirm (a plain 'yes' works). Do NOT "
                        "call this tool again until he answers."
                    )
                result = call(approved=True)
            text = result if isinstance(result, str) else json.dumps(result, default=str)
            self.event_fn("end", cap_name, {"ok": True})
            return text
        except ConstitutionViolation as cv:
            self.event_fn("end", cap_name, {"ok": False, "blocked": True})
            return f"BLOCKED: {cv}"
        except Exception as exc:  # noqa: BLE001 — surface to the model, don't crash
            self.event_fn("error", cap_name, {"error": str(exc)})
            return f"ERROR running '{cap_name}': {exc}"

    # ------------------------------------------------- system MCP (15a)
    def get_time(self) -> str:
        """Report the current local time and date on this Mac. Read-only.

        Use for 'what time is it', 'what's the date', 'what day is it'.
        Returns a compact JSON snapshot (local time, timezone, ISO, unix)
        to summarize aloud — lead with the local time.
        """
        from tools.system import macos_mcp

        return self._run_capability("macos.get_time", "", macos_mcp.get_time)

    def run_command(self, command: str) -> str:
        """Run a terminal command on this Mac. Guarded — safe ones auto-run.

        Use for 'run <command>', 'check disk with df', any explicit terminal
        request. Allowlisted read-only commands (date, uptime, ls, df, git
        status, ...) run immediately; anything else needs Tony's OK first
        (say what you'll run and ask him to confirm). Destructive patterns
        are blocked outright. Returns JSON with stdout/stderr/returncode —
        summarize the OUTPUT aloud, don't read it verbatim.
        """
        command = (command or "").strip()
        if not command:
            return "ERROR: command required."

        from tools.system import macos_mcp

        return self._run_capability(
            "macos.run_command",
            command,
            lambda **kw: macos_mcp.run_command(command, **kw),
        )

    # ------------------------------------------------- filesystem (15b, scoped)
    def read_file(self, path: str) -> str:
        """Read a text file inside the allowed roots (~/Codehome, ~/Brain2). Read-only.

        Use for 'read <file>', 'show me <file>', 'what's in <path>'. Returns
        JSON with the (capped) content — summarize aloud, don't read verbatim.
        """
        from tools.system import fs_mcp

        return self._run_capability("fs.read_file", path, lambda **kw: fs_mcp.read_file(path, **kw))

    def list_dir(self, path: str) -> str:
        """List a directory inside the allowed roots. Read-only.

        Use for 'list <dir>', 'what's in <folder>', 'show my Codehome files'.
        """
        from tools.system import fs_mcp

        return self._run_capability("fs.list_dir", path, lambda **kw: fs_mcp.list_dir(path, **kw))

    def search_files(self, root: str, pattern: str) -> str:
        """Find files by name glob under a directory in the allowed roots. Read-only.

        Use for 'find <pattern> files', 'search for *.md under <dir>'.
        """
        from tools.system import fs_mcp

        return self._run_capability("fs.search", root, lambda **kw: fs_mcp.search(root, pattern, **kw))

    def write_file(self, path: str, content: str) -> str:
        """Write a text file in the allowed roots. Guarded — auto only inside scratch.

        Use for 'save this to <file>', 'write <content> to <path>'. Outside the
        scratch folder it needs Tony's OK first — say what you'll write and ask
        him to confirm (a plain 'yes' works).
        """
        from tools.system import fs_mcp

        return self._run_capability("fs.write_file", path, lambda **kw: fs_mcp.write_file(path, content, **kw))

    def append_file(self, path: str, content: str) -> str:
        """Append text to a file in the allowed roots. Guarded (auto inside scratch).

        Use for 'append <text> to <file>', 'add a line to <path>'.
        """
        from tools.system import fs_mcp

        return self._run_capability("fs.append", path, lambda **kw: fs_mcp.append(path, content, **kw))

    def move_file(self, src: str, dst: str) -> str:
        """Move/rename a file inside the allowed roots. Irreversible — needs Tony's OK.

        Use for 'move <a> to <b>', 'rename <file>'. Both ends must be inside
        the allowed roots. Say what you'll move and ask him to confirm.
        """
        from tools.system import fs_mcp

        return self._run_capability("fs.move", src, lambda **kw: fs_mcp.move(src, dst, **kw))

    def delete_file(self, path: str) -> str:
        """Delete a file or EMPTY directory in the allowed roots. Irreversible — needs Tony's OK.

        Use for 'delete <file>', 'remove <path>'. Ask him to confirm first.
        """
        from tools.system import fs_mcp

        return self._run_capability("fs.delete", path, lambda **kw: fs_mcp.delete(path, **kw))

    # ------------------------------------------------- iMessage reads (15c)
    def read_messages(self, contact: str) -> str:
        """Read recent iMessages with a contact (phone/email handle). Read-only. Needs Full Disk Access.

        Use for 'read my messages with <person>', 'what did <handle> say'.
        """
        from tools.system import messages_mcp

        return self._run_capability("messages.read_thread", contact, lambda **kw: messages_mcp.read_thread(contact, **kw))

    def search_messages(self, query: str) -> str:
        """Search iMessage text for a substring. Read-only. Needs Full Disk Access.

        Use for 'search my messages for <text>', 'did anyone mention <x>'.
        """
        from tools.system import messages_mcp

        return self._run_capability("messages.search_messages", query, lambda **kw: messages_mcp.search_messages(query, **kw))

    def list_recent_chats(self) -> str:
        """List recent iMessage conversations. Read-only. Needs Full Disk Access.

        Use for 'what are my recent chats', 'who have I been messaging'.
        """
        from tools.system import messages_mcp

        return self._run_capability("messages.list_recent_chats", "", messages_mcp.list_recent_chats)

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

    # ---------------------------------------------------- monitoring (14b)
    def apps_health(self) -> str:
        """Report which apps are up and healthy right now. Read-only.

        Use for 'how are my apps', 'which apps are up', 'is everything
        healthy'. Wraps the same aggregation that backs GET /api/apps/health:
        only running apps that have a health signal appear. Returns a compact
        JSON snapshot (per-app healthy flag + a total) the model summarizes
        aloud, status-first.
        """
        from gui.sidecar import launch_config

        def _do() -> dict:
            """Aggregate per-app health into a spoken-friendly summary."""
            h = launch_config.list_all_health()
            apps = h.get("apps", {}) or {}
            summary = {
                app_id: {
                    "healthy": bool(entry.get("healthy")),
                    "ports": len(entry.get("ports", []) or []),
                }
                for app_id, entry in apps.items()
            }
            unhealthy = [a for a, e in summary.items() if not e["healthy"]]
            return {
                "total": h.get("total", len(summary)),
                "apps": summary,
                "unhealthy": unhealthy,
            }

        return self._run("apps_health", "", _do)

    def list_projects(self) -> str:
        """List scaffolded projects from the ledger. Read-only.

        Use for 'what projects do I have', 'list my projects'. Wraps the same
        ledger query that backs GET /api/projects; returns a compact JSON list
        (name/template/subfolder/port) the model summarizes aloud. Degrades to
        an empty list if the ledger is unreachable rather than failing.
        """
        def _do() -> dict:
            """Query the projects ledger (same source as /api/projects)."""
            from gui.sidecar.db import SessionLocal
            from gui.sidecar.models import Project

            try:
                session = SessionLocal()
            except Exception:  # noqa: BLE001 — degrade like the route
                return {"projects": [], "total": 0, "available": False}
            try:
                rows = (
                    session.query(Project)
                    .order_by(Project.created_at.desc())
                    .all()
                )
                projects = [
                    {
                        "name": p.name,
                        "template": p.template,
                        "subfolder": p.subfolder,
                        "port": p.port,
                    }
                    for p in rows
                ]
                return {"projects": projects, "total": len(projects)}
            finally:
                session.close()

        return self._run("list_projects", "", _do)

    # ------------------------------------------------------- brain switching
    def switch_model(self, target: str) -> str:
        """Switch OSA's brain — pin every turn to one model, or back to auto.

        Use for 'switch to Sonnet', 'use your local brain', 'back to auto' —
        or to ASK about the brain: target 'status' / 'current' / '?' reports
        the mode and pin without changing anything. ``target`` is the brain in
        the user's words ('sonnet', 'haiku', 'local', 'qwen', an installed
        Ollama model like 'mistral:latest', a full model id, or 'auto'). The
        pin is durable (survives restarts); a local pin still sends tool work
        to Claude. Not destructive — no approval needed.
        """
        target = (target or "").strip()

        def _do() -> str:
            """Resolve the spoken name, validate, pin, confirm in persona."""
            from core import llm
            from gui.sidecar import osa_settings

            # Status/query intent — report the facts, change nothing.
            if target.lower().rstrip("?!. ") in _BRAIN_STATUS_TOKENS or target == "?":
                pin = osa_settings.get_model_pin()
                if not pin:
                    return (
                        "Automatic routing — the local brain takes small "
                        "talk, Claude takes reasoning and tools."
                    )
                label = _model_label(pin)
                if _pin_is_local(pin):
                    return (
                        f"Pinned to {label}. Tool work still escalates "
                        "to Claude."
                    )
                return f"Pinned to {label} for every turn."

            res = osa_settings.resolve_brain(target)
            status = res.get("status")
            if status == "ambiguous":
                opts = ", ".join(res.get("matches", []))
                return (
                    f"Which brain did you mean? That matches {opts}. "
                    "Say the word and I'll switch."
                )
            if status == "unknown":
                valid = ", ".join(res.get("valid", []))
                return (
                    f"No brain called '{target}' on the shelf. "
                    f"I've got auto, {valid}."
                )
            if status == "auto":
                osa_settings.set_model_pin(None)
                return (
                    "Back on automatic routing. "
                    "I'll pick the right brain per turn."
                )
            model = res["model"]
            try:
                osa_settings.set_model_pin(model)
            except osa_settings.UnavailableBrainError as exc:
                return f"Can't switch — {exc}. Staying where I am."
            info = llm.get_model_info(model)
            if info is None:  # discovered (uncurated) Ollama model
                info = next(
                    (i for i in osa_settings._discovered_infos() if i.id == model),
                    None,
                )
            label = info.label if info else model
            is_local = bool(info.is_local) if info else llm.looks_like_ollama_id(model)
            # RAM note (2026-07-07): pinnable, but warn when it may not fit.
            warn = ""
            try:
                if osa_settings._availability(model)[1] == "may_not_fit_ram":
                    warn = (
                        " She'll be slow, Sir — that one's bigger than "
                        "your RAM."
                    )
            except Exception:  # noqa: BLE001 — the warning is best-effort
                pass
            if is_local:
                return (
                    f"Switched to {label}. Anything needing tools still goes "
                    f"to Claude — the local brain doesn't get the keys.{warn}"
                )
            # Uncurated cloud pin (escape hatch): the id shape + key were
            # checked, but only Anthropic knows if the id is real — be honest.
            if osa_settings.is_uncurated_cloud(model):
                return (
                    f"Switched to {label}. That one's not on my curated "
                    "shelf, so if Anthropic doesn't recognize the id, "
                    "you'll hear about it on the next turn."
                )
            return (
                f"Switched to {label}. Every turn goes there "
                f"until you say otherwise.{warn}"
            )

        # Same _guarded plumbing as every other tool for consistency — the
        # Constitution has no switch_model approval gate, so this never blocks.
        return self._guarded("switch_model", target, _do)

    def pull_model(self, name: str) -> str:
        """Download a new local model through Ollama. Guarded — needs Tony's OK.

        Use for 'pull llama3.3', 'download mistral', 'add a new local model'.
        ``name`` is an Ollama model ref (e.g. 'llama3.3' or
        'qwen2.5:7b-instruct'). Pulls are multi-GB, so the model_pull gate
        asks Tony to confirm first; approved pulls run in the background and
        OSA announces completion through the proactive feed. Asking again
        while a pull is running reports progress instead of restarting it.
        """
        name = (name or "").strip()
        if not name:
            return "ERROR: model name required."
        if not _OLLAMA_REF_RE.match(name):
            return (
                f"'{name}' doesn't look like an Ollama model name, Sir. "
                "Give me something like llama3.3 or qwen2.5:7b-instruct."
            )
        # Duplicate and already-installed asks are answered up front — no
        # point walking Tony through an approval for a no-op.
        with _pull_lock:
            if name in _pulls_in_flight:
                return (
                    f"Already pulling {name}. "
                    "I'll let you know the moment it lands."
                )
        try:
            from core import llm

            if name in llm.discover_ollama():
                return (
                    f"{name} is already on the shelf. "
                    f"Say 'switch to {name}' and it's yours."
                )
        except Exception:  # noqa: BLE001 — discovery down ⇒ just attempt the pull
            pass

        def _do() -> str:
            """Register the pull and hand it to a background worker thread."""
            with _pull_lock:
                if name in _pulls_in_flight:
                    return (
                        f"Already pulling {name}. "
                        "I'll let you know the moment it lands."
                    )
                _pulls_in_flight.add(name)
            threading.Thread(
                target=_pull_worker, args=(name,), daemon=True
            ).start()
            return (
                f"Pulling {name} now — it runs in the background. "
                "I'll let you know when it's on the shelf."
            )

        # Hardware-aware confirm (Tony, 2026-07-07): estimate the download
        # BEFORE asking, and fold the size + RAM verdict into the approval
        # description — "pull llama3.3" must come back as "that's ≈42.5GB and
        # too big for your 16GB RAM — sure?" rather than a blind confirm.
        describe = f"Downloading {name}"
        try:
            from core import llm

            size = llm.estimate_pull_size(name)
            if size:
                describe += f" (≈{size / 1e9:.1f}GB)"
                ram = llm.total_ram_bytes()
                if ram and size >= ram / 2:
                    describe += (
                        f" — too big to run well in this machine's "
                        f"{ram / 1e9:.0f}GB RAM"
                    )
            else:
                describe += " (size unknown)"
        except Exception:  # noqa: BLE001 — sizing is best-effort
            describe += " (size unknown)"

        return self._guarded("model_pull", name, _do, describe=describe)

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
        (toolbox.apps_health, "apps_health"),
        (toolbox.list_projects, "list_projects"),
        (toolbox.start_app, "start_app"),
        (toolbox.stop_app, "stop_app"),
        (toolbox.remember, "remember"),
        (toolbox.switch_model, "switch_model"),
        (toolbox.pull_model, "pull_model"),
        (toolbox.get_time, "get_time"),
        (toolbox.run_command, "run_command"),
        (toolbox.read_file, "read_file"),
        (toolbox.list_dir, "list_dir"),
        (toolbox.search_files, "search_files"),
        (toolbox.write_file, "write_file"),
        (toolbox.append_file, "append_file"),
        (toolbox.move_file, "move_file"),
        (toolbox.delete_file, "delete_file"),
        (toolbox.read_messages, "read_messages"),
        (toolbox.search_messages, "search_messages"),
        (toolbox.list_recent_chats, "list_recent_chats"),
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
    system_suffix: str | None = None,
    voice_aware: bool = False,
):
    """Build a compiled LangGraph ReAct OSA agent over the toolbox.

    ``model_id`` is a concrete model id (or alias-resolved id) — callers usually
    pass the result of ``pick_model`` through ``core.llm.resolve``. Pass a
    ``checkpointer`` (a ``PyMySQLSaver`` from ``core.memory.get_checkpointer``)
    to make threads durable; omit it for a stateless agent (unit tests).
    ``system_suffix`` is a dynamic tail appended to the composed system prompt
    — the chat route injects the per-turn brain-status line through it
    (``brain_prompt_line``) so OSA knows its brain without a tool call.
    ``voice_aware=True`` (2026-07-09) inserts ``VOICE_AWARENESS_LINE`` so OSA
    knows it has ears + a voice when the Constitution's voice block is live —
    it sits BEFORE ``system_suffix`` so the brain line stays the very tail
    (small local models echo trailing text; the brain line already carries the
    never-repeat marker for that). All heavy imports are local so the toolbox
    stays testable without LangChain.
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
    if voice_aware:
        prompt = f"{prompt}\n\n{VOICE_AWARENESS_LINE}"
    if system_suffix:
        prompt = f"{prompt}\n\n{system_suffix}"
    kwargs: dict[str, Any] = {"prompt": prompt}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
    return create_react_agent(model, tools, **kwargs)
