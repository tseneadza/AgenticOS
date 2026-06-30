/**
 * GroupHeader Component
 *
 * Renders an expandable/collapsible group header with chevron icon.
 * Used to organize endpoints into logical groups (Cards, Scripts, etc.).
 *
 * @param {string} name - Group name (e.g., "Cards", "Scripts")
 * @param {boolean} isOpen - Whether the group is expanded
 * @param {function} onToggle - Callback: () => void, called when user clicks header
 * @param {number} [itemCount=0] - Number of items in this group (optional badge)
 */

export default function GroupHeader({ name, isOpen, onToggle, itemCount = 0 }) {
  if (!name) return null;

  const chevronRotation = isOpen ? "rotate(90deg)" : "rotate(0deg)";

  return (
    <div
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
      onClick={onToggle}
      data-testid={`group-header-${name}`}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onToggle();
        }
      }}
      aria-expanded={isOpen}
      aria-label={`${name} group, ${isOpen ? "expanded" : "collapsed"}`}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span data-testid={`group-name-${name}`}>{name}</span>
        {itemCount > 0 && (
          <span
            style={{
              fontSize: 9,
              color: "var(--text-dim)",
              opacity: 0.7,
            }}
            data-testid={`group-count-${name}`}
          >
            ({itemCount})
          </span>
        )}
      </div>
      <span
        style={{
          fontSize: 9,
          display: "inline-block",
          transform: chevronRotation,
          transition: "transform .15s",
          minWidth: 12,
        }}
        data-testid={`group-chevron-${name}`}
        aria-hidden="true"
      >
        ▶
      </span>
    </div>
  );
}
