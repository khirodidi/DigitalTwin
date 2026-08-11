// =============================================================================
// SensorDetail.jsx
// Panel that appears when a sensor cell is clicked.
// Shows: sensor info, env readings, and all assets grouped by type.
// =============================================================================
import { useMemo } from "react";
// Inlined so this component has no dependency on build-time env vars
const ASSET_ICONS = { worker:"👷", forklift:"🚜", pallet:"📦", object:"📍" };
const assetIcon = t => ASSET_ICONS[t] || "📍";
const statusBg = (s, e) =>
  s === "offline"  ? { bg:"#111827", border:"#374151", text:"#6b7280" } :
  s === "degraded" ? { bg:"#1c1408", border:"#d97706", text:"#fbbf24" } :
  e === "critical" ? { bg:"#1a0808", border:"#dc2626", text:"#f87171" } :
  e === "warning"  ? { bg:"#1a0f04", border:"#f97316", text:"#fb923c" } :
                     { bg:"#041a10", border:"#10b981", text:"#34d399" };

const ACCESS_STYLE = {
  authorised: { color:"#4ade80", icon:"●" },
  violation:  { color:"#f87171", icon:"✕" },
  unknown:    { color:"#fbbf24", icon:"?" },
};

function AssetGroup({ type, assets }) {
  const style = { color:"#e2e8f0", icon: assetIcon(type) };
  return (
    <div style={{ marginBottom:10 }}>
      <div style={{
        fontSize:10, fontWeight:700, color:"#94a3b8",
        fontFamily:"monospace", letterSpacing:1,
        textTransform:"uppercase", marginBottom:4,
        paddingBottom:3, borderBottom:"0.5px solid #1e293b",
      }}>
        {style.icon} {type}s ({assets.length})
      </div>
      {assets.map(a => {
        const ast = ACCESS_STYLE[a.access_status] || ACCESS_STYLE.unknown;
        return (
          <div key={a.id} style={{
            display:"flex", alignItems:"center", justifyContent:"space-between",
            padding:"4px 6px", marginBottom:3, borderRadius:5,
            background:"rgba(255,255,255,0.04)",
            border:"0.5px solid #1e293b",
          }}>
            <span style={{ fontSize:11, fontFamily:"monospace", color:"#e2e8f0" }}>
              {style.icon} {a.name || a.id}
            </span>
            <span style={{
              fontSize:9, fontWeight:700, fontFamily:"monospace",
              color: ast.color, padding:"1px 6px",
              background: ast.color + "18",
              border:`0.5px solid ${ast.color}44`,
              borderRadius:3,
            }}>
              {ast.icon} {a.access_status || "unknown"}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default function SensorDetail({ sensorId, sensor, health, assets, onClose, config, zone }) {
  // NOTE: every hook must run on every render — the early return for a missing
  // sensorId lives BELOW the useMemo, never above it. Returning first would
  // change the hook count between renders and crash React.

  const S   = sensor || {};
  const H   = health || {};
  const col = statusBg(H.status, S.env_status);

  // Group assets by type
  const groups = useMemo(() => {
    const g = {};
    (assets || []).forEach(a => {
      const t = a.asset_type || "object";
      if (!g[t]) g[t] = [];
      g[t].push(a);
    });
    return g;
  }, [assets]);

  // Safe to bail out now that all hooks have run
  if (!sensorId) return null;

  const totalAssets = (assets || []).length;

  return (
    <>
      {/* Backdrop.
          z-index sits above the full-screen factory view (which uses 200) so
          clicking a sensor works identically in normal and full-screen mode.
          Anything layered over the map must stay below this. */}
      <div
        onClick={onClose}
        style={{
          position:"fixed", inset:0, background:"rgba(0,0,0,0.55)", zIndex:300,
        }}
      />

      {/* Panel */}
      <div style={{
        position:"fixed", top:"50%", left:"50%",
        transform:"translate(-50%,-50%)",
        width:340, maxWidth:"92vw", maxHeight:"85vh", minHeight:0,
        background:"#0d1829",
        border:`1.5px solid ${col.border}`,
        borderRadius:12,
        boxShadow:`0 0 40px ${col.border}44`,
        zIndex:301, display:"flex", flexDirection:"column",
        overflow:"hidden", fontFamily:"monospace",
      }}>

        {/* Header */}
        <div style={{
          padding:"12px 16px",
          background: col.bg,
          borderBottom:`1px solid ${col.border}44`,
          display:"flex", alignItems:"center", justifyContent:"space-between",
        }}>
          <div>
            <div style={{ fontSize:14, fontWeight:700, color:col.text }}>{sensorId}</div>
            <div style={{ fontSize:10, color:"#64748b", marginTop:1 }}>
              Zone: {zone?.name || S.zone_id || "unassigned"}
              {zone?.sensorCount ? ` (${zone.sensorCount} sensors)` : ""}
              {config?.coverage_type && ` · ${config.coverage_type}`}
              {config?.passable === false && (
                <span style={{ color:"#f87171" }}> · not passable</span>
              )}
            </div>
            {config?.description && (
              <div style={{ fontSize:9, color:"#475569", marginTop:2 }}>
                {config.description}
              </div>
            )}
          </div>
          <div style={{ display:"flex", alignItems:"center", gap:10 }}>
            <span style={{
              fontSize:9, fontWeight:700, padding:"2px 8px",
              borderRadius:4, border:`1px solid ${col.border}`,
              color: col.text, background: col.border + "22",
              letterSpacing:1, textTransform:"uppercase",
            }}>
              {H.status || "unknown"}
            </span>
            <button onClick={onClose} style={{
              background:"none", border:"none", cursor:"pointer",
              color:"#64748b", fontSize:18, lineHeight:1, padding:0,
            }}>×</button>
          </div>
        </div>

        {/* Env readings */}
        <div style={{
          padding:"10px 16px",
          borderBottom:"1px solid #1e293b",
          display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:6,
        }}>
          <div style={{ textAlign:"center" }}>
            <div style={{ fontSize:18, fontWeight:700, color:
              S.temperature > 60 ? "#f87171" : S.temperature > 50 ? "#fb923c" : "#e2e8f0"
            }}>
              {S.temperature != null ? `${S.temperature.toFixed(1)}°` : "—"}
            </div>
            <div style={{ fontSize:8, color:"#475569" }}>TEMP (°C)</div>
          </div>
          <div style={{ textAlign:"center" }}>
            <div style={{ fontSize:18, fontWeight:700, color:
              S.humidity > 85 ? "#f87171" : S.humidity > 70 ? "#fb923c" : "#e2e8f0"
            }}>
              {S.humidity != null ? `${S.humidity.toFixed(0)}%` : "—"}
            </div>
            <div style={{ fontSize:8, color:"#475569" }}>HUMIDITY</div>
          </div>
          <div style={{ textAlign:"center" }}>
            <div style={{ fontSize:18, fontWeight:700,
              color: S.smoke ? "#f87171" : "#4ade80"
            }}>
              {S.smoke ? "💨 YES" : "✓ NO"}
            </div>
            <div style={{ fontSize:8, color:"#475569" }}>SMOKE</div>
          </div>
        </div>

        {/* Asset list */}
        <div style={{ flex:1, minHeight:0, overflowY:"auto", padding:"12px 16px" }}>
          <div style={{
            fontSize:9, fontWeight:700, color:"#475569",
            letterSpacing:1.5, marginBottom:10,
          }}>
            ASSETS IN RANGE ({totalAssets})
          </div>

          {totalAssets === 0 ? (
            <div style={{ textAlign:"center", color:"#334155", fontSize:11, padding:20 }}>
              No assets in range of this sensor
            </div>
          ) : (
            Object.entries(groups).map(([type, list]) => (
              <AssetGroup key={type} type={type} assets={list} />
            ))
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding:"8px 16px",
          borderTop:"1px solid #1e293b",
          fontSize:9, color:"#334155", textAlign:"center",
        }}>
          Last update: {H.last_heartbeat
            ? new Date(H.last_heartbeat).toLocaleTimeString()
            : "—"}
          {H.consecutive_failures > 0 &&
            <span style={{ color:"#f59e0b", marginLeft:8 }}>
              ⚠ {H.consecutive_failures} missed heartbeat(s)
            </span>}
        </div>
      </div>
    </>
  );
}
