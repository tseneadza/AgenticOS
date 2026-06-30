/**
 * CallLogEntry Component
 *
 * Renders a single API call log entry with timestamp, method, path, status, and duration.
 * Shows success/error color indicator on the left border.
 *
 * @param {object} entry - Call log entry with shape:
 *   - ts: Date (timestamp of the call)
 *   - method: string (HTTP method)
 *   - path: string (API path)
 *   - status: number (HTTP status code)
 *   - ok: boolean (whether response was successful)
 *   - dur: number (duration in milliseconds)
 * @param {function} [onSelect] - Optional callback when entry is clicked
 */

import MethodBadge from "./MethodBadge";
import StatusIndicator from "./StatusIndicator";

export default function CallLogEntry({ entry, onSelect }) {
  if (!entry) return null;

  const handleClick = () => {
    if (onSelect) onSelect(entry);
  };

  // Determine left border color based on success/error
  const borderColor = entry.ok ? "#7fb069" : "#d9534f";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        gap: 8,
        padding: "5px 10px",
        background: "var(--bg-inset)",
        borderRadius: 4,
        borderLeft: `3px solid ${borderColor}`,
        fontSize: 12,
        cursor: onSelect ? "pointer" : "default",
      }}
      onClick={handleClick}
      data-testid="call-log-entry"
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={(e) => {
        if (onSelect && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          handleClick();
        }
      }}
    >
      {/* Timestamp */}
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-dim)",
          minWidth: 64,
        }}
        data-testid="call-timestamp"
      >
        {entry.ts.toLocaleTimeString("en-US", { hour12: false })}
      </span>

      {/* HTTP Method Badge */}
      <div data-testid="call-method">
        <MethodBadge method={entry.method} />
      </div>

      {/* API Path */}
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 11,
          flex: 1,
        }}
        data-testid="call-path"
      >
        {entry.path}
      </span>

      {/* Status Code */}
      <div data-testid="call-status">
        <StatusIndicator
          status={entry.status || "ERR"}
          ok={entry.ok}
          style="text"
          customStyle={{ marginRight: 0 }}
        />
      </div>

      {/* Duration */}
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-dim)",
        }}
        data-testid="call-duration"
      >
        {entry.dur}ms
      </span>
    </div>
  );
}
