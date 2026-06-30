/**
 * TabSwitcher Component
 *
 * Renders a tab switcher with active state styling.
 * Used to switch between "Explorer" and "Call Log" views.
 *
 * @param {string} activeTab - The currently active tab ("explorer" or "calllog")
 * @param {function} onTabChange - Callback: (tabName) => void
 * @param {number} [callLogCount=0] - Number of call log entries (shown in badge)
 * @param {array} [tabs] - Array of tab objects: { id, label }
 */

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
    <div
      style={{
        display: "flex",
        marginLeft: 12,
      }}
      data-testid="tab-switcher"
      role="tablist"
    >
      {tabList.map((t, i) => (
        <button
          key={t.id}
          onClick={() => onTabChange(t.id)}
          style={{
            padding: "3px 12px",
            fontSize: 11,
            cursor: "pointer",
            border: "1px solid var(--border-soft)",
            borderRight: i === 0 ? "none" : "1px solid var(--border-soft)",
            borderRadius: i === 0 ? "4px 0 0 4px" : "0 4px 4px 0",
            background: activeTab === t.id ? "var(--accent)" : "none",
            color: activeTab === t.id ? "#1b1b19" : "var(--text-dim)",
            fontWeight: activeTab === t.id ? 700 : 400,
          }}
          data-testid={`tab-button-${t.id}`}
          role="tab"
          aria-selected={activeTab === t.id}
          aria-label={t.label}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
