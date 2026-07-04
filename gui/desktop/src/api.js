// Sidecar API client (default port 5130 — see hub/docs/PORT_ASSIGNMENTS.md,
// TR-10). Base URL is user-configurable via Settings (settings.js) and read
// lazily per request so changes apply without a reload.
import { sidecarUrl, sidecarWsUrl } from "./settings";

export async function get(path) {
  const r = await fetch(`${sidecarUrl()}${path}`);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

export async function post(path, body) {
  const r = await fetch(`${sidecarUrl()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

// AG-UI WebSocket with auto-reconnect (FR-21)
export function connectAgui(onEvent, onStatus) {
  let ws;
  let closed = false;

  function open() {
    ws = new WebSocket(sidecarWsUrl("/ws/agui"));
    ws.onopen = () => onStatus?.(true);
    ws.onmessage = (m) => {
      try {
        onEvent(JSON.parse(m.data));
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onclose = () => {
      onStatus?.(false);
      if (!closed) setTimeout(open, 2000);
    };
    ws.onerror = () => ws.close();
  }
  open();
  return () => {
    closed = true;
    ws?.close();
  };
}

export const fmtAge = (s) => {
  if (s == null) return "—";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m ago`;
};

export const fmtEta = (s) => {
  if (s == null) return "—";
  if (s <= 0) return "due now";
  if (s < 3600) return `in ${Math.ceil(s / 60)}m`;
  return `in ${Math.floor(s / 3600)}h ${Math.ceil((s % 3600) / 60)}m`;
};

export const fmtUptime = (s) => {
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return d > 0 ? `${d}d ${h}h` : `${h}h ${m}m`;
};

export const fmtBytes = (b) => {
  if (b > 1e9) return `${(b / 1e9).toFixed(1)} GB`;
  if (b > 1e6) return `${(b / 1e6).toFixed(1)} MB`;
  return `${(b / 1e3).toFixed(0)} KB`;
};
