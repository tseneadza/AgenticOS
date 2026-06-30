/**
 * TabSwitcher Component
 *
 * Renders a tab switcher with active state styling.
 * All colors use theme variables for full theme compatibility.
 *
 * @param {string} activeTab - The currently active tab ("explorer" or "calllog")
 * @param {function} onTabChange - Callback: (tabName) => void
 * @param {number} [callLogCount=0] - Number of call log entries (shown in badge)
 * @param {array} [tabs] - Array of tab objects: { id, label }
 */

const styles = `
.tab-switcher {
  display: flex;
  margin-left: 12px;
}

.tab-button {
  padding: 3px 12px;
  font-size: 11px;
  cursor: pointer;
  border: 1px solid var(--border-soft);
  background: transparent;
  color: var(--text-dim);
  font-weight: 400;
  transition: background-color 150ms, color 150ms, font-weight 150ms cubic-bezier(0.4, 0, 0.2, 1);
}

.tab-button:first-child {
  border-right: none;
  border-radius: 4px 0 0 4px;
}

.tab-button:last-child {
  border-radius: 0 4px 4px 0;
}

.tab-button.active {
  background: var(--accent);
  color: var(--bg);
  font-weight: 700;
}

.tab-button:not(.active):hover {
  background: rgba(127, 127, 127, 0.06);
}
`;

export default function TabSwitcher({
  activeTab,
  onTabChange,
  callLogCount = 0,
  tabs,
}) {
  // Default tabs
  const defaultTabs = [
    { id: "explorer", label: "Explorer" },
    { id: "calllog", label: `Call Log${callLogCount ? ` (${callLogCount})` : ""}` },
  ];

  const tabList = tabs || defaultTabs;

  return (
    <>
      <style>{styles}</style>
      <div className="tab-switcher" data-testid="tab-switcher" role="tablist">
        {tabList.map((t) => (
          <button
            key={t.id}
            onClick={() => onTabChange(t.id)}
            className={`tab-button ${activeTab === t.id ? "active" : ""}`}
            data-testid={`tab-button-${t.id}`}
            role="tab"
            aria-selected={activeTab === t.id}
            aria-label={t.label}
          >
            {t.label}
          </button>
        ))}
      </div>
    </>
  );
}
