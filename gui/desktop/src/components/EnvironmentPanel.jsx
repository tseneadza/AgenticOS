import { useCallback, useEffect, useRef, useState } from "react";
import { THEMES, loadTheme, applyTheme } from "../theme";
import {
  loadSettings, saveSettings, resetSettings,
  POLL_SPEEDS, DEFAULT_SIDECAR_URL, sidecarUrl,
} from "../settings";
import pkg from "../../package.json";

// ─────────────────────────────────────────────────────────────────────────
// EnvironmentPanel — the Settings view (reworked).
//
// Every control here is wired to real behavior:
//   Appearance  → theme.js applyTheme (synced with the native View ▸ Theme
//                 menu via the window.__agenticOsSetTheme bridge, FR-60)
//   Polling     → settings.pollMs(), consumed by ProjectsView, explorers,
//                 WorkflowsWorkspace, ToolCallVisualizer
//   Connection  → settings.sidecarUrl(), consumed by api.js + all explorers
//   Diagnostics → read-only live info (sidecar reachability, version, storage)
//
// The Phase 9 panel stored API keys + toggles nothing consumed; settings.js
// purges those legacy fields from localStorage on load.
// ─────────────────────────────────────────────────────────────────────────

// Scoped stylesheet (conventions rule 3 — hover states need real CSS).
const STYLE_ID = "sv-styles";
const STYLE_CSS = `
.sv-theme-btn {
  padding: 8px 10px; border: 1px solid var(--border-soft); border-radius: 4px;
  background: var(--bg-inset); color: var(--text); font-size: 12px;
  cursor: pointer; text-align: left; transition: border-color 100ms, background 100ms;
}
.sv-theme-btn:hover { border-color: var(--border); }
.sv-theme-btn.sv-active {
  border-color: var(--accent); background: var(--bg-panel);
  box-shadow: inset 0 0 0 1px var(--accent);
}
.sv-speed-btn {
  flex: 1; padding: 8px 10px; border: 1px solid var(--border-soft); border-radius: 4px;
  background: var(--bg-inset); color: var(--text); font-size: 12px;
  cursor: pointer; transition: border-color 100ms, background 100ms;
}
.sv-speed-btn:hover { border-color: var(--border); }
.sv-speed-btn.sv-active {
  border-color: var(--accent); background: var(--bg-panel);
  box-shadow: inset 0 0 0 1px var(--accent);
}
.sv-btn {
  padding: 6px 12px; border: 1px solid var(--border); border-radius: 4px;
  background: transparent; color: var(--text-dim); cursor: pointer;
  font-size: 12px; transition: color 100ms, border-color 100ms;
}
.sv-btn:hover { color: var(--text); }
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

// ─── Section wrapper ──────────────────────────────────────────────────────

function Section({ title, hint, children }) {
  return (
    <div style={{ marginBottom: "28px" }}>
      <div
        style={{
          fontSize: "13px", fontWeight: 600, color: "var(--accent)",
          marginBottom: "4px", paddingBottom: "6px",
          borderBottom: "1px solid var(--border-soft)",
        }}
      >
        {title}
      </div>
      {hint && (
        <div style={{ fontSize: "11px", color: "var(--text-dim)", margin: "6px 0 10px" }}>
          {hint}
        </div>
      )}
      {children}
    </div>
  );
}

// ─── Diagnostics row ──────────────────────────────────────────────────────

function DiagRow({ label, children, testid }) {
  return (
    <div
      data-testid={testid}
      style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "6px 8px", borderBottom: "1px solid var(--border-soft)",
        fontSize: "12px",
      }}
    >
      <span style={{ color: "var(--text-dim)" }}>{label}</span>
      <span style={{ fontFamily: "var(--mono)", color: "var(--text)" }}>{children}</span>
    </div>
  );
}

// Approximate bytes used by the app's localStorage keys.
function storageUsage() {
  let bytes = 0, count = 0;
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      bytes += k.length + (localStorage.getItem(k)?.length || 0);
      count++;
    }
  } catch {}
  return { bytes, count };
}

// ─── Main component ───────────────────────────────────────────────────────

export default function EnvironmentPanel({ onClose }) {
  useScopedStyles();

  const [settings, setSettings] = useState(loadSettings);
  const [theme, setTheme] = useState(loadTheme);
  const [urlDraft, setUrlDraft] = useState(() => loadSettings().sidecar_url);
  const [urlError, setUrlError] = useState("");
  const [testResult, setTestResult] = useState(null); // {ok, label}
  const [testing, setTesting] = useState(false);
  const [saved, setSaved] = useState(false);
  const [sidecarUp, setSidecarUp] = useState(null);
  const [storage, setStorage] = useState(storageUsage);
  const savedTimer = useRef(null);

  const flashSaved = useCallback(() => {
    setSaved(true);
    clearTimeout(savedTimer.current);
    savedTimer.current = setTimeout(() => setSaved(false), 1500);
  }, []);
  useEffect(() => () => clearTimeout(savedTimer.current), []);

  const update = useCallback((patch) => {
    setSettings(saveSettings(patch));
    setStorage(storageUsage());
    flashSaved();
  }, [flashSaved]);

  // ── Appearance ──
  const pickTheme = useCallback((key) => {
    // Prefer the App.jsx bridge (FR-60) so the HUD window re-skins and the
    // native View ▸ Theme menu stays in sync; fall back to applyTheme.
    if (typeof window.__agenticOsSetTheme === "function") {
      window.__agenticOsSetTheme(key);
    } else {
      applyTheme(key);
    }
    setTheme(key);
    flashSaved();
  }, [flashSaved]);

  // ── Connection ──
  const validateUrl = (raw) => {
    const v = (raw || "").trim();
    if (!/^https?:\/\/.+/.test(v)) return "Must start with http:// or https://";
    try { new URL(v); } catch { return "Not a valid URL"; }
    return "";
  };

  const commitUrl = useCallback((raw) => {
    const err = validateUrl(raw);
    setUrlError(err);
    if (!err) {
      update({ sidecar_url: raw.trim().replace(/\/+$/, "") });
      setTestResult(null);
    }
  }, [update]);

  const testConnection = useCallback(async () => {
    const candidate = (urlDraft || "").trim().replace(/\/+$/, "");
    if (validateUrl(candidate)) { setTestResult({ ok: false, label: "invalid URL" }); return; }
    setTesting(true);
    setTestResult(null);
    try {
      const r = await fetch(`${candidate}/api/health`, { signal: AbortSignal.timeout(2500) });
      setTestResult(r.ok ? { ok: true, label: "online" } : { ok: false, label: `HTTP ${r.status}` });
    } catch {
      setTestResult({ ok: false, label: "unreachable" });
    } finally {
      setTesting(false);
    }
  }, [urlDraft]);

  // ── Diagnostics: sidecar reachability on mount ──
  useEffect(() => {
    let alive = true;
    fetch(`${sidecarUrl()}/api/health`, { signal: AbortSignal.timeout(2500) })
      .then((r) => { if (alive) setSidecarUp(r.ok); })
      .catch(() => { if (alive) setSidecarUp(false); });
    return () => { alive = false; };
  }, [settings.sidecar_url]);

  // ── Reset all ──
  const handleReset = useCallback(() => {
    if (!confirm("Reset all settings to defaults? (Theme is kept.)")) return;
    const next = resetSettings();
    setSettings(next);
    setUrlDraft(next.sidecar_url);
    setUrlError("");
    setTestResult(null);
    flashSaved();
  }, [flashSaved]);

  const activeThemeLabel = THEMES.find((t) => t.key === theme)?.label || theme;

  return (
    <div
      data-testid="environment-panel"
      style={{
        display: "flex", flexDirection: "column", height: "100%",
        background: "var(--bg)", color: "var(--text)",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "12px 16px", borderBottom: "1px solid var(--border)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "14px", fontWeight: 600 }}>Settings</h2>
        {onClose && (
          <button
            data-testid="close-settings"
            onClick={onClose}
            style={{
              background: "transparent", border: "none", color: "var(--text-dim)",
              cursor: "pointer", fontSize: "16px",
            }}
          >
            ✕
          </button>
        )}
      </div>

      {/* Content */}
      <div data-testid="settings-content" style={{ flex: 1, overflow: "auto", padding: "16px", maxWidth: "560px" }}>
        {/* ── Appearance ── */}
        <Section title="Appearance" hint="Applies instantly, syncs with the native View ▸ Theme menu, and persists across restarts.">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "8px" }}>
            {THEMES.map((t) => (
              <button
                key={t.key}
                data-testid={`theme-option-${t.key}`}
                className={`sv-theme-btn${theme === t.key ? " sv-active" : ""}`}
                onClick={() => pickTheme(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>
        </Section>

        {/* ── Polling ── */}
        <Section
          title="Polling speed"
          hint="Scales the refresh cadence of Projects, health chips, API/Scripts explorers, and Workflows. Open views pick the new speed up when re-opened."
        >
          <div style={{ display: "flex", gap: "8px" }}>
            {POLL_SPEEDS.map((s) => (
              <button
                key={s.key}
                data-testid={`polling-${s.key}`}
                className={`sv-speed-btn${settings.polling_speed === s.key ? " sv-active" : ""}`}
                onClick={() => update({ polling_speed: s.key })}
              >
                <div style={{ fontWeight: 500 }}>{s.label}</div>
                <div style={{ fontSize: "11px", color: "var(--text-dim)" }}>{s.hint}</div>
              </button>
            ))}
          </div>
        </Section>

        {/* ── Connection ── */}
        <Section
          title="Sidecar connection"
          hint={`Base URL of the AgenticOS sidecar (default ${DEFAULT_SIDECAR_URL}). Used by every view; applies immediately to new requests.`}
        >
          <div style={{ display: "flex", gap: "6px" }}>
            <input
              data-testid="sidecar-url-input"
              type="text"
              value={urlDraft}
              onChange={(e) => setUrlDraft(e.target.value)}
              onBlur={() => commitUrl(urlDraft)}
              onKeyDown={(e) => { if (e.key === "Enter") commitUrl(urlDraft); }}
              spellCheck={false}
              style={{
                flex: 1, padding: "6px 8px", borderRadius: "var(--radius-sm)",
                border: urlError ? "2px solid var(--red)" : "1px solid var(--border)",
                background: "var(--bg-inset)", color: "var(--text)",
                fontSize: "12px", fontFamily: "var(--mono)",
              }}
            />
            <button data-testid="test-connection" className="sv-btn" onClick={testConnection} disabled={testing}>
              {testing ? "Testing…" : "Test"}
            </button>
            <button
              data-testid="reset-sidecar-url"
              className="sv-btn"
              onClick={() => { setUrlDraft(DEFAULT_SIDECAR_URL); commitUrl(DEFAULT_SIDECAR_URL); }}
            >
              Default
            </button>
          </div>
          {urlError && (
            <div data-testid="sidecar-url-error" style={{ marginTop: "4px", fontSize: "11px", color: "var(--red)" }}>
              {urlError}
            </div>
          )}
          {testResult && (
            <div
              data-testid="test-result"
              style={{ marginTop: "4px", fontSize: "11px", color: testResult.ok ? "var(--green)" : "var(--red)" }}
            >
              {testResult.ok ? "✓" : "✗"} {testResult.label}
            </div>
          )}
        </Section>

        {/* ── Diagnostics ── */}
        <Section title="Diagnostics" hint="Read-only snapshot — refreshed when you open Settings or change the sidecar URL.">
          <div style={{ border: "1px solid var(--border-soft)", borderRadius: "var(--radius-sm)", background: "var(--bg-inset)" }}>
            <DiagRow label="Sidecar" testid="diag-sidecar">
              {sidecarUp == null ? "checking…" : sidecarUp ? (
                <span style={{ color: "var(--green)" }}>● online</span>
              ) : (
                <span style={{ color: "var(--red)" }}>● offline</span>
              )}
            </DiagRow>
            <DiagRow label="Sidecar URL" testid="diag-url">{sidecarUrl()}</DiagRow>
            <DiagRow label="App version" testid="diag-version">{pkg.version}</DiagRow>
            <DiagRow label="Active theme" testid="diag-theme">{activeThemeLabel}</DiagRow>
            <DiagRow label="Local storage" testid="diag-storage">
              {storage.count} keys · {(storage.bytes / 1024).toFixed(1)} KB
            </DiagRow>
          </div>
        </Section>
      </div>

      {/* Footer */}
      <div
        style={{
          padding: "12px 16px", borderTop: "1px solid var(--border)",
          display: "flex", gap: "8px", justifyContent: "flex-end", alignItems: "center",
        }}
      >
        {saved && (
          <div data-testid="save-indicator" style={{ color: "var(--green)", fontSize: "12px" }}>
            ✓ Saved
          </div>
        )}
        <button data-testid="reset-settings" className="sv-btn" onClick={handleReset}>
          Reset to Defaults
        </button>
      </div>
    </div>
  );
}
