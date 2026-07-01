import { useState, useEffect, useRef, useCallback } from "react";

// ─────────────────────────────────────────────────────────────────────────
// LogsExplorer Component
// Displays, filters, searches, and exports logs with real-time tail
// ─────────────────────────────────────────────────────────────────────────

const LEVELS = ["DEBUG", "INFO", "WARN", "ERROR"];

const LEVEL_COLORS = {
  ERROR: { color: "var(--red)" },
  WARN: { color: "var(--yellow)" },
  INFO: { color: "var(--text-dim)" },
  DEBUG: { color: "#888888" },
};

// Parse log line: [timestamp] [level] message
function parseLogLine(line) {
  const match = line.match(/^\[([^\]]+)\]\s*\[([^\]]+)\]\s*(.*)$/);
  if (!match) return null;
  return {
    timestamp: match[1],
    level: match[2],
    message: match[3],
  };
}

// Highlight search terms in text
function highlightText(text, searchTerm) {
  if (!searchTerm) return text;
  const regex = new RegExp(`(${searchTerm.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
  return text.split(regex).map((part, idx) =>
    regex.test(part) ? `${part}` : part
  ).join("");
}

// ─────────────────────────────────────────────────────────────────────────
// LogEntry Sub-component
// ─────────────────────────────────────────────────────────────────────────

function LogEntry({ log, searchTerm, onCopy }) {
  if (!log) return null;

  const highlightedMessage = highlightText(log.message, searchTerm);
  const parts = highlightedMessage.split(/|/);

  const handleCopy = async () => {
    const logText = `[${log.timestamp}] [${log.level}] ${log.message}`;
    try {
      await navigator.clipboard.writeText(logText);
      onCopy?.();
    } catch (e) {
      console.error("Failed to copy:", e);
    }
  };

  return (
    <div
      data-testid={`log-entry-${log.level}`}
      style={{
        padding: "6px 8px",
        borderBottom: "1px solid var(--border-soft)",
        fontSize: "12px",
        fontFamily: "var(--mono)",
        display: "flex",
        gap: "8px",
        cursor: "pointer",
        transition: "background-color 100ms",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--bg-inset)")}
      onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
      onClick={handleCopy}
      title="Click to copy"
    >
      <div style={{ flex: "0 0 120px", color: "var(--text-dim)" }}>
        [{log.timestamp}]
      </div>
      <div style={{ flex: "0 0 60px", ...LEVEL_COLORS[log.level] || {} }}>
        [{log.level}]
      </div>
      <div style={{ flex: 1, color: "var(--text)", wordBreak: "break-word" }}>
        {parts.map((part, idx) => (
          idx % 2 === 1 ? (
            <span key={idx} style={{ backgroundColor: "var(--yellow)", color: "var(--bg)" }}>
              {part}
            </span>
          ) : (
            part
          )
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// LogFilter Sub-component
// ─────────────────────────────────────────────────────────────────────────

function LogFilter({ activeFilters, onChange }) {
  const handleToggle = (level) => {
    const updated = activeFilters.includes(level)
      ? activeFilters.filter((l) => l !== level)
      : [...activeFilters, level];
    onChange(updated);
  };

  return (
    <div data-testid="log-filter" style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
      {LEVELS.map((level) => (
        <button
          key={level}
          data-testid={`filter-btn-${level}`}
          onClick={() => handleToggle(level)}
          aria-pressed={activeFilters.includes(level)}
          style={{
            padding: "4px 10px",
            border: activeFilters.includes(level) ? "2px solid var(--accent)" : "1px solid var(--border)",
            borderRadius: "4px",
            background: activeFilters.includes(level) ? "var(--bg-panel)" : "transparent",
            color: LEVEL_COLORS[level]?.color || "var(--text)",
            cursor: "pointer",
            fontSize: "12px",
            fontWeight: "500",
            transition: "all 100ms",
          }}
        >
          {level}
        </button>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// LogSearch Sub-component
// ─────────────────────────────────────────────────────────────────────────

function LogSearch({ searchTerm, onChange }) {
  return (
    <div style={{ marginBottom: "12px" }}>
      <input
        data-testid="log-search-input"
        type="text"
        placeholder="Search logs..."
        value={searchTerm}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: "100%",
          padding: "6px 8px",
          border: "1px solid var(--border)",
          borderRadius: "4px",
          background: "var(--bg-inset)",
          color: "var(--text)",
          fontSize: "12px",
          fontFamily: "var(--mono)",
        }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Main LogsExplorer Component
// ─────────────────────────────────────────────────────────────────────────

export default function LogsExplorer({ logs = [], onLogsUpdate }) {
  // ── localStorage helpers ────────────────────────────────────────────────────
  const loadFromLS = (key, defaultVal) => {
    try {
      const stored = localStorage.getItem(`logs-explorer-${key}`);
      return stored ? JSON.parse(stored) : defaultVal;
    } catch { return defaultVal; }
  };
  const saveToLS = (key, val) => {
    try { localStorage.setItem(`logs-explorer-${key}`, JSON.stringify(val)); } catch {}
  };

  const [filteredLogs, setFilteredLogs] = useState([]);
  const [activeFilters, setActiveFilters] = useState(() => loadFromLS("activeFilters", LEVELS));
  const [searchTerm, setSearchTerm] = useState(() => loadFromLS("searchTerm", ""));
  const [autoScroll, setAutoScroll] = useState(() => loadFromLS("autoScroll", true));
  const [copied, setCopied] = useState(false);
  const logsEndRef = useRef(null);
  const containerRef = useRef(null);

  // Filter and search logs
  useEffect(() => {
    let result = logs;

    // Apply level filter (OR logic)
    if (activeFilters.length > 0) {
      result = result.filter((log) => activeFilters.includes(log.level));
    }

    // Apply search filter (AND logic, case-insensitive)
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      result = result.filter(
        (log) =>
          log.message.toLowerCase().includes(term) ||
          log.level.toLowerCase().includes(term) ||
          log.timestamp.toLowerCase().includes(term)
      );
    }

    setFilteredLogs(result);
  }, [logs, activeFilters, searchTerm]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (autoScroll && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [filteredLogs, autoScroll]);

  // ── Persist filter state to localStorage ─────────────────────────────────
  useEffect(() => { saveToLS("activeFilters", activeFilters); }, [activeFilters]);
  useEffect(() => { saveToLS("searchTerm", searchTerm); }, [searchTerm]);
  useEffect(() => { saveToLS("autoScroll", autoScroll); }, [autoScroll]);

  const handleCopy = useCallback(() => {
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, []);

  // Export as text
  const exportAsText = () => {
    const text = filteredLogs
      .map((log) => `[${log.timestamp}] [${log.level}] ${log.message}`)
      .join("\n");
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "logs.txt";
    a.click();
    URL.revokeObjectURL(url);
  };

  // Export as JSON
  const exportAsJson = () => {
    const json = JSON.stringify(filteredLogs, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "logs.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div data-testid="logs-explorer" style={{ display: "flex", flexDirection: "column", height: "100%", gap: "8px" }}>
      {/* Header Controls */}
      <div style={{ padding: "8px 0" }}>
        <LogSearch searchTerm={searchTerm} onChange={setSearchTerm} />
        <LogFilter activeFilters={activeFilters} onChange={setActiveFilters} />

        {/* Control Buttons */}
        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
          <button
            data-testid="toggle-autoscroll"
            onClick={() => setAutoScroll(!autoScroll)}
            style={{
              padding: "4px 8px",
              border: autoScroll ? "2px solid var(--green)" : "1px solid var(--border)",
              borderRadius: "4px",
              background: autoScroll ? "var(--bg-panel)" : "transparent",
              color: autoScroll ? "var(--green)" : "var(--text-dim)",
              cursor: "pointer",
              fontSize: "11px",
              transition: "all 100ms",
            }}
          >
            {autoScroll ? "▼ Auto-scroll ON" : "⊡ Auto-scroll OFF"}
          </button>
          <button
            data-testid="export-txt"
            onClick={exportAsText}
            style={{
              padding: "4px 8px",
              border: "1px solid var(--border)",
              borderRadius: "4px",
              background: "transparent",
              color: "var(--text-dim)",
              cursor: "pointer",
              fontSize: "11px",
              transition: "all 100ms",
            }}
          >
            Export .txt
          </button>
          <button
            data-testid="export-json"
            onClick={exportAsJson}
            style={{
              padding: "4px 8px",
              border: "1px solid var(--border)",
              borderRadius: "4px",
              background: "transparent",
              color: "var(--text-dim)",
              cursor: "pointer",
              fontSize: "11px",
              transition: "all 100ms",
            }}
          >
            Export .json
          </button>
          {copied && (
            <div style={{ color: "var(--green)", fontSize: "11px" }}>
              Copied!
            </div>
          )}
        </div>

        {/* Log Count */}
        <div style={{ marginTop: "8px", fontSize: "11px", color: "var(--text-dim)" }}>
          Showing {filteredLogs.length} of {logs.length} logs
        </div>
      </div>

      {/* Log Display */}
      <div
        ref={containerRef}
        data-testid="logs-container"
        style={{
          flex: 1,
          overflow: "auto",
          border: "1px solid var(--border)",
          borderRadius: "4px",
          backgroundColor: "var(--bg-inset)",
        }}
      >
        {filteredLogs.length === 0 ? (
          <div
            data-testid="empty-logs"
            style={{
              padding: "32px",
              textAlign: "center",
              color: "var(--text-dim)",
              fontSize: "12px",
            }}
          >
            {logs.length === 0 ? "No logs available" : "No logs match your filter"}
          </div>
        ) : (
          <>
            {filteredLogs.map((log, idx) => (
              <LogEntry key={idx} log={log} searchTerm={searchTerm} onCopy={handleCopy} />
            ))}
            <div ref={logsEndRef} />
          </>
        )}
      </div>
    </div>
  );
}
