// =============================================================================
// SensorCell.jsx
// One grid cell representing a single sensor.
// Shows: status (background colour), env readings, asset count by type.
// On click: calls onSelect(sensorId) to open the detail panel.
// =============================================================================
import { useMemo } from "react";
import { statusBg, assetIcon } from "../config/factory";

export default function SensorCell({ sensorId, sensor, health, assets, onSelect, cellPx }) {
  const S    = sensor  || {};
  const H    = health  || {};
  const col  = statusBg(H.status, S.env_status);

  // Group assets by type
  const groups = useMemo(() => {
    const g = {};
    (assets || []).forEach(a => {
      const t = a.asset_type || "object";
      g[t] = (g[t] || 0) + 1;
    });
    return g;
  }, [assets]);

  const totalAssets = (assets || []).length;
  const isOffline   = H.status === "offline";
  const isCritical  = S.env_status === "critical" || S.smoke;
  const pulse       = isCritical && !isOffline;

  const px = cellPx || 96;

  return (
    <div
      onClick={() => onSelect && onSelect(sensorId)}
      title={`${sensorId} — click for details`}
      style={{
        width: px, height: px,
        background:   col.bg,
        border:       `1.5px solid ${col.border}`,
        borderRadius: 6,
        cursor:       "pointer",
        display:      "flex",
        flexDirection:"column",
        padding:      "4px 5px",
        boxSizing:    "border-box",
        position:     "relative",
        transition:   "transform .12s",
        boxShadow:    pulse ? `0 0 10px ${col.border}88` : "none",
        animation:    pulse ? "pulse 1.8s ease-in-out infinite" : "none",
      }}
      onMouseEnter={e => e.currentTarget.style.transform = "scale(1.06)"}
      onMouseLeave={e => e.currentTarget.style.transform = "scale(1)"}
    >
      {/* ── Header row: sensor ID + status dot ── */}
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:2 }}>
        <span style={{ fontSize:9, fontWeight:700, color:col.text, fontFamily:"monospace" }}>
          {sensorId}
        </span>
        <span style={{
          width:7, height:7, borderRadius:"50%",
          background: isOffline ? "#6b7280" : isCritical ? "#ef4444" :
                      H.status==="degraded" ? "#f59e0b" : "#10b981",
          flexShrink:0,
        }}/>
      </div>

      {/* ── Env readings ── */}
      {isOffline ? (
        <div style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center" }}>
          <span style={{ fontSize:9, color:"#4b5563", fontFamily:"monospace" }}>offline</span>
        </div>
      ) : (
        <div style={{ flex:1 }}>
          <div style={{ fontSize:9.5, color: col.text, fontFamily:"monospace", lineHeight:1.6 }}>
            {S.temperature != null && (
              <div>🌡 {S.temperature.toFixed(1)}°C</div>
            )}
            {S.humidity != null && (
              <div>💧 {S.humidity.toFixed(0)}%</div>
            )}
            {S.smoke && (
              <div style={{ color:"#ef4444", fontWeight:700 }}>💨 SMOKE</div>
            )}
          </div>
        </div>
      )}

      {/* ── Asset counts by type ── */}
      {totalAssets > 0 && (
        <div style={{
          borderTop:`0.5px solid ${col.border}44`,
          paddingTop:2, marginTop:2,
          display:"flex", gap:4, flexWrap:"wrap",
        }}>
          {Object.entries(groups).map(([type, count]) => (
            <span key={type} style={{
              fontSize:9, color:"#94a3b8", fontFamily:"monospace",
              background:"rgba(255,255,255,0.06)",
              borderRadius:3, padding:"1px 3px",
            }}>
              {assetIcon(type)}×{count}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
