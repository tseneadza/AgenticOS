/**
 * MethodBadge Component
 *
 * Renders an HTTP method badge with color coding.
 * Colors are semantic and theme-aware:
 * - GET: Green (read/safe)
 * - POST: Accent/Orange (create)
 * - PUT: Yellow (update)
 * - DELETE: Red (destructive)
 *
 * @param {string} method - HTTP method (GET, POST, PUT, DELETE, PATCH, etc.)
 * @param {object} [style] - Additional inline styles to merge
 */

const styles = `
.method-badge {
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 3px;
  min-width: 44px;
  text-align: center;
  display: inline-block;
  user-select: none;
  animation: fadeIn 300ms cubic-bezier(0.4, 0, 0.2, 1);
}

.method-badge.get {
  background: rgba(127, 176, 105, 0.16);
  color: var(--green);
  border: 1px solid rgba(127, 176, 105, 0.3);
}

.method-badge.post {
  background: rgba(217, 123, 79, 0.16);
  color: var(--accent);
  border: 1px solid rgba(217, 123, 79, 0.3);
}

.method-badge.delete {
  background: rgba(217, 83, 79, 0.16);
  color: var(--red);
  border: 1px solid rgba(217, 83, 79, 0.3);
}

.method-badge.put {
  background: rgba(224, 184, 76, 0.16);
  color: var(--yellow);
  border: 1px solid rgba(224, 184, 76, 0.3);
}

.method-badge.patch {
  background: rgba(176, 127, 217, 0.16);
  color: var(--accent2);
  border: 1px solid rgba(176, 127, 217, 0.3);
}
`;

export default function MethodBadge({ method, style }) {
  const methodClass = method?.toLowerCase() || "get";
  const className = `method-badge ${methodClass}`;

  return (
    <>
      <style>{styles}</style>
      <span className={className} style={style} data-testid={`method-badge-${method}`}>
        {method}
      </span>
    </>
  );
}
