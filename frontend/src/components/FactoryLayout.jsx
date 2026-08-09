// =============================================================================
// FactoryLayout.jsx — Configuration Tab 1
//   • Factory name
//   • Blueprint IMAGE UPLOAD (drag & drop or file picker) with live preview
//   • Grid columns / rows  (regenerates sensors on save)
//   • Zones defined by clicking sensors on a visual grid picker
// =============================================================================

import { useState, useEffect } from "react";
import BlueprintUpload from "./BlueprintUpload";
import SensorGridPicker from "./SensorGridPicker";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";
const PALETTE = ["#14b8a6","#3b82f6","#8b5cf6","#f59e0b",
                 "#ec4899","#ef4444","#22c55e","#f97316"];

const input = { background:"#0d1829", border:"1px solid #334155", borderRadius:6,
  color:"#e2e8f0", padding:"7px 10px", fontSize:12, fontFamily:"monospace",
  width:"100%", boxSizing:"border-box" };
const btn = (c="#6366f1", sm=false) => ({
  padding: sm?"4px 10px":"7px 16px", fontSize: sm?10:12, fontWeight:600,
  border:`1px solid ${c}`, borderRadius:6, background:`${c}22`, color:c,
  cursor:"pointer", fontFamily:"monospace" });
const lbl = { fontSize:10, color:"#64748b", marginBottom:4, display:"block", letterSpacing:1 };
const card = { background:"#0d1829", border:"1px solid #1e293b",
  borderRadius:10, padding:16, marginBottom:14 };

export default function FactoryLayout({ zones, sensors, apiCall, reload }) {
  const [cfg,      setCfg]      = useState({ factory_name:"", blueprint_url:"", grid_cols:6, grid_rows:5 });
  const [editZone, setEditZone] = useState(null);
  const [zoneSel,  setZoneSel]  = useState({});
  const [zoneTh,   setZoneTh]   = useState({});
  const [newZone,  setNewZone]  = useState({ zone_id:"", name:"", description:"" });

  useEffect(() => { loadCfg(); }, []);

  async function loadCfg() {
    try {
      const d = await fetch(`${API}/api/config/factory`).then(r => r.json());
      setCfg({ factory_name:d.factory_name||"", blueprint_url:d.blueprint_url||"",
               grid_cols:d.grid_cols||6, grid_rows:d.grid_rows||5,
               temp_warning:d.temp_warning, temp_critical:d.temp_critical,
               humidity_warning:d.humidity_warning,
               humidity_critical:d.humidity_critical });
    } catch {}
  }

  function saveFactory() {
    apiCall("/api/config/factory", "PUT", {
      factory_name: cfg.factory_name,
      grid_cols:    parseInt(cfg.grid_cols),
      grid_rows:    parseInt(cfg.grid_rows),
      temp_warning:      cfg.temp_warning      ?? null,
      temp_critical:     cfg.temp_critical     ?? null,
      humidity_warning:  cfg.humidity_warning  ?? null,
      humidity_critical: cfg.humidity_critical ?? null,
    });
  }

  // ── Zones ─────────────────────────────────────────────────────────────────
  function startEdit(z) {
    setEditZone(z.zone_id);
    setZoneSel(p => ({ ...p, [z.zone_id]: z.sensor_ids || [] }));
  }
  function toggleSensor(zid, sid) {
    setZoneSel(p => {
      const cur = p[zid] || [];
      return { ...p, [zid]: cur.includes(sid) ? cur.filter(x=>x!==sid) : [...cur, sid] };
    });
  }
  function saveZone(z) {
    const th = zoneTh[z.zone_id] || {};
    apiCall("/api/config/zones", "POST", {
      zone_id: z.zone_id, name: z.name, description: z.description,
      sensor_ids: zoneSel[z.zone_id] || [],
      temp_warning:      th.temp_warning      ?? z.temp_warning      ?? null,
      temp_critical:     th.temp_critical     ?? z.temp_critical     ?? null,
      humidity_warning:  th.humidity_warning  ?? z.humidity_warning  ?? null,
      humidity_critical: th.humidity_critical ?? z.humidity_critical ?? null,
    });
    setEditZone(null);
  }
  function addZone() {
    if (!newZone.zone_id || !newZone.name) return;
    apiCall("/api/config/zones", "POST", { ...newZone, sensor_ids:[] });
    setNewZone({ zone_id:"", name:"", description:"" });
  }
  function delZone(zid) {
    if (!window.confirm(`Delete ${zid}? Its sensors become unassigned.`)) return;
    apiCall(`/api/config/zones/${zid}`, "DELETE");
  }

  const cols = parseInt(cfg.grid_cols) || 6;
  const rows = parseInt(cfg.grid_rows) || 5;

  // sensor_id → zone_id (for showing which zone owns each cell)
  const owner = {};
  zones.forEach(z => (z.sensor_ids||[]).forEach(s => { owner[s] = z.zone_id; }));

  const unassigned = sensors.filter(s => !s.zone_id).length;

  return (
    <div>
      {/* ═══ Blueprint upload ═══ */}
      <div style={card}>
        <div style={{ fontSize:13, fontWeight:700, color:"#a5b4fc", marginBottom:12 }}>
          Factory Blueprint
        </div>

        <BlueprintUpload
          value={cfg.blueprint_url}
          onChange={url => setCfg(p => ({ ...p, blueprint_url: url }))} />
      </div>

      {/* ═══ Factory name + grid size ═══ */}
      <div style={card}>
        <div style={{ fontSize:13, fontWeight:700, color:"#a5b4fc", marginBottom:12 }}>
          Factory Name &amp; Grid Size
        </div>
        <div style={{ display:"grid", gridTemplateColumns:"1fr 110px 110px auto", gap:12,
                      alignItems:"end" }}>
          <div>
            <span style={lbl}>FACTORY NAME</span>
            <input style={input} value={cfg.factory_name}
              onChange={e => setCfg(p=>({...p, factory_name:e.target.value}))} />
          </div>
          <div>
            <span style={lbl}>COLUMNS (N)</span>
            <input style={input} type="number" min={1} max={30} value={cfg.grid_cols}
              onChange={e => setCfg(p=>({...p, grid_cols:e.target.value}))} />
          </div>
          <div>
            <span style={lbl}>ROWS (M)</span>
            <input style={input} type="number" min={1} max={30} value={cfg.grid_rows}
              onChange={e => setCfg(p=>({...p, grid_rows:e.target.value}))} />
          </div>
          <button style={btn("#22c55e")} onClick={saveFactory}>Apply</button>
        </div>
        <div style={{ marginTop:16, paddingTop:14, borderTop:"1px solid #1e293b" }}>
          <div style={{ fontSize:10, color:"#64748b", letterSpacing:1, marginBottom:8 }}>
            GLOBAL THRESHOLD DEFAULTS
            <span style={{ letterSpacing:0, marginLeft:6, color:"#475569" }}>
              — used when neither the sensor nor its zone defines a limit
            </span>
          </div>
          <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:10 }}>
            {[
              ["temp_warning",      "TEMP WARN °C"],
              ["temp_critical",     "TEMP CRIT °C"],
              ["humidity_warning",  "HUM WARN %"],
              ["humidity_critical", "HUM CRIT %"],
            ].map(([k, label]) => (
              <div key={k}>
                <span style={lbl}>{label}</span>
                <input style={input} type="number" value={cfg[k] ?? ""}
                  onChange={e => setCfg(p => ({ ...p,
                    [k]: e.target.value === "" ? null : parseFloat(e.target.value) }))} />
              </div>
            ))}
          </div>
        </div>

        <div style={{ fontSize:10, color:"#f59e0b", marginTop:10, lineHeight:1.6 }}>
          ⚠ Changing the grid regenerates sensors: {cols}×{rows} = <b>{cols*rows} sensors</b> (S01–S{String(cols*rows).padStart(2,"0")}).
          Sensors outside the new grid are removed; existing zone assignments are kept.
          The monitoring view updates immediately — no rebuild needed.
        </div>
      </div>

      {/* ═══ Zones defined by their sensors ═══ */}
      <div style={card}>
        <div style={{ fontSize:13, fontWeight:700, color:"#a5b4fc", marginBottom:4 }}>
          Zones — defined by the sensors they contain
        </div>
        <div style={{ fontSize:10, color:"#475569", marginBottom:14 }}>
          Click <b>Define</b> then click cells on the grid to add or remove them from the zone.
          {unassigned > 0 && <span style={{ color:"#f59e0b" }}> · {unassigned} sensor(s) unassigned</span>}
        </div>

        {zones.map((z, idx) => {
          const col = PALETTE[idx % PALETTE.length];
          const sel = zoneSel[z.zone_id] || z.sensor_ids || [];
          return (
            <div key={z.zone_id} style={{
              border:`1px solid ${col}44`, borderLeft:`4px solid ${col}`,
              borderRadius:8, padding:12, marginBottom:10, background:"#050c1a" }}>

              <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:8 }}>
                <span style={{ fontWeight:700, color:col, fontSize:12 }}>{z.zone_id}</span>
                <span style={{ color:"#e2e8f0", fontSize:12 }}>{z.name}</span>
                <span style={{ color:"#475569", fontSize:10, flex:1 }}>{z.description}</span>
                <span style={{ fontSize:10, color:"#64748b" }}>
                  {(z.sensor_ids||[]).length} sensors
                </span>
                <button style={btn(col, true)}
                  onClick={() => editZone===z.zone_id ? setEditZone(null) : startEdit(z)}>
                  {editZone===z.zone_id ? "Close" : "Define"}
                </button>
                <button style={btn("#ef4444", true)} onClick={() => delZone(z.zone_id)}>Del</button>
              </div>

              {/* Visual grid picker */}
              {editZone === z.zone_id ? (
                <div>
                  <SensorGridPicker
                    sensors={sensors} zones={zones}
                    cols={cols} rows={rows}
                    blueprintUrl={cfg.blueprint_url}
                    selected={sel}
                    onToggle={(sid) => toggleSensor(z.zone_id, sid)}
                    mode="select" accent={col}
                    highlightZone={z.zone_id} />
                  <div style={{ fontSize:10, color:"#64748b", marginBottom:10 }}>
                    {sel.length} sensor(s) selected
                    {sel.length > 0 && ` — ${sel.slice(0,10).join(", ")}${sel.length>10?"…":""}`}
                  </div>
                  {/* Zone thresholds — inherited by every sensor in the zone */}
                  <div style={{ marginTop:14, padding:"11px 13px",
                    background:"#050c1a", borderRadius:8,
                    border:"1px solid #1e293b" }}>
                    <div style={{ fontSize:10, color:"#64748b", letterSpacing:1,
                      marginBottom:8 }}>
                      ZONE THRESHOLDS
                      <span style={{ letterSpacing:0, marginLeft:6, color:"#475569" }}>
                        — every sensor in this zone inherits these unless it
                        defines its own. Leave blank to use the factory default.
                      </span>
                    </div>
                    <div style={{ display:"grid",
                      gridTemplateColumns:"repeat(4, 1fr)", gap:9 }}>
                      {[
                        ["temp_warning",      "TEMP WARN °C",  "50"],
                        ["temp_critical",     "TEMP CRIT °C",  "60"],
                        ["humidity_warning",  "HUM WARN %",    "70"],
                        ["humidity_critical", "HUM CRIT %",    "85"],
                      ].map(([k, label, ph]) => (
                        <div key={k}>
                          <span style={lbl}>{label}</span>
                          <input style={input} type="number" placeholder={ph}
                            value={zoneTh[z.zone_id]?.[k] ?? z[k] ?? ""}
                            onChange={e => setZoneTh(p => ({ ...p,
                              [z.zone_id]: { ...(p[z.zone_id] || {}),
                                [k]: e.target.value === "" ? null
                                     : parseFloat(e.target.value) } }))} />
                        </div>
                      ))}
                    </div>
                  </div>

                  <div style={{ display:"flex", gap:8, marginTop:12 }}>
                    <button style={btn("#22c55e")} onClick={() => saveZone(z)}>Save zone</button>
                    <button style={btn("#6b7280")} onClick={() => setEditZone(null)}>Cancel</button>
                  </div>
                </div>
              ) : (
                (z.sensor_ids||[]).length > 0 && (
                  <div style={{ display:"flex", flexWrap:"wrap", gap:4 }}>
                    {z.sensor_ids.map(s => (
                      <span key={s} style={{ padding:"1px 7px", fontSize:9, borderRadius:3,
                        background:col+"22", color:col, border:`1px solid ${col}44` }}>{s}</span>
                    ))}
                  </div>
                )
              )}
            </div>
          );
        })}

        {/* Add zone */}
        <div style={{ borderTop:"1px solid #1e293b", paddingTop:14, marginTop:6 }}>
          <div style={{ fontSize:11, fontWeight:700, color:"#64748b", marginBottom:10 }}>
            ADD NEW ZONE
          </div>
          <div style={{ display:"grid", gridTemplateColumns:"130px 1fr 1fr auto", gap:10,
                        alignItems:"end" }}>
            <div>
              <span style={lbl}>ZONE ID</span>
              <input style={input} placeholder="zone_F" value={newZone.zone_id}
                onChange={e => setNewZone(p=>({...p, zone_id:e.target.value.replace(/\s/g,"_")}))} />
            </div>
            <div>
              <span style={lbl}>NAME</span>
              <input style={input} placeholder="Maintenance" value={newZone.name}
                onChange={e => setNewZone(p=>({...p, name:e.target.value}))} />
            </div>
            <div>
              <span style={lbl}>DESCRIPTION</span>
              <input style={input} placeholder="Tool store" value={newZone.description}
                onChange={e => setNewZone(p=>({...p, description:e.target.value}))} />
            </div>
            <button style={btn("#22c55e")} onClick={addZone}>+ Add</button>
          </div>
        </div>
      </div>
    </div>
  );
}
