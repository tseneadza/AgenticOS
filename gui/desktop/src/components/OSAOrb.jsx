/**
 * OSAOrb — Phase 14c JARVIS-style OSA reactor orb.
 *
 * A presentational reactor pinned to the upper-right corner of every non-Agent
 * view. Ported faithfully from the approved mockup
 * (gui/mockups/osa_reactor.html — signed off by Tony 2026-07-07): concentric
 * rotating rings, amber "thinking" sweep, "OSA" core, emanating "speaking"
 * waves, and a green "listening" equalizer (voice state — dormant until 14d).
 *
 * The animations are driven entirely by `data-state` on the root, matching the
 * mockup's four states. Colors follow the frontend conventions: theme tokens
 * for text/neutral surfaces, with the cyan/amber/green *state hues* kept as
 * clearly-named CSS custom properties so they're easy to retune.
 *
 * Props:
 *   state    — "idle" | "thinking" | "speaking" | "listening" (default "idle")
 *   lastLine — OSA's most recent line (empty → "Standing by.")
 *   status   — optional short sub-caption (e.g. "Local · Ollama up")
 *   onOpen   — click handler (used to jump to the Agent view)
 */

import { useEffect, useMemo, useState } from "react";
import { get } from "../api";

// Component-scoped stylesheet. Inline styles can't express @keyframes or
// data-state selectors (conventions rule 3), so we inject a scoped <style>
// block once, with orb-* prefixed classes to avoid collisions.
const styles = `
.osa-orb {
  --osa-idle: #35d0e0;   /* cyan — calm presence */
  --osa-think: #ffb454;  /* amber — working */
  --osa-listen: #49e08b; /* green — voice (14d) */
  position: absolute;
  /* Pinned to the upper-right of the main content area. The offset clears the
     app topbar so the orb floats in the view body, matching the mockup. */
  top: 56px;
  right: 16px;
  z-index: 50;
  width: 118px;
  height: 118px;
  cursor: pointer;
  user-select: none;
  background: none;
  border: none;
  padding: 0;
}
.osa-orb .orb-reactor {
  width: 118px;
  height: 118px;
  display: block;
  position: relative;
  z-index: 2;
  overflow: visible;
}
.osa-orb .orb-glow {
  position: absolute;
  inset: 8px;
  border-radius: 50%;
  z-index: 1;
  background: radial-gradient(circle, var(--osa-idle) 0%, transparent 68%);
  opacity: .22;
  filter: blur(6px);
  transition: opacity .4s, background .4s;
}
.osa-orb .orb-stroke { fill: none; stroke: var(--osa-idle); stroke-width: 2; opacity: .85; }
.osa-orb .orb-dash-a { stroke-dasharray: 6 10; opacity: .7; }
.osa-orb .orb-dash-b { stroke-dasharray: 34 20; opacity: .6; }
.osa-orb .orb-thin { stroke-width: 1.3; opacity: .55; }
.osa-orb .orb-core { fill: rgba(10, 26, 34, .55); stroke: var(--osa-idle); stroke-width: 1.4; }
.osa-orb .orb-label {
  fill: #eaf6f9;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: 2px;
  text-anchor: middle;
  font-family: ui-sans-serif, system-ui, sans-serif;
}
.osa-orb .orb-sweep { opacity: 0; transform-origin: 100px 100px; }
.osa-orb .orb-sweep-arc {
  fill: none;
  stroke: var(--osa-think);
  stroke-width: 3;
  stroke-linecap: round;
  filter: drop-shadow(0 0 4px var(--osa-think));
}
.osa-orb .orb-waves .orb-wave { fill: none; stroke: #4ff0ff; stroke-width: 2; opacity: 0; }
.osa-orb .orb-eq rect { fill: var(--osa-listen); opacity: 0; transform-origin: center; }
.osa-orb .orb-cap {
  position: absolute;
  top: 122px;
  right: 2px;
  width: 150px;
  text-align: right;
  font-size: 11px;
  line-height: 1.35;
  color: var(--text-dim);
  z-index: 2;
}
.osa-orb .orb-cap .orb-status { display: block; margin-top: 3px; color: var(--text-dim); opacity: .8; }

.osa-orb .orb-ring { transform-origin: 100px 100px; }
.osa-orb .orb-ring-out { animation: orbSpin 26s linear infinite; }
.osa-orb .orb-ring-mid { animation: orbSpin 18s linear infinite reverse; }
.osa-orb .orb-ring-in { animation: orbSpin 12s linear infinite; }
@keyframes orbSpin { to { transform: rotate(360deg); } }

.osa-orb[data-state="idle"] .orb-glow { opacity: .16; }

.osa-orb[data-state="thinking"] .orb-ring-out { animation-duration: 7s; }
.osa-orb[data-state="thinking"] .orb-ring-mid { animation-duration: 5s; }
.osa-orb[data-state="thinking"] .orb-ring-in { animation-duration: 3.5s; }
.osa-orb[data-state="thinking"] .orb-glow { opacity: .3; background: radial-gradient(circle, var(--osa-think) 0%, transparent 68%); }
.osa-orb[data-state="thinking"] .orb-sweep { opacity: 1; animation: orbSpin 1.15s linear infinite; }
.osa-orb[data-state="thinking"] .orb-stroke { stroke: #ffcf8f; }

.osa-orb[data-state="speaking"] .orb-glow { animation: orbPulseGlow 1s ease-in-out infinite; }
.osa-orb[data-state="speaking"] .orb-core { animation: orbPulseCore 1s ease-in-out infinite; }
.osa-orb[data-state="speaking"] .orb-label { animation: orbPulseCore 1s ease-in-out infinite; }
.osa-orb[data-state="speaking"] .orb-wave { animation: orbEmanate 1.6s ease-out infinite; }
.osa-orb[data-state="speaking"] .orb-wave.orb-w2 { animation-delay: .8s; }
@keyframes orbPulseGlow { 0%, 100% { opacity: .2; } 50% { opacity: .5; } }
@keyframes orbPulseCore { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.06); } }
.osa-orb .orb-core, .osa-orb .orb-label { transform-origin: 100px 100px; }
@keyframes orbEmanate { 0% { opacity: .55; transform: scale(1); } 100% { opacity: 0; transform: scale(1.9); transform-origin: 100px 100px; } }

.osa-orb[data-state="listening"] .orb-glow { opacity: .28; background: radial-gradient(circle, var(--osa-listen) 0%, transparent 68%); }
.osa-orb[data-state="listening"] .orb-stroke { stroke: var(--osa-listen); }
.osa-orb[data-state="listening"] .orb-core { stroke: var(--osa-listen); }
.osa-orb[data-state="listening"] .orb-ring-out { animation-duration: 40s; }
.osa-orb[data-state="listening"] .orb-ring-mid { animation-duration: 30s; }
.osa-orb[data-state="listening"] .orb-eq rect { opacity: .95; animation: orbBounce 1s ease-in-out infinite; }
.osa-orb[data-state="listening"] .orb-eq rect:nth-child(1) { animation-delay: 0s; }
.osa-orb[data-state="listening"] .orb-eq rect:nth-child(2) { animation-delay: .15s; }
.osa-orb[data-state="listening"] .orb-eq rect:nth-child(3) { animation-delay: .3s; }
.osa-orb[data-state="listening"] .orb-eq rect:nth-child(4) { animation-delay: .15s; }
.osa-orb[data-state="listening"] .orb-eq rect:nth-child(5) { animation-delay: 0s; }
.osa-orb[data-state="listening"] .orb-label { opacity: .25; }
@keyframes orbBounce { 0%, 100% { transform: scaleY(.5); opacity: .6; } 50% { transform: scaleY(2.4); opacity: 1; } }

@media (prefers-reduced-motion: reduce) {
  .osa-orb *, .osa-orb [class*="orb-"] { animation: none !important; }
}
`;

const VALID_STATES = ["idle", "thinking", "speaking", "listening"];

export default function OSAOrb({
  state = "idle",
  lastLine = "",
  status = "",
  onOpen,
}) {
  // Optional cheap live status: fetch /api/osa/state on mount + a light 15s
  // interval to populate the sub-caption when the caller didn't pass one.
  // Degrades silently on error.
  const [fetchedStatus, setFetchedStatus] = useState("");
  useEffect(() => {
    if (status) return; // caller-provided status wins; skip polling
    let alive = true;
    const load = () => {
      get("/api/osa/state")
        .then((s) => {
          if (!alive || !s) return;
          const label = s.active_label || "OSA";
          const ollama = s.ollama_up ? "Ollama up" : "Ollama down";
          setFetchedStatus(`${label} · ${ollama}`);
        })
        .catch(() => { /* degrade silently */ });
    };
    load();
    const t = setInterval(load, 15_000);
    return () => { alive = false; clearInterval(t); };
  }, [status]);

  const dataState = VALID_STATES.includes(state) ? state : "idle";
  const caption = lastLine && lastLine.trim() ? lastLine : "Standing by.";
  const subStatus = status || fetchedStatus;

  const label = useMemo(
    () => `OSA presence — ${dataState}. Open OSA chat.`,
    [dataState]
  );

  return (
    <button
      type="button"
      className="osa-orb"
      data-state={dataState}
      data-testid="osa-orb"
      onClick={onOpen}
      title="Open OSA chat"
      aria-label={label}
    >
      <style>{styles}</style>
      <span className="orb-glow" aria-hidden="true" />
      <svg viewBox="0 0 200 200" className="orb-reactor" role="img" aria-label="OSA reactor">
        <g className="orb-ring orb-ring-out"><circle cx="100" cy="100" r="92" className="orb-stroke orb-dash-a" /></g>
        <g className="orb-ring orb-ring-mid"><circle cx="100" cy="100" r="74" className="orb-stroke orb-dash-b" /></g>
        <g className="orb-ring orb-ring-in"><circle cx="100" cy="100" r="58" className="orb-stroke orb-thin" /></g>
        <g className="orb-sweep"><path d="M100 22 A78 78 0 0 1 178 100" className="orb-sweep-arc" /></g>
        <circle cx="100" cy="100" r="42" className="orb-core" />
        <g className="orb-waves">
          <circle cx="100" cy="100" r="46" className="orb-wave" />
          <circle cx="100" cy="100" r="46" className="orb-wave orb-w2" />
        </g>
        <g className="orb-eq">
          <rect x="72" y="96" width="5" height="8" rx="2" /><rect x="84" y="96" width="5" height="8" rx="2" />
          <rect x="96" y="96" width="5" height="8" rx="2" /><rect x="108" y="96" width="5" height="8" rx="2" />
          <rect x="120" y="96" width="5" height="8" rx="2" />
        </g>
        <text x="100" y="107" className="orb-label">OSA</text>
      </svg>
      <span className="orb-cap">
        {caption}
        {subStatus && <span className="orb-status">{subStatus}</span>}
      </span>
    </button>
  );
}
