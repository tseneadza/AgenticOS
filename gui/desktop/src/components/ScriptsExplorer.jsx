import { useState, useEffect, useRef } from "react";
import ScriptTypeBadge from "./ScriptTypeBadge";
import ScriptGroupHeader from "./ScriptGroupHeader";
import ScriptItem from "./ScriptItem";

const SIDECAR = "http://localhost:5130/api";
const HUB = SIDECAR; // Phase 9c: native sidecar, no Hub dependency

// ─── Type classification ─────────────────────────────────────────────────────
// Type hues encode meaning (semantic) and stay fixed across themes; their
// backgrounds derive from the active theme surface via color-mix so each badge
// reads on every skin. Hues that map to status tokens use the token directly.
const TYPE_STYLE = {
  "Launcher":    { bg:"color-mix(in srgb, var(--green) 16%, var(--bg-inset))",  color:"var(--green)" },
  "Test":        { bg:"color-mix(in srgb, #4fa8d9 16%, var(--bg-inset))",       color:"#4fa8d9" },
  "Data":        { bg:"color-mix(in srgb, var(--yellow) 16%, var(--bg-inset))", color:"var(--yellow)" },
  "Scraper":     { bg:"color-mix(in srgb, #b07fd9 16%, var(--bg-inset))",       color:"#b07fd9" },
  "Diagnostic":  { bg:"color-mix(in srgb, var(--accent) 16%, var(--bg-inset))", color:"var(--accent)" },
  "Maintenance": { bg:"color-mix(in srgb, var(--red) 16%, var(--bg-inset))",    color:"var(--red)" },
  "Dev Setup":   { bg:"color-mix(in srgb, #4fd9cc 16%, var(--bg-inset))",       color:"#4fd9cc" },
  "Unknown":     { bg:"color-mix(in srgb, var(--text-dim) 16%, var(--bg-inset))", color:"var(--text-dim)" },
};

function classifyScript(s) {
  const n = (s.name || "").toLowerCase();
  if (n.includes("start") || n.includes("launch") || n.includes("serve")) return "Launcher";
  if (n.includes("test") || n.includes("smoke") || n.includes("spec")) return "Test";
  if (n.includes("seed") || n.includes("import") || n.includes("populate") || n.includes("backfill") || n.includes("migrate") || n.includes("setup_db") || n.includes("load_") || n.includes("collect_") || n.includes("update_all")) return "Data";
  if (n.includes("scrape") || n.includes("fetch") || n.includes("crawl") || n.includes("download") || n.includes("update_fighter") || n.includes("update_full")) return "Scraper";
  if (n.includes("diagnose") || n.includes("discover") || n.includes("inspect") || n.includes("debug") || n.includes("probe") || n.includes("setup_database")) return "Diagnostic";
  if (n.includes("clear") || n.includes("clean") || n.includes("sync") || n.includes("update-port") || n.includes("show_cron") || n.includes("repo-sync")) return "Maintenance";
  if (n.includes("setup") || n.includes("init") || n.includes("install") || n.includes("symlink") || n.includes("branch") || n.includes("build")) return "Dev Setup";
  const d = (s.description || "").toLowerCase();
  if (d.includes("start") || d.includes("boot") || d.includes("launch")) return "Launcher";
  if (d.includes("test") || d.includes("verify")) return "Test";
  if (d.includes("seed") || d.includes("import") || d.includes("populate")) return "Data";
  return "Unknown";
}

// ─── Header parser ────────────────────────────────────────────────────────────
// Reads raw script content and extracts structured info from comment blocks.
function parseScriptContent(content, sc) {
  if (!content) return null;
  const lines = content.split("\n");
  const ext = (sc.path || "").split(".").pop().toLowerCase();
  const isPy  = ext === "py";
  const isSh  = ext === "sh" || ext === "bash" || !ext.match(/^[a-z]+$/);

  // ── Extract the top comment block ─────────────────────────────────────────
  const headerLines = [];
  let inTripleQuote = false;
  let pastShebang   = false;
  let hitCode       = false;

  for (const raw of lines) {
    const l = raw.trim();
    if (!pastShebang && l.startsWith("#!")) { pastShebang = true; continue; }
    if (hitCode) break;

    if (isPy) {
      if (!inTripleQuote && (l.startsWith('"""') || l.startsWith("'''"))) {
        inTripleQuote = true;
        const inner = l.replace(/^"""|^'''/, "").replace(/"""|'''$/, "").trim();
        if (inner) headerLines.push(inner);
        // one-liner docstring?
        if ((l.match(/"""/g)||[]).length >= 2 || (l.match(/'''/g)||[]).length >= 2) inTripleQuote = false;
        continue;
      }
      if (inTripleQuote) {
        if (l.endsWith('"""') || l.endsWith("'''")) {
          const inner = l.replace(/"""|'''$/, "").trim();
          if (inner) headerLines.push(inner);
          inTripleQuote = false;
        } else {
          headerLines.push(raw); // preserve indentation for usage blocks
        }
        continue;
      }
    }

    if (l.startsWith("#")) {
      headerLines.push(raw.replace(/^#+\s?/, ""));
      continue;
    }
    // Blank lines inside header are OK; a non-comment, non-blank line ends it
    if (l === "") {
      if (headerLines.length > 0) headerLines.push("");
      continue;
    }
    hitCode = true;
  }

  const fullHeader = headerLines.join("\n").trim();
  if (!fullHeader) return null;

  // ── Purpose: first meaningful sentence ────────────────────────────────────
  const meaningfulLines = headerLines.filter(l => l.trim() && !l.match(/^[-=*─]+$/));
  const purpose = meaningfulLines[0]?.trim() || sc.description || "";

  // ── Usage patterns ────────────────────────────────────────────────────────
  // Lines that look like invocations: leading whitespace + script/command name
  // OR lines after a "Usage:" or "Run:" label
  const usageLines = [];
  let inUsageBlock = false;
  for (const l of headerLines) {
    const t = l.trim();
    if (/^(usage|run|invoke|call)\s*:/i.test(t)) { inUsageBlock = true; continue; }
    if (inUsageBlock) {
      if (t === "" || t.match(/^[A-Z][^:]+:$/)) { inUsageBlock = false; continue; }
      usageLines.push(t);
      continue;
    }
    // Indented lines that look like shell commands
    if (/^\s{2,}(bash|python|\.\/|python3|\.venv|\$\s|cd\s|npm\s|go\s|node\s|\w[\w.-]+\s+(start|stop|install|run|build|test|status|restart))/.test(l)) {
      usageLines.push(t);
    }
    // Lines containing the script name followed by a subcommand
    const scriptBase = (sc.name || "").replace(/\.(sh|py|ts|js)$/, "");
    if (scriptBase && new RegExp(`${scriptBase}\\s+\\w`).test(t)) {
      if (!usageLines.includes(t)) usageLines.push(t);
    }
  }

  // ── Parameters / flags ────────────────────────────────────────────────────
  const paramLines = [];
  let inParamBlock = false;
  for (const l of headerLines) {
    const t = l.trim();
    if (/^(parameters?|args?|arguments?|flags?|options?)\s*:/i.test(t)) { inParamBlock = true; continue; }
    if (inParamBlock) {
      if (t === "" || (t.match(/^[A-Z][^:]+:$/) && !t.match(/^-/))) { inParamBlock = false; continue; }
      if (t) paramLines.push(t);
      continue;
    }
    // Lines that define --flags, -f flags, or ARG= patterns
    if (/^\s*(--|-)[\w-]/.test(l) || /^\s*[A-Z_]{2,}=/.test(l)) {
      paramLines.push(t);
    }
  }

  // ── Environment variables ─────────────────────────────────────────────────
  // Scan full script content (not just header) for ${VAR} and $VAR patterns
  const envSet = new Set();
  const envRe = /\$\{?([A-Z][A-Z0-9_]{1,})\}?/g;
  let m;
  while ((m = envRe.exec(content)) !== null) {
    const v = m[1];
    if (!["PATH","HOME","PWD","USER","SHELL","TERM","IFS","BASH","SECONDS","RANDOM","LINENO","PPID"].includes(v)) {
      envSet.add(v);
    }
  }
  const envVars = [...envSet].slice(0, 12);

  // ── Dependencies / tools required ─────────────────────────────────────────
  const deps = new Set();
  const depPatterns = [
    /command -v\s+(\w+)/g,
    /which\s+(\w+)/g,
    /Requires?\s+([\w,\s]+)\./gi,
    /Install with:\s+(\w+\s+install\s+[\w-]+)/gi,
    /^# Requires?\s*:\s*(.+)/gim,
  ];
  for (const re of depPatterns) {
    let dm;
    const src = re.source.includes("Requires") ? fullHeader : content;
    const reCopy = new RegExp(re.source, re.flags);
    while ((dm = reCopy.exec(src)) !== null) {
      dm[1].split(/[,\s]+/).filter(d => d.match(/^[a-z][\w-]+$/) && d.length > 1).forEach(d => deps.add(d));
    }
  }

  // ── Notes / warnings ──────────────────────────────────────────────────────
  const noteLines = [];
  let inNoteBlock = false;
  for (const l of headerLines) {
    const t = l.trim();
    if (/^(note|warn|warning|caution|important)\s*[s:]?/i.test(t)) { inNoteBlock = true; noteLines.push(t); continue; }
    if (inNoteBlock) {
      if (t === "" || (t.match(/^[A-Z][^:]+:$/) && !t.match(/^note|warn/i))) { inNoteBlock = false; continue; }
      if (t) noteLines.push(t);
    }
  }

  return {
    purpose,
    fullHeader,
    usageLines:  [...new Set(usageLines)].slice(0, 10),
    paramLines:  [...new Set(paramLines)].slice(0, 12),
    envVars,
    deps:        [...deps].slice(0, 8),
    noteLines:   [...new Set(noteLines)].slice(0, 6),
    lineCount:   lines.length,
  };
}

const SORT_OPTIONS = [
  { key:"name",    label:"Name" },
  { key:"type",    label:"Type" },
  { key:"project", label:"Project" },
];

export default function ScriptsExplorer() {
  // ── localStorage helpers ────────────────────────────────────────────────────
  const loadFromLS = (key, defaultVal) => {
    try {
      const stored = localStorage.getItem(`scripts-explorer-${key}`);
      return stored ? JSON.parse(stored) : defaultVal;
    } catch { return defaultVal; }
  };
  const saveToLS = (key, val) => {
    try { localStorage.setItem(`scripts-explorer-${key}`, JSON.stringify(val)); } catch {}
  };

  const [scripts, setScripts]         = useState([]);
  const [loading, setLoading]         = useState(true);
  const [fetchErr, setFetchErr]       = useState(null);
  const [tab, setTab]                 = useState("explorer");
  const [selected, setSelected]       = useState(null);
  const [groupOpen, setGroupOpen]     = useState(() => loadFromLS("groupOpen", {}));
  const [filter, setFilter]           = useState(() => loadFromLS("filter", ""));
  const [sortBy, setSortBy]           = useState(() => loadFromLS("sortBy", "type"));
  const [sortDir, setSortDir]         = useState(() => loadFromLS("sortDir", "asc"));
  const [groupBy, setGroupBy]         = useState(() => loadFromLS("groupBy", "type"));
  const [scriptInfo, setScriptInfo]   = useState(null);
  const [infoLoading, setInfoLoading] = useState(false);
  const [infoErr, setInfoErr]         = useState(null);
  const [output, setOutput]           = useState(null);
  const [running, setRunning]         = useState(false);
  const [runLog, setRunLog]           = useState([]);
  const [hubOk, setHubOk]             = useState(null);
  const [copied, setCopied]           = useState(false);

  // ── Hub health ──────────────────────────────────────────────────────────
  useEffect(() => {
    const check = async () => {
      try {
        const r = await fetch("http://localhost:5130/api/health", { signal: AbortSignal.timeout(2000) });
        setHubOk(r.ok);
      } catch { setHubOk(false); }
    };
    check();
    const id = setInterval(check, 5000);
    return () => clearInterval(id);
  }, []);

  // ── Load scripts from Hub ───────────────────────────────────────────────
  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const r = await fetch(`${SIDECAR}/apps/scripts`);
        const d = await r.json();
        const enriched = (d.scripts || []).map(s => ({
          ...s,
          type:    classifyScript(s),
          project: s.app_name || s.app_id || "Unknown",
        }));
        setScripts(enriched);
        const allKeys = [...new Set([...enriched.map(s => s.type), ...enriched.map(s => s.project)])];
        // Preserve loaded state, only set new groups to open
        setGroupOpen(prev => Object.fromEntries(allKeys.map(k => [k, prev?.[k] ?? true])));
      } catch (e) { setFetchErr(e.message); }
      setLoading(false);
    };
    load();
  }, []);

  // ── Load script info when selection changes ─────────────────────────────
  useEffect(() => {
    if (!selected) { setScriptInfo(null); setInfoErr(null); return; }
    const sc = scripts.find(s => s.id === selected);
    if (!sc) return;
    const load = async () => {
      setInfoLoading(true);
      setScriptInfo(null);
      setInfoErr(null);
      try {
        const r = await fetch(`${SIDECAR}/apps/scripts/info?id=${encodeURIComponent(sc.app_id + '/' + sc.name)}`);
        if (!r.ok) throw new Error(`Hub returned ${r.status}`);
        const ct = r.headers.get("content-type") || "";
        if (!ct.includes("application/json")) throw new Error("Hub returned non-JSON (HTML catch-all)");
        const d = await r.json();
        if (!d.success) throw new Error(d.error || "Unknown error");
        const parsed = parseScriptContent(d.content, sc);
        // Merge Hub-provided structured fields if present
        if (d.parameters && !parsed?.paramLines?.length) {
          if (parsed) parsed.paramLines = [d.parameters];
        }
        if (d.examples?.length && parsed) {
          parsed.usageLines = [...(parsed.usageLines || []), ...d.examples].slice(0, 10);
        }
        setScriptInfo(parsed || { purpose: sc.description || "", fullHeader: "", usageLines: [], paramLines: [], envVars: [], deps: [], noteLines: [], lineCount: d.line_count || 0 });
      } catch (e) {
        setInfoErr(e.message);
        // Still show what we have from the list
        setScriptInfo({ purpose: sc.description || "", fullHeader: "", usageLines: [], paramLines: [], envVars: [], deps: [], noteLines: [], lineCount: 0 });
      }
      setInfoLoading(false);
    };
    load();
  }, [selected, scripts]);

  // ── Persist filter state to localStorage ─────────────────────────────────
  useEffect(() => { saveToLS("filter", filter); }, [filter]);
  useEffect(() => { saveToLS("sortBy", sortBy); }, [sortBy]);
  useEffect(() => { saveToLS("sortDir", sortDir); }, [sortDir]);
  useEffect(() => { saveToLS("groupBy", groupBy); }, [groupBy]);
  useEffect(() => { saveToLS("groupOpen", groupOpen); }, [groupOpen]);

  // ── Sort / filter / group ───────────────────────────────────────────────
  const filtered = scripts.filter(s =>
    !filter ||
    s.name.toLowerCase().includes(filter.toLowerCase()) ||
    s.project.toLowerCase().includes(filter.toLowerCase()) ||
    (s.description || "").toLowerCase().includes(filter.toLowerCase()) ||
    s.type.toLowerCase().includes(filter.toLowerCase())
  );
  const sorted = [...filtered].sort((a, b) => {
    const av = (a[sortBy] || "").toLowerCase();
    const bv = (b[sortBy] || "").toLowerCase();
    return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
  });
  const groupKeys = groupBy === "none"
    ? ["All"]
    : [...new Set(sorted.map(s => groupBy === "type" ? s.type : s.project))].sort();
  const groupedScripts = (key) =>
    groupBy === "none" ? sorted : sorted.filter(s => (groupBy === "type" ? s.type : s.project) === key);

  // ── Actions ─────────────────────────────────────────────────────────────
  const sc = scripts.find(s => s.id === selected) || null;
  const selectScript = (id) => { setSelected(id); setOutput(null); setTab("explorer"); };
  const toggleSort   = (key) => {
    if (sortBy === key) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortBy(key); setSortDir("asc"); }
  };

  const runScript = async () => {
    if (!sc) return;
    setRunning(true); setOutput(null);
    const start = Date.now();
    try {
      const res = await fetch(`${SIDECAR}/apps/scripts/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ app_id: sc.app_id, script_id: sc.name }),
      });
      const dur = Date.now() - start;
      let text;
      try { text = JSON.stringify(await res.json(), null, 2); } catch { text = await res.text(); }
      setOutput({ ok: res.ok, text, dur, exitCode: res.status });
      setRunLog(prev => [{ type:sc.type, name:sc.name, project:sc.project, ok:res.ok, dur, exitCode:res.status, ts:new Date() }, ...prev].slice(0, 50));
    } catch (e) {
      const dur = Date.now() - start;
      setOutput({ ok:false, text:`Network error: ${e.message}`, dur, exitCode:0 });
      setRunLog(prev => [{ type:sc.type, name:sc.name, project:sc.project, ok:false, dur, exitCode:0, ts:new Date() }, ...prev].slice(0, 50));
    }
    setRunning(false);
  };

  const copyCmd = () => {
    if (!sc) return;
    navigator.clipboard?.writeText(sc.command || `bash ${sc.path}`);
    setCopied(true); setTimeout(() => setCopied(false), 1500);
  };

  // ── Style helpers ────────────────────────────────────────────────────────
  const badge = (type) => ({
    fontFamily:"var(--mono)", fontSize:10, fontWeight:700,
    padding:"2px 6px", borderRadius:3, minWidth:62, textAlign:"center",
    display:"inline-block", whiteSpace:"nowrap", flexShrink:0,
    ...(TYPE_STYLE[type] || TYPE_STYLE["Unknown"]),
  });
  const sortBtn = (key) => ({
    padding:"2px 7px", fontSize:10, cursor:"pointer",
    border:"1px solid var(--border-soft)", borderRadius:3,
    background: sortBy===key ? "var(--accent)" : "none",
    color: sortBy===key ? "var(--bg)" : "var(--text-dim)",
    fontWeight: sortBy===key ? 700 : 400,
    display:"flex", alignItems:"center", gap:3,
  });
  const groupBtn = (val) => ({
    padding:"2px 7px", fontSize:10, cursor:"pointer",
    border:"1px solid var(--border-soft)", borderRadius:3,
    background: groupBy===val ? "var(--bg-panel)" : "none",
    color: groupBy===val ? "var(--text)" : "var(--text-dim)",
    fontWeight: groupBy===val ? 600 : 400,
  });
  const sectionLabel = { fontSize:10, textTransform:"uppercase", letterSpacing:1, color:"var(--text-dim)", marginBottom:5 };
  const card = { background:"var(--bg-inset)", borderRadius:4, border:"1px solid var(--border-soft)", overflow:"hidden" };

  const hubDot   = hubOk===null ? "var(--yellow)" : hubOk ? "var(--green)" : "var(--red)";
  const hubLabel = hubOk===null ? "checking…" : hubOk ? "sidecar:5130 · online" : "sidecar:5130 · offline";

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div style={{ display:"flex", flexDirection:"column", height:"100%", overflow:"hidden" }}>

      {/* topbar */}
      <div style={{ display:"flex", alignItems:"center", gap:10, padding:"8px 16px", borderBottom:"1px solid var(--border-soft)", background:"var(--bg-inset)", flexShrink:0, flexWrap:"wrap" }}>
        <div style={{ fontWeight:700, fontSize:13, letterSpacing:.4 }}>Scripts <span style={{ color:"var(--accent)" }}>Explorer</span></div>
        <div style={{ display:"flex" }}>
          {["explorer","runlog"].map((t,i) => (
            <button key={t} onClick={() => setTab(t)} style={{
              padding:"3px 12px", fontSize:11, cursor:"pointer",
              border:"1px solid var(--border-soft)",
              borderRight: i===0 ? "none" : undefined,
              borderRadius: i===0 ? "4px 0 0 4px" : "0 4px 4px 0",
              background: tab===t ? "var(--accent)" : "none",
              color: tab===t ? "var(--bg)" : "var(--text-dim)",
              fontWeight: tab===t ? 700 : 400,
            }}>
              {t==="explorer" ? "Explorer" : `Run Log${runLog.length ? ` (${runLog.length})` : ""}`}
            </button>
          ))}
        </div>
        <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
          {Object.entries(TYPE_STYLE).filter(([k])=>k!=="Unknown").map(([t,s]) => (
            <span key={t} style={{ display:"flex", alignItems:"center", gap:3, fontSize:10, color:"var(--text-dim)" }}>
              <span style={{ width:6, height:6, borderRadius:"50%", background:s.color, display:"inline-block" }} />
              {t}
            </span>
          ))}
        </div>
        <div style={{ marginLeft:"auto", display:"flex", alignItems:"center", gap:6, fontSize:11, color:"var(--text-dim)" }}>
          <div style={{ width:7, height:7, borderRadius:"50%", background:hubDot }} />
          <span>{hubLabel}</span>
        </div>
      </div>

      <div style={{ display:"flex", flex:1, overflow:"hidden" }}>

        {/* LEFT list */}
        <div style={{ width:300, minWidth:300, borderRight:"1px solid var(--border-soft)", display:"flex", flexDirection:"column", background:"var(--bg-inset)", overflow:"hidden" }}>
          <div style={{ padding:"7px 10px 4px", borderBottom:"1px solid var(--border-soft)", flexShrink:0 }}>
            <input
              style={{ width:"100%", background:"var(--bg)", border:"1px solid var(--border-soft)", color:"var(--text)", borderRadius:4, padding:"4px 9px", fontFamily:"inherit", fontSize:12, outline:"none", boxSizing:"border-box" }}
              placeholder="Filter by name, project, type…"
              value={filter} onChange={e => setFilter(e.target.value)}
            />
          </div>
          <div style={{ padding:"5px 10px", borderBottom:"1px solid var(--border-soft)", flexShrink:0, display:"flex", flexDirection:"column", gap:5 }}>
            <div style={{ display:"flex", alignItems:"center", gap:5 }}>
              <span style={{ fontSize:10, color:"var(--text-dim)", minWidth:32 }}>Sort</span>
              {SORT_OPTIONS.map(o => (
                <button key={o.key} onClick={() => toggleSort(o.key)} style={sortBtn(o.key)}>
                  {o.label}{sortBy===o.key && <span style={{fontSize:9}}>{sortDir==="asc"?"↑":"↓"}</span>}
                </button>
              ))}
            </div>
            <div style={{ display:"flex", alignItems:"center", gap:5 }}>
              <span style={{ fontSize:10, color:"var(--text-dim)", minWidth:32 }}>Group</span>
              {[["type","Type"],["project","Project"],["none","None"]].map(([v,l]) => (
                <button key={v} onClick={() => setGroupBy(v)} style={groupBtn(v)}>{l}</button>
              ))}
            </div>
            <div style={{ display:"flex", alignItems:"center", gap:5 }}>
              <span style={{ fontSize:10, color:"var(--text-dim)", minWidth:32 }}>Collapse</span>
              <button onClick={() => setGroupOpen(Object.fromEntries(groupKeys.map(k => [k, false])))} style={sortBtn(false)}>
                All
              </button>
              <button onClick={() => setGroupOpen(Object.fromEntries(groupKeys.map(k => [k, true])))} style={sortBtn(true)}>
                Expand
              </button>
            </div>
          </div>
          <div style={{ padding:"3px 12px", fontSize:10, color:"var(--text-dim)", borderBottom:"1px solid var(--border-soft)", flexShrink:0 }}>
            {loading ? "Loading scripts…" : fetchErr ? `Error: ${fetchErr}` :
              filter ? `${filtered.length} of ${scripts.length} scripts` :
              `${scripts.length} scripts · ${[...new Set(scripts.map(s=>s.project))].length} projects`}
          </div>
          <div style={{ flex:1, overflowY:"auto" }}>
            {loading ? (
              <div style={{ padding:20, textAlign:"center", color:"var(--text-dim)", fontSize:12 }}>Loading from Hub…</div>
            ) : fetchErr ? (
              <div style={{ padding:16, color:"var(--red)", fontSize:12 }}>{fetchErr}</div>
            ) : (
              groupKeys.map(key => {
                const items = groupedScripts(key);
                if (!items.length) return null;
                const isOpen = groupBy==="none" ? true : (groupOpen[key] ?? true);
                return (
                  <div key={key}>
                    {groupBy !== "none" && (
                      <ScriptGroupHeader
                        name={key}
                        isOpen={isOpen}
                        onToggle={() => setGroupOpen(p => ({ ...p, [key]: !p[key] }))}
                        itemCount={items.length}
                        groupBy={groupBy}
                      />
                    )}
                    {isOpen && items.map(s => (
                      <ScriptItem
                        key={s.id}
                        script={s}
                        isSelected={selected === s.id}
                        onSelect={() => selectScript(s.id)}
                      />
                    ))}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* RIGHT */}
        <div style={{ flex:1, display:"flex", flexDirection:"column", overflow:"hidden" }}>
          {tab==="runlog" ? (
            runLog.length ? (
              <div style={{ padding:14, flex:1, overflowY:"auto" }}>
                <div style={sectionLabel}>Run history · {runLog.length} entries</div>
                <div style={{ display:"flex", flexDirection:"column", gap:5 }}>
                  {runLog.map((l,i) => (
                    <div key={i} style={{ display:"flex", alignItems:"baseline", gap:8, padding:"5px 10px", background:"var(--bg-inset)", borderRadius:4, borderLeft:`3px solid ${l.ok?"var(--green)":"var(--red)"}` }}>
                      <span style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--text-dim)", minWidth:64 }}>{l.ts.toLocaleTimeString("en-US",{hour12:false})}</span>
                      <ScriptTypeBadge type={l.type} />
                      <span style={{ fontFamily:"var(--mono)", fontSize:11 }}>{l.name}</span>
                      <span style={{ fontSize:10, color:"var(--text-dim)", flex:1, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{l.project}</span>
                      <span style={{ fontFamily:"var(--mono)", fontSize:10, color:l.ok?"var(--green)":"var(--red)" }}>{l.ok?"OK":`exit ${l.exitCode||"ERR"}`}</span>
                      <span style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--text-dim)" }}>{l.dur}ms</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : <div style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center", color:"var(--text-dim)", fontSize:12 }}>No scripts run yet.</div>
          ) : !sc ? (
            <div style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center", color:"var(--text-dim)", fontSize:12 }}>← Select a script to view details</div>
          ) : (
            <>
              {/* detail header */}
              <div style={{ padding:"11px 16px", borderBottom:"1px solid var(--border-soft)", background:"var(--bg-panel)", flexShrink:0 }}>
                <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:4 }}>
                  <span style={badge(sc.type)}>{sc.type}</span>
                  <span style={{ fontFamily:"var(--mono)", fontSize:13 }}>{sc.name}</span>
                  <span style={{ fontSize:10, color:"var(--text-dim)", padding:"2px 7px", background:"var(--bg-inset)", borderRadius:3, border:"1px solid var(--border-soft)" }}>{sc.project}</span>
                  {scriptInfo?.lineCount > 0 && <span style={{ fontSize:10, color:"var(--text-dim)", marginLeft:"auto" }}>{scriptInfo.lineCount} lines</span>}
                </div>
                <div style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--text-dim)", marginBottom:9, padding:"4px 8px", background:"var(--bg-inset)", borderRadius:3, border:"1px solid var(--border-soft)", overflowX:"auto", whiteSpace:"nowrap" }}>
                  {sc.path}
                </div>
                <div style={{ display:"flex", gap:8, alignItems:"center" }}>
                  <button onClick={runScript} disabled={running||!hubOk}
                    style={{ padding:"4px 14px", background:"var(--accent)", color:"var(--bg)", border:"none", borderRadius:4, fontFamily:"inherit", fontWeight:700, fontSize:12, cursor:running||!hubOk?"not-allowed":"pointer", opacity:running||!hubOk?0.6:1 }}>
                    {running ? "Running…" : "▶ Run"}
                  </button>
                  <button onClick={copyCmd}
                    style={{ padding:"4px 11px", background:"none", border:"1px solid var(--border-soft)", color:"var(--text-dim)", borderRadius:4, fontFamily:"inherit", fontSize:12, cursor:"pointer" }}>
                    {copied ? "Copied!" : "Copy command"}
                  </button>
                  {!hubOk && <span style={{ fontSize:11, color:"var(--red)" }}>⚠ Hub offline</span>}
                </div>
              </div>

              {/* info + output */}
              <div style={{ flex:1, overflowY:"auto", padding:14, display:"flex", flexDirection:"column", gap:14 }}>

                {infoLoading && (
                  <div style={{ fontSize:11, color:"var(--text-dim)", display:"flex", alignItems:"center", gap:8 }}>
                    <span style={{ display:"inline-block", width:10, height:10, borderRadius:"50%", border:"2px solid var(--accent)", borderTopColor:"transparent", animation:"spin 0.8s linear infinite" }} />
                    Reading script…
                  </div>
                )}

                {infoErr && (
                  <div style={{ fontSize:11, color:"var(--accent)", padding:"6px 10px", background:"color-mix(in srgb, var(--accent) 12%, var(--bg-inset))", borderRadius:4, border:"1px solid color-mix(in srgb, var(--accent) 30%, var(--border-soft))" }}>
                    ⚠ Could not read script file: {infoErr}
                  </div>
                )}

                {scriptInfo && !infoLoading && (
                  <>
                    {/* Purpose */}
                    {scriptInfo.purpose && (
                      <div>
                        <div style={sectionLabel}>Purpose</div>
                        <div style={{ fontSize:12, lineHeight:1.7, color:"var(--text)", padding:"8px 12px", background:"var(--bg-inset)", borderRadius:4, borderLeft:"3px solid var(--accent)" }}>
                          {scriptInfo.purpose}
                        </div>
                      </div>
                    )}

                    {/* Usage */}
                    {scriptInfo.usageLines.length > 0 && (
                      <div>
                        <div style={sectionLabel}>Usage</div>
                        <div style={card}>
                          {scriptInfo.usageLines.map((l,i) => (
                            <div key={i} style={{ fontFamily:"var(--mono)", fontSize:11, padding:"6px 12px", borderBottom:i<scriptInfo.usageLines.length-1?"1px solid var(--border-soft)":"none", lineHeight:1.5, display:"flex", gap:8, alignItems:"baseline" }}>
                              <span style={{ color:"var(--yellow)", userSelect:"none", flexShrink:0 }}>$</span>
                              <span style={{ color:"var(--text)" }}>{l}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Parameters */}
                    {scriptInfo.paramLines.length > 0 && (
                      <div>
                        <div style={sectionLabel}>Parameters</div>
                        <div style={card}>
                          {scriptInfo.paramLines.map((l,i) => {
                            const parts = l.split(/\s{2,}|\t/);
                            return (
                              <div key={i} style={{ fontFamily:"var(--mono)", fontSize:11, padding:"6px 12px", borderBottom:i<scriptInfo.paramLines.length-1?"1px solid var(--border-soft)":"none", lineHeight:1.5, display:"flex", gap:16 }}>
                                <span style={{ color:"#4fa8d9", flexShrink:0, minWidth:160 }}>{parts[0]}</span>
                                {parts.slice(1).map((p,j) => <span key={j} style={{ color:"var(--text-dim)" }}>{p}</span>)}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* Env vars + deps row */}
                    {(scriptInfo.envVars.length > 0 || scriptInfo.deps.length > 0) && (
                      <div style={{ display:"flex", gap:14, flexWrap:"wrap" }}>
                        {scriptInfo.envVars.length > 0 && (
                          <div style={{ flex:1, minWidth:180 }}>
                            <div style={sectionLabel}>Env Variables</div>
                            <div style={{ display:"flex", flexWrap:"wrap", gap:5 }}>
                              {scriptInfo.envVars.map(v => (
                                <span key={v} style={{ fontFamily:"var(--mono)", fontSize:10, padding:"2px 8px", background:"color-mix(in srgb, var(--yellow) 14%, var(--bg-inset))", color:"var(--yellow)", borderRadius:3, border:"1px solid color-mix(in srgb, var(--yellow) 30%, var(--border-soft))" }}>{v}</span>
                              ))}
                            </div>
                          </div>
                        )}
                        {scriptInfo.deps.length > 0 && (
                          <div style={{ flex:1, minWidth:140 }}>
                            <div style={sectionLabel}>Requires</div>
                            <div style={{ display:"flex", flexWrap:"wrap", gap:5 }}>
                              {scriptInfo.deps.map(d => (
                                <span key={d} style={{ fontFamily:"var(--mono)", fontSize:10, padding:"2px 8px", background:"color-mix(in srgb, #4fa8d9 14%, var(--bg-inset))", color:"#4fa8d9", borderRadius:3, border:"1px solid color-mix(in srgb, #4fa8d9 30%, var(--border-soft))" }}>{d}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Notes / warnings */}
                    {scriptInfo.noteLines.length > 0 && (
                      <div>
                        <div style={sectionLabel}>Notes</div>
                        <div style={{ ...card, borderLeft:"3px solid var(--yellow)" }}>
                          {scriptInfo.noteLines.map((l,i) => (
                            <div key={i} style={{ fontSize:12, padding:"5px 12px", borderBottom:i<scriptInfo.noteLines.length-1?"1px solid var(--border-soft)":"none", lineHeight:1.6, color:"var(--text-dim)" }}>{l}</div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Full header */}
                    {scriptInfo.fullHeader && (
                      <details>
                        <summary style={{ ...sectionLabel, cursor:"pointer", userSelect:"none", marginBottom:4, listStyle:"none", display:"flex", alignItems:"center", gap:5 }}>
                          <span style={{ fontSize:9 }}>▶</span> Full Header Comment
                        </summary>
                        <pre style={{ fontFamily:"var(--mono)", fontSize:10, lineHeight:1.6, color:"var(--text-dim)", background:"var(--bg-inset)", borderRadius:4, border:"1px solid var(--border-soft)", padding:"8px 12px", overflowX:"auto", margin:"6px 0 0", whiteSpace:"pre-wrap" }}>
                          {scriptInfo.fullHeader}
                        </pre>
                      </details>
                    )}
                  </>
                )}

                {/* Output */}
                <div>
                  <div style={sectionLabel}>Output</div>
                  <div style={{
                    background:"var(--bg-inset)",
                    border:`1px solid ${running?"var(--border-soft)":output?.ok?"color-mix(in srgb, var(--green) 35%, var(--bg-inset))":output?"color-mix(in srgb, var(--red) 35%, var(--bg-inset))":"var(--border-soft)"}`,
                    borderRadius:4, padding:"10px 12px",
                    fontFamily:"var(--mono)", fontSize:11, lineHeight:1.7,
                    whiteSpace:"pre-wrap", overflowX:"auto",
                    minHeight:80, maxHeight:220, overflowY:"auto",
                    color:running?"var(--yellow)":output?.ok?"var(--green)":output?"var(--red)":"var(--text-dim)",
                  }}>
                    {running ? "Running script…" : output ? (
                      <>
                        <span style={{ display:"inline-block", fontFamily:"var(--mono)", fontSize:11, padding:"2px 8px", borderRadius:3, marginRight:8, background:output.ok?"color-mix(in srgb, var(--green) 18%, var(--bg-inset))":"color-mix(in srgb, var(--red) 18%, var(--bg-inset))", color:output.ok?"var(--green)":"var(--red)" }}>
                          {output.ok?"OK":`exit ${output.exitCode||"ERR"}`}
                        </span>
                        <span style={{ color:"var(--text-dim)", fontSize:10 }}>{output.dur}ms</span>
                        {"\n\n"}{output.text}
                      </>
                    ) : "No output yet — click ▶ Run to execute this script."}
                  </div>
                </div>

              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
