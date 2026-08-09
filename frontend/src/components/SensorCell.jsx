// =============================================================================
// SensorCell.jsx — border-only rendering
// No background fill at all, so the factory blueprint underneath is fully
// visible. State is communicated purely by border colour, border weight and
// the status dot. Text carries a shadow so it stays readable over any image.
// =============================================================================

import { useMemo } from "react";

// [borderColour, textColour, borderWidth]
const STATE = {
  offline:  ["#6b7280", "#9ca3af", 1.2],
  degraded: ["#f59e0b", "#fcd34d", 1.8],
  critical: ["#ef4444", "#fca5a5", 2.4],
  warning:  ["#f97316", "#fdba74", 1.8],
  normal:   ["#10b981", "#6ee7b7", 1.2],
};

const styleFor = (h, e) =>
  h === "offline"  ? STATE.offline  :
  h === "degraded" ? STATE.degraded :
  e === "critical" ? STATE.critical :
  e === "warning"  ? STATE.warning  : STATE.normal;

const COVER = { machine:"⚙", storage:"📦", exit:"🚪", passage:"" };
const AICON = { worker:"👷", forklift:"🚜", pallet:"📦", object:"📍" };
const SHADOW = "0 1px 3px rgba(0,0,0,0.95), 0 0 6px rgba(0,0,0,0.7)";

export default function SensorCell({
  sensorId, sensor, health, assets, onSelect, cellPx, config, zone,
}) {
  const S = sensor || {}, H = health || {};
  const [border, text, bw] = styleFor(H.status, S.env_status);

  const groups = useMemo(() => {
    const g = {};
    (assets || []).forEach(a => { const t = a.asset_type || "object";
      g[t] = (g[t] || 0) + 1; });
    return g;
  }, [assets]);

  const total      = (assets || []).length;
  const isOffline  = H.status === "offline";
  const isCritical = S.env_status === "critical" || S.smoke;
  const px         = cellPx || 96;
  const cover      = COVER[config?.coverage_type] || "";
  const blocked    = config?.passable === false;

  return (
    <div
      onClick={() => onSelect && onSelect(sensorId)}
      title={`${sensorId}${zone ? ` · ${zone.name}` : ""}` +
             `${config?.description ? ` · ${config.description}` : ""}`}
      style={{
        width: px, height: px,
        background: "transparent",              // ← no fill: blueprint visible
        border: `${bw}px solid ${border}`,
        borderStyle: blocked ? "dashed" : "solid",
        borderRadius: 6,
        cursor: "pointer",
        display: "flex", flexDirection: "column",
        padding: "4px 5px", boxSizing: "border-box",
        position: "relative", overflow: "hidden",
        transition: "border-color .2s, box-shadow .2s, transform .12s",
        boxShadow: isCritical && !isOffline ? `0 0 14px ${border}aa` : "none",
        animation: isCritical && !isOffline ? "dtPulse 1.8s ease-in-out infinite" : "none",
      }}
      onMouseEnter={e => {
        e.currentTarget.style.transform = "scale(1.05)";
        e.currentTarget.style.boxShadow = `0 0 12px ${border}cc`;
      }}
      onMouseLeave={e => {
        e.currentTarget.style.transform = "scale(1)";
        e.currentTarget.style.boxShadow =
          isCritical && !isOffline ? `0 0 14px ${border}aa` : "none";
      }}
    >
      {/* Header */}
      <div style={{ display:"flex", justifyContent:"space-between",
                    alignItems:"center", marginBottom:2 }}>
        <span style={{ fontSize:9, fontWeight:700, color:text,
                       fontFamily:"monospace", textShadow:SHADOW }}>
          {sensorId}
          {cover && <span style={{ marginLeft:3 }}>{cover}</span>}
          {blocked && <span style={{ color:"#ef4444", marginLeft:2 }}>✕</span>}
        </span>
        <span style={{ width:7, height:7, borderRadius:"50%", flexShrink:0,
          background: isOffline ? "#6b7280" : isCritical ? "#ef4444"
                    : H.status === "degraded" ? "#f59e0b" : "#10b981",
          boxShadow:"0 0 5px rgba(0,0,0,0.9)" }}/>
      </div>

      {/* Readings */}
      {isOffline ? (
        <div style={{ flex:1, display:"flex", alignItems:"center",
                      justifyContent:"center" }}>
          <span style={{ fontSize:9, color:"#9ca3af", fontFamily:"monospace",
                         textShadow:SHADOW }}>offline</span>
        </div>
      ) : (
        <div style={{ flex:1, fontSize:9.5, color:text, fontFamily:"monospace",
                      lineHeight:1.55, textShadow:SHADOW }}>
          {S.temperature != null && <div>🌡 {S.temperature.toFixed(1)}°</div>}
          {S.humidity    != null && <div>💧 {S.humidity.toFixed(0)}%</div>}
          {S.smoke && <div style={{ color:"#fca5a5", fontWeight:700 }}>💨 SMOKE</div>}
        </div>
      )}

      {/* Asset counts */}
      {total > 0 && (
        <div style={{ display:"flex", gap:4, flexWrap:"wrap", marginTop:2 }}>
          {Object.entries(groups).map(([t, n]) => (
            <span key={t} style={{ fontSize:9, color:"#e2e8f0",
              fontFamily:"monospace", background:"rgba(2,8,20,0.72)",
              borderRadius:3, padding:"1px 4px", textShadow:SHADOW }}>
              {AICON[t] || "📍"}×{n}
            </span>
          ))}
        </div>
      )}

      <style>{`
        @keyframes dtPulse {
          0%,100% { box-shadow: 0 0 10px ${border}88; }
          50%     { box-shadow: 0 0 22px ${border}ee; }
        }
      `}</style>
    </div>
  );
}
