# OSAOrb — enhancement ideas

> **Purpose.** A parking lot of ideas for evolving the OSA reactor orb
> (`gui/desktop/src/components/OSAOrb.jsx`), captured 2026-07-09. Not a
> commitment — a menu to pull from next session. Each idea carries a rough
> **effort** (ponytail-sized) and **why it matters**, so a budget-limited
> session can grab the cheapest high-value one and stop.

> **UPDATE 2026-07-09:** the base **living-orb redesign shipped** (breathing
> luminous core + ripple rings + orbiting satellites, from Tony's reference).
> The ideas below now build ON that orb, not the retired flat reactor.

## Where the orb stands today (baseline)

- Presentational reactor in the OSA right rail. Root `data-state` drives every
  animation: `idle | listening | thinking | speaking | alert`.
- State comes from two places: `App.jsx` `osaEffectiveState` (manual override >
  alert/approvals > chat thinking/speaking > active runs > idle) AND a 1.5s
  poll of `/api/osa/voice/state` mapped onto listening/thinking/speaking.
  Precedence in the orb: **alert > live voice state > context state**.
- Idle now means *genuinely waiting* (2026-07-09 fix): armed-but-waiting reads
  idle; listening only during real speech capture.
- Caption line + optional sub-status; click jumps to the Agent view.

## Ideas (roughly prioritized)

1. **Announcements flash the orb `alert`.** *(effort: S · why: full state
   visibility — Tony's ask.)* Proactive `osa_proactive` ANNOUNCED messages
   land in the rail feed but don't flash the orb today; only pending approvals
   raise `alert`. Wire announced events → a decaying `alert` (auto-clears, or
   clears on view/ack). Root-cause spot: the `osaEffectiveState` precedence in
   `App.jsx` + the events bridge.

2. **Push state instead of polling.** *(effort: M · why: "promptly" = speed.)*
   The 1.5s voice-state poll caps how fast the orb reacts (up to 1.5s lag).
   Push voice-state transitions over the existing AGUI WS (or a small SSE) so
   listening/speaking show instantly. Keep the poll as a fallback. ponytail:
   only if the lag is actually felt — a shorter poll interval is the one-line
   version to try first.

3. **Distinct "armed" affordance.** *(effort: S · why: know it can hear you.)*
   With wake ON but idle, the orb looks identical to wake OFF. A subtle static
   ring/dot when `wake_active` (already in `/api/osa/voice/state`) tells Tony
   "listening is armed" without the full listening animation. Complements the
   idle-vs-listening fix.

4. **Orb as a light control surface.** *(effort: M · why: parked debate.)*
   Click/hover reveals mute, wake toggle, and brain picker — WITHOUT fusing
   rendering with orchestration (keep the orb a presence/face; controls are a
   thin popover calling existing routes). Prior take (Claude): don't make the
   orb the sidecar; add surfaces, not responsibilities. Debate still open.

5. **Greeting moment on the orb.** *(effort: S · why: ties to the new presence
   greeting.)* When the welcome-back greeting fires, give the orb a brief warm
   "hello" beat (a one-off pulse in the idle hue) so the greeting is felt
   visually, not just heard. Hook: the `speak(text)` call already runs on
   return.

6. **Respect `prefers-reduced-motion`.** *(effort: S · why: accessibility +
   it's the right default.)* The orb pulses/rotates constantly. Gate the
   animations behind the media query so reduced-motion users get a calm,
   static-but-colored orb. Small CSS-only change in the scoped `<style>`.

7. **Thinking isn't a black box.** *(effort: M · why: long tool runs feel
   stuck.)* During a long `thinking` (active LangGraph run), surface a hint —
   elapsed time or the current tool/step — in the caption so a 30s tool call
   doesn't look frozen. Data already flows on the AGUI stream.

8. **Time-of-day tint.** *(effort: S · cosmetic.)* Nudge the idle hue subtly by
   time bucket (morning/evening/late-night), matching the greeting's buckets.
   Pure polish; do last.

## Guardrails (don't repeat past mistakes)

- **New paradigm = new nav link**, not another always-on dashboard panel
  (design principle #7). The orb is presence, not a growing control panel.
- State must reflect *reality* — see `skills/osa-orb-state`. Never show a state
  the pipeline isn't actually in (that's the idle-vs-listening lesson).
- Any reply-side behavior must be wired into BOTH chat paths — see
  `skills/osa-chat-dual-path`.
