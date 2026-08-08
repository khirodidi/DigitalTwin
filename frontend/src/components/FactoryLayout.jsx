// =============================================================================
// frontend/src/components/FactoryLayout.jsx
// Tab 1 of ConfigPage:
//   - Factory name and blueprint image filename
//   - Grid columns / rows
//   - Zone list: add / rename / delete, assign sensors to zones
// =============================================================================

import { useState, useEffect } from "react";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

const COVERAGE_COLORS = {
  zone_A: "#14b8a6", zone_B: "#3b82f6", zone_C: "#8b5cf6",
  zone_D: "#f59e0b", zone_E: "#ec4899",
};
function zoneColor(zid, idx) {
  const palette = ["#14b8a6","#3b82f6","#8b5cf6","#f59e0b","#ec4899","#ef4444","#22c55e","#f97316"];
  return COVERAGE_COLORS[zid] || palette[idx % palette.length];
}

const input = {
  background: "#0d1829", border: "1px solid #334155", borderRadius: 6,
  color: "#e2e8f0", padding: "6px 10px", fontSize: 12, fontFamily: "monospace",
  width: "100%", boxSizing: "border-box",
};
const btn = (col = "#6366f1") => ({
  padding: "6px 14px", fontSize: 11, fontWeight: 600,
  border: `1px solid ${col}`, borderRadius: 6,
  background: col + "22", color: col, cursor: "pointer",
  fontFamily: "monospace",
});
const label = { fontSize: 10, color: "#64748b", marginBottom: 4, display: "block", letterSpacing: 1 };
const card = { background: "#0d1829", border: "1px solid #1e293b", borderRadius: 10, padding: 16, marginBottom: 12 };

export default function FactoryLayout({ zones, sensors, apiCall }) {
  const [cfg,        setCfg]       = useState({ factory_name:"", blueprint_url:"", grid_cols:6, grid_rows:5 });
  const [newZone,    setNewZone]   = useState({ zone_id:"", name:"", description:"" });
  const [editZone,   setEditZone]  = useState(null);  // zone_id being edited
  const [zoneSensors,setZS]        = useState({});    // zone_id → selected sensor_ids (edit mode)

  useEffect(() => {
    fetch(`${API}/api/config/factory`).then(r => r.json()).then(d => {
      setCfg({
        factory_name:  d.factory_name  || "",
        blueprint_url: d.blueprint_url || "",
        grid_cols:     parseInt(d.grid_cols || "6"),
        grid_rows:     parseInt(d.grid_rows || "5"),
      });
    }).catch(() => {});
  }, []);

  function saveFactory() {
    apiCall("/api/config/factory", "PUT", cfg);
  }

  function saveZone(z) {
    const sensor_ids = zoneSensors[z.zone_id] || z.sensor_ids || [];
    apiCall("/api/config/zones", "POST", { ...z, sensor_ids });
    setEditZone(null);
  }

  function deleteZone(zone_id) {
    if (!window.confirm(`Delete zone ${zone_id}? Sensors will become unassigned.`)) return;
    apiCall(`/api/config/zones/${zone_id}`, "DELETE");
  }

  function addZone() {
    if (!newZone.zone_id || !newZone.name) return;
    apiCall("/api/config/zones", "POST", { ...newZone, sensor_ids: [] });
    setNewZone({ zone_id:"", name:"", description:"" });
  }

  function startEdit(z) {
    setEditZone(z.zone_id);
    setZS(prev => ({ ...prev, [z.zone_id]: z.sensor_ids || [] }));
  }

  function toggleSensor(zone_id, sid) {
    setZS(prev => {
      const cur = prev[zone_id] || [];
      return { ...prev, [zone_id]: cur.includes(sid) ? cur.filter(s => s !== sid) : [...cur, sid] };
    });
  }

  const unassignedSensors = sensors.filter(s => !s.zone_id);

  return (
    <div>
      {/* ── Factory global config ── */}
      <div style={card}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#a5b4fc", marginBottom: 12 }}>
          Factory Settings
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 80px 80px", gap: 12, marginBottom: 12 }}>
          <div>
            <span style={label}>FACTORY NAME</span>
            <input style={input} value={cfg.factory_name}
              onChange={e => setCfg(p => ({ ...p, factory_name: e.target.value }))} />
          </div>
          <div>
            <span style={label}>BLUEPRINT IMAGE (filename in public/)</span>
            <input style={input} placeholder="factory.png" value={cfg.blueprint_url}
              onChange={e => setCfg(p => ({ ...p, blueprint_url: e.target.value }))} />
          </div>
          <div>
            <span style={label}>COLUMNS</span>
            <input style={input} type="number" min={1} max={20} value={cfg.grid_cols}
              onChange={e => setCfg(p => ({ ...p, grid_cols: parseInt(e.target.value) }))} />
          </div>
          <div>
            <span style={label}>ROWS</span>
            <input style={input} type="number" min={1} max={20} value={cfg.grid_rows}
              onChange={e => setCfg(p => ({ ...p, grid_rows: parseInt(e.target.value) }))} />
          </div>
        </div>
        <div style={{ fontSize: 10, color: "#475569", marginBottom: 10 }}>
          Place the blueprint image in <code style={{ color: "#a5b4fc" }}>frontend/public/</code> then
          enter its filename above. Grid changes take effect after rebuilding the frontend container.
        </div>
        <button style={btn()} onClick={saveFactory}>Save factory settings</button>
      </div>

      {/* ── Zone list ── */}
      <div style={card}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#a5b4fc", marginBottom: 12 }}>
          Zones
          {unassignedSensors.length > 0 && (
            <span style={{ marginLeft: 10, fontSize: 10, color: "#f59e0b" }}>
              ⚠ {unassignedSensors.length} sensor(s) not assigned to any zone
            </span>
          )}
        </div>

        {zones.map((z, idx) => (
          <div key={z.zone_id} style={{
            border: `1px solid ${zoneColor(z.zone_id, idx)}44`,
            borderLeft: `4px solid ${zoneColor(z.zone_id, idx)}`,
            borderRadius: 8, padding: 12, marginBottom: 10,
            background: "#050c1a",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <span style={{ fontWeight: 700, color: zoneColor(z.zone_id, idx), fontSize: 12 }}>
                {z.zone_id}
              </span>
              <span style={{ color: "#e2e8f0", fontSize: 12 }}>{z.name}</span>
              <span style={{ color: "#475569", fontSize: 11, flex: 1 }}>{z.description}</span>
              <span style={{ fontSize: 10, color: "#64748b" }}>
                {(z.sensor_ids || []).length} sensors
              </span>
              <button style={btn("#6366f1")} onClick={() => startEdit(z)}>Edit</button>
              <button style={btn("#ef4444")} onClick={() => deleteZone(z.zone_id)}>Delete</button>
            </div>

            {/* Sensor assignment editor */}
            {editZone === z.zone_id && (
              <div style={{ marginTop: 10 }}>
                <div style={{ fontSize: 10, color: "#64748b", marginBottom: 6, letterSpacing: 1 }}>
                  SELECT SENSORS IN THIS ZONE — click to toggle
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
                  {sensors.map(s => {
                    const selected = (zoneSensors[z.zone_id] || []).includes(s.sensor_id);
                    return (
                      <button key={s.sensor_id}
                        onClick={() => toggleSensor(z.zone_id, s.sensor_id)}
                        style={{
                          padding: "3px 10px", fontSize: 10, borderRadius: 4, cursor: "pointer",
                          fontFamily: "monospace", fontWeight: 600,
                          border: `1px solid ${selected ? zoneColor(z.zone_id, idx) : "#334155"}`,
                          background: selected ? zoneColor(z.zone_id, idx) + "33" : "#0d1829",
                          color: selected ? zoneColor(z.zone_id, idx) : "#64748b",
                        }}>
                        {s.sensor_id}
                      </button>
                    );
                  })}
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button style={btn()} onClick={() => saveZone(z)}>Save zone</button>
                  <button style={btn("#6b7280")} onClick={() => setEditZone(null)}>Cancel</button>
                </div>
              </div>
            )}

            {/* Sensor chips when not editing */}
            {editZone !== z.zone_id && (z.sensor_ids || []).length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {z.sensor_ids.map(sid => (
                  <span key={sid} style={{
                    padding: "1px 8px", fontSize: 9, borderRadius: 3,
                    background: zoneColor(z.zone_id, idx) + "22",
                    color: zoneColor(z.zone_id, idx),
                    border: `1px solid ${zoneColor(z.zone_id, idx)}44`,
                  }}>{sid}</span>
                ))}
              </div>
            )}
          </div>
        ))}

        {/* Add new zone */}
        <div style={{ borderTop: "1px solid #1e293b", paddingTop: 12, marginTop: 4 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#64748b", marginBottom: 10 }}>
            ADD NEW ZONE
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "120px 1fr 1fr auto", gap: 10 }}>
            <div>
              <span style={label}>ZONE ID</span>
              <input style={input} placeholder="zone_F" value={newZone.zone_id}
                onChange={e => setNewZone(p => ({ ...p, zone_id: e.target.value.replace(/\s/g, "_") }))} />
            </div>
            <div>
              <span style={label}>NAME</span>
              <input style={input} placeholder="Maintenance" value={newZone.name}
                onChange={e => setNewZone(p => ({ ...p, name: e.target.value }))} />
            </div>
            <div>
              <span style={label}>DESCRIPTION</span>
              <input style={input} placeholder="Tool store and workshop" value={newZone.description}
                onChange={e => setNewZone(p => ({ ...p, description: e.target.value }))} />
            </div>
            <div style={{ paddingTop: 18 }}>
              <button style={btn("#22c55e")} onClick={addZone}>+ Add zone</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
