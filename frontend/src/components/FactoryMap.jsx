// =============================================================================
// FactoryMap.jsx
//   2D view — blueprint background, zone OUTLINES (no fill), border-only cells
//   3D view — isometric stack:
//       layer 0  factory blueprint as a flat ground plane
//       layer 1  workers / assets floating above it (by NAME)
//       layer 2  sensors floating above the workers
// =============================================================================

import { useState, useMemo, useEffect } from "react";
import SensorCell   from "./SensorCell";
import SensorDetail from "./SensorDetail";

const CELL = 96, GAP = 4, MARGIN = 20;
const PALETTE = ["#14b8a6","#3b82f6","#8b5cf6","#f59e0b",
                 "#ec4899","#ef4444","#22c55e","#f97316"];
const AICON = { worker:"👷", forklift:"🚜", pallet:"📦", object:"📍" };
const SHADOW = "0 1px 3px rgba(0,0,0,0.95)";

export default function FactoryMap({
  sensors, health, assets, cols = 6, rows = 5,
  blueprintSrc = null, zones = [], sensorConfig = [],
}) {
  const [selected,   setSelected]   = useState(null);
  const [imgError,   setImgError]   = useState(false);
  const [view,       setView]       = useState("2d");   // "2d" | "3d"
  const [fullscreen, setFullscreen] = useState(false);  // blueprint overlay
  const [zoom,       setZoom]       = useState(1);

  const sensorMap = useMemo(() => Object.fromEntries(
    (sensors||[]).map(s => [s.sensor_id, s])), [sensors]);
  const healthMap = useMemo(() => Object.fromEntries(
    (health||[]).map(h => [h.sensor_id, h])), [health]);
  const cfgMap = useMemo(() => Object.fromEntries(
    (sensorConfig||[]).map(s => [s.sensor_id, s])), [sensorConfig]);

  const assetsBySensor = useMemo(() => {
    const m = {};
    (assets||[]).forEach(a => {
      if (a.current_sensor_id) (m[a.current_sensor_id] = m[a.current_sensor_id] || []).push(a);
    });
    return m;
  }, [assets]);

  // sensor → zone (built from each zone's sensor list)
  const sensorZone = useMemo(() => {
    const m = {};
    (zones||[]).forEach((z,i) => {
      const color = PALETTE[i % PALETTE.length];
      (z.sensor_ids||[]).forEach(sid => {
        m[sid] = { color, zone_id:z.zone_id, name:z.name };
      });
    });
    return m;
  }, [zones]);

  // Esc closes the fullscreen blueprint
  useEffect(() => {
    if (!fullscreen) return;
    const onKey = e => { if (e.key === "Escape") setFullscreen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fullscreen]);

  const gridW = cols*CELL + (cols-1)*GAP;
  const gridH = rows*CELL + (rows-1)*GAP;
  const svgW  = MARGIN*2 + gridW;
  const svgH  = MARGIN*2 + gridH;

  const sid = (r,c) => `S${String(r*cols + c + 1).padStart(2,"0")}`;
  const posOf = s => {
    const n = parseInt(String(s).replace(/\D/g,""),10) - 1;
    return { row: Math.floor(n/cols), col: n%cols };
  };
  const showImg = blueprintSrc && !imgError;

  // ── Zone outline segments: draw a border only where a cell's neighbour
  //    belongs to a different zone, producing a clean zone perimeter.
  const zoneEdges = useMemo(() => {
    const segs = [];
    for (let r=0; r<rows; r++) for (let c=0; c<cols; c++) {
      const z = sensorZone[sid(r,c)];
      if (!z) continue;
      const x = MARGIN + c*(CELL+GAP) - GAP/2;
      const y = MARGIN + r*(CELL+GAP) - GAP/2;
      const w = CELL+GAP, h = CELL+GAP;
      const diff = (rr,cc) => {
        if (rr<0||cc<0||rr>=rows||cc>=cols) return true;
        const o = sensorZone[sid(rr,cc)];
        return !o || o.zone_id !== z.zone_id;
      };
      if (diff(r-1,c)) segs.push({ x1:x,     y1:y,     x2:x+w, y2:y,     c:z.color });
      if (diff(r+1,c)) segs.push({ x1:x,     y1:y+h,   x2:x+w, y2:y+h,   c:z.color });
      if (diff(r,c-1)) segs.push({ x1:x,     y1:y,     x2:x,   y2:y+h,   c:z.color });
      if (diff(r,c+1)) segs.push({ x1:x+w,   y1:y,     x2:x+w, y2:y+h,   c:z.color });
    }
    return segs;
  }, [sensorZone, rows, cols]);

  // Zone label anchored at each zone's top-left cell
  const zoneLabels = useMemo(() => (zones||[]).map((z,i) => {
    const cells = (z.sensor_ids||[]).map(posOf);
    if (!cells.length) return null;
    const minR = Math.min(...cells.map(p=>p.row));
    const minC = Math.min(...cells.map(p=>p.col));
    return { name:z.name, count:cells.length, color:PALETTE[i%PALETTE.length],
             x: MARGIN + minC*(CELL+GAP) + 5,
             y: MARGIN + minR*(CELL+GAP) + 12 };
  }).filter(Boolean), [zones, cols]);

  const tbtn = (active) => ({
    padding:"6px 14px", fontSize:11, fontWeight:700, fontFamily:"monospace",
    cursor:"pointer", borderRadius:6,
    border:`1px solid ${active ? "#6366f1" : "#1e293b"}`,
    background: active ? "#6366f133" : "#0d1829",
    color: active ? "#a5b4fc" : "#475569",
  });

  const Toolbar = () => (
    <div style={{ display:"flex", gap:8, marginBottom:10,
      alignItems:"center", flexWrap:"wrap" }}>
      <div style={{ display:"flex", gap:0 }}>
        {["2d","3d"].map(v => (
          <button key={v} onClick={()=>setView(v)}
            style={{ ...tbtn(view===v),
              borderRadius: v==="2d" ? "6px 0 0 6px" : "0 6px 6px 0" }}>
            {v === "2d" ? "▦  2D" : "◈  3D"}
          </button>
        ))}
      </div>

      {view === "2d" && (
        <div style={{ display:"flex", gap:0, marginLeft:4 }}>
          <button onClick={()=>setZoom(z=>Math.max(0.4, +(z-0.2).toFixed(2)))}
            style={{ ...tbtn(false), borderRadius:"6px 0 0 6px" }}>−</button>
          <button onClick={()=>setZoom(1)}
            style={{ ...tbtn(zoom!==1), borderRadius:0, minWidth:56 }}>
            {Math.round(zoom*100)}%
          </button>
          <button onClick={()=>setZoom(z=>Math.min(2.5, +(z+0.2).toFixed(2)))}
            style={{ ...tbtn(false), borderRadius:"0 6px 6px 0" }}>+</button>
        </div>
      )}

      {blueprintSrc && (
        <button onClick={()=>setFullscreen(true)} style={tbtn(false)}
          title="Show the factory blueprint full screen">
          ⛶  Blueprint full screen
        </button>
      )}

      <span style={{ marginLeft:"auto", fontSize:9, color:"#475569",
        fontFamily:"monospace" }}>
        {view === "3d" ? "blueprint ▸ workers ▸ sensors"
                       : `${cols}×${rows} · ${rows*cols} sensors · ${zones.length} zones`}
      </span>
    </div>
  );

  // ── Fullscreen blueprint overlay ──
  const FullscreenBlueprint = () => (
    <div onClick={()=>setFullscreen(false)}
      style={{ position:"fixed", inset:0, zIndex:200,
        background:"rgba(2,8,20,0.96)", display:"flex",
        flexDirection:"column", alignItems:"center", justifyContent:"center",
        padding:20, cursor:"zoom-out" }}>
      <div style={{ position:"absolute", top:16, right:20, display:"flex", gap:10 }}>
        <span style={{ fontSize:10, color:"#475569", fontFamily:"monospace",
          alignSelf:"center" }}>click anywhere or press Esc to close</span>
        <button onClick={()=>setFullscreen(false)}
          style={{ ...tbtn(false), fontSize:16, padding:"2px 12px" }}>×</button>
      </div>
      <img src={blueprintSrc} alt="Factory blueprint"
        onClick={e => e.stopPropagation()}
        style={{ maxWidth:"96vw", maxHeight:"88vh", objectFit:"contain",
          borderRadius:8, border:"1px solid #1e3a5f",
          boxShadow:"0 20px 60px rgba(0,0,0,.9)", cursor:"default" }} />
    </div>
  );

  // ═══════════════════════════════════════════════════════════════════════════
  //  3D ISOMETRIC VIEW
  // ═══════════════════════════════════════════════════════════════════════════
  if (view === "3d") {
    const SCALE = 0.82;
    const W = svgW * SCALE, H = svgH * SCALE;
    // Layer separation capped so the top layer sits at most 2x a sensor
    // width above the blueprint (previously 240px — far too detached).
    const LAYER_GAP = Math.round(CELL * SCALE * 0.5);   // ≈ 39px per layer
    const stageH = H * 0.72 + LAYER_GAP * 2 + 120;

    const plate = (children, lift, z) => (
      <div style={{
        position:"absolute", left:"50%", top: stageH - lift - H*0.55,
        width:W, height:H,
        transform:`translateX(-50%) rotateX(58deg) rotateZ(-45deg)`,
        transformStyle:"preserve-3d", zIndex:z,
      }}>{children}</div>
    );

    return (
      <>
        <Toolbar />
        <div style={{
          position:"relative", height:stageH, width:"100%",
          perspective:"1600px", perspectiveOrigin:"50% 42%",
          background:"radial-gradient(ellipse at 50% 40%, #0d1e3a 0%, #050c1a 72%)",
          borderRadius:12, border:"1px solid #1e3a5f",
          overflow:"auto", maxHeight:"calc(100vh - 260px)",
        }}>
          {/* ── LAYER 0 — blueprint ground plane ── */}
          {plate(
            <div style={{ width:"100%", height:"100%", position:"relative",
              background: showImg ? "#0a1628" : "#0a1628",
              border:"2px solid #1e3a5f", borderRadius:8,
              boxShadow:"0 30px 70px rgba(0,0,0,0.8)", overflow:"hidden" }}>
              {showImg ? (
                <img src={blueprintSrc} alt="" onError={()=>setImgError(true)}
                  style={{ width:"100%", height:"100%", objectFit:"cover",
                           opacity:0.9 }} />
              ) : (
                <svg width="100%" height="100%">
                  {Array.from({length:cols+1},(_,i)=>(
                    <line key={"v"+i} x1={i*(CELL+GAP)*SCALE} y1={0}
                      x2={i*(CELL+GAP)*SCALE} y2={H} stroke="#1e3a5f" strokeWidth="1"/>
                  ))}
                  {Array.from({length:rows+1},(_,i)=>(
                    <line key={"h"+i} x1={0} y1={i*(CELL+GAP)*SCALE}
                      x2={W} y2={i*(CELL+GAP)*SCALE} stroke="#1e3a5f" strokeWidth="1"/>
                  ))}
                </svg>
              )}
              {/* Zone outlines on the ground plane */}
              <svg style={{ position:"absolute", inset:0 }} width="100%" height="100%">
                {zoneEdges.map((s,i)=>(
                  <line key={i} x1={s.x1*SCALE} y1={s.y1*SCALE}
                    x2={s.x2*SCALE} y2={s.y2*SCALE}
                    stroke={s.c} strokeWidth="2.5" opacity={0.85}/>
                ))}
              </svg>
            </div>, 0, 1)}

          {/* ── LAYER 1 — assets, above the blueprint ── */}
          {plate(
            <div style={{ width:"100%", height:"100%", position:"relative" }}>
              {(assets||[]).map(a => {
                if (!a.current_sensor_id) return null;
                const { row, col } = posOf(a.current_sensor_id);
                if (row >= rows || col >= cols) return null;
                const viol = a.access_status === "violation";
                return (
                  <div key={a.id} style={{
                    position:"absolute",
                    left: (MARGIN + col*(CELL+GAP) + CELL/2)*SCALE,
                    top:  (MARGIN + row*(CELL+GAP) + CELL/2)*SCALE,
                    transform:"translate(-50%,-50%) rotateZ(45deg) rotateX(-58deg)",
                    transformStyle:"preserve-3d",
                    display:"flex", flexDirection:"column", alignItems:"center",
                    transition:"left .6s ease, top .6s ease",
                  }}>
                    <div style={{ fontSize:26, filter:
                      `drop-shadow(0 4px 8px rgba(0,0,0,.9))` }}>
                      {AICON[a.asset_type] || "📍"}
                    </div>
                    {/* NAME, not ID */}
                    <div style={{ fontSize:9, fontWeight:700, marginTop:1,
                      color: viol ? "#fca5a5" : "#e2e8f0",
                      background:"rgba(2,8,20,0.85)", padding:"1px 6px",
                      borderRadius:3, whiteSpace:"nowrap", fontFamily:"monospace",
                      border:`1px solid ${viol ? "#ef4444" : "#334155"}` }}>
                      {a.name || a.id}
                    </div>
                  </div>
                );
              })}
            </div>, LAYER_GAP, 2)}

          {/* ── LAYER 2 — sensors, topmost ── */}
          {plate(
            <div style={{ width:"100%", height:"100%", position:"relative" }}>
              {Array.from({length: rows*cols}, (_, i) => {
                const r = Math.floor(i/cols), c = i%cols;
                const id = sid(r,c);
                const S = sensorMap[id] || {}, Hh = healthMap[id] || {};
                const z = sensorZone[id];
                const col_ =
                  Hh.status === "offline"  ? "#6b7280" :
                  Hh.status === "degraded" ? "#f59e0b" :
                  S.env_status === "critical" ? "#ef4444" :
                  S.env_status === "warning"  ? "#f97316" : "#10b981";
                const crit = S.env_status === "critical" || S.smoke;
                return (
                  <div key={id} onClick={()=>setSelected(id)}
                    style={{ position:"absolute",
                      left:(MARGIN + c*(CELL+GAP))*SCALE,
                      top: (MARGIN + r*(CELL+GAP))*SCALE,
                      width: CELL*SCALE, height: CELL*SCALE,
                      border:`${crit?2.4:1.3}px solid ${col_}`,
                      borderStyle: cfgMap[id]?.passable === false ? "dashed" : "solid",
                      borderRadius:6, cursor:"pointer",
                      background:"rgba(5,12,26,0.30)",
                      boxShadow: crit ? `0 0 18px ${col_}cc` : `0 6px 16px rgba(0,0,0,.6)`,
                      display:"flex", flexDirection:"column",
                      alignItems:"center", justifyContent:"center",
                    }}>
                    <div style={{ transform:"rotateZ(45deg) rotateX(-58deg)",
                      textAlign:"center", fontFamily:"monospace" }}>
                      <div style={{ fontSize:9, fontWeight:700, color:col_,
                        textShadow:SHADOW }}>{id}</div>
                      {S.temperature != null && (
                        <div style={{ fontSize:8, color:col_, textShadow:SHADOW }}>
                          {S.temperature.toFixed(0)}°
                        </div>
                      )}
                      {S.smoke && <div style={{ fontSize:9 }}>💨</div>}
                      {z && <div style={{ fontSize:7, color:z.color,
                        textShadow:SHADOW }}>{z.name}</div>}
                    </div>
                  </div>
                );
              })}
            </div>, LAYER_GAP*2, 3)}

          {/* Layer legend */}
          <div style={{ position:"absolute", top:12, left:14, zIndex:10,
            fontFamily:"monospace", fontSize:9, color:"#475569", lineHeight:1.9 }}>
            <div><span style={{ color:"#10b981" }}>▲</span> sensors</div>
            <div><span style={{ color:"#a5b4fc" }}>▲</span> workers &amp; assets</div>
            <div><span style={{ color:"#64748b" }}>▲</span> factory blueprint</div>
          </div>
        </div>

        {fullscreen && blueprintSrc && <FullscreenBlueprint />}

        {selected && (
          <SensorDetail sensorId={selected} sensor={sensorMap[selected]}
            health={healthMap[selected]} assets={assetsBySensor[selected]||[]}
            config={cfgMap[selected]} zone={sensorZone[selected]}
            onClose={()=>setSelected(null)} />
        )}
      </>
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  2D VIEW
  // ═══════════════════════════════════════════════════════════════════════════
  return (
    <>
      <Toolbar />
      <div style={{ width:"100%", overflow:"auto", maxHeight:"calc(100vh - 260px)" }}>
        <svg viewBox={`0 0 ${svgW} ${svgH}`} width={svgW * zoom}
          style={{ display:"block", background:"#0a1628",
                   borderRadius:12, transition:"width .15s" }}>

          {showImg && (
            <image href={blueprintSrc} x={0} y={0} width={svgW} height={svgH}
              preserveAspectRatio="xMidYMid slice" opacity={0.85}
              onError={()=>setImgError(true)} />
          )}

          {!showImg && (
            <>
              {Array.from({length:cols+1},(_,i)=>(
                <line key={"v"+i} x1={MARGIN+i*(CELL+GAP)} y1={MARGIN}
                  x2={MARGIN+i*(CELL+GAP)} y2={svgH-MARGIN}
                  stroke="#1e3a5f" strokeWidth="0.6"/>
              ))}
              {Array.from({length:rows+1},(_,i)=>(
                <line key={"h"+i} x1={MARGIN} y1={MARGIN+i*(CELL+GAP)}
                  x2={svgW-MARGIN} y2={MARGIN+i*(CELL+GAP)}
                  stroke="#1e3a5f" strokeWidth="0.6"/>
              ))}
            </>
          )}

          {/* Zone perimeters — outline only, no fill */}
          {zoneEdges.map((s,i)=>(
            <line key={i} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2}
              stroke={s.c} strokeWidth="2.5" opacity={0.9} strokeLinecap="round"/>
          ))}

          {/* Zone labels with sensor counts */}
          {zoneLabels.map((z,i)=>(
            <text key={i} x={z.x} y={z.y} fill={z.color}
              fontSize={9} fontWeight={700} fontFamily="monospace"
              style={{ textShadow:"0 1px 3px rgba(0,0,0,.95)" }}>
              {z.name} · {z.count} sensors
            </text>
          ))}

          <rect x={MARGIN} y={MARGIN} width={gridW} height={gridH}
            fill="none" stroke="#1e3a5f" strokeWidth="1.5" rx={4}/>

          <foreignObject x={MARGIN} y={MARGIN} width={gridW} height={gridH}>
            <div xmlns="http://www.w3.org/1999/xhtml" style={{
              display:"grid",
              gridTemplateColumns:`repeat(${cols}, ${CELL}px)`,
              gridTemplateRows:`repeat(${rows}, ${CELL}px)`, gap:GAP }}>
              {Array.from({length: rows*cols}, (_,i) => {
                const id = sid(Math.floor(i/cols), i%cols);
                return <SensorCell key={id} sensorId={id}
                  sensor={sensorMap[id]} health={healthMap[id]}
                  assets={assetsBySensor[id]} config={cfgMap[id]}
                  zone={sensorZone[id]} onSelect={setSelected} cellPx={CELL}/>;
              })}
            </div>
          </foreignObject>

          <text x={MARGIN+2} y={MARGIN-7} fill="#334155"
            fontSize={9} fontFamily="monospace" fontWeight={700}>
            {cols}×{rows} · {rows*cols} sensors · {zones.length} zones
          </text>
        </svg>
      </div>

      {fullscreen && blueprintSrc && <FullscreenBlueprint />}

      {selected && (
        <SensorDetail sensorId={selected} sensor={sensorMap[selected]}
          health={healthMap[selected]} assets={assetsBySensor[selected]||[]}
          config={cfgMap[selected]} zone={sensorZone[selected]}
          onClose={()=>setSelected(null)} />
      )}
    </>
  );
}
