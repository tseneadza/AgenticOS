import { useState, useEffect } from "react";

/**
 * Hook for checking service health periodically
 * @param {string} url - Health check URL
 * @param {number} interval - Check interval in ms (default 5000)
 * @returns {object} { ok, label, color }
 */
export function useHealthCheck(url, interval = 5000) {
  const [ok, setOk] = useState(null);
  const [label, setLabel] = useState("checking…");
  const [color, setColor] = useState("#e0b84c");

  useEffect(() => {
    if (!url) return;

    const check = async () => {
      try {
        const r = await fetch(url, { signal: AbortSignal.timeout(2000) });
        setOk(r.ok);
        setLabel(r.ok ? "online" : `offline (${r.status})`);
        setColor(r.ok ? "#7fb069" : "#d9534f");
      } catch (e) {
        setOk(false);
        setLabel("offline");
        setColor("#d9534f");
      }
    };

    check();
    const id = setInterval(check, interval);
    return () => clearInterval(id);
  }, [url, interval]);

  return { ok, label, color };
}
