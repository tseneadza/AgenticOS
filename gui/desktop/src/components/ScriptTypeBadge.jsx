/**
 * ScriptTypeBadge Component
 *
 * Renders a script type badge with semantic color coding.
 * Displays the script type (Launcher, Test, Data, etc.) with appropriate styling.
 *
 * @param {string} type - The script type (e.g., "Launcher", "Test", "Data")
 * @param {object} [customStyle] - Optional inline style overrides
 */

// Type classification styles
const TYPE_STYLE = {
  "Launcher":    { background: "color-mix(in srgb, var(--green) 16%, var(--bg-inset))",  color: "var(--green)" },
  "Test":        { background: "color-mix(in srgb, #4fa8d9 16%, var(--bg-inset))",       color: "#4fa8d9" },
  "Data":        { background: "color-mix(in srgb, var(--yellow) 16%, var(--bg-inset))", color: "var(--yellow)" },
  "Scraper":     { background: "color-mix(in srgb, #b07fd9 16%, var(--bg-inset))",       color: "#b07fd9" },
  "Diagnostic":  { background: "color-mix(in srgb, var(--accent) 16%, var(--bg-inset))", color: "var(--accent)" },
  "Maintenance": { background: "color-mix(in srgb, var(--red) 16%, var(--bg-inset))",    color: "var(--red)" },
  "Dev Setup":   { background: "color-mix(in srgb, #4fd9cc 16%, var(--bg-inset))",       color: "#4fd9cc" },
  "Unknown":     { background: "color-mix(in srgb, var(--text-dim) 16%, var(--bg-inset))", color: "var(--text-dim)" },
};

export default function ScriptTypeBadge({
  type,
  customStyle,
}) {
  const typeStyle = TYPE_STYLE[type] || TYPE_STYLE["Unknown"];

  const baseStyle = {
    fontFamily: "var(--mono)",
    fontSize: 10,
    fontWeight: 700,
    padding: "2px 6px",
    borderRadius: 3,
    minWidth: 62,
    textAlign: "center",
    display: "inline-block",
    whiteSpace: "nowrap",
    flexShrink: 0,
    ...typeStyle,
    ...customStyle,
  };

  return (
    <span
      style={baseStyle}
      data-testid={`script-type-badge-${type}`}
      role="status"
      aria-label={`Script type: ${type}`}
    >
      {type}
    </span>
  );
}
