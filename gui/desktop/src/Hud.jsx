// Agentic OS — HUD (Phase 14, FR-63/63a)
//
// Floating, always-on-top mini view rendered in the second WebviewWindow
// (index.html#/hud). It mirrors the main sidebar: the OSA brand header, the
// same nav list, and the live Diagnostics panel (reused verbatim, forced open),
// plus the top approval inline so the urgent HITL moment is actionable without
// expanding. Themes for free via the shared tokens + App.css classes.
//
// Nav clicks emit a Tauri "goto-view" event (App.jsx listens, switches view),
// then re-show + focus the main window and hide the HUD. The same window calls
// back the "Minimize to HUD" path in App.jsx / the native Window menu.
import { useEffect, useState } from "react";
import { get, post } from "./api";
import { applyTheme, loadTheme } from "./theme";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { WebviewWindow } from "@tauri-apps/api/webviewWindow";
import { emit, listen } from "@tauri-apps/api/event";
import DiagnosticsPanel from "./components/DiagnosticsPanel";
import "./App.css";

// Mirrors the VIEWS registry in App.jsx (id + label). Order locked to match.
const NAV = [
  { id: "sysops", label: "SysOps", badge: true },
  { id: "workflows", label: "Workflows" },
  { id: "web-news", label: "Web News" },
  { id: "scripts", label: "Scripts" },
  { id: "zsh-config", label: "Zsh Config Editor" },
  { id: "obsidian", label: "Obsidian Viewer" },
  { id: "hub-api", label: "Hub API" },
  { id: "agent", label: "Agent", badge: true },
];
const VIEW_KEY = "agentic-os.activeView";

// Minimal poller (the HUD is light; no adaptive recovery needed).
function usePoll(path, ms) {
  const [data, setData] = useState(null);
  useEffect(() => {
    let alive = true;
    const tick = () =>
      get(path)
        .then((d) => { if (alive) setData(d); })
        .catch(() => { if (alive) setData({ available: false }); });
    tick();
    const id = setInterval(tick, ms);
    return () => { alive = false; clearInterval(id); };
  }, [path, ms]);
  return data;
}

async function showMain() {
  const main = await WebviewWindow.getByLabel("main");
  if (main) { await main.show(); await main.setFocus(); }
  await getCurrentWindow().hide();
}

export default function Hud() {
  const [approvals, setApprovals] = useState([]);
  const [active, setActive] = useState(() => {
    try { return localStorage.getItem(VIEW_KEY) || "sysops"; } catch { return "sysops"; }
  });
  const sys = usePoll("/api/panels/system", 2000);
  const apr = usePoll("/api/approvals", 1500);

  // Apply the theme the main window persisted on mount, then stay in sync with
  // live changes broadcast from the app (FR-60) so the HUD always shows the
  // theme last set in the app.
  useEffect(() => {
    applyTheme(loadTheme());
    const un = listen("theme-changed", (e) => applyTheme(e.payload));
    return () => { un.then((f) => f()).catch(() => {}); };
  }, []);
  useEffect(() => { if (apr?.approvals) setApprovals(apr.approvals); }, [apr]);

  const decide = (id, decision) =>
    post(`/api/approvals/${id}`, { decision })
      .then(() => setApprovals((a) => a.filter((x) => (x.approval_id ?? x.id) !== id)))
      .catch(() => {});

  // Jump to a view in the full app: tell main, then expand to it.
  const goTo = async (id) => {
    setActive(id);
    try { await emit("goto-view", id); } catch { /* not under Tauri */ }
    try { await showMain(); } catch { /* not under Tauri */ }
  };

  const expand = async () => { try { await showMain(); } catch { /* not under Tauri */ } };

  const top = approvals[0];
  const topId = top ? (top.approval_id ?? top.id) : null;
  const topLabel = top
    ? (top.question ?? top.prompt ?? top.tool ?? top.summary ?? "Approval required")
    : null;

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: "var(--bg)", color: "var(--text)", overflow: "hidden" }}>
      {/* Brand header (matches the sidebar) — draggable, with Expand */}
      <div className="brand" data-tauri-drag-region style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>OSA<small>agentic os · v0.4</small></div>
        <button className="hud-btn" style={{ margin: 0, padding: "4px 9px", fontSize: 11 }} onClick={expand} title="Expand to the full app">
          ⤢ Expand
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto" }}>
        {/* Nav — same items as the sidebar; click jumps to that view in the app */}
        <nav className="nav">
          {NAV.map((v) => (
            <button
              key={v.id}
              className={`nav-item${v.id === active ? " active" : ""}`}
              onClick={() => goTo(v.id)}
            >
              {v.label}
              {v.badge && approvals.length > 0 && (
                <span className="nav-badge">{approvals.length}</span>
              )}
            </button>
          ))}
        </nav>

        {/* Top approval — the HUD's reason to exist (inline Allow/Deny) */}
        {top && (
          <div className="side-section">
            <h3>Pending approval</h3>
            <div style={{ padding: "0 16px" }}>
              <div className="agent-approval">
                <div className="q">{topLabel}</div>
                <div className="agent-approval-actions">
                  <button className="btn approve" onClick={() => decide(topId, "approve")}>✓ Allow</button>
                  <button className="btn deny" onClick={() => decide(topId, "deny")}>✕ Deny</button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Live diagnostics — same component as the sidebar, forced open */}
        <div className="sidebar-diagnostics">
          <DiagnosticsPanel data={sys} forceExpanded />
        </div>
      </div>
    </div>
  );
}
