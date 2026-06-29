import { useState } from "react";

/**
 * Hook for managing collapsible group state
 * @param {array} initialKeys - Initial group keys to manage
 * @returns {object} { groupOpen, toggleGroup, expandAll, collapseAll }
 */
export function useGroupState(initialKeys = []) {
  const [groupOpen, setGroupOpen] = useState(() =>
    Object.fromEntries(initialKeys.map(k => [k, true]))
  );

  const toggleGroup = (key) => {
    setGroupOpen(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const expandAll = (keys = Object.keys(groupOpen)) => {
    setGroupOpen(Object.fromEntries(keys.map(k => [k, true])));
  };

  const collapseAll = (keys = Object.keys(groupOpen)) => {
    setGroupOpen(Object.fromEntries(keys.map(k => [k, false])));
  };

  const setAll = (keys, state) => {
    setGroupOpen(Object.fromEntries(keys.map(k => [k, state])));
  };

  return { groupOpen, toggleGroup, expandAll, collapseAll, setAll, setGroupOpen };
}
