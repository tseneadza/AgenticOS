/**
 * BrainOrb — Phase 16c rotating node-orb of the Brain2 vault (Canvas 2D,
 * NO new dependency — locked decision §2#5; three.js deliberately not added).
 *
 * One dot per note (fibonacci-sphere layout), tags as hollow dots. Idle:
 * slow Y-axis rotation (the "idiot lights" ambience). Selecting a note —
 * from the tree OR by clicking a dot — freezes the spin and highlights the
 * dot + its linked neighbors. Deselect resumes.
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

// deterministic folder → palette-slot hash
function folderColor(folder, theme) {
  const palette = [theme["--accent"], theme["--green"], theme["--yellow"], theme["--red"], theme["--text"]];
  if (!folder) return theme["--text-dim"];
  let h = 0;
  for (let i = 0; i < folder.length; i++) h = (h * 31 + folder.charCodeAt(i)) >>> 0;
  return palette[h % palette.length];
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

  // Precompute layout + adjacency whenever the graph changes.
  const model = useMemo(() => {
    const nodes = graph?.nodes || [];
    const pts = spherePoints(nodes.length);
    const neighbors = new Map();
    for (const e of graph?.edges || []) {
      if (!neighbors.has(e.source)) neighbors.set(e.source, new Set());
      if (!neighbors.has(e.target)) neighbors.set(e.target, new Set());
      neighbors.get(e.source).add(e.target);
      neighbors.get(e.target).add(e.source);
    }
    return {
      nodes: nodes.map((n, i) => ({ ...n, p: pts[i] })),
      neighbors,
    };
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

    const draw = () => {
      if (!running) return;
      const frozen = Boolean(selectedPath);
      if (!frozen) st.angle += 0.0035;

      const W = canvas.width;
      const H = canvas.height;
      const dpr = window.devicePixelRatio || 1;
      const cx = W / 2;
      const cy = H / 2;
      const R = Math.min(W, H) * 0.4;
      const sin = Math.sin(st.angle);
      const cos = Math.cos(st.angle);
      const selSet = selectedPath ? model.neighbors.get(selectedPath) : null;

      ctx.clearRect(0, 0, W, H);

      // pass 1 — project every node
      projected = model.nodes.map((n) => {
        const [x0, y0, z0] = n.p;
        const x = x0 * cos + z0 * sin; // Y-axis rotation
        const z = -x0 * sin + z0 * cos;
        const depth = (z + 1) / 2; // 0 back → 1 front
        const isSel = n.id === selectedPath;
        const isNbr = selSet ? selSet.has(n.id) : false;
        const r = (n.type === "tag" ? 1.6 : 2.2) * dpr * (0.6 + depth * 0.8) * (isSel ? 2.4 : isNbr ? 1.5 : 1);
        return {
          id: n.id, label: n.label, type: n.type, folder: n.folder,
          x: cx + x * R, y: cy + y0 * R, z, depth, r, isSel, isNbr,
        };
      });

      // pass 2 — dim edges selected → neighbors (under the dots)
      const sel = selectedPath ? projected.find((p) => p.isSel) : null;
      if (sel && selSet) {
        ctx.globalAlpha = 0.25;
        ctx.strokeStyle = st.theme["--border-soft"];
        ctx.lineWidth = dpr;
        for (const p of projected) {
          if (p.isNbr) {
            ctx.beginPath();
            ctx.moveTo(sel.x, sel.y);
            ctx.lineTo(p.x, p.y);
            ctx.stroke();
          }
        }
      }

      // pass 3 — dots, back to front
      for (const p of [...projected].sort((a, b) => a.z - b.z)) {
        const base = p.type === "tag" ? st.theme["--text-dim"] : folderColor(p.folder, st.theme);
        ctx.globalAlpha = selectedPath && !p.isSel && !p.isNbr ? 0.18 + p.depth * 0.12 : 0.35 + p.depth * 0.65;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        if (p.type === "tag" && !p.isSel) {
          ctx.strokeStyle = base;
          ctx.lineWidth = dpr;
          ctx.stroke();
        } else {
          ctx.fillStyle = p.isSel ? st.theme["--accent"] : base;
          ctx.fill();
        }
        if (p.isSel) {
          ctx.globalAlpha = 0.35;
          ctx.beginPath();
          ctx.arc(p.x, p.y, p.r * 2.2, 0, Math.PI * 2);
          ctx.strokeStyle = st.theme["--accent"];
          ctx.lineWidth = dpr;
          ctx.stroke();
        }
      }
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
