import { useState, useEffect } from 'react';

/**
 * useFavorites hook
 *
 * Manages favorite workflows persisted to localStorage.
 * Storage key: "agentic-os.favorites"
 *
 * Usage:
 *   const { favorites, addFavorite, removeFavorite } = useFavorites();
 *   favorites.includes('my-workflow') → true
 *   addFavorite('new-workflow')
 *   removeFavorite('old-workflow')
 */
export function useFavorites() {
  const [favorites, setFavorites] = useState([]);

  // Load from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem('agentic-os.favorites');
      if (stored) {
        setFavorites(JSON.parse(stored));
      }
    } catch (e) {
      console.warn('Failed to load favorites:', e);
    }
  }, []);

  const addFavorite = (name) => {
    setFavorites((prev) => {
      const updated = [...new Set([...prev, name])]; // deduplicate
      localStorage.setItem('agentic-os.favorites', JSON.stringify(updated));
      return updated;
    });
  };

  const removeFavorite = (name) => {
    setFavorites((prev) => {
      const updated = prev.filter((n) => n !== name);
      localStorage.setItem('agentic-os.favorites', JSON.stringify(updated));
      return updated;
    });
  };

  const isFavorite = (name) => favorites.includes(name);

  return { favorites, addFavorite, removeFavorite, isFavorite };
}
