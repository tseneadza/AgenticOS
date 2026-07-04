// Agentic OS — user settings registry (Settings rework)
//
// Mirrors theme.js: values persist in localStorage under ONE key; this module
// owns load/save/subscribe plus the derived helpers the rest of the app
// consumes (pollMs, sidecarUrl). Components must never read the raw
// localStorage key directly — import helpers from here.
//
// History: the Phase 9 EnvironmentPanel wrote API keys + feature toggles here
// that NOTHING consumed (dark_mode duplicated theme.js, api keys sat in
// plaintext, intervals were ignored). loadSettings() purges those legacy
// fields on sight so stale secrets don't linger in localStorage.

const LS_KEY = "agentic-os.settings";

export const DEFAULT_SIDECAR_URL = "http://localhost:5130";

// Poll-speed multipliers applied to each view's base interval.
// (Base intervals stay hardcoded per-view — they encode per-view knowledge
// like ProjectsView's fast-retry-while-down; the speed setting scales them.)
export const POLL_SPEEDS = [
  { key: "slow",   label: "Slow",   hint: "2× intervals — lighter on the sidecar", factor: 2 },
  { key: "normal", label: "Normal", hint: "default cadence",                        factor: 1 },
  { key: "fast",   label: "Fast",   hint: "½ intervals — snappier, chattier",       factor: 0.5 },
];

export const DEFAULTS = {
  polling_speed: "normal",
  sidecar_url: DEFAULT_SIDECAR_URL,
};

// Phase 9 fields nothing ever consumed — purged (rewritten out) on load.
const LEGACY_KEYS = [
  "anthropic_api_key", "github_token", "dark_mode", "animations",
  "auto_refresh", "log_refresh_interval", "api_timeout",
];

export function loadSettings() {
  let stored = {};
  try { stored = JSON.parse(localStorage.getItem(LS_KEY)) || {}; } catch { /* corrupt → defaults */ }
  const hadLegacy = LEGACY_KEYS.some((k) => k in stored);
  const clean = {};
  for (const k of Object.keys(DEFAULTS)) {
    if (k in stored) clean[k] = stored[k];
  }
  const settings = { ...DEFAULTS, ...clean };
  if (hadLegacy) {
    // One-time migration: rewrite without dead fields (drops stored api keys).
    try { localStorage.setItem(LS_KEY, JSON.stringify(settings)); } catch {}
  }
  return settings;
}

export function saveSettings(patch) {
  const next = { ...loadSettings(), ...patch };
  try { localStorage.setItem(LS_KEY, JSON.stringify(next)); } catch {}
  try {
    window.dispatchEvent(new CustomEvent("agentic-os:settings-changed", { detail: next }));
  } catch {}
  return next;
}

export function resetSettings() {
  return saveSettings({ ...DEFAULTS });
}

// Subscribe to settings changes (same-window). Returns an unsubscribe fn.
export function subscribeSettings(fn) {
  const handler = (e) => fn(e.detail || loadSettings());
  window.addEventListener("agentic-os:settings-changed", handler);
  return () => window.removeEventListener("agentic-os:settings-changed", handler);
}

// Scale a view's base poll interval by the user's polling speed.
export function pollMs(baseMs) {
  const speed = loadSettings().polling_speed;
  const factor = POLL_SPEEDS.find((s) => s.key === speed)?.factor ?? 1;
  return Math.round(baseMs * factor);
}

// Sidecar base URL — trimmed, no trailing slash, http(s) only, else default.
export function sidecarUrl() {
  const raw = (loadSettings().sidecar_url || "").trim().replace(/\/+$/, "");
  return /^https?:\/\/.+/.test(raw) ? raw : DEFAULT_SIDECAR_URL;
}

// ws:// (or wss://) equivalent of sidecarUrl, with optional path appended.
export function sidecarWsUrl(path = "") {
  return sidecarUrl().replace(/^http/, "ws") + path;
}

// "host:port" of the sidecar for status labels / error messages.
export function sidecarHost() {
  try { return new URL(sidecarUrl()).host; } catch { return "localhost:5130"; }
}
