import { useState, useCallback } from "react";

/**
 * Hook for managing explorer state (selection, loading, etc)
 * @returns {object} { selected, setSelected, loading, setLoading, error, setError, data, setData }
 */
export function useExplorer() {
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [details, setDetails] = useState(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState(null);

  const selectItem = useCallback((id) => {
    setSelected(id);
    setDetails(null);
    setDetailsError(null);
  }, []);

  const clearSelection = useCallback(() => {
    setSelected(null);
    setDetails(null);
    setDetailsError(null);
  }, []);

  return {
    selected,
    setSelected,
    selectItem,
    clearSelection,
    loading,
    setLoading,
    error,
    setError,
    data,
    setData,
    details,
    setDetails,
    detailsLoading,
    setDetailsLoading,
    detailsError,
    setDetailsError,
  };
}
