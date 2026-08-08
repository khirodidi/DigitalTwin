// =============================================================================
// App.jsx — Root component
// Manages WebSocket state, layout, and passes data to all components.
// =============================================================================
import { useReducer, useCallback, useEffect, useState } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { useApi }       from "./hooks/useApi";
import FactoryMap       from "./components/FactoryMap";
import StatusBar        from "./components/StatusBar";
import AlertPanel       from "./components/AlertPanel";
import AssetList        from "./components/AssetList";
import { FACTORY_NAME } from "./config/factory";

// ── State reducer ─────────────────────────────────────────────────────────────
function reducer(state, action) {
  switch (action.type) {
    case "SNAPSHOT": {
      const p = action.payload;
      return {
        ...state,
        systemState: p.system_state || state.systemState,
        sensors:     Object.fromEntries((p.sensors || []).map(s => [s.sensor_id, s])),
        health:      Object.fromEntries((p.health  || []).map(h => [h.sensor_id, h])),
        assets:      Object.fromEntries((p.assets  || []).map(a => [a.id, a])),
      };
    }
    case "SYSTEM_STATE":
      return { ...state, systemState: action.payload };
    case "SENSOR_UPDATE":
      return { ...state, sensors: { ...state.sensors, [action.payload.sensor_id]: action.payload } };
    case "HEALTH_UPDATE":
      return { ...state, health:  { ...state.health,  [action.payload.sensor_id]: action.payload } };
    case "ASSET_UPDATE":
      return { ...state, assets:  { ...state.assets,  [action.payload.id]: action.payload } };
    case "ALERT":
      return { ...state, alerts: [{ ...action.payload, _ts: Date.now() }, ...state.alerts].slice(0, 120) };
    case "AI_INSIGHT":
      return { ...state, aiInsights: [action.payload, ...state.aiInsights].slice(0, 60) };
    case "WS_CONNECTED":
      return { ...state, wsConnected: action.value };
    default: return state;
  }
}

const INITIAL = {
  systemState: null, sensors: {}, health: {}, assets: {},
  alerts: [], aiInsights: [], wsConnected: false,
};

// ── App ───────────────────────────────────────────────────────────────────────
export default function App() {
  const [state, dispatch] = useReducer(reducer, INITIAL);
  const [time, setTime]   = useState(new Date());

  useEffect(() => { const t = setInterval(() => setTime(new Date()), 1000); return () => clearInterval(t); }, []);

  const onEvent = useCallback((msg) => {
    const map = {
      snapshot:      "SNAPSHOT",
      system_state:  "SYSTEM_STATE",
      sensor_update: "SENSOR_UPDATE",
      health_update: "HEALTH_UPDATE",
      asset_update:  "ASSET_UPDATE",
      alert:         "ALERT",
      ai_insight:    "AI_INSIGHT",
    };
    if (map[msg.event]) dispatch({ type: map[msg.event], payload: msg.payload });
  }, []);

  useWebSocket(onEvent);

  const sensorArr = Object.values(state.sensors);
  const healthArr = Object.values(state.health);
  const assetArr  = Object.values(state.assets);

  return (
    <div style={{
      display:"flex", flexDirection:"column", height:"100vh",
      background:"#050c1a", color:"#e2e8f0",
      fontFamily:"'IBM Plex Mono','Fira Code',monospace", overflow:"hidden",
    }}>
      {/* ── Header ── */}
      <div style={{
        padding:"8px 20px", display:"flex", alignItems:"center", gap:16,
        background:"#0d1829", borderBottom:"1px solid #1e293b", flexShrink:0,
      }}>
        <div>
          <div style={{ fontSize:8, color:"#6366f1", letterSpacing:3, textTransform:"uppercase" }}>
            Digital Twin
          </div>
          <div style={{ fontSize:15, fontWeight:700 }}>{FACTORY_NAME} — Live Dashboard</div>
        </div>
        <div style={{ marginLeft:"auto", fontSize:11, color:"#475569" }}>
          {time.toLocaleTimeString()}
        </div>
      </div>

      {/* ── Status bar ── */}
      <StatusBar systemState={state.systemState} wsConnected={state.wsConnected} />

      {/* ── Main layout ── */}
      <div style={{ flex:1, display:"flex", overflow:"hidden" }}>

        {/* Left: asset list */}
        <div style={{ width:200, borderRight:"1px solid #1e293b", overflowY:"auto", flexShrink:0 }}>
          <AssetList assets={assetArr} />
        </div>

        {/* Centre: factory map */}
        <div style={{ flex:1, overflowX:"auto", overflowY:"auto", padding:16, background:"#050c1a" }}>
          <FactoryMap
            sensors={sensorArr}
            health={healthArr}
            assets={assetArr}
          />

          {/* Counters below map */}
          {state.systemState && (
            <div style={{ display:"flex", gap:8, marginTop:12, flexWrap:"wrap" }}>
              {[
                { l:"Sensors online",  v:state.systemState.sensors?.online,              c:"#4ade80" },
                { l:"Sensors offline", v:state.systemState.sensors?.offline,             c:"#f87171" },
                { l:"Zones critical",  v:state.systemState.environment?.zones_critical,  c:"#f87171" },
                { l:"Total assets",    v:state.systemState.access?.total_assets,         c:"#93c5fd" },
                { l:"Violations",      v:state.systemState.access?.violations,           c:"#f87171" },
              ].map(c => (
                <div key={c.l} style={{
                  padding:"6px 12px", borderRadius:6,
                  background:"#0d1829", border:"1px solid #1e293b", minWidth:110,
                }}>
                  <div style={{ fontSize:20, fontWeight:700, color:c.c }}>{c.v ?? "—"}</div>
                  <div style={{ fontSize:8, color:"#475569" }}>{c.l}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: alerts */}
        <div style={{ width:290, borderLeft:"1px solid #1e293b", flexShrink:0 }}>
          <AlertPanel alerts={state.alerts} aiInsights={state.aiInsights} />
        </div>
      </div>
    </div>
  );
}
