/**
 * ResponseDisplay Component
 *
 * Renders an API response with status, duration, and formatted text.
 * Handles loading states, success/error styling, and scrollable text area.
 *
 * @param {object} response - Response object with shape:
 *   - status: number (HTTP status code)
 *   - ok: boolean (success indicator)
 *   - dur: number (duration in ms)
 *   - text: string (response body)
 * @param {boolean} [loading=false] - Loading state indicator
 * @param {object} [customStyle] - Additional inline styles to merge
 */

import StatusIndicator from "./StatusIndicator";

export default function ResponseDisplay({ response, loading = false, customStyle }) {
  // Determine border color based on state
  let borderColor = "#4a4a46"; // default (no response)
  if (loading) {
    borderColor = "#4a4a46"; // loading
  } else if (response?.ok) {
    borderColor = "#2a4a2a"; // success (dark green)
  } else if (response) {
    borderColor = "#4a2a2a"; // error (dark red)
  }

  // Determine text color based on state
  let textColor = "var(--text-dim)"; // default
  if (loading) {
    textColor = "#e0b84c"; // yellow (loading)
  } else if (response?.ok) {
    textColor = "#7fb069"; // green (success)
  } else if (response) {
    textColor = "#d9534f"; // red (error)
  }

  const containerStyle = {
    background: "var(--bg-inset)",
    border: `1px solid ${borderColor}`,
    borderRadius: 4,
    padding: "10px 12px",
    fontFamily: "var(--mono)",
    fontSize: 11,
    lineHeight: 1.6,
    whiteSpace: "pre-wrap",
    overflowX: "auto",
    minHeight: 80,
    maxHeight: 300,
    overflowY: "auto",
    color: textColor,
    ...customStyle,
  };

  return (
    <div>
      <div
        style={{
          fontSize: 10,
          textTransform: "uppercase",
          letterSpacing: 1,
          color: "var(--text-dim)",
          marginBottom: 6,
        }}
      >
        Response
      </div>
      <div style={containerStyle} data-testid="response-display">
        {loading ? (
          "Sending request…"
        ) : response ? (
          <>
            <StatusIndicator
              status={response.status || "ERR"}
              ok={response.ok}
            />
            <span style={{ color: "var(--text-dim)", fontSize: 10 }}>
              {response.dur}ms
            </span>
            {"\n\n"}
            {response.text}
          </>
        ) : (
          "No response yet — click Run to send the request."
        )}
      </div>
    </div>
  );
}
