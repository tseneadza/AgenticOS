/**
 * OSAOrb — the OSA presence orb (living-orb redesign, 2026-07-09).
 *
 * Presentational orb mounted in the OSA right rail (components/OSARail.jsx),
 * shown on every view. Redesigned from the flat SVG "reactor" to a luminous,
 * breathing sphere from Tony's approved reference (uploads/jarvis-orb.html,
 * signed off 2026-07-09): a white-hot core with layered glow, expanding ripple
 * rings, orbiting satellites, and a voice waveform — all colored by state.
 *
 * State drives everything via `data-state` on the root button; the state hue is
 * one CSS custom property (`--orb`, an "r,g,b" triple) so retuning a color is a
 * one-line change. The wiring is UNCHANGED from the reactor version: the same
 * /api/osa/state (15s) + /api/osa/voice/state (1.5s) polls, the same
 * alert > voice > context precedence, caption, brain-status line, and onState.
 *
 * Props:
 *   state    — "idle" | "thinking" | "speaking" | "listening" | "alert" (default "idle")
 *   lastLine — OSA's most recent line (empty → "Standing by.")
 *   status   — optional short sub-caption (e.g. "Local · Ollama up")
 *   onOpen   — click handler (used to jump to the Agent view)
 *   onState  — optional observer of each /api/osa/state payload (rail piggyback)
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { get } from "../api";

// Component-scoped stylesheet. @keyframes + data-state selectors can't be
// inline styles (conventions rule 3), so we inject a scoped <style> once, with
// orb-* prefixed classes. The state hue is `--orb` (an "r,g,b" triple) so every
// glow/stroke derives from rgba(var(--orb), a); data-state just swaps the triple.
const styles = `
.osa-orb {
  --orb: 56,189,248;   /* idle — cyan */
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  cursor: pointer;
  user-select: none;
  background: none;
  border: none;
  padding: 0;
}
.osa-orb[data-state="listening"] { --orb: 52,211,153; }  /* emerald */
.osa-orb[data-state="thinking"]  { --orb: 251,191,36; }  /* amber */
.osa-orb[data-state="speaking"]  { --orb: 167,139,250; } /* violet */
.osa-orb[data-state="alert"]     { --orb: 248,113,113; } /* red */

/* Stage: a fixed square that centers every layer in one grid cell so the
   core, rings, orbits and monogram all stack concentrically. */
.osa-orb .orb-stage {
  position: relative;
  width: 240px;
  height: 240px;
  display: grid;
  place-items: center;
}
/* CRITICAL: every layer shares grid cell 1/1 so core, rings, orbits and the
   monogram stack CONCENTRICALLY. Without this, grid auto-placement puts each
   child in its own implicit ROW and the orb's pieces scatter down the rail
   (the 2026-07-10 "exploded orb" bug — jsdom tests can't catch layout). */
.osa-orb .orb-stage > * { grid-area: 1 / 1; }

/* Core — the luminous sphere: white hot-spot → state hue → transparent, with
   three layered outer glows + an inner sheen. Breathes at rest. */
.osa-orb .orb-core {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 32%,
    rgba(255,255,255,0.95) 0%,
    rgba(var(--orb),0.95) 22%,
    rgba(var(--orb),0.65) 55%,
    rgba(var(--orb),0.15) 100%);
  box-shadow:
    0 0 34px rgba(var(--orb),0.85),
    0 0 66px rgba(var(--orb),0.45),
    0 0 120px rgba(var(--orb),0.25),
    inset 0 0 32px rgba(255,255,255,0.25);
  animation: orbBreathe 3.2s ease-in-out infinite;
  transition: box-shadow 0.6s ease;
  z-index: 3;
}
.osa-orb[data-state="thinking"] .orb-core { animation-duration: 0.9s; }
.osa-orb[data-state="alert"]    .orb-core { animation-duration: 0.55s; }
.osa-orb[data-state="speaking"] .orb-core { animation: orbTalk 0.45s ease-in-out infinite; }
@keyframes orbBreathe { 0%,100% { transform: scale(1); } 50% { transform: scale(1.07); } }
@keyframes orbTalk { 0%,100% { transform: scale(1); } 30% { transform: scale(1.13); } 65% { transform: scale(0.97); } }

/* Faint "OSA" monogram floating in the core's glow. */
.osa-orb .orb-mark {
  z-index: 4;
  font: 700 14px/1 ui-sans-serif, system-ui, sans-serif;
  letter-spacing: 4px;
  text-indent: 4px;
  color: rgba(255,255,255,0.9);
  mix-blend-mode: screen;
  pointer-events: none;
}

/* Expanding ripple rings. */
.osa-orb .orb-ring {
  width: 140px;
  height: 140px;
  border-radius: 50%;
  border: 1.5px solid rgba(var(--orb),0.5);
  animation: orbRipple 3.4s linear infinite;
  z-index: 1;
}
.osa-orb .orb-ring:nth-of-type(2) { animation-delay: 1.13s; }
.osa-orb .orb-ring:nth-of-type(3) { animation-delay: 2.26s; }
.osa-orb[data-state="thinking"]  .orb-ring { animation-duration: 1.3s; }
.osa-orb[data-state="listening"] .orb-ring { animation-duration: 2.1s; }
@keyframes orbRipple { from { transform: scale(1); opacity: 0.85; } to { transform: scale(1.75); opacity: 0; } }

/* Orbiting satellites — a dashed ring + a dotted counter-rotating ring, each
   carrying a glowing dot. */
.osa-orb .orb-orbit {
  width: 185px;
  height: 185px;
  border-radius: 50%;
  border: 1px dashed rgba(var(--orb),0.28);
  animation: orbSpin 12s linear infinite;
  z-index: 2;
}
.osa-orb .orb-orbit::before {
  content: '';
  position: absolute;
  top: -4px;
  left: 50%;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgb(var(--orb));
  box-shadow: 0 0 14px rgba(var(--orb),0.95);
}
.osa-orb .orb-orbit.rev {
  width: 224px;
  height: 224px;
  border-style: dotted;
  animation: orbSpin 19s linear infinite reverse;
}
.osa-orb[data-state="thinking"] .orb-orbit     { animation-duration: 3s; }
.osa-orb[data-state="thinking"] .orb-orbit.rev { animation-duration: 4.5s; }
@keyframes orbSpin { to { transform: rotate(360deg); } }

/* Voice waveform — only while listening or speaking. */
.osa-orb .orb-wave {
  position: absolute;
  bottom: 14px;
  left: 50%;
  transform: translateX(-50%);
  display: none;
  gap: 4px;
  z-index: 4;
}
.osa-orb[data-state="listening"] .orb-wave,
.osa-orb[data-state="speaking"]  .orb-wave { display: flex; }
.osa-orb .orb-wave i {
  width: 4px;
  height: 14px;
  border-radius: 2px;
  background: rgba(var(--orb),0.9);
  animation: orbBar 0.8s ease-in-out infinite;
}
.osa-orb .orb-wave i:nth-child(2) { animation-delay: .1s; }
.osa-orb .orb-wave i:nth-child(3) { animation-delay: .2s; }
.osa-orb .orb-wave i:nth-child(4) { animation-delay: .3s; }
.osa-orb .orb-wave i:nth-child(5) { animation-delay: .4s; }
@keyframes orbBar { 0%,100% { transform: scaleY(.4); } 50% { transform: scaleY(1.7); } }

/* State word — a small uppercase readout in the current state hue. */
.osa-orb .orb-word {
  display: block;
  margin-top: 14px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 4px;
  text-transform: uppercase;
  color: rgb(var(--orb));
  transition: color .4s;
}
/* Armed affordance (2026-07-09, OSAORB_IDEAS #3) — wake listening is ON but
   OSA is merely waiting. Deliberately STATIC (no animation) so it can never
   be confused with the animated listening state: the state stays honest
   (idle), this chip just says "it can hear you". Emerald = the voice hue. */
.osa-orb .orb-armed {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 5px;
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 2.5px;
  text-transform: uppercase;
  color: rgba(52,211,153,0.85);
}
.osa-orb .orb-armed::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgb(52,211,153);
  box-shadow: 0 0 6px rgba(52,211,153,0.7);
}
/* A faint steady outer ring on the stage while armed — static, sub-ripple. */
.osa-orb[data-wake="on"] .orb-stage::after {
  content: '';
  position: absolute;
  inset: 4px;
  border-radius: 50%;
  border: 1px solid rgba(52,211,153,0.22);
  pointer-events: none;
}
.osa-orb .orb-cap {
  display: block;
  margin-top: 6px;
  width: 100%;
  max-width: 248px;
  text-align: center;
  font-size: 11px;
  line-height: 1.35;
  color: var(--text-dim);
}
.osa-orb .orb-cap .orb-status { display: block; margin-top: 3px; color: var(--text-dim); opacity: .8; }

@media (prefers-reduced-motion: reduce) {
  .osa-orb .orb-core,
  .osa-orb .orb-ring,
  .osa-orb .orb-orbit,
  .osa-orb .orb-wave i { animation: none !important; }
}
`;

const VALID_STATES = ["idle", "thinking", "speaking", "listening", "alert"];

export default function OSAOrb({
  state = "idle",
  lastLine = "",
  status = "",
  onOpen,
  // onState (2026-07-07): optional callback invoked with each successful
  // /api/osa/state payload from the orb's 15s poll. Lets the rail piggyback
  // this poll to detect pin changes made OUTSIDE its Brain picker (chat's
  // switch_model, the REST route, another window) without a second poller.
  // Not called when the caller supplies `status` (the poll is skipped).
  onState,
}) {
  // Optional cheap live status: fetch /api/osa/state on mount + a light 15s
  // interval to populate the sub-caption when the caller didn't pass one.
  // Degrades silently on error.
  const [fetchedStatus, setFetchedStatus] = useState("");
  const onStateRef = useRef(onState);
  onStateRef.current = onState;
  useEffect(() => {
    if (status) return; // caller-provided status wins; skip polling
    let alive = true;
    const load = () => {
      get("/api/osa/state")
        .then((s) => {
          if (!alive || !s) return;
          try { onStateRef.current?.(s); } catch { /* observer must not break the orb */ }
          // Brain display (2026-07-07): show OSA's brain truthfully — the pin
          // when pinned (with the actual runtime when the guardrail escalated
          // the last turn), the auto route otherwise.
          const brain = s.pinned_model
            ? `Pinned: ${s.pinned_label || s.pinned_model}`
            : `Auto · ${s.active_label || "OSA"}`;
          const ran = s.last_turn_escalated && s.last_turn_label
            ? ` (ran ${s.last_turn_label})`
            : "";
          const ollama = s.ollama_up ? "Ollama up" : "Ollama down";
          setFetchedStatus(`${brain}${ran} · ${ollama}`);
        })
        .catch(() => { /* degrade silently */ });
    };
    load();
    const t = setInterval(load, 15_000);
    return () => { alive = false; clearInterval(t); };
  }, [status]);

  // Live voice states (2026-07-08): the wake loop / PTT run SERVER-side, so
  // the caller's context state can't know about them. A light localhost poll
  // of /api/osa/voice/state maps the pipeline's action states onto the orb
  // (listening -> listening, transcribing -> thinking, speaking -> speaking).
  // Stops polling entirely when voice is disabled or deps are missing.
  // Armed affordance (2026-07-09, OSAORB_IDEAS #3): the same payload carries
  // wake_active — captured here so an armed-but-idle orb shows a static
  // "armed" chip WITHOUT lying about its state (armed reads idle; see
  // skills/osa-orb-state).
  const [voiceState, setVoiceState] = useState(null);
  const [wakeActive, setWakeActive] = useState(false);
  useEffect(() => {
    let alive = true;
    let timer = null;
    const poll = () => {
      get("/api/osa/voice/state")
        .then((v) => {
          if (!alive) return;
          if (!v?.enabled || !v?.deps_ok) {
            setVoiceState(null);
            setWakeActive(false);
            return; // voice off — no further polling this mount
          }
          const map = {
            listening: "listening",
            transcribing: "thinking",
            speaking: "speaking",
          };
          setVoiceState(map[v.state] || null);
          setWakeActive(Boolean(v.wake_active));
          timer = setTimeout(poll, 1500);
        })
        .catch(() => {
          if (alive) timer = setTimeout(poll, 8000); // sidecar down — back off
        });
    };
    poll();
    return () => { alive = false; clearTimeout(timer); };
  }, []);

  const requested = VALID_STATES.includes(state) ? state : "idle";
  // Precedence: alert (needs the human) > live voice state > context state.
  const dataState = requested === "alert" ? "alert" : (voiceState || requested);
  const caption = lastLine && lastLine.trim() ? lastLine : "Standing by.";
  const subStatus = status || fetchedStatus;

  const label = useMemo(
    () => `OSA presence — ${dataState}${wakeActive ? ", wake armed" : ""}. Open OSA chat.`,
    [dataState, wakeActive]
  );

  return (
    <button
      type="button"
      className="osa-orb"
      data-state={dataState}
      data-wake={wakeActive ? "on" : undefined}
      data-testid="osa-orb"
      onClick={onOpen}
      title="Open OSA chat"
      aria-label={label}
    >
      <style>{styles}</style>
      <span className="orb-stage" role="img" aria-label="OSA reactor">
        <span className="orb-ring" aria-hidden="true" />
        <span className="orb-ring" aria-hidden="true" />
        <span className="orb-ring" aria-hidden="true" />
        <span className="orb-orbit" aria-hidden="true" />
        <span className="orb-orbit rev" aria-hidden="true" />
        <span className="orb-core" aria-hidden="true" />
        <span className="orb-mark">OSA</span>
        <span className="orb-wave" aria-hidden="true">
          <i /><i /><i /><i /><i />
        </span>
      </span>
      <span className="orb-cap">
        <span className="orb-word" data-testid="osa-orb-word">{dataState}</span>
        {wakeActive && (
          <span className="orb-armed" data-testid="osa-orb-armed">armed</span>
        )}
        {caption}
        {subStatus && <span className="orb-status">{subStatus}</span>}
      </span>
    </button>
  );
}
