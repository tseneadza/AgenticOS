/**
 * ParamInput Component
 *
 * Renders a single API parameter row with name, type, location, and input field.
 * All colors use theme variables for full theme compatibility.
 *
 * @param {object} param - Parameter object with shape:
 *   - name: string (parameter name)
 *   - type: string ("string", "number", "boolean", "json", etc.)
 *   - _in: string ("path", "query", "body", "header")
 *   - required: boolean (whether parameter is required)
 *   - hint: string (placeholder/example text)
 * @param {string} [value=""] - Current value from paramValues state
 * @param {function} onChange - Callback: (newValue) => void
 */

const styles = `
.param-row td {
  padding: 5px 8px;
  border-bottom: 1px solid var(--border-soft);
}

.param-name {
  color: var(--accent);
  font-family: var(--mono);
  font-size: 11px;
}

.param-required {
  color: var(--red);
  font-size: 10px;
  margin-left: 4px;
}

.param-location {
  color: var(--text-dim);
  font-size: 11px;
}

.param-type {
  color: var(--yellow);
  font-family: var(--mono);
  font-size: 10px;
}

.param-input-field {
  width: 100%;
  background: var(--bg);
  border: 1px solid var(--border-soft);
  color: var(--text);
  border-radius: 3px;
  padding: 3px 7px;
  font-family: var(--mono);
  font-size: 11px;
  outline: none;
  transition: border-color 100ms, box-shadow 100ms;
}

.param-input-field:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(217, 123, 79, 0.1);
}

.param-input-field::placeholder {
  color: var(--text-dim);
  opacity: 0.7;
}
`;

export default function ParamInput({ param, value = "", onChange }) {
  if (!param) return null;

  const handleChange = (e) => {
    onChange(e.target.value);
  };

  return (
    <>
      <style>{styles}</style>
      <tr className="param-row">
        {/* Parameter Name + Required Indicator */}
        <td>
          <span className="param-name" data-testid={`param-name-${param.name}`}>
            {param.name}
          </span>
          {param.required && (
            <span
              className="param-required"
              data-testid={`param-required-indicator-${param.name}`}
            >
              *
            </span>
          )}
        </td>

        {/* Parameter Location (path, query, body, etc.) */}
        <td className="param-location" data-testid={`param-in-${param.name}`}>
          {param._in}
        </td>

        {/* Parameter Type */}
        <td>
          <span className="param-type" data-testid={`param-type-${param.name}`}>
            {param.type}
          </span>
        </td>

        {/* Parameter Input Field */}
        <td>
          <input
            type="text"
            className="param-input-field"
            placeholder={param.hint || ""}
            value={value}
            onChange={handleChange}
            data-testid={`param-input-${param.name}`}
            aria-label={`${param.name} parameter input`}
          />
        </td>
      </tr>
    </>
  );
}
