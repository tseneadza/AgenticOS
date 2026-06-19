import { useState, useEffect } from 'react';

/**
 * useDiagnosticsPanel hook
 *
 * Manages Diagnostics panel expanded/collapsed state.
 * State persists to localStorage["agentic-os.diagExpanded"]
 *
 * Usage:
 *   const { expanded, toggle } = useDiagnosticsPanel();
 *   return (
 *     <>
 *       <button onClick={toggle}>{expanded ? '⊟' : '⊞'}</button>
 *       {expanded && <FullDetails />}
 *     </>
 *   );
 */
export function useDiagnosticsPanel() {
  const [expanded, setExpanded] = useState(false);

  // Load from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem('agentic-os.diagExpanded');
      if (stored !== null) {
        setExpanded(JSON.parse(stored));
      }
    } catch (e) {
      console.warn('Failed to load diagnostics state:', e);
    }
  }, []);

  // Update localStorage when expanded state changes
  useEffect(() => {
    localStorage.setItem('agentic-os.diagExpanded', JSON.stringify(expanded));
  }, [expanded]);

  const toggle = () => setExpanded(!expanded);

  return { expanded, setExpanded, toggle };
}
