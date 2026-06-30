/**
 * FilterBar Component
 *
 * A search/filter input field for filtering endpoints by path, method, or description.
 * All colors and transitions use theme variables for full theme compatibility.
 *
 * @param {string} value - Current filter value
 * @param {function} onChange - Callback: (newValue) => void
 * @param {string} [placeholder="Filter endpoints…"] - Input placeholder text
 * @param {object} [customStyle] - Additional inline styles
 */

const styles = `
.filter-bar-container {
  padding: 7px 10px;
  border-bottom: 1px solid var(--border-soft);
  flex-shrink: 0;
}

.filter-input {
  width: 100%;
  background: var(--bg);
  border: 1px solid var(--border-soft);
  color: var(--text);
  border-radius: 4px;
  padding: 4px 9px;
  font-family: inherit;
  font-size: 12px;
  outline: none;
  transition: border-color 100ms, box-shadow 100ms cubic-bezier(0.4, 0, 0.2, 1);
}

.filter-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(217, 123, 79, 0.1);
}

.filter-input::placeholder {
  color: var(--text-dim);
  opacity: 0.6;
}
`;

export default function FilterBar({
  value,
  onChange,
  placeholder = "Filter endpoints…",
  customStyle,
}) {
  const handleChange = (e) => {
    onChange(e.target.value);
  };

  return (
    <>
      <style>{styles}</style>
      <div className="filter-bar-container" style={customStyle}>
        <input
          type="text"
          className="filter-input"
          placeholder={placeholder}
          value={value}
          onChange={handleChange}
          data-testid="filter-input"
          aria-label="Filter endpoints by path, method, or description"
        />
      </div>
    </>
  );
}
