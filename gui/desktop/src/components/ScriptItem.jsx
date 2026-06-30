/**
 * ScriptItem Component
 *
 * Renders a single script in the explorer list.
 * Shows type badge, script name, and project name.
 * Displays selection state via left border and background highlight.
 * All colors use theme variables for full theme compatibility.
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

const styles = `
.script-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  cursor: pointer;
  border-left: 3px solid transparent;
  background: transparent;
  transition: background-color 100ms, border-left-color 100ms cubic-bezier(0.4, 0, 0.2, 1);
}

.script-item:hover {
  background-color: rgba(127, 127, 127, 0.06);
}

.script-item.selected {
  border-left-color: var(--accent);
  background-color: var(--bg-panel);
}

.script-info {
  overflow: hidden;
  min-width: 0;
}

.script-name {
  font-family: var(--mono);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
}

.script-project {
  font-size: 10px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
`;

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
    <>
      <style>{styles}</style>
      <div
        className={`script-item ${isSelected ? "selected" : ""}`}
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
        <div className="script-info" data-testid={`script-info-${script.id}`}>
          {/* Script Name */}
          <div className="script-name" data-testid={`script-name-${script.id}`}>
            {script.name}
          </div>

          {/* Project Name */}
          <div
            className="script-project"
            data-testid={`script-project-${script.id}`}
          >
            {script.project}
          </div>
        </div>
      </div>
    </>
  );
}
