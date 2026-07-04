/**
 * Utility functions shared across explorers
 * Extracted from ScriptsExplorer and HubApiExplorer components
 */
import { sidecarUrl } from "../settings";

// ─────────────────────────────────────────────────────────────────────────────
// Script utilities (from ScriptsExplorer.jsx)
// ─────────────────────────────────────────────────────────────────────────────

export const TYPE_STYLE = {
  "Launcher":    { bg:"color-mix(in srgb, var(--green) 16%, var(--bg-inset))",  color:"var(--green)" },
  "Test":        { bg:"color-mix(in srgb, #4fa8d9 16%, var(--bg-inset))",       color:"#4fa8d9" },
  "Data":        { bg:"color-mix(in srgb, var(--yellow) 16%, var(--bg-inset))", color:"var(--yellow)" },
  "Scraper":     { bg:"color-mix(in srgb, #b07fd9 16%, var(--bg-inset))",       color:"#b07fd9" },
  "Diagnostic":  { bg:"color-mix(in srgb, var(--accent) 16%, var(--bg-inset))", color:"var(--accent)" },
  "Maintenance": { bg:"color-mix(in srgb, var(--red) 16%, var(--bg-inset))",    color:"var(--red)" },
  "Dev Setup":   { bg:"color-mix(in srgb, #4fd9cc 16%, var(--bg-inset))",       color:"#4fd9cc" },
  "Unknown":     { bg:"color-mix(in srgb, var(--text-dim) 16%, var(--bg-inset))", color:"var(--text-dim)" },
};

/**
 * Classify a script by its name and description
 * @param {object} script - Script object with name and description
 * @returns {string} Type classification
 */
export function classifyScript(script) {
  const n = (script.name || "").toLowerCase();
  // Check diagnostic first (before test, to avoid "inspect" matching "spec")
  if (n.includes("diagnose") || n.includes("discover") || n.includes("inspect") || n.includes("debug") || n.includes("probe") || n.includes("setup_database")) return "Diagnostic";
  // Then check other types
  if (n.includes("start") || n.includes("launch") || n.includes("serve")) return "Launcher";
  if (n.includes("test") || n.includes("smoke") || n.includes("spec")) return "Test";
  if (n.includes("seed") || n.includes("import") || n.includes("populate") || n.includes("backfill") || n.includes("migrate") || n.includes("setup_db") || n.includes("load_") || n.includes("collect_") || n.includes("update_all")) return "Data";
  if (n.includes("scrape") || n.includes("fetch") || n.includes("crawl") || n.includes("download") || n.includes("update_fighter") || n.includes("update_full")) return "Scraper";
  if (n.includes("clear") || n.includes("clean") || n.includes("sync") || n.includes("update-port") || n.includes("show_cron") || n.includes("repo-sync")) return "Maintenance";
  if (n.includes("setup") || n.includes("init") || n.includes("install") || n.includes("symlink") || n.includes("branch") || n.includes("build")) return "Dev Setup";
  const d = (script.description || "").toLowerCase();
  if (d.includes("start") || d.includes("boot") || d.includes("launch")) return "Launcher";
  if (d.includes("test") || d.includes("verify")) return "Test";
  if (d.includes("seed") || d.includes("import") || d.includes("populate")) return "Data";
  return "Unknown";
}

/**
 * Parse script content and extract structured information
 * @param {string} content - Raw script content
 * @param {object} sc - Script config with name, path, description
 * @returns {object|null} Parsed script info or null
 */
export function parseScriptContent(content, sc) {
  if (!content) return null;
  const lines = content.split("\n");
  const ext = (sc.path || "").split(".").pop().toLowerCase();
  const isPy  = ext === "py";
  const isSh  = ext === "sh" || ext === "bash" || !ext.match(/^[a-z]+$/);

  // Extract the top comment block
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
        if ((l.match(/"""/g)||[]).length >= 2 || (l.match(/'''/g)||[]).length >= 2) inTripleQuote = false;
        continue;
      }
      if (inTripleQuote) {
        if (l.endsWith('"""') || l.endsWith("'''")) {
          const inner = l.replace(/"""|'''$/, "").trim();
          if (inner) headerLines.push(inner);
          inTripleQuote = false;
        } else {
          headerLines.push(raw);
        }
        continue;
      }
    }

    if (l.startsWith("#")) {
      headerLines.push(raw.replace(/^#+\s?/, ""));
      continue;
    }
    if (l === "") {
      if (headerLines.length > 0) headerLines.push("");
      continue;
    }
    hitCode = true;
  }

  const fullHeader = headerLines.join("\n").trim();
  if (!fullHeader) return null;

  // Purpose: first meaningful sentence
  const meaningfulLines = headerLines.filter(l => l.trim() && !l.match(/^[-=*─]+$/));
  const purpose = meaningfulLines[0]?.trim() || sc.description || "";

  // Usage patterns
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
    if (/^\s{2,}(bash|python|\.\/|python3|\.venv|\$\s|cd\s|npm\s|go\s|node\s|\w[\w.-]+\s+(start|stop|install|run|build|test|status|restart))/.test(l)) {
      usageLines.push(t);
    }
    const scriptBase = (sc.name || "").replace(/\.(sh|py|ts|js)$/, "");
    if (scriptBase && new RegExp(`${scriptBase}\\s+\\w`).test(t)) {
      if (!usageLines.includes(t)) usageLines.push(t);
    }
  }

  // Parameters / flags
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
    if (/^\s*(--|-)[\w-]/.test(l) || /^\s*[A-Z_]{2,}=/.test(l)) {
      paramLines.push(t);
    }
  }

  // Environment variables
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

  // Dependencies / tools required
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

  // Notes / warnings
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

/**
 * Filter scripts by search term
 * @param {array} scripts - Array of scripts
 * @param {string} filter - Search filter string
 * @returns {array} Filtered scripts
 */
export function filterScripts(scripts, filter) {
  if (!filter) return scripts;
  const lower = filter.toLowerCase();
  return scripts.filter(s =>
    s.name.toLowerCase().includes(lower) ||
    s.project.toLowerCase().includes(lower) ||
    (s.description || "").toLowerCase().includes(lower) ||
    s.type.toLowerCase().includes(lower)
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// API endpoint utilities (from HubApiExplorer.jsx)
// ─────────────────────────────────────────────────────────────────────────────

export const METHOD_COLOR = {
  GET:    { bg:"#1c3a2a", color:"#7fb069" },
  POST:   { bg:"#3a2a1c", color:"#d97b4f" },
  DELETE: { bg:"#3a1c1c", color:"#d9534f" },
  PUT:    { bg:"#2a2a1c", color:"#e0b84c" },
};

/**
 * Build a full URL from an endpoint and parameter values
 * @param {object} ep - Endpoint object
 * @param {object} paramValues - Parameter value map
 * @param {string} baseUrl - Optional base URL override
 * @returns {string} Full URL
 */
export function buildUrl(ep, paramValues, baseUrl = null) {
  const SIDECAR = sidecarUrl();               // user-configurable (settings.js)
  const HUB = "http://localhost:8085/api";    // decommissioned hub — left for a later phase

  let path = ep.path;
  ep.params?.filter(p => p._in === "path").forEach(p => {
    path = path.replace(`{${p.name}}`, paramValues[p.name] || `{${p.name}}`);
  });
  const qp = ep.params?.filter(p => p._in === "query" && paramValues[p.name]) || [];
  const qs = qp.map(p => `${p.name}=${encodeURIComponent(paramValues[p.name])}`).join("&");
  const base = baseUrl || (ep.server === "sidecar" ? SIDECAR
             : ep.rootPath ? "http://localhost:8085" : HUB);
  return base + path + (qs ? "?" + qs : "");
}

/**
 * Filter endpoints by group and search term
 * @param {array} endpoints - Array of endpoints
 * @param {string} group - Group name to filter by
 * @param {string} filter - Search filter string
 * @returns {array} Filtered endpoints with indices
 */
export function filterEndpoints(endpoints, group, filter) {
  return endpoints
    .map((e, i) => ({ ...e, _i: i }))
    .filter(e =>
      e.group === group &&
      (!filter ||
        e.path.toLowerCase().includes(filter.toLowerCase()) ||
        e.method.toLowerCase().includes(filter.toLowerCase()) ||
        e.desc.toLowerCase().includes(filter.toLowerCase()))
    );
}

/**
 * Convert OpenAPI spec to explorer endpoint format
 * @param {object} spec - OpenAPI specification
 * @returns {array} Array of endpoints
 */
export function convertOpenAPIToEndpoints(spec) {
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

// ─────────────────────────────────────────────────────────────────────────────
// Generic utilities
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Generic sort function for arrays
 * @param {array} items - Array to sort
 * @param {string} field - Field name to sort by
 * @param {string} direction - 'asc' or 'desc'
 * @returns {array} Sorted array
 */
export function sortByField(items, field, direction = "asc") {
  return [...items].sort((a, b) => {
    const av = (a[field] || "").toString().toLowerCase();
    const bv = (b[field] || "").toString().toLowerCase();
    const cmp = av.localeCompare(bv);
    return direction === "asc" ? cmp : -cmp;
  });
}
