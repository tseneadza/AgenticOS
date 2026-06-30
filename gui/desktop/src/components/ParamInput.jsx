/**
 * ParamInput Component
 *
 * Renders a single API parameter row with name, type, location, and input field.
 * Handles text input for all parameter types (string, number, json, etc.).
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

export default function ParamInput({ param, value = "", onChange }) {
  if (!param) return null;

  const handleChange = (e) => {
    onChange(e.target.value);
  };

  return (
    <tr>
      {/* Parameter Name + Required Indicator */}
      <td style={{ padding: "5px 8px", borderBottom: "1px solid #2a2a28" }}>
        <span
          style={{
            color: "var(--accent)",
            fontFamily: "var(--mono)",
            fontSize: 11,
          }}
          data-testid={`param-name-${param.name}`}
        >
          {param.name}
        </span>
        {param.required && (
          <span
            style={{ color: "#d9534f", fontSize: 10, marginLeft: 4 }}
            data-testid={`param-required-indicator-${param.name}`}
          >
            *
          </span>
        )}
      </td>

      {/* Parameter Location (path, query, body, etc.) */}
      <td
        style={{
          padding: "5px 8px",
          borderBottom: "1px solid #2a2a28",
          color: "var(--text-dim)",
          fontSize: 11,
        }}
        data-testid={`param-in-${param.name}`}
      >
        {param._in}
      </td>

      {/* Parameter Type */}
      <td style={{ padding: "5px 8px", borderBottom: "1px solid #2a2a28" }}>
        <span
          style={{
            color: "#e0b84c",
            fontFamily: "var(--mono)",
            fontSize: 10,
          }}
          data-testid={`param-type-${param.name}`}
        >
          {param.type}
        </span>
      </td>

      {/* Parameter Input Field */}
      <td style={{ padding: "5px 8px", borderBottom: "1px solid #2a2a28" }}>
        <input
          type="text"
          style={{
            width: "100%",
            background: "var(--bg)",
            border: "1px solid var(--border-soft)",
            color: "var(--text)",
            borderRadius: 3,
            padding: "3px 7px",
            fontFamily: "var(--mono)",
            fontSize: 11,
            outline: "none",
          }}
          placeholder={param.hint || ""}
          value={value}
          onChange={handleChange}
          data-testid={`param-input-${param.name}`}
          aria-label={`${param.name} parameter input`}
        />
      </td>
    </tr>
  );
}
