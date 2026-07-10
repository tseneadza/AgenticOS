---
name: osa-orb-state
description: |
  Understand and correctly change what the OSA reactor orb DISPLAYS. Use this skill whenever you touch orb state — adding a new state, changing when the orb shows listening/thinking/speaking/alert/idle, wiring a new signal (voice, approvals, proactive events, workflow runs) to the orb, or debugging "the orb shows the wrong thing." The orb must reflect OSA's REAL state; the classic bug (fixed 2026-07-09) was showing "listening" while merely armed and waiting. Covers the two state sources, their precedence, the idle-vs-listening rule, the poll intervals, and how to test orb state headlessly.
compatibility: AgenticOS repo, gui/desktop/src/components/OSAOrb.jsx + gui/desktop/src/App.jsx + osa_voice/pipeline.py
---

# OSA Orb State (make the orb tell the truth)

## The rule

**The orb's `data-state` must reflect the state OSA is ACTUALLY in — never a
state it merely *could* be in.** Showing "listening" because the mic is armed,
"thinking" because a run *might* start, or "alert" that never clears are all
the same bug: the face lies about the system.

## Two state sources (know which you're touching)

1. **Context state — `App.jsx` `osaEffectiveState`.** Precedence, highest
   first: manual override (`window.__osaSetState`) > `alert` (pending
   approvals) > chat `thinking`/`speaking` > active LangGraph runs
   (`thinking`) > `idle`. This is the app's view of OSA.
2. **Live voice state — `OSAOrb.jsx` poll of `/api/osa/voice/state` (1.5s).**
   Maps the pipeline's machine onto the orb: `listening→listening`,
   `transcribing→thinking`, `speaking→speaking`. Only active when voice is
   enabled + deps present.

**Orb precedence (in `OSAOrb.jsx`):** `alert` > live voice state > context
state. So a pending approval always wins; otherwise a live voice transition
wins over the context state.

## The idle-vs-listening rule (the bug we already hit)

The voice pipeline (`osa_voice/pipeline.py`) state machine is
`disabled | idle | listening | transcribing | speaking | error`.

- **`idle` = armed and waiting.** The wake loop sits in `_capture_utterance`
  waiting for someone to speak — that window MUST read the resting state
  (idle), not `listening`.
- **`listening` = actively capturing directed speech.** Set only once VAD (+
  the `min_rms` energy gate) detects `in_speech`.

The original bug: `_capture_utterance` set `listening` for the WHOLE
start-timeout window, so with wake ON the orb read "listening" nonstop. Fix
(2026-07-09): stay at `_resting_state()` while armed; flip to `listening` on
`in_speech`. **If you edit capture, preserve this** — grep for `in_speech` and
`_resting_state()` before changing state assignments.

## When you add a new signal to the orb

- Decide which source owns it: an app-level fact (approvals, runs) → extend
  `osaEffectiveState`; a pipeline fact (voice) → it flows through
  `/api/osa/voice/state`.
- Respect precedence — don't let a low-signal state mask `alert`.
- Every `alert`/attention state needs a **clear path** (ack, decay, or the
  condition resolving). An alert with no exit is a stuck orb.

## Testing (headless — no browser, no mic)

- **Orb rendering:** vitest against `OSAOrb.jsx` with a `state` prop +
  `/api/osa/voice/state` mocked (see `src/__tests__/OSAOrb.test.jsx`); assert
  `data-state` / the caption word.
- **Pipeline state:** pytest with fake `sounddevice` + `webrtcvad` injected via
  `sys.modules`, controlling the per-frame VAD verdict (see
  `gui/sidecar/tests/test_osa_idle_state.py`). Assert the state after a silent
  capture (idle) vs a speech capture (listening). No real audio, ever.

## Gotchas

- **Two sources, one truth:** if the orb shows the wrong thing, check BOTH
  `osaEffectiveState` and the voice poll — the winner is per the precedence
  above, not "last writer".
- **Poll lag:** voice state can be up to ~1.5s stale (the poll interval). If
  "promptly" is the complaint, that's the knob (or push-based) — not a state
  bug. See `docs/OSAORB_IDEAS.md` #2.
- **`prefers-reduced-motion`:** the orb animates constantly; a reduced-motion
  path is on the ideas list, don't assume it exists yet.
