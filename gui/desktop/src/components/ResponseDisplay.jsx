/**
 * ResponseDisplay Component
 *
 * Renders an API response with status, duration, and formatted text.
 * All colors use theme variables for full theme compatibility.
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

const styles = `
.response-container {
  background: var(--bg-inset);
  border-radius: 4px;
  padding: 10px 12px;
  font-family: var(--mono);
  font-size: 11px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-x: auto;
  min-height: 80px;
  max-height: 300px;
  overflow-y: auto;
}

.response-container.default {
  border: 1px solid var(--border-soft);
  color: var(--text-dim);
}

.response-container.loading {
  border: 1px solid var(--border-soft);
  color: var(--yellow);
}

.response-container.success {
  border: 1px solid rgba(127, 176, 105, 0.4);
  color: var(--green);
}

.response-container.error {
  border: 1px solid rgba(217, 83, 79, 0.4);
  color: var(--red);
}

.response-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-dim);
  margin-bottom: 6px;
}

.response-duration {
  color: var(--text-dim);
  font-size: 10px;
}
`;

export default function ResponseDisplay({ response, loading = false, customStyle }) {
  // Determine state class for styling
  let stateClass = "default"; // default (no response)
  if (loading) {
    stateClass = "loading";
  } else if (response?.ok) {
    stateClass = "success";
  } else if (response) {
    stateClass = "error";
  }

  return (
    <div>
      <style>{styles}</style>
      <div className="response-label">Response</div>
      <div
        className={`response-container ${stateClass}`}
        style={customStyle}
        data-testid="response-display"
      >
        {loading ? (
          "Sending request…"
        ) : response ? (
          <>
            <StatusIndicator
              status={response.status || "ERR"}
              ok={response.ok}
            />
            <span className="response-duration">{response.dur}ms</span>
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
