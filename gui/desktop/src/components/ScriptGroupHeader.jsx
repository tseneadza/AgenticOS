/**
 * ScriptGroupHeader Component
 *
 * Renders a collapsible group header for script groups.
 * Shows group name, type indicator dot (if grouping by type), item count, and chevron.
 *
 * @param {string} name - The group name (type name or project name)
 * @param {boolean} isOpen - Whether the group is expanded
 * @param {function} onToggle - Callback: () => void
 * @param {number} itemCount - Number of items in group
 * @param {string} [groupBy] - How groups are organized ("type" | "project" | "none")
 */

const TYPE_COLORS = {
  "Launcher":    "var(--green)",
  "Test":        "#4fa8d9",
  "Data":        "var(--yellow)",
  "Scraper":     "#b07fd9",
  "Diagnostic":  "var(--accent)",
  "Maintenance": "var(--red)",
  "Dev Setup":   "#4fd9cc",
  "Unknown":     "var(--text-dim)",
};

export default function ScriptGroupHeader({
  name,
  isOpen,
  onToggle,
  itemCount,
  groupBy,
}) {
  const handleClick = () => {
    if (onToggle) onToggle();
  };

  const handleKeyDown = (e) => {
    if ((e.key === "Enter" || e.key === " ") && onToggle) {
      e.preventDefault();
      onToggle();
    }
  };

  const typeColor = groupBy === "type" ? TYPE_COLORS[name] : null;

  return (
    <div
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      style={{
        padding: "7px 12px 4px",
        fontSize: 10,
        textTransform: "uppercase",
        letterSpacing: 1.2,
        color: "var(--text-dim)",
        borderBottom: "1px solid var(--border-soft)",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        cursor: "pointer",
        userSelect: "none",
      }}
      data-testid={`script-group-header-${name}`}
      role="button"
      tabIndex={0}
      aria-expanded={isOpen}
      aria-label={`${name} group, ${itemCount} items`}
    >
      {/* Name + Item Count */}
      <span
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
        data-testid={`script-group-name-${name}`}
      >
        {/* Type Indicator Dot */}
        {typeColor && (
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: typeColor,
              display: "inline-block",
            }}
            data-testid={`script-group-dot-${name}`}
          />
        )}
        {name}
        <span style={{ opacity: 0.5 }} data-testid={`script-group-count-${name}`}>
          · {itemCount}
        </span>
      </span>

      {/* Chevron */}
      <span
        style={{
          fontSize: 9,
          transform: isOpen ? "rotate(90deg)" : "rotate(0deg)",
          transition: "transform .15s",
          display: "inline-block",
        }}
        data-testid={`script-group-chevron-${name}`}
      >
        ▶
      </span>
    </div>
  );
}
