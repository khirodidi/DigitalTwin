// =============================================================================
// App.jsx — root component
//
// Key behaviour: the monitoring view reads layout from useConfig() at RUNTIME
// and refreshes the moment a `config_updated` WebSocket event arrives, so
// changes saved in the Configuration page appear instantly.
// =============================================================================

import { useReducer, useCallback, useEffect, useState } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { useConfig }    from "./hooks/useConfig";
import FactoryMap  from "./components/FactoryMap";
import StatusBar   from "./components/StatusBar";
import AlertPanel  from "./components/AlertPanel";
import AssetList   from "./components/AssetList";
import ConfigPage  from "./pages/ConfigPage";

function reducer(state, action) {
  switch (action.type) {
    case "SNAPSHOT": {
      const p = action.payload;
      return { ...state,
        systemState: p.system_state || state.systemState,
        sensors: Object.fromEntries((p.sensors || []).map(s => [s.sensor_id, s])),
        health:  Object.fromEntries((p.health  || []).map(h => [h.sensor_id, h])),
        assets:  Object.fromEntries((p.assets  || []).map(a => [a.id, a])) };
    }
    case "SYSTEM_STATE":  return { ...state, systemState: action.payload };
    case "SENSOR_UPDATE": return { ...state, sensors: { ...state.sensors, [action.payload.sensor_id]: action.payload } };
    case "HEALTH_UPDATE": return { ...state, health:  { ...state.health,  [action.payload.sensor_id]: action.payload } };
    case "ASSET_UPDATE":  return { ...state, assets:  { ...state.assets,  [action.payload.id]: action.payload } };
    case "ALERT":         return { ...state, alerts: [{ ...action.payload, _ts: Date.now() }, ...state.alerts].slice(0,120) };
    case "AI_INSIGHT":    return { ...state, aiInsights: [{ ...action.payload, _ts: Date.now() }, ...state.aiInsights].slice(0,60) };
    case "WS_CONNECTED":  return { ...state, wsConnected: action.value };
    default: return state;
  }
}

const INITIAL = { systemState:null, sensors:{}, health:{}, assets:{},
                  alerts:[], aiInsights:[], wsConnected:false };

export default function App() {
  const [state, dispatch] = useReducer(reducer, INITIAL);
  const [time,  setTime]  = useState(new Date());
  const [page,  setPage]  = useState("monitor");
  const [flash, setFlash] = useState(null);

  // ── Runtime configuration (grid, blueprint, zones, sensor metadata) ───────
  const { config, sensors: sensorConfig, zones, cols, rows,
          blueprintSrc, refresh, loading } = useConfig();

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // ── WebSocket event router ────────────────────────────────────────────────
  const onEvent = useCallback((msg) => {
    // Live config change → reload the affected part and flash a banner
    if (msg.event === "config_updated") {
      const section = msg.payload?.section || "all";
      refresh(section);
      setFlash(`Configuration updated (${section}) — view refreshed`);
      setTimeout(() => setFlash(null), 3500);
      return;
    }
    const map = {
      snapshot:"SNAPSHOT", system_state:"SYSTEM_STATE",
      sensor_update:"SENSOR_UPDATE", health_update:"HEALTH_UPDATE",
      asset_update:"ASSET_UPDATE", alert:"ALERT", ai_insight:"AI_INSIGHT",
    };
    if (map[msg.event]) dispatch({ type: map[msg.event], payload: msg.payload });
  }, [refresh]);

  useWebSocket(onEvent);

  // ── Config page — refresh monitoring data when returning ──────────────────
  if (page === "config") {
    return <ConfigPage onBack={() => { refresh("all"); setPage("monitor"); }} />;
  }

  const sensorArr = Object.values(state.sensors);
  const healthArr = Object.values(state.health);
  const assetArr  = Object.values(state.assets);

  return (
    <div style={{ display:"flex", flexDirection:"column",
      height:"100vh", minHeight:0,
      background:"#050c1a", color:"#e2e8f0",
      fontFamily:"'IBM Plex Mono','Fira Code',monospace",
      overflow:"hidden" }}>

      {/* Header */}
      <div style={{ padding:"8px 20px", display:"flex", alignItems:"center", gap:16,
        background:"#0d1829", borderBottom:"1px solid #1e293b",
        flexShrink:0, flexWrap:"wrap" }}>
        <div>
          <div style={{ fontSize:8, color:"#6366f1", letterSpacing:3,
                        textTransform:"uppercase" }}>Digital Twin</div>
          <div style={{ fontSize:15, fontWeight:700 }}>
            {config.factory_name} — Live Monitor
          </div>
        </div>

        <div style={{ marginLeft:"auto", display:"flex", alignItems:"center", gap:12 }}>
          <span style={{ fontSize:9, color:"#334155" }}>
            {cols}×{rows} · {zones.length} zones
            {blueprintSrc ? " · blueprint ✓" : ""}
          </span>
          <button onClick={() => setPage("config")} style={{
            padding:"6px 16px", fontSize:11, fontWeight:600,
            border:"1px solid #6366f1", borderRadius:6,
            background:"#6366f122", color:"#a5b4fc",
            cursor:"pointer", fontFamily:"monospace" }}>
            ⚙️  Configuration
          </button>
          <div style={{ fontSize:11, color:"#475569" }}>{time.toLocaleTimeString()}</div>
        </div>
      </div>

      <StatusBar systemState={state.systemState} wsConnected={state.wsConnected} />

      {/* Live config-change banner */}
      {flash && (
        <div style={{ padding:"6px 20px", background:"#052e16",
          borderBottom:"1px solid #16a34a", fontSize:11, color:"#4ade80",
          display:"flex", alignItems:"center", gap:8 }}>
          <span>✓</span>{flash}
        </div>
      )}

      <div style={{ flex:1, display:"flex", minHeight:0, overflow:"hidden" }}>
        {/* Left sidebar — scrolls independently */}
        <div style={{ width:200, flexShrink:0, minHeight:0,
                      borderRight:"1px solid #1e293b",
                      overflowY:"auto", overflowX:"hidden" }}>
          <AssetList assets={assetArr} />
        </div>

        {/* Centre — scrolls both axes (wide grids scroll horizontally) */}
        <div style={{ flex:1, minWidth:0, minHeight:0,
                      overflowX:"auto", overflowY:"auto", padding:16 }}>
          {loading ? (
            <div style={{ padding:48, textAlign:"center", color:"#334155" }}>
              Loading factory configuration…
            </div>
          ) : (
            <FactoryMap
              sensors={sensorArr} health={healthArr} assets={assetArr}
              cols={cols} rows={rows}
              blueprintSrc={blueprintSrc}
              zones={zones} sensorConfig={sensorConfig} />
          )}

          {state.systemState && (
            <div style={{ display:"flex", gap:8, marginTop:12, flexWrap:"wrap" }}>
              {[
                { l:"Sensors online",  v:state.systemState.sensors?.online,             c:"#4ade80" },
                { l:"Sensors offline", v:state.systemState.sensors?.offline,            c:"#f87171" },
                { l:"Zones critical",  v:state.systemState.environment?.zones_critical, c:"#f87171" },
                { l:"Total assets",    v:state.systemState.access?.total_assets,        c:"#93c5fd" },
                { l:"Violations",      v:state.systemState.access?.violations,          c:"#f87171" },
              ].map(c => (
                <div key={c.l} style={{ padding:"6px 12px", borderRadius:6,
                  background:"#0d1829", border:"1px solid #1e293b", minWidth:110 }}>
                  <div style={{ fontSize:20, fontWeight:700, color:c.c }}>{c.v ?? "—"}</div>
                  <div style={{ fontSize:8, color:"#475569" }}>{c.l}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right sidebar — scrolls independently */}
        <div style={{ width:290, flexShrink:0, minHeight:0,
                      borderLeft:"1px solid #1e293b", display:"flex" }}>
          <AlertPanel alerts={state.alerts} aiInsights={state.aiInsights} />
        </div>
      </div>
    </div>
  );
}
