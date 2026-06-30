/**
 * EndpointListItem Component
 *
 * Renders a single endpoint in the explorer list with method and path.
 * Shows selection state via left border and background highlight.
 * All colors use theme variables for full theme compatibility.
 *
 * @param {object} endpoint - Endpoint object with shape:
 *   - method: string (HTTP method)
 *   - path: string (API path)
 * @param {boolean} isSelected - Whether this endpoint is currently selected
 * @param {function} onSelect - Callback: () => void, called when endpoint is clicked
 */

import MethodBadge from "./MethodBadge";
import PathDisplay from "./PathDisplay";

const styles = `
.endpoint-list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  cursor: pointer;
  border-left: 3px solid transparent;
  background: transparent;
  transition: background-color 100ms, border-left-color 100ms cubic-bezier(0.4, 0, 0.2, 1);
}

.endpoint-list-item:hover {
  background-color: rgba(127, 127, 127, 0.06);
}

.endpoint-list-item.selected {
  border-left-color: var(--accent);
  background-color: var(--bg-panel);
}

.endpoint-path {
  font-family: var(--mono);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
`;

export default function EndpointListItem({
  endpoint,
  isSelected,
  onSelect,
}) {
  if (!endpoint) return null;

  const handleClick = () => {
    if (onSelect) onSelect();
  };

  const handleKeyDown = (e) => {
    if ((e.key === "Enter" || e.key === " ") && onSelect) {
      e.preventDefault();
      onSelect();
    }
  };

  return (
    <>
      <style>{styles}</style>
      <div
        className={`endpoint-list-item ${isSelected ? "selected" : ""}`}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        data-testid={`endpoint-list-item-${endpoint.method}-${endpoint.path}`}
        role="button"
        tabIndex={0}
        aria-selected={isSelected}
        aria-label={`${endpoint.method} ${endpoint.path}`}
      >
        {/* HTTP Method Badge */}
        <div data-testid={`endpoint-method-${endpoint.method}`}>
          <MethodBadge method={endpoint.method} />
        </div>

        {/* API Path with Parameter Highlighting */}
        <span
          className="endpoint-path"
          data-testid={`endpoint-path-${endpoint.path}`}
        >
          <PathDisplay path={endpoint.path} />
        </span>
      </div>
    </>
  );
}
