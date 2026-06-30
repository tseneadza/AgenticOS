/**
 * FilterBar Component
 *
 * A search/filter input field for filtering endpoints by path, method, or description.
 * Displays placeholder text and handles value changes.
 *
 * @param {string} value - Current filter value
 * @param {function} onChange - Callback: (newValue) => void
 * @param {string} [placeholder="Filter endpoints…"] - Input placeholder text
 * @param {object} [customStyle] - Additional inline styles
 */

export default function FilterBar({
  value,
  onChange,
  placeholder = "Filter endpoints…",
  customStyle,
}) {
  const handleChange = (e) => {
    onChange(e.target.value);
  };

  const containerStyle = {
    padding: "7px 10px",
    borderBottom: "1px solid var(--border-soft)",
    flexShrink: 0,
    ...customStyle,
  };

  const inputStyle = {
    width: "100%",
    background: "var(--bg)",
    border: "1px solid var(--border-soft)",
    color: "var(--text)",
    borderRadius: 4,
    padding: "4px 9px",
    fontFamily: "inherit",
    fontSize: 12,
    outline: "none",
  };

  return (
    <div style={containerStyle}>
      <input
        type="text"
        style={inputStyle}
        placeholder={placeholder}
        value={value}
        onChange={handleChange}
        data-testid="filter-input"
        aria-label="Filter endpoints by path, method, or description"
      />
    </div>
  );
}
