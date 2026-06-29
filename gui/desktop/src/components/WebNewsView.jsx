/**
 * WebNewsView — Science RSS reader with keyword pre-filter + AI relevance ranking
 *
 * Architecture:
 *   1. User picks domains + keywords (persisted to localStorage)
 *   2. On "Fetch" → POST /api/news/fetch with selected feed URLs + keywords
 *   3. Sidecar fetches/caches feeds (15 min TTL), keyword-filters, returns items
 *   4. (Optional) "Rank with AI" → Claude API call scores each item 0-10 for relevance
 *   5. Items displayed as card list, sorted by AI score or date
 */
import { useState, useEffect, useLayoutEffect, useCallback, useRef } from "react";

const SIDECAR = "http://localhost:5130";

// Built-in defaults — used as a fallback until /api/news/categories responds
// (or if MySQL is unavailable). The live catalogue comes from the DB.
const DEFAULT_CATEGORIES = [
  { id: "physics-space",       name: "Physics & Space",          color: "#7b9fd4" },
  { id: "biology-life",        name: "Biology & Life Sciences",  color: "#7fb069" },
  { id: "ai-ml",               name: "AI & Machine Learning",    color: "#d97b4f" },
  { id: "neuroscience",        name: "Neuroscience",             color: "#c47bd9" },
  { id: "mathematics",         name: "Mathematics",              color: "#e0b84c" },
  { id: "engineering-tech",    name: "Engineering & Technology", color: "#4fd9c4" },
  { id: "chemistry-materials", name: "Chemistry & Materials",    color: "#d94f8a" },
  { id: "climate-earth",       name: "Climate & Earth Science",  color: "#4fa8d9" },
];

const DOMAIN_COLORS = Object.fromEntries(DEFAULT_CATEGORIES.map(c => [c.name, c.color]));
const ALL_DOMAINS = DEFAULT_CATEGORIES.map(c => c.name);

const LS_KEY = "agentic-os.webnews";

// ── component-scoped stylesheet (hover, transitions, skeleton shimmer) ───────
const STYLE_ID = "wnv-styles";
const STYLE_CSS = `
.wnv-card {
  position: relative;
  padding: 12px 14px 12px 16px;
  border-radius: 8px;
  background: var(--bg-panel);
  border: 1px solid var(--border-soft);
  border-left-width: 3px;
  margin-bottom: 10px;
  transition: transform 0.12s ease, border-color 0.12s ease, box-shadow 0.12s ease;
}
.wnv-card:hover {
  transform: translateY(-1px);
  border-color: var(--accent);
  box-shadow: 0 4px 14px rgba(0,0,0,0.28);
}
.wnv-title {
  color: var(--text);
  text-decoration: none;
  font-weight: 600;
  font-size: 13.5px;
  line-height: 1.42;
  display: block;
  letter-spacing: 0.1px;
}
.wnv-card:hover .wnv-title { color: var(--accent); }
.wnv-pill {
  all: unset; cursor: pointer; box-sizing: border-box;
  padding: 3px 9px; border-radius: 999px;
  font-size: 10px; font-family: var(--mono); letter-spacing: 0.3px;
  border: 1px solid var(--border-soft);
  color: var(--text-dim); background: var(--bg-inset);
  transition: all 0.12s ease; white-space: nowrap;
}
.wnv-pill:hover { color: var(--text); border-color: var(--text-dim); }
.wnv-btn {
  all: unset; cursor: pointer; box-sizing: border-box;
  padding: 6px 12px; border-radius: 6px;
  font-family: var(--mono); font-size: 11px;
  border: 1px solid var(--border-soft);
  color: var(--text); background: var(--bg-inset);
  transition: all 0.12s ease;
}
.wnv-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.wnv-btn:disabled { cursor: default; color: var(--text-dim); opacity: 0.6; }
.wnv-btn-primary {
  background: var(--accent); color: var(--bg); border-color: var(--accent); font-weight: 700;
}
.wnv-btn-primary:hover:not(:disabled) { filter: brightness(1.08); color: var(--bg); }
.wnv-skel {
  border-radius: 8px; margin-bottom: 10px; height: 84px;
  background: linear-gradient(100deg, var(--bg-panel) 30%, var(--bg-inset) 50%, var(--bg-panel) 70%);
  background-size: 220% 100%;
  animation: wnv-shimmer 1.4s ease-in-out infinite;
  border: 1px solid var(--border-soft);
}
@keyframes wnv-shimmer { 0% { background-position: 180% 0; } 100% { background-position: -40% 0; } }
.wnv-scroll::-webkit-scrollbar { width: 9px; }
.wnv-scroll::-webkit-scrollbar-thumb { background: var(--border-soft); border-radius: 5px; }
.wnv-scroll::-webkit-scrollbar-track { background: transparent; }
.wnv-thumb {
  width: 104px; height: 78px; flex-shrink: 0;
  object-fit: cover; border-radius: 6px;
  border: 1px solid var(--border-soft); background: var(--bg-inset);
}
.wnv-thumb-top {
  width: 100%; height: 132px; flex-shrink: 0;
  object-fit: cover; border-radius: 6px;
  border: 1px solid var(--border-soft); background: var(--bg-inset);
  margin-bottom: 10px;
}
.wnv-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--wnv-col, 320px), 1fr));
  gap: 10px; align-items: start; margin-bottom: 8px;
}
.wnv-grid .wnv-card { margin-bottom: 0; }
.wnv-cat { transition: background 0.12s ease, border-color 0.12s ease; }
.wnv-cat:hover { border-color: var(--text-dim); background: var(--bg-panel); }
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

function loadPrefs() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  return {
    domains: ALL_DOMAINS,
    keywords: ["quantum", "neural", "LLM", "genome", "dark matter", "climate", "protein", "transformer"],
    feedIds: null, // null = all feeds for selected domains
  };
}

function savePrefs(prefs) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(prefs)); } catch {}
}

const LS_COLLAPSED = "agentic-os.webnews.collapsed";
function loadCollapsed() {
  try {
    const raw = localStorage.getItem(LS_COLLAPSED);
    if (raw) return new Set(JSON.parse(raw));
  } catch {}
  return new Set();
}
function saveCollapsed(set) {
  try { localStorage.setItem(LS_COLLAPSED, JSON.stringify([...set])); } catch {}
}

const LS_VIEW = "agentic-os.webnews.view";
function loadView() { try { return localStorage.getItem(LS_VIEW) || "list"; } catch { return "list"; } }
const LS_DENSITY = "agentic-os.webnews.density";
const DENSITY_PX = { compact: 340, cozy: 440, comfy: 560 };
function loadDensity() { try { return localStorage.getItem(LS_DENSITY) || "cozy"; } catch { return "cozy"; } }

// relative "time ago" from an ISO-ish published string
function timeAgo(published) {
  if (!published) return "";
  const then = new Date(published);
  if (isNaN(then)) return published.slice(0, 16);
  const secs = Math.max(0, (Date.now() - then.getTime()) / 1000);
  if (secs < 90) return "just now";
  const mins = secs / 60;
  if (mins < 60) return `${Math.round(mins)}m ago`;
  const hrs = mins / 60;
  if (hrs < 24) return `${Math.round(hrs)}h ago`;
  const days = hrs / 24;
  if (days < 7) return `${Math.round(days)}d ago`;
  return then.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// ── small helpers ──────────────────────────────────────────────────────────

function DomainBadge({ domain, small, colors = DOMAIN_COLORS }) {
  const color = colors[domain] || DOMAIN_COLORS[domain] || "var(--text-dim)";
  return (
    <span style={{
      display: "inline-block",
      padding: small ? "1px 6px" : "2px 8px",
      borderRadius: 4,
      background: color + "1f",
      border: `1px solid ${color}55`,
      color,
      fontSize: small ? 9 : 10,
      fontFamily: "var(--mono)",
      fontWeight: 600,
      textTransform: "uppercase",
      letterSpacing: 0.5,
      whiteSpace: "nowrap",
    }}>
      {domain}
    </span>
  );
}

function ScoreBadge({ score }) {
  const n = typeof score === "number" ? score : null;
  const color = n == null ? "var(--text-dim)" : n >= 7 ? "var(--green)" : n >= 4 ? "var(--yellow)" : "var(--red)";
  return (
    <span style={{
      display: "inline-flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      width: 30, height: 30, borderRadius: 8,
      background: color + "22", border: `1.5px solid ${color}`,
      color, fontFamily: "var(--mono)", fontWeight: 700, flexShrink: 0,
      lineHeight: 1,
    }}>
      <span style={{ fontSize: 12 }}>{n ?? "?"}</span>
    </span>
  );
}

function ArticleCard({ item, ranked, colors = DOMAIN_COLORS, layout = "list" }) {
  const [expanded, setExpanded] = useState(false);
  const [overflowing, setOverflowing] = useState(false);
  const [imgOk, setImgOk] = useState(Boolean(item.image));
  const summaryRef = useRef(null);
  const color = colors[item.domain_label] || colors[item.domain] || "var(--border-soft)";
  const grid = layout === "grid";

  // Only show the toggle when the clamped summary actually overflows 2 lines.
  useLayoutEffect(() => {
    const el = summaryRef.current;
    if (!el || expanded) return;
    setOverflowing(el.scrollHeight > el.clientHeight + 2);
  }, [item.summary, expanded]);

  const thumb = item.image && imgOk ? (
    <img
      className={grid ? "wnv-thumb-top" : "wnv-thumb"}
      src={item.image}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setImgOk(false)}
    />
  ) : null;

  return (
    <div
      className="wnv-card"
      style={grid
        ? { borderLeftColor: color, display: "flex", flexDirection: "column" }
        : { borderLeftColor: color }}
    >
      {grid && thumb}
      <div style={{ display: "flex", alignItems: "flex-start", gap: grid ? 8 : 10 }}>
        {ranked && <ScoreBadge score={item._score} />}
        {!grid && thumb}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 5, flexWrap: "wrap" }}>
            <DomainBadge domain={item.domain_label || item.domain} small colors={colors} />
            <span style={{ fontSize: 10, color: "var(--text-dim)", fontFamily: "var(--mono)" }}>
              {item.source_label || item.domain}
            </span>
            {item.published && (
              <span title={item.published} style={{ fontSize: 10, color: "var(--text-dim)", fontFamily: "var(--mono)", marginLeft: "auto" }}>
                {timeAgo(item.published)}
              </span>
            )}
          </div>
          <a className="wnv-title" href={item.link} target="_blank" rel="noopener noreferrer">
            {item.title}
          </a>
          {item.summary && (
            <>
              <p ref={summaryRef} style={expanded ? {
                margin: "6px 0 0", fontSize: 11.5, color: "var(--text-dim)",
                lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word",
              } : {
                margin: "6px 0 0", fontSize: 11.5, color: "var(--text-dim)",
                lineHeight: 1.6,
                display: "-webkit-box",
                WebkitLineClamp: grid ? 3 : 2,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }}>
                {item.summary}
              </p>
              {(overflowing || expanded) && (
                <button
                  onClick={() => setExpanded(e => !e)}
                  style={{
                    all: "unset", cursor: "pointer", fontSize: 10,
                    color: "var(--accent)", marginTop: 4, fontFamily: "var(--mono)",
                  }}
                >
                  {expanded ? "show less ▴" : "show more ▾"}
                </button>
              )}
            </>
          )}
          {ranked && item._reasoning && (
            <p style={{
              margin: "7px 0 0", padding: "5px 8px", borderRadius: 5,
              background: "var(--bg-inset)",
              fontSize: 10.5, color: "var(--yellow)",
              fontStyle: "italic", lineHeight: 1.5,
            }}>
              ✦ {item._reasoning}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// ── settings sidebar ───────────────────────────────────────────────────────

const FIELD_STYLE = {
  all: "unset", boxSizing: "border-box", display: "block", width: "100%",
  padding: "6px 9px", background: "var(--bg-inset)",
  border: "1px solid var(--border-soft)", borderRadius: 5,
  fontFamily: "var(--mono)", fontSize: 11, color: "var(--text)",
};

function SectionLabel({ children }) {
  return (
    <label style={{ display: "block", marginTop: 16, marginBottom: 6, fontSize: 11, color: "var(--text-dim)", fontFamily: "var(--mono)", textTransform: "uppercase", letterSpacing: 0.5 }}>
      {children}
    </label>
  );
}

function SettingsPanel({ allFeeds, prefs, onChange, onClose, categories, colors, reloadCatalogue }) {
  const [domains, setDomains] = useState(prefs.domains);
  const [keywords, setKeywords] = useState(prefs.keywords.join(", "));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [nf, setNf] = useState({ label: "", url: "", category_id: (categories[0] && categories[0].id) || "" });
  const [nc, setNc] = useState({ name: "", color: "#7b9fd4" });

  const feedsByCat = {};
  allFeeds.forEach(f => { (feedsByCat[f.category_id] = feedsByCat[f.category_id] || []).push(f); });

  const api = async (method, path, body) => {
    setBusy(true); setErr(null);
    try {
      const res = await fetch(`${SIDECAR}${path}`, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok && res.status !== 204) {
        const t = await res.text();
        throw new Error(`HTTP ${res.status}: ${t.slice(0, 160)}`);
      }
      await reloadCatalogue();
      return true;
    } catch (e) {
      setErr(e.message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const addFeed = async () => {
    if (!nf.label.trim() || !nf.url.trim() || !nf.category_id) return;
    if (await api("POST", "/api/news/feeds", nf)) setNf({ label: "", url: "", category_id: nf.category_id });
  };
  const addCategory = async () => {
    if (!nc.name.trim()) return;
    if (await api("POST", "/api/news/categories", nc)) setNc({ name: "", color: "#7b9fd4" });
  };

  const apply = () => {
    const kws = keywords.split(",").map(s => s.trim()).filter(Boolean);
    onChange({ ...prefs, domains, keywords: kws });
    onClose();
  };
  const toggleDomain = (d) =>
    setDomains(prev => prev.includes(d) ? prev.filter(x => x !== d) : [...prev, d]);

  return (
    <div style={{
      position: "absolute", top: 0, right: 0, bottom: 0,
      width: 360, background: "var(--bg-panel)",
      borderLeft: "1px solid var(--border-soft)",
      display: "flex", flexDirection: "column", zIndex: 10,
      boxShadow: "-4px 0 24px rgba(0,0,0,0.4)",
    }}>
      <div style={{ padding: "12px 14px 10px", borderBottom: "1px solid var(--border-soft)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: 1, color: "var(--text)" }}>Settings</span>
        <button onClick={onClose} style={{ all: "unset", cursor: "pointer", color: "var(--text-dim)", fontSize: 16 }}>✕</button>
      </div>

      <div className="wnv-scroll" style={{ flex: 1, overflowY: "auto", padding: "4px 14px 14px" }}>
        {err && (
          <div style={{ marginTop: 12, padding: "7px 9px", borderRadius: 5, fontSize: 10.5, fontFamily: "var(--mono)", color: "var(--red)", background: "rgba(217,83,79,0.1)", border: "1px solid rgba(217,83,79,0.3)" }}>
            ⚠ {err}
          </div>
        )}

        {/* keyword filter */}
        <SectionLabel>Keywords (comma-separated)</SectionLabel>
        <textarea
          value={keywords}
          onChange={e => setKeywords(e.target.value)}
          rows={3}
          style={{ ...FIELD_STYLE, lineHeight: 1.6, resize: "vertical" }}
        />

        {/* domain toggles — data-driven from categories */}
        <SectionLabel>Active Domains</SectionLabel>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {categories.map(cat => {
            const d = cat.name;
            const on = domains.includes(d);
            const col = cat.color || "var(--border-soft)";
            const feedCount = (feedsByCat[cat.id] || []).length;
            return (
              <button
                key={cat.id}
                onClick={() => toggleDomain(d)}
                style={{
                  all: "unset", cursor: "pointer",
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "7px 10px", borderRadius: 6,
                  background: on ? col + "18" : "var(--bg-inset)",
                  border: `1px solid ${on ? col + "55" : "var(--border-soft)"}`,
                  transition: "all 0.15s",
                }}
              >
                <span style={{
                  width: 10, height: 10, borderRadius: "50%",
                  background: on ? col : "var(--bg-panel)",
                  border: `2px solid ${col}`, flexShrink: 0,
                }} />
                <span style={{ fontSize: 12, color: "var(--text)", flex: 1 }}>{d}</span>
                <span style={{ fontSize: 10, color: "var(--text-dim)", fontFamily: "var(--mono)" }}>{feedCount} feeds</span>
              </button>
            );
          })}
        </div>

        {/* ── manage feeds ── */}
        <SectionLabel>Manage Feeds</SectionLabel>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 8 }}>
          <input style={FIELD_STYLE} placeholder="Feed name" value={nf.label}
            onChange={e => setNf({ ...nf, label: e.target.value })} />
          <input style={FIELD_STYLE} placeholder="https://…/rss" value={nf.url}
            onChange={e => setNf({ ...nf, url: e.target.value })} />
          <div style={{ display: "flex", gap: 6 }}>
            <select style={{ ...FIELD_STYLE, flex: 1 }} value={nf.category_id}
              onChange={e => setNf({ ...nf, category_id: e.target.value })}>
              {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <button onClick={addFeed} disabled={busy} className="wnv-btn wnv-btn-primary" style={{ fontSize: 11 }}>+ Add</button>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {categories.map(cat => (feedsByCat[cat.id] || []).map(f => (
            <div key={f.id} style={{
              display: "flex", alignItems: "center", gap: 7, padding: "5px 8px",
              borderRadius: 5, background: "var(--bg-inset)",
              border: "1px solid var(--border-soft)", borderLeft: `3px solid ${cat.color}`,
              opacity: f.enabled ? 1 : 0.5,
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 11, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.label}</div>
                <div style={{ fontSize: 9, color: "var(--text-dim)", fontFamily: "var(--mono)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.url}</div>
              </div>
              <button title={f.enabled ? "Disable" : "Enable"} onClick={() => api("PATCH", `/api/news/feeds/${f.id}`, { enabled: !f.enabled })}
                style={{ all: "unset", cursor: "pointer", fontSize: 12, color: f.enabled ? "var(--green)" : "var(--text-dim)" }}>
                {f.enabled ? "◉" : "○"}
              </button>
              <button title="Delete" onClick={() => api("DELETE", `/api/news/feeds/${f.id}`)}
                style={{ all: "unset", cursor: "pointer", fontSize: 12, color: "var(--text-dim)" }}>✕</button>
            </div>
          )))}
        </div>

        {/* ── manage categories ── */}
        <SectionLabel>Manage Categories</SectionLabel>
        <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
          <input style={{ ...FIELD_STYLE, flex: 1 }} placeholder="Category name" value={nc.name}
            onChange={e => setNc({ ...nc, name: e.target.value })} />
          <input type="color" value={nc.color} onChange={e => setNc({ ...nc, color: e.target.value })}
            style={{ all: "unset", width: 30, height: 30, borderRadius: 5, border: "1px solid var(--border-soft)", cursor: "pointer", background: nc.color }} />
          <button onClick={addCategory} disabled={busy} className="wnv-btn wnv-btn-primary" style={{ fontSize: 11 }}>+ Add</button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {categories.map(cat => (
            <div key={cat.id} style={{
              display: "flex", alignItems: "center", gap: 8, padding: "5px 8px",
              borderRadius: 5, background: "var(--bg-inset)", border: "1px solid var(--border-soft)",
            }}>
              <span style={{ width: 12, height: 12, borderRadius: 3, background: cat.color, flexShrink: 0 }} />
              <span style={{ flex: 1, fontSize: 11, color: "var(--text)" }}>{cat.name}</span>
              <span style={{ fontSize: 9, color: "var(--text-dim)", fontFamily: "var(--mono)" }}>{(feedsByCat[cat.id] || []).length} feeds</span>
              <button title="Delete category + its feeds" onClick={() => api("DELETE", `/api/news/categories/${cat.id}`)}
                style={{ all: "unset", cursor: "pointer", fontSize: 12, color: "var(--text-dim)" }}>✕</button>
            </div>
          ))}
        </div>
      </div>

      <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border-soft)" }}>
        <button
          onClick={apply}
          style={{
            all: "unset", cursor: "pointer",
            display: "block", width: "100%", boxSizing: "border-box",
            padding: "9px 0", textAlign: "center",
            background: "var(--accent)", color: "var(--bg)",
            borderRadius: 6, fontFamily: "var(--mono)", fontSize: 12, fontWeight: 700,
          }}
        >
          Apply & Fetch
        </button>
      </div>
    </div>
  );
}

// ── main component ─────────────────────────────────────────────────────────

export default function WebNewsView() {
  useScopedStyles();
  const [prefs, setPrefs]         = useState(loadPrefs);
  const [allFeeds, setAllFeeds]   = useState([]);
  const [items, setItems]         = useState([]);
  const [loading, setLoading]     = useState(false);
  const [ranking, setRanking]     = useState(false);
  const [ranked, setRanked]       = useState(false);
  const [error, setError]         = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sortBy, setSortBy]       = useState("date"); // "date" | "score"
  const [domainFilter, setDomainFilter] = useState("all");
  const [search, setSearch]       = useState("");
  const [collapsed, setCollapsed] = useState(loadCollapsed);
  const [viewMode, setViewMode]   = useState(loadView);
  const [density, setDensity]     = useState(loadDensity);
  const [categories, setCategories] = useState(DEFAULT_CATEGORIES);
  const abortRef = useRef(null);

  // load categories + feed catalogue (MySQL-backed, via the sidecar)
  const loadCatalogue = useCallback(() => {
    fetch(`${SIDECAR}/api/news/categories`)
      .then(r => r.json())
      .then(d => { if (d.categories && d.categories.length) setCategories(d.categories); })
      .catch(() => {});
    return fetch(`${SIDECAR}/api/news/feeds`)
      .then(r => r.json())
      .then(d => setAllFeeds(d.feeds || []))
      .catch(() => {});
  }, []);
  useEffect(() => { loadCatalogue(); }, [loadCatalogue]);

  const activeFeeds = allFeeds.filter(f => prefs.domains.includes(f.domain));

  const fetchNews = useCallback(async (overridePrefs) => {
    const p = overridePrefs || prefs;
    const feeds = allFeeds.filter(f => p.domains.includes(f.domain));
    if (!feeds.length) { setError("No feeds selected."); return; }

    setLoading(true);
    setError(null);
    setRanked(false);
    setItems([]);
    try {
      // Build feed_map: url -> {domain, label} so the sidecar can tag each
      // article at source — avoids ambiguity when multiple feeds share a hostname
      // (e.g. Quanta has feeds for Physics, Math, and Earth Science).
      const feedMap = {};
      feeds.forEach(f => { feedMap[f.url] = { domain: f.domain, label: f.label }; });

      // Fetch WITHOUT keywords — keyword filtering happens client-side below
      // so categories with niche content (e.g. Mathematics) aren't silently
      // wiped out by biology/AI keywords.
      const res = await fetch(`${SIDECAR}/api/news/fetch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls: feeds.map(f => f.url), keywords: [], feed_map: feedMap }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      // Enrich: sidecar now returns domain_label/source_label when feed_map is
      // provided. Fall back to feed_url lookup for any items missing them.
      const urlToFeed = {};
      feeds.forEach(f => { urlToFeed[f.url] = f; });

      const enriched = (data.items || []).map(item => {
        // Prefer server-side enrichment (authoritative, avoids hostname ambiguity)
        if (item.domain_label) return item;
        // Fallback: look up by feed_url tag
        const feed = item.feed_url ? urlToFeed[item.feed_url] : null;
        return {
          ...item,
          domain_label: feed?.domain || item.domain,
          source_label: feed?.label || item.domain,
        };
      });

      // Client-side keyword filter: apply globally, but if a category would be
      // left with zero results, keep its articles unfiltered so it's never blank.
      const keywords = p.keywords.map(k => k.toLowerCase());
      let filtered = enriched;
      if (keywords.length) {
        const matches = (item) => {
          const text = (item.title + " " + (item.summary || "")).toLowerCase();
          return keywords.some(kw => text.includes(kw));
        };
        // Per-category fallback: if filtering empties a category, keep all its items
        const byCategory = {};
        enriched.forEach(item => {
          const cat = item.domain_label || item.domain;
          (byCategory[cat] = byCategory[cat] || []).push(item);
        });
        filtered = enriched.filter(item => {
          if (matches(item)) return true;
          // Keep unfiltered if this item's category would otherwise be empty
          const cat = item.domain_label || item.domain;
          return !byCategory[cat].some(matches);
        });
      }

      setItems(filtered);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [allFeeds, prefs]);

  // auto-fetch on mount once feeds are loaded
  const didInitFetch = useRef(false);
  useEffect(() => {
    if (allFeeds.length && !didInitFetch.current) {
      didInitFetch.current = true;
      fetchNews();
    }
  }, [allFeeds, fetchNews]);

  const handlePrefsChange = (newPrefs) => {
    setPrefs(newPrefs);
    savePrefs(newPrefs);
    fetchNews(newPrefs);
  };

  // AI ranking — runs server-side through the sidecar (core.llm: local Ollama
  // or cloud, whichever model is active in the app). No API key in the frontend.
  const rankWithAI = async () => {
    if (!items.length) return;
    setRanking(true);
    setError(null);
    try {
      const toRank = items.slice(0, 40); // cap for cost/latency
      const res = await fetch(`${SIDECAR}/api/news/rank`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          articles: toRank.map(a => ({ title: a.title, domain_label: a.domain_label || a.domain })),
          domains: prefs.domains,
          keywords: prefs.keywords,
        }),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(`HTTP ${res.status}: ${t.slice(0, 160)}`);
      }
      const data = await res.json();
      const scores = data.scores || [];

      setItems(prev => prev.map((item, i) => {
        const s = scores[i];
        return s ? { ...item, _score: s.score, _reasoning: s.reasoning } : item;
      }));
      setRanked(true);
      setSortBy("score");
    } catch (e) {
      setError("AI ranking failed: " + e.message);
    } finally {
      setRanking(false);
    }
  };

  // derived display list
  const displayItems = items
    .filter(item => {
      if (domainFilter !== "all" && item.domain_label !== domainFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        return item.title.toLowerCase().includes(q) || item.summary.toLowerCase().includes(q);
      }
      return true;
    })
    .sort((a, b) => {
      if (sortBy === "score" && ranked) return (b._score ?? 0) - (a._score ?? 0);
      return 0; // keep fetch order (already newest-first from sidecar)
    });

  const activeDomains = [...new Set(items.map(i => i.domain_label))];

  // colour map, data-driven from categories (falls back to built-in defaults)
  const colors = categories.length
    ? Object.fromEntries(categories.map(c => [c.name, c.color]))
    : DOMAIN_COLORS;

  // group the visible (filtered) articles by category
  const grouped = {};
  displayItems.forEach(it => {
    const cat = it.domain_label || it.domain || "Other";
    (grouped[cat] = grouped[cat] || []).push(it);
  });

  // enabled-feed counts per category name (drives the empty-state message)
  const feedCountByCat = {};
  allFeeds.forEach(f => {
    if (f.enabled !== false) feedCountByCat[f.domain] = (feedCountByCat[f.domain] || 0) + 1;
  });

  // Always show every known category (empty ones included), so the full set is
  // discoverable; append any extra categories that only appear in fetched items.
  const knownCatNames = categories.map(c => c.name);
  const extraCats = Object.keys(grouped).filter(d => !knownCatNames.includes(d));
  let orderedCats = [...knownCatNames, ...extraCats];
  if (domainFilter !== "all") {
    orderedCats = orderedCats.filter(c => c === domainFilter);
  } else if (search) {
    orderedCats = orderedCats.filter(c => (grouped[c] || []).length > 0);
  }

  const toggleCollapsed = (cat) => setCollapsed(prev => {
    const next = new Set(prev);
    if (next.has(cat)) next.delete(cat); else next.add(cat);
    saveCollapsed(next);
    return next;
  });
  const allCollapsed = orderedCats.length > 0 && orderedCats.every(c => collapsed.has(c));
  const toggleAll = () => {
    const next = allCollapsed ? new Set() : new Set(orderedCats);
    saveCollapsed(next);
    setCollapsed(next);
  };

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden", position: "relative" }}>
      {/* ── main column ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* toolbar */}
        <div style={{
          padding: "11px 14px 10px",
          borderBottom: "1px solid var(--border-soft)",
          display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
          background: "var(--bg-inset)",
        }}>
          <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 700, color: "var(--text)", textTransform: "uppercase", letterSpacing: 1, display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ color: "var(--accent)" }}>◈</span> Science Feed
          </span>

          {/* domain quick-filter pills */}
          <div style={{ display: "flex", gap: 5, flex: 1, flexWrap: "wrap" }}>
            <button
              onClick={() => setDomainFilter("all")}
              className="wnv-pill"
              style={domainFilter === "all" ? {
                background: "var(--accent)", color: "var(--bg)", borderColor: "var(--accent)", fontWeight: 700,
              } : undefined}
            >
              All
            </button>
            {activeDomains.map(d => {
              const on = domainFilter === d;
              const c = colors[d] || "var(--border-soft)";
              return (
                <button
                  key={d}
                  onClick={() => setDomainFilter(on ? "all" : d)}
                  className="wnv-pill"
                  style={on ? { background: c + "33", color: c, borderColor: c + "88", fontWeight: 700 } : undefined}
                >
                  {d.split(" ")[0]}
                </button>
              );
            })}
          </div>

          {/* search */}
          <input
            type="text"
            placeholder="Search…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              all: "unset", padding: "5px 10px",
              background: "var(--bg-panel)", border: "1px solid var(--border-soft)",
              borderRadius: 6, fontFamily: "var(--mono)", fontSize: 11, color: "var(--text)",
              width: 140,
            }}
          />

          {/* sort toggle */}
          {ranked && (
            <div style={{ display: "flex", gap: 0, border: "1px solid var(--border-soft)", borderRadius: 6, overflow: "hidden" }}>
              {["date", "score"].map(s => (
                <button key={s} onClick={() => setSortBy(s)} style={{
                  all: "unset", cursor: "pointer", padding: "5px 10px",
                  background: sortBy === s ? "var(--accent)" : "var(--bg-panel)",
                  color: sortBy === s ? "var(--bg)" : "var(--text-dim)",
                  fontFamily: "var(--mono)", fontSize: 10, fontWeight: sortBy === s ? 700 : 400,
                }}>
                  {s === "score" ? "AI score" : "newest"}
                </button>
              ))}
            </div>
          )}

          {/* view toggle: list / grid */}
          <div style={{ display: "flex", gap: 0, border: "1px solid var(--border-soft)", borderRadius: 6, overflow: "hidden" }}>
            {["list", "grid"].map(v => (
              <button key={v} onClick={() => { setViewMode(v); try { localStorage.setItem(LS_VIEW, v); } catch {} }}
                title={v === "grid" ? "Grid view — responsive columns" : "List view"}
                style={{
                  all: "unset", cursor: "pointer", padding: "5px 10px",
                  background: viewMode === v ? "var(--accent)" : "var(--bg-panel)",
                  color: viewMode === v ? "var(--bg)" : "var(--text-dim)",
                  fontFamily: "var(--mono)", fontSize: 10, fontWeight: viewMode === v ? 700 : 400,
                }}>
                {v === "grid" ? "▦ Grid" : "▤ List"}
              </button>
            ))}
          </div>

          {/* density (grid only) — cycles column width → more/fewer columns */}
          {viewMode === "grid" && (
            <button className="wnv-btn"
              title="Card width — more (smaller) or fewer (larger) columns for the window width"
              onClick={() => {
                const order = ["compact", "cozy", "comfy"];
                const next = order[(order.indexOf(density) + 1) % order.length];
                setDensity(next); try { localStorage.setItem(LS_DENSITY, next); } catch {}
              }}>
              {density === "compact" ? "▦ compact" : density === "comfy" ? "▦ wide" : "▦ cozy"}
            </button>
          )}

          {/* action buttons */}
          <button onClick={() => fetchNews()} disabled={loading} className="wnv-btn">
            {loading ? "Loading…" : "↻ Refresh"}
          </button>

          <button
            onClick={rankWithAI}
            disabled={ranking || loading || !items.length}
            className={`wnv-btn ${ranking ? "" : "wnv-btn-primary"}`}
            title="Use the app's AI (your selected local or cloud model) to score the fetched articles 0–10 for relevance to your active domains + keywords, then sort by score."
          >
            {ranking ? "Ranking…" : ranked ? "✓ Re-rank AI" : "✦ Rank with AI"}
          </button>

          <button
            onClick={() => setSettingsOpen(o => !o)}
            className="wnv-btn"
            style={settingsOpen ? { borderColor: "var(--accent)", color: "var(--accent)" } : undefined}
          >
            ⚙
          </button>
        </div>

        {/* stats bar */}
        {items.length > 0 && (
          <div style={{
            padding: "6px 14px", borderBottom: "1px solid var(--border-soft)",
            display: "flex", gap: 12, alignItems: "center",
            background: "var(--bg)",
          }}>
            <span style={{ fontSize: 10, color: "var(--text-dim)", fontFamily: "var(--mono)" }}>
              <b style={{ color: "var(--text)" }}>{displayItems.length}</b> / {items.length} articles · {activeFeeds.length} feeds
            </span>
            {prefs.keywords.length > 0 && (
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {prefs.keywords.slice(0, 8).map(k => (
                  <span key={k} style={{
                    padding: "1px 6px", borderRadius: 3,
                    background: "var(--bg-inset)", border: "1px solid var(--border-soft)",
                    fontSize: 9, color: "var(--text-dim)", fontFamily: "var(--mono)",
                  }}>{k}</span>
                ))}
              </div>
            )}
            {orderedCats.length > 1 && (
              <button onClick={toggleAll} className="wnv-btn" style={{ marginLeft: "auto", padding: "3px 9px", fontSize: 10 }}>
                {allCollapsed ? "▾ expand all" : "▸ collapse all"}
              </button>
            )}
          </div>
        )}

        {/* article list */}
        <div className="wnv-scroll" style={{ flex: 1, overflowY: "auto", padding: "14px 16px" }}>
          {error && (
            <div style={{
              color: "var(--red)", fontSize: 12, fontFamily: "var(--mono)", marginBottom: 12,
              padding: "8px 10px", borderRadius: 6,
              background: "rgba(217,83,79,0.1)", border: "1px solid rgba(217,83,79,0.3)",
            }}>
              ⚠ {error}
            </div>
          )}

          {loading && (
            <>
              <div style={{ color: "var(--text-dim)", fontSize: 11, fontFamily: "var(--mono)", marginBottom: 12 }}>
                Fetching {activeFeeds.length} feeds…
              </div>
              {Array.from({ length: 6 }).map((_, i) => <div key={i} className="wnv-skel" />)}
            </>
          )}

          {!loading && items.length === 0 && !error && (
            <div style={{ color: "var(--text-dim)", fontSize: 13, marginTop: 50, textAlign: "center" }}>
              <div style={{ fontSize: 30, marginBottom: 10 }}>📡</div>
              <div style={{ color: "var(--text)", fontWeight: 600 }}>No articles yet</div>
              <div style={{ fontSize: 11, marginTop: 5 }}>Click Refresh or adjust domains/keywords in ⚙ Settings.</div>
            </div>
          )}

          {!loading && orderedCats.length === 0 && items.length > 0 && (
            <div style={{ color: "var(--text-dim)", fontSize: 12, marginTop: 24, textAlign: "center" }}>
              No articles match your current filters.
            </div>
          )}

          {!loading && items.length > 0 && orderedCats.map(cat => {
            const c = colors[cat] || "var(--border-soft)";
            const isCollapsed = collapsed.has(cat);
            const arts = grouped[cat] || [];
            const empty = arts.length === 0;
            const isActive = prefs.domains.includes(cat);
            const feedN = feedCountByCat[cat] || 0;
            const emptyMsg = !isActive
              ? "Off — enable this domain in ⚙ Settings"
              : feedN === 0
              ? "No feeds yet — add one in ⚙ Settings"
              : "No recent articles";
            return (
              <div key={cat} style={{ marginBottom: 4 }}>
                <button
                  className="wnv-cat"
                  onClick={() => toggleCollapsed(cat)}
                  style={{
                    all: "unset", cursor: "pointer", boxSizing: "border-box",
                    display: "flex", alignItems: "center", gap: 8, width: "100%",
                    padding: "7px 10px", marginBottom: 8,
                    background: "var(--bg-inset)",
                    border: "1px solid var(--border-soft)",
                    borderLeft: `3px solid ${c}`,
                    borderRadius: 6,
                    opacity: empty ? 0.6 : 1,
                  }}
                >
                  <span style={{ fontSize: 10, color: "var(--text-dim)", width: 10, textAlign: "center" }}>
                    {isCollapsed ? "▸" : "▾"}
                  </span>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: c, flexShrink: 0 }} />
                  <span style={{ fontSize: 11, fontFamily: "var(--mono)", fontWeight: 700, color: "var(--text)", textTransform: "uppercase", letterSpacing: 0.6 }}>
                    {cat}
                  </span>
                  {!isActive && (
                    <span style={{ fontSize: 8.5, fontFamily: "var(--mono)", color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: 0.5, border: "1px solid var(--border-soft)", borderRadius: 3, padding: "0 4px" }}>off</span>
                  )}
                  <span style={{ marginLeft: "auto", fontSize: 9, fontFamily: "var(--mono)", color: empty ? "var(--text-dim)" : "var(--text)", padding: "1px 7px", borderRadius: 999, border: "1px solid var(--border-soft)" }}>
                    {arts.length}
                  </span>
                </button>
                {!isCollapsed && (empty ? (
                  <div style={{ padding: "2px 4px 10px 13px", fontSize: 11, fontFamily: "var(--mono)", fontStyle: "italic", color: "var(--text-dim)" }}>
                    {emptyMsg}
                  </div>
                ) : viewMode === "grid" ? (
                  <div className="wnv-grid" style={{ "--wnv-col": (DENSITY_PX[density] || 320) + "px" }}>
                    {arts.map(item => (
                      <ArticleCard key={item.id} item={item} ranked={ranked} colors={colors} layout="grid" />
                    ))}
                  </div>
                ) : arts.map(item => (
                  <ArticleCard key={item.id} item={item} ranked={ranked} colors={colors} layout="list" />
                )))}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── settings drawer ── */}
      {settingsOpen && (
        <SettingsPanel
          allFeeds={allFeeds}
          prefs={prefs}
          onChange={handlePrefsChange}
          onClose={() => setSettingsOpen(false)}
          categories={categories}
          colors={colors}
          reloadCatalogue={loadCatalogue}
        />
      )}
    </div>
  );
}