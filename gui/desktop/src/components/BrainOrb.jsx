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
 * - Tag nodes are NOT rendered (no hollow placeholder dots); edges are real
 *   [[wikilink]] connections only.
 *
 * Rules honored (design §7 / gui-frontend-conventions):
 * - Canvas 2D can't read CSS vars → theme tokens via getComputedStyle at
 *   mount, re-read on `theme-changed` / data-theme mutation. No hardcoded hex.
 * - getContext('2d') is null under jsdom → component no-ops cleanly.
 * - rAF pauses when the document is hidden (battery) and stops on unmount.
 *
 * Props: graph {nodes, edges} · selectedPath · onSelect(id|null)
 */
import { useRef, useEffect, useState, useMemo } from "react";

const TOKEN_NAMES = ["--accent", "--green", "--yellow", "--red", "--text", "--text-dim", "--bg-panel", "--border-soft"];

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

// deterministic folder → palette-slot hash
function folderColor(folder, theme) {
  const palette = [theme["--accent"], theme["--green"], theme["--yellow"], theme["--red"], theme["--text"]];
  if (!folder) return theme["--text-dim"];
  return palette[hashStr(folder) % palette.length];
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

export default function BrainOrb({ graph, selectedPath, onSelect }) {
  const canvasRef = useRef(null);
  const [hover, setHover] = useState(null); // {id, label, x, y}
  const stateRef = useRef({ angle: 0, theme: readTheme(), hoverId: null });

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
    return { nodes, edges, neighbors, byId: new Map(nodes.map((n) => [n.id, n])) };
  }, [graph]);

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

    const project = (p, cx, cy, R, sin, cos) => {
      const [x0, y0, z0] = p;
      const x = x0 * cos + z0 * sin; // Y-axis rotation
      const z = -x0 * sin + z0 * cos;
      return { x: cx + x * R, y: cy + y0 * R, z, depth: (z + 1) / 2 };
    };

    const truncate = (s, n = 20) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

    // FULL mode — the whole collection, spinning, with faint link edges.
    const drawFull = (W, H, dpr) => {
      const cx = W / 2;
      const cy = H / 2;
      const R = Math.min(W, H) * 0.4;
      const sin = Math.sin(st.angle);
      const cos = Math.cos(st.angle);

      projected = model.nodes.map((n) => {
        const pr = project(n.p, cx, cy, R, sin, cos);
        return {
          id: n.id, label: n.label, folder: n.folder,
          x: pr.x, y: pr.y, z: pr.z, depth: pr.depth,
          r: 2.2 * dpr * (0.6 + pr.depth * 0.8),
        };
      });
      const byId = new Map(projected.map((p) => [p.id, p]));

      // link edges between connected docs — always visible, depth-faded
      ctx.lineWidth = dpr * 0.6;
      ctx.strokeStyle = st.theme["--text-dim"];
      for (const e of model.edges) {
        const a = byId.get(e.source);
        const b = byId.get(e.target);
        if (!a || !b) continue;
        ctx.globalAlpha = 0.04 + ((a.depth + b.depth) / 2) * 0.1;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }

      // dots, back to front
      for (const p of [...projected].sort((a, b) => a.z - b.z)) {
        ctx.globalAlpha = 0.35 + p.depth * 0.65;
        ctx.fillStyle = folderColor(p.folder, st.theme);
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
      const sin = Math.sin(st.angle);
      const cos = Math.cos(st.angle);
      const nbrIds = [...(model.neighbors.get(sel.id) || [])];
      const pts = spherePoints(nbrIds.length);
      const font = `${Math.round(10 * dpr)}px sans-serif`;

      projected = nbrIds.map((id, i) => {
        const n = model.byId.get(id);
        const pr = project(pts[i], cx, cy, R, sin, cos);
        return {
          id, label: n?.label || id, folder: n?.folder || "",
          x: pr.x, y: pr.y, z: pr.z, depth: pr.depth,
          r: 3.2 * dpr * (0.7 + pr.depth * 0.6),
        };
      });

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
        ctx.fillStyle = folderColor(p.folder, st.theme);
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
      st.angle += selectedPath ? 0.0015 : 0.0035; // local orb turns gently

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

    const onClick = (ev) => {
      const best = pick(ev);
      onSelect?.(best ? best.id : null);
    };
    const onMove = (ev) => {
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
    canvas.addEventListener("click", onClick);
    canvas.addEventListener("mousemove", onMove);

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
      canvas.removeEventListener("click", onClick);
      canvas.removeEventListener("mousemove", onMove);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("theme-changed", onTheme);
      mo?.disconnect();
      ro?.disconnect();
    };
  }, [model, selectedPath, onSelect]);

  const folders = useMemo(() => {
    const seen = new Map();
    for (const n of graph?.nodes || []) {
      if (n.type === "note" && !seen.has(n.folder)) seen.set(n.folder, true);
    }
    return [...seen.keys()].sort();
  }, [graph]);

  if (!graph) {
    return (
      <div style={{ color: "var(--text-dim)", fontSize: 12, padding: 8 }} data-testid="orb-empty">
        Graph unavailable.
      </div>
    );
  }

  return (
    <div style={{ position: "relative", flex: 1, minHeight: 0 }} data-testid="brain-orb">
      <canvas ref={canvasRef} style={{ display: "block", width: "100%", height: "100%" }} />
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
        {folders.map((f) => (
          <span key={f || "(root)"} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: folderColor(f, stateRef.current.theme),
                display: "inline-block",
              }}
            />
            {f || "(root)"}
          </span>
        ))}
      </div>
    </div>
  );
}
