// =============================================================================
// SensorCell.jsx
// One grid cell = one sensor.
//
// TRANSLUCENCY: the cell background is intentionally semi-transparent so the
// uploaded factory blueprint stays visible underneath. Opacity scales with
// severity — a NORMAL sensor is barely tinted (blueprint fully readable),
// a CRITICAL one is strongly tinted so it stands out. Text and borders stay
// fully opaque so readings remain legible over any background image.
// =============================================================================

import { useMemo } from "react";

// [borderColour, textColour, fillAlpha]  — fillAlpha drives blueprint visibility
const STATE_STYLE = {
  offline:  ["#6b7280", "#9ca3af", 0.55],  // opaque-ish: sensor is dead, hide map
  degraded: ["#f59e0b", "#fcd34d", 0.34],
  critical: ["#ef4444", "#fca5a5", 0.42],  // stands out over the blueprint
  warning:  ["#f97316", "#fdba74", 0.30],
  normal:   ["#10b981", "#6ee7b7", 0.16],  // faint: blueprint clearly visible
};

function styleFor(healthStatus, envStatus) {
  if (healthStatus === "offline")  return STATE_STYLE.offline;
  if (healthStatus === "degraded") return STATE_STYLE.degraded;
  if (envStatus === "critical")    return STATE_STYLE.critical;
  if (envStatus === "warning")     return STATE_STYLE.warning;
  return STATE_STYLE.normal;
}

const COVERAGE_ICON = { machine: "⚙", storage: "📦", exit: "🚪", passage: "" };
const ASSET_ICON    = { worker: "👷", forklift: "🚜", pallet: "📦", object: "📍" };

export default function SensorCell({
  sensorId, sensor, health, assets, onSelect, cellPx, config, zone,
}) {
  const S = sensor || {};
  const H = health || {};
  const [border, text, alpha] = styleFor(H.status, S.env_status);

  const groups = useMemo(() => {
    const g = {};
    (assets || []).forEach(a => {
      const t = a.asset_type || "object";
      g[t] = (g[t] || 0) + 1;
    });
    return g;
  }, [assets]);

  const total      = (assets || []).length;
  const isOffline  = H.status === "offline";
  const isCritical = S.env_status === "critical" || S.smoke;
  const px         = cellPx || 96;
  const covIcon    = COVERAGE_ICON[config?.coverage_type] || "";
  const blocked    = config?.passable === false;

  // Hex colour + alpha → rgba, so the blueprint shows through the fill
  const rgba = (hex, a) => {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  };

  return (
    <div
      onClick={() => onSelect && onSelect(sensorId)}
      title={`${sensorId}${zone ? ` · ${zone.name}` : ""}${
        config?.description ? ` · ${config.description}` : ""}`}
      style={{
        width: px, height: px,
        // Translucent fill — blueprint remains visible underneath
        background:   rgba(border, alpha),
        border:       `1.5px solid ${border}`,
        // Blur the backdrop slightly so text stays readable over busy blueprints
        backdropFilter: "blur(1px)",
        borderRadius: 6,
        cursor:       "pointer",
        display:      "flex",
        flexDirection:"column",
        padding:      "4px 5px",
        boxSizing:    "border-box",
        position:     "relative",
        overflow:     "hidden",
        transition:   "transform .12s, background .2s",
        boxShadow:    isCritical && !isOffline ? `0 0 12px ${border}99` : "none",
        animation:    isCritical && !isOffline ? "dtPulse 1.8s ease-in-out infinite" : "none",
      }}
      onMouseEnter={e => {
        e.currentTarget.style.transform  = "scale(1.05)";
        e.currentTarget.style.background = rgba(border, Math.min(alpha + 0.18, 0.75));
      }}
      onMouseLeave={e => {
        e.currentTarget.style.transform  = "scale(1)";
        e.currentTarget.style.background = rgba(border, alpha);
      }}
    >
      {/* Header: sensor ID + coverage icon + status dot */}
      <div style={{ display:"flex", justifyContent:"space-between",
                    alignItems:"center", marginBottom:2 }}>
        <span style={{ fontSize:9, fontWeight:700, color:text,
                       fontFamily:"monospace", textShadow:"0 1px 3px rgba(0,0,0,0.9)" }}>
          {sensorId}
          {covIcon && <span style={{ marginLeft:3, opacity:0.85 }}>{covIcon}</span>}
          {blocked && <span style={{ color:"#ef4444", marginLeft:2 }} title="Not passable">✕</span>}
        </span>
        <span style={{
          width:7, height:7, borderRadius:"50%", flexShrink:0,
          background: isOffline ? "#6b7280"
                    : isCritical ? "#ef4444"
                    : H.status === "degraded" ? "#f59e0b" : "#10b981",
          boxShadow: "0 0 4px rgba(0,0,0,0.8)",
        }}/>
      </div>

      {/* Readings */}
      {isOffline ? (
        <div style={{ flex:1, display:"flex", alignItems:"center",
                      justifyContent:"center" }}>
          <span style={{ fontSize:9, color:"#9ca3af", fontFamily:"monospace",
                         textShadow:"0 1px 3px rgba(0,0,0,0.9)" }}>offline</span>
        </div>
      ) : (
        <div style={{ flex:1, fontSize:9.5, color:text, fontFamily:"monospace",
                      lineHeight:1.55, textShadow:"0 1px 3px rgba(0,0,0,0.9)" }}>
          {S.temperature != null && <div>🌡 {S.temperature.toFixed(1)}°</div>}
          {S.humidity    != null && <div>💧 {S.humidity.toFixed(0)}%</div>}
          {S.smoke && <div style={{ color:"#fca5a5", fontWeight:700 }}>💨 SMOKE</div>}
        </div>
      )}

      {/* Asset counts by type */}
      {total > 0 && (
        <div style={{
          borderTop: `0.5px solid ${border}66`,
          paddingTop:2, marginTop:2,
          display:"flex", gap:4, flexWrap:"wrap",
        }}>
          {Object.entries(groups).map(([type, n]) => (
            <span key={type} style={{
              fontSize:9, color:"#e2e8f0", fontFamily:"monospace",
              background:"rgba(0,0,0,0.45)", borderRadius:3, padding:"1px 4px",
              textShadow:"0 1px 2px rgba(0,0,0,0.9)",
            }}>
              {ASSET_ICON[type] || "📍"}×{n}
            </span>
          ))}
        </div>
      )}

      <style>{`
        @keyframes dtPulse {
          0%,100% { box-shadow: 0 0 8px ${border}88; }
          50%     { box-shadow: 0 0 20px ${border}dd; }
        }
      `}</style>
    </div>
  );
}
