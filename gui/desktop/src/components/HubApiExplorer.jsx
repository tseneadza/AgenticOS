import { useState, useEffect } from "react";

const HUB = "http://localhost:8085/api";
const SIDECAR = "http://localhost:5130";

// All 42 Hub + Sidecar API endpoints (comprehensive list)
const ENDPOINTS_HARDCODED = [
  { group:"Cards", method:"GET",    path:"/cards",                    desc:"List all registered project cards", params:[] },
  { group:"Cards", method:"GET",    path:"/cards/favorites",          desc:"Cards marked as favourite", params:[] },
  { group:"Cards", method:"GET",    path:"/cards/recent",             desc:"Recently accessed cards", params:[] },
  { group:"Cards", method:"GET",    path:"/cards/{id}",               desc:"Single card detail", params:[{name:"id",_in:"path",type:"string",required:true,hint:"e.g. dreamcatcher"}] },
  { group:"Cards", method:"GET",    path:"/cards/{id}/status",        desc:"Running / stopped status", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Cards", method:"GET",    path:"/cards/{id}/health",        desc:"Health check for card service", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Cards", method:"POST",   path:"/cards/{id}/start",         desc:"Start the card service", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Cards", method:"POST",   path:"/cards/{id}/stop",          desc:"Stop the card service", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Cards", method:"POST",   path:"/cards/{id}/restart",       desc:"Restart the card service", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Cards", method:"POST",   path:"/cards/{id}/favorite",      desc:"Mark card as favourite", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Cards", method:"DELETE", path:"/cards/{id}/favorite",      desc:"Remove from favourites", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Logs & Env", method:"GET",    path:"/cards/{id}/logs",        desc:"Fetch recent log output", params:[{name:"id",_in:"path",type:"string",required:true},{name:"lines",_in:"query",type:"number",required:false,hint:"50"}] },
  { group:"Logs & Env", method:"GET",    path:"/cards/{id}/logs/stream", desc:"SSE stream of live logs", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Logs & Env", method:"GET",    path:"/cards/{id}/env",         desc:"Get environment variables", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Logs & Env", method:"POST",   path:"/cards/{id}/env",         desc:"Set / update env vars", params:[{name:"id",_in:"path",type:"string",required:true},{name:"body",_in:"body",type:"json",required:true,hint:'{"KEY":"value"}'}] },
  { group:"Logs & Env", method:"DELETE", path:"/cards/{id}/env/{key}",   desc:"Delete an env var", params:[{name:"id",_in:"path",type:"string",required:true},{name:"key",_in:"path",type:"string",required:true}] },
  { group:"Scripts", method:"GET",  path:"/scripts",             desc:"All registered scripts", params:[] },
  { group:"Scripts", method:"GET",  path:"/cards/{id}/scripts",  desc:"Scripts for a specific card", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Scripts", method:"POST", path:"/scripts/run",         desc:"Execute a script", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"script":"path/to/script.sh"}'}] },
  { group:"Scripts", method:"GET",  path:"/scripts/terminal",    desc:"Open terminal for scripts", params:[] },
  { group:"Analytics", method:"GET", path:"/analytics",              desc:"Global analytics data", params:[] },
  { group:"Analytics", method:"GET", path:"/cards/{id}/analytics",   desc:"Per-card analytics", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Discovery", method:"GET",  path:"/tags",      desc:"All card tags", params:[] },
  { group:"Discovery", method:"GET",  path:"/ports",     desc:"Port assignments", params:[] },
  { group:"Discovery", method:"POST", path:"/discover",  desc:"Re-discover local projects", params:[] },
  { group:"Discovery", method:"POST", path:"/stop-all",  desc:"Stop all running services", params:[] },
  { group:"Jupyter", method:"GET",  path:"/jupyter/directories", desc:"List notebook directories", params:[] },
  { group:"Jupyter", method:"POST", path:"/jupyter/launch",      desc:"Launch a Jupyter server", params:[{name:"body",_in:"body",type:"json",required:false,hint:'{"dir":"/path/to/notebooks"}'}] },
  { group:"Jupyter", method:"GET",  path:"/jupyter/status",      desc:"Jupyter running status", params:[] },
  { group:"Jupyter", method:"POST", path:"/jupyter/stop",        desc:"Stop Jupyter server", params:[] },
  { group:"System", method:"GET", path:"/health", desc:"Hub server health (root level)", params:[], rootPath:true },
  { group:"News (Sidecar)", server:"sidecar", method:"GET",    path:"/api/news/categories",      desc:"List feed categories (id, name, color)", params:[] },
  { group:"News (Sidecar)", server:"sidecar", method:"POST",   path:"/api/news/categories",      desc:"Create a category", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"name":"Robotics","color":"#7fb069"}'}] },
  { group:"News (Sidecar)", server:"sidecar", method:"PATCH",  path:"/api/news/categories/{id}", desc:"Update a category", params:[{name:"id",_in:"path",type:"string",required:true},{name:"body",_in:"body",type:"json",required:true,hint:'{"color":"#d97b4f"}'}] },
  { group:"News (Sidecar)", server:"sidecar", method:"DELETE", path:"/api/news/categories/{id}", desc:"Delete a category (and its feeds)", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"News (Sidecar)", server:"sidecar", method:"GET",    path:"/api/news/feeds",           desc:"List feeds (joined to category)", params:[{name:"enabled_only",_in:"query",type:"boolean",required:false,hint:"true"},{name:"category_id",_in:"query",type:"string",required:false}] },
  { group:"News (Sidecar)", server:"sidecar", method:"POST",   path:"/api/news/feeds",           desc:"Create a feed", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"label":"New Scientist","url":"https://...","category_id":"physics-space"}'}] },
  { group:"News (Sidecar)", server:"sidecar", method:"PATCH",  path:"/api/news/feeds/{id}",      desc:"Update a feed (enable/disable, recategorize)", params:[{name:"id",_in:"path",type:"string",required:true},{name:"body",_in:"body",type:"json",required:true,hint:'{"enabled":false}'}] },
  { group:"News (Sidecar)", server:"sidecar", method:"DELETE", path:"/api/news/feeds/{id}",      desc:"Delete a feed", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"News (Sidecar)", server:"sidecar", method:"POST",   path:"/api/news/fetch",           desc:"Fetch + keyword-filter RSS items", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"urls":["https://..."],"keywords":["quantum"]}'}] },
  { group:"News (Sidecar)", server:"sidecar", method:"POST",   path:"/api/news/rank",            desc:"AI-rank articles via the app's active model", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"articles":[{"title":"…"}],"domains":[],"keywords":[]}'}] },
  { group:"System", server:"sidecar", method:"GET", path:"/api/health", desc:"Sidecar health", params:[] },
];

// Convert OpenAPI spec to explorer format
function convertOpenAPIToEndpoints(spec) {
  const endpoints = [];
  if (!spec?.paths) return endpoints;

  for (const [path, methods] of Object.entries(spec.paths)) {
    for (const [method, details] of Object.entries(methods)) {
      if (!["get", "post", "put", "delete", "patch"].includes(method.toLowerCase())) continue;

      const params = [];
      if (details.parameters) {
        details.parameters.forEach(p => {
          params.push({
            name: p.name,
            _in: p.in || "query",
            type: p.schema?.type || "string",
            required: p.required || false,
            hint: p.description || "",
          });
        });
      }
      if (details.requestBody) {
        params.push({
          name: "body",
          _in: "body",
          type: "json",
          required: details.requestBody.required || false,
          hint: "Request body",
        });
      }

      endpoints.push({
        group: details.tags?.[0] || "Other",
        method: method.toUpperCase(),
        path: path,
        desc: details.summary || details.description || "",
        params: params,
        server: path.startsWith("/api") ? "sidecar" : "hub",
      });
    }
  }
  return endpoints;
}

const METHOD_COLOR = {
  GET:    { bg:"#1c3a2a", color:"#7fb069" },
  POST:   { bg:"#3a2a1c", color:"#d97b4f" },
  DELETE: { bg:"#3a1c1c", color:"#d9534f" },
  PUT:    { bg:"#2a2a1c", color:"#e0b84c" },
};

function buildUrl(ep, paramValues) {
  let path = ep.path;
  ep.params.filter(p => p._in === "path").forEach(p => {
    path = path.replace(`{${p.name}}`, paramValues[p.name] || `{${p.name}}`);
  });
  const qp = ep.params.filter(p => p._in === "query" && paramValues[p.name]);
  const qs = qp.map(p => `${p.name}=${encodeURIComponent(paramValues[p.name])}`).join("&");
  const base = ep.server === "sidecar" ? SIDECAR
             : ep.rootPath ? "http://localhost:8085" : HUB;
  return base + path + (qs ? "?" + qs : "");
}

function PathDisplay({ path }) {
  return path.split(/(\{[^}]+\})/).map((seg, i) =>
    seg.startsWith("{")
      ? <span key={i} style={{ color: "#d97b4f" }}>{seg}</span>
      : <span key={i}>{seg}</span>
  );
}

export default function HubApiExplorer() {
  const [endpoints, setEndpoints]   = useState(ENDPOINTS_HARDCODED);
  const [tab, setTab]               = useState("explorer");
  const [selected, setSelected]     = useState(null);
  const [groupOpen, setGroupOpen]   = useState(() =>
    Object.fromEntries(
      [...new Set(ENDPOINTS_HARDCODED.map(e => e.group))].map(g => [g, true])
    )
  );
  const [filter, setFilter]         = useState("");
  const [paramValues, setParamValues] = useState({});
  const [response, setResponse]     = useState(null);
  const [loading, setLoading]       = useState(false);
  const [callLog, setCallLog]       = useState([]);
  const [hubColor, setHubColor]     = useState("#e0b84c");
  const [hubLabel, setHubLabel]     = useState("localhost:8085");
  const [sidecarColor, setSidecarColor] = useState("#e0b84c");
  const [sidecarLabel, setSidecarLabel] = useState("localhost:5130");
  const [copied, setCopied]         = useState(false);

  useEffect(() => {
    const check = async () => {
      try {
        const r = await fetch("http://localhost:8085/health", { signal: AbortSignal.timeout(2000) });
        setHubColor(r.ok ? "#7fb069" : "#e0b84c");
        setHubLabel(r.ok ? "localhost:8085 · online" : `localhost:8085 · ${r.status}`);
      } catch {
        setHubColor("#d9534f");
        setHubLabel("localhost:8085 · offline");
      }
    };
    check();
    const id = setInterval(check, 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const check = async () => {
      try {
        const r = await fetch("http://localhost:5130/api/health", { signal: AbortSignal.timeout(2000) });
        setSidecarColor(r.ok ? "#7fb069" : "#e0b84c");
        setSidecarLabel(r.ok ? "localhost:5130 · online" : `localhost:5130 · ${r.status}`);
      } catch {
        setSidecarColor("#d9534f");
        setSidecarLabel("localhost:5130 · offline");
      }
    };
    check();
    const id = setInterval(check, 5000);
    return () => clearInterval(id);
  }, []);

  const groups = [...new Set(endpoints.map(e => e.group))];
  const ep  = selected !== null ? endpoints[selected] : null;
  const url = ep ? buildUrl(ep, paramValues) : "";
  const curlCmd = ep ? `curl -X ${ep.method} "${url}"` : "";

  const selectEndpoint = (idx) => {
    setSelected(idx);
    setParamValues({});
    setResponse(null);
    setTab("explorer");
  };

  const tryIt = async () => {
    if (!ep) return;
    setLoading(true);
    setResponse(null);
    const bodyParam = ep.params.find(p => p._in === "body");
    const start = Date.now();
    try {
      const opts = { method: ep.method, headers: { "Content-Type": "application/json" } };
      if (bodyParam && paramValues[bodyParam.name]) {
        try { opts.body = JSON.stringify(JSON.parse(paramValues[bodyParam.name])); }
        catch { opts.body = paramValues[bodyParam.name]; }
      }
      const res = await fetch(url, opts);
      const dur = Date.now() - start;
      let text;
      try { text = JSON.stringify(await res.json(), null, 2); }
      catch { text = await res.text(); }
      setResponse({ status: res.status, text, ok: res.ok, dur });
      setCallLog(prev => [{ method: ep.method, path: ep.path, status: res.status, dur, ok: res.ok, ts: new Date() }, ...prev].slice(0, 50));
    } catch (e) {
      const dur = Date.now() - start;
      const where = ep.server === "sidecar" ? "the sidecar at localhost:5130" : "Hub at localhost:8085";
      setResponse({ status: 0, text: `Network error: ${e.message}\n\n(Is ${where} running?)`, ok: false, dur });
      setCallLog(prev => [{ method: ep.method, path: ep.path, status: 0, dur, ok: false, ts: new Date() }, ...prev].slice(0, 50));
    }
    setLoading(false);
  };

  const copyCurl = () => {
    navigator.clipboard?.writeText(curlCmd);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const filteredEps = (group) =>
    endpoints.map((e, i) => ({ ...e, _i: i })).filter(e =>
      e.group === group &&
      (!filter || e.path.toLowerCase().includes(filter) || e.method.toLowerCase().includes(filter) || e.desc.toLowerCase().includes(filter))
    );

  const badge = (m) => ({
    fontFamily: "var(--mono)", fontSize: 10, fontWeight: 700,
    padding: "2px 6px", borderRadius: 3, minWidth: 44, textAlign: "center",
    display: "inline-block", ...(METHOD_COLOR[m] || METHOD_COLOR.GET),
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>

      {/* ── sub-topbar ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 16px", borderBottom: "1px solid var(--border-soft)", background: "var(--bg-inset)", flexShrink: 0 }}>
        <div style={{ fontWeight: 700, fontSize: 13, letterSpacing: .4 }}>Codehome <span style={{ color: "var(--accent)" }}>API Explorer</span></div>
        <div style={{ display: "flex", marginLeft: 12 }}>
          {["explorer", "calllog"].map((t, i) => (
            <button key={t} onClick={() => setTab(t)} style={{
              padding: "3px 12px", fontSize: 11, cursor: "pointer",
              border: "1px solid var(--border-soft)",
              borderRight: i === 0 ? "none" : "1px solid var(--border-soft)",
              borderRadius: i === 0 ? "4px 0 0 4px" : "0 4px 4px 0",
              background: tab === t ? "var(--accent)" : "none",
              color: tab === t ? "#1b1b19" : "var(--text-dim)",
              fontWeight: tab === t ? 700 : 400,
            }}>
              {t === "explorer" ? "Explorer" : `Call Log${callLog.length ? ` (${callLog.length})` : ""}`}
            </button>
          ))}
        </div>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 14, fontSize: 11, color: "var(--text-dim)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{ width: 7, height: 7, borderRadius: "50%", background: hubColor }} />
            <span>Hub {hubLabel}</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{ width: 7, height: 7, borderRadius: "50%", background: sidecarColor }} />
            <span>Sidecar {sidecarLabel}</span>
          </div>
        </div>
      </div>

      {/* ── body ── */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

        {/* LEFT: endpoint list */}
        <div style={{ width: 290, minWidth: 290, borderRight: "1px solid var(--border-soft)", display: "flex", flexDirection: "column", background: "var(--bg-inset)", overflow: "hidden" }}>
          <div style={{ padding: "7px 10px", borderBottom: "1px solid var(--border-soft)", flexShrink: 0, display: "flex", flexDirection: "column", gap: 7 }}>
            <input
              style={{ width: "100%", background: "var(--bg)", border: "1px solid var(--border-soft)", color: "var(--text)", borderRadius: 4, padding: "4px 9px", fontFamily: "inherit", fontSize: 12, outline: "none" }}
              placeholder="Filter endpoints…"
              value={filter}
              onChange={e => setFilter(e.target.value)}
            />
            <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
              <span style={{ fontSize: 10, color: "var(--text-dim)" }}>Collapse:</span>
              <button
                onClick={() => setGroupOpen(Object.fromEntries(groups.map(g => [g, false])))}
                style={{ padding: "2px 8px", fontSize: 10, cursor: "pointer", border: "1px solid var(--border-soft)", borderRadius: 3, background: "none", color: "var(--text-dim)" }}
              >
                All
              </button>
              <button
                onClick={() => setGroupOpen(Object.fromEntries(groups.map(g => [g, true])))}
                style={{ padding: "2px 8px", fontSize: 10, cursor: "pointer", border: "1px solid var(--border-soft)", borderRadius: 3, background: "none", color: "var(--text-dim)" }}
              >
                Expand
              </button>
            </div>
          </div>
          <div style={{ flex: 1, overflowY: "auto" }}>
            {groups.map(g => {
              const items = filteredEps(g);
              if (!items.length) return null;
              return (
                <div key={g}>
                  <div
                    style={{ padding: "7px 12px 4px", fontSize: 10, textTransform: "uppercase", letterSpacing: 1.2, color: "var(--text-dim)", borderBottom: "1px solid var(--border-soft)", display: "flex", justifyContent: "space-between", cursor: "pointer", userSelect: "none" }}
                    onClick={() => setGroupOpen(p => ({ ...p, [g]: !p[g] }))}
                  >
                    <span>{g}</span>
                    <span style={{ fontSize: 9, display: "inline-block", transform: groupOpen[g] ? "rotate(90deg)" : "rotate(0deg)", transition: "transform .15s" }}>▶</span>
                  </div>
                  {groupOpen[g] && items.map(e => (
                    <div
                      key={e._i}
                      style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 12px", cursor: "pointer", borderLeft: selected === e._i ? "3px solid var(--accent)" : "3px solid transparent", background: selected === e._i ? "#272724" : "transparent" }}
                      onClick={() => selectEndpoint(e._i)}
                    >
                      <span style={badge(e.method)}>{e.method}</span>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 11, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        <PathDisplay path={e.path} />
                      </span>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </div>

        {/* RIGHT: detail or call log */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {tab === "calllog" ? (
            callLog.length ? (
              <div style={{ padding: 14, flex: 1, overflowY: "auto" }}>
                <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 1, color: "var(--text-dim)", marginBottom: 8 }}>Recent calls · {callLog.length} total</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                  {callLog.map((l, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "baseline", gap: 8, padding: "5px 10px", background: "var(--bg-inset)", borderRadius: 4, borderLeft: `3px solid ${l.ok ? "#7fb069" : "#d9534f"}`, fontSize: 12 }}>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-dim)", minWidth: 64 }}>{l.ts.toLocaleTimeString("en-US", { hour12: false })}</span>
                      <span style={badge(l.method)}>{l.method}</span>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 11, flex: 1 }}>{l.path}</span>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: l.ok ? "#7fb069" : "#d9534f" }}>{l.status || "ERR"}</span>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-dim)" }}>{l.dur}ms</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-dim)", fontSize: 12 }}>No calls yet — use Explorer to run requests.</div>
            )
          ) : !ep ? (
            <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-dim)", fontSize: 12 }}>← Select an endpoint to explore</div>
          ) : (
            <>
              <div style={{ padding: "11px 16px", borderBottom: "1px solid var(--border-soft)", background: "var(--bg-panel)", flexShrink: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 5 }}>
                  <span style={badge(ep.method)}>{ep.method}</span>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 13 }}><PathDisplay path={ep.path} /></span>
                </div>
                <div style={{ fontSize: 12, color: "var(--text-dim)" }}>{ep.desc}</div>
                <div style={{ display: "flex", gap: 8, marginTop: 9, alignItems: "center" }}>
                  <button
                    onClick={tryIt}
                    disabled={loading}
                    style={{ padding: "4px 14px", background: "var(--accent)", color: "#1b1b19", border: "none", borderRadius: 4, fontFamily: "inherit", fontWeight: 700, fontSize: 12, cursor: "pointer" }}
                  >
                    {loading ? "…" : "▶ Run"}
                  </button>
                  <button
                    onClick={copyCurl}
                    style={{ padding: "4px 11px", background: "none", border: "1px solid var(--border-soft)", color: "var(--text-dim)", borderRadius: 4, fontFamily: "inherit", fontSize: 12, cursor: "pointer" }}
                  >
                    {copied ? "Copied!" : "Copy curl"}
                  </button>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-dim)", marginLeft: "auto", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 340 }}>{curlCmd}</span>
                </div>
              </div>

              <div style={{ flex: 1, overflowY: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 14 }}>
                {ep.params.length > 0 && (
                  <div>
                    <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 1, color: "var(--text-dim)", marginBottom: 6 }}>Parameters</div>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                      <thead>
                        <tr>
                          {["Name", "In", "Type", "Value"].map(h => (
                            <th key={h} style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid var(--border-soft)", color: "var(--text-dim)", fontWeight: 600, fontSize: 11 }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {ep.params.map(p => (
                          <tr key={p.name}>
                            <td style={{ padding: "5px 8px", borderBottom: "1px solid #2a2a28" }}>
                              <span style={{ color: "var(--accent)", fontFamily: "var(--mono)", fontSize: 11 }}>{p.name}</span>
                              {p.required && <span style={{ color: "#d9534f", fontSize: 10 }}> *</span>}
                            </td>
                            <td style={{ padding: "5px 8px", borderBottom: "1px solid #2a2a28", color: "var(--text-dim)", fontSize: 11 }}>{p._in}</td>
                            <td style={{ padding: "5px 8px", borderBottom: "1px solid #2a2a28" }}>
                              <span style={{ color: "#e0b84c", fontFamily: "var(--mono)", fontSize: 10 }}>{p.type}</span>
                            </td>
                            <td style={{ padding: "5px 8px", borderBottom: "1px solid #2a2a28" }}>
                              <input
                                style={{ width: "100%", background: "var(--bg)", border: "1px solid var(--border-soft)", color: "var(--text)", borderRadius: 3, padding: "3px 7px", fontFamily: "var(--mono)", fontSize: 11, outline: "none" }}
                                placeholder={p.hint || ""}
                                value={paramValues[p.name] || ""}
                                onChange={e => setParamValues(prev => ({ ...prev, [p.name]: e.target.value }))}
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <div>
                  <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 1, color: "var(--text-dim)", marginBottom: 6 }}>Response</div>
                  <div style={{
                    background: "var(--bg-inset)",
                    border: `1px solid ${loading ? "#4a4a46" : response?.ok ? "#2a4a2a" : response ? "#4a2a2a" : "#4a4a46"}`,
                    borderRadius: 4, padding: "10px 12px",
                    fontFamily: "var(--mono)", fontSize: 11, lineHeight: 1.6,
                    whiteSpace: "pre-wrap", overflowX: "auto",
                    minHeight: 80, maxHeight: 300, overflowY: "auto",
                    color: loading ? "#e0b84c" : response?.ok ? "#7fb069" : response ? "#d9534f" : "var(--text-dim)",
                  }}>
                    {loading ? "Sending request…" : response ? (
                      <>
                        <span style={{ display: "inline-block", fontFamily: "var(--mono)", fontSize: 11, padding: "2px 8px", borderRadius: 3, marginRight: 8, background: response.ok ? "#1c3a2a" : "#3a1c1c", color: response.ok ? "#7fb069" : "#d9534f" }}>{response.status || "ERR"}</span>
                        <span style={{ color: "var(--text-dim)", fontSize: 10 }}>{response.dur}ms</span>
                        {"\n\n"}
                        {response.text}
                      </>
                    ) : "No response yet — click Run to send the request."}
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
