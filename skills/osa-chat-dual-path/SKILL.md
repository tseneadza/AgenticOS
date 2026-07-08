---
name: osa-chat-dual-path
description: |
  Understand and correctly modify OSA's TWO chat code paths in AgenticOS. Use this skill whenever you add or change any per-turn behavior on OSA replies — speaking replies aloud, logging, analytics, telemetry, reply scrubbing/post-processing, notifications, tool-trace handling, or anything that should happen "on every OSA answer." The Agent view's PRIMARY chat path is the streaming WebSocket (/api/osa/ws/chat); the synchronous POST (/api/osa/chat) is only a fallback. A change wired into only one path will appear to work in curl but silently do nothing in the app (or vice versa). Also covers the two-turn vs interrupt confirm flows and the double-connection/dedup gotcha.
compatibility: AgenticOS repo, gui/sidecar/routes/api_osa.py + gui/desktop/src/App.jsx
---

# OSA Chat Dual-Path (wire reply behavior into BOTH routes)

## Overview

OSA has **two** server-side chat entry points that both produce a final reply:

1. `POST /api/osa/chat` — synchronous, one request/response. `osa_chat()` in
   `gui/sidecar/routes/api_osa.py`. Two-turn *conversational* confirm for
   destructive actions (can't block on a human).
2. `WS /api/osa/ws/chat` — streaming tokens + live tool events over one socket.
   `osa_chat_ws()` in the same file. REAL mid-run confirms via LangGraph
   `interrupt()` (the graph parks on the MySQL checkpointer).

**The Agent view uses the WebSocket as its PRIMARY path** (`gui/desktop/src/App.jsx`,
`openSocket`), and falls back to `POST` only when the socket can't open
(`ws.onclose` with no frames → `sendViaPost`). So:

> Any behavior you want on every OSA reply MUST be added to BOTH handlers.
> Testing with `curl POST` exercises only the fallback — it can pass while the
> app (WebSocket) does nothing.

## When to use

Adding/altering anything that runs once per finished reply, e.g.:
- Speaking the reply (voice-OUT) — the 2026-07-08 bug: hooked only in POST, so
  the app was silent while curl spoke.
- Logging / analytics / metrics on replies.
- Reply post-processing (echo scrub, escalation clause, redaction).
- Recording "last turn" state, notifications, side effects.

## The shared choke points (use these, don't duplicate logic)

Both routes already funnel the finished reply through shared helpers — extend
those, or call them from both handlers:

- `_scrub_reply(reply, brain_line, *, escalated=...)` — echo scrub + escalation
  clause. Called by BOTH `osa_chat` and `osa_chat_ws` (and `_fold_history`).
- `_maybe_speak_reply(reply)` — voice-OUT. Must be called in BOTH after
  `_scrub_reply`. In `osa_chat`: right before the return dict. In
  `osa_chat_ws`: right after `reply = _scrub_reply(...)`, before the `final`
  frame.
- `_LAST_TURN.update(model=..., escalated=...)` — orb brain display. Both.

Pattern to follow when adding a new per-reply side effect:

```python
# 1. Write ONE helper (module-level in api_osa.py), guarded/best-effort:
def _my_reply_hook(reply: str) -> None:
    try:
        ...   # never raise into the chat path
    except Exception:  # noqa: BLE001
        pass

# 2. Call it in osa_chat() after _scrub_reply, before the return dict.
# 3. Call it in osa_chat_ws() after `reply = _scrub_reply(...)`, before
#    `await ws.send_json({"type": "final", ...})`.
```

Add a regression guard so the WS path can't lose the hook again (source-level
check is enough; a full WS integration test needs a live graph + checkpointer):

```python
def test_ws_handler_has_my_hook():
    import inspect
    from gui.sidecar.routes import api_osa
    assert "_my_reply_hook(reply)" in inspect.getsource(api_osa.osa_chat_ws)
```

## Verifying the WS path without the GUI

Exercise the real socket the app uses:

```python
import asyncio, websockets, json
async def go():
    async with websockets.connect("ws://localhost:5130/api/osa/ws/chat") as ws:
        await ws.send(json.dumps({"message": "hi", "thread_id": "verify-1"}))
        async for raw in ws:
            m = json.loads(raw)
            if m.get("type") == "final":
                print("final reply:", m["reply"]); break
asyncio.run(go())
```

Check the access log to see which path the app actually hit:

```bash
grep -iE "osa/ws/chat|osa/chat" /tmp/agenticos_sidecar.log | tail
# "WebSocket /api/osa/ws/chat [accepted]"  → app used the WS (primary)
# "POST /api/osa/chat"                       → fallback (or your curl)
```

## Double-connection / dedup gotcha

The client can open the chat socket **more than once** for one logical turn
(React dev StrictMode, a reconnect, or a second window). That means a per-reply
side effect can fire **twice near-simultaneously**. If the effect is
user-visible (audio!), make it idempotent within a short window rather than
assuming one-call-per-turn. Example: `VoiceService.speak()` de-dupes identical
text within an 8s window (`_last_spoken` + `_dedupe_window_s`). Barge-in alone
does NOT catch two calls that start at the same instant (both still synthesizing).

## Confirm flows differ by path (don't cross them)

- POST route: two-turn *conversational* confirm (`_PENDING_CONFIRM`, "just say
  yes"). Voice (14d) rides this because it can't block on a human.
- WS route: real `interrupt()` — sends `awaiting_confirm`, the graph parks on
  the checkpointer, resumes on `{"resume":"approve"|"deny"}` (survives socket
  death via `_WS_TURN_STATE`).

When adding confirm-related behavior, respect which mechanism the path uses.

## Key learnings (2026-07-08)

1. "Works in curl, silent in the app" = you touched POST but the app uses the
   WebSocket. Always wire both.
2. Prefer a single shared helper called from both handlers over copy-paste.
3. Add a source-level regression test asserting the WS handler calls your hook.
4. Client can double-open the socket → make user-visible per-reply effects
   idempotent (dedup window), not just barge-in-cancelled.
