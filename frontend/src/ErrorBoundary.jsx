// =============================================================================
// frontend/src/ErrorBoundary.jsx
// Catches render errors and displays them instead of unmounting the tree.
// Without this, any exception (a hooks-order violation, a bad prop, a failed
// import) leaves a completely blank page with no clue as to the cause.
// =============================================================================

import React from "react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null, info: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    this.setState({ info });
    console.error("[Digital Twin] Render error:", error, info);
  }

  render() {
    const { error, info } = this.state;
    if (!error) return this.props.children;

    const box = {
      background: "#0d1829", border: "1px solid #1e293b",
      borderRadius: 10, padding: 16, marginBottom: 14,
      fontFamily: "monospace", fontSize: 11, color: "#94a3b8",
      whiteSpace: "pre-wrap", overflowX: "auto",
    };

    return (
      <div style={{
        height: "100vh", overflowY: "auto",
        background: "#050c1a", color: "#e2e8f0",
        fontFamily: "'IBM Plex Mono','Fira Code',monospace",
        padding: "40px 20px",
      }}>
        <div style={{ maxWidth: 860, margin: "0 auto" }}>
          <div style={{ fontSize: 34, marginBottom: 10 }}>⚠️</div>
          <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 6 }}>
            The dashboard failed to render
          </div>
          <div style={{ fontSize: 12, color: "#475569", marginBottom: 22 }}>
            The error below stopped React from mounting. Copy it when reporting
            the problem.
          </div>

          <div style={{ ...box, borderColor: "#ef4444", color: "#fca5a5" }}>
            {String(error && (error.stack || error.message || error))}
          </div>

          {info?.componentStack && (
            <>
              <div style={{ fontSize: 10, color: "#64748b",
                letterSpacing: 1, marginBottom: 6 }}>COMPONENT STACK</div>
              <div style={box}>{info.componentStack}</div>
            </>
          )}

          <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
            <button onClick={() => window.location.reload()}
              style={{ padding: "9px 18px", fontSize: 12, fontWeight: 600,
                fontFamily: "monospace", borderRadius: 8, cursor: "pointer",
                border: "1px solid #6366f1", background: "#6366f122",
                color: "#a5b4fc" }}>
              Reload
            </button>
            <button onClick={() => this.setState({ error: null, info: null })}
              style={{ padding: "9px 18px", fontSize: 12, fontWeight: 600,
                fontFamily: "monospace", borderRadius: 8, cursor: "pointer",
                border: "1px solid #334155", background: "transparent",
                color: "#64748b" }}>
              Try again
            </button>
          </div>
        </div>
      </div>
    );
  }
}
