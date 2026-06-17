// Agentic OS dashboard — Phase 7 (FR-40–44): expandable panels over Phase 3 nav shell
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { get, post, connectAgui, fmtAge, fmtEta, fmtUptime, fmtBytes } from "./api";
import "./App.css";
import "@xterm/xterm/css/xterm.css";

function usePoll(path, ms) {
  const [data, setData] = useState(null);
  useEffect(() => {
    let alive = true;
    const tick = () =>
      get(path)
        .then((d) => alive && setData(d))
        .catch(() => alive && setData({ available: false, error: "sidecar unreachable" }));
    tick();
    const id = setInterval(tick, ms);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [path, ms]);
  return data;
}

// ---------------------------------------------------------------- FR-28
function SystemHealth({ expanded }) {
  const d = usePoll("/api/panels/system", 2000);
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
  const [d, setD] = useState(null);
  const [allRuns, setAllRuns] = useState(null);

  useEffect(() => {
    get("/api/panels/activity").then(setD).catch(() => setD(null));
  }, [refreshKey]);

  useEffect(() => {
    if (!expanded) return;
    get("/api/runs?limit=50")
      .then((r) => setAllRuns(r.runs))
      .catch(() => {});
  }, [expanded, refreshKey]);

  if (!d) return <Empty msg="No activity data" />;

  if (!expanded) {
    return (
      <>
        <dl className="kv">
          <dt>Cost today</dt><dd>${d.cost_today_usd.toFixed(4)}</dd>
          <dt>Cost this month</dt><dd>${d.cost_month_usd.toFixed(4)}</dd>
          <dt>Runs today</dt><dd>{d.runs_today}</dd>
          <dt>Total tokens</dt><dd>{d.tokens_total.toLocaleString()}</dd>
          <dt>Success rate</dt><dd>{d.success_rate ?? "—"}%</dd>
          <dt>Avg duration</dt><dd>{d.avg_duration_s ?? "—"}s</dd>
        </dl>
        <table style={{ marginTop: 8 }}>
          <thead><tr><th>Workflow</th><th>Status</th><th>Cost</th></tr></thead>
          <tbody>
            {d.recent_runs.slice(0, 6).map((r) => (
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
  const runs = allRuns || d.recent_runs;
  return (
    <div className="exp-grid-2">
      <div className="exp-col">
        <div className="exp-section-title">Summary</div>
        <dl className="kv">
          <dt>Cost today</dt><dd>${d.cost_today_usd.toFixed(4)}</dd>
          <dt>Cost this month</dt><dd>${d.cost_month_usd.toFixed(4)}</dd>
          <dt>Runs today</dt><dd>{d.runs_today}</dd>
          <dt>Total tokens</dt><dd>{d.tokens_total.toLocaleString()}</dd>
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
  const d = usePoll("/api/panels/keno", 30000);
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
  const d = usePoll("/api/panels/hub", 5000);
  const m = usePoll("/api/panels/hub/manifests", 60000);
  const [busy, setBusy] = useState(null);
  const [expandedManifest, setExpandedManifest] = useState(null);

  if (!d) return <Empty msg="Loading…" />;
  if (!d.available) return <Empty msg={`Hub unreachable — ${d.error}`} />;

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
  const d = usePoll("/api/panels/terminal", 3000);

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

  return (
    <div ref={gridRef} className={`grid${exp ? " has-expanded" : ""}`}>
      {P("System Health", <SystemHealth expanded={exp === "System Health"} />)}
      {P("Agent Activity", <AgentActivity refreshKey={refreshKey} expanded={exp === "Agent Activity"} />)}
      {P("Keno Telemetry", <KenoTelemetry expanded={exp === "Keno Telemetry"} />)}
      {P("Codehome Hub", <HubPanel expanded={exp === "Codehome Hub"} />)}
      {P("Approval Queue", <ApprovalQueue approvals={approvals} onDecide={decide} expanded={exp === "Approval Queue"} />)}
      {P("Terminal", <TerminalStrip expanded={exp === "Terminal"} />)}
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
        return (
          <div className={`feed-line linkable${cls}`} key={i} onClick={() => onSelectEvent(e)}>
            <b>{e.type}</b> {e.workflow || ""}{e.step ? ` · ${e.step}` : ""}
            {e.run_id ? <span className="feed-run"> {shortId(e.run_id)}</span> : null}
            {e.ts ? <span className="feed-ts"> {e.ts}</span> : null}
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

// ================================================================ Agent (FR-56/58)
// Conversational governing-agent dashboard. New interaction paradigm → its own
// nav link (GUI principle #7), never an always-on panel. The transcript is
// reconstructed from the shared AG-UI feed (every agent turn has a run_id that
// starts with "agt-"); messages are sent via POST /api/agent/chat, whose output
// streams back over that same feed. Inline approvals reuse the shared approval
// queue (ctx.approvals + ctx.decide); the model selector + escalate toggle drive
// GET/POST /api/agent/model[s].
const AGENT_SESSION = "gui";

// Fold the flat event feed into ordered agent turns.
function buildTranscript(feed) {
  const turns = [];
  const byId = {};
  for (const e of feed) {
    const id = e.run_id;
    if (!id || !String(id).startsWith("agt-")) continue;
    let t = byId[id];
    switch (e.type) {
      case "RUN_STARTED":
        if (!t) {
          t = { id, model: e.model, user: e.message || "", text: "",
                tools: [], status: "running", cost: 0, tokens: 0 };
          byId[id] = t;
          turns.push(t);
        }
        break;
      case "TEXT_MESSAGE_CONTENT":
        if (t && e.delta) t.text += e.delta;
        break;
      case "TOOL_CALL_START":
        if (t) t.tools.push({ tool: e.tool, payload: e.payload || "", status: "running" });
        break;
      case "TOOL_CALL_END":
        if (t) {
          const tc = [...t.tools].reverse().find((x) => x.tool === e.tool && x.status === "running");
          if (tc) tc.status = e.ok ? "done" : "error";
        }
        break;
      case "RUN_FINISHED":
        if (t) {
          t.status = "completed";
          if (!t.text && e.text) t.text = e.text;
          t.cost = e.cost_usd || 0;
          t.tokens = e.tokens_used || 0;
        }
        break;
      case "RUN_ERROR":
        if (t) { t.status = "failed"; t.error = e.error; }
        break;
      default:
        break;
    }
  }
  return turns;
}

function ModelBadge({ isLocal }) {
  return (
    <span className={`agent-badge ${isLocal ? "local" : "cloud"}`}>
      {isLocal ? "● local" : "☁ cloud"}
    </span>
  );
}

// Format a model's RAM/disk footprint (bytes → "4.7 GB").
const gb = (bytes) => (bytes ? `${(bytes / 1e9).toFixed(1)} GB` : "");

// Dropdown suffix: show size for runnable locals, or why one is unavailable.
function modelSuffix(m) {
  if (m.available) return m.is_local && m.size_bytes ? ` · ${gb(m.size_bytes)}` : "";
  switch (m.reason) {
    case "ollama_off": return " (Ollama offline)";
    case "not_installed": return " (not installed)";
    case "too_large": return ` (too large${m.size_bytes ? ` · ${gb(m.size_bytes)}` : ""})`;
    case "no_api_key": return " (no API key)";
    default: return m.is_local ? " (unavailable)" : " (no API key)";
  }
}

// Inline hint explaining why the active model can't be used, and the fix.
function modelHint(m) {
  if (!m) return "The selected model is unavailable — pick another above.";
  switch (m.reason) {
    case "ollama_off":
      return `Ollama isn’t running, so ${m.label} can’t be used — it should start automatically; press Reload, or start Ollama manually.`;
    case "not_installed":
      return `${m.label} isn’t installed — pull it with Ollama (\`ollama pull ${m.id}\`), or pick an available model above.`;
    case "too_large":
      return `${m.label} needs ${m.size_bytes ? `~${gb(m.size_bytes)}` : "more than half your RAM"} and may not run comfortably on this machine — pick a smaller model, or escalate to cloud.`;
    case "no_api_key":
      return `No API key for ${m.label} — set ANTHROPIC_API_KEY, or pick a local model above.`;
    default:
      return `${m.label} is unavailable — pick another model above.`;
  }
}

function AgentView({ ctx }) {
  const { feed, approvals, decide } = ctx;
  const [models, setModels] = useState(null);
  const [active, setActive] = useState(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef(null);

  const loadModels = useCallback(() => {
    get("/api/agent/models")
      .then((d) => { setModels(d); setActive(d.active); })
      .catch(() => setModels({ models: [], active: null, ollama_up: false }));
  }, []);
  useEffect(() => { loadModels(); }, [loadModels]);

  const transcript = useMemo(() => buildTranscript(feed), [feed]);
  // Pending approvals raised by an agent turn (workflow tag "agent:<session>").
  const agentApprovals = approvals.filter(
    (a) => String(a.workflow || "").startsWith("agent:")
  );

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [transcript, agentApprovals.length]);

  // RUN_STARTED echoes the user message, so clear the "sending" flag once the
  // turn shows up in the transcript.
  const lastTurn = transcript[transcript.length - 1];
  useEffect(() => {
    if (sending && lastTurn && lastTurn.status === "running") setSending(false);
  }, [sending, lastTurn]);

  const activeInfo = models?.models?.find((m) => m.id === active);
  const activeIsLocal = !!activeInfo?.is_local;
  // Issue 1: the active model can be unavailable (e.g. the default local model
  // isn't installed, or a cloud model has no API key). Until models load,
  // activeInfo is undefined — treat that as "not yet sendable" too.
  const activeAvailable = !!activeInfo?.available;

  const selectModel = (id) => {
    setActive(id); // optimistic
    post("/api/agent/model", { id }).then(loadModels).catch(loadModels);
  };

  // Issue 1: if the active model is unavailable, fall back once to the first
  // available LOCAL model. We never auto-jump to a cloud model — that could
  // incur cost silently; instead Send is disabled with a hint and the user can
  // escalate to cloud explicitly.
  const fellBackRef = useRef(false);
  useEffect(() => {
    if (!models?.models?.length || !active) return;
    if (activeAvailable) { fellBackRef.current = false; return; }
    if (fellBackRef.current) return;
    const fallback = models.models.find((m) => m.is_local && m.available);
    if (fallback) {
      fellBackRef.current = true;
      selectModel(fallback.id);
    }
  }, [models, active, activeAvailable]);

  // FR-58: per-conversation escalate-to-cloud. On → switch to the first
  // available cloud model; off → back to the first available local model.
  const toggleEscalate = () => {
    const list = models?.models || [];
    const target = activeIsLocal
      ? list.find((m) => !m.is_local && m.available) || list.find((m) => !m.is_local)
      : list.find((m) => m.is_local && m.available) || list.find((m) => m.is_local);
    if (target) selectModel(target.id);
  };

  const send = () => {
    const text = input.trim();
    if (!text || sending || !activeAvailable) return;
    setSending(true);
    setInput("");
    post("/api/agent/chat", { message: text, session_id: AGENT_SESSION })
      .catch(() => setSending(false));
  };
  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  return (
    <div className="agent-view">
      <div className="agent-bar">
        <div className="agent-model">
          <label>Model</label>
          <select value={active || ""} onChange={(e) => selectModel(e.target.value)}>
            {(models?.models || []).map((m) => (
              <option key={m.id} value={m.id} disabled={!m.available}>
                {m.label}{modelSuffix(m)}
              </option>
            ))}
          </select>
          {activeInfo && <ModelBadge isLocal={activeIsLocal} />}
        </div>
        <label className="agent-escalate" title="Switch this conversation between a local and a cloud model">
          <input type="checkbox" checked={!activeIsLocal} onChange={toggleEscalate} />
          Escalate to cloud
        </label>
      </div>

      <div className="agent-scroll" ref={scrollRef}>
        {transcript.length === 0 && (
          <Empty msg="Ask the governing agent to operate the OS — e.g. “list my workflows”." />
        )}
        {transcript.map((t) => (
          <div className="agent-turn" key={t.id}>
            {t.user && <div className="agent-msg user"><div className="bubble">{t.user}</div></div>}
            {t.tools.length > 0 && (
              <div className="agent-trace">
                {t.tools.map((tc, i) => (
                  <span className={`trace-chip ${tc.status}`} key={i} title={tc.payload}>
                    <span className="trace-dot" />{tc.tool}
                  </span>
                ))}
              </div>
            )}
            <div className="agent-msg assistant">
              <div className="bubble">
                {t.text || (t.status === "running" ? <span className="typing">…</span> : "")}
                {t.status === "failed" && <span className="agent-err">error: {t.error}</span>}
              </div>
              {t.status === "completed" && (
                <div className="agent-meta">
                  {t.tokens ? `${t.tokens.toLocaleString()} tok` : "0 tok"}
                  {t.cost > 0 ? ` · $${t.cost.toFixed(4)}` : " · $0"}
                </div>
              )}
            </div>
          </div>
        ))}

        {agentApprovals.map((a) => (
          <div className="agent-approval" key={a.approval_id}>
            <div className="q">{a.question}</div>
            <div className="agent-approval-actions">
              <button className="btn approve" onClick={() => decide(a.approval_id, "approve")}>✓ Allow</button>
              <button className="btn deny" onClick={() => decide(a.approval_id, "deny")}>✕ Deny</button>
            </div>
          </div>
        ))}
        {sending && <div className="agent-sending">sending…</div>}
      </div>

      {models && active && !activeAvailable && (
        <div className="agent-hint">{modelHint(activeInfo)}</div>
      )}

      <div className="agent-input">
        <textarea
          rows={2}
          placeholder={activeAvailable
            ? "Message the governing agent…  (Enter to send, Shift+Enter for newline)"
            : "Select an available model to start chatting…"}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          disabled={!activeAvailable}
        />
        <button
          className="btn approve send-btn"
          disabled={!input.trim() || sending || !activeAvailable}
          title={!activeAvailable ? "The selected model is unavailable" : undefined}
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
const VIEWS = [
  { id: "sysops", label: "SysOps", component: SysOpsView, badge: "approvals" },
  { id: "workflows", label: "Workflows", component: WorkflowsDashboard },
  { id: "web-news", label: "Web News", placeholder: true,
    purpose: "Curated developer & AI news, summarized by the agent." },
  { id: "scripts", label: "Scripts", placeholder: true,
    purpose: "Browse and run Codehome scripts — future home of the absorbed Hub (NF-4)." },
  { id: "zsh-config", label: "Zsh Config Editor", placeholder: true,
    purpose: "Edit and version your zsh configuration with safe rollbacks." },
  { id: "obsidian", label: "Obsidian Viewer", placeholder: true,
    purpose: "Read and search the Brain2 Obsidian vault inside the app." },
  { id: "agent", label: "Agent", component: AgentView, badge: "approvals" },
];

const VIEW_KEY = "agentic-os.activeView";

// ================================================================ shell
export default function App() {
  const [workflows, setWorkflows] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [feed, setFeed] = useState([]);
  const [connected, setConnected] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [view, setView] = useState(() => {
    let saved = localStorage.getItem(VIEW_KEY);
    if (saved === "dashboard") saved = "sysops";      // FR-47 migration
    if (saved === "events") saved = "workflows";      // Events merged into Workflows dashboard
    return VIEWS.some((v) => v.id === saved) ? saved : "sysops";
  });

  const loadApprovals = () =>
    get("/api/approvals").then((d) => setApprovals(d.approvals)).catch(() => {});

  useEffect(() => {
    get("/api/workflows").then((d) => setWorkflows(d.workflows)).catch(() => {});
    loadApprovals();
    const stop = connectAgui((evt) => {
      setFeed((f) => [...f.slice(-200), evt]);
      if (evt.type === "APPROVAL_REQUIRED" || evt.type === "APPROVAL_RESOLVED") loadApprovals();
      if (evt.type === "RUN_FINISHED" || evt.type === "RUN_ERROR") setRefreshKey((k) => k + 1);
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

  const runWorkflow = (name) => post(`/api/workflows/${name}/run`).catch(() => {});
  const decide = (id, decision) =>
    post(`/api/approvals/${id}`, { decision }).then(loadApprovals).catch(() => {});

  const active = VIEWS.find((v) => v.id === view) || VIEWS[0];
  const ActiveView = active.component;
  const ctx = { workflows, approvals, feed, refreshKey, runWorkflow, decide };

  return (
    <div className="shell">
      {/* FR-36: sidebar is navigation only */}
      <aside className="sidebar">
        <div className="brand">AGENTIC OS<small>orchestration layer · v0.3</small></div>
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
        <div className="spacer" />
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
          : <ActiveView ctx={ctx} />}
        <div className="statusbar">
          <span>AG-UI {connected ? "● live" : "○ reconnecting"}</span>
          <span>events {feed.length}</span>
        </div>
      </main>
    </div>
  );
}
