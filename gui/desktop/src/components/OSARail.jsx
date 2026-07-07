/**
 * OSARail — dedicated OSA right rail (14e follow-on, 2026-07-07).
 *
 * A fixed-width (220px) column on the right edge of the shell, shown on EVERY
 * view — including Agent (which previously hid the floating orb). Replaces the
 * old absolutely-positioned OSAOrb overlay. Contents, top to bottom:
 *
 *   1. Presence block — the 14c reactor orb (OSAOrb, now static-flow) with its
 *      caption (lastLine) + status sub-caption.
 *   2. Proactive feed — recent messages from GET /api/osa/events (downs,
 *      recoveries, briefings) with relative timestamps, newest first.
 *      Announced messages get a state-hue accent bar; silent ones stay muted.
 *
 * The rail does NOT poll anything itself (the orb's cheap /api/osa/state
 * status poll aside): the event feed arrives via the `events` prop, fed by the
 * single OSAEventsBridge poll in App.jsx (shared with the speak/caption
 * logic — one poll, two consumers).
 *
 * Structure is deliberately sectioned (`rail-section` blocks) so future blocks
 * (e.g. vitals) are drop-ins: add a new <section className="rail-section">
 * between the presence block and the feed. The rail itself is fixed; only the
 * feed list scrolls.
 *
 * Props:
 *   state    — orb state: "idle" | "thinking" | "speaking" | "listening"
 *   lastLine — OSA's most recent line (caption inside the orb block)
 *   events   — proactive messages [{ id, ts, app_id, kind, text, announced }]
 *   onOpen   — click handler for the orb (jump to the Agent view)
 *   onBrief  — async handler for the "Brief me" button (POSTs
 *              /api/osa/briefing upstream); button hidden if omitted
 */

import { useEffect, useState } from "react";
import OSAOrb from "./OSAOrb";

// Keep the feed bounded — the sidecar ring buffer holds ~50; we show the
// freshest RAIL_FEED_MAX regardless of how many the caller accumulated.
export const RAIL_FEED_MAX = 20;

// Relative timestamp in OSA's terse register ("just now", "2m ago", …).
// Exported for tests. `ts` is the sidecar's ISO-8601 UTC string.
export function fmtRel(ts, now = Date.now()) {
  const t = Date.parse(ts);
  if (Number.isNaN(t)) return "";
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

// Component-scoped stylesheet (conventions rule 3 — hover/media/keyframes need
// real CSS; classes are rail-* prefixed to avoid collisions). Theme tokens
// only, plus the same clearly-named OSA state-hue custom props the orb and HUD
// define (--osa-idle/think/listen) for the announced accent bars.
const styles = `
.osa-rail {
  --osa-idle: #35d0e0;   /* cyan — calm presence / briefings */
  --osa-think: #ffb454;  /* amber — working / downs */
  --osa-listen: #49e08b; /* green — voice / recoveries */
  flex: 0 0 220px;
  width: 220px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-left: 2px solid var(--border);
  background: var(--bg-inset);
  overflow: hidden;
}
.osa-rail .rail-section {
  padding: 14px 12px 12px;
  border-bottom: 1px solid var(--border-soft);
}
.osa-rail .rail-presence {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.osa-rail .rail-head {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 1.2px;
  text-transform: uppercase;
  color: var(--text-dim);
  margin-bottom: 8px;
}
/* Brief-me-now: quiet, terse — a request, not a command center. */
.osa-rail .rail-brief {
  margin-top: 10px;
  padding: 3px 12px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--text-dim);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 999px;
  cursor: pointer;
}
.osa-rail .rail-brief:hover:not(:disabled) {
  color: var(--text);
  border-color: var(--osa-idle);
}
.osa-rail .rail-brief:disabled {
  opacity: .5;
  cursor: default;
}
/* Feed section: the rail is fixed; only this list scrolls. */
.osa-rail .rail-feed-section {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-bottom: none;
}
.osa-rail .rail-feed {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.osa-rail .rail-item {
  border-left: 2px solid transparent;
  padding: 4px 6px 4px 8px;
  font-size: 11px;
  line-height: 1.4;
  color: var(--text-dim);
  border-radius: 0 4px 4px 0;
}
/* Announced messages are visually distinct: a state-hue accent bar + brighter
   text. Hue tracks the message kind — downs amber (think), recoveries green
   (listen), briefings/other cyan (idle). */
.osa-rail .rail-item.announced {
  color: var(--text);
  background: var(--bg-panel);
  border-left-color: var(--osa-idle);
}
.osa-rail .rail-item.announced[data-kind="down"] { border-left-color: var(--osa-think); }
.osa-rail .rail-item.announced[data-kind="up"] { border-left-color: var(--osa-listen); }
.osa-rail .rail-item .rail-ts {
  display: block;
  margin-top: 2px;
  font-size: 10px;
  font-family: var(--mono);
  color: var(--text-dim);
  opacity: .8;
}
.osa-rail .rail-empty {
  font-size: 11px;
  color: var(--text-dim);
  font-style: italic;
  padding: 4px 6px;
}
/* Responsive floor: below ~900px the main content would be crushed by a fixed
   220px column, so the whole rail hides rather than squeezing the views (the
   orb caption still surfaces OSA speech in the HUD window if that's up). */
@media (max-width: 900px) {
  .osa-rail { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .osa-rail * { animation: none !important; transition: none !important; }
}
`;

export default function OSARail({
  state = "idle",
  lastLine = "",
  events = [],
  onOpen,
  onBrief,
}) {
  // Brief-me-now in-flight guard — one request at a time; errors release the
  // button and stay otherwise silent (sidecar down ≡ the bridge's behavior).
  const [briefing, setBriefing] = useState(false);
  const handleBrief = async () => {
    if (briefing || !onBrief) return;
    setBriefing(true);
    try {
      await onBrief();
    } catch {
      /* degrade silently */
    } finally {
      setBriefing(false);
    }
  };
  // Re-render every 30s so relative timestamps ("2m ago") stay honest without
  // the caller having to push new props.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  // Newest first, bounded. `events` arrives oldest→newest from the bridge.
  const feed = events.slice(-RAIL_FEED_MAX).reverse();

  return (
    <aside className="osa-rail" data-testid="osa-rail" aria-label="OSA rail">
      <style>{styles}</style>

      {/* — Presence block: reactor orb + caption/status (OSAOrb renders the
            caption + /api/osa/state sub-status itself). — */}
      <section className="rail-section rail-presence" data-testid="rail-presence">
        <OSAOrb state={state} lastLine={lastLine} onOpen={onOpen} />
        {onBrief && (
          <button
            type="button"
            className="rail-brief"
            data-testid="rail-brief"
            onClick={handleBrief}
            disabled={briefing}
            aria-label="Ask OSA for a status briefing now"
          >
            {briefing ? "One moment…" : "Brief me"}
          </button>
        )}
      </section>

      {/* — Future blocks (e.g. vitals) drop in here as more rail-sections. — */}

      {/* — Proactive feed: downs / recoveries / briefings from the shared
            /api/osa/events poll. — */}
      <section className="rail-section rail-feed-section" data-testid="rail-feed">
        <div className="rail-head">Proactive feed</div>
        <div className="rail-feed" role="log" aria-label="OSA proactive messages">
          {feed.length === 0 && (
            <div className="rail-empty" data-testid="rail-empty">Nothing to report.</div>
          )}
          {feed.map((m) => (
            <div
              key={m.id}
              className={`rail-item${m.announced ? " announced" : ""}`}
              data-kind={m.kind}
              data-announced={m.announced ? "true" : "false"}
              data-testid="rail-feed-item"
            >
              {m.text}
              <span className="rail-ts">{fmtRel(m.ts, now)}</span>
            </div>
          ))}
        </div>
      </section>
    </aside>
  );
}
