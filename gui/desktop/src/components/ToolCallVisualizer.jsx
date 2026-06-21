import { useState, useEffect, useCallback, useRef } from "react";

const SIDECAR = "http://localhost:8000";

// ── helpers ────────────────────────────────────────────────────────────────

function fmtTime(ts) {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtDuration(start, end) {
  if (!start || !end) return "";
  const ms = Math.round((end - start) * 1000);
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

function statusColor(status) {
  if (status === "completed") return "#7fb069";
  if (status === "failed")    return "#d9534f";
  if (status === "running")   return "#e0b84c";
  if (status === "interrupted") return "#a0a0ff";
  return "var(--fg-muted)";
}

function StatusDot({ status }) {
  const color = statusColor(status);
  const pulse = status === "running";
  return (
    <span style={{
      display: "inline-block", width: 8, height: 8, borderRadius: "50%",
      background: color, marginRight: 6, flexShrink: 0,
      boxShadow: pulse ? `0 0 0 2px ${color}44` : "none",
      animation: pulse ? "pulse-ring 1.4s ease infinite" : "none",
    }} />
  );
}

function JsonTree({ data, depth = 0 }) {
  const [collapsed, setCollapsed] = useState(depth > 1);

  if (data === null || data === undefined) return <span style={{ color: "var(--fg-muted)" }}>null</span>;
  if (typeof data === "boolean") return <span style={{ color: "#d97b4f" }}>{String(data)}</span>;
  if (typeof data === "number") return <span style={{ color: "#7fb069" }}>{data}</span>;
  if (typeof data === "string") {
    const truncated = data.length > 300 ? data.slice(0, 300) + "…" : data;
    return <span style={{ color: "#c8a96e", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{truncated}</span>;
  }
  if (Array.isArray(data)) {
    if (data.length === 0) return <span style={{ color: "var(--fg-muted)" }}>[]</span>;
    return (
      <span>
        <button className="json-toggle" onClick={() => setCollapsed(c => !c)}>
          {collapsed ? `▶ [${data.length}]` : "▼ ["}
        </button>
        {!collapsed && (
          <div style={{ paddingLeft: 16, borderLeft: "1px solid var(--border-soft)" }}>
            {data.map((item, i) => (
              <div key={i}><JsonTree data={item} depth={depth + 1} /></div>
            ))}
            <span style={{ color: "var(--fg-muted)" }}>]</span>
          </div>
        )}
      </span>
    );
  }
  if (typeof data === "object") {
    const keys = Object.keys(data);
    if (keys.length === 0) return <span style={{ color: "var(--fg-muted)" }}>{"{}"}</span>;
    return (
      <span>
        <button className="json-toggle" onClick={() => setCollapsed(c => !c)}>
          {collapsed ? `▶ {${keys.length}}` : "▼ {"}
        </button>
        {!collapsed && (
          <div style={{ paddingLeft: 16, borderLeft: "1px solid var(--border-soft)" }}>
            {keys.map(k => (
              <div key={k} style={{ marginBottom: 2 }}>
                <span style={{ color: "var(--accent)" }}>{k}</span>
                <span style={{ color: "var(--fg-muted)" }}>: </span>
                <JsonTree data={data[k]} depth={depth + 1} />
              </div>
            ))}
            <span style={{ color: "var(--fg-muted)" }}>{"}"}</span>
          </div>
        )}
      </span>
    );
  }
  return <span>{String(data)}</span>;
}

// ── Step node in the timeline ───────────────────────────────────────────────

function StepNode({ step, index, isLast }) {
  const [open, setOpen] = useState(false);
  const hasOutput = step.output !== null && step.output !== undefined;
  const hasTokens = step.tokens && step.tokens > 0;
  const hasCost = step.cost_usd && step.cost_usd > 0;

  return (
    <div style={{ display: "flex", gap: 0, position: "relative" }}>
      {/* vertical connector */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 28, flexShrink: 0 }}>
        <div style={{
          width: 12, height: 12, borderRadius: "50%",
          background: "var(--accent)", border: "2px solid var(--bg-inset)",
          flexShrink: 0, marginTop: 10,
        }} />
        {!isLast && (
          <div style={{ flex: 1, width: 2, background: "var(--border-soft)", minHeight: 20 }} />
        )}
      </div>

      {/* step card */}
      <div style={{ flex: 1, marginBottom: 8 }}>
        <button
          onClick={() => hasOutput && setOpen(o => !o)}
          style={{
            all: "unset", cursor: hasOutput ? "pointer" : "default",
            display: "flex", alignItems: "center", gap: 8,
            background: "var(--bg-inset)", borderRadius: 6, padding: "7px 10px",
            width: "100%", boxSizing: "border-box",
            border: "1px solid var(--border-soft)",
            userSelect: "none",
          }}
        >
          <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--accent)", minWidth: 20 }}>
            {index + 1}
          </span>
          <span style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--fg)", fontWeight: 600, flex: 1 }}>
            {step.step || <span style={{ color: "var(--fg-muted)" }}>—</span>}
          </span>
          {step.branch_to && (
            <span style={{ fontSize: 11, color: "#a0a0ff", fontFamily: "var(--mono)" }}>
              → {step.branch_to}
            </span>
          )}
          {hasTokens && (
            <span style={{ fontSize: 11, color: "#7fb069", fontFamily: "var(--mono)" }}>
              {step.tokens.toLocaleString()} tok
            </span>
          )}
          {hasCost && (
            <span style={{ fontSize: 11, color: "#e0b84c", fontFamily: "var(--mono)" }}>
              ${step.cost_usd.toFixed(4)}
            </span>
          )}
          {hasOutput && (
            <span style={{ fontSize: 11, color: "var(--fg-muted)" }}>
              {open ? "▲" : "▼"}
            </span>
          )}
        </button>

        {open && hasOutput && (
          <div style={{
            marginTop: 4, padding: "8px 10px",
            background: "var(--bg-panel)", borderRadius: 6,
            border: "1px solid var(--border-soft)",
            fontFamily: "var(--mono)", fontSize: 11,
            lineHeight: 1.6, overflow: "auto", maxHeight: 280,
          }}>
            <JsonTree data={step.output} depth={0} />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Run list item ───────────────────────────────────────────────────────────

function RunListItem({ run, selected, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        all: "unset", cursor: "pointer",
        display: "flex", flexDirection: "column", gap: 2,
        padding: "9px 12px", borderRadius: 6,
        background: selected ? "var(--bg-inset)" : "transparent",
        border: `1px solid ${selected ? "var(--accent)" : "transparent"}`,
        marginBottom: 3,
        transition: "background 0.1s",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <StatusDot status={run.status} />
        <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600, color: "var(--fg)", flex: 1 }}>
          {run.workflow}
        </span>
        <span style={{ fontSize: 10, color: "var(--fg-muted)", fontFamily: "var(--mono)" }}>
          {fmtDuration(run.started_at, run.finished_at)}
        </span>
      </div>
      <div style={{ display: "flex", gap: 8, paddingLeft: 14 }}>
        <span style={{ fontSize: 10, color: "var(--fg-muted)" }}>{fmtTime(run.started_at)}</span>
        {run.tokens_used > 0 && (
          <span style={{ fontSize: 10, color: "#7fb069" }}>{run.tokens_used.toLocaleString()} tok</span>
        )}
        {run.cost_usd > 0 && (
          <span style={{ fontSize: 10, color: "#e0b84c" }}>${run.cost_usd?.toFixed(4)}</span>
        )}
      </div>
    </button>
  );
}

// ── Main component ──────────────────────────────────────────────────────────

export default function ToolCallVisualizer() {
  const [runs, setRuns]           = useState([]);
  const [activeRuns, setActive]   = useState([]);
  const [selectedId, setSelected] = useState(null);
  const [steps, setSteps]         = useState(null);
  const [stepsErr, setStepsErr]   = useState(null);
  const [loadingSteps, setLoadingSteps] = useState(false);
  const [runsErr, setRunsErr]     = useState(null);
  const [filter, setFilter]       = useState("");
  const pollRef = useRef(null);

  // ── fetch run list ──
  const fetchRuns = useCallback(async () => {
    try {
      const res = await fetch(`${SIDECAR}/api/runs?limit=50`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setRuns(data.runs || []);
      setActive(data.active || []);
      setRunsErr(null);
    } catch (e) {
      setRunsErr(e.message);
    }
  }, []);

  useEffect(() => {
    fetchRuns();
    pollRef.current = setInterval(fetchRuns, 4000);
    return () => clearInterval(pollRef.current);
  }, [fetchRuns]);

  // ── fetch steps for selected run ──
  const fetchSteps = useCallback(async (runId) => {
    setLoadingSteps(true);
    setSteps(null);
    setStepsErr(null);
    try {
      const res = await fetch(`${SIDECAR}/api/runs/${runId}/steps`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSteps(data.steps || []);
      setStepsErr(null);
    } catch (e) {
      setStepsErr(e.message);
    } finally {
      setLoadingSteps(false);
    }
  }, []);

  const handleSelectRun = (runId) => {
    setSelected(runId);
    fetchSteps(runId);
  };

  // Auto-refresh steps for active (running) workflows
  useEffect(() => {
    if (!selectedId) return;
    const isActive = activeRuns.some(r => r.run_id === selectedId);
    if (!isActive) return;
    const id = setInterval(() => fetchSteps(selectedId), 2000);
    return () => clearInterval(id);
  }, [selectedId, activeRuns, fetchSteps]);

  const selectedRun = [...activeRuns, ...runs].find(r => r.run_id === selectedId);

  const filteredRuns = runs.filter(r =>
    !filter || r.workflow.toLowerCase().includes(filter.toLowerCase())
  );

  // Summary totals
  const totalTokens = runs.reduce((s, r) => s + (r.tokens_used || 0), 0);
  const totalCost   = runs.reduce((s, r) => s + (r.cost_usd || 0), 0);

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden", gap: 0 }}>
      {/* ── LEFT: run list ── */}
      <div style={{
        width: 260, flexShrink: 0, display: "flex", flexDirection: "column",
        borderRight: "1px solid var(--border-soft)", overflow: "hidden",
      }}>
        {/* header */}
        <div style={{ padding: "12px 12px 8px", borderBottom: "1px solid var(--border-soft)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
            <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--fg-muted)", textTransform: "uppercase", letterSpacing: 1 }}>
              Workflow Runs
            </span>
            <button
              onClick={fetchRuns}
              title="Refresh"
              style={{
                all: "unset", cursor: "pointer", fontSize: 13,
                color: "var(--fg-muted)", lineHeight: 1,
                transition: "color 0.15s",
              }}
              onMouseEnter={e => e.target.style.color = "var(--accent)"}
              onMouseLeave={e => e.target.style.color = "var(--fg-muted)"}
            >↻</button>
          </div>
          <input
            type="text"
            placeholder="Filter workflows…"
            value={filter}
            onChange={e => setFilter(e.target.value)}
            style={{
              all: "unset", width: "100%", boxSizing: "border-box",
              padding: "5px 8px", background: "var(--bg-inset)",
              border: "1px solid var(--border-soft)", borderRadius: 5,
              fontFamily: "var(--mono)", fontSize: 12, color: "var(--fg)",
            }}
          />
        </div>

        {/* totals bar */}
        <div style={{ padding: "6px 12px", borderBottom: "1px solid var(--border-soft)", display: "flex", gap: 12 }}>
          <span style={{ fontSize: 10, color: "#7fb069", fontFamily: "var(--mono)" }}>
            {totalTokens.toLocaleString()} tok total
          </span>
          <span style={{ fontSize: 10, color: "#e0b84c", fontFamily: "var(--mono)" }}>
            ${totalCost.toFixed(4)} total
          </span>
        </div>

        {/* active badge */}
        {activeRuns.length > 0 && (
          <div style={{ padding: "6px 12px", borderBottom: "1px solid var(--border-soft)" }}>
            <span style={{ fontSize: 10, fontFamily: "var(--mono)", color: "#e0b84c" }}>
              ● {activeRuns.length} active
            </span>
            {activeRuns.map(r => (
              <RunListItem
                key={r.run_id}
                run={r}
                selected={selectedId === r.run_id}
                onClick={() => handleSelectRun(r.run_id)}
              />
            ))}
          </div>
        )}

        {/* run list */}
        <div style={{ flex: 1, overflowY: "auto", padding: "8px 8px" }}>
          {runsErr && <p style={{ color: "#d9534f", fontSize: 11, margin: "8px 4px" }}>⚠ {runsErr}</p>}
          {filteredRuns.length === 0 && !runsErr && (
            <p style={{ color: "var(--fg-muted)", fontSize: 12, margin: "12px 4px" }}>No runs yet.</p>
          )}
          {filteredRuns.map(r => (
            <RunListItem
              key={r.run_id}
              run={r}
              selected={selectedId === r.run_id}
              onClick={() => handleSelectRun(r.run_id)}
            />
          ))}
        </div>
      </div>

      {/* ── RIGHT: step timeline ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* panel header */}
        <div style={{
          padding: "12px 16px 10px",
          borderBottom: "1px solid var(--border-soft)",
          display: "flex", alignItems: "center", gap: 10,
        }}>
          {selectedRun ? (
            <>
              <StatusDot status={selectedRun.status} />
              <span style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 700, color: "var(--fg)" }}>
                {selectedRun.workflow}
              </span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--fg-muted)" }}>
                {fmtTime(selectedRun.started_at)}
                {selectedRun.finished_at && ` → ${fmtTime(selectedRun.finished_at)}`}
                {" · "}{fmtDuration(selectedRun.started_at, selectedRun.finished_at)}
              </span>
              <span style={{
                marginLeft: "auto", fontSize: 10, fontFamily: "var(--mono)",
                color: statusColor(selectedRun.status), textTransform: "uppercase",
              }}>
                {selectedRun.status}
              </span>
              {selectedRun.status === "running" && (
                <button
                  onClick={() => fetchSteps(selectedId)}
                  title="Refresh steps"
                  style={{ all: "unset", cursor: "pointer", fontSize: 13, color: "var(--fg-muted)" }}
                >↻</button>
              )}
            </>
          ) : (
            <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--fg-muted)" }}>
              Select a run to inspect its step timeline
            </span>
          )}
        </div>

        {/* timeline */}
        <div style={{ flex: 1, overflowY: "auto", padding: "16px 16px" }}>
          {!selectedId && (
            <div style={{ color: "var(--fg-muted)", fontSize: 13, marginTop: 40, textAlign: "center" }}>
              <div style={{ fontSize: 28, marginBottom: 10 }}>⏱</div>
              <div>Select a workflow run from the left panel</div>
              <div style={{ fontSize: 11, marginTop: 4 }}>to inspect its agent step timeline</div>
            </div>
          )}

          {loadingSteps && (
            <div style={{ color: "var(--fg-muted)", fontSize: 12, fontFamily: "var(--mono)", marginTop: 20 }}>
              Loading steps…
            </div>
          )}

          {stepsErr && (
            <div style={{ color: "#d9534f", fontSize: 12, fontFamily: "var(--mono)", marginTop: 20 }}>
              ⚠ {stepsErr}
            </div>
          )}

          {steps && steps.length === 0 && (
            <div style={{ color: "var(--fg-muted)", fontSize: 12, marginTop: 20 }}>
              No step data found for this run.
            </div>
          )}

          {steps && steps.length > 0 && (
            <>
              <div style={{
                fontFamily: "var(--mono)", fontSize: 10, color: "var(--fg-muted)",
                marginBottom: 12, textTransform: "uppercase", letterSpacing: 1,
              }}>
                {steps.filter(s => s.step).length} steps
                {" · "}
                {steps.reduce((s, st) => s + (st.tokens || 0), 0).toLocaleString()} tokens
                {" · "}
                ${steps.reduce((s, st) => s + (st.cost_usd || 0), 0).toFixed(4)}
              </div>
              {steps.map((step, i) => (
                <StepNode key={step.task_id} step={step} index={i} isLast={i === steps.length - 1} />
              ))}
            </>
          )}
        </div>
      </div>

      <style>{`
        .json-toggle {
          all: unset;
          cursor: pointer;
          color: var(--fg-muted);
          font-family: var(--mono);
          font-size: 11px;
          padding: 0 2px;
          border-radius: 2px;
          transition: color 0.1s;
        }
        .json-toggle:hover { color: var(--accent); }

        @keyframes pulse-ring {
          0%   { box-shadow: 0 0 0 0 rgba(224,184,76,0.5); }
          70%  { box-shadow: 0 0 0 5px rgba(224,184,76,0); }
          100% { box-shadow: 0 0 0 0 rgba(224,184,76,0); }
        }
      `}</style>
    </div>
  );
}
