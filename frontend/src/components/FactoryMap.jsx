// =============================================================================
// FactoryMap.jsx
//   2D  — blueprint background, zone OUTLINES (no fill), border-only cells
//   3D  — isometric stack: blueprint ground plane → assets → sensors
//   Full screen — the complete view (blueprint + sensors + worker names),
//                 not just the raw image, in whichever mode is active.
// =============================================================================

import { useState, useMemo, useEffect } from "react";
import SensorCell   from "./SensorCell";
import SensorDetail from "./SensorDetail";

const CELL = 96, GAP = 4, MARGIN = 20;
const PALETTE = ["#14b8a6","#3b82f6","#8b5cf6","#f59e0b",
                 "#ec4899","#ef4444","#22c55e","#f97316"];
const AICON  = { worker:"👷", forklift:"🚜", pallet:"📦", object:"📍" };
const SHADOW = "0 1px 3px rgba(0,0,0,0.95)";
const STAGE3D_SCALE = 0.82;

export default function FactoryMap({
  sensors, health, assets, cols = 6, rows = 5,
  blueprintSrc = null, zones = [], sensorConfig = [],
}) {
  const [selected,   setSelected]   = useState(null);
  const [imgError,   setImgError]   = useState(false);
  const [view,       setView]       = useState("2d");
  const [fullscreen, setFullscreen] = useState(false);
  const [zoom,       setZoom]       = useState(1);

  // ── Lookups ──────────────────────────────────────────────────────────────
  const sensorMap = useMemo(() => Object.fromEntries(
    (sensors || []).map(s => [s.sensor_id, s])), [sensors]);
  const healthMap = useMemo(() => Object.fromEntries(
    (health || []).map(h => [h.sensor_id, h])), [health]);
  const cfgMap = useMemo(() => Object.fromEntries(
    (sensorConfig || []).map(s => [s.sensor_id, s])), [sensorConfig]);

  const assetsBySensor = useMemo(() => {
    const m = {};
    (assets || []).forEach(a => {
      if (a.current_sensor_id)
        (m[a.current_sensor_id] = m[a.current_sensor_id] || []).push(a);
    });
    return m;
  }, [assets]);

  // sensor → its zone, built from each zone's sensor list
  const sensorZone = useMemo(() => {
    const m = {};
    (zones || []).forEach((z, i) => {
      const color = PALETTE[i % PALETTE.length];
      (z.sensor_ids || []).forEach(sid => {
        m[sid] = { color, zone_id: z.zone_id, name: z.name };
      });
    });
    return m;
  }, [zones]);

  // ── Geometry ─────────────────────────────────────────────────────────────
  const gridW = cols * CELL + (cols - 1) * GAP;
  const gridH = rows * CELL + (rows - 1) * GAP;
  const svgW  = MARGIN * 2 + gridW;
  const svgH  = MARGIN * 2 + gridH;

  const sid = (r, c) => `S${String(r * cols + c + 1).padStart(2, "0")}`;
  const posOf = s => {
    const n = parseInt(String(s).replace(/\D/g, ""), 10) - 1;
    return { row: Math.floor(n / cols), col: n % cols };
  };
  const showImg = blueprintSrc && !imgError;

  // Esc closes full screen
  useEffect(() => {
    if (!fullscreen) return;
    const onKey = e => { if (e.key === "Escape") setFullscreen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fullscreen]);

  // ── Zone perimeters: an edge only where the neighbour is a different zone ─
  const zoneEdges = useMemo(() => {
    const segs = [];
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const z = sensorZone[sid(r, c)];
      if (!z) continue;
      const x = MARGIN + c * (CELL + GAP) - GAP / 2;
      const y = MARGIN + r * (CELL + GAP) - GAP / 2;
      const w = CELL + GAP, h = CELL + GAP;
      const diff = (rr, cc) => {
        if (rr < 0 || cc < 0 || rr >= rows || cc >= cols) return true;
        const o = sensorZone[sid(rr, cc)];
        return !o || o.zone_id !== z.zone_id;
      };
      if (diff(r - 1, c)) segs.push({ x1:x,   y1:y,   x2:x+w, y2:y,   c:z.color });
      if (diff(r + 1, c)) segs.push({ x1:x,   y1:y+h, x2:x+w, y2:y+h, c:z.color });
      if (diff(r, c - 1)) segs.push({ x1:x,   y1:y,   x2:x,   y2:y+h, c:z.color });
      if (diff(r, c + 1)) segs.push({ x1:x+w, y1:y,   x2:x+w, y2:y+h, c:z.color });
    }
    return segs;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sensorZone, rows, cols]);

  const zoneLabels = useMemo(() => (zones || []).map((z, i) => {
    const cells = (z.sensor_ids || []).map(posOf);
    if (!cells.length) return null;
    const minR = Math.min(...cells.map(p => p.row));
    const minC = Math.min(...cells.map(p => p.col));
    return { name: z.name, count: cells.length,
             color: PALETTE[i % PALETTE.length],
             x: MARGIN + minC * (CELL + GAP) + 5,
             y: MARGIN + minR * (CELL + GAP) + 12 };
  }).filter(Boolean),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [zones, cols]);

  // ── Toolbar ──────────────────────────────────────────────────────────────
  const tbtn = (active) => ({
    padding: "6px 14px", fontSize: 11, fontWeight: 700, fontFamily: "monospace",
    cursor: "pointer", borderRadius: 6,
    border: `1px solid ${active ? "#6366f1" : "#1e293b"}`,
    background: active ? "#6366f133" : "#0d1829",
    color: active ? "#a5b4fc" : "#475569",
  });

  const Toolbar = () => (
    <div style={{ display: "flex", gap: 8, marginBottom: 10,
      alignItems: "center", flexWrap: "wrap" }}>
      <div style={{ display: "flex", gap: 0 }}>
        {["2d", "3d"].map(v => (
          <button key={v} onClick={() => setView(v)}
            style={{ ...tbtn(view === v),
              borderRadius: v === "2d" ? "6px 0 0 6px" : "0 6px 6px 0" }}>
            {v === "2d" ? "▦  2D" : "◈  3D"}
          </button>
        ))}
      </div>

      {view === "2d" && (
        <div style={{ display: "flex", gap: 0, marginLeft: 4 }}>
          <button onClick={() => setZoom(z => Math.max(0.4, +(z - 0.2).toFixed(2)))}
            style={{ ...tbtn(false), borderRadius: "6px 0 0 6px" }}>−</button>
          <button onClick={() => setZoom(1)}
            style={{ ...tbtn(zoom !== 1), borderRadius: 0, minWidth: 56 }}>
            {Math.round(zoom * 100)}%
          </button>
          <button onClick={() => setZoom(z => Math.min(2.5, +(z + 0.2).toFixed(2)))}
            style={{ ...tbtn(false), borderRadius: "0 6px 6px 0" }}>+</button>
        </div>
      )}

      <button onClick={() => setFullscreen(true)} style={tbtn(false)}
        title="Full screen — blueprint with sensors and workers">
        ⛶  Full screen
      </button>

      <span style={{ marginLeft: "auto", fontSize: 9, color: "#475569",
        fontFamily: "monospace" }}>
        {view === "3d" ? "blueprint ▸ workers ▸ sensors"
          : `${cols}×${rows} · ${rows * cols} sensors · ${zones.length} zones`}
      </span>
    </div>
  );

  // ── Shared 2D scene, reused by the inline and full-screen views ──────────
  function Scene2D({ width, withNames = false }) {
    return (
      <svg viewBox={`0 0 ${svgW} ${svgH}`} width={width}
        style={{ display: "block", background: "#0a1628",
                 borderRadius: 12, transition: "width .15s" }}>

        {showImg && (
          <image href={blueprintSrc} x={0} y={0} width={svgW} height={svgH}
            preserveAspectRatio="xMidYMid slice" opacity={0.85}
            onError={() => setImgError(true)} />
        )}

        {!showImg && (
          <>
            {Array.from({ length: cols + 1 }, (_, i) => (
              <line key={"v" + i} x1={MARGIN + i * (CELL + GAP)} y1={MARGIN}
                x2={MARGIN + i * (CELL + GAP)} y2={svgH - MARGIN}
                stroke="#1e3a5f" strokeWidth="0.6" />
            ))}
            {Array.from({ length: rows + 1 }, (_, i) => (
              <line key={"h" + i} x1={MARGIN} y1={MARGIN + i * (CELL + GAP)}
                x2={svgW - MARGIN} y2={MARGIN + i * (CELL + GAP)}
                stroke="#1e3a5f" strokeWidth="0.6" />
            ))}
          </>
        )}

        {zoneEdges.map((e, i) => (
          <line key={i} x1={e.x1} y1={e.y1} x2={e.x2} y2={e.y2}
            stroke={e.c} strokeWidth={withNames ? 3 : 2.5} opacity={0.9}
            strokeLinecap="round" />
        ))}

        {zoneLabels.map((z, i) => (
          <text key={i} x={z.x} y={z.y} fill={z.color}
            fontSize={withNames ? 11 : 9} fontWeight={700} fontFamily="monospace"
            style={{ textShadow: "0 1px 3px rgba(0,0,0,.95)" }}>
            {z.name} · {z.count} sensors
          </text>
        ))}

        <rect x={MARGIN} y={MARGIN} width={gridW} height={gridH}
          fill="none" stroke="#1e3a5f" strokeWidth="1.5" rx={4} />

        <foreignObject x={MARGIN} y={MARGIN} width={gridW} height={gridH}>
          <div xmlns="http://www.w3.org/1999/xhtml" style={{
            display: "grid",
            gridTemplateColumns: `repeat(${cols}, ${CELL}px)`,
            gridTemplateRows: `repeat(${rows}, ${CELL}px)`, gap: GAP }}>
            {Array.from({ length: rows * cols }, (_, i) => {
              const id = sid(Math.floor(i / cols), i % cols);
              const here = assetsBySensor[id] || [];
              return (
                <div key={id} style={{ position: "relative" }}>
                  <SensorCell sensorId={id}
                    sensor={sensorMap[id]} health={healthMap[id]}
                    assets={here} config={cfgMap[id]} zone={sensorZone[id]}
                    onSelect={setSelected} cellPx={CELL} />

                  {/* Worker names — the detail the compact view omits */}
                  {withNames && here.length > 0 && (
                    <div style={{ position: "absolute", left: "50%", bottom: -4,
                      transform: "translateX(-50%)", display: "flex",
                      flexDirection: "column", gap: 1,
                      pointerEvents: "none", zIndex: 5 }}>
                      {here.slice(0, 3).map(a => {
                        const viol = a.access_status === "violation";
                        return (
                          <span key={a.id} style={{
                            fontSize: 8, fontFamily: "monospace", fontWeight: 700,
                            whiteSpace: "nowrap", padding: "1px 5px",
                            borderRadius: 3, background: "rgba(2,8,20,.92)",
                            color: viol ? "#fca5a5" : "#e2e8f0",
                            border: `1px solid ${viol ? "#ef4444" : "#334155"}` }}>
                            {AICON[a.asset_type] || "📍"} {a.name || a.id}
                          </span>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </foreignObject>
      </svg>
    );
  }

  // ── Shared 3D stage ──────────────────────────────────────────────────────
  function Stage3D({ maxH = "calc(100vh - 260px)" }) {
    const SCALE = STAGE3D_SCALE;
    const W = svgW * SCALE, H = svgH * SCALE;
    // Layers sit at most ~1 sensor width above the plane below them
    const LAYER_GAP = Math.round(CELL * SCALE * 0.5);
    const stageH = H * 0.72 + LAYER_GAP * 2 + 120;

    const plate = (children, lift, z) => (
      <div style={{
        position: "absolute", left: "50%", top: stageH - lift - H * 0.55,
        width: W, height: H,
        transform: "translateX(-50%) rotateX(58deg) rotateZ(-45deg)",
        transformStyle: "preserve-3d", zIndex: z,
      }}>{children}</div>
    );

    return (
      <div style={{
        position: "relative", height: stageH, width: "100%",
        perspective: "1600px", perspectiveOrigin: "50% 42%",
        background: "radial-gradient(ellipse at 50% 40%, #0d1e3a 0%, #050c1a 72%)",
        borderRadius: 12, border: "1px solid #1e3a5f",
        overflow: "auto", maxHeight: maxH,
      }}>
        {/* Layer 0 — blueprint ground plane */}
        {plate(
          <div style={{ width: "100%", height: "100%", position: "relative",
            background: "#0a1628", border: "2px solid #1e3a5f", borderRadius: 8,
            boxShadow: "0 30px 70px rgba(0,0,0,0.8)", overflow: "hidden" }}>
            {showImg ? (
              <img src={blueprintSrc} alt="" onError={() => setImgError(true)}
                style={{ width: "100%", height: "100%",
                         objectFit: "cover", opacity: 0.9 }} />
            ) : (
              <svg width="100%" height="100%">
                {Array.from({ length: cols + 1 }, (_, i) => (
                  <line key={"v" + i} x1={i * (CELL + GAP) * SCALE} y1={0}
                    x2={i * (CELL + GAP) * SCALE} y2={H}
                    stroke="#1e3a5f" strokeWidth="1" />
                ))}
                {Array.from({ length: rows + 1 }, (_, i) => (
                  <line key={"h" + i} x1={0} y1={i * (CELL + GAP) * SCALE}
                    x2={W} y2={i * (CELL + GAP) * SCALE}
                    stroke="#1e3a5f" strokeWidth="1" />
                ))}
              </svg>
            )}
            <svg style={{ position: "absolute", inset: 0 }} width="100%" height="100%">
              {zoneEdges.map((e, i) => (
                <line key={i} x1={e.x1 * SCALE} y1={e.y1 * SCALE}
                  x2={e.x2 * SCALE} y2={e.y2 * SCALE}
                  stroke={e.c} strokeWidth="2.5" opacity={0.85} />
              ))}
            </svg>
          </div>, 0, 1)}

        {/* Layer 1 — assets */}
        {plate(
          <div style={{ width: "100%", height: "100%", position: "relative" }}>
            {(assets || []).map(a => {
              if (!a.current_sensor_id) return null;
              const { row, col } = posOf(a.current_sensor_id);
              if (row >= rows || col >= cols) return null;
              const viol = a.access_status === "violation";
              return (
                <div key={a.id} style={{
                  position: "absolute",
                  left: (MARGIN + col * (CELL + GAP) + CELL / 2) * SCALE,
                  top:  (MARGIN + row * (CELL + GAP) + CELL / 2) * SCALE,
                  transform: "translate(-50%,-50%) rotateZ(45deg) rotateX(-58deg)",
                  transformStyle: "preserve-3d",
                  display: "flex", flexDirection: "column", alignItems: "center",
                  transition: "left .6s ease, top .6s ease",
                }}>
                  <div style={{ fontSize: 26,
                    filter: "drop-shadow(0 4px 8px rgba(0,0,0,.9))" }}>
                    {AICON[a.asset_type] || "📍"}
                  </div>
                  <div style={{ fontSize: 9, fontWeight: 700, marginTop: 1,
                    color: viol ? "#fca5a5" : "#e2e8f0",
                    background: "rgba(2,8,20,0.85)", padding: "1px 6px",
                    borderRadius: 3, whiteSpace: "nowrap", fontFamily: "monospace",
                    border: `1px solid ${viol ? "#ef4444" : "#334155"}` }}>
                    {a.name || a.id}
                  </div>
                </div>
              );
            })}
          </div>, LAYER_GAP, 2)}

        {/* Layer 2 — sensors */}
        {plate(
          <div style={{ width: "100%", height: "100%", position: "relative" }}>
            {Array.from({ length: rows * cols }, (_, i) => {
              const r = Math.floor(i / cols), c = i % cols;
              const id = sid(r, c);
              const S = sensorMap[id] || {}, Hh = healthMap[id] || {};
              const z = sensorZone[id];
              const col_ =
                Hh.status === "offline"  ? "#6b7280" :
                Hh.status === "degraded" ? "#f59e0b" :
                S.env_status === "critical" ? "#ef4444" :
                S.env_status === "warning"  ? "#f97316" : "#10b981";
              const crit = S.env_status === "critical" || S.smoke;
              return (
                <div key={id} onClick={() => setSelected(id)}
                  style={{ position: "absolute",
                    left: (MARGIN + c * (CELL + GAP)) * SCALE,
                    top:  (MARGIN + r * (CELL + GAP)) * SCALE,
                    width: CELL * SCALE, height: CELL * SCALE,
                    border: `${crit ? 2.4 : 1.3}px solid ${col_}`,
                    borderStyle: cfgMap[id]?.passable === false ? "dashed" : "solid",
                    borderRadius: 6, cursor: "pointer",
                    background: "rgba(5,12,26,0.30)",
                    boxShadow: crit ? `0 0 18px ${col_}cc`
                                    : "0 6px 16px rgba(0,0,0,.6)",
                    display: "flex", flexDirection: "column",
                    alignItems: "center", justifyContent: "center",
                  }}>
                  <div style={{ transform: "rotateZ(45deg) rotateX(-58deg)",
                    textAlign: "center", fontFamily: "monospace" }}>
                    <div style={{ fontSize: 9, fontWeight: 700, color: col_,
                      textShadow: SHADOW }}>{id}</div>
                    {S.temperature != null && (
                      <div style={{ fontSize: 8, color: col_, textShadow: SHADOW }}>
                        {S.temperature.toFixed(0)}°
                      </div>
                    )}
                    {S.smoke && <div style={{ fontSize: 9 }}>💨</div>}
                    {z && <div style={{ fontSize: 7, color: z.color,
                      textShadow: SHADOW }}>{z.name}</div>}
                  </div>
                </div>
              );
            })}
          </div>, LAYER_GAP * 2, 3)}

        <div style={{ position: "absolute", top: 12, left: 14, zIndex: 10,
          fontFamily: "monospace", fontSize: 9, color: "#475569", lineHeight: 1.9 }}>
          <div><span style={{ color: "#10b981" }}>▲</span> sensors</div>
          <div><span style={{ color: "#a5b4fc" }}>▲</span> workers &amp; assets</div>
          <div><span style={{ color: "#64748b" }}>▲</span> factory blueprint</div>
        </div>
      </div>
    );
  }

  // ── Full screen — full detail, honouring the current mode ────────────────
  function FullscreenView() {
    const vw = typeof window !== "undefined" ? window.innerWidth  : 1600;
    const vh = typeof window !== "undefined" ? window.innerHeight : 900;
    const scale = Math.min((vw - 60) / svgW, (vh - 200) / svgH);

    return (
      <div style={{ position: "fixed", inset: 0, zIndex: 200,
        background: "rgba(2,8,20,0.97)", display: "flex",
        flexDirection: "column", overflow: "hidden" }}>

        <div style={{ display: "flex", alignItems: "center", gap: 12,
          padding: "10px 18px", borderBottom: "1px solid #1e293b",
          background: "#0d1829", flexShrink: 0, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, fontWeight: 700 }}>Factory — full screen</span>
          <div style={{ display: "flex", gap: 0 }}>
            {["2d", "3d"].map(v => (
              <button key={v} onClick={() => setView(v)}
                style={{ ...tbtn(view === v),
                  borderRadius: v === "2d" ? "6px 0 0 6px" : "0 6px 6px 0" }}>
                {v === "2d" ? "▦ 2D" : "◈ 3D"}
              </button>
            ))}
          </div>
          <span style={{ fontSize: 10, color: "#475569", fontFamily: "monospace" }}>
            {cols}×{rows} · {rows * cols} sensors · {zones.length} zones ·{" "}
            {(assets || []).length} assets
          </span>
          <div style={{ marginLeft: "auto", display: "flex", gap: 10,
            alignItems: "center" }}>
            <span style={{ fontSize: 10, color: "#475569" }}>Esc to close</span>
            <button onClick={() => setFullscreen(false)}
              style={{ ...tbtn(false), fontSize: 16, padding: "2px 12px" }}>×</button>
          </div>
        </div>

        <div style={{ flex: 1, minHeight: 0, overflow: "auto", padding: 20,
          display: "flex", alignItems: "flex-start", justifyContent: "center" }}>
          {view === "3d"
            ? <div style={{ width: svgW * STAGE3D_SCALE,
                transform: `scale(${Math.min(scale * 1.15, 1.9)})`,
                transformOrigin: "top center" }}>
                {Stage3D({ maxH: "none" })}
              </div>
            : Scene2D({ width: svgW * Math.max(scale, 0.5), withNames: true })}
        </div>

        {/* Asset roster */}
        <div style={{ flexShrink: 0, borderTop: "1px solid #1e293b",
          background: "#0d1829", padding: "9px 18px",
          maxHeight: 120, overflowY: "auto" }}>
          <div style={{ fontSize: 9, color: "#475569", letterSpacing: 1,
            marginBottom: 6 }}>ASSETS ({(assets || []).length})</div>
          <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}>
            {(assets || []).map(a => {
              const viol = a.access_status === "violation";
              const unk  = a.access_status === "unknown";
              return (
                <span key={a.id} style={{ fontSize: 10, fontFamily: "monospace",
                  padding: "3px 9px", borderRadius: 5,
                  background: viol ? "#7f1d1d33" : unk ? "#78350f33" : "#0a1628",
                  border: `1px solid ${viol ? "#ef4444" : unk ? "#f59e0b" : "#1e293b"}`,
                  color: viol ? "#fca5a5" : unk ? "#fcd34d" : "#94a3b8" }}>
                  {AICON[a.asset_type] || "📍"}{" "}
                  <b style={{ color: "#e2e8f0" }}>{a.name || a.id}</b>
                  {" · "}{a.current_sensor_id || "—"}{viol && " ⚠"}
                </span>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  // ── Render ───────────────────────────────────────────────────────────────
  const detail = selected && (
    <SensorDetail sensorId={selected} sensor={sensorMap[selected]}
      health={healthMap[selected]} assets={assetsBySensor[selected] || []}
      config={cfgMap[selected]} zone={sensorZone[selected]}
      onClose={() => setSelected(null)} />
  );

  // NOTE: Toolbar/Scene2D/Stage3D/FullscreenView are called as plain
  // functions, not rendered as JSX components (<Scene2D/>). They are
  // declared inside this component body, so a JSX call would give React a
  // new component type on every render — remounting the scrollable subtree
  // and resetting scroll position on every state update. Calling them as
  // functions inlines their returned elements instead, so React can diff
  // normally and scroll position survives re-renders.
  if (view === "3d") {
    return (
      <>
        {Toolbar()}
        {Stage3D({})}
        {fullscreen && FullscreenView()}
        {detail}
      </>
    );
  }

  return (
    <>
      {Toolbar()}
      <div style={{ width: "100%", overflow: "auto",
        maxHeight: "calc(100vh - 260px)" }}>
        {Scene2D({ width: svgW * zoom })}
      </div>
      {fullscreen && FullscreenView()}
      {detail}
    </>
  );
}
