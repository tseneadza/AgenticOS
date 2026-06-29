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
  { key: "terra",  label: "Terracotta Dark" },
  { key: "cyber",  label: "Cyber Neon" },
  { key: "future", label: "Bold Futuristic" },
  { key: "term",   label: "Terminal Green" },
];

const LS_KEY = "agentic-os.theme";
const DEFAULT = "terra";

const isKnown = (key) => THEMES.some((t) => t.key === key);

export function loadTheme() {
  try {
    const saved = localStorage.getItem(LS_KEY);
    if (saved && isKnown(saved)) return saved;
  } catch {}
  return DEFAULT;
}

export function applyTheme(key) {
  const next = isKnown(key) ? key : DEFAULT;
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem(LS_KEY, next); } catch {}
  return next;
}
