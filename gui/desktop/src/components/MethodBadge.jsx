/**
 * MethodBadge Component
 *
 * Renders an HTTP method badge with color coding.
 * Colors are semantic:
 * - GET: Green (read/safe)
 * - POST: Orange (create)
 * - PUT: Yellow (update)
 * - DELETE: Red (destructive)
 *
 * @param {string} method - HTTP method (GET, POST, PUT, DELETE, PATCH, etc.)
 * @param {object} [style] - Additional inline styles to merge
 */

const METHOD_COLOR = {
  GET:    { background: "#1c3a2a", color: "#7fb069" },
  POST:   { background: "#3a2a1c", color: "#d97b4f" },
  DELETE: { background: "#3a1c1c", color: "#d9534f" },
  PUT:    { background: "#2a2a1c", color: "#e0b84c" },
  PATCH:  { background: "#2a1c3a", color: "#b07fd9" },
};

const defaultBadgeStyle = {
  fontFamily: "var(--mono)",
  fontSize: 10,
  fontWeight: 700,
  padding: "2px 6px",
  borderRadius: 3,
  minWidth: 44,
  textAlign: "center",
  display: "inline-block",
  userSelect: "none",
};

export default function MethodBadge({ method, style }) {
  const colors = METHOD_COLOR[method] || METHOD_COLOR.GET;
  const badgeStyle = {
    ...defaultBadgeStyle,
    ...colors,
    ...style,
  };

  return (
    <span style={badgeStyle} data-testid={`method-badge-${method}`}>
      {method}
    </span>
  );
}
