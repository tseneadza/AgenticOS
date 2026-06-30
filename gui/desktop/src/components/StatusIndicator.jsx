/**
 * StatusIndicator Component
 *
 * Renders an HTTP status code or state label with semantic color coding.
 * Colors are context-aware:
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

const STATUS_COLOR_MAP = {
  // Success (2xx)
  200: { bg: "#1c3a2a", text: "#7fb069", label: "OK" },
  201: { bg: "#1c3a2a", text: "#7fb069", label: "Created" },
  204: { bg: "#1c3a2a", text: "#7fb069", label: "No Content" },
  // Redirect (3xx)
  300: { bg: "#2a2a1c", text: "#e0b84c", label: "Multiple Choices" },
  301: { bg: "#2a2a1c", text: "#e0b84c", label: "Moved" },
  302: { bg: "#2a2a1c", text: "#e0b84c", label: "Found" },
  304: { bg: "#2a2a1c", text: "#e0b84c", label: "Not Modified" },
  // Client Error (4xx)
  400: { bg: "#3a1c1c", text: "#d9534f", label: "Bad Request" },
  401: { bg: "#3a1c1c", text: "#d9534f", label: "Unauthorized" },
  403: { bg: "#3a1c1c", text: "#d9534f", label: "Forbidden" },
  404: { bg: "#3a1c1c", text: "#d9534f", label: "Not Found" },
  409: { bg: "#3a1c1c", text: "#d9534f", label: "Conflict" },
  429: { bg: "#3a1c1c", text: "#d9534f", label: "Too Many Requests" },
  // Server Error (5xx)
  500: { bg: "#3a1c1c", text: "#d9534f", label: "Server Error" },
  502: { bg: "#3a1c1c", text: "#d9534f", label: "Bad Gateway" },
  503: { bg: "#3a1c1c", text: "#d9534f", label: "Unavailable" },
};

// Default colors by status category
const DEFAULT_COLORS = {
  success: { bg: "#1c3a2a", text: "#7fb069" },
  warning: { bg: "#2a2a1c", text: "#e0b84c" },
  error: { bg: "#3a1c1c", text: "#d9534f" },
};

function getStatusColors(status, ok) {
  // If ok is explicitly provided, use it
  if (typeof ok === "boolean") {
    return ok ? DEFAULT_COLORS.success : DEFAULT_COLORS.error;
  }

  // If status is in the map, use mapped colors
  if (STATUS_COLOR_MAP[status]) {
    const mapped = STATUS_COLOR_MAP[status];
    return { bg: mapped.bg, text: mapped.text };
  }

  // Infer from status code
  if (typeof status === "number") {
    if (status >= 200 && status < 300) return DEFAULT_COLORS.success;
    if (status >= 300 && status < 400) return DEFAULT_COLORS.warning;
    if (status >= 400 && status < 600) return DEFAULT_COLORS.error;
  }

  // Default to error if unable to determine
  return DEFAULT_COLORS.error;
}

export default function StatusIndicator({
  status,
  ok,
  style = "badge",
  customStyle,
}) {
  if (status === null || status === undefined) return null;

  const colors = getStatusColors(status, ok);
  const displayText = String(status);

  const badgeStyle = {
    display: "inline-block",
    fontFamily: "var(--mono)",
    fontSize: 11,
    padding: "2px 8px",
    borderRadius: 3,
    background: colors.bg,
    color: colors.text,
    marginRight: 8,
    userSelect: "none",
    ...customStyle,
  };

  const textStyle = {
    fontFamily: "var(--mono)",
    fontSize: 11,
    color: colors.text,
    userSelect: "none",
    ...customStyle,
  };

  const finalStyle = style === "text" ? textStyle : badgeStyle;

  return (
    <span
      data-testid={`status-indicator-${status}`}
      style={finalStyle}
    >
      {displayText}
    </span>
  );
}
