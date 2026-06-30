/**
 * GroupHeader Component
 *
 * Renders an expandable/collapsible group header with chevron icon.
 * Used to organize endpoints into logical groups (Cards, Scripts, etc.).
 * All colors and animations use theme variables for consistency.
 *
 * @param {string} name - Group name (e.g., "Cards", "Scripts")
 * @param {boolean} isOpen - Whether the group is expanded
 * @param {function} onToggle - Callback: () => void, called when user clicks header
 * @param {number} [itemCount=0] - Number of items in this group (optional badge)
 */

const styles = `
.group-header {
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

.group-header:hover {
  background-color: rgba(127, 127, 127, 0.05);
}

.group-header:focus {
  outline: 2px solid var(--accent);
  outline-offset: -1px;
}

.group-header-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.group-count {
  font-size: 9px;
  color: var(--text-dim);
  opacity: 0.7;
}

.group-chevron {
  font-size: 9px;
  display: inline-block;
  transform: rotate(0deg);
  transition: transform 150ms cubic-bezier(0.4, 0, 0.2, 1);
  min-width: 12px;
}

.group-header[aria-expanded="true"] .group-chevron {
  transform: rotate(90deg);
}
`;

export default function GroupHeader({ name, isOpen, onToggle, itemCount = 0 }) {
  if (!name) return null;

  return (
    <>
      <style>{styles}</style>
      <div
        className="group-header"
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
        <div className="group-header-content">
          <span data-testid={`group-name-${name}`}>{name}</span>
          {itemCount > 0 && (
            <span className="group-count" data-testid={`group-count-${name}`}>
              ({itemCount})
            </span>
          )}
        </div>
        <span
          className="group-chevron"
          data-testid={`group-chevron-${name}`}
          aria-hidden="true"
        >
          ▶
        </span>
      </div>
    </>
  );
}
