// =============================================================================
// frontend/src/App.jsx  — UPDATED
//
// Changes:
//   1. Added `page` state to switch between "monitor" and "config"
//   2. Added a ⚙️ Configuration button in the header
//   3. Renders <ConfigPage> when page === "config"
//   All monitoring logic is unchanged.
// =============================================================================

import { useReducer, useCallback, useEffect, useState } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import FactoryMap  from "./components/FactoryMap";
import StatusBar   from "./components/StatusBar";
import AlertPanel  from "./components/AlertPanel";
import AssetList   from "./components/AssetList";
import ConfigPage  from "./pages/ConfigPage";        // ← NEW

const FACTORY_NAME = process.env.REACT_APP_FACTORY_NAME || "Factory";

// ── State reducer (unchanged) ─────────────────────────────────────────────────
function reducer(state, action) {
  switch (action.type) {
    case "SNAPSHOT": {
      const p = action.payload;
      return {
        ...state,
        systemState: p.system_state || state.systemState,
        sensors: Object.fromEntries((p.sensors || []).map(s => [s.sensor_id, s])),
        health:  Object.fromEntries((p.health  || []).map(h => [h.sensor_id, h])),
        assets:  Object.fromEntries((p.assets  || []).map(a => [a.id, a])),
      };
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

const INITIAL = {
  systemState: null, sensors: {}, health: {}, assets: {},
  alerts: [], aiInsights: [], wsConnected: false,
};

export default function App() {
  const [state, dispatch] = useReducer(reducer, INITIAL);
  const [time,  setTime]  = useState(new Date());
  const [page,  setPage]  = useState("monitor");   // ← NEW: "monitor" | "config"

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const onEvent = useCallback((msg) => {
    const map = {
      snapshot:"SNAPSHOT", system_state:"SYSTEM_STATE",
      sensor_update:"SENSOR_UPDATE", health_update:"HEALTH_UPDATE",
      asset_update:"ASSET_UPDATE", alert:"ALERT", ai_insight:"AI_INSIGHT",
    };
    if (map[msg.event]) dispatch({ type: map[msg.event], payload: msg.payload });
  }, []);

  useWebSocket(onEvent);

  // ── NEW: render config page ────────────────────────────────────────────────
  if (page === "config") {
    return <ConfigPage onBack={() => setPage("monitor")} />;
  }

  // ── Monitoring page (unchanged except header button) ──────────────────────
  const sensorArr = Object.values(state.sensors);
  const healthArr = Object.values(state.health);
  const assetArr  = Object.values(state.assets);

  return (
    <div style={{
      display:"flex", flexDirection:"column", height:"100vh",
      background:"#050c1a", color:"#e2e8f0",
      fontFamily:"'IBM Plex Mono','Fira Code',monospace", overflow:"hidden",
    }}>
      {/* Header */}
      <div style={{
        padding:"8px 20px", display:"flex", alignItems:"center", gap:16,
        background:"#0d1829", borderBottom:"1px solid #1e293b", flexShrink:0,
      }}>
        <div>
          <div style={{ fontSize:8, color:"#6366f1", letterSpacing:3, textTransform:"uppercase" }}>
            Digital Twin
          </div>
          <div style={{ fontSize:15, fontWeight:700 }}>{FACTORY_NAME} — Live Monitor</div>
        </div>

        {/* ── NEW: Configuration link ── */}
        <button
          onClick={() => setPage("config")}
          style={{
            marginLeft:"auto", padding:"6px 16px", fontSize:11, fontWeight:600,
            border:"1px solid #6366f1", borderRadius:6,
            background:"#6366f122", color:"#a5b4fc",
            cursor:"pointer", fontFamily:"monospace",
            display:"flex", alignItems:"center", gap:6,
          }}
          onMouseEnter={e => e.currentTarget.style.background = "#6366f144"}
          onMouseLeave={e => e.currentTarget.style.background = "#6366f122"}
        >
          ⚙️  Configuration
        </button>

        <div style={{ fontSize:11, color:"#475569" }}>{time.toLocaleTimeString()}</div>
      </div>

      <StatusBar systemState={state.systemState} wsConnected={state.wsConnected} />

      <div style={{ flex:1, display:"flex", overflow:"hidden" }}>
        <div style={{ width:200, borderRight:"1px solid #1e293b", overflowY:"auto", flexShrink:0 }}>
          <AssetList assets={assetArr} />
        </div>

        <div style={{ flex:1, overflowX:"auto", overflowY:"auto", padding:16 }}>
          <FactoryMap sensors={sensorArr} health={healthArr} assets={assetArr} />

          {state.systemState && (
            <div style={{ display:"flex", gap:8, marginTop:12, flexWrap:"wrap" }}>
              {[
                { l:"Sensors online",  v:state.systemState.sensors?.online,             c:"#4ade80" },
                { l:"Sensors offline", v:state.systemState.sensors?.offline,            c:"#f87171" },
                { l:"Zones critical",  v:state.systemState.environment?.zones_critical, c:"#f87171" },
                { l:"Total assets",    v:state.systemState.access?.total_assets,        c:"#93c5fd" },
                { l:"Violations",      v:state.systemState.access?.violations,          c:"#f87171" },
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

        <div style={{ width:290, borderLeft:"1px solid #1e293b", flexShrink:0 }}>
          <AlertPanel alerts={state.alerts} aiInsights={state.aiInsights} />
        </div>
      </div>
    </div>
  );
}
