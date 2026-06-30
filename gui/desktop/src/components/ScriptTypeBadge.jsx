/**
 * ScriptTypeBadge Component
 *
 * Renders a script type badge with semantic color coding.
 * Displays the script type (Launcher, Test, Data, etc.) with appropriate styling.
 * All colors use theme variables for full theme compatibility.
 *
 * @param {string} type - The script type (e.g., "Launcher", "Test", "Data")
 * @param {object} [customStyle] - Optional inline style overrides
 */

const styles = `
.script-type-badge {
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 3px;
  min-width: 62px;
  text-align: center;
  display: inline-block;
  white-space: nowrap;
  flex-shrink: 0;
  animation: fadeIn 300ms cubic-bezier(0.4, 0, 0.2, 1);
}

.script-type-badge.launcher {
  background: rgba(127, 176, 105, 0.16);
  color: var(--green);
  border: 1px solid rgba(127, 176, 105, 0.3);
}

.script-type-badge.test {
  background: rgba(79, 168, 217, 0.16);
  color: #4fa8d9;
  border: 1px solid rgba(79, 168, 217, 0.3);
}

.script-type-badge.data {
  background: rgba(224, 184, 76, 0.16);
  color: var(--yellow);
  border: 1px solid rgba(224, 184, 76, 0.3);
}

.script-type-badge.scraper {
  background: rgba(176, 127, 217, 0.16);
  color: #b07fd9;
  border: 1px solid rgba(176, 127, 217, 0.3);
}

.script-type-badge.diagnostic {
  background: rgba(217, 123, 79, 0.16);
  color: var(--accent);
  border: 1px solid rgba(217, 123, 79, 0.3);
}

.script-type-badge.maintenance {
  background: rgba(217, 83, 79, 0.16);
  color: var(--red);
  border: 1px solid rgba(217, 83, 79, 0.3);
}

.script-type-badge.dev-setup {
  background: rgba(79, 217, 204, 0.16);
  color: #4fd9cc;
  border: 1px solid rgba(79, 217, 204, 0.3);
}

.script-type-badge.unknown {
  background: rgba(160, 158, 149, 0.16);
  color: var(--text-dim);
  border: 1px solid rgba(160, 158, 149, 0.3);
}
`;

export default function ScriptTypeBadge({
  type,
  customStyle,
}) {
  // Map type to CSS class name
  const typeClass = type
    ? type.toLowerCase().replace(/\s+/g, "-")
    : "unknown";

  const className = `script-type-badge ${typeClass}`;

  return (
    <>
      <style>{styles}</style>
      <span
        className={className}
        style={customStyle}
        data-testid={`script-type-badge-${type}`}
        role="status"
        aria-label={`Script type: ${type}`}
      >
        {type}
      </span>
    </>
  );
}
