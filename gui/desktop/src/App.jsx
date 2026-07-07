// Agentic OS dashboard — Phase 7 (FR-40–44): expandable panels over Phase 3 nav shell
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { get, post, connectAgui, fmtAge, fmtEta, fmtUptime, fmtBytes } from "./api";
import { applyTheme, loadTheme } from "./theme";
import pkg from "../package.json"; // single source of truth for the version (scripts/sync_version.py)
import { getCurrentWindow } from "@tauri-apps/api/window";
import { WebviewWindow } from "@tauri-apps/api/webviewWindow";
import { emit, listen } from "@tauri-apps/api/event";
import "./App.css";
import "@xterm/xterm/css/xterm.css";

// Phase 2 GUI Components (Diagnostics + ErrorBoundary)
import DiagnosticsPanel from "./components/DiagnosticsPanel";
import ErrorBoundary from "./components/ErrorBoundary";
import HubApiExplorer from "./components/HubApiExplorer";
import ProjectCreationDrawer from "./components/ProjectCreationDrawer";  // Phase 11d
import SelfDiagnosticsView from "./components/SelfDiagnosticsView";  // Phase 12 (hidden)
import WorkflowsWorkspace from "./components/WorkflowsWorkspace";
import WebNewsView from "./components/WebNewsView";
import ScriptsExplorer from "./components/ScriptsExplorer";
import ProjectsView from "./components/ProjectsView";  // Phase 13d

// Phase 9 Views
import SettingsView from "./views/SettingsView";

// Adaptive polling hook.
//   ms      — normal interval when service is available
//   fastMs  — recovery interval when service is down (default 2 s)
//   key     — increment to trigger an immediate extra fetch (e.g. on WS event)
function usePoll(path, ms, fastMs = 2000, key = 0) {
  const [data, setData]       = useState(null);
  const [available, setAvail] = useState(true); // optimistic; corrected on first tick

  // When down use fastMs so we detect recovery quickly; when up use ms.
  const interval = available ? ms : fastMs;

  useEffect(() => {
    let alive = true;
    const tick = () =>
      get(path)
        .then((d) => {
          if (!alive) return;
          setData(d);
          setAvail(d?.available !== false);
        })
        .catch(() => {
          if (!alive) return;
          setData({ available: false, error: "sidecar unreachable" });
          setAvail(false);
        });
    tick();                                   // immediate fetch on mount / key change
    const id = setInterval(tick, interval);
    return () => { alive = false; clearInterval(id); };
  }, [path, interval, key]);                  // key change re-runs → immediate tick

  return data;
}

// ---------------------------------------------------------------- FR-28
function SystemHealth({ expanded }) {
  const d = usePoll("/api/panels/system", 2000, 1000);
  if (!d || d.available === false) return <Empty msg="No system data" />;

  if (!expanded) {
    const root = d.disks?.find((x) => x.mount === "/") || d.disks?.[0];
    return (
      <>
        <dl className="kv">
          <dt>CPU</dt><dd>{d.cpu_percent}%</dd>
        </dl>
        <div className="bar"><i style={{ width: `${d.cpu_percent}%` }} /></div>
        <dl className="kv">
          <dt>RAM</dt><dd>{d.ram.used_gb} / {d.ram.total_gb} GB ({d.ram.percent}%)</dd>
        </dl>
        <div className="bar"><i style={{ width: `${d.ram.percent}%` }} /></div>
        <dl className="kv">
          <dt>Disk {root?.mount}</dt><dd>{root?.used_gb} GB used · {root?.free_gb} GB free</dd>
          <dt>Network</dt><dd>↓ {fmtBytes(d.network.bytes_in)} · ↑ {fmtBytes(d.network.bytes_out)}</dd>
          <dt>Uptime</dt><dd>{fmtUptime(d.uptime_s)}</dd>
          <dt>Load</dt><dd>{d.load_avg.join(" / ")}</dd>
        </dl>
        <table style={{ marginTop: 8 }}>
          <thead><tr><th>Top CPU</th><th>%</th><th>Top Mem</th><th>%</th></tr></thead>
          <tbody>
            {[0, 1, 2].map((i) => (
              <tr key={i}>
                <td>{d.top_cpu[i]?.name}</td><td>{d.top_cpu[i]?.cpu_percent}</td>
                <td>{d.top_memory[i]?.name}</td><td>{d.top_memory[i]?.memory_percent}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </>
    );
  }

  // ---- Expanded view ----
  const cores = d.cpu_per_core || [];
  return (
    <div className="exp-grid-2">
      <div className="exp-col">
        <div className="exp-section-title">CPU</div>
        <dl className="kv">
          <dt>Overall</dt><dd>{d.cpu_percent}%</dd>
          <dt>Load avg</dt><dd>{d.load_avg.join(" / ")}</dd>
          <dt>Uptime</dt><dd>{fmtUptime(d.uptime_s)}</dd>
        </dl>
        {cores.length > 0 && (
          <>
            <div className="exp-section-title" style={{ marginTop: 14 }}>Per Core</div>
            <div className="core-bars">
              {cores.map((pct, i) => (
                <div className="core-bar-wrap" key={i} title={`Core ${i}: ${pct}%`}>
                  <div className="core-bar" style={{ height: `${Math.max(pct, 2)}%` }} />
                  <span className="core-label">{i}</span>
                </div>
              ))}
            </div>
          </>
        )}

        <div className="exp-section-title" style={{ marginTop: 18 }}>RAM</div>
        <dl className="kv">
          <dt>Used</dt><dd>{d.ram.used_gb} GB</dd>
          <dt>Total</dt><dd>{d.ram.total_gb} GB</dd>
          <dt>Pressure</dt><dd>{d.ram.percent}%</dd>
        </dl>
        <div className="bar" style={{ marginTop: 6, height: 8 }}>
          <i style={{ width: `${d.ram.percent}%` }} />
        </div>

        <div className="exp-section-title" style={{ marginTop: 18 }}>Network</div>
        <dl className="kv">
          <dt>Received</dt><dd>{fmtBytes(d.network.bytes_in)}</dd>
          <dt>Sent</dt><dd>{fmtBytes(d.network.bytes_out)}</dd>
        </dl>

        <div className="exp-section-title" style={{ marginTop: 18 }}>Volumes</div>
        <table>
          <thead><tr><th>Mount</th><th>Used</th><th>Free</th><th>%</th></tr></thead>
          <tbody>
            {d.disks.map((disk) => (
              <tr key={disk.mount}>
                <td>{disk.mount}</td>
                <td>{disk.used_gb} GB</td>
                <td>{disk.free_gb} GB</td>
                <td>
                  <div className="bar inline-bar">
                    <i style={{ width: `${disk.percent}%` }} />
                  </div>
                  <span style={{ marginLeft: 6 }}>{disk.percent}%</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="exp-col">
        <div className="exp-section-title">Top Processes — CPU</div>
        <table>
          <thead><tr><th>PID</th><th>Name</th><th>CPU %</th></tr></thead>
          <tbody>
            {d.top_cpu.map((p) => (
              <tr key={p.pid}>
                <td style={{ color: "var(--text-dim)" }}>{p.pid}</td>
                <td>{p.name}</td>
                <td>{p.cpu_percent}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="exp-section-title" style={{ marginTop: 18 }}>Top Processes — Memory</div>
        <table>
          <thead><tr><th>PID</th><th>Name</th><th>Mem %</th></tr></thead>
          <tbody>
            {d.top_memory.map((p) => (
              <tr key={p.pid}>
                <td style={{ color: "var(--text-dim)" }}>{p.pid}</td>
                <td>{p.name}</td>
                <td>{p.memory_percent}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- FR-29
function AgentActivity({ refreshKey, expanded }) {
  // Poll every 10 s normally; drop to 2 s when sidecar is unreachable so we
  // recover quickly. refreshKey causes an immediate extra fetch on WS events.
  const d = usePoll("/api/panels/activity", 10_000, 2_000, refreshKey);
  const [allRuns, setAllRuns] = useState(null);

  useEffect(() => {
    if (!expanded) return;
    get("/api/runs?limit=50")
      .then((r) => setAllRuns(r.runs))
      .catch(() => {});
  }, [expanded, refreshKey]);

  if (!d || d.available === false) return <Empty msg="No activity data — sidecar unreachable" />;

  // Numbers can be absent in a partial/degraded payload; coerce defensively so
  // a missing field never crashes the panel (.toFixed on undefined throws).
  const costToday = Number(d.cost_today_usd ?? 0);
  const costMonth = Number(d.cost_month_usd ?? 0);
  const tokensTotal = Number(d.tokens_total ?? 0);
  const recentRuns = d.recent_runs ?? [];

  if (!expanded) {
    return (
      <>
        <dl className="kv">
          <dt>Cost today</dt><dd>${costToday.toFixed(4)}</dd>
          <dt>Cost this month</dt><dd>${costMonth.toFixed(4)}</dd>
          <dt>Runs today</dt><dd>{d.runs_today ?? 0}</dd>
          <dt>Total tokens</dt><dd>{tokensTotal.toLocaleString()}</dd>
          <dt>Success rate</dt><dd>{d.success_rate ?? "—"}%</dd>
          <dt>Avg duration</dt><dd>{d.avg_duration_s ?? "—"}s</dd>
        </dl>
        <table style={{ marginTop: 8 }}>
          <thead><tr><th>Workflow</th><th>Status</th><th>Cost</th></tr></thead>
          <tbody>
            {recentRuns.slice(0, 6).map((r) => (
              <tr key={r.run_id}>
                <td>{r.workflow}</td>
                <td>
                  <span className={`dot ${r.status === "completed" ? "on" : r.status === "running" ? "warn" : "err"}`} />
                  {r.status}
                </td>
                <td>${(r.cost_usd || 0).toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </>
    );
  }

  // ---- Expanded view ----
  const runs = allRuns || recentRuns;
  return (
    <div className="exp-grid-2">
      <div className="exp-col">
        <div className="exp-section-title">Summary</div>
        <dl className="kv">
          <dt>Cost today</dt><dd>${costToday.toFixed(4)}</dd>
          <dt>Cost this month</dt><dd>${costMonth.toFixed(4)}</dd>
          <dt>Runs today</dt><dd>{d.runs_today ?? 0}</dd>
          <dt>Total tokens</dt><dd>{tokensTotal.toLocaleString()}</dd>
          <dt>Success rate</dt><dd>{d.success_rate ?? "—"}%</dd>
          <dt>Avg duration</dt><dd>{d.avg_duration_s ?? "—"}s</dd>
        </dl>

        {/* Cost breakdown by workflow */}
        {runs.length > 0 && (() => {
          const bywf = {};
          for (const r of runs) {
            bywf[r.workflow] = (bywf[r.workflow] || 0) + (r.cost_usd || 0);
          }
          const sorted = Object.entries(bywf).sort((a, b) => b[1] - a[1]);
          return (
            <>
              <div className="exp-section-title" style={{ marginTop: 18 }}>Cost by Workflow</div>
              <table>
                <thead><tr><th>Workflow</th><th>Total Cost</th></tr></thead>
                <tbody>
                  {sorted.map(([wf, cost]) => (
                    <tr key={wf}>
                      <td>{wf}</td>
                      <td>${cost.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          );
        })()}
      </div>

      <div className="exp-col">
        <div className="exp-section-title">Run History ({runs.length})</div>
        <div className="exp-scroll">
          <table>
            <thead>
              <tr><th>Workflow</th><th>Status</th><th>Duration</th><th>Cost</th><th>Tokens</th></tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id}>
                  <td>{r.workflow}</td>
                  <td>
                    <span className={`dot ${r.status === "completed" ? "on" : r.status === "running" ? "warn" : "err"}`} />
                    {r.status}
                  </td>
                  <td>
                    {r.finished_at && r.started_at
                      ? `${Math.round(r.finished_at - r.started_at)}s`
                      : "—"}
                  </td>
                  <td>${(r.cost_usd || 0).toFixed(4)}</td>
                  <td>{(r.tokens_used || 0).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- FR-30
function KenoTelemetry({ expanded }) {
  const d = usePoll("/api/panels/keno", 30_000, 3_000);
  if (!d) return <Empty msg="Loading…" />;
  if (!d.available) return <Empty msg={`Keno DB unavailable — ${d.error}`} />;

  if (!expanded) {
    return (
      <dl className="kv">
        <dt>Total draws</dt><dd>{d.total_draws.toLocaleString()}</dd>
        <dt>Latest draw</dt><dd>#{d.latest_draw}</dd>
        <dt>Last sync</dt><dd>{fmtAge(d.last_sync_age_s)}</dd>
        <dt>Next sync</dt><dd>{fmtEta(d.next_sync_eta_s)}</dd>
        <dt>Imported last run</dt><dd>{d.imported_last_run}</dd>
        <dt>Gaps remaining</dt><dd>{d.gaps_remaining}</dd>
        <dt>Coverage</dt><dd>{d.coverage_percent}%</dd>
      </dl>
    );
  }

  // ---- Expanded view ----
  const cov = d.coverage_percent ?? 0;
  return (
    <div className="exp-grid-2">
      <div className="exp-col">
        <div className="exp-section-title">Draw Database</div>
        <dl className="kv">
          <dt>Total draws</dt><dd>{d.total_draws.toLocaleString()}</dd>
          <dt>Latest draw</dt><dd>#{d.latest_draw}</dd>
          <dt>Gaps remaining</dt><dd>{d.gaps_remaining}</dd>
        </dl>

        <div className="exp-section-title" style={{ marginTop: 18 }}>Coverage</div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
          <div className="bar" style={{ flex: 1, height: 12, margin: 0 }}>
            <i style={{ width: `${cov}%`, background: cov > 95 ? "var(--green)" : "var(--accent)" }} />
          </div>
          <span style={{ fontFamily: "var(--mono)", fontSize: 13, minWidth: 46 }}>{cov}%</span>
        </div>
        <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
          {d.gaps_remaining === 0
            ? "✓ No gaps — full coverage"
            : `${d.gaps_remaining} draw${d.gaps_remaining !== 1 ? "s" : ""} missing from span`}
        </div>
      </div>

      <div className="exp-col">
        <div className="exp-section-title">Sync Status</div>
        <dl className="kv">
          <dt>Last sync</dt><dd>{fmtAge(d.last_sync_age_s)}</dd>
          <dt>Next sync</dt><dd>{fmtEta(d.next_sync_eta_s)}</dd>
          <dt>Imported last run</dt><dd>{d.imported_last_run}</dd>
          <dt>Schedule</dt><dd>every 2 hours</dd>
        </dl>

        {d.last_sync_age_s != null && (
          <>
            <div className="exp-section-title" style={{ marginTop: 18 }}>Sync Window</div>
            <div style={{ fontSize: 11, color: "var(--text-dim)", lineHeight: 1.7 }}>
              <div>Elapsed: {fmtAge(d.last_sync_age_s)}</div>
              <div>Remaining: {fmtEta(d.next_sync_eta_s)}</div>
              <div className="bar" style={{ marginTop: 8, height: 8 }}>
                <i style={{
                  width: `${Math.min(100, Math.round(100 * d.last_sync_age_s / 7200))}%`,
                  background: "var(--text-dim)"
                }} />
              </div>
              <div style={{ marginTop: 4 }}>
                {Math.min(100, Math.round(100 * d.last_sync_age_s / 7200))}% through 2-hour window
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- FR-31
function HubPanel({ expanded }) {
  const d = usePoll("/api/panels/hub", 5_000, 2_000);
  const m = usePoll("/api/panels/hub/manifests", 60_000, 5_000);
  const [busy, setBusy] = useState(null);
  const [expandedManifest, setExpandedManifest] = useState(null);
  const lastStartAttempt = useRef(0);

  // Auto-start hub on every poll that finds it offline, rate-limited to once
  // per 30 s so we don't spam the endpoint. This fires immediately on first
  // offline poll (lastStartAttempt starts at 0) and self-resets — no stuck
  // "prevAvailable=false" state to worry about if a start attempt silently fails.
  useEffect(() => {
    if (!d || d.available) return;
    const now = Date.now();
    if (now - lastStartAttempt.current > 30_000) {
      lastStartAttempt.current = now;
      post("/api/panels/hub/start").catch(() => {});
    }
  }, [d]);

  const retryStart = () => {
    lastStartAttempt.current = 0; // reset cooldown so next poll fires immediately
    post("/api/panels/hub/start").catch(() => {});
  };

  if (!d) return <Empty msg="Loading…" />;
  if (!d.available) return (
    <div className="hub-offline">
      <span className="hub-offline-status">
        <span className="dot warn hub-pulse" />
        Hub offline — reconnecting…
      </span>
      <button className="btn" onClick={retryStart}>↻ Retry</button>
    </div>
  );

  const manifests = m?.manifests || {};
  const act = async (id, action) => {
    setBusy(id);
    try { await post(`/api/panels/hub/${id}/${action}`); } catch { /* surfaced by next poll */ }
    setBusy(null);
  };
  const toggleManifest = (id) =>
    setExpandedManifest((prev) => (prev === id ? null : id));

  if (!expanded) {
    return (
      <>
        <dl className="kv" style={{ marginBottom: 8 }}>
          <dt>Hub health</dt>
          <dd><span className="dot on" />OK · {d.response_ms}ms</dd>
        </dl>
        <table>
          <thead><tr><th>App</th><th>Port</th><th>Status</th><th>Agent</th><th></th></tr></thead>
          <tbody>
            {d.apps.map((a) => {
              const manifest = manifests[a.id];
              const hasAgent = !!(manifest && (manifest.tools?.length || manifest.api_base));
              const toolCount = manifest?.tools?.length || 0;
              return (
                <>
                  <tr key={a.id}>
                    <td>{a.name}</td>
                    <td>{a.port || "—"}</td>
                    <td><span className={`dot ${a.running ? "on" : "off"}`} />{a.running ? "running" : "stopped"}</td>
                    <td style={{ textAlign: "center" }}>
                      {hasAgent ? (
                        <button
                          className="btn"
                          title={`${toolCount} agent tool${toolCount !== 1 ? "s" : ""} — click to expand`}
                          style={{ fontSize: "0.7rem", padding: "1px 5px" }}
                          onClick={() => toggleManifest(a.id)}
                        >
                          ✦ {toolCount}
                        </button>
                      ) : "—"}
                    </td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {a.running ? (
                        <>
                          <button className="btn" disabled={busy === a.id} onClick={() => act(a.id, "restart")}>↻</button>
                          <button className="btn deny" disabled={busy === a.id} onClick={() => act(a.id, "stop")}>■</button>
                        </>
                      ) : (
                        <button className="btn approve" disabled={busy === a.id} onClick={() => act(a.id, "start")}>▶</button>
                      )}
                    </td>
                  </tr>
                  {expandedManifest === a.id && hasAgent && (
                    <tr key={`${a.id}-manifest`}>
                      <td colSpan={5} style={{ background: "var(--bg2)", padding: "6px 10px", fontSize: "0.72rem", fontFamily: "monospace" }}>
                        <b>api_base:</b> {manifest.api_base || "—"}<br />
                        {manifest.tools?.map((t, i) => (
                          <span key={i} style={{ marginRight: 12 }}>
                            <b>{t.name}</b> {t.method || "GET"} {t.path}
                            {t.description ? <span style={{ color: "var(--muted)" }}> — {t.description}</span> : null}
                            <br />
                          </span>
                        ))}
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </>
    );
  }

  // ---- Expanded view ----
  return (
    <div className="exp-grid-2">
      <div className="exp-col">
        <div className="exp-section-title">Hub Status</div>
        <dl className="kv" style={{ marginBottom: 14 }}>
          <dt>Health</dt><dd><span className="dot on" />OK</dd>
          <dt>Response time</dt><dd>{d.response_ms}ms</dd>
          <dt>Apps registered</dt><dd>{d.apps.length}</dd>
          <dt>Running</dt><dd>{d.apps.filter((a) => a.running).length}</dd>
          <dt>Stopped</dt><dd>{d.apps.filter((a) => !a.running).length}</dd>
        </dl>

        <div className="exp-section-title">Apps</div>
        <table>
          <thead><tr><th>Name</th><th>Port</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {d.apps.map((a) => (
              <tr key={a.id}>
                <td>{a.name}</td>
                <td>{a.port || "—"}</td>
                <td><span className={`dot ${a.running ? "on" : "off"}`} />{a.running ? "running" : "stopped"}</td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  {a.running ? (
                    <>
                      <button className="btn" disabled={busy === a.id} onClick={() => act(a.id, "restart")}>↻</button>
                      <button className="btn deny" disabled={busy === a.id} onClick={() => act(a.id, "stop")}>■</button>
                    </>
                  ) : (
                    <button className="btn approve" disabled={busy === a.id} onClick={() => act(a.id, "start")}>▶</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="exp-col">
        <div className="exp-section-title">Agent Capability Manifests</div>
        <div className="exp-scroll">
          {d.apps.map((a) => {
            const manifest = manifests[a.id];
            const hasAgent = !!(manifest && (manifest.tools?.length || manifest.api_base));
            return (
              <div key={a.id} className="manifest-block">
                <div className="manifest-title">
                  {a.name}
                  {hasAgent
                    ? <span className="manifest-badge">✦ {manifest.tools?.length || 0} tools</span>
                    : <span className="manifest-badge muted">no agent block</span>}
                </div>
                {hasAgent && (
                  <div className="manifest-body">
                    {manifest.api_base && <div><b>api_base:</b> {manifest.api_base}</div>}
                    {manifest.tools?.map((t, i) => (
                      <div key={i} className="manifest-tool">
                        <b>{t.name}</b>
                        <span style={{ color: "var(--text-dim)" }}> {t.method || "GET"} {t.path}</span>
                        {t.description && <div style={{ color: "var(--text-dim)", marginTop: 1 }}>{t.description}</div>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- FR-32
function ApprovalQueue({ approvals, onDecide, expanded }) {
  if (!approvals.length) return <Empty msg="No pending approvals" />;

  if (!expanded) {
    return approvals.map((a) => (
      <div className="approval" key={a.approval_id}>
        <b>{a.workflow}</b> · step <code>{a.step}</code>
        <div className="q">{a.question}</div>
        <button className="btn approve" onClick={() => onDecide(a.approval_id, "approve")}>Allow</button>
        <button className="btn deny" onClick={() => onDecide(a.approval_id, "deny")}>Deny</button>
      </div>
    ));
  }

  // ---- Expanded view ----
  return (
    <div>
      <div className="exp-section-title">
        {approvals.length} pending approval{approvals.length !== 1 ? "s" : ""}
      </div>
      {approvals.map((a) => (
        <div className="approval approval-expanded" key={a.approval_id}>
          <div className="approval-meta">
            <span className="approval-workflow">{a.workflow}</span>
            <span style={{ color: "var(--text-dim)", marginLeft: 8 }}>
              step <code>{a.step}</code>
            </span>
          </div>
          <div className="approval-question-exp">{a.question}</div>
          <div className="approval-actions-exp">
            <button className="btn approve btn-lg" onClick={() => onDecide(a.approval_id, "approve")}>
              ✓ Allow
            </button>
            <button className="btn deny btn-lg" onClick={() => onDecide(a.approval_id, "deny")}>
              ✕ Deny
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- FR-33
function TerminalStrip({ expanded }) {
  // Condensed: read-only strip showing the last 15 lines of agent shell output
  const d = usePoll("/api/panels/terminal", 3_000, 2_000);

  // Expanded: full interactive xterm.js terminal over a PTY WebSocket
  const containerRef = useRef(null);
  const xtermRef    = useRef(null);
  const wsRef       = useRef(null);

  useEffect(() => {
    if (!expanded) return;

    let cancelled = false;
    let resizeObserver;

    (async () => {
      // Dynamic import keeps xterm out of the initial bundle
      const { Terminal }  = await import("@xterm/xterm");
      const { FitAddon }  = await import("@xterm/addon-fit");

      if (cancelled || !containerRef.current) return;

      const term = new Terminal({
        theme: {
          background:          "#111110",
          foreground:          "#e8e6df",
          cursor:              "#d97b4f",
          cursorAccent:        "#111110",
          selectionBackground: "rgba(217,123,79,0.25)",
          black:    "#1b1b19", red:     "#d9534f",
          green:    "#7fb069", yellow:  "#e0b84c",
          blue:     "#5b87c5", magenta: "#b07fc5",
          cyan:     "#5bbcba", white:   "#e8e6df",
          brightBlack:   "#555550", brightRed:     "#e06c6b",
          brightGreen:   "#9fce85", brightYellow:  "#f0cc6e",
          brightBlue:    "#7aa0d8", brightMagenta: "#c99ad8",
          brightCyan:    "#7dd4d2", brightWhite:   "#ffffff",
        },
        fontFamily:  '"SF Mono", ui-monospace, Menlo, monospace',
        fontSize:    13,
        lineHeight:  1.4,
        cursorBlink: true,
        cursorStyle: "block",
        scrollback:  5000,
      });

      const fitAddon = new FitAddon();
      term.loadAddon(fitAddon);
      term.open(containerRef.current);
      fitAddon.fit();
      xtermRef.current = term;

      // Connect to PTY WebSocket
      const ws = new WebSocket("ws://localhost:5130/ws/terminal");
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = () => {
        const dims = fitAddon.proposeDimensions();
        if (dims) {
          ws.send(JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows }));
        }
      };

      ws.onmessage = (e) => {
        if (e.data instanceof ArrayBuffer) {
          term.write(new Uint8Array(e.data));
        } else {
          term.write(e.data);
        }
      };

      ws.onclose = () => {
        if (!cancelled) {
          term.write("\r\n\x1b[2m[terminal session ended — collapse and re-expand to reconnect]\x1b[0m\r\n");
        }
      };

      // Keystrokes → PTY
      term.onData((data) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(new TextEncoder().encode(data));
        }
      });

      // Resize terminal when the panel body resizes
      resizeObserver = new ResizeObserver(() => {
        try {
          fitAddon.fit();
          const dims = fitAddon.proposeDimensions();
          if (dims && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows }));
          }
        } catch (_) {}
      });
      resizeObserver.observe(containerRef.current);
    })();

    return () => {
      cancelled = true;
      resizeObserver?.disconnect();
      wsRef.current?.close();
      wsRef.current = null;
      xtermRef.current?.dispose();
      xtermRef.current = null;
    };
  }, [expanded]);

  if (!expanded) {
    const lines = d?.lines?.length ? d.lines.join("\n") : (d?.note || "…");
    return <div className="term">{lines}</div>;
  }

  return <div ref={containerRef} className="term-xterm" />;
}

const Empty = ({ msg }) => <div className="empty">{msg}</div>;

// ================================================================ Panel (FR-40/41)
const EXPAND_KEY = "agentic-os.expandedPanel";

const Panel = ({ title, children, expanded, onExpand }) => {
  // FR-40: Escape key collapses
  useEffect(() => {
    if (!expanded) return;
    const handler = (e) => { if (e.key === "Escape") onExpand(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [expanded, onExpand]);

  return (
    <section className={`panel${expanded ? " expanded" : ""}`}>
      <div className="panel-head" onDoubleClick={onExpand}>
        {title}
        <span
          className="panel-expand-icon"
          title={expanded ? "Collapse (Esc)" : "Expand (double-click)"}
          onClick={(e) => { e.stopPropagation(); onExpand(); }}
        >
          {expanded ? "✕" : "⤢"}
        </span>
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
};

// ================================================================ views (FR-38)
// Shared panel-grid expand/collapse logic (FR-40/41/44). Each multi-panel
// dashboard calls this with its own storage key so its "expanded panel"
// persists independently.
function usePanelGrid(storageKey) {
  const gridRef = useRef(null);
  const [expandedPanel, setExpandedPanel] = useState(
    () => localStorage.getItem(storageKey) || null
  );
  const toggle = useCallback((title) => {
    setExpandedPanel((prev) => {
      const next = prev === title ? null : title;
      if (next) {
        localStorage.setItem(storageKey, next);
        // scroll grid to top so the absolute overlay starts from the visible area
        if (gridRef.current) gridRef.current.scrollTop = 0;
      } else {
        localStorage.removeItem(storageKey);
      }
      return next;
    });
  }, [storageKey]);
  return { gridRef, expandedPanel, toggle };
}

const mkPanel = (title, content, expandedPanel, toggle) => (
  <Panel
    key={title}
    title={title}
    expanded={expandedPanel === title}
    onExpand={() => toggle(title)}
  >
    {content}
  </Panel>
);

// FR-47: SysOps — the system-operations grid (formerly "Dashboard").
function SysOpsView({ ctx }) {
  const { approvals, refreshKey, decide } = ctx;
  const { gridRef, expandedPanel, toggle } = usePanelGrid(EXPAND_KEY);
  const exp = expandedPanel;
  const P = (title, content) => mkPanel(title, content, expandedPanel, toggle);

  // Phase 11d: project-creation drawer, triggered from the Codehome Hub panel.
  const [showNewProject, setShowNewProject] = useState(false);

  // Codehome Hub panel body with a "New Project" trigger pinned to the top so
  // it's reachable whether the hub is online, offline, or the panel is expanded.
  const codehomeHub = (
    <>
      <button
        className="btn"
        onClick={(e) => { e.stopPropagation(); setShowNewProject(true); }}
        style={{
          marginBottom: 8, background: "var(--accent)", color: "#1b1b19",
          border: "none", borderRadius: 4, padding: "5px 11px",
          fontSize: "0.76rem", fontWeight: 600, cursor: "pointer",
        }}
      >
        ＋ New Project
      </button>
      <HubPanel expanded={exp === "Codehome Hub"} />
    </>
  );

  return (
    <div ref={gridRef} className={`grid${exp ? " has-expanded" : ""}`}>
      {P("System Health", <SystemHealth expanded={exp === "System Health"} />)}
      {P("Agent Activity", <AgentActivity refreshKey={refreshKey} expanded={exp === "Agent Activity"} />)}
      {P("Keno Telemetry", <KenoTelemetry expanded={exp === "Keno Telemetry"} />)}
      {P("Codehome Hub", codehomeHub)}
      {P("Approval Queue", <ApprovalQueue approvals={approvals} onDecide={decide} expanded={exp === "Approval Queue"} />)}
      {P("Terminal", <TerminalStrip expanded={exp === "Terminal"} />)}
      <ProjectCreationDrawer
        open={showNewProject}
        onClose={() => setShowNewProject(false)}
      />
    </div>
  );
}

// FR-48: combined "Workflows" dashboard — Workflows + Events as linked panels.
const WF_EXPAND_KEY = "agentic-os.wfExpandedPanel";
const shortId = (id) => (id ? String(id).slice(0, 8) : "—");
const runDot = (s) =>
  `dot ${s === "completed" ? "on" : s === "running" ? "warn" : s === "error" ? "err" : "off"}`;

// Workflows panel: definitions, each row expandable to its recent runs (FR-48).
function WorkflowsPanel({
  workflows, runs, feed, runWorkflow,
  selWf, selRun, openWf, onSelectWorkflow, onSelectRun, rowRefs,
}) {
  const lastRunEvent = (name) =>
    [...feed].reverse().find(
      (e) => e.workflow === name &&
        (e.type === "RUN_FINISHED" || e.type === "RUN_ERROR" || e.type === "RUN_STARTED")
    );
  const runsByWf = useMemo(() => {
    const m = {};
    for (const r of runs) (m[r.workflow] ||= []).push(r);
    return m;
  }, [runs]);

  if (!workflows.length) return <Empty msg="No workflows defined" />;
  return (
    <table className="linked-table">
      <thead><tr><th>Workflow</th><th>Last event</th><th></th></tr></thead>
      <tbody>
        {workflows.map((w) => {
          const ev = lastRunEvent(w.name);
          const wfRuns = runsByWf[w.name] || [];
          const open = openWf === w.name;
          return (
            <Fragment key={w.name}>
              <tr
                ref={(el) => { if (rowRefs) rowRefs.current[w.name] = el; }}
                className={`linked-row${selWf === w.name && !selRun ? " selected" : ""}`}
                onClick={() => onSelectWorkflow(w.name)}
              >
                <td><span className="disclosure">{open ? "▾" : "▸"}</span>{w.name}</td>
                <td>{ev ? ev.type : "—"}</td>
                <td style={{ textAlign: "right" }}>
                  <button
                    className="run-btn"
                    onClick={(e) => { e.stopPropagation(); runWorkflow(w.name); }}
                  >run</button>
                </td>
              </tr>
              {open && wfRuns.length === 0 && (
                <tr className="run-subrow">
                  <td colSpan={3} style={{ color: "var(--text-dim)", paddingLeft: 22 }}>no recorded runs</td>
                </tr>
              )}
              {open && wfRuns.map((r) => (
                <tr
                  key={r.run_id}
                  className={`run-subrow${selRun === r.run_id ? " selected" : ""}`}
                  onClick={(e) => { e.stopPropagation(); onSelectRun(r); }}
                >
                  <td style={{ paddingLeft: 22 }}>
                    <span className={runDot(r.status)} />{shortId(r.run_id)}
                  </td>
                  <td>{r.status}</td>
                  <td style={{ textAlign: "right", color: "var(--text-dim)" }}>
                    {r.finished_at && r.started_at
                      ? `${Math.round(r.finished_at - r.started_at)}s`
                      : "—"}
                  </td>
                </tr>
              ))}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}

// Format a millisecond epoch timestamp as HH:MM:SS
const fmtTs = (ms) => {
  if (!ms) return null;
  const d = new Date(ms);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
};

// Events panel: the live AG-UI feed, highlight-linked to the selection (FR-49).
function LinkedEventsPanel({ feed, selWf, selRun, onSelectEvent }) {
  const ref = useRef(null);
  const hasSel = !!(selWf || selRun);
  useEffect(() => {
    if (!hasSel) ref.current?.scrollTo(0, ref.current.scrollHeight);
  }, [feed, hasSel]);
  if (!feed.length) return <Empty msg="No events yet — run a workflow" />;
  const isHi = (e) => (selRun ? e.run_id === selRun : selWf ? e.workflow === selWf : true);
  return (
    <div className="feed-scroll linked-feed" ref={ref}>
      {feed.map((e, i) => {
        const cls = hasSel ? (isHi(e) ? " hi" : " dim") : "";
        const ts = fmtTs(e.timestamp);
        return (
          <div className={`feed-line linkable${cls}`} key={i} onClick={() => onSelectEvent(e)}>
            {ts && <span className="feed-ts">{ts}</span>}
            <b>{e.type}</b> {e.workflow || ""}{e.step ? ` · ${e.step}` : ""}
            {e.run_id ? <span className="feed-run"> {shortId(e.run_id)}</span> : null}
            {e.type === 'RUN_ERROR' && e.error
              ? <span className="feed-error"> — {e.error}</span>
              : null}
            {e.type === 'RUN_SKIPPED' && e.reason
              ? <span className="feed-skipped"> — {e.reason}</span>
              : null}
          </div>
        );
      })}
    </div>
  );
}

function WorkflowsDashboard({ ctx }) {
  const { workflows, runWorkflow, feed, refreshKey } = ctx;
  const { gridRef, expandedPanel, toggle } = usePanelGrid(WF_EXPAND_KEY);
  const [runs, setRuns] = useState([]);
  const [selWf, setSelWf] = useState(null);
  const [selRun, setSelRun] = useState(null);
  const [openWf, setOpenWf] = useState(null);
  const rowRefs = useRef({});

  // FR-48: recent runs from /api/runs; refresh when a run finishes (refreshKey).
  useEffect(() => {
    get("/api/runs?limit=50").then((r) => setRuns(r.runs || [])).catch(() => {});
  }, [refreshKey]);

  // FR-49: shared selection model.
  const onSelectWorkflow = (name) => {
    setSelWf(name);
    setSelRun(null);
    setOpenWf((o) => (o === name ? null : name));
  };
  const onSelectRun = (r) => { setSelWf(r.workflow); setSelRun(r.run_id); setOpenWf(r.workflow); };
  const onSelectEvent = (e) => {
    if (e.run_id) { setSelWf(e.workflow || null); setSelRun(e.run_id); }
    else if (e.workflow) { setSelWf(e.workflow); setSelRun(null); }
    if (e.workflow) {
      setOpenWf(e.workflow);
      requestAnimationFrame(() =>
        rowRefs.current[e.workflow]?.scrollIntoView({ block: "nearest" })
      );
    }
  };
  const clearSel = () => { setSelWf(null); setSelRun(null); };

  const exp = expandedPanel;
  const selLabel = selRun ? `run ${shortId(selRun)}` : selWf || null;

  const wfPanel = (
    <WorkflowsPanel
      workflows={workflows} runs={runs} feed={feed} runWorkflow={runWorkflow}
      selWf={selWf} selRun={selRun} openWf={openWf}
      onSelectWorkflow={onSelectWorkflow} onSelectRun={onSelectRun} rowRefs={rowRefs}
    />
  );
  const evPanel = (
    <LinkedEventsPanel feed={feed} selWf={selWf} selRun={selRun} onSelectEvent={onSelectEvent} />
  );

  return (
    <>
      {selLabel && (
        <div className="sel-bar">
          <span>selection: <b>{selLabel}</b></span>
          <button className="btn" onClick={clearSel}>clear</button>
        </div>
      )}
      <div ref={gridRef} className={`grid wf-grid${exp ? " has-expanded" : ""}`}>
        {mkPanel("Workflows", wfPanel, expandedPanel, toggle)}
        {mkPanel("Events", evPanel, expandedPanel, toggle)}
      </div>
    </>
  );
}

// FR-50: shared "Coming Soon" stub for placeholder dashboards.
function ComingSoon({ dashboard }) {
  return (
    <div className="view-pad coming-soon">
      <div className="cs-card">
        <div className="cs-title">{dashboard.label}</div>
        <div className="cs-badge">Coming Soon</div>
        <p className="cs-purpose">{dashboard.purpose}</p>
      </div>
    </div>
  );
}

// ================================================================ Agent → OSA
// The "Agent" nav view is now an OSA chat (POST /api/osa/chat, synchronous
// request/response; see AgentView below). New interaction paradigm → its own
// nav link (GUI principle #7), never an always-on panel.
//
// The governor still exists and stays reachable via its own API
// (POST /api/agent/chat, streamed over the AG-UI feed with run_ids starting
// "agt-"). foldAgentEvent + AGENT_SESSION below remain the governor's plumbing;
// they are intentionally left intact even though AgentView no longer drives it.
const AGENT_SESSION = "gui";

// Fold a single AG-UI event into a *persistent* agent-turn accumulator.
// `acc` = { byId: {}, list: [] }. Returns true if the event changed state.
//
// The chat transcript must NOT be re-derived from the global event feed: that
// feed is capped (slice(-200)) and reply text streams one event per token, so a
// single answer evicts the RUN_STARTED markers that anchor earlier turns. Folding
// incrementally into long-lived state keeps the whole session's log intact.
function foldAgentEvent(acc, e) {
  const id = e.run_id;
  if (!id || !String(id).startsWith("agt-")) return false;
  let t = acc.byId[id];
  switch (e.type) {
    case "RUN_STARTED":
      if (!t) {
        t = { id, model: e.model, user: e.message || "", text: "",
              tools: [], status: "running", cost: 0, tokens: 0 };
        acc.byId[id] = t;
        acc.list.push(t);
        return true;
      }
      // A late RUN_STARTED (e.g. after reconnect) may carry the user message.
      if (!t.user && e.message) { t.user = e.message; return true; }
      return false;
    case "TEXT_MESSAGE_CONTENT":
      if (t && e.delta) { t.text += e.delta; return true; }
      return false;
    case "TOOL_CALL_START":
      if (t) { t.tools.push({ tool: e.tool, payload: e.payload || "", status: "running" }); return true; }
      return false;
    case "TOOL_CALL_END":
      if (t) {
        const tc = [...t.tools].reverse().find((x) => x.tool === e.tool && x.status === "running");
        if (tc) { tc.status = e.ok ? "done" : "error"; return true; }
      }
      return false;
    case "RUN_FINISHED":
      if (t) {
        t.status = "completed";
        if (!t.text && e.text) t.text = e.text;
        t.cost = e.cost_usd || 0;
        t.tokens = e.tokens_used || 0;
        return true;
      }
      return false;
    case "RUN_ERROR":
      if (t) { t.status = "failed"; t.error = e.error; return true; }
      return false;
    default:
      return false;
  }
}

// OSA chat view. Unlike the governor (streamed over AG-UI), OSA's
// POST /api/osa/chat is synchronous request/response, so the transcript lives
// in *local* component state — we append the user message, show a thinking
// placeholder, then append OSA's reply. thread_id is captured from the first
// reply and reused so the conversation is continuous/durable for the session.
// OSA auto-routes each turn (local vs. cloud), so there is no manual model
// picker; a read-only status strip reflects GET /api/osa/state instead.
export function AgentView() {
  const [osa, setOsa] = useState(null); // GET /api/osa/state
  const [turns, setTurns] = useState([]); // [{ id, user, text, tools, route, model, status, error }]
  const [threadId, setThreadId] = useState(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef(null);
  const idRef = useRef(0);

  const loadState = useCallback(() => {
    get("/api/osa/state")
      .then(setOsa)
      .catch(() => setOsa({ ready: false, ollama_up: false, active_label: "OSA", soul: null }));
  }, []);
  useEffect(() => { loadState(); }, [loadState]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [turns, sending]);

  // OSA is reachable whenever the sidecar reports ready. Until state loads we
  // optimistically allow sending (the sidecar is up if this view rendered).
  const ready = osa ? osa.ready !== false : true;

  const send = () => {
    const text = input.trim();
    if (!text || sending || !ready) return;
    const id = ++idRef.current;
    setTurns((prev) => [
      ...prev,
      { id, user: text, text: "", tools: [], route: null, model: null, status: "running" },
    ]);
    setInput("");
    setSending(true);
    post("/api/osa/chat", { message: text, thread_id: threadId })
      .then((d) => {
        if (d.thread_id) setThreadId(d.thread_id);
        setTurns((prev) => prev.map((t) => (t.id === id
          ? { ...t, text: d.reply || "", tools: d.tool_trace || [],
              route: d.route || null, model: d.model || null, status: "completed" }
          : t)));
      })
      .catch((e) => {
        setTurns((prev) => prev.map((t) => (t.id === id
          ? { ...t, status: "failed", error: String(e.message || e) }
          : t)));
      })
      .finally(() => setSending(false));
  };
  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  return (
    <div className="agent-view">
      <div className="agent-bar">
        <div className="agent-model">
          <label>OSA</label>
          <span className="agent-badge local" title="Active OSA brain">
            {osa?.active_label || "loading…"}
          </span>
          <span className={`agent-badge ${osa?.ollama_up ? "local" : "cloud"}`}
            title="Local Ollama runtime status">
            {osa?.ollama_up ? "● Ollama up" : "○ Ollama down"}
          </span>
        </div>
        {osa?.soul && (
          <span className="agent-escalate" title="Active soul / persona file">soul: {osa.soul}</span>
        )}
      </div>

      <div className="agent-scroll" ref={scrollRef}>
        {turns.length === 0 && (
          <Empty msg="Ask OSA to run the machine — e.g. “how’s my memory?”" />
        )}
        {turns.map((t) => (
          <div className="agent-turn" key={t.id}>
            {t.user && <div className="agent-msg user"><div className="bubble">{t.user}</div></div>}
            {t.tools.length > 0 && (
              <div className="agent-trace">
                {t.tools.map((tc, i) => (
                  <span className="trace-chip done" key={i}
                    title={tc.args ? JSON.stringify(tc.args) : undefined}>
                    <span className="trace-dot" />{tc.tool}
                  </span>
                ))}
              </div>
            )}
            <div className="agent-msg assistant">
              <div className="bubble">
                {t.text || (t.status === "running" ? <span className="typing">thinking…</span> : "")}
                {t.status === "failed" && <span className="agent-err">error: {t.error}</span>}
              </div>
              {t.status === "completed" && t.route && (
                <div className="agent-meta">
                  <span className={`agent-badge ${t.route === "local" ? "local" : "cloud"}`}>
                    {t.route === "local" ? "● local" : "☁ cloud"}
                  </span>
                  {t.model ? ` ${t.model}` : ""}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="agent-input">
        <textarea
          rows={2}
          placeholder="Message OSA…  (Enter to send, Shift+Enter for newline)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          disabled={!ready}
        />
        <button
          className="btn approve send-btn"
          disabled={!input.trim() || sending || !ready}
          onClick={send}
        >
          Send
        </button>
      </div>
    </div>
  );
}


// Dashboard registry (FR-46) — single source of truth for the nav + native menu.
// Order locked 2026-06-14: SysOps, Workflows, the four placeholders, then Agent
// (⌘7). Agent is appended last so the ⌘1–6 bindings stay stable.
// Phase 9: Settings added as full-page view.
const VIEWS = [
  { id: "sysops", label: "SysOps", component: SysOpsView, badge: "approvals" },
  { id: "workflows", label: "Workflows", component: WorkflowsWorkspace },
  { id: "web-news", label: "Web News", component: WebNewsView },

  { id: "scripts", label: "Scripts", component: ScriptsExplorer },
  { id: "zsh-config", label: "Zsh Config Editor", placeholder: true,
    purpose: "Edit and version your zsh configuration with safe rollbacks." },
  { id: "obsidian", label: "Obsidian Viewer", placeholder: true,
    purpose: "Read and search the Brain2 Obsidian vault inside the app." },
  { id: "projects", label: "Projects", component: ProjectsView },  // Phase 13d (⌘8 — appended after ⌘1–7 so existing bindings stay stable)
  { id: "hub-api", label: "Hub API", component: HubApiExplorer },
  { id: "settings", label: "Settings", component: SettingsView },
  { id: "agent", label: "Agent", component: AgentView, badge: "approvals" },
];

const VIEW_KEY = "agentic-os.activeView";

// Hidden reveal for the Self-Diagnostics dashboard (Phase 12): an invisible
// hit-target pinned to the very bottom-right corner. Triple-tap within 700ms
// opens the overlay. Deliberately undiscoverable — not in the nav or menu.
function CornerReveal({ onReveal }) {
  const taps = useRef([]);
  const handle = () => {
    const now = Date.now();
    taps.current = [...taps.current, now].filter((t) => now - t < 700);
    if (taps.current.length >= 3) {
      taps.current = [];
      onReveal();
    }
  };
  return (
    <div
      onClick={handle}
      aria-hidden="true"
      style={{ position: "fixed", right: 0, bottom: 0, width: 26, height: 26, zIndex: 8000 }}
    />
  );
}

// ================================================================ shell
export default function App() {
  const [workflows, setWorkflows] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [feed, setFeed] = useState([]);
  const [agentTurns, setAgentTurns] = useState([]);
  const agentAcc = useRef({ byId: {}, list: [] });
  const [connected, setConnected] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [view, setView] = useState(() => {
    let saved = localStorage.getItem(VIEW_KEY);
    if (saved === "dashboard") saved = "sysops";      // FR-47 migration (old dashboard → sysops)
    if (saved === "events") saved = "workflows";      // Events merged into Workflows dashboard
    if (saved === "tool-viz") saved = "workflows";    // Run Visualizer merged into Workflows workspace
    if (saved === "config") saved = "scripts";        // Phase 2 migration: old config → scripts tabs
    return VIEWS.some((v) => v.id === saved) ? saved : "sysops";
  });

  // Phase 12: hidden self-diagnostics overlay. Revealed by the corner gesture
  // (CornerReveal) or the `#diag` URL-hash escape hatch when the gesture misfires.
  const [showDiag, setShowDiag] = useState(false);
  useEffect(() => {
    const check = () => { if (window.location.hash === "#diag") setShowDiag(true); };
    check();
    window.addEventListener("hashchange", check);
    return () => window.removeEventListener("hashchange", check);
  }, []);
  const closeDiag = useCallback(() => {
    setShowDiag(false);
    if (window.location.hash === "#diag") {
      history.replaceState(null, "", window.location.pathname + window.location.search);
    }
  }, []);

  // Approvals: fast when sidecar is down; immediate re-fetch on WS approval events.
  const [approvalKey, setApprovalKey] = useState(0);
  const approvalsData = usePoll("/api/approvals", 15_000, 2_000, approvalKey);
  useEffect(() => {
    if (approvalsData?.approvals) setApprovals(approvalsData.approvals);
  }, [approvalsData]);

  // Workflows: change slowly (WS events drive real-time); fast recovery when down.
  const workflowsData = usePoll("/api/workflows", 30_000, 2_000);
  useEffect(() => {
    if (workflowsData?.workflows) setWorkflows(workflowsData.workflows);
  }, [workflowsData]);

  useEffect(() => {
    const stop = connectAgui((evt) => {
      setFeed((f) => [...f.slice(-200), evt]);
      // Persist the agent chat log independently of the capped feed.
      if (foldAgentEvent(agentAcc.current, evt)) {
        setAgentTurns(agentAcc.current.list.slice());
      }
      if (evt.type === "APPROVAL_REQUIRED" || evt.type === "APPROVAL_RESOLVED")
        setApprovalKey((k) => k + 1);           // immediate re-fetch
      if (evt.type === "RUN_FINISHED" || evt.type === "RUN_ERROR")
        setRefreshKey((k) => k + 1);
    }, setConnected);
    return stop;
  }, []);

  useEffect(() => {
    localStorage.setItem(VIEW_KEY, view);
  }, [view]);

  // Expose global hook so the native menu bar (lib.rs) can switch views
  useEffect(() => {
    window.__agenticOsSetView = (viewId) => {
      if (VIEWS.some((v) => v.id === viewId)) setView(viewId);
    };
    return () => { delete window.__agenticOsSetView; };
  }, []);

  // FR-60: apply the persisted theme on boot + expose the native-menu switch
  // bridge (View ▸ Theme in lib.rs), mirroring __agenticOsSetView above.
  useEffect(() => {
    applyTheme(loadTheme());
    // Apply locally AND broadcast so the HUD window (and any other) re-skins
    // live — keeps the HUD on the theme last set in the app (FR-60).
    window.__agenticOsSetTheme = (key) => {
      applyTheme(key);
      emit("theme-changed", key).catch(() => {});
    };
    return () => { delete window.__agenticOsSetTheme; };
  }, []);

  // FR-63: the HUD nav drives the (re-shown) main window via a Tauri event.
  useEffect(() => {
    const un = listen("goto-view", (e) => {
      const id = e.payload;
      if (typeof id === "string" && VIEWS.some((v) => v.id === id)) setView(id);
    });
    return () => { un.then((f) => f()).catch(() => {}); };
  }, []);

  // FR-63: collapse to the HUD — drop it where the sidebar was (the main
  // window's content top-left), then hide main so the sidebar appears to stay.
  const minimizeToHud = async () => {
    try {
      const main = getCurrentWindow();
      const hud = await WebviewWindow.getByLabel("hud");
      if (hud) {
        try { await hud.setPosition(await main.innerPosition()); } catch { /* positioning best-effort */ }
        await hud.show();
        await hud.setFocus();
      }
      await main.hide();
    } catch { /* not running under Tauri (browser dev) */ }
  };

  const runWorkflow = (name) => post(`/api/workflows/${name}/run`).catch(() => {});
  const decide = (id, decision) =>
    post(`/api/approvals/${id}`, { decision }).then(loadApprovals).catch(() => {});

  // Phase 2: Diagnostics panel polling (2s normal, 1s when down)
  const systemHealthData = usePoll("/api/panels/system", 2000, 1000);

  const active = VIEWS.find((v) => v.id === view) || VIEWS[0];
  const ActiveView = active.component;
  const ctx = { workflows, approvals, feed, agentTurns, refreshKey, runWorkflow, decide };

  return (
    <div className="shell">
      {/* FR-36: sidebar is navigation only */}
      <aside className="sidebar">
        <div className="brand">OSA<small>agentic os · v{pkg.version}</small></div>
        <nav className="nav">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              className={`nav-item${v.id === active.id ? " active" : ""}`}
              onClick={() => setView(v.id)}
            >
              {v.label}
              {v.badge === "approvals" && approvals.length > 0 && (
                <span className="nav-badge">{approvals.length}</span>
              )}
            </button>
          ))}
        </nav>

        {/* Phase 2: Diagnostics sidebar panel */}
        <div className="sidebar-diagnostics">
          <DiagnosticsPanel data={systemHealthData} />
        </div>

        <div className="spacer" />
        <button className="hud-btn" onClick={minimizeToHud} title="Hide the app and float a compact always-on-top HUD">
          ⤡ Minimize to HUD
        </button>
        <div className="conn">
          <span className={`dot ${connected ? "on" : "err"}`} />
          sidecar {connected ? "connected" : "disconnected"} · :5130
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          <span className="title">{active.label}</span>
          <span className="metric">approvals pending <b>{approvals.length}</b></span>
        </div>
        {active.placeholder
          ? <ComingSoon dashboard={active} />
          : <ErrorBoundary key={active.id} label={active.label}>
              <ActiveView ctx={ctx} />
            </ErrorBoundary>}
        <div className="statusbar">
          <span>AG-UI {connected ? "● live" : "○ reconnecting"}</span>
          <span>events {feed.length}</span>
        </div>
      </main>

      {/* Phase 12: hidden self-diagnostics — corner gesture reveal + overlay */}
      <CornerReveal onReveal={() => setShowDiag(true)} />
      {showDiag && <SelfDiagnosticsView onClose={closeDiag} />}
    </div>
  );
}
