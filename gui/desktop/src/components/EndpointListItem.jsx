/**
 * EndpointListItem Component
 *
 * Renders a single endpoint in the explorer list with method and path.
 * Shows selection state via left border and background highlight.
 *
 * @param {object} endpoint - Endpoint object with shape:
 *   - method: string (HTTP method)
 *   - path: string (API path)
 * @param {boolean} isSelected - Whether this endpoint is currently selected
 * @param {function} onSelect - Callback: () => void, called when endpoint is clicked
 */

import MethodBadge from "./MethodBadge";
import PathDisplay from "./PathDisplay";

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
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 12px",
        cursor: "pointer",
        borderLeft: isSelected
          ? "3px solid var(--accent)"
          : "3px solid transparent",
        background: isSelected ? "#272724" : "transparent",
      }}
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
        style={{
          fontFamily: "var(--mono)",
          fontSize: 11,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        data-testid={`endpoint-path-${endpoint.path}`}
      >
        <PathDisplay path={endpoint.path} />
      </span>
    </div>
  );
}
