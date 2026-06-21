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
import { useState, useEffect, useCallback, useRef } from "react";

const SIDECAR = "http://localhost:8000";

const DOMAIN_COLORS = {
  "Physics & Space":          "#7b9fd4",
  "Biology & Life Sciences":  "#7fb069",
  "AI & Machine Learning":    "#d97b4f",
  "Neuroscience":             "#c47bd9",
  "Mathematics":              "#e0b84c",
  "Engineering & Technology": "#4fd9c4",
  "Chemistry & Materials":    "#d94f8a",
  "Climate & Earth Science":  "#4fa8d9",
};

const ALL_DOMAINS = Object.keys(DOMAIN_COLORS);

const LS_KEY = "agentic-os.webnews";

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

// ── small helpers ──────────────────────────────────────────────────────────

function DomainBadge({ domain, small }) {
  const color = DOMAIN_COLORS[domain] || "var(--fg-muted)";
  return (
    <span style={{
      display: "inline-block",
      padding: small ? "1px 5px" : "2px 8px",
      borderRadius: 4,
      background: color + "22",
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
  const color = score >= 7 ? "#7fb069" : score >= 4 ? "#e0b84c" : "#888";
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      width: 28, height: 28, borderRadius: "50%",
      background: color + "22", border: `1.5px solid ${color}`,
      color, fontSize: 11, fontFamily: "var(--mono)", fontWeight: 700,
      flexShrink: 0,
    }}>
      {score}
    </span>
  );
}

function ArticleCard({ item, ranked }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div style={{
      padding: "10px 12px", borderRadius: 7,
      background: "var(--bg-inset)",
      border: "1px solid var(--border-soft)",
      marginBottom: 8,
      transition: "border-color 0.15s",
    }}
    onMouseEnter={e => e.currentTarget.style.borderColor = "var(--accent)"}
    onMouseLeave={e => e.currentTarget.style.borderColor = "var(--border-soft)"}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
        {ranked && <ScoreBadge score={item._score ?? "?"} />}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4, flexWrap: "wrap" }}>
            <DomainBadge domain={item.domain_label || item.domain} small />
            <span style={{ fontSize: 10, color: "var(--fg-muted)", fontFamily: "var(--mono)" }}>
              {item.source_label || item.domain}
            </span>
            {item.published && (
              <span style={{ fontSize: 10, color: "var(--fg-muted)", fontFamily: "var(--mono)", marginLeft: "auto" }}>
                {item.published.slice(0, 16)}
              </span>
            )}
          </div>
          <a
            href={item.link}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              color: "var(--fg)", textDecoration: "none", fontWeight: 600,
              fontSize: 13, lineHeight: 1.4, display: "block",
            }}
          >
            {item.title}
          </a>
          {item.summary && (
            <>
              <p style={{
                margin: "5px 0 0", fontSize: 11, color: "var(--fg-muted)",
                lineHeight: 1.6,
                display: expanded ? "block" : "-webkit-box",
                WebkitLineClamp: expanded ? "unset" : 3,
                WebkitBoxOrient: "vertical",
                overflow: expanded ? "visible" : "hidden",
              }}>
                {item.summary}
              </p>
              {item.summary.length > 150 && (
                <button
                  onClick={() => setExpanded(e => !e)}
                  style={{
                    all: "unset", cursor: "pointer", fontSize: 10,
                    color: "var(--accent)", marginTop: 3,
                  }}
                >
                  {expanded ? "show less" : "show more"}
                </button>
              )}
            </>
          )}
          {ranked && item._reasoning && (
            <p style={{
              margin: "5px 0 0", fontSize: 10, color: "#e0b84c",
              fontStyle: "italic", lineHeight: 1.5,
            }}>
              AI: {item._reasoning}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// ── settings sidebar ───────────────────────────────────────────────────────

function SettingsPanel({ allFeeds, prefs, onChange, onClose }) {
  const [domains, setDomains] = useState(prefs.domains);
  const [keywords, setKeywords] = useState(prefs.keywords.join(", "));

  const grouped = {};
  allFeeds.forEach(f => {
    if (!grouped[f.domain]) grouped[f.domain] = [];
    grouped[f.domain].push(f);
  });

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
      width: 340, background: "var(--bg-panel)",
      borderLeft: "1px solid var(--border-soft)",
      display: "flex", flexDirection: "column", zIndex: 10,
      boxShadow: "-4px 0 20px rgba(0,0,0,0.3)",
    }}>
      <div style={{ padding: "12px 14px 10px", borderBottom: "1px solid var(--border-soft)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: 1, color: "var(--fg)" }}>Settings</span>
        <button onClick={onClose} style={{ all: "unset", cursor: "pointer", color: "var(--fg-muted)", fontSize: 16 }}>✕</button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "12px 14px" }}>
        {/* keyword filter */}
        <label style={{ fontSize: 11, color: "var(--fg-muted)", fontFamily: "var(--mono)", textTransform: "uppercase", letterSpacing: 0.5 }}>
          Keywords (comma-separated)
        </label>
        <textarea
          value={keywords}
          onChange={e => setKeywords(e.target.value)}
          rows={3}
          style={{
            all: "unset", display: "block", width: "100%", boxSizing: "border-box",
            marginTop: 5, marginBottom: 14,
            padding: "7px 9px", background: "var(--bg-inset)",
            border: "1px solid var(--border-soft)", borderRadius: 5,
            fontFamily: "var(--mono)", fontSize: 11, color: "var(--fg)",
            lineHeight: 1.6, resize: "vertical",
          }}
        />

        {/* domain toggles */}
        <label style={{ fontSize: 11, color: "var(--fg-muted)", fontFamily: "var(--mono)", textTransform: "uppercase", letterSpacing: 0.5 }}>
          Active Domains
        </label>
        <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 6 }}>
          {ALL_DOMAINS.map(d => {
            const on = domains.includes(d);
            const feedCount = (grouped[d] || []).length;
            return (
              <button
                key={d}
                onClick={() => toggleDomain(d)}
                style={{
                  all: "unset", cursor: "pointer",
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "7px 10px", borderRadius: 6,
                  background: on ? DOMAIN_COLORS[d] + "18" : "var(--bg-inset)",
                  border: `1px solid ${on ? DOMAIN_COLORS[d] + "55" : "var(--border-soft)"}`,
                  transition: "all 0.15s",
                }}
              >
                <span style={{
                  width: 10, height: 10, borderRadius: "50%",
                  background: on ? DOMAIN_COLORS[d] : "var(--bg-panel)",
                  border: `2px solid ${DOMAIN_COLORS[d]}`,
                  flexShrink: 0,
                }} />
                <span style={{ fontSize: 12, color: "var(--fg)", flex: 1 }}>{d}</span>
                <span style={{ fontSize: 10, color: "var(--fg-muted)", fontFamily: "var(--mono)" }}>{feedCount} feeds</span>
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border-soft)" }}>
        <button
          onClick={apply}
          style={{
            all: "unset", cursor: "pointer",
            display: "block", width: "100%", boxSizing: "border-box",
            padding: "9px 0", textAlign: "center",
            background: "var(--accent)", color: "#000",
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
  const abortRef = useRef(null);

  // load feed catalogue on mount
  useEffect(() => {
    fetch(`${SIDECAR}/api/news/feeds`)
      .then(r => r.json())
      .then(d => setAllFeeds(d.feeds || []))
      .catch(() => {});
  }, []);

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
      const res = await fetch(`${SIDECAR}/api/news/fetch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls: feeds.map(f => f.url), keywords: p.keywords }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      // Tag each item with its domain label from feed catalogue
      const urlToDomain = {};
      const urlToLabel = {};
      feeds.forEach(f => { urlToDomain[f.url] = f.domain; urlToLabel[f.url] = f.label; });

      // items come back with domain = hostname; enrich with domain label
      const enriched = (data.items || []).map(item => {
        const feed = feeds.find(f => f.url.includes(item.domain) || item.domain.includes(f.url.split("/")[2]?.replace("www.", "")));
        return {
          ...item,
          domain_label: feed?.domain || item.domain,
          source_label: feed?.label || item.domain,
        };
      });

      setItems(enriched);
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

  // AI ranking
  const rankWithAI = async () => {
    if (!items.length) return;
    setRanking(true);
    try {
      const toRank = items.slice(0, 40); // cap at 40 for API cost
      const prompt = `You are a science news ranker. Score each article 0–10 for how interesting and significant it is to a researcher interested in: ${prefs.domains.join(", ")}.

Keywords of particular interest: ${prefs.keywords.join(", ")}.

For each article, respond ONLY with a JSON array, one object per article in the same order:
[{"score": 8, "reasoning": "one short sentence why"}, ...]

Articles:
${toRank.map((a, i) => `${i + 1}. [${a.domain_label}] ${a.title}`).join("\n")}

Respond with only the JSON array.`;

      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-6",
          max_tokens: 1000,
          messages: [{ role: "user", content: prompt }],
        }),
      });
      const data = await res.json();
      const text = data.content?.map(c => c.text || "").join("") || "";
      const clean = text.replace(/```json|```/g, "").trim();
      const scores = JSON.parse(clean);

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

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden", position: "relative" }}>
      {/* ── main column ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* toolbar */}
        <div style={{
          padding: "10px 14px 9px",
          borderBottom: "1px solid var(--border-soft)",
          display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
        }}>
          <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--fg-muted)", textTransform: "uppercase", letterSpacing: 1 }}>
            Science Feed
          </span>

          {/* domain quick-filter pills */}
          <div style={{ display: "flex", gap: 4, flex: 1, flexWrap: "wrap" }}>
            <button
              onClick={() => setDomainFilter("all")}
              style={{
                all: "unset", cursor: "pointer",
                padding: "2px 8px", borderRadius: 4, fontSize: 10, fontFamily: "var(--mono)",
                background: domainFilter === "all" ? "var(--accent)" : "var(--bg-inset)",
                color: domainFilter === "all" ? "#000" : "var(--fg-muted)",
                border: "1px solid var(--border-soft)",
              }}
            >
              All
            </button>
            {activeDomains.map(d => (
              <button
                key={d}
                onClick={() => setDomainFilter(d === domainFilter ? "all" : d)}
                style={{
                  all: "unset", cursor: "pointer",
                  padding: "2px 8px", borderRadius: 4, fontSize: 10, fontFamily: "var(--mono)",
                  background: domainFilter === d ? DOMAIN_COLORS[d] + "33" : "var(--bg-inset)",
                  color: domainFilter === d ? DOMAIN_COLORS[d] : "var(--fg-muted)",
                  border: `1px solid ${domainFilter === d ? DOMAIN_COLORS[d] + "55" : "var(--border-soft)"}`,
                }}
              >
                {d.split(" ")[0]}
              </button>
            ))}
          </div>

          {/* search */}
          <input
            type="text"
            placeholder="Search…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              all: "unset", padding: "4px 8px",
              background: "var(--bg-inset)", border: "1px solid var(--border-soft)",
              borderRadius: 5, fontFamily: "var(--mono)", fontSize: 11, color: "var(--fg)",
              width: 140,
            }}
          />

          {/* sort toggle */}
          {ranked && (
            <div style={{ display: "flex", gap: 2 }}>
              {["date", "score"].map(s => (
                <button key={s} onClick={() => setSortBy(s)} style={{
                  all: "unset", cursor: "pointer", padding: "4px 8px",
                  background: sortBy === s ? "var(--accent)" : "var(--bg-inset)",
                  color: sortBy === s ? "#000" : "var(--fg-muted)",
                  border: "1px solid var(--border-soft)", borderRadius: 4,
                  fontFamily: "var(--mono)", fontSize: 10,
                }}>
                  {s === "score" ? "AI score" : "newest"}
                </button>
              ))}
            </div>
          )}

          {/* action buttons */}
          <button
            onClick={() => fetchNews()}
            disabled={loading}
            style={{
              all: "unset", cursor: loading ? "default" : "pointer",
              padding: "5px 11px", background: "var(--bg-inset)",
              border: "1px solid var(--border-soft)", borderRadius: 5,
              fontFamily: "var(--mono)", fontSize: 11, color: loading ? "var(--fg-muted)" : "var(--fg)",
            }}
          >
            {loading ? "Loading…" : "↻ Refresh"}
          </button>

          <button
            onClick={rankWithAI}
            disabled={ranking || loading || !items.length}
            style={{
              all: "unset", cursor: (ranking || !items.length) ? "default" : "pointer",
              padding: "5px 11px",
              background: ranking ? "var(--bg-inset)" : "var(--accent)",
              color: ranking ? "var(--fg-muted)" : "#000",
              border: "1px solid var(--border-soft)", borderRadius: 5,
              fontFamily: "var(--mono)", fontSize: 11, fontWeight: 700,
            }}
          >
            {ranking ? "Ranking…" : ranked ? "✓ Re-rank AI" : "✦ Rank with AI"}
          </button>

          <button
            onClick={() => setSettingsOpen(o => !o)}
            style={{
              all: "unset", cursor: "pointer",
              padding: "5px 10px", background: "var(--bg-inset)",
              border: `1px solid ${settingsOpen ? "var(--accent)" : "var(--border-soft)"}`,
              borderRadius: 5, fontFamily: "var(--mono)", fontSize: 12,
              color: settingsOpen ? "var(--accent)" : "var(--fg-muted)",
            }}
          >
            ⚙
          </button>
        </div>

        {/* stats bar */}
        {items.length > 0 && (
          <div style={{
            padding: "5px 14px", borderBottom: "1px solid var(--border-soft)",
            display: "flex", gap: 12, alignItems: "center",
          }}>
            <span style={{ fontSize: 10, color: "var(--fg-muted)", fontFamily: "var(--mono)" }}>
              {displayItems.length} / {items.length} articles · {activeFeeds.length} feeds
            </span>
            {prefs.keywords.length > 0 && (
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {prefs.keywords.slice(0, 8).map(k => (
                  <span key={k} style={{
                    padding: "1px 5px", borderRadius: 3,
                    background: "var(--bg-inset)", border: "1px solid var(--border-soft)",
                    fontSize: 9, color: "var(--fg-muted)", fontFamily: "var(--mono)",
                  }}>{k}</span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* article list */}
        <div style={{ flex: 1, overflowY: "auto", padding: "12px 14px" }}>
          {error && (
            <div style={{ color: "#d9534f", fontSize: 12, fontFamily: "var(--mono)", marginBottom: 12 }}>
              ⚠ {error}
            </div>
          )}

          {loading && (
            <div style={{ color: "var(--fg-muted)", fontSize: 12, fontFamily: "var(--mono)", marginTop: 20 }}>
              Fetching {activeFeeds.length} feeds…
            </div>
          )}

          {!loading && items.length === 0 && !error && (
            <div style={{ color: "var(--fg-muted)", fontSize: 13, marginTop: 40, textAlign: "center" }}>
              <div style={{ fontSize: 28, marginBottom: 10 }}>📡</div>
              <div>No articles yet.</div>
              <div style={{ fontSize: 11, marginTop: 4 }}>Click Refresh or adjust domains/keywords in ⚙ Settings.</div>
            </div>
          )}

          {!loading && displayItems.length === 0 && items.length > 0 && (
            <div style={{ color: "var(--fg-muted)", fontSize: 12, marginTop: 20 }}>
              No articles match your current filters.
            </div>
          )}

          {displayItems.map(item => (
            <ArticleCard key={item.id} item={item} ranked={ranked} />
          ))}
        </div>
      </div>

      {/* ── settings drawer ── */}
      {settingsOpen && (
        <SettingsPanel
          allFeeds={allFeeds}
          prefs={prefs}
          onChange={handlePrefsChange}
          onClose={() => setSettingsOpen(false)}
        />
      )}
    </div>
  );
}
