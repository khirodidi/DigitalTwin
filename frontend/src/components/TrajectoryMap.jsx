// =============================================================================
// frontend/src/components/TrajectoryMap.jsx
// Tab 4 of ConfigPage:
//   - Select a worker from the list
//   - Shows their last N location events as a path on the sensor grid
//   - Each step colour-coded by access status (green=OK, red=violation)
//   - Chronological step numbers overlaid on sensor cells
// =============================================================================

import { useState, useEffect } from "react";

const API    = process.env.REACT_APP_API_URL || "http://localhost:8000";
const COLS   = parseInt(process.env.REACT_APP_GRID_COLS,  10) || 6;
const ROWS   = parseInt(process.env.REACT_APP_GRID_ROWS,  10) || 5;
const CELL   = 76;
const GAP    = 3;
const MARGIN = 16;

const STATUS_COL = { authorised:"#4ade80", violation:"#f87171", unknown:"#fbbf24" };
const TYPE_ICON  = { worker:"👷", forklift:"🚜", pallet:"📦" };

function sensorPos(sid) {
  const n = parseInt((sid || "S1").replace(/\D/g,""), 10) - 1;
  return { row: Math.floor(n / COLS), col: n % COLS };
}

export default function TrajectoryMap({ workers, sensors }) {
  const [selected, setSelected] = useState(null);
  const [limit,    setLimit]    = useState(50);
  const [path,     setPath]     = useState([]);
  const [loading,  setLoading]  = useState(false);

  useEffect(() => {
    if (!selected) return;
    setLoading(true);
    fetch(`${API}/api/config/workers/${selected}/trajectory?limit=${limit}`)
      .then(r => r.json())
      .then(d => { setPath(Array.isArray(d) ? d : []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [selected, limit]);

  const svgW = MARGIN * 2 + COLS * CELL + (COLS - 1) * GAP;
  const svgH = MARGIN * 2 + ROWS * CELL + (ROWS - 1) * GAP;

  // Build per-sensor visit info
  const visitMap = {};   // sensor_id → [{ step, status }]
  path.forEach((p, i) => {
    if (!p.sensor_id) return;
    if (!visitMap[p.sensor_id]) visitMap[p.sensor_id] = [];
    visitMap[p.sensor_id].push({ step: i + 1, status: p.access_status });
  });

  // Build polyline path points
  const linePoints = path
    .filter(p => p.sensor_id)
    .map(p => {
      const { row, col } = sensorPos(p.sensor_id);
      return `${MARGIN + col * (CELL + GAP) + CELL / 2},${MARGIN + row * (CELL + GAP) + CELL / 2}`;
    }).join(" ");

  const worker = workers.find(w => w.asset_id === selected);

  return (
    <div>
      {/* Controls */}
      <div style={{ display:"flex", gap:12, marginBottom:20,
        alignItems:"flex-end", flexWrap:"wrap" }}>
        <div>
          <div style={{ fontSize:10, color:"#64748b", marginBottom:4, letterSpacing:1 }}>SELECT ASSET</div>
          <select
            value={selected || ""}
            onChange={e => { setSelected(e.target.value || null); setPath([]); }}
            style={{
              background:"#0d1829", border:"1px solid #334155", borderRadius:6,
              color:"#e2e8f0", padding:"7px 12px", fontSize:12, fontFamily:"monospace",
              minWidth:200,
            }}>
            <option value="">— choose worker —</option>
            {workers.map(w => (
              <option key={w.asset_id} value={w.asset_id}>
                {TYPE_ICON[w.asset_type] || "📍"} {w.asset_id} — {w.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <div style={{ fontSize:10, color:"#64748b", marginBottom:4, letterSpacing:1 }}>LAST N STEPS</div>
          <select value={limit} onChange={e => setLimit(parseInt(e.target.value))}
            style={{
              background:"#0d1829", border:"1px solid #334155", borderRadius:6,
              color:"#e2e8f0", padding:"7px 12px", fontSize:12, fontFamily:"monospace",
            }}>
            {[20,50,100,200].map(n => <option key={n} value={n}>{n} steps</option>)}
          </select>
        </div>

        {path.length > 0 && (
          <div style={{ fontSize:11, color:"#64748b", paddingBottom:6 }}>
            {path.length} location events loaded
            {worker && ` for ${worker.name}`}
          </div>
        )}

        {loading && <div style={{ fontSize:11, color:"#6366f1", paddingBottom:6 }}>Loading…</div>}
      </div>

      {!selected && (
        <div style={{
          padding:48, textAlign:"center", color:"#334155", fontSize:13,
          background:"#0d1829", borderRadius:10, border:"1px solid #1e293b",
        }}>
          Select a worker above to visualize their movement trajectory on the grid
        </div>
      )}

      {selected && path.length === 0 && !loading && (
        <div style={{
          padding:48, textAlign:"center", color:"#334155", fontSize:13,
          background:"#0d1829", borderRadius:10, border:"1px solid #1e293b",
        }}>
          No location events recorded yet for this asset
        </div>
      )}

      {selected && path.length > 0 && (
        <div style={{ display:"flex", gap:24, flexWrap:"wrap",
          alignItems:"flex-start" }}>
          {/* Grid SVG */}
          <div style={{ background:"#0a1628", borderRadius:12,
            border:"1px solid #1e3a5f", flexShrink:0,
            overflowX:"auto", maxWidth:"100%" }}>
            <svg viewBox={`0 0 ${svgW} ${svgH}`} width={svgW} height={svgH}>

              {/* Grid lines */}
              {Array.from({ length: COLS + 1 }, (_, i) => (
                <line key={`v${i}`}
                  x1={MARGIN + i * (CELL + GAP)} y1={MARGIN}
                  x2={MARGIN + i * (CELL + GAP)} y2={svgH - MARGIN}
                  stroke="#1e3a5f" strokeWidth="0.5" />
              ))}
              {Array.from({ length: ROWS + 1 }, (_, i) => (
                <line key={`h${i}`}
                  x1={MARGIN} y1={MARGIN + i * (CELL + GAP)}
                  x2={svgW - MARGIN} y2={MARGIN + i * (CELL + GAP)}
                  stroke="#1e3a5f" strokeWidth="0.5" />
              ))}

              {/* Trajectory polyline */}
              {linePoints && (
                <polyline points={linePoints}
                  fill="none" stroke="#6366f1" strokeWidth="2"
                  strokeDasharray="5 3" opacity="0.6" />
              )}

              {/* Visited sensors */}
              {sensors.map(s => {
                const visits = visitMap[s.sensor_id];
                if (!visits) return null;
                const { row, col } = sensorPos(s.sensor_id);
                const cx = MARGIN + col * (CELL + GAP) + CELL / 2;
                const cy = MARGIN + row * (CELL + GAP) + CELL / 2;
                const last = visits[visits.length - 1];
                const col_ = STATUS_COL[last?.status] || "#94a3b8";
                const count = visits.length;
                return (
                  <g key={s.sensor_id}>
                    <rect x={MARGIN + col * (CELL + GAP)} y={MARGIN + row * (CELL + GAP)}
                      width={CELL} height={CELL}
                      fill={col_ + "22"} stroke={col_} strokeWidth="1.5" rx={5} />
                    <text x={cx} y={cy - 10} textAnchor="middle"
                      fill={col_} fontSize={10} fontWeight={700} fontFamily="monospace">
                      {s.sensor_id}
                    </text>
                    <text x={cx} y={cy + 4} textAnchor="middle"
                      fill={col_} fontSize={9} fontFamily="monospace">
                      {count} visit{count > 1 ? "s" : ""}
                    </text>
                    {/* Step numbers for first and last visit */}
                    <text x={cx} y={cy + 16} textAnchor="middle"
                      fill="#64748b" fontSize={8} fontFamily="monospace">
                      #{visits[0].step}
                      {visits.length > 1 ? `→#${visits[visits.length-1].step}` : ""}
                    </text>
                  </g>
                );
              })}

              {/* Start (S) and End (E) markers */}
              {path[0]?.sensor_id && (() => {
                const { row, col } = sensorPos(path[0].sensor_id);
                const cx = MARGIN + col * (CELL + GAP) + CELL / 2;
                const cy = MARGIN + row * (CELL + GAP) + CELL / 2;
                return <circle cx={cx} cy={cy} r={8} fill="#22c55e" opacity={0.85}>
                  <title>Start</title>
                </circle>;
              })()}
              {path[path.length-1]?.sensor_id && (() => {
                const { row, col } = sensorPos(path[path.length-1].sensor_id);
                const cx = MARGIN + col * (CELL + GAP) + CELL / 2;
                const cy = MARGIN + row * (CELL + GAP) + CELL / 2;
                return <circle cx={cx} cy={cy} r={8} fill="#ef4444" opacity={0.85}>
                  <title>Last known position</title>
                </circle>;
              })()}

              {/* Legend */}
              {[
                { col:"#22c55e", label:"Start" },
                { col:"#ef4444", label:"Last position" },
                { col:"#4ade80", label:"Authorised" },
                { col:"#f87171", label:"Violation" },
                { col:"#fbbf24", label:"Unknown" },
              ].map(({ col: c, label }, i) => (
                <g key={label} transform={`translate(${MARGIN + i * 105}, ${svgH - 14})`}>
                  <rect width={10} height={10} rx={2} fill={c} opacity={0.8} />
                  <text x={13} y={9} fill="#64748b" fontSize={8} fontFamily="monospace">{label}</text>
                </g>
              ))}
            </svg>
          </div>

          {/* Step log table */}
          <div style={{ flex:1, minWidth:260 }}>
            <div style={{
              background:"#0d1829", border:"1px solid #1e293b",
              borderRadius:10, overflow:"auto", maxHeight:"min(460px, 60vh)",
            }}>
              <div style={{
                padding:"8px 14px", background:"#0a1628",
                fontSize:9, fontWeight:700, color:"#475569", letterSpacing:1,
                display:"grid", gridTemplateColumns:"36px 60px 90px 1fr",
                position:"sticky", top:0, zIndex:2,
              }}>
                <span>#</span><span>SENSOR</span><span>STATUS</span><span>TIME</span>
              </div>
              {path.map((p, i) => {
                const col = STATUS_COL[p.access_status] || "#94a3b8";
                return (
                  <div key={i} style={{
                    display:"grid", gridTemplateColumns:"36px 60px 90px 1fr",
                    padding:"5px 14px",
                    borderTop: i > 0 ? "1px solid #0a1628" : "none",
                    background: i % 2 === 0 ? "#0d1829" : "#0a1628",
                  }}>
                    <span style={{ fontSize:10, color:"#475569" }}>{i+1}</span>
                    <span style={{ fontSize:11, fontWeight:700, color:"#e2e8f0", fontFamily:"monospace" }}>
                      {p.sensor_id || "—"}
                    </span>
                    <span style={{ fontSize:10, color:col, fontWeight:600 }}>
                      {p.access_status || "—"}
                    </span>
                    <span style={{ fontSize:9, color:"#475569" }}>
                      {p.timestamp ? new Date(p.timestamp).toLocaleTimeString() : "—"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
