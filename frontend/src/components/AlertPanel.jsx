// components/AlertPanel.jsx — live alert feed with AI insights
import { useState } from "react";

const LEVEL_STYLE = {
  critical: { border: "#ef4444", bg: "#7f1d1d22", text: "#fca5a5", icon: "🔴" },
  warning:  { border: "#f59e0b", bg: "#78350f22", text: "#fcd34d", icon: "🟡" },
  info:     { border: "#3b82f6", bg: "#1e3a5f22", text: "#93c5fd", icon: "🔵" },
};

export default function AlertPanel({ alerts, aiInsights }) {
  const [filter, setFilter] = useState("all");

  const all = [
    ...(aiInsights || []).map(a => ({ ...a, _source: "ai" })),
    ...(alerts     || []).map(a => ({ ...a, _source: "rule" })),
  ].sort((a, b) => new Date(b.ts || b.timestamp) - new Date(a.ts || a.timestamp))
   .slice(0, 50);

  const shown = filter === "all" ? all
    : filter === "ai"   ? all.filter(a => a._source === "ai")
    : all.filter(a => a.level === filter);

  return (
    <div style={{
      display: "flex", flexDirection: "column", height: "100%",
      background: "#0d1829", borderLeft: "1px solid #1e293b",
    }}>
      {/* Header */}
      <div style={{
        padding: "12px 16px", borderBottom: "1px solid #1e293b",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", fontFamily: "monospace", letterSpacing: 1 }}>
          ALERTS & AI INSIGHTS
        </span>
        <span style={{
          fontSize: 9, padding: "2px 8px", borderRadius: 10,
          background: "#7f1d1d", color: "#fca5a5", fontWeight: 700,
        }}>
          {all.filter(a => a.level === "critical").length} critical
        </span>
      </div>

      {/* Filter tabs */}
      <div style={{ display: "flex", gap: 2, padding: "8px 10px", borderBottom: "1px solid #1e293b" }}>
        {["all", "critical", "warning", "ai"].map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{
            padding: "3px 10px", fontSize: 9, fontWeight: 600,
            borderRadius: 4, border: "none", cursor: "pointer", fontFamily: "monospace",
            background: filter === f ? "#1e40af" : "#1e293b",
            color: filter === f ? "#93c5fd" : "#64748b",
          }}>{f.toUpperCase()}</button>
        ))}
      </div>

      {/* Alert list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "8px" }}>
        {shown.length === 0 && (
          <div style={{ padding: 20, textAlign: "center", color: "#334155", fontSize: 11 }}>
            No alerts
          </div>
        )}
        {shown.map((a, i) => {
          const st = LEVEL_STYLE[a.level] || LEVEL_STYLE.info;
          return (
            <div key={i} style={{
              marginBottom: 6, padding: "8px 10px", borderRadius: 6,
              border: `1px solid ${st.border}33`, background: st.bg,
              fontFamily: "monospace",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                <span style={{ fontSize: 10 }}>{st.icon}</span>
                <span style={{ fontSize: 9, fontWeight: 700, color: st.text }}>
                  {a.type?.replace(/_/g, " ").toUpperCase()}
                </span>
                {a._source === "ai" && (
                  <span style={{
                    fontSize: 7, padding: "1px 5px", borderRadius: 3,
                    background: "#7c3aed", color: "#c4b5fd", fontWeight: 700, marginLeft: "auto",
                  }}>AI</span>
                )}
                <span style={{ fontSize: 7, color: "#475569", marginLeft: "auto" }}>
                  {new Date(a.ts || a.timestamp).toLocaleTimeString()}
                </span>
              </div>
              <div style={{ fontSize: 9, color: "#94a3b8", lineHeight: 1.4 }}>{a.message}</div>
              {a.action && (
                <div style={{ fontSize: 8, color: "#475569", marginTop: 3 }}>→ {a.action}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
