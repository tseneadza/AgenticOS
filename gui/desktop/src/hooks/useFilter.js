import { useState, useCallback, useRef, useEffect } from "react";

/**
 * Hook for managing filtered/searched data with debouncing
 * @param {function} filterFn - Filter function that takes (items, filter) => filteredItems
 * @param {function} sortFn - Sort function that takes (items, sortBy, sortDir) => sortedItems
 * @returns {object} { filter, setFilter, sortBy, setSortBy, sortDir, toggleSort, results }
 */
export function useFilter(filterFn, sortFn) {
  const [filter, setFilterState] = useState("");
  const [sortBy, setSortBy] = useState("name");
  const [sortDir, setSortDir] = useState("asc");
  const [results, setResults] = useState([]);
  const debounceTimer = useRef(null);

  const setFilter = useCallback((value) => {
    setFilterState(value);
    // Debounce filter updates by 150ms
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      // Filter will be applied in useEffect
    }, 150);
  }, []);

  const toggleSort = useCallback((key) => {
    if (sortBy === key) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortBy(key);
      setSortDir("asc");
    }
  }, [sortBy]);

  const reset = useCallback(() => {
    setFilterState("");
    setSortBy("name");
    setSortDir("asc");
  }, []);

  return {
    filter,
    setFilter,
    sortBy,
    setSortBy,
    sortDir,
    toggleSort,
    reset,
  };
}
