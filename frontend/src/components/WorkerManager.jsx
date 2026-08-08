// =============================================================================
// frontend/src/components/WorkerManager.jsx
// Tab 3 of ConfigPage:
//   - Table of all workers / forklifts / pallets
//   - Add / edit / delete assets
//   - Per-asset authorization editor: tick zones and individual sensors
// =============================================================================

import { useState } from "react";

const TYPES = ["worker","forklift","pallet"];
const TYPE_ICON = { worker:"👷", forklift:"🚜", pallet:"📦" };

const input = {
  background:"#0d1829", border:"1px solid #334155", borderRadius:6,
  color:"#e2e8f0", padding:"6px 10px", fontSize:12, fontFamily:"monospace",
  boxSizing:"border-box",
};
const btn = (col="#6366f1",sm=false) => ({
  padding: sm ? "3px 10px" : "6px 14px",
  fontSize: sm ? 10 : 12, fontWeight:600, fontFamily:"monospace",
  border:`1px solid ${col}`, borderRadius:6,
  background:`${col}22`, color:col, cursor:"pointer",
});
const labelS = { fontSize:10, color:"#64748b", marginBottom:3, display:"block", letterSpacing:1 };

const ZONE_COLORS = ["#14b8a6","#3b82f6","#8b5cf6","#f59e0b","#ec4899","#ef4444","#22c55e","#f97316"];

export default function WorkerManager({ workers, zones, sensors, apiCall, reload }) {
  const [form,      setForm]    = useState({ asset_id:"", asset_type:"worker", name:"" });
  const [editing,   setEditing] = useState(null);   // asset_id being auth-edited
  const [auth,      setAuth]    = useState({ allowed_zones:[], allowed_sensors:[] });
  const [showForm,  setShowForm]= useState(false);
  const [filterType,setFT]      = useState("all");

  const shown = filterType === "all" ? workers : workers.filter(w => w.asset_type === filterType);

  // ── Add / update worker ────────────────────────────────────────────────────
  async function saveWorker() {
    if (!form.asset_id.trim() || !form.name.trim()) return;
    await apiCall("/api/config/workers", "POST", form);
    setForm({ asset_id:"", asset_type:"worker", name:"" });
    setShowForm(false);
  }

  async function deleteWorker(id) {
    if (!window.confirm(`Delete ${id}? This also removes all their authorisations.`)) return;
    await apiCall(`/api/config/workers/${id}`, "DELETE");
  }

  // ── Open auth editor for a worker ─────────────────────────────────────────
  function openAuth(w) {
    const auths = w.authorisations || [];
    setAuth({
      allowed_zones:   auths.filter(a => a.type === "zone").map(a => a.id),
      allowed_sensors: auths.filter(a => a.type === "sensor").map(a => a.id),
    });
    setEditing(w.asset_id);
  }

  function toggleZone(zid) {
    setAuth(p => ({
      ...p,
      allowed_zones: p.allowed_zones.includes(zid)
        ? p.allowed_zones.filter(z => z !== zid)
        : [...p.allowed_zones, zid],
    }));
  }

  function toggleSensor(sid) {
    setAuth(p => ({
      ...p,
      allowed_sensors: p.allowed_sensors.includes(sid)
        ? p.allowed_sensors.filter(s => s !== sid)
        : [...p.allowed_sensors, sid],
    }));
  }

  async function saveAuth() {
    await apiCall(`/api/config/workers/${editing}/authorisations`, "PUT", auth);
    setEditing(null);
  }

  function authorisationSummary(w) {
    const auths = w.authorisations || [];
    const zones   = auths.filter(a => a.type === "zone").map(a => a.id);
    const sensorL = auths.filter(a => a.type === "sensor").map(a => a.id);
    if (!zones.length && !sensorL.length) return <span style={{color:"#475569",fontSize:10}}>no access</span>;
    return (
      <span style={{fontSize:10}}>
        {zones.map(z => <span key={z} style={{
          marginRight:4, padding:"1px 6px", borderRadius:3,
          background:"#6366f122", color:"#a5b4fc", border:"1px solid #6366f144"
        }}>{z}</span>)}
        {sensorL.map(s => <span key={s} style={{
          marginRight:4, padding:"1px 6px", borderRadius:3,
          background:"#14b8a622", color:"#5eead4", border:"1px solid #14b8a644"
        }}>{s}</span>)}
      </span>
    );
  }

  return (
    <div>
      {/* Controls */}
      <div style={{ display:"flex", gap:10, marginBottom:16, alignItems:"center" }}>
        <div style={{ display:"flex", gap:4 }}>
          {["all","worker","forklift","pallet"].map(t => (
            <button key={t} onClick={() => setFT(t)} style={{
              ...btn(filterType===t ? "#6366f1" : "#334155", true),
              background: filterType===t ? "#6366f133" : "transparent",
            }}>
              {t==="all" ? "All" : `${TYPE_ICON[t]} ${t}s`}
            </button>
          ))}
        </div>
        <button style={{ ...btn("#22c55e"), marginLeft:"auto" }}
          onClick={() => setShowForm(p => !p)}>
          {showForm ? "✕ Cancel" : "+ Add asset"}
        </button>
      </div>

      {/* Add form */}
      {showForm && (
        <div style={{
          background:"#0d1829", border:"1px solid #334155", borderRadius:10,
          padding:16, marginBottom:16,
        }}>
          <div style={{ fontSize:12, fontWeight:700, color:"#22c55e", marginBottom:12 }}>
            New asset
          </div>
          <div style={{ display:"grid", gridTemplateColumns:"120px 130px 1fr auto", gap:10 }}>
            <div>
              <span style={labelS}>ID (matches tag)</span>
              <input style={{ ...input, width:"100%" }}
                placeholder="W06"
                value={form.asset_id}
                onChange={e => setForm(p => ({ ...p, asset_id: e.target.value.trim() }))} />
            </div>
            <div>
              <span style={labelS}>TYPE</span>
              <select style={{ ...input, width:"100%" }} value={form.asset_type}
                onChange={e => setForm(p => ({ ...p, asset_type: e.target.value }))}>
                {TYPES.map(t => <option key={t} value={t}>{TYPE_ICON[t]} {t}</option>)}
              </select>
            </div>
            <div>
              <span style={labelS}>NAME / DESCRIPTION</span>
              <input style={{ ...input, width:"100%" }}
                placeholder="Fatima Hassan"
                value={form.name}
                onChange={e => setForm(p => ({ ...p, name: e.target.value }))} />
            </div>
            <div style={{ paddingTop:18 }}>
              <button style={btn("#22c55e")} onClick={saveWorker}>Add</button>
            </div>
          </div>
        </div>
      )}

      {/* Worker table */}
      <div style={{ background:"#0d1829", border:"1px solid #1e293b", borderRadius:10, overflow:"hidden" }}>
        {/* Header */}
        <div style={{
          display:"grid", gridTemplateColumns:"80px 110px 1fr 1fr 120px",
          padding:"8px 16px", background:"#0a1628",
          fontSize:9, fontWeight:700, color:"#475569", letterSpacing:1,
        }}>
          <span>ID</span><span>TYPE</span><span>NAME</span>
          <span>AUTHORISED FOR</span><span>ACTIONS</span>
        </div>

        {shown.length === 0 && (
          <div style={{ padding:24, textAlign:"center", color:"#334155", fontSize:12 }}>
            No assets yet — add one above
          </div>
        )}

        {shown.map((w, i) => (
          <div key={w.asset_id}>
            <div style={{
              display:"grid", gridTemplateColumns:"80px 110px 1fr 1fr 120px",
              padding:"8px 16px", alignItems:"center",
              borderTop: i > 0 ? "1px solid #0a1628" : "none",
              background: editing === w.asset_id ? "#1a1a2e" : (i%2===0 ? "#0d1829" : "#0a1628"),
            }}>
              <span style={{ fontWeight:700, color:"#e2e8f0", fontSize:12 }}>{w.asset_id}</span>
              <span style={{ fontSize:11, color:"#94a3b8" }}>
                {TYPE_ICON[w.asset_type]} {w.asset_type}
              </span>
              <span style={{ fontSize:12, color:"#e2e8f0" }}>{w.name}</span>
              <div>{authorisationSummary(w)}</div>
              <div style={{ display:"flex", gap:6 }}>
                <button style={btn("#6366f1",true)}
                  onClick={() => editing === w.asset_id ? setEditing(null) : openAuth(w)}>
                  {editing === w.asset_id ? "Close" : "Auth"}
                </button>
                <button style={btn("#ef4444",true)}
                  onClick={() => deleteWorker(w.asset_id)}>Del</button>
              </div>
            </div>

            {/* Authorisation editor — inline expand */}
            {editing === w.asset_id && (
              <div style={{
                padding:16, background:"#0f172a",
                borderTop:"1px solid #1e293b",
              }}>
                <div style={{ fontSize:11, fontWeight:700, color:"#a5b4fc", marginBottom:12 }}>
                  Authorisations for {w.asset_id} — {w.name}
                </div>

                {/* Zone access */}
                <div style={{ marginBottom:14 }}>
                  <div style={{ fontSize:10, color:"#64748b", marginBottom:6, letterSpacing:1 }}>
                    ZONES (coarse — all sensors in zone)
                  </div>
                  <div style={{ display:"flex", flexWrap:"wrap", gap:8 }}>
                    {zones.map((z, idx) => {
                      const active = auth.allowed_zones.includes(z.zone_id);
                      const col    = ZONE_COLORS[idx % ZONE_COLORS.length];
                      return (
                        <button key={z.zone_id} onClick={() => toggleZone(z.zone_id)}
                          style={{
                            padding:"5px 14px", fontSize:11, borderRadius:6, cursor:"pointer",
                            fontFamily:"monospace", fontWeight:600,
                            border:`1px solid ${active ? col : "#334155"}`,
                            background: active ? col+"33" : "#0d1829",
                            color: active ? col : "#475569",
                          }}>
                          {active ? "✓ " : ""}{z.zone_id} — {z.name}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Sensor-level access */}
                <div style={{ marginBottom:14 }}>
                  <div style={{ fontSize:10, color:"#64748b", marginBottom:6, letterSpacing:1 }}>
                    SPECIFIC SENSORS (fine — overrides zone restriction for one cell)
                  </div>
                  <div style={{ display:"flex", flexWrap:"wrap", gap:6 }}>
                    {sensors.map(s => {
                      const active = auth.allowed_sensors.includes(s.sensor_id);
                      return (
                        <button key={s.sensor_id} onClick={() => toggleSensor(s.sensor_id)}
                          style={{
                            padding:"3px 10px", fontSize:10, borderRadius:4, cursor:"pointer",
                            fontFamily:"monospace", fontWeight:600,
                            border:`1px solid ${active ? "#14b8a6" : "#1e293b"}`,
                            background: active ? "#14b8a622" : "#0a1628",
                            color: active ? "#5eead4" : "#334155",
                          }}>
                          {s.sensor_id}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Summary & save */}
                <div style={{
                  padding:"8px 12px", background:"#050c1a", borderRadius:6,
                  fontSize:10, color:"#64748b", marginBottom:12,
                }}>
                  {auth.allowed_zones.length === 0 && auth.allowed_sensors.length === 0
                    ? "⚠ No access granted — every location will show as VIOLATION"
                    : `✓ Access to ${auth.allowed_zones.length} zone(s) and ${auth.allowed_sensors.length} specific sensor(s)`}
                </div>

                <div style={{ display:"flex", gap:8 }}>
                  <button style={btn()} onClick={saveAuth}>Save authorisations</button>
                  <button style={btn("#6b7280")} onClick={() => setEditing(null)}>Cancel</button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Help */}
      <div style={{ marginTop:16, padding:"10px 14px", background:"#0d1829",
        border:"1px solid #1e293b", borderRadius:8, fontSize:10, color:"#475569",
        lineHeight:1.7 }}>
        <strong style={{color:"#94a3b8"}}>How authorisations work:</strong><br/>
        Zone access = worker can go anywhere inside that zone.<br/>
        Sensor access = worker can be at that one specific grid cell (overrides zone restriction).<br/>
        No access anywhere = every location shows as <span style={{color:"#f87171"}}>VIOLATION</span>.<br/>
        Sensor offline = status becomes <span style={{color:"#fbbf24"}}>UNKNOWN</span> (no false alarm).
      </div>
    </div>
  );
}
