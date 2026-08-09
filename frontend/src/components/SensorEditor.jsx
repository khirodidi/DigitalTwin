// =============================================================================
// frontend/src/components/SensorEditor.jsx
// Tab 2 of ConfigPage:
//   For every sensor in the grid, configure:
//     - coverage_type: passage | machine | storage | exit
//     - passable: can workers walk through this cell?
//     - description: free text (e.g. "Press machine row 3", "Emergency exit A")
// =============================================================================

import { useState } from "react";

const TYPES = [
  { id: "passage", icon: "🚶", label: "Passage",  desc: "Corridor or walkway — workers pass through freely" },
  { id: "machine", icon: "⚙️",  label: "Machine",  desc: "Machinery area — workers operate near but don't cross" },
  { id: "storage", icon: "📦", label: "Storage",  desc: "Shelving or rack area" },
  { id: "exit",    icon: "🚪", label: "Exit",     desc: "Emergency exit or doorway" },
];

const TYPE_COLOR = {
  passage: "#22c55e", machine: "#f59e0b", storage: "#3b82f6", exit: "#ef4444",
};

const input = {
  background: "#0d1829", border: "1px solid #334155", borderRadius: 6,
  color: "#e2e8f0", padding: "5px 8px", fontSize: 11, fontFamily: "monospace",
  width: "100%", boxSizing: "border-box",
};
const label = { fontSize: 10, color: "#64748b", marginBottom: 3, display: "block", letterSpacing: 1 };

export default function SensorEditor({ sensors, zones, apiCall }) {
  const [edits,  setEdits]  = useState({});   // sensor_id → partial overrides
  const [filter, setFilter] = useState("all");
  const [saving, setSaving] = useState(null);

  const zoneMap = Object.fromEntries(zones.map(z => [z.zone_id, z.name]));

  function edit(sid, field, val) {
    setEdits(p => ({ ...p, [sid]: { ...p[sid], [field]: val } }));
  }

  function current(s, field) {
    return edits[s.sensor_id]?.[field] ?? s[field];
  }

  async function saveOne(s) {
    setSaving(s.sensor_id);
    const payload = {
      coverage_type: current(s, "coverage_type"),
      passable:      current(s, "passable"),
      description:   current(s, "description") || "",
    };
    await apiCall(`/api/config/sensors/${s.sensor_id}`, "PUT", payload);
    setSaving(null);
  }

  async function saveAll() {
    for (const s of sensors) {
      if (edits[s.sensor_id]) {
        await saveOne(s);
      }
    }
  }

  const displayed = filter === "all" ? sensors
    : filter === "unset" ? sensors.filter(s => !s.coverage_type || s.coverage_type === "passage" && !s.description)
    : sensors.filter(s => s.zone_id === filter);

  const GRID_COLS = parseInt(process.env.REACT_APP_GRID_COLS || "6");

  return (
    <div>
      {/* Legend */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {TYPES.map(t => (
          <div key={t.id} style={{
            padding: "4px 12px", borderRadius: 6, fontSize: 11,
            border: `1px solid ${TYPE_COLOR[t.id]}44`,
            background: TYPE_COLOR[t.id] + "18",
            color: TYPE_COLOR[t.id],
          }}>
            {t.icon} {t.label} — {t.desc}
          </div>
        ))}
      </div>

      {/* Filters */}
      <div style={{ display:"flex", gap:8, marginBottom:16, alignItems:"center",
        flexWrap:"wrap" }}>
        <span style={{ fontSize: 11, color: "#64748b" }}>Filter by zone:</span>
        {[{ zone_id:"all", name:"All" }, ...zones].map(z => (
          <button key={z.zone_id}
            onClick={() => setFilter(z.zone_id)}
            style={{
              padding: "3px 12px", fontSize: 10, borderRadius: 4,
              border: "1px solid #334155", fontFamily: "monospace",
              background: filter === z.zone_id ? "#6366f1" : "#0d1829",
              color: filter === z.zone_id ? "white" : "#94a3b8", cursor: "pointer",
            }}>
            {z.name || z.zone_id}
          </button>
        ))}
        <button onClick={saveAll} style={{
          marginLeft: "auto", padding: "4px 14px", fontSize: 11, fontWeight: 600,
          border: "1px solid #6366f1", borderRadius: 6, background: "#6366f1",
          color: "white", cursor: "pointer", fontFamily: "monospace",
        }}>
          Save all changes
        </button>
      </div>

      {/* Sensor table */}
      <div style={{ background:"#0d1829", border:"1px solid #1e293b",
        borderRadius:10, overflow:"auto", maxHeight:"calc(100vh - 300px)" }}>
        {/* Header */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "60px 100px 160px 80px 1fr 80px",
          gap: 0, padding: "8px 12px",
          background: "#0a1628", fontSize: 9, fontWeight: 700,
          color: "#475569", letterSpacing: 1,
          position:"sticky", top:0, zIndex:2,
        }}>
          <span>ID</span><span>ZONE</span><span>COVERAGE TYPE</span>
          <span>PASSABLE</span><span>DESCRIPTION</span><span></span>
        </div>

        {displayed.map((s, i) => {
          const ctype  = current(s, "coverage_type") || "passage";
          const pass   = current(s, "passable") !== false;
          const desc   = current(s, "description") || "";
          const isDirty = !!edits[s.sensor_id];
          const col    = TYPE_COLOR[ctype] || "#6b7280";
          const row    = Math.floor((parseInt(s.sensor_id?.slice(1)||"1") - 1) / GRID_COLS);
          const col_n  = (parseInt(s.sensor_id?.slice(1)||"1") - 1) % GRID_COLS;

          return (
            <div key={s.sensor_id} style={{
              display: "grid",
              gridTemplateColumns: "60px 100px 160px 80px 1fr 80px",
              gap: 0, padding: "6px 12px", alignItems: "center",
              borderTop: i > 0 ? "1px solid #0a1628" : "none",
              background: isDirty ? "#1e2a1e" : (i % 2 === 0 ? "#0d1829" : "#0a1628"),
            }}>
              {/* Sensor ID */}
              <span style={{ fontWeight: 700, color: col, fontSize: 11, fontFamily: "monospace" }}>
                {s.sensor_id}
                <div style={{ fontSize: 8, color: "#334155" }}>r{row} c{col_n}</div>
              </span>

              {/* Zone */}
              <span style={{ fontSize: 10, color: "#94a3b8" }}>
                {zoneMap[s.zone_id] || s.zone_id || "—"}
              </span>

              {/* Coverage type selector */}
              <select value={ctype}
                onChange={e => edit(s.sensor_id, "coverage_type", e.target.value)}
                style={{ ...input, padding: "4px 6px" }}>
                {TYPES.map(t => (
                  <option key={t.id} value={t.id}>{t.icon} {t.label}</option>
                ))}
              </select>

              {/* Passable toggle */}
              <div style={{ textAlign: "center" }}>
                <label style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
                  <input type="checkbox" checked={pass}
                    onChange={e => edit(s.sensor_id, "passable", e.target.checked)} />
                  <span style={{ fontSize: 10, color: pass ? "#4ade80" : "#f87171" }}>
                    {pass ? "Yes" : "No"}
                  </span>
                </label>
              </div>

              {/* Description */}
              <input style={{ ...input, fontSize: 10 }}
                placeholder={`e.g. Press machine A, Emergency exit north`}
                value={desc}
                onChange={e => edit(s.sensor_id, "description", e.target.value)} />

              {/* Save button */}
              <button
                onClick={() => saveOne(s)}
                disabled={!isDirty || saving === s.sensor_id}
                style={{
                  padding: "3px 10px", fontSize: 10, borderRadius: 4, cursor: "pointer",
                  fontFamily: "monospace", fontWeight: 600,
                  border: `1px solid ${isDirty ? "#6366f1" : "#1e293b"}`,
                  background: isDirty ? "#6366f122" : "#0a1628",
                  color: isDirty ? "#a5b4fc" : "#334155",
                }}>
                {saving === s.sensor_id ? "…" : "Save"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
