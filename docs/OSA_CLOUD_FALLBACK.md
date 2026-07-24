# OSA Cloud-Brain Fallback (billing-error resilience)

**Status:** shipped 2026-07-24 · **Decisions locked with Tony (interview, 2026-07-24)**

## Why

A dead Anthropic key (out of credits, revoked key) used to kill every
cloud-routed turn: the 2026-07-22 graceful-error layer made the failure
*speak in persona*, but nothing changed behavior — the next turn burned the
same dead key, and Tony had to manually pin local. This layer makes OSA
degrade instead of dying.

## Locked decisions

| Q | Decision |
|---|---|
| On a durable failure (billing/auth) | **Both**: same-turn local rescue AND a sticky degraded flag |
| Cloud-worthy turns while degraded | **Fail in persona** (keys guardrail: web/heavy has no safe local home) |
| Recovery | **Lazy TTL re-probe** (15 min) + manual phrase + observed success |

## Mechanics

State lives in `agents/osa_agent.py` — in-memory on purpose (a sidecar
restart resets it; one failed attempt re-arms, so nothing can go stale):
`mark_cloud_dead(kind)` / `clear_cloud_dead()` / `note_cloud_ok()` /
`cloud_dead_status() → {kind, since, fresh}` / `is_cloud_retry_request(msg)`.
`DURABLE_ERROR_KINDS = {billing, auth}` — rate-limit/overloaded/local_down
NEVER arm the flag (they keep the plain 2026-07-22 persona messages).

Per turn (both the sync POST and the WS route in
`gui/sidecar/routes/api_osa.py`):

1. **Manual clear** — while armed, "try your cloud brain again" (regex, only
   consulted while armed) clears the flag, so that very turn becomes the probe.
2. **Fresh flag + cloud-worthy turn** → fast-fail in persona
   (`_CLOUD_STILL_DEAD_MSG`), **zero API calls**.
3. **Fresh flag + local-capable turn** (`route_turn == "local"`, Ollama up,
   a real local model resolves) → **pre-emptive downgrade**: the turn runs on
   the local brain from the start — even under a cloud pin, which yields to
   survival here since the pin can't run anyway.
4. **Durable error classified on a turn that did run cloud** →
   `mark_cloud_dead`; if the turn was local-capable, `_retry_turn_local`
   re-runs it on the local brain (same thread, same approval_fn). The FIRST
   arming prefixes the one-time `_CLOUD_DEAD_ANNOUNCE`; re-arms stay quiet.
5. **Recovery** — past the TTL, `fresh` flips False and the next cloud-worthy
   turn simply attempts cloud (that attempt IS the probe — a billing 400
   costs $0); failure re-arms quietly, success (or any successful cloud turn)
   calls `note_cloud_ok()` and clears.

`GET /api/osa/state` now returns `cloud_degraded: {kind, since, fresh}` —
`kind` stays set past the TTL so a future HUD chip stays honest while
`fresh` governs routing.

## Known tradeoffs

- **Duplicate user message on rescue:** the failed cloud invoke may have
  already checkpointed the user turn; the rescue appends it again. Cosmetic
  (no dangling tool calls — `_heal_pending_interrupt` runs first).
- **WS resumes are not fast-failed:** a resume is mid-interrupt and always a
  cloud tool turn; if cloud is dead it fails into the classifier like before.
- **GUI chip not built yet** — the state field exists; wiring a rail/HUD chip
  off the existing 15s poll is a follow-up.

## Tests

`gui/sidecar/tests/test_osa_cloud_fallback.py` (hermetic): flag mechanics +
TTL + phrase detector, sync fast-fail (asserts **no agent is built**), lazy
probe clears on success, manual phrase, first-rescue announcement, quiet
pre-emptive downgrade when already armed, rescue-unavailable fallback,
transient-never-arms, `/api/osa/state` exposure, WS source-level wiring
guard. The 2026-07-22 graceful-errors suite gained an autouse flag-disarm
fixture (its billing test now arms real state).
