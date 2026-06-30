/**
 * ScriptGroupHeader Component
 *
 * Renders a collapsible group header for script groups.
 * Shows group name, type indicator dot (if grouping by type), item count, and chevron.
 * All colors use theme variables for full theme compatibility.
 *
 * @param {string} name - The group name (type name or project name)
 * @param {boolean} isOpen - Whether the group is expanded
 * @param {function} onToggle - Callback: () => void
 * @param {number} itemCount - Number of items in group
 * @param {string} [groupBy] - How groups are organized ("type" | "project" | "none")
 */

const styles = `
.script-group-header {
  padding: 7px 12px 4px;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  color: var(--text-dim);
  border-bottom: 1px solid var(--border-soft);
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  user-select: none;
  transition: background-color 100ms cubic-bezier(0.4, 0, 0.2, 1);
}

.script-group-header:hover {
  background-color: rgba(127, 127, 127, 0.05);
}

.script-group-header-content {
  display: flex;
  align-items: center;
  gap: 6px;
}

.script-group-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}

.script-group-dot.launcher {
  background: var(--green);
}

.script-group-dot.test {
  background: #4fa8d9;
}

.script-group-dot.data {
  background: var(--yellow);
}

.script-group-dot.scraper {
  background: #b07fd9;
}

.script-group-dot.diagnostic {
  background: var(--accent);
}

.script-group-dot.maintenance {
  background: var(--red);
}

.script-group-dot.dev-setup {
  background: #4fd9cc;
}

.script-group-dot.unknown {
  background: var(--text-dim);
}

.script-group-count {
  opacity: 0.5;
}

.script-group-chevron {
  font-size: 9px;
  transform: rotate(0deg);
  transition: transform 150ms cubic-bezier(0.4, 0, 0.2, 1);
  display: inline-block;
}

.script-group-header[aria-expanded="true"] .script-group-chevron {
  transform: rotate(90deg);
}
`;

const TYPE_COLOR_MAP = {
  "Launcher":    "launcher",
  "Test":        "test",
  "Data":        "data",
  "Scraper":     "scraper",
  "Diagnostic":  "diagnostic",
  "Maintenance": "maintenance",
  "Dev Setup":   "dev-setup",
  "Unknown":     "unknown",
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

  const showTypeDot = groupBy === "type";
  const dotClass = showTypeDot ? TYPE_COLOR_MAP[name] || "unknown" : null;

  return (
    <>
      <style>{styles}</style>
      <div
        className="script-group-header"
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        data-testid={`script-group-header-${name}`}
        role="button"
        tabIndex={0}
        aria-expanded={isOpen}
        aria-label={`${name} group, ${itemCount} items`}
      >
        {/* Name + Item Count */}
        <span
          className="script-group-header-content"
          data-testid={`script-group-name-${name}`}
        >
          {/* Type Indicator Dot */}
          {showTypeDot && dotClass && (
            <span
              className={`script-group-dot ${dotClass}`}
              data-testid={`script-group-dot-${name}`}
            />
          )}
          {name}
          <span
            className="script-group-count"
            data-testid={`script-group-count-${name}`}
          >
            · {itemCount}
          </span>
        </span>

        {/* Chevron */}
        <span
          className="script-group-chevron"
          data-testid={`script-group-chevron-${name}`}
          aria-hidden="true"
        >
          ▶
        </span>
      </div>
    </>
  );
}
