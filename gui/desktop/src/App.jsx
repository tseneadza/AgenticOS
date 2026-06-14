// Agentic OS dashboard — Phase 7 (FR-40–44): expandable panels over Phase 3 nav shell
import { useCallback, useEffect, useRef, useState } from "react";
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
function DashboardView({ ctx }) {
  const { approvals, refreshKey, decide } = ctx;
  const gridRef = useRef(null);

  // FR-44: persist last-expanded panel across restarts
  const [expandedPanel, setExpandedPanel] = useState(
    () => localStorage.getItem(EXPAND_KEY) || null
  );

  const toggle = useCallback((title) => {
    setExpandedPanel((prev) => {
      const next = prev === title ? null : title;
      if (next) {
        localStorage.setItem(EXPAND_KEY, next);
        // scroll grid to top so the absolute overlay starts from the visible area
        if (gridRef.current) gridRef.current.scrollTop = 0;
      } else {
        localStorage.removeItem(EXPAND_KEY);
      }
      return next;
    });
  }, []);

  const mkPanel = (title, content) => (
    <Panel
      key={title}
      title={title}
      expanded={expandedPanel === title}
      onExpand={() => toggle(title)}
    >
      {content}
    </Panel>
  );

  const exp = expandedPanel;

  return (
    <div ref={gridRef} className={`grid${exp ? " has-expanded" : ""}`}>
      {mkPanel("System Health", <SystemHealth expanded={exp === "System Health"} />)}
      {mkPanel("Agent Activity", <AgentActivity refreshKey={refreshKey} expanded={exp === "Agent Activity"} />)}
      {mkPanel("Keno Telemetry", <KenoTelemetry expanded={exp === "Keno Telemetry"} />)}
      {mkPanel("Codehome Hub", <HubPanel expanded={exp === "Codehome Hub"} />)}
      {mkPanel("Approval Queue", <ApprovalQueue approvals={approvals} onDecide={decide} expanded={exp === "Approval Queue"} />)}
      {mkPanel("Terminal", <TerminalStrip expanded={exp === "Terminal"} />)}
    </div>
  );
}

function WorkflowsView({ ctx }) {
  const { workflows, runWorkflow, feed } = ctx;
  const lastRunEvent = (name) =>
    [...feed].reverse().find((e) => e.workflow === name && (e.type === "RUN_FINISHED" || e.type === "RUN_ERROR" || e.type === "RUN_STARTED"));
  if (!workflows.length) return <div className="view-pad"><Empty msg="No workflows defined" /></div>;
  return (
    <div className="view-pad">
      <table>
        <thead><tr><th>Workflow</th><th>Description</th><th>Last event</th><th></th></tr></thead>
        <tbody>
          {workflows.map((w) => {
            const ev = lastRunEvent(w.name);
            return (
              <tr key={w.name}>
                <td>{w.name}</td>
                <td style={{ fontFamily: "inherit" }}>{w.description}</td>
                <td>{ev ? ev.type : "—"}</td>
                <td style={{ textAlign: "right" }}>
                  <button className="run-btn" onClick={() => runWorkflow(w.name)}>run</button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function EventsView({ ctx }) {
  const { feed } = ctx;
  const ref = useRef(null);
  useEffect(() => {
    ref.current?.scrollTo(0, ref.current.scrollHeight);
  }, [feed]);
  if (!feed.length) return <div className="view-pad"><Empty msg="No events yet — run a workflow" /></div>;
  return (
    <div className="view-pad feed-scroll" ref={ref}>
      {feed.map((e, i) => (
        <div className="feed-line" key={i}>
          <b>{e.type}</b> {e.workflow || ""}{e.step ? ` · ${e.step}` : ""}
          {e.ts ? <span className="feed-ts"> {e.ts}</span> : null}
        </div>
      ))}
    </div>
  );
}

// View registry (FR-37)
const VIEWS = [
  { id: "dashboard", label: "Dashboard", component: DashboardView },
  { id: "workflows", label: "Workflows", component: WorkflowsView },
  { id: "events", label: "Events", component: EventsView },
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
    const saved = localStorage.getItem(VIEW_KEY);
    return VIEWS.some((v) => v.id === saved) ? saved : "dashboard";
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
              {v.id === "dashboard" && approvals.length > 0 && (
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
        <ActiveView ctx={ctx} />
        <div className="statusbar">
          <span>AG-UI {connected ? "● live" : "○ reconnecting"}</span>
          <span>events {feed.length}</span>
        </div>
      </main>
    </div>
  );
}
