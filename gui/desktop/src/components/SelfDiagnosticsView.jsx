import { useCallback, useEffect, useRef, useState } from "react";
import { get } from "../api";
import { sidecarWsUrl, sidecarHost } from "../settings";

/**
 * SelfDiagnosticsView — the hidden self-diagnostics dashboard (Phase 12).
 *
 * A full-screen overlay (NOT registered in the nav `VIEWS`) revealed by a
 * secret gesture (triple-tapping the bottom-right corner; see App.jsx
 * `CornerReveal`). Also reachable via the `#diag` URL hash as a quiet dev
 * escape hatch when the gesture misfires.
 *
 * Shows last-known (cached) results instantly on open, refreshes the live
 * system self-checks immediately, and offers a "Run diagnostics" button that
 * streams a full pytest + vitest + system run over
 * ws://localhost:5130/api/diagnostics/ws/run.
 *
 * All colors use real theme tokens (App.css :root). Hover/transition CSS lives
 * in a component-scoped injected stylesheet (`sd-*`) per the frontend
 * conventions — inline styles can't express pseudo-states.
 */

// Sidecar WS endpoint — resolved lazily from Settings (settings.js).
const wsUrl = () => sidecarWsUrl("/api/diagnostics/ws/run");
const MAX_LOG = 200;

const STATUS_META = {
  ok: { label: "OK", cls: "sd-ok" },
  warn: { label: "WARN", cls: "sd-warn" },
  fail: { label: "FAIL", cls: "sd-fail" },
  running: { label: "…", cls: "sd-running" },
  unknown: { label: "—", cls: "sd-unknown" },
};

function Pill({ status }) {
  const m = STATUS_META[status] || STATUS_META.unknown;
  return <span className={`sd-pill ${m.cls}`}>{m.label}</span>;
}

function fmtTs(ts) {
  if (!ts) return "never";
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return "unknown";
  }
}

// Derive a suite's status from a result row (returncode + failed count).
function suiteStatus(res) {
  if (!res) return "unknown";
  if (res.status) return res.status;
  return res.failed === 0 && res.returncode === 0 ? "ok" : "fail";
}

const SCOPED_CSS = `
.sd-backdrop {
  position: fixed; inset: 0; z-index: 9000;
  background: rgba(0,0,0,0.55);
  display: flex; align-items: center; justify-content: center;
  animation: sd-fade 140ms ease-out;
}
@keyframes sd-fade { from { opacity: 0; } to { opacity: 1; } }
.sd-panel {
  width: min(920px, 94vw); max-height: 90vh; overflow: hidden;
  display: flex; flex-direction: column;
  background: var(--bg-panel); color: var(--text);
  border: var(--border-w) solid var(--border);
  border-radius: 8px; box-shadow: 0 18px 60px rgba(0,0,0,0.5);
}
.sd-head {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 18px; border-bottom: 1px solid var(--border-soft);
  background: var(--bg-inset);
}
.sd-title { font-weight: 700; font-size: 15px; letter-spacing: 0.02em; }
.sd-sub { color: var(--text-dim); font-size: 12px; font-family: var(--mono); }
.sd-overall {
  margin-left: 4px; padding: 2px 10px; border-radius: 12px;
  font-family: var(--mono); font-size: 11px; font-weight: 700;
  text-transform: uppercase;
}
.sd-overall.sd-ok   { background: rgba(127,176,105,0.18); color: var(--green); }
.sd-overall.sd-warn { background: rgba(224,184,76,0.18);  color: var(--yellow); }
.sd-overall.sd-fail { background: rgba(217,83,79,0.18);   color: var(--red); }
.sd-spacer { flex: 1; }
.sd-btn {
  font-family: var(--mono); font-size: 12px; cursor: pointer;
  padding: 6px 14px; border-radius: 5px;
  border: 1px solid var(--border-soft); background: var(--bg-panel);
  color: var(--text); transition: background 120ms, border-color 120ms;
}
.sd-btn:hover { border-color: var(--accent); }
.sd-btn.sd-primary { background: var(--accent); color: #1b1b19; border-color: var(--accent); font-weight: 700; }
.sd-btn.sd-primary:hover { filter: brightness(1.06); }
.sd-btn:disabled { opacity: 0.5; cursor: default; }
.sd-close {
  font-size: 18px; line-height: 1; cursor: pointer; color: var(--text-dim);
  background: none; border: none; padding: 4px 8px;
}
.sd-close:hover { color: var(--text); }
.sd-body { overflow-y: auto; padding: 16px 18px; }
.sd-section { margin-bottom: 20px; }
.sd-section-h {
  display: flex; align-items: center; gap: 10px; margin-bottom: 8px;
  font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--text-dim);
}
.sd-section-h .sd-count { font-family: var(--mono); font-size: 11px; }
.sd-check {
  display: flex; align-items: center; gap: 12px;
  padding: 9px 12px; border: 1px solid var(--border-soft);
  border-radius: 5px; margin-bottom: 6px; background: var(--bg-inset);
}
.sd-check-label { font-weight: 600; min-width: 190px; }
.sd-check-detail { color: var(--text-dim); font-size: 12px; font-family: var(--mono); flex: 1; }
.sd-pill {
  font-family: var(--mono); font-size: 10px; font-weight: 700;
  padding: 2px 7px; border-radius: 3px; min-width: 42px; text-align: center;
}
.sd-pill.sd-ok   { background: rgba(127,176,105,0.16); color: var(--green); border: 1px solid rgba(127,176,105,0.3); }
.sd-pill.sd-warn { background: rgba(224,184,76,0.16);  color: var(--yellow); border: 1px solid rgba(224,184,76,0.3); }
.sd-pill.sd-fail { background: rgba(217,83,79,0.16);   color: var(--red); border: 1px solid rgba(217,83,79,0.3); }
.sd-pill.sd-running { background: var(--bg-panel); color: var(--accent); border: 1px solid var(--border-soft); }
.sd-pill.sd-unknown { background: var(--bg-panel); color: var(--text-dim); border: 1px solid var(--border-soft); }
.sd-suite {
  display: flex; align-items: center; gap: 14px;
  padding: 12px; border: 1px solid var(--border-soft);
  border-radius: 5px; margin-bottom: 6px; background: var(--bg-inset);
}
.sd-suite-name { font-weight: 700; min-width: 150px; }
.sd-suite-stats { font-family: var(--mono); font-size: 12px; color: var(--text-dim); flex: 1; }
.sd-suite-stats b.sd-pass { color: var(--green); }
.sd-suite-stats b.sd-failn { color: var(--red); }
.sd-log {
  margin-top: 4px; background: #000; color: #cfcfc7;
  font-family: var(--mono); font-size: 11px; line-height: 1.45;
  padding: 10px 12px; border-radius: 5px; border: 1px solid var(--border-soft);
  max-height: 180px; overflow-y: auto; white-space: pre-wrap; word-break: break-all;
}
.sd-empty { color: var(--text-dim); font-size: 12px; font-style: italic; }
`;

export default function SelfDiagnosticsView({ onClose }) {
  const [system, setSystem] = useState(null); // { checks, summary }
  const [suites, setSuites] = useState({}); // { pytest, vitest }
  const [ts, setTs] = useState(null);
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState([]);
  const [error, setError] = useState("");
  const wsRef = useRef(null);
  const logRef = useRef(null);

  // Load cached results + fresh live system checks on open.
  useEffect(() => {
    let alive = true;
    get("/api/diagnostics/cached")
      .then((c) => {
        if (!alive || !c || c.available === false) return;
        if (c.system) setSystem(c.system);
        if (c.suites) setSuites(c.suites);
        if (c.ts) setTs(c.ts);
      })
      .catch(() => {});
    // Always refresh live system checks — they're cheap and shouldn't be stale.
    get("/api/diagnostics/system")
      .then((s) => {
        if (alive && s?.checks) setSystem({ checks: s.checks, summary: s.summary });
      })
      .catch(() => setError(`Sidecar unreachable — is it running on ${sidecarHost()}?`));
    return () => { alive = false; };
  }, []);

  // Esc closes.
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Auto-scroll the streaming log.
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [log]);

  useEffect(() => () => wsRef.current?.close(), []);

  const runDiagnostics = useCallback(() => {
    if (running) return;
    setRunning(true);
    setError("");
    setLog([]);
    setSuites({}); // clear prior suite rows so pills show "running"
    let ws;
    try {
      ws = new WebSocket(wsUrl());
    } catch {
      setError("Could not open diagnostics socket.");
      setRunning(false);
      return;
    }
    wsRef.current = ws;
    ws.onopen = () => ws.send(JSON.stringify({ suites: ["system", "pytest", "vitest"] }));
    ws.onmessage = (m) => {
      let f;
      try { f = JSON.parse(m.data); } catch { return; }
      if (f.type === "progress") {
        setLog((l) => [...l.slice(-(MAX_LOG - 1)), `[${f.suite}] ${f.message}`]);
      } else if (f.type === "system") {
        setSystem({ checks: f.checks, summary: f.summary });
      } else if (f.type === "suite_result") {
        setSuites((prev) => ({ ...prev, [f.suite]: f }));
      } else if (f.type === "complete") {
        if (f.result?.ts) setTs(f.result.ts);
        setRunning(false);
        ws.close();
      } else if (f.type === "error") {
        setError(f.error || "Diagnostics run failed.");
        setRunning(false);
      }
    };
    ws.onerror = () => { setError("Diagnostics socket error."); setRunning(false); };
    ws.onclose = () => setRunning(false);
  }, [running]);

  const overall = system?.summary?.overall || "unknown";
  const overallCls = { ok: "sd-ok", warn: "sd-warn", fail: "sd-fail" }[overall] || "";
  const checks = system?.checks || [];

  const suiteRow = (key, name) => {
    const res = suites[key];
    const status = running && !res ? "running" : suiteStatus(res);
    return (
      <div className="sd-suite" key={key}>
        <Pill status={status} />
        <span className="sd-suite-name">{name}</span>
        <span className="sd-suite-stats">
          {res ? (
            <>
              <b className="sd-pass">{res.passed} passed</b>
              {res.failed > 0 && <> · <b className="sd-failn">{res.failed} failed</b></>}
              {" "}· {res.total} total
              {res.duration_s != null && <> · {res.duration_s}s</>}
            </>
          ) : running ? "running…" : <span className="sd-empty">no run yet — press Run diagnostics</span>}
        </span>
      </div>
    );
  };

  return (
    <div className="sd-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <style>{SCOPED_CSS}</style>
      <div className="sd-panel" role="dialog" aria-label="Self Diagnostics">
        <div className="sd-head">
          <span className="sd-title">Self-Diagnostics</span>
          {overallCls && <span className={`sd-overall ${overallCls}`}>{overall}</span>}
          <span className="sd-sub">last run: {fmtTs(ts)}</span>
          <div className="sd-spacer" />
          <button className="sd-btn sd-primary" onClick={runDiagnostics} disabled={running}>
            {running ? "Running…" : "Run diagnostics"}
          </button>
          <button className="sd-close" onClick={onClose} aria-label="Close">×</button>
        </div>

        <div className="sd-body">
          {error && (
            <div className="sd-check" style={{ borderColor: "var(--red)" }}>
              <Pill status="fail" />
              <span className="sd-check-detail" style={{ color: "var(--red)" }}>{error}</span>
            </div>
          )}

          <div className="sd-section">
            <div className="sd-section-h">
              <span>System self-checks</span>
              {system?.summary && (
                <span className="sd-count">
                  {system.summary.ok} ok · {system.summary.warn} warn · {system.summary.fail} fail
                </span>
              )}
            </div>
            {checks.length === 0 ? (
              <div className="sd-empty">No system data yet.</div>
            ) : (
              checks.map((c) => (
                <div className="sd-check" key={c.id}>
                  <Pill status={c.status} />
                  <span className="sd-check-label">{c.label}</span>
                  <span className="sd-check-detail">{c.detail}</span>
                </div>
              ))
            )}
          </div>

          <div className="sd-section">
            <div className="sd-section-h"><span>Test suites</span></div>
            {suiteRow("pytest", "Backend (pytest)")}
            {suiteRow("vitest", "Frontend (vitest)")}
          </div>

          {(running || log.length > 0) && (
            <div className="sd-section">
              <div className="sd-section-h"><span>Live output</span></div>
              <div className="sd-log" ref={logRef}>
                {log.length ? log.join("\n") : "waiting for output…"}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
