/**
 * ErrorBoundary — keeps a render error in one view from blanking the whole app.
 *
 * Without this, any uncaught error thrown while rendering a view unmounts the
 * entire React tree (sidebar included), leaving a black window with no way out.
 * Wrap each active view in this boundary and give it a `key` tied to the view
 * id so switching views (or hitting "Try again") clears the error state.
 */

import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Surface in the console for debugging; the UI shows a recoverable message.
    console.error("View render error:", error, info?.componentStack);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      return (
        <div className="view-error" style={{ padding: "2rem", maxWidth: 640 }}>
          <h2 style={{ marginTop: 0 }}>This view hit an error</h2>
          <p style={{ opacity: 0.8 }}>
            {this.props.label ? `The “${this.props.label}” view ` : "The view "}
            failed to render. The rest of the app is still working — pick another
            item in the sidebar, or try again.
          </p>
          <pre
            style={{
              whiteSpace: "pre-wrap",
              background: "var(--bg-inset, #2a2a27)",
              padding: "0.75rem 1rem",
              borderRadius: 6,
              fontSize: 12,
              overflow: "auto",
            }}
          >
            {String(this.state.error?.message || this.state.error)}
          </pre>
          <button className="btn" onClick={this.reset} style={{ marginTop: 12 }}>
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
