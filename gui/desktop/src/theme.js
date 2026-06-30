// Agentic OS — theme registry + runtime switch (FR-60)
//
// The token values live in theme.css (:root + per-theme [data-theme] blocks).
// This module owns the *selection*: which key is active, persistence, and the
// applyTheme() that flips `document.documentElement[data-theme]`.
//
// The native View ▸ Theme menu (lib.rs) drives this through the
// window.__agenticOsSetTheme bridge exposed in App.jsx — the exact mirror of
// the existing __agenticOsSetView view-switch bridge (FR-51).

export const THEMES = [
  // Terracotta
  { key: "terracotta-light", label: "Terracotta Light" },
  { key: "terracotta-dark",  label: "Terracotta Dark" },

  // Cyber
  { key: "cyber-light",      label: "Cyber Neon Light" },
  { key: "cyber-dark",       label: "Cyber Neon Dark" },

  // Future
  { key: "future-light",     label: "Bold Futuristic Light" },
  { key: "future-dark",      label: "Bold Futuristic Dark" },

  // Terminal
  { key: "term-light",       label: "Terminal Green Light" },
  { key: "term-dark",        label: "Terminal Green Dark" },
];

// Legacy theme aliases (for backward compatibility)
const LEGACY_THEMES = {
  "terra": "terracotta-dark",
  "cyber": "cyber-dark",
  "future": "future-dark",
  "term": "term-dark",
};

const LS_KEY = "agentic-os.theme";
const DEFAULT = "terracotta-dark";

const isKnown = (key) => THEMES.some((t) => t.key === key) || LEGACY_THEMES.hasOwnProperty(key);

export function loadTheme() {
  try {
    const saved = localStorage.getItem(LS_KEY);
    if (saved && isKnown(saved)) {
      // Upgrade legacy keys to new names
      return LEGACY_THEMES[saved] || saved;
    }
  } catch {}
  return DEFAULT;
}

export function applyTheme(key) {
  let next = key;
  // Upgrade legacy keys to new names
  if (LEGACY_THEMES.hasOwnProperty(next)) {
    next = LEGACY_THEMES[next];
  }
  // Validate and fall back to default
  next = THEMES.some((t) => t.key === next) ? next : DEFAULT;
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem(LS_KEY, next); } catch {}
  return next;
}
