// =============================================================================
// WorkerManager.jsx — Configuration Tab 3
//   • Add / edit / delete assets (shown by NAME, id secondary)
//   • ZONE authorisation list  — tick the zones the asset may enter
//   • SENSOR authorisation list — tick individual cells
//   • DEFAULT TRAJECTORY       — ordered sensors the asset works at
//   • "Authorise all" rescue button to clear a violation storm
// =============================================================================

import { useState } from "react";
import SensorGridPicker from "./SensorGridPicker";

const API   = process.env.REACT_APP_API_URL || "http://localhost:8000";
const TYPES = ["worker", "forklift", "pallet"];
const ICON  = { worker: "👷", forklift: "🚜", pallet: "📦" };
const PALETTE = ["#14b8a6","#3b82f6","#8b5cf6","#f59e0b",
                 "#ec4899","#ef4444","#22c55e","#f97316"];

const input = { background:"#0d1829", border:"1px solid #334155", borderRadius:6,
  color:"#e2e8f0", padding:"7px 10px", fontSize:12, fontFamily:"monospace",
  width:"100%", boxSizing:"border-box" };
const btn = (c="#6366f1", sm=false) => ({
  padding: sm?"4px 10px":"7px 15px", fontSize: sm?10:11, fontWeight:600,
  border:`1px solid ${c}`, borderRadius:6, background:`${c}22`, color:c,
  cursor:"pointer", fontFamily:"monospace", whiteSpace:"nowrap" });
const lbl = { fontSize:10, color:"#64748b", marginBottom:4, display:"block", letterSpacing:1 };

export default function WorkerManager({ workers, zones, sensors, apiCall, reload,
                                        cols = 6, rows = 5, blueprintUrl = "" }) {
  const [form,     setForm]     = useState({ asset_id:"", asset_type:"worker", name:"" });
  const [showForm, setShowForm] = useState(false);
  const [openId,   setOpenId]   = useState(null);
  const [auth,     setAuth]     = useState({ allowed_zones:[], allowed_sensors:[] });
  const [traj,     setTraj]     = useState([]);
  const [filter,   setFilter]   = useState("all");

  const cols = Math.max(...sensors.map(s => (s.grid_col ?? 0) + 1), 1);
  const zoneColor = zid => PALETTE[Math.max(0, zones.findIndex(z=>z.zone_id===zid)) % PALETTE.length];
  const sensorZone = {};
  zones.forEach(z => (z.sensor_ids||[]).forEach(s => { sensorZone[s] = z.zone_id; }));

  const shown = filter === "all" ? workers : workers.filter(w => w.asset_type === filter);
  const noAuth = workers.filter(w => !(w.authorisations||[]).length);

  // ── Open the editor for one asset ────────────────────────────────────────
  function open(w) {
    const a = w.authorisations || [];
    setAuth({
      allowed_zones:   a.filter(x => x.type === "zone").map(x => x.id),
      allowed_sensors: a.filter(x => x.type === "sensor").map(x => x.id),
    });
    setTraj(Array.isArray(w.default_trajectory) ? [...w.default_trajectory] : []);
    setOpenId(w.asset_id);
  }

  const toggleZone   = z => setAuth(p => ({ ...p,
    allowed_zones: p.allowed_zones.includes(z)
      ? p.allowed_zones.filter(x=>x!==z) : [...p.allowed_zones, z] }));
  const toggleSensor = s => setAuth(p => ({ ...p,
    allowed_sensors: p.allowed_sensors.includes(s)
      ? p.allowed_sensors.filter(x=>x!==s) : [...p.allowed_sensors, s] }));

  // Trajectory is ORDERED — clicking appends, clicking again removes
  const toggleTraj = s => setTraj(p =>
    p.includes(s) ? p.filter(x=>x!==s) : [...p, s]);

  // A zone authorisation covers EVERY sensor in that zone. Compute the
  // implied set live so the operator sees the real coverage while editing.
  const impliedSensors = (() => {
    const out = new Set();
    auth.allowed_zones.forEach(zid => {
      const z = zones.find(x => x.zone_id === zid);
      (z?.sensor_ids || []).forEach(sid => out.add(sid));
    });
    return [...out];
  })();

  async function saveAuth(w) {
    await apiCall(`/api/config/workers/${w.asset_id}/authorisations`, "PUT", auth);
    await apiCall(`/api/config/workers/${w.asset_id}`, "PUT", {
      asset_id: w.asset_id, asset_type: w.asset_type, name: w.name,
      default_trajectory: traj,
    });
    setOpenId(null);
  }

  async function saveWorker() {
    if (!form.asset_id.trim() || !form.name.trim()) return;
    await apiCall("/api/config/workers", "POST", { ...form, default_trajectory: [] });
    setForm({ asset_id:"", asset_type:"worker", name:"" });
    setShowForm(false);
  }

  async function delWorker(w) {
    if (!window.confirm(`Delete ${w.name} (${w.asset_id})?`)) return;
    await apiCall(`/api/config/workers/${w.asset_id}`, "DELETE");
  }

  async function authoriseAll() {
    if (!zones.length) { alert("Define zones first in the Factory Layout tab."); return; }
    if (!window.confirm(
      `Grant every asset access to all ${zones.length} zones?\n\n` +
      `This clears access-violation alerts caused by assets that have no ` +
      `authorisations. You can then restrict individuals as needed.`)) return;
    await apiCall("/api/config/workers/bulk-authorise", "POST", {
      asset_ids: "all", allowed_zones: zones.map(z=>z.zone_id),
      allowed_sensors: [], mode: "replace",
    });
  }

  return (
    <div>
      {/* ── Violation warning banner ── */}
      {noAuth.length > 0 && (
        <div style={{ padding:"12px 16px", marginBottom:14, borderRadius:8,
          background:"#7f1d1d33", border:"1px solid #ef4444",
          display:"flex", alignItems:"center", gap:14, flexWrap:"wrap" }}>
          <span style={{ fontSize:18 }}>⚠</span>
          <div style={{ flex:1, minWidth:220 }}>
            <div style={{ fontSize:12, fontWeight:700, color:"#fca5a5" }}>
              {noAuth.length} asset(s) have no authorisations
            </div>
            <div style={{ fontSize:10, color:"#94a3b8", marginTop:2 }}>
              Every location they report counts as a VIOLATION, which forces the
              system status to CRITICAL. Grant zone access below, or use the
              rescue button.
            </div>
          </div>
          <button style={btn("#22c55e")} onClick={authoriseAll}>
            Authorise all assets for all zones
          </button>
        </div>
      )}

      {/* ── Controls ── */}
      <div style={{ display:"flex", gap:8, marginBottom:14,
        alignItems:"center", flexWrap:"wrap" }}>
        {["all","worker","forklift","pallet"].map(t => (
          <button key={t} onClick={() => setFilter(t)}
            style={{ ...btn(filter===t ? "#6366f1" : "#334155", true),
                     background: filter===t ? "#6366f133" : "transparent" }}>
            {t === "all" ? "All" : `${ICON[t]} ${t}s`}
          </button>
        ))}
        <button style={{ ...btn("#22c55e"), marginLeft:"auto" }}
          onClick={() => setShowForm(p=>!p)}>
          {showForm ? "✕ Cancel" : "+ Add asset"}
        </button>
      </div>

      {/* ── Add form ── */}
      {showForm && (
        <div style={{ background:"#0d1829", border:"1px solid #334155",
          borderRadius:10, padding:16, marginBottom:14 }}>
          <div style={{ display:"grid",
            gridTemplateColumns:"120px 140px 1fr auto", gap:10, alignItems:"end" }}>
            <div><span style={lbl}>TAG ID</span>
              <input style={input} placeholder="W06" value={form.asset_id}
                onChange={e=>setForm(p=>({...p, asset_id:e.target.value.trim()}))} /></div>
            <div><span style={lbl}>TYPE</span>
              <select style={input} value={form.asset_type}
                onChange={e=>setForm(p=>({...p, asset_type:e.target.value}))}>
                {TYPES.map(t=><option key={t} value={t}>{ICON[t]} {t}</option>)}
              </select></div>
            <div><span style={lbl}>NAME</span>
              <input style={input} placeholder="Fatima Hassan" value={form.name}
                onChange={e=>setForm(p=>({...p, name:e.target.value}))} /></div>
            <button style={btn("#22c55e")} onClick={saveWorker}>Add</button>
          </div>
        </div>
      )}

      {/* ── Asset list ── */}
      {shown.map(w => {
        const a       = w.authorisations || [];
        const zoneIds = a.filter(x=>x.type==="zone").map(x=>x.id);
        const sensIds = a.filter(x=>x.type==="sensor").map(x=>x.id);
        const tr      = Array.isArray(w.default_trajectory) ? w.default_trajectory : [];
        const isOpen  = openId === w.asset_id;
        const none    = !zoneIds.length && !sensIds.length;

        return (
          <div key={w.asset_id} style={{
            background:"#0d1829", borderRadius:10, marginBottom:10,
            border:`1px solid ${isOpen ? "#6366f1" : none ? "#ef444455" : "#1e293b"}` }}>

            {/* Row header — NAME first */}
            <div style={{ display:"flex", alignItems:"center", gap:12,
              padding:"12px 16px", flexWrap:"wrap" }}>
              <span style={{ fontSize:20 }}>{ICON[w.asset_type] || "📍"}</span>
              <div style={{ minWidth:150 }}>
                <div style={{ fontSize:13, fontWeight:700, color:"#e2e8f0" }}>
                  {w.name}
                </div>
                <div style={{ fontSize:9, color:"#475569" }}>
                  {w.asset_id} · {w.asset_type}
                </div>
              </div>

              <div style={{ flex:1, minWidth:180, display:"flex",
                gap:4, flexWrap:"wrap" }}>
                {none ? (
                  <span style={{ fontSize:10, color:"#f87171" }}>
                    ⚠ no access — always violation
                  </span>
                ) : (
                  <>
                    {zoneIds.map(z => (
                      <span key={z} style={{ fontSize:9, padding:"2px 7px",
                        borderRadius:3, background:zoneColor(z)+"22",
                        color:zoneColor(z), border:`1px solid ${zoneColor(z)}55` }}>
                        {zones.find(x=>x.zone_id===z)?.name || z}
                      </span>
                    ))}
                    {sensIds.map(s => (
                      <span key={s} style={{ fontSize:9, padding:"2px 6px",
                        borderRadius:3, background:"#14b8a622",
                        color:"#5eead4", border:"1px solid #14b8a655" }}>{s}</span>
                    ))}
                  </>
                )}
              </div>

              <span style={{ fontSize:10,
                color: w.trajectory_source === "learned" ? "#c4b5fd"
                     : tr.length ? "#a5b4fc" : "#334155" }}>
                🧭 {tr.length ? `${tr.length} waypoints` : "no trajectory"}
                {w.trajectory_source === "learned" && " · AI"}
              </span>

              <button style={btn(isOpen ? "#6b7280" : "#6366f1", true)}
                onClick={() => isOpen ? setOpenId(null) : open(w)}>
                {isOpen ? "Close" : "Configure"}
              </button>
              <button style={btn("#ef4444", true)} onClick={() => delWorker(w)}>Delete</button>
            </div>

            {/* ── Editor ── */}
            {isOpen && (
              <div style={{ padding:"0 16px 16px", borderTop:"1px solid #1e293b" }}>

                {/* ZONE AUTHORISATIONS */}
                <div style={{ marginTop:14 }}>
                  <div style={{ ...lbl, color:"#a5b4fc", fontWeight:700 }}>
                    1 · ZONE AUTHORISATIONS — the asset may enter these zones
                  </div>
                  {zones.length === 0 ? (
                    <div style={{ fontSize:11, color:"#f59e0b" }}>
                      No zones defined yet — create them in the Factory Layout tab.
                    </div>
                  ) : (
                    <div style={{ display:"flex", flexWrap:"wrap", gap:7 }}>
                      {zones.map(z => {
                        const on = auth.allowed_zones.includes(z.zone_id);
                        const c  = zoneColor(z.zone_id);
                        return (
                          <button key={z.zone_id} onClick={()=>toggleZone(z.zone_id)}
                            style={{ padding:"7px 14px", fontSize:11, borderRadius:6,
                              cursor:"pointer", fontFamily:"monospace", fontWeight:600,
                              border:`1px solid ${on ? c : "#334155"}`,
                              background: on ? c+"33" : "#0a1628",
                              color: on ? c : "#475569" }}>
                            {on ? "✓ " : ""}{z.name}
                            <span style={{ opacity:0.6, marginLeft:5, fontSize:9 }}>
                              {(z.sensor_ids||[]).length} sensors
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* SENSOR AUTHORISATIONS */}
                <div style={{ marginTop:16 }}>
                  <div style={{ ...lbl, color:"#5eead4", fontWeight:700 }}>
                    2 · SENSOR AUTHORISATIONS — extra individual cells
                    <span style={{ color:"#475569", fontWeight:400, letterSpacing:0 }}>
                      {" "}(optional — {auth.allowed_sensors.length} extra
                      {impliedSensors.length > 0 &&
                        `, ${impliedSensors.length} already covered by the zones above`})
                    </span>
                  </div>
                  <SensorGridPicker
                    sensors={sensors} zones={zones} cols={cols} rows={rows}
                    blueprintUrl={blueprintUrl}
                    selected={auth.allowed_sensors}
                    implied={impliedSensors}
                    onToggle={toggleSensor}
                    mode="select" accent="#14b8a6" />
                </div>

                {/* DEFAULT TRAJECTORY */}
                <div style={{ marginTop:16 }}>
                  <div style={{ ...lbl, color:"#f59e0b", fontWeight:700 }}>
                    3 · TRAJECTORY — initial route, refined by AI over time
                    <span style={{ color:"#475569", fontWeight:400, letterSpacing:0 }}>
                      {" "}(click cells in visiting order)
                    </span>
                    {w.trajectory_source === "learned" && (
                      <span style={{ marginLeft:8, padding:"1px 7px", fontSize:9,
                        borderRadius:3, background:"#7c3aed33", color:"#c4b5fd",
                        border:"1px solid #7c3aed" }}>
                        AI-learned v{w.trajectory_version}
                      </span>
                    )}
                  </div>
                  <SensorGridPicker
                    sensors={sensors} zones={zones} cols={cols} rows={rows}
                    blueprintUrl={blueprintUrl}
                    selected={traj}
                    implied={impliedSensors}
                    onToggle={toggleTraj}
                    mode="ordered" accent="#f59e0b" />
                  {traj.length > 0 && (
                    <div style={{ marginTop:8, padding:"7px 11px",
                      background:"#050c1a", borderRadius:6, fontSize:10,
                      color:"#fcd34d", fontFamily:"monospace" }}>
                      Route: {traj.join(" → ")}
                      <button style={{ ...btn("#6b7280", true), marginLeft:10 }}
                        onClick={()=>setTraj([])}>Clear</button>
                    </div>
                  )}
                </div>

                {/* Summary + save */}
                <div style={{ marginTop:16, padding:"9px 13px", background:"#050c1a",
                  borderRadius:6, fontSize:10,
                  color: auth.allowed_zones.length || auth.allowed_sensors.length
                          ? "#4ade80" : "#f87171" }}>
                  {auth.allowed_zones.length || auth.allowed_sensors.length
                    ? `✓ ${auth.allowed_zones.length} zone(s), ${auth.allowed_sensors.length} sensor(s), ${traj.length} waypoint(s)`
                    : "⚠ No access granted — every position will be a VIOLATION"}
                </div>

                <div style={{ display:"flex", gap:8, marginTop:12 }}>
                  <button style={btn("#22c55e")} onClick={()=>saveAuth(w)}>
                    Save configuration
                  </button>
                  <button style={btn("#6b7280")} onClick={()=>setOpenId(null)}>Cancel</button>
                </div>
              </div>
            )}
          </div>
        );
      })}

      {shown.length === 0 && (
        <div style={{ padding:36, textAlign:"center", color:"#334155",
          fontSize:12, background:"#0d1829", borderRadius:10 }}>
          No assets — add one above
        </div>
      )}
    </div>
  );
}
