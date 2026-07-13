---
name: osa-gated-confirm
description: |
  How OSA's two-turn conversational confirm for destructive System-MCP actions actually works — and the MODEL-BEHAVIOR pitfalls that silently break it. Consult whenever a gated capability (fs.write_file/append/move/delete, the future messages.send) "won't confirm", when a user's "yes" loops or gets denied, when OSA asks permission before acting, when a confirm turn hangs/thrashes, or when adding or gating any destructive OSA tool. Covers the sync POST two-turn confirm vs the WebSocket interrupt()+Allow/Deny path, the call-tool-first rule, the escalate-the-yes-to-cloud rule, and the never-bypass-the-guard rule. These are the fixes from the first live OSA->MCP delete demo (2026-07-12).
compatibility: AgenticOS repo, gui/sidecar/routes/api_osa.py + agents/osa_agent.py (OSA_SYSTEM) + tools/system/*
---

# OSA gated-confirm (the two-turn flow + its failure modes)

## The mechanism (sync `POST /api/osa/chat`)

Destructive System-MCP capabilities are guarded. The sync chat route can't block
on a human, so it confirms across TWO turns:

- **Turn 1 (request):** the model CALLS the guarded tool → the capability raises
  `ApprovalRequired` → the route's `approval_fn` DENIES and RECORDS a
  pending-confirm keyed by `thread_id` → OSA relays "needs your OK".
- **Turn 2 (an affirmative WITH a live pending):** `approval_fn` APPROVES for
  that turn and clears the pending → the checkpointed history replays the
  request so the model re-issues the tool and it proceeds.

The **WebSocket** path (`/api/osa/ws/chat`, the app's PRIMARY path) is different
and sturdier: a real LangGraph `interrupt()` parks the run and the app shows
Allow/Deny **buttons** — no dependence on model phrasing. The sync path is the
fallback used by curl and voice, and it's where the pitfalls below bite.

## Pitfall 1 — the confirm never ARMS (model asks BEFORE calling)

**Symptom:** turn 1 returns `tool_trace: []` plus a "shall I?" question; turn 2
"yes" loops or is denied; nothing ever executes.
**Cause:** the pending is recorded ONLY inside `approval_fn`, which only fires
when the model actually CALLS the tool. A polite model (Claude) that asks in
prose first never arms the pending, so "yes" has nothing to approve.
**Fix (prompt, `OSA_SYSTEM` in `agents/osa_agent.py`):** "ALWAYS CALL THE TOOL
FIRST — the guard's DENIED is the confirm signal; never ask without calling."
**Verify:** turn 1 `tool_trace` must contain the tool and `awaiting_confirm` must
be `true`.

## Pitfall 2 — the "yes" turn routes to a weak LOCAL model

**Symptom:** turn 1 arms correctly, but turn 2 "yes" hangs/thrashes (e.g.
`get_time` called ×15, no action, curl times out).
**Cause:** a bare "yes" looks like chit-chat to `pick_model`, so the
tool-RE-issuing turn lands on a local 7B model, which is unreliable at re-calling
tools.
**Fix (route, `gui/sidecar/routes/api_osa.py`):** when
`get_pending(thread_id) is not None AND is_affirmative(message)`, escalate
`chosen` to the cloud brain (`"default"`) unless a cloud model is pinned.
**Verify:** turn 2 `model` is a `claude-*` id and `tool_trace` re-issues the tool.

## Pitfall 3 — the human's approval WORDING isn't recognized

**Symptom:** the confirm is armed, the human clearly approves ("I approve"),
but OSA re-denies and asks again — only the literal word "yes" unlocks it.
**Cause:** `is_affirmative` (`api_osa.py`) is an allowlist of phrasings; a
natural approval outside it reads as a non-affirmative turn, which re-arms
the pending instead of approving. (Live-hit 2026-07-12: "I approve" bounced.)
**Fix:** widen `_AFFIRMATIVES` / `_AFFIRM_FIRST_WORDS` / the prefix list —
with WORD-BOUNDARY-safe prefixes (`p + " "`), or "i approved it last week"
becomes a false approve. Add every new phrasing to the
test_phase14b_osa.py parametrize lists in the same change.

## Pitfall 4 — OSA tries to route AROUND its own guard

A denied destructive action must NEVER be re-attempted by another route (e.g.
`run_command` / `rm`). OSA once suggested `rm` to work around a denied delete.
The prompt now forbids it: "NEVER accomplish a denied or blocked action by
another route — working around your own safety guard is forbidden." If you see
OSA proposing a workaround for a BLOCKED/DENIED op, that's a regression here.

## How to test (LIVE — unit tests can't see model behavior)

These are MODEL-BEHAVIOR bugs: the route mechanism unit-tests stay green while
the live flow fails. Always drive a real turn against a running sidecar:

```
# turn 1 — expect tool_trace:[<tool>], awaiting_confirm:true, file still present
curl -s localhost:5130/api/osa/chat -H 'Content-Type: application/json' \
  -d '{"message":"delete <scratch file>","thread_id":"t"}'
# turn 2 — expect model:claude-*, tool re-issued, file GONE
curl -s localhost:5130/api/osa/chat -H 'Content-Type: application/json' \
  -d '{"message":"yes","thread_id":"t"}'
```

**Prereqs:**
- **MySQL up** — OSA chat needs the MySQL checkpointer; a down DB fails the turn
  with `2003 (HY000) Can't connect`. Start: `sudo /usr/local/mysql/support-files/mysql.server start`.
- **Sidecar restarted** to load any prompt/route/config change (it doesn't
  hot-reload — see `osa-sidecar-lifecycle`).
- Use a scratch file under `data/osa_scratch/` (writes there auto-run; safe to delete).

## Related
- `osa-chat-dual-path` — any per-reply behavior must be wired into BOTH routes.
- `osa-system-mcp` — the capability/guard layer these tools live in.
- `osa-sidecar-lifecycle` — restart the right way so changes take effect.
