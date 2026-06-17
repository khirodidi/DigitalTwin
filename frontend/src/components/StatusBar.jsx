// components/StatusBar.jsx — top system status banner
import { useMemo } from "react";

const STATUS_CONFIG = {
  nominal:  { bg: "#052e16", border: "#16a34a", text: "#4ade80", icon: "✓", label: "NOMINAL"  },
  degraded: { bg: "#431407", border: "#ea580c", text: "#fb923c", icon: "⚠", label: "DEGRADED" },
  critical: { bg: "#450a0a", border: "#dc2626", text: "#f87171", icon: "✕", label: "CRITICAL" },
  unknown:  { bg: "#0f172a", border: "#334155", text: "#64748b", icon: "?", label: "UNKNOWN"  },
};

export default function StatusBar({ systemState, wsConnected, aiStatus }) {
  const status = systemState?.overall_status || "unknown";
  const cfg    = STATUS_CONFIG[status] || STATUS_CONFIG.unknown;

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 16,
      padding: "10px 20px",
      background: cfg.bg, borderBottom: `1px solid ${cfg.border}`,
      fontFamily: "monospace",
    }}>
      {/* Status badge */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "4px 14px", borderRadius: 6,
        border: `1px solid ${cfg.border}`, background: cfg.border + "22",
      }}>
        <span style={{ fontSize: 14, color: cfg.text }}>{cfg.icon}</span>
        <span style={{ fontSize: 11, fontWeight: 700, color: cfg.text, letterSpacing: 1.5 }}>
          {cfg.label}
        </span>
      </div>

      {/* Sensor counters */}
      <div style={{ display: "flex", gap: 12, fontSize: 10, color: "#94a3b8" }}>
        <span>Sensors:
          <span style={{ color: "#4ade80", marginLeft: 4 }}>{systemState?.sensors?.online ?? "—"} online</span>
          {" · "}
          <span style={{ color: "#fb923c" }}>{systemState?.sensors?.degraded ?? "—"} degraded</span>
          {" · "}
          <span style={{ color: "#f87171" }}>{systemState?.sensors?.offline ?? "—"} offline</span>
        </span>
        <span>|</span>
        <span>Zones:
          <span style={{ color: "#4ade80", marginLeft: 4 }}>{systemState?.environment?.zones_normal ?? "—"} normal</span>
          {" · "}
          <span style={{ color: "#f87171" }}>{systemState?.environment?.zones_critical ?? "—"} critical</span>
        </span>
        <span>|</span>
        <span>Violations:
          <span style={{ color: systemState?.access?.violations > 0 ? "#f87171" : "#4ade80", marginLeft: 4 }}>
            {systemState?.access?.violations ?? "—"}
          </span>
        </span>
      </div>

      {/* Right side: WS + AI status */}
      <div style={{ marginLeft: "auto", display: "flex", gap: 10, alignItems: "center" }}>
        <span style={{
          fontSize: 9, fontWeight: 700, letterSpacing: 1, padding: "2px 8px",
          borderRadius: 4, border: `1px solid ${wsConnected ? "#16a34a" : "#6b7280"}`,
          color: wsConnected ? "#4ade80" : "#9ca3af",
          background: wsConnected ? "#16a34a22" : "#33415522",
        }}>
          {wsConnected ? "⬤ LIVE" : "○ OFFLINE"}
        </span>
        {aiStatus && (
          <span style={{
            fontSize: 9, padding: "2px 8px", borderRadius: 4,
            border: "1px solid #7c3aed", color: "#c4b5fd", background: "#7c3aed22",
          }}>
            AI {aiStatus}
          </span>
        )}
        <span style={{ fontSize: 9, color: "#334155" }}>
          {new Date().toLocaleTimeString()}
        </span>
      </div>
    </div>
  );
}
