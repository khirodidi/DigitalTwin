// =============================================================================
// frontend/src/pages/SetupScreen.jsx
//
// Shown whenever the factory is not yet configured. The dashboard renders
// nothing until BOTH requirements are satisfied:
//    1. grid columns and rows  (> 0)
//    2. a factory blueprint image
// Everything else (zones, sensor coverage, workers) is optional and can be
// added later from the Configuration page.
// =============================================================================

import { useState, useEffect } from "react";
import BlueprintUpload from "../components/BlueprintUpload";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

export default function SetupScreen({ onDone, onOpenConfig }) {
  const [name,      setName]      = useState("");
  const [cols,      setCols]      = useState(6);
  const [rows,      setRows]      = useState(5);
  const [blueprint, setBlueprint] = useState("");
  const [saving,    setSaving]    = useState(false);
  const [err,       setErr]       = useState(null);

  // Pick up anything already stored (e.g. a half-finished setup)
  useEffect(() => {
    fetch(`${API}/api/config/factory`).then(r => r.json()).then(d => {
      if (d.factory_name)  setName(d.factory_name);
      if (d.grid_cols > 0) setCols(d.grid_cols);
      if (d.grid_rows > 0) setRows(d.grid_rows);
      if (d.blueprint_url) setBlueprint(d.blueprint_url);
    }).catch(() => {});
  }, []);

  async function finish() {
    if (!ready) return;
    setSaving(true); setErr(null);
    try {
      const r = await fetch(`${API}/api/config/factory`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          factory_name: name.trim() || "Factory",
          grid_cols: parseInt(cols), grid_rows: parseInt(rows),
        }),
      });
      if (!r.ok) throw new Error(await r.text());
      onDone && onDone();
    } catch (e) {
      setErr("Could not save: " + e.message);
    } finally {
      setSaving(false);
    }
  }

  const ready = cols > 0 && rows > 0 && Boolean(blueprint);
  const src   = blueprint
    ? (blueprint.startsWith("http") ? blueprint : `${API}${blueprint}`) : null;

  const card = { background:"#0d1829", border:"1px solid #1e293b",
    borderRadius:12, padding:22, marginBottom:16 };
  const input = { background:"#050c1a", border:"1px solid #334155",
    borderRadius:8, color:"#e2e8f0", padding:"10px 12px", fontSize:14,
    fontFamily:"monospace", width:"100%", boxSizing:"border-box" };
  const lbl = { fontSize:10, color:"#64748b", marginBottom:6,
    display:"block", letterSpacing:1.5 };
  const step = (n, done) => ({
    width:24, height:24, borderRadius:"50%", flexShrink:0,
    display:"flex", alignItems:"center", justifyContent:"center",
    fontSize:11, fontWeight:700, fontFamily:"monospace",
    background: done ? "#16a34a" : "#1e293b",
    color: done ? "#fff" : "#64748b",
    border:`1px solid ${done ? "#22c55e" : "#334155"}`,
  });

  return (
    <div style={{
      height:"100vh", minHeight:0, display:"flex", flexDirection:"column",
      background:"#050c1a", color:"#e2e8f0",
      fontFamily:"'IBM Plex Mono','Fira Code',monospace",
      overflow:"hidden",
    }}>
      {/* Scrollable body — the only scrolling region on this screen */}
      <div style={{ flex:1, minHeight:0, overflowY:"auto", overflowX:"hidden" }}>
      <div style={{ maxWidth:780, margin:"0 auto", padding:"48px 20px 80px" }}>

        {/* Header */}
        <div style={{ textAlign:"center", marginBottom:34 }}>
          <div style={{ fontSize:44, marginBottom:10 }}>🏭</div>
          <div style={{ fontSize:9, color:"#6366f1", letterSpacing:4,
            textTransform:"uppercase", marginBottom:6 }}>Digital Twin</div>
          <div style={{ fontSize:24, fontWeight:700, marginBottom:8 }}>
            Factory Setup
          </div>
          <div style={{ fontSize:12, color:"#475569", lineHeight:1.7 }}>
            The monitoring dashboard needs a floor plan and a sensor grid before
            it can display anything.<br/>
            Zones, sensor coverage and workers can be configured afterwards.
          </div>
        </div>

        {/* Step 1 — grid */}
        <div style={card}>
          <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:16 }}>
            <div style={step(1, cols > 0 && rows > 0)}>
              {cols > 0 && rows > 0 ? "✓" : "1"}
            </div>
            <div>
              <div style={{ fontSize:14, fontWeight:700 }}>Sensor grid</div>
              <div style={{ fontSize:10, color:"#475569" }}>
                Required · one sensor per cell, covering the whole floor
              </div>
            </div>
          </div>

          <div style={{ display:"grid",
            gridTemplateColumns:"1fr 120px 120px", gap:14, marginBottom:14 }}>
            <div>
              <span style={lbl}>FACTORY NAME (optional)</span>
              <input style={input} placeholder="Factory A" value={name}
                onChange={e => setName(e.target.value)} />
            </div>
            <div>
              <span style={lbl}>COLUMNS *</span>
              <input style={input} type="number" min={1} max={30} value={cols}
                onChange={e => setCols(parseInt(e.target.value) || 0)} />
            </div>
            <div>
              <span style={lbl}>ROWS *</span>
              <input style={input} type="number" min={1} max={30} value={rows}
                onChange={e => setRows(parseInt(e.target.value) || 0)} />
            </div>
          </div>

          {cols > 0 && rows > 0 && (
            <div style={{ padding:"10px 14px", background:"#050c1a",
              borderRadius:8, fontSize:11, color:"#4ade80" }}>
              ✓ {cols} × {rows} = <b>{cols * rows} sensors</b>
              {" "}(S01–S{String(cols * rows).padStart(2, "0")}) will be created
            </div>
          )}
        </div>

        {/* Step 2 — blueprint */}
        <div style={card}>
          <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:16 }}>
            <div style={step(2, Boolean(blueprint))}>{blueprint ? "✓" : "2"}</div>
            <div>
              <div style={{ fontSize:14, fontWeight:700 }}>Factory blueprint</div>
              <div style={{ fontSize:10, color:"#475569" }}>
                Required · the floor plan shown behind the sensor grid
              </div>
            </div>
          </div>

          <BlueprintUpload value={blueprint} onChange={setBlueprint} />
        </div>

        {/* Error */}
        {err && (
          <div style={{ padding:"11px 15px", marginBottom:16, borderRadius:8,
            background:"#7f1d1d33", border:"1px solid #ef4444",
            color:"#fca5a5", fontSize:12 }}>{err}</div>
        )}

        {/* Finish */}
        <button onClick={finish} disabled={!ready || saving}
          style={{
            width:"100%", padding:"15px", fontSize:14, fontWeight:700,
            fontFamily:"monospace", borderRadius:10,
            cursor: ready && !saving ? "pointer" : "not-allowed",
            border:`1px solid ${ready ? "#22c55e" : "#1e293b"}`,
            background: ready ? "#22c55e22" : "#0d1829",
            color: ready ? "#4ade80" : "#334155",
            transition:"all .15s",
          }}>
          {saving ? "Saving…"
            : ready ? "Start monitoring →"
            : `Complete step ${cols > 0 && rows > 0 ? "2" : "1"} to continue`}
        </button>

        <div style={{ textAlign:"center", marginTop:20, fontSize:10,
          color:"#334155", lineHeight:1.9 }}>
          After setup you can define zones, set what each sensor covers,<br/>
          and add workers with their authorisations and trajectories.
          {onOpenConfig && (
            <>
              <br/>
              <button onClick={onOpenConfig} style={{
                marginTop:10, padding:"5px 14px", fontSize:10,
                background:"none", border:"1px solid #334155", borderRadius:6,
                color:"#64748b", cursor:"pointer", fontFamily:"monospace" }}>
                Open full configuration instead
              </button>
            </>
          )}
        </div>
      </div>
      </div>
    </div>
  );
}
