/**
 * ProjectsView — Phase 13d (Projects GUI over the data-driven launch system)
 *
 * Card grid over the `projects` ledger (GET /api/projects), joined with live
 * running status from GET /api/apps (in-memory hot path — no per-app DB hits).
 * Start/Stop wired to POST /api/apps/{id}/start|stop (ONE launch system:
 * launch-config plan when configured, legacy registry otherwise).
 *
 * Expanding a card fetches the per-app detail:
 *   GET /api/apps/{id}/status       — pid-verified app_processes rows (13c)
 *   GET /api/apps/{id}/launch-plan  — resolved build_launch_command steps
 *
 * Status badge: green = running, yellow = partial (some tracked processes
 * stopped while the app is up), red = stopped.
 *
 * Conventions: theme tokens only (docs/gui-frontend-conventions.md rule 1);
 * hover/transitions via a scoped injected stylesheet (rule 3, `pv-*` classes).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { get, post } from "../api";

const POLL_MS = 5000;
const POLL_MS_DOWN = 2000;

// ── component-scoped stylesheet (rule 3) ────────────────────────────────────
const STYLE_ID = "pv-styles";
const STYLE_CSS = `
.pv-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
  gap: var(--gap);
  align-content: start;
}
.pv-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  padding: 12px 14px;
  transition: border-color 0.12s ease, box-shadow 0.12s ease;
}
.pv-card:hover { border-color: var(--accent); box-shadow: var(--glow); }
.pv-card.pv-expanded { grid-column: 1 / -1; }
.pv-btn {
  all: unset; cursor: pointer; box-sizing: border-box;
  padding: 5px 12px; border-radius: 6px;
  font-family: var(--mono); font-size: 11px;
  border: 1px solid var(--border-soft);
  color: var(--text); background: var(--bg-inset);
  transition: all 0.12s ease;
}
.pv-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.pv-btn:disabled { cursor: default; color: var(--text-dim); opacity: 0.6; }
.pv-btn-start:hover:not(:disabled) { border-color: var(--green); color: var(--green); }
.pv-btn-stop:hover:not(:disabled) { border-color: var(--red); color: var(--red); }
.pv-link { color: var(--text-dim); text-decoration: none; font-size: 11px; }
.pv-link:hover { color: var(--accent); }
.pv-chip {
  display: inline-block; padding: 2px 8px; border-radius: 999px;
  font-size: 10px; font-family: var(--mono); letter-spacing: 0.3px;
  border: 1px solid var(--border-soft);
  color: var(--text-dim); background: var(--bg-inset); white-space: nowrap;
}
.pv-expand-toggle {
  all: unset; cursor: pointer; font-size: 11px; font-family: var(--mono);
  color: var(--text-dim); padding: 2px 4px;
}
.pv-expand-toggle:hover { color: var(--accent); }
.pv-detail-table { width: 100%; border-collapse: collapse; font-size: 11px; font-family: var(--mono); }
.pv-detail-table th {
  text-align: left; color: var(--text-dim); font-weight: 500;
  padding: 4px 10px 4px 0; border-bottom: 1px solid var(--border-soft);
}
.pv-detail-table td { padding: 4px 10px 4px 0; color: var(--text); vertical-align: top; }
`;

function useScopedStyles() {
  useEffect(() => {
    if (document.getElementById(STYLE_ID)) return;
    const el = document.createElement("style");
    el.id = STYLE_ID;
    el.textContent = STYLE_CSS;
    document.head.appendChild(el);
  }, []);
}

// ── status badge (green all-running / yellow partial / red stopped) ─────────
function badgeState(running, detail) {
  if (!running) return "stopped";
  const procs = detail?.processes;
  if (Array.isArray(procs) && procs.length > 0) {
    const up = procs.filter((p) => p.status === "running").length;
    if (up > 0 && up < procs.length) return "partial";
  }
  return "running";
}

const BADGE = {
  running: { color: "var(--green)", label: "running" },
  partial: { color: "var(--yellow)", label: "partial" },
  stopped: { color: "var(--red)", label: "stopped" },
};

function StatusBadge({ state }) {
  const b = BADGE[state] || BADGE.stopped;
  return (
    <span
      data-testid={`pv-badge-${state}`}
      style={{
        display: "inline-flex", alignItems: "center", gap: 5,
        fontSize: 10, fontFamily: "var(--mono)", color: b.color,
      }}
    >
      <span style={{
        width: 8, height: 8, borderRadius: "50%", background: b.color,
        display: "inline-block",
      }} />
      {b.label}
    </span>
  );
}

// ── expanded detail: processes + launch plan ────────────────────────────────
function CardDetail({ appId, detail, plan }) {
  const procs = detail?.processes || [];
  return (
    <div style={{ marginTop: 10, borderTop: "1px solid var(--border-soft)", paddingTop: 10 }}>
      <div style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 6 }}>
        Processes
      </div>
      {procs.length === 0 ? (
        <div style={{ fontSize: 11, color: "var(--text-dim)", fontStyle: "italic" }}>
          No tracked processes.
        </div>
      ) : (
        <table className="pv-detail-table" data-testid={`pv-procs-${appId}`}>
          <thead>
            <tr><th>pid</th><th>port</th><th>type</th><th>status</th><th>started</th></tr>
          </thead>
          <tbody>
            {procs.map((p, i) => (
              <tr key={`${p.pid}-${i}`}>
                <td>{p.pid ?? "—"}</td>
                <td>{p.port ?? "—"}</td>
                <td>{p.port_type ?? "—"}</td>
                <td style={{ color: p.status === "running" ? "var(--green)" : "var(--text-dim)" }}>
                  {p.status}
                </td>
                <td>{p.started_at ? p.started_at.replace("T", " ").slice(0, 19) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div style={{ fontSize: 11, color: "var(--text-dim)", margin: "12px 0 6px" }}>
        Launch plan
      </div>
      {plan == null ? (
        <div style={{ fontSize: 11, color: "var(--text-dim)" }}>Loading…</div>
      ) : !plan.configured ? (
        <div style={{ fontSize: 11, color: "var(--text-dim)", fontStyle: "italic" }}>
          No launch config — {plan.reason || "starts via legacy registry command"}.
        </div>
      ) : (
        <table className="pv-detail-table" data-testid={`pv-plan-${appId}`}>
          <thead>
            <tr><th>#</th><th>command</th><th>cwd</th><th>port</th><th>wait</th></tr>
          </thead>
          <tbody>
            {plan.steps.map((s) => (
              <tr key={s.step}>
                <td>{s.step}</td>
                <td style={{ wordBreak: "break-all" }}>
                  {s.command} {(s.args || []).join(" ")}
                </td>
                <td style={{ wordBreak: "break-all", color: "var(--text-dim)" }}>{s.cwd}</td>
                <td>{s.port ?? "—"}</td>
                <td style={{ color: "var(--text-dim)" }}>
                  {s.wait_for_completion ? "completion" : s.wait_for_port ? `port :${s.port}` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ── one project card ─────────────────────────────────────────────────────────
function ProjectCard({ project, app, onAction, busy }) {
  const appId = project.id;
  const inRegistry = app != null;
  const running = !!app?.running;

  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState(null);
  const [plan, setPlan] = useState(null);

  const loadDetail = useCallback(() => {
    get(`/api/apps/${appId}/status`).then(setDetail).catch(() => setDetail(null));
    get(`/api/apps/${appId}/launch-plan`).then(setPlan).catch(() => setPlan(null));
  }, [appId]);

  // Refresh the expanded detail when running state flips (start/stop landed).
  useEffect(() => {
    if (expanded && inRegistry) loadDetail();
  }, [expanded, running, inRegistry, loadDetail]);

  const state = badgeState(running, detail);

  return (
    <div className={`pv-card${expanded ? " pv-expanded" : ""}`} data-testid={`pv-card-${appId}`}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: "var(--text)", flex: 1,
                       overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {project.name}
        </span>
        <StatusBadge state={state} />
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "8px 0" }}>
        <span className="pv-chip">{project.template || "—"}</span>
        <span className="pv-chip">{project.subfolder || "Codehome root"}</span>
        {project.port != null && <span className="pv-chip">:{project.port}</span>}
        {running && app?.port_live != null && app.port_live !== project.port && (
          <span className="pv-chip" style={{ color: "var(--yellow)" }}>live :{app.port_live}</span>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {running ? (
          <button
            className="pv-btn pv-btn-stop"
            disabled={busy || !inRegistry}
            onClick={() => onAction(appId, "stop")}
          >
            {busy ? "…" : "Stop"}
          </button>
        ) : (
          <button
            className="pv-btn pv-btn-start"
            disabled={busy || !inRegistry}
            title={inRegistry ? undefined : "Not in the app registry — cannot launch"}
            onClick={() => onAction(appId, "start")}
          >
            {busy ? "…" : "Start"}
          </button>
        )}
        {running && app?.url && (
          <a className="pv-link" href={app.url} target="_blank" rel="noreferrer">open ↗</a>
        )}
        {project.github_repo_url && (
          <a className="pv-link" href={project.github_repo_url} target="_blank" rel="noreferrer">
            github ↗
          </a>
        )}
        <span style={{ flex: 1 }} />
        <button
          className="pv-expand-toggle"
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
        >
          {expanded ? "▴ less" : "▾ detail"}
        </button>
      </div>

      {expanded && (
        inRegistry
          ? <CardDetail appId={appId} detail={detail} plan={plan} />
          : <div style={{ marginTop: 10, fontSize: 11, color: "var(--text-dim)", fontStyle: "italic" }}>
              Not discovered by the app registry (no app.json?) — status and launch unavailable.
            </div>
      )}
    </div>
  );
}

// ── main view ────────────────────────────────────────────────────────────────
export default function ProjectsView() {
  useScopedStyles();

  const [projects, setProjects] = useState(null);   // null = loading
  const [ledgerOk, setLedgerOk] = useState(true);
  const [apps, setApps] = useState({});             // app_id → enriched app row
  const [sidecarOk, setSidecarOk] = useState(true);
  const [busy, setBusy] = useState({});             // app_id → bool
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  const loadProjects = useCallback(() => {
    get("/api/projects")
      .then((d) => { setProjects(d.projects || []); setLedgerOk(d.available !== false); })
      .catch(() => { setProjects([]); setLedgerOk(false); });
  }, []);

  const loadApps = useCallback(() => {
    get("/api/apps")
      .then((d) => {
        setApps(Object.fromEntries((d.apps || []).map((a) => [a.id, a])));
        setSidecarOk(true);
      })
      .catch(() => setSidecarOk(false));
  }, []);

  useEffect(() => { loadProjects(); }, [loadProjects]);

  // Adaptive status polling (usePoll pattern: fast retry while the sidecar is down).
  useEffect(() => {
    loadApps();
    const ms = sidecarOk ? POLL_MS : POLL_MS_DOWN;
    pollRef.current = setInterval(loadApps, ms);
    return () => clearInterval(pollRef.current);
  }, [sidecarOk, loadApps]);

  const onAction = useCallback(async (appId, action) => {
    setBusy((b) => ({ ...b, [appId]: true }));
    setError(null);
    try {
      await post(`/api/apps/${appId}/${action}`);
    } catch (e) {
      setError(`${action} ${appId} failed — ${e.message}`);
    } finally {
      setBusy((b) => ({ ...b, [appId]: false }));
      loadApps();
    }
  }, [loadApps]);

  const runningCount = Object.values(apps).filter((a) => a.running).length;

  return (
    <div style={{ padding: "var(--density-pad)", overflowY: "auto", height: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <span style={{ fontSize: 12, color: "var(--text-dim)", fontFamily: "var(--mono)" }}>
          {projects == null ? "loading…" : `${projects.length} projects · ${runningCount} running`}
        </span>
        {!ledgerOk && (
          <span style={{ fontSize: 11, color: "var(--yellow)" }}>
            ledger unavailable (MySQL down?)
          </span>
        )}
        {!sidecarOk && (
          <span style={{ fontSize: 11, color: "var(--red)" }}>sidecar unreachable</span>
        )}
        <span style={{ flex: 1 }} />
        <button className="pv-btn" onClick={() => { loadProjects(); loadApps(); }}>
          ↻ Refresh
        </button>
      </div>

      {error && (
        <div style={{
          marginBottom: 10, padding: "8px 12px", borderRadius: 6, fontSize: 12,
          border: "1px solid var(--red)", color: "var(--red)", background: "var(--bg-inset)",
        }}>
          {error}
        </div>
      )}

      {projects != null && projects.length === 0 && (
        <div style={{ color: "var(--text-dim)", fontSize: 13, padding: 20 }}>
          No projects in the ledger yet
          {ledgerOk ? " — scaffold one via SysOps → Codehome Hub → ＋ New Project." : "."}
        </div>
      )}

      <div className="pv-grid">
        {(projects || []).map((p) => (
          <ProjectCard
            key={p.id}
            project={p}
            app={apps[p.id]}
            busy={!!busy[p.id]}
            onAction={onAction}
          />
        ))}
      </div>
    </div>
  );
}
