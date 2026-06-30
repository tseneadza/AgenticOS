/**
 * StatusIndicator Component
 *
 * Renders an HTTP status code or state label with semantic color coding.
 * All colors use theme variables for full theme compatibility.
 * - Success (2xx, ok=true): Green
 * - Error (4xx, 5xx, ok=false): Red
 * - Warning/Other (3xx, 1xx): Yellow
 *
 * Can be used as:
 * 1. Badge style (default): inline-block with background
 * 2. Text style: just colored text without background
 *
 * @param {number|string} status - HTTP status code or label (e.g., 200, "OK", "ERR")
 * @param {boolean} [ok] - Whether the status indicates success (overrides numeric interpretation)
 * @param {string} [style] - "badge" (default) or "text"
 * @param {object} [customStyle] - Additional inline styles to merge
 */

const styles = `
.status-badge-success {
  background: rgba(127, 176, 105, 0.16);
  color: var(--green);
  border: 1px solid rgba(127, 176, 105, 0.3);
}

.status-badge-warning {
  background: rgba(224, 184, 76, 0.16);
  color: var(--yellow);
  border: 1px solid rgba(224, 184, 76, 0.3);
}

.status-badge-error {
  background: rgba(217, 83, 79, 0.16);
  color: var(--red);
  border: 1px solid rgba(217, 83, 79, 0.3);
}

.status-text {
  font-family: var(--mono);
  font-size: 11px;
  user-select: none;
}

.status-badge {
  display: inline-block;
  font-family: var(--mono);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 3px;
  margin-right: 8px;
  user-select: none;
}

.status-text-success {
  color: var(--green);
}

.status-text-warning {
  color: var(--yellow);
}

.status-text-error {
  color: var(--red);
}
`;

// Maps for reference (labels only, colors now in CSS)
const STATUS_LABEL_MAP = {
  200: "OK",
  201: "Created",
  204: "No Content",
  300: "Multiple Choices",
  301: "Moved",
  302: "Found",
  304: "Not Modified",
  400: "Bad Request",
  401: "Unauthorized",
  403: "Forbidden",
  404: "Not Found",
  409: "Conflict",
  429: "Too Many Requests",
  500: "Server Error",
  502: "Bad Gateway",
  503: "Unavailable",
};

function getStatusCategory(status, ok) {
  // If ok is explicitly provided, use it
  if (typeof ok === "boolean") {
    return ok ? "success" : "error";
  }

  // Infer from status code
  if (typeof status === "number") {
    if (status >= 200 && status < 300) return "success";
    if (status >= 300 && status < 400) return "warning";
    if (status >= 400 && status < 600) return "error";
  }

  // Default to error if unable to determine
  return "error";
}

export default function StatusIndicator({
  status,
  ok,
  style = "badge",
  customStyle,
}) {
  if (status === null || status === undefined) return null;

  const category = getStatusCategory(status, ok);
  const displayText = String(status);
  const isTextStyle = style === "text";
  const className = isTextStyle
    ? `status-text status-text-${category}`
    : `status-badge status-badge-${category}`;

  return (
    <>
      <style>{styles}</style>
      <span
        className={className}
        data-testid={`status-indicator-${status}`}
        style={customStyle}
      >
        {displayText}
      </span>
    </>
  );
}
