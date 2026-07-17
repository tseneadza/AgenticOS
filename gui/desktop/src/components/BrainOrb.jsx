/**
 * BrainOrb — Phase 16c rotating node-orb of the Brain2 vault (Canvas 2D,
 * NO new dependency — locked decision §2#5; three.js deliberately not added).
 *
 * Obsidian-graph behavior (Tony, 2026-07-16):
 * - FULL mode (nothing selected): every note is a solid dot on an evenly
 *   distributed sphere (deterministic shuffle so folders don't band into
 *   latitude stripes), with faint wikilink edges drawn between connected
 *   docs — the whole thing slowly rotating.
 * - LOCAL mode (a doc selected, from the tree OR by clicking a dot): a NEW
 *   orb replaces the collection — the selected doc at center with only its
 *   linked docs orbiting it, edges + labels visible (Obsidian's local graph).
 *   Clicking a neighbor re-centers on it; clicking empty space returns to
 *   the full collection.
 * - STEERABLE (Tony, 2026-07-16): drag the orb to rotate it freely on both
 *   axes; releasing a drag keeps the spin going in the flung direction at
 *   the ambient speed. A drag is not a click — selection only fires on
 *   press-release with <4px movement.
 * - COLORS (Tony, 2026-07-16): every group (top-level folder) gets its own
 *   hue, evenly spaced on the wheel so groups are visually unique; docs not
 *   in any group share one neutral color until they find a group.
 * - Tag nodes are NOT rendered (no hollow placeholder dots); edges are real
 *   [[wikilink]] connections only.
 *
 * Rules honored (design §7 / gui-frontend-conventions):
 * - UI chrome uses theme tokens via getComputedStyle (re-read on
 *   `theme-changed` / data-theme mutation). Group hues are data-viz colors
 *   generated on the HSL wheel (same precedent as WebNewsView categories).
 * - getContext('2d') is null under jsdom → component no-ops cleanly.
 * - rAF pauses when the document is hidden (battery) and stops on unmount.
 *
 * Props: graph {nodes, edges} · selectedPath · onSelect(id|null)
 */
import { useRef, useEffect, useState, useMemo } from "react";

const TOKEN_NAMES = ["--accent", "--green", "--yellow", "--red", "--text", "--text-dim", "--bg-panel", "--border-soft"];
const AMBIENT_SPEED = 0.0035; // radians/frame — the "idiot lights" pace
const DRAG_CLICK_PX = 4; // press-release under this = click, over = steer

function readTheme() {
  if (typeof document === "undefined") return {};
  const cs = getComputedStyle(document.documentElement);
  const theme = {};
  for (const t of TOKEN_NAMES) theme[t] = (cs.getPropertyValue(t) || "").trim() || "#888";
  return theme;
}

function hashStr(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}

// evenly distribute N points on a unit sphere (fibonacci spiral)
function spherePoints(n) {
  const pts = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = n === 1 ? 0 : 1 - (i / (n - 1)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const th = golden * i;
    pts.push([Math.cos(th) * r, y, Math.sin(th) * r]);
  }
  return pts;
}

// One unique hue per group, evenly spaced around the wheel so every group is
// visually distinct regardless of how many exist. Ungrouped (root-level)
// docs share one neutral color until they find a group.
function buildGroupColors(folders) {
  const named = folders.filter((f) => f);
  const map = new Map();
  named.forEach((f, i) => {
    const hue = Math.round((i / Math.max(named.length, 1)) * 360);
    map.set(f, `hsl(${hue}, 60%, 62%)`);
  });
  return map;
}

export default function BrainOrb({ graph, selectedPath, onSelect }) {
  const canvasRef = useRef(null);
  const [hover, setHover] = useState(null); // {id, label, x, y}
  const stateRef = useRef({
    rot: { x: -0.35, y: 0 },
    vel: { x: 0, y: AMBIENT_SPEED },
    drag: null, // {px, py, moved, vx, vy}
    theme: readTheme(),
    hoverId: null,
  });

  // Precompute layout + adjacency whenever the graph changes. Notes only —
  // tag nodes would render as placeholder-looking dots; edges are wikilinks.
  const model = useMemo(() => {
    const notes = (graph?.nodes || []).filter((n) => n.type === "note");
    const noteIds = new Set(notes.map((n) => n.id));
    const edges = (graph?.edges || []).filter(
      (e) => e.kind === "link" && noteIds.has(e.source) && noteIds.has(e.target)
    );
    const neighbors = new Map();
    for (const e of edges) {
      if (!neighbors.has(e.source)) neighbors.set(e.source, new Set());
      if (!neighbors.has(e.target)) neighbors.set(e.target, new Set());
      neighbors.get(e.source).add(e.target);
      neighbors.get(e.target).add(e.source);
    }
    // Deterministic shuffle before assigning sphere points: the vault list is
    // alphabetical (= folder-grouped), which paints folder-colored latitude
    // bands on the spiral. Hash order spreads colors uniformly.
    const shuffled = [...notes].sort((a, b) => hashStr(a.id) - hashStr(b.id));
    const pts = spherePoints(shuffled.length);
    const nodes = shuffled.map((n, i) => ({ ...n, p: pts[i] }));
    const folders = [...new Set(notes.map((n) => n.folder))].sort();
    return {
      nodes,
      edges,
      neighbors,
      byId: new Map(nodes.map((n) => [n.id, n])),
      folders,
      groupColors: buildGroupColors(folders),
    };
  }, [graph]);

  // group color lookup shared by canvas + legend
  const colorFor = (folder, theme) =>
    folder ? model.groupColors.get(folder) || theme["--text"] : theme["--text-dim"];

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext && canvas.getContext("2d");
    if (!ctx) return undefined; // jsdom / vitest — no-op cleanly

    const st = stateRef.current;
    let raf = 0;
    let running = true;
    let projected = []; // [{id,label,x,y,r,z}] refreshed every frame for hit-tests

    const onTheme = () => {
      st.theme = readTheme();
    };
    window.addEventListener("theme-changed", onTheme);
    const mo = typeof MutationObserver !== "undefined" ? new MutationObserver(onTheme) : null;
    mo?.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });

    const resize = () => {
      const rect = canvas.parentElement?.getBoundingClientRect();
      if (!rect) return;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor((rect.height || 320) * dpr));
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height || 320}px`;
    };
    resize();
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(resize) : null;
    ro?.observe(canvas.parentElement || canvas);

    // free two-axis rotation: yaw (Y) then pitch (X)
    const project = (p, cx, cy, R) => {
      const [x0, y0, z0] = p;
      const sy = Math.sin(st.rot.y);
      const cyw = Math.cos(st.rot.y);
      const sx = Math.sin(st.rot.x);
      const cxp = Math.cos(st.rot.x);
      const x1 = x0 * cyw + z0 * sy;
      const z1 = -x0 * sy + z0 * cyw;
      const y2 = y0 * cxp - z1 * sx;
      const z2 = y0 * sx + z1 * cxp;
      return { x: cx + x1 * R, y: cy + y2 * R, z: z2, depth: (z2 + 1) / 2 };
    };

    const truncate = (s, n = 20) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

    // FULL mode — the whole collection, spinning, with faint link edges.
    const drawFull = (W, H, dpr) => {
      const cx = W / 2;
      const cy = H / 2;
      const R = Math.min(W, H) * 0.4;

      projected = model.nodes.map((n) => {
        const pr = project(n.p, cx, cy, R);
        return {
          id: n.id, label: n.label, folder: n.folder,
          x: pr.x, y: pr.y, z: pr.z, depth: pr.depth,
          r: 2.2 * dpr * (0.6 + pr.depth * 0.8),
        };
      });
      const byId = new Map(projected.map((p) => [p.id, p]));

      // link edges between connected docs — always visible, depth-faded.
      // Alpha floor keeps back-side links legible; front links read clearly
      // (0.04–0.14 was invisible on-device — Tony 2026-07-16).
      ctx.lineWidth = dpr * 0.9;
      ctx.strokeStyle = st.theme["--text-dim"];
      for (const e of model.edges) {
        const a = byId.get(e.source);
        const b = byId.get(e.target);
        if (!a || !b) continue;
        ctx.globalAlpha = 0.14 + ((a.depth + b.depth) / 2) * 0.3;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }

      // dots, back to front
      for (const p of [...projected].sort((a, b) => a.z - b.z)) {
        ctx.globalAlpha = 0.35 + p.depth * 0.65;
        ctx.fillStyle = colorFor(p.folder, st.theme);
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    // LOCAL mode — a new orb: the selected doc centered, its linked docs
    // orbiting it with visible edges + labels (Obsidian's local graph).
    const drawLocal = (W, H, dpr, sel) => {
      const cx = W / 2;
      const cy = H / 2;
      const R = Math.min(W, H) * 0.33;
      const nbrIds = [...(model.neighbors.get(sel.id) || [])];
      const pts = spherePoints(nbrIds.length);
      const font = `${Math.round(10 * dpr)}px sans-serif`;

      projected = nbrIds.map((id, i) => {
        const n = model.byId.get(id);
        const pr = project(pts[i], cx, cy, R);
        return {
          id, label: n?.label || id, folder: n?.folder || "",
          x: pr.x, y: pr.y, z: pr.z, depth: pr.depth,
          r: 3.2 * dpr * (0.7 + pr.depth * 0.6),
        };
      });

      // cross-links among the linked docs themselves (drilling down keeps
      // showing the connections, not just spokes — Tony 2026-07-16), drawn
      // first so the center spokes read on top
      const byId = new Map(projected.map((p) => [p.id, p]));
      ctx.lineWidth = dpr * 0.7;
      ctx.strokeStyle = st.theme["--text-dim"];
      for (const e of model.edges) {
        if (e.source === sel.id || e.target === sel.id) continue; // spokes below
        const a = byId.get(e.source);
        const b = byId.get(e.target);
        if (!a || !b) continue;
        ctx.globalAlpha = 0.18 + ((a.depth + b.depth) / 2) * 0.3;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }

      // edges: center → every linked doc
      ctx.lineWidth = dpr * 0.8;
      ctx.strokeStyle = st.theme["--border-soft"];
      for (const p of projected) {
        ctx.globalAlpha = 0.25 + p.depth * 0.35;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(p.x, p.y);
        ctx.stroke();
      }

      // linked docs, back to front; labels only on the front hemisphere so a
      // heavily-linked doc doesn't dissolve into overlapping text
      ctx.font = font;
      ctx.textAlign = "center";
      for (const p of [...projected].sort((a, b) => a.z - b.z)) {
        ctx.globalAlpha = 0.5 + p.depth * 0.5;
        ctx.fillStyle = colorFor(p.folder, st.theme);
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
        if (p.depth > 0.55) {
          ctx.globalAlpha = (p.depth - 0.55) * 2.2;
          ctx.fillStyle = st.theme["--text-dim"];
          ctx.fillText(truncate(p.label), p.x, p.y + p.r + 11 * dpr);
        }
      }

      // the selected doc at center: accent dot + halo + label
      const cr = 6 * dpr;
      ctx.globalAlpha = 1;
      ctx.fillStyle = st.theme["--accent"];
      ctx.beginPath();
      ctx.arc(cx, cy, cr, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 0.4;
      ctx.strokeStyle = st.theme["--accent"];
      ctx.lineWidth = dpr;
      ctx.beginPath();
      ctx.arc(cx, cy, cr * 2, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillStyle = st.theme["--text"];
      ctx.fillText(truncate(sel.label, 28), cx, cy + cr + 13 * dpr);
      if (nbrIds.length === 0) {
        ctx.globalAlpha = 0.7;
        ctx.fillStyle = st.theme["--text-dim"];
        ctx.fillText("no linked docs", cx, cy + cr + 26 * dpr);
      }

      projected.push({ id: sel.id, label: sel.label, x: cx, y: cy, z: 1, r: cr });
    };

    const draw = () => {
      if (!running) return;
      if (!st.drag) {
        // ambient spin continues in whatever direction the last fling set;
        // the local orb turns at a gentler pace, same heading
        const damp = selectedPath ? 0.45 : 1;
        st.rot.x += st.vel.x * damp;
        st.rot.y += st.vel.y * damp;
      }

      const W = canvas.width;
      const H = canvas.height;
      const dpr = window.devicePixelRatio || 1;
      ctx.clearRect(0, 0, W, H);

      const sel = selectedPath ? model.byId.get(selectedPath) : null;
      if (sel) drawLocal(W, H, dpr, sel);
      else drawFull(W, H, dpr);

      // hit-tests want generous radii
      for (const p of projected) p.r = Math.max(p.r, 4 * dpr);
      ctx.globalAlpha = 1;
      raf = requestAnimationFrame(draw);
    };

    const pick = (ev) => {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const mx = (ev.clientX - rect.left) * dpr;
      const my = (ev.clientY - rect.top) * dpr;
      let best = null;
      for (const p of projected) {
        const d2 = (p.x - mx) ** 2 + (p.y - my) ** 2;
        const hit = (p.r + 5 * dpr) ** 2;
        if (d2 <= hit && (!best || p.z > best.z)) best = { ...p, d2 };
      }
      return best;
    };

    // ── steering: drag rotates the orb directly; release flings the spin in
    // that direction at ambient speed; a tiny press-release is a click ──────
    const onDown = (ev) => {
      st.drag = { px: ev.clientX, py: ev.clientY, x0: ev.clientX, y0: ev.clientY, moved: false, vx: 0, vy: 0 };
    };
    const onMove = (ev) => {
      if (st.drag) {
        const dx = ev.clientX - st.drag.px;
        const dy = ev.clientY - st.drag.py;
        st.drag.px = ev.clientX;
        st.drag.py = ev.clientY;
        // horizontal drag = yaw, vertical drag = pitch (grab-and-turn feel)
        st.rot.y += dx * 0.008;
        st.rot.x -= dy * 0.008;
        st.drag.vy = dx * 0.008;
        st.drag.vx = -dy * 0.008;
        if (Math.abs(ev.clientX - st.drag.x0) + Math.abs(ev.clientY - st.drag.y0) > DRAG_CLICK_PX) {
          st.drag.moved = true;
          if (st.hoverId) {
            st.hoverId = null;
            setHover(null);
          }
        }
        return;
      }
      const best = pick(ev);
      const next = best ? best.id : null;
      if (next !== st.hoverId) {
        st.hoverId = next;
        setHover(
          best
            ? { id: best.id, label: best.label, x: ev.clientX, y: ev.clientY }
            : null
        );
      }
    };
    const onUp = (ev) => {
      const drag = st.drag;
      st.drag = null;
      if (!drag) return;
      if (!drag.moved) {
        // a click: select the dot under the pointer (or clear selection)
        const best = pick(ev);
        onSelect?.(best ? best.id : null);
        return;
      }
      // a fling: keep spinning in the flung direction at the ambient pace
      const mag = Math.hypot(drag.vx, drag.vy);
      if (mag > 1e-4) {
        st.vel = {
          x: (drag.vx / mag) * AMBIENT_SPEED,
          y: (drag.vy / mag) * AMBIENT_SPEED,
        };
      }
    };
    canvas.addEventListener("mousedown", onDown);
    canvas.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);

    const onVis = () => {
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(raf);
      } else if (!running) {
        running = true;
        raf = requestAnimationFrame(draw);
      }
    };
    document.addEventListener("visibilitychange", onVis);

    raf = requestAnimationFrame(draw);
    return () => {
      running = false;
      cancelAnimationFrame(raf);
      canvas.removeEventListener("mousedown", onDown);
      canvas.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("theme-changed", onTheme);
      mo?.disconnect();
      ro?.disconnect();
    };
  }, [model, selectedPath, onSelect]);

  if (!graph) {
    return (
      <div style={{ color: "var(--text-dim)", fontSize: 12, padding: 8 }} data-testid="orb-empty">
        Graph unavailable.
      </div>
    );
  }

  return (
    <div style={{ position: "relative", flex: 1, minHeight: 0 }} data-testid="brain-orb">
      <canvas
        ref={canvasRef}
        style={{ display: "block", width: "100%", height: "100%", cursor: "grab" }}
      />
      {hover && (
        <div
          style={{
            position: "fixed",
            left: hover.x + 10,
            top: hover.y + 10,
            background: "var(--bg-inset)",
            border: "1px solid var(--border-soft)",
            borderRadius: 6,
            padding: "2px 8px",
            fontSize: 11,
            color: "var(--text)",
            pointerEvents: "none",
            zIndex: 50,
          }}
          data-testid="orb-tooltip"
        >
          {hover.label}
        </div>
      )}
      <div
        style={{
          position: "absolute",
          left: 8,
          bottom: 6,
          display: "flex",
          flexWrap: "wrap",
          gap: "4px 10px",
          fontSize: 10.5,
          color: "var(--text-dim)",
          maxWidth: "90%",
        }}
        data-testid="orb-legend"
      >
        {model.folders.map((f) => (
          <span key={f || "(ungrouped)"} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: f ? model.groupColors.get(f) : "var(--text-dim)",
                display: "inline-block",
              }}
            />
            {f || "(ungrouped)"}
          </span>
        ))}
      </div>
    </div>
  );
}
