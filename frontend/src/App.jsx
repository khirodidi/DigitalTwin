// =============================================================================
// frontend/src/App.jsx
// Root application — manages all live state, WebSocket, and layout
// =============================================================================
import { useState, useCallback, useReducer, useEffect } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { useApi }       from "./hooks/useApi";
import FactoryMap       from "./components/FactoryMap";
import StatusBar        from "./components/StatusBar";
import AlertPanel       from "./components/AlertPanel";
import AssetList        from "./components/AssetList";

// ─── State reducer ─────────────────────────────────────────────────────────────
function reducer(state, action) {
  switch (action.type) {
    case "SNAPSHOT": {
      const p = action.payload;
      return {
        ...state,
        systemState: p.system_state || state.systemState,
        sensors:     p.sensors      || state.sensors,
        health:      p.health       || state.health,
        assets:      p.assets       || state.assets,
      };
    }
    case "SYSTEM_STATE":
      return { ...state, systemState: action.payload };

    case "SENSOR_UPDATE":
      return {
        ...state,
        sensors: state.sensors.map(s =>
          s.sensor_id === action.payload.sensor_id ? { ...s, ...action.payload } : s
        ),
      };

    case "HEALTH_UPDATE":
      return {
        ...state,
        health: state.health.map(h =>
          h.sensor_id === action.payload.sensor_id ? { ...h, ...action.payload } : h
        ),
      };

    case "ASSET_UPDATE": {
      const exists = state.assets.find(a => a.id === action.payload.id);
      return {
        ...state,
        assets: exists
          ? state.assets.map(a => a.id === action.payload.id ? { ...a, ...action.payload } : a)
          : [...state.assets, action.payload],
      };
    }

    case "ALERT":
      return { ...state, alerts: [action.payload, ...state.alerts].slice(0, 100) };

    case "AI_INSIGHT":
      return { ...state, aiInsights: [action.payload, ...state.aiInsights].slice(0, 50) };

    case "WS_STATUS":
      return { ...state, wsConnected: action.connected };

    default:
      return state;
  }
}

const initialState = {
  systemState:  null,
  sensors:      [],
  health:       [],
  assets:       [],
  alerts:       [],
  aiInsights:   [],
  wsConnected:  false,
};

// ─── App ───────────────────────────────────────────────────────────────────────
export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const { data: layout }  = useApi("/api/system/layout");

  const onEvent = useCallback((msg) => {
    switch (msg.event) {
      case "snapshot":     dispatch({ type: "SNAPSHOT",      payload: msg.payload }); break;
      case "system_state": dispatch({ type: "SYSTEM_STATE",  payload: msg.payload }); break;
      case "sensor_update":dispatch({ type: "SENSOR_UPDATE", payload: msg.payload }); break;
      case "health_update":dispatch({ type: "HEALTH_UPDATE", payload: msg.payload }); break;
      case "asset_update": dispatch({ type: "ASSET_UPDATE",  payload: msg.payload }); break;
      case "alert":        dispatch({ type: "ALERT",         payload: msg.payload }); break;
      case "ai_insight":   dispatch({ type: "AI_INSIGHT",    payload: msg.payload }); break;
    }
  }, []);

  useWebSocket(onEvent);

  // Clock
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div style={{
      display: "flex", flexDirection: "column", height: "100vh",
      background: "#050c1a", color: "#e2e8f0", fontFamily: "monospace",
      overflow: "hidden",
    }}>
      {/* ── Header ── */}
      <div style={{
        padding: "10px 20px", display: "flex", alignItems: "center", gap: 16,
        background: "#0d1829", borderBottom: "1px solid #1e293b",
      }}>
        <div>
          <div style={{ fontSize: 8, color: "#6366f1", letterSpacing: 3, textTransform: "uppercase" }}>
            Factory Monitoring
          </div>
          <div style={{ fontSize: 16, fontWeight: 700, color: "#e2e8f0" }}>
            Digital Twin Dashboard
          </div>
        </div>
        <div style={{ marginLeft: "auto", fontSize: 11, color: "#334155" }}>
          {time.toLocaleTimeString()}
        </div>
      </div>

      {/* ── Status bar ── */}
      <StatusBar
        systemState={state.systemState}
        wsConnected={state.wsConnected}
      />

      {/* ── Main layout ── */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* Left sidebar — asset list */}
        <div style={{ width: 220, borderRight: "1px solid #1e293b", overflowY: "auto" }}>
          <AssetList assets={state.assets} />
        </div>

        {/* Centre — factory map */}
        <div style={{ flex: 1, padding: 20, overflowY: "auto", background: "#050c1a" }}>
          <FactoryMap
            sensors={state.sensors}
            health={state.health}
            assets={state.assets}
            layout={layout}
          />

          {/* System state counters */}
          {state.systemState && (
            <div style={{
              marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap",
            }}>
              {[
                { label: "Sensors online",   val: state.systemState.sensors?.online,          col: "#4ade80" },
                { label: "Zones critical",   val: state.systemState.environment?.zones_critical, col: "#f87171" },
                { label: "Total assets",     val: state.systemState.access?.total_assets,     col: "#93c5fd" },
                { label: "Violations",       val: state.systemState.access?.violations,        col: "#f87171" },
                { label: "Unknown location", val: state.systemState.access?.unknown,           col: "#fb923c" },
              ].map(c => (
                <div key={c.label} style={{
                  padding: "8px 14px", borderRadius: 6,
                  background: "#0d1829", border: "1px solid #1e293b",
                  minWidth: 120,
                }}>
                  <div style={{ fontSize: 18, fontWeight: 700, color: c.col }}>{c.val ?? "—"}</div>
                  <div style={{ fontSize: 8, color: "#475569", marginTop: 2 }}>{c.label}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right sidebar — alerts */}
        <div style={{ width: 300, borderLeft: "1px solid #1e293b" }}>
          <AlertPanel alerts={state.alerts} aiInsights={state.aiInsights} />
        </div>
      </div>
    </div>
  );
}
