/**
 * ScriptItem Component
 *
 * Renders a single script in the explorer list.
 * Shows type badge, script name, and project name.
 * Displays selection state via left border and background highlight.
 *
 * @param {object} script - Script object with shape:
 *   - id: string (unique identifier)
 *   - type: string (e.g., "Launcher", "Test")
 *   - name: string (script name)
 *   - project: string (project name)
 * @param {boolean} isSelected - Whether this script is currently selected
 * @param {function} onSelect - Callback: () => void, called when script is clicked
 */

import ScriptTypeBadge from "./ScriptTypeBadge";

export default function ScriptItem({
  script,
  isSelected,
  onSelect,
}) {
  if (!script) return null;

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
        background: isSelected ? "var(--bg-panel)" : "transparent",
      }}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      data-testid={`script-item-${script.id}`}
      role="button"
      tabIndex={0}
      aria-selected={isSelected}
      aria-label={`${script.name}, ${script.project}`}
    >
      {/* Type Badge */}
      <div data-testid={`script-type-${script.id}`}>
        <ScriptTypeBadge type={script.type} />
      </div>

      {/* Script Info: Name + Project */}
      <div
        style={{
          overflow: "hidden",
          minWidth: 0,
        }}
        data-testid={`script-info-${script.id}`}
      >
        {/* Script Name */}
        <div
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          data-testid={`script-name-${script.id}`}
        >
          {script.name}
        </div>

        {/* Project Name */}
        <div
          style={{
            fontSize: 10,
            color: "var(--text-dim)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          data-testid={`script-project-${script.id}`}
        >
          {script.project}
        </div>
      </div>
    </div>
  );
}
