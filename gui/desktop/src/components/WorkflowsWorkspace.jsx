import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { get, post, fmtAge } from "../api";
import { pollMs } from "../settings";

/**
 * WorkflowsWorkspace — unified Workflows + Run Visualizer view.
 *
 * Three linked panes sharing one selection model:
 *   1. Definitions rail   — every workflow; launch + filter the runs list.
 *   2. Runs + Events      — runs for the selected workflow (or all), plus a
 *                           collapsible live AG-UI event strip.
 *   3. Step timeline      — decoded LangGraph steps for the selected run,
 *                           with expandable JSON output and token/cost.
 *
 * Flow: pick a workflow → launch it or pick a past run → inspect its steps
 * → cross-reference the live event feed. Replaces the old separate
 * "Workflows" dashboard and "Run Visualizer" panel.
 *
 * Props:
 *   ctx.workflows   — [{ name, description, steps, lastRun, runCount, costAvg }]
 *   ctx.feed        — live AG-UI event array
 *   ctx.refreshKey  — bumps when a run finishes (drives a runs refetch)
 *   ctx.runWorkflow — (name) => launch
 */

// ── helpers ────────────────────────────────────────────────────────────────

const STATUS_COLORS = {
  completed:   "var(--green)",
  failed:      "var(--red)",
  running:     "var(--yellow)",
  interrupted: "#a0a0ff",
  skipped:     "var(--text-dim)",
};
const statusColor = (s) => STATUS_COLORS[s] || "var(--text-dim)";

const shortId = (id) => (id ? String(id).slice(0, 8) : "—");

function fmtClock(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  });
}

function fmtEventTs(ms) {
  if (!ms) return null;
  return new Date(ms).toLocaleTimeString([], {
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  });
}

function fmtDuration(start, end) {
  if (!start || !end) return "";
  const ms = Math.round((end - start) * 1000);
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

function StatusDot({ status, size = 8 }) {
  const color = statusColor(status);
  const pulse = status === "running";
  return (
    <span
      className={pulse ? "wfx-dot wfx-dot-pulse" : "wfx-dot"}
      style={{ width: size, height: size, background: color }}
    />
  );
}

// ── JSON tree (from the Run Visualizer, retokenised) ────────────────────────

function JsonTree({ data, depth = 0 }) {
  const [collapsed, setCollapsed] = useState(depth > 1);

  if (data === null || data === undefined)
    return <span className="wfx-json-null">null</span>;
  if (typeof data === "boolean")
    return <span className="wfx-json-bool">{String(data)}</span>;
  if (typeof data === "number")
    return <span className="wfx-json-num">{data}</span>;
  if (typeof data === "string") {
    const truncated = data.length > 300 ? data.slice(0, 300) + "…" : data;
    return <span className="wfx-json-str">{truncated}</span>;
  }
  if (Array.isArray(data)) {
    if (data.length === 0) return <span className="wfx-json-null">[]</span>;
    return (
      <span>
        <button className="wfx-json-toggle" onClick={() => setCollapsed((c) => !c)}>
          {collapsed ? `▶ [${data.length}]` : "▼ ["}
        </button>
        {!collapsed && (
          <div className="wfx-json-nest">
            {data.map((item, i) => (
              <div key={i}><JsonTree data={item} depth={depth + 1} /></div>
            ))}
            <span className="wfx-json-null">]</span>
          </div>
        )}
      </span>
    );
  }
  if (typeof data === "object") {
    const keys = Object.keys(data);
    if (keys.length === 0) return <span className="wfx-json-null">{"{}"}</span>;
    return (
      <span>
        <button className="wfx-json-toggle" onClick={() => setCollapsed((c) => !c)}>
          {collapsed ? `▶ {${keys.length}}` : "▼ {"}
        </button>
        {!collapsed && (
          <div className="wfx-json-nest">
            {keys.map((k) => (
              <div key={k} style={{ marginBottom: 2 }}>
                <span className="wfx-json-key">{k}</span>
                <span className="wfx-json-null">: </span>
                <JsonTree data={data[k]} depth={depth + 1} />
              </div>
            ))}
            <span className="wfx-json-null">{"}"}</span>
          </div>
        )}
      </span>
    );
  }
  return <span>{String(data)}</span>;
}

// ── step node ───────────────────────────────────────────────────────────────

function StepNode({ step, index, isLast }) {
  const [open, setOpen] = useState(false);
  const hasOutput = step.output !== null && step.output !== undefined;
  const hasTokens = step.tokens && step.tokens > 0;
  const hasCost = step.cost_usd && step.cost_usd > 0;

  return (
    <div className="wfx-step">
      <div className="wfx-step-rail">
        <div className="wfx-step-node" />
        {!isLast && <div className="wfx-step-line" />}
      </div>
      <div className="wfx-step-body">
        <button
          className="wfx-step-card"
          onClick={() => hasOutput && setOpen((o) => !o)}
          style={{ cursor: hasOutput ? "pointer" : "default" }}
        >
          <span className="wfx-step-idx">{index + 1}</span>
          <span className="wfx-step-name">
            {step.step || <span className="wfx-muted">—</span>}
          </span>
          {step.branch_to && (
            <span className="wfx-step-branch">→ {step.branch_to}</span>
          )}
          {hasTokens && (
            <span className="wfx-tok">{step.tokens.toLocaleString()} tok</span>
          )}
          {hasCost && <span className="wfx-cost">${step.cost_usd.toFixed(4)}</span>}
          {hasOutput && <span className="wfx-muted">{open ? "▲" : "▼"}</span>}
        </button>
        {open && hasOutput && (
          <div className="wfx-step-output">
            <JsonTree data={step.output} depth={0} />
          </div>
        )}
      </div>
    </div>
  );
}

// ── run row (middle pane) ───────────────────────────────────────────────────

function RunRow({ run, selected, onClick }) {
  return (
    <button
      className={`wfx-run${selected ? " sel" : ""}`}
      onClick={onClick}
    >
      <div className="wfx-run-top">
        <StatusDot status={run.status} />
        <span className="wfx-run-id">{shortId(run.run_id)}</span>
        <span className="wfx-run-status" style={{ color: statusColor(run.status) }}>
          {run.status}
        </span>
        <span className="wfx-run-dur">
          {fmtDuration(run.started_at, run.finished_at) || "—"}
        </span>
      </div>
      <div className="wfx-run-meta">
        <span>{fmtClock(run.started_at)}</span>
        {run.tokens_used > 0 && (
          <span className="wfx-tok">{run.tokens_used.toLocaleString()} tok</span>
        )}
        {run.cost_usd > 0 && (
          <span className="wfx-cost">${run.cost_usd.toFixed(4)}</span>
        )}
      </div>
    </button>
  );
}

// ── main ─────────────────────────────────────────────────────────────────────

export default function WorkflowsWorkspace({ ctx }) {
  const { workflows = [], feed = [], refreshKey = 0, runWorkflow } = ctx;

  const [runs, setRuns]             = useState([]);
  const [activeRuns, setActiveRuns] = useState([]);
  const [selWf, setSelWf]           = useState(null);   // selected workflow name (filter)
  const [selRun, setSelRun]         = useState(null);   // selected run_id
  const [steps, setSteps]           = useState(null);
  const [stepsErr, setStepsErr]     = useState(null);
  const [loadingSteps, setLoading]  = useState(false);
  const [showEvents, setShowEvents] = useState(true);
  const [launching, setLaunching]   = useState(null);

  const feedRef = useRef(null);

  // ── poll runs (own loop so the timeline stays live even between WS events) ──
  const fetchRuns = useCallback(async () => {
    try {
      const r = await get("/api/runs?limit=50");
      setRuns(r.runs || []);
      setActiveRuns(r.active || []);
    } catch { /* surfaced as empty list */ }
  }, []);

  useEffect(() => {
    fetchRuns();
    const id = setInterval(fetchRuns, pollMs(4000));
    return () => clearInterval(id);
  }, [fetchRuns, refreshKey]);

  // ── steps for the selected run ──
  const fetchSteps = useCallback(async (runId) => {
    setLoading(true); setSteps(null); setStepsErr(null);
    try {
      const r = await get(`/api/runs/${runId}/steps`);
      setSteps(r.steps || []);
    } catch (e) {
      setStepsErr(e.message || "Failed to load steps");
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-refresh steps while the selected run is still active.
  useEffect(() => {
    if (!selRun) return;
    if (!activeRuns.some((r) => r.run_id === selRun)) return;
    const id = setInterval(() => fetchSteps(selRun), pollMs(2000));
    return () => clearInterval(id);
  }, [selRun, activeRuns, fetchSteps]);

  // Auto-scroll the events strip unless the user has a selection pinned.
  useEffect(() => {
    if (!selRun && !selWf && feedRef.current)
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [feed, selRun, selWf]);

  // ── selection handlers ──
  const selectWorkflow = (name) => {
    setSelWf((prev) => (prev === name ? null : name));
    setSelRun(null);
    setSteps(null);
  };
  const selectRun = (run) => {
    setSelRun(run.run_id);
    setSelWf(run.workflow);
    fetchSteps(run.run_id);
  };
  const selectEvent = (e) => {
    if (e.run_id) {
      const run = allRuns.find((r) => r.run_id === e.run_id);
      if (run) { selectRun(run); return; }
      setSelRun(e.run_id);
      setSelWf(e.workflow || null);
      fetchSteps(e.run_id);
    } else if (e.workflow) {
      setSelWf(e.workflow);
    }
  };

  const launch = async (name) => {
    setLaunching(name);
    try {
      if (runWorkflow) await runWorkflow(name);
      else await post(`/api/workflows/${name}/run`);
      setSelWf(name);
      setTimeout(fetchRuns, 600);
    } catch { /* surfaced by next poll */ }
    finally { setLaunching(null); }
  };

  // ── derived ──
  const allRuns = useMemo(() => [...activeRuns, ...runs], [activeRuns, runs]);

  const runsByWf = useMemo(() => {
    const m = {};
    for (const r of runs) (m[r.workflow] ||= []).push(r);
    return m;
  }, [runs]);

  const visibleRuns = useMemo(() => {
    const list = selWf ? runs.filter((r) => r.workflow === selWf) : runs;
    return list;
  }, [runs, selWf]);

  const visibleActive = useMemo(
    () => (selWf ? activeRuns.filter((r) => r.workflow === selWf) : activeRuns),
    [activeRuns, selWf]
  );

  const selectedRun = allRuns.find((r) => r.run_id === selRun);

  const totalTokens = runs.reduce((s, r) => s + (r.tokens_used || 0), 0);
  const totalCost = runs.reduce((s, r) => s + (r.cost_usd || 0), 0);

  const lastEventFor = (name) =>
    [...feed].reverse().find(
      (e) => e.workflow === name &&
        ["RUN_FINISHED", "RUN_ERROR", "RUN_SKIPPED", "RUN_STARTED"].includes(e.type)
    );

  const filteredFeed = selRun
    ? feed.filter((e) => e.run_id === selRun)
    : selWf
    ? feed.filter((e) => e.workflow === selWf)
    : feed;

  // ── render ──
  return (
    <div className="wfx">
      {/* ─────────── LEFT: workflow definitions ─────────── */}
      <aside className="wfx-rail">
        <div className="wfx-rail-head">
          <span className="wfx-eyebrow">Workflows</span>
          {selWf && (
            <button className="wfx-clear" onClick={() => { setSelWf(null); setSelRun(null); setSteps(null); }}>
              clear filter
            </button>
          )}
        </div>
        <div className="wfx-rail-list">
          {workflows.length === 0 && <div className="wfx-empty">No workflows defined</div>}
          {workflows.map((w) => {
            const ev = lastEventFor(w.name);
            const wfRuns = runsByWf[w.name] || [];
            const lastStatus = wfRuns[0]?.status;
            const isSel = selWf === w.name;
            return (
              <div
                key={w.name}
                className={`wfx-wf${isSel ? " sel" : ""}`}
                onClick={() => selectWorkflow(w.name)}
              >
                <div className="wfx-wf-row">
                  <StatusDot status={lastStatus || (ev?.type === "RUN_STARTED" ? "running" : undefined)} />
                  <span className="wfx-wf-name">{w.name}</span>
                  <button
                    className="wfx-launch"
                    disabled={launching === w.name}
                    onClick={(e) => { e.stopPropagation(); launch(w.name); }}
                    title="Run this workflow"
                  >
                    {launching === w.name ? "…" : "▶ run"}
                  </button>
                </div>
                {w.description && <div className="wfx-wf-desc">{w.description}</div>}
                <div className="wfx-wf-meta">
                  <span>{(w.steps?.length ?? 0)} steps</span>
                  {w.runCount > 0 && <span>· {w.runCount} runs</span>}
                  {w.lastRun && <span>· {fmtAge(Math.round(Date.now() / 1000 - w.lastRun))}</span>}
                </div>
              </div>
            );
          })}
        </div>
        <div className="wfx-rail-foot">
          <span className="wfx-tok">{totalTokens.toLocaleString()} tok</span>
          <span className="wfx-cost">${totalCost.toFixed(4)}</span>
        </div>
      </aside>

      {/* ─────────── MIDDLE: runs + events ─────────── */}
      <section className="wfx-mid">
        <div className="wfx-mid-head">
          <span className="wfx-eyebrow">
            {selWf ? `${selWf} · runs` : "All runs"}
          </span>
          <button className="wfx-refresh" onClick={fetchRuns} title="Refresh runs">↻</button>
        </div>

        <div className="wfx-runs">
          {visibleActive.length > 0 && (
            <>
              <div className="wfx-runs-label">● {visibleActive.length} active</div>
              {visibleActive.map((r) => (
                <RunRow key={r.run_id} run={r} selected={selRun === r.run_id} onClick={() => selectRun(r)} />
              ))}
            </>
          )}
          {visibleRuns.length === 0 && visibleActive.length === 0 && (
            <div className="wfx-empty">No runs yet — launch one from the left.</div>
          )}
          {visibleRuns.map((r) => (
            <RunRow key={r.run_id} run={r} selected={selRun === r.run_id} onClick={() => selectRun(r)} />
          ))}
        </div>

        {/* live events strip */}
        <div className={`wfx-events${showEvents ? " open" : ""}`}>
          <button className="wfx-events-head" onClick={() => setShowEvents((s) => !s)}>
            <span className="wfx-eyebrow">Events</span>
            <span className="wfx-events-count">
              {filteredFeed.length}{(selWf || selRun) ? " filtered" : ""}
            </span>
            <span className="wfx-muted">{showEvents ? "▾" : "▸"}</span>
          </button>
          {showEvents && (
            <div className="wfx-feed" ref={feedRef}>
              {filteredFeed.length === 0 && <div className="wfx-empty">No events yet.</div>}
              {filteredFeed.map((e, i) => {
                const ts = fmtEventTs(e.timestamp);
                return (
                  <div className="wfx-feed-line" key={i} onClick={() => selectEvent(e)}>
                    {ts && <span className="wfx-feed-ts">{ts}</span>}
                    <b>{e.type}</b>
                    <span className="wfx-muted"> {e.workflow || ""}{e.step ? ` · ${e.step}` : ""}</span>
                    {e.run_id && <span className="wfx-feed-run"> {shortId(e.run_id)}</span>}
                    {e.type === "RUN_ERROR" && e.error && <span className="wfx-feed-err"> — {e.error}</span>}
                    {e.type === "RUN_SKIPPED" && e.reason && <span className="wfx-feed-skip"> — {e.reason}</span>}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </section>

      {/* ─────────── RIGHT: step timeline ─────────── */}
      <section className="wfx-timeline">
        <div className="wfx-tl-head">
          {selectedRun ? (
            <>
              <StatusDot status={selectedRun.status} />
              <span className="wfx-tl-title">{selectedRun.workflow}</span>
              <span className="wfx-muted">
                {fmtClock(selectedRun.started_at)}
                {selectedRun.finished_at && ` → ${fmtClock(selectedRun.finished_at)}`}
                {fmtDuration(selectedRun.started_at, selectedRun.finished_at) &&
                  ` · ${fmtDuration(selectedRun.started_at, selectedRun.finished_at)}`}
              </span>
              <span className="wfx-tl-status" style={{ color: statusColor(selectedRun.status) }}>
                {selectedRun.status}
              </span>
              {selectedRun.status === "running" && (
                <button className="wfx-refresh" onClick={() => fetchSteps(selRun)} title="Refresh steps">↻</button>
              )}
            </>
          ) : (
            <span className="wfx-muted">Select a run to inspect its step timeline</span>
          )}
        </div>

        <div className="wfx-tl-body">
          {!selRun && (
            <div className="wfx-tl-placeholder">
              <div className="wfx-tl-glyph">⏱</div>
              <div>Pick a run from the middle pane</div>
              <div className="wfx-tl-sub">to walk through its agent steps</div>
            </div>
          )}
          {loadingSteps && <div className="wfx-muted wfx-tl-loading">Loading steps…</div>}
          {stepsErr && <div className="wfx-feed-err wfx-tl-loading">⚠ {stepsErr}</div>}
          {steps && steps.length === 0 && (
            <div className="wfx-muted wfx-tl-loading">No step data found for this run.</div>
          )}
          {steps && steps.length > 0 && (
            <>
              <div className="wfx-tl-summary">
                {steps.filter((s) => s.step).length} steps · {" "}
                {steps.reduce((s, st) => s + (st.tokens || 0), 0).toLocaleString()} tokens · {" "}
                ${steps.reduce((s, st) => s + (st.cost_usd || 0), 0).toFixed(4)}
              </div>
              {steps.map((step, i) => (
                <StepNode key={step.task_id} step={step} index={i} isLast={i === steps.length - 1} />
              ))}
            </>
          )}
        </div>
      </section>
    </div>
  );
}
