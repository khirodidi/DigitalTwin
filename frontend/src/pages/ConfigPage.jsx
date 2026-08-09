// =============================================================================
// frontend/src/pages/ConfigPage.jsx
// Four-tab configuration page:
//   Tab 1 — Factory Layout  : blueprint image, grid N×M, zone definitions
//   Tab 2 — Sensors         : coverage type + passable flag per sensor
//   Tab 3 — Workers         : add / edit workers + zone/sensor authorisations
//   Tab 4 — Trajectory      : select worker → draw path on grid
// =============================================================================

import { useState, useEffect } from "react";
import FactoryLayout  from "../components/FactoryLayout";
import SensorEditor   from "../components/SensorEditor";
import WorkerManager  from "../components/WorkerManager";
import TrajectoryMap  from "../components/TrajectoryMap";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

const TABS = [
  { id: "layout",     label: "🏭  Factory Layout"  },
  { id: "sensors",    label: "📡  Sensors"          },
  { id: "workers",    label: "👷  Workers"           },
  { id: "trajectory", label: "📍  Trajectory"        },
];

export default function ConfigPage({ onBack }) {
  const [tab,       setTab]       = useState("layout");
  const [zones,     setZones]     = useState([]);
  const [sensors,   setSensors]   = useState([]);
  const [workers,   setWorkers]   = useState([]);
  const [saving,    setSaving]    = useState(false);
  const [factory,   setFactory]   = useState({ grid_cols:6, grid_rows:5 });
  const [toast,     setToast]     = useState(null);

  // ── Load all reference data once ─────────────────────────────────────────
  useEffect(() => { reload(); }, []);

  async function reload() {
    try {
      const [z, s, w, f] = await Promise.all([
        fetch(`${API}/api/config/zones`).then(r => r.json()),
        fetch(`${API}/api/config/sensors`).then(r => r.json()),
        fetch(`${API}/api/config/workers`).then(r => r.json()),
        fetch(`${API}/api/config/factory`).then(r => r.json()),
      ]);
      if (f) setFactory(f);
      setZones(Array.isArray(z) ? z : []);
      setSensors(Array.isArray(s) ? s : []);
      setWorkers(Array.isArray(w) ? w : []);
    } catch (e) {
      showToast("Failed to load config — is the backend running?", "error");
    }
  }

  function showToast(msg, type = "ok") {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  }

  async function apiCall(url, method, body) {
    setSaving(true);
    try {
      const r = await fetch(`${API}${url}`, {
        method,
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!r.ok) throw new Error(await r.text());
      showToast("Saved successfully");
      await reload();
    } catch (e) {
      showToast(e.message || "Save failed", "error");
    } finally {
      setSaving(false);
    }
  }

  // ── Styles ────────────────────────────────────────────────────────────────
  const S = {
    page: {
      // Fixed viewport height with an internal scroll area, so the header
      // and tab bar stay visible while long content scrolls underneath.
      height: "100vh", minHeight: 0,
      display: "flex", flexDirection: "column",
      background: "#050c1a", color: "#e2e8f0",
      fontFamily: "monospace", overflow: "hidden",
    },
    header: {
      display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
      padding: "12px 24px", background: "#0d1829",
      borderBottom: "1px solid #1e293b", flexShrink: 0,
    },
    backBtn: {
      padding: "5px 14px", background: "none",
      border: "1px solid #334155", borderRadius: 6,
      color: "#94a3b8", cursor: "pointer", fontSize: 12,
      fontFamily: "monospace",
    },
    title: { fontSize: 16, fontWeight: 700 },
    tabRow: {
      display: "flex", gap: 2, padding: "0 24px",
      background: "#0d1829", borderBottom: "1px solid #1e293b",
      flexShrink: 0, overflowX: "auto", overflowY: "hidden",
    },
    tab: (active) => ({
      padding: "10px 18px", fontSize: 12, fontWeight: 600,
      whiteSpace: "nowrap", flexShrink: 0,
      border: "none", background: "none", cursor: "pointer",
      fontFamily: "monospace", color: active ? "#a5b4fc" : "#475569",
      borderBottom: active ? "2px solid #6366f1" : "2px solid transparent",
      transition: "all .15s",
    }),
    body: {
      // The only scrolling region on this page
      flex: 1, minHeight: 0,
      overflowY: "auto", overflowX: "auto",
      padding: 24, paddingBottom: 60,
    },
    toast: (type) => ({
      position: "fixed", bottom: 24, right: 24,
      padding: "10px 20px", borderRadius: 8, fontSize: 12,
      fontFamily: "monospace", fontWeight: 600, zIndex: 999,
      background: type === "error" ? "#7f1d1d" : "#052e16",
      color:      type === "error" ? "#fca5a5" : "#4ade80",
      border: `1px solid ${type === "error" ? "#ef4444" : "#16a34a"}`,
    }),
  };

  return (
    <div style={S.page}>
      {/* Header */}
      <div style={S.header}>
        <button style={S.backBtn} onClick={onBack}>← Monitor</button>
        <span style={S.title}>⚙️  Factory Configuration</span>
        {saving && <span style={{ fontSize: 11, color: "#6366f1" }}>Saving…</span>}
      </div>

      {/* Tab bar */}
      <div style={S.tabRow}>
        {TABS.map(t => (
          <button key={t.id} style={S.tab(tab === t.id)} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div style={S.body}>
        {tab === "layout"     && <FactoryLayout zones={zones} sensors={sensors} apiCall={apiCall} reload={reload} />}
        {tab === "sensors"    && <SensorEditor  sensors={sensors} zones={zones} apiCall={apiCall} />}
        {tab === "workers"    && <WorkerManager workers={workers} zones={zones}
                                                sensors={sensors} apiCall={apiCall} reload={reload} />}
        {tab === "trajectory" && <TrajectoryMap workers={workers} sensors={sensors}
                                                zones={zones}
                                                cols={factory.grid_cols}
                                                rows={factory.grid_rows} />}
      </div>

      {/* Toast */}
      {toast && <div style={S.toast(toast.type)}>{toast.msg}</div>}
    </div>
  );
}
