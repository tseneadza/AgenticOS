/**
 * CallLogEntry Component
 *
 * Renders a single API call log entry with timestamp, method, path, status, and duration.
 * Shows success/error color indicator on the left border.
 * All colors use theme variables for full theme compatibility.
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

const styles = `
.call-log-entry {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 5px 10px;
  background: var(--bg-inset);
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: background-color 100ms;
}

.call-log-entry:hover:not(.call-log-entry-disabled) {
  background-color: rgba(127, 127, 127, 0.08);
}

.call-log-entry-disabled {
  cursor: default;
}

.call-log-entry.success {
  border-left: 3px solid var(--green);
}

.call-log-entry.error {
  border-left: 3px solid var(--red);
}

.call-timestamp {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-dim);
  min-width: 64px;
}

.call-path {
  font-family: var(--mono);
  font-size: 11px;
  flex: 1;
  color: var(--text);
}

.call-duration {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-dim);
}
`;

export default function CallLogEntry({ entry, onSelect }) {
  if (!entry) return null;

  const handleClick = () => {
    if (onSelect) onSelect(entry);
  };

  const entryClass = `call-log-entry ${entry.ok ? "success" : "error"}`;

  return (
    <>
      <style>{styles}</style>
      <div
        className={entryClass}
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
        <span className="call-timestamp" data-testid="call-timestamp">
          {entry.ts.toLocaleTimeString("en-US", { hour12: false })}
        </span>

        {/* HTTP Method Badge */}
        <div data-testid="call-method">
          <MethodBadge method={entry.method} />
        </div>

        {/* API Path */}
        <span className="call-path" data-testid="call-path">
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
        <span className="call-duration" data-testid="call-duration">
          {entry.dur}ms
        </span>
      </div>
    </>
  );
}
