// =============================================================================
// FactoryMap.jsx
// Renders the factory floor:
//   - Uploaded blueprint image as background (SVG <image>, runtime URL)
//   - N×M sensor grid driven by RUNTIME config (not build-time env vars)
//   - Zone tint overlays derived from which sensors each zone contains
//   - Click a cell → SensorDetail panel
//
// cols / rows / blueprintSrc / zones come from useConfig() in App.jsx, so any
// change saved in the Configuration page appears here immediately.
// =============================================================================

import { useState, useMemo } from "react";
import SensorCell   from "./SensorCell";
import SensorDetail from "./SensorDetail";

const CELL_PX = 96;
const GAP_PX  = 4;
const MARGIN  = 20;

const ZONE_PALETTE = ["#14b8a6","#3b82f6","#8b5cf6","#f59e0b",
                       "#ec4899","#ef4444","#22c55e","#f97316"];

export default function FactoryMap({
  sensors, health, assets,
  cols = 6, rows = 5,
  blueprintSrc = null,
  zones = [],
  sensorConfig = [],
}) {
  const [selected, setSelected] = useState(null);
  const [imgError, setImgError] = useState(false);

  const sensorMap = useMemo(() =>
    Object.fromEntries((sensors || []).map(s => [s.sensor_id, s])), [sensors]);
  const healthMap = useMemo(() =>
    Object.fromEntries((health || []).map(h => [h.sensor_id, h])), [health]);
  const cfgMap = useMemo(() =>
    Object.fromEntries((sensorConfig || []).map(s => [s.sensor_id, s])), [sensorConfig]);

  const assetsBySensor = useMemo(() => {
    const m = {};
    (assets || []).forEach(a => {
      const sid = a.current_sensor_id;
      if (!sid) return;
      (m[sid] = m[sid] || []).push(a);
    });
    return m;
  }, [assets]);

  // sensor_id → { color, zone_id, name }  built from the zones' sensor lists
  const sensorZone = useMemo(() => {
    const m = {};
    (zones || []).forEach((z, i) => {
      const color = ZONE_PALETTE[i % ZONE_PALETTE.length];
      (z.sensor_ids || []).forEach(sid => {
        m[sid] = { color, zone_id: z.zone_id, name: z.name };
      });
    });
    return m;
  }, [zones]);

  const gridW = cols * CELL_PX + (cols - 1) * GAP_PX;
  const gridH = rows * CELL_PX + (rows - 1) * GAP_PX;
  const svgW  = MARGIN * 2 + gridW;
  const svgH  = MARGIN * 2 + gridH;

  const sensorId = (r, c) => `S${String(r * cols + c + 1).padStart(2, "0")}`;
  const showImage = blueprintSrc && !imgError;

  return (
    <>
      <div style={{ width: "100%", overflowX: "auto" }}>
        <svg viewBox={`0 0 ${svgW} ${svgH}`} width={svgW}
             style={{ display: "block", background: "#0a1628", borderRadius: 12,
                      maxWidth: "100%" }}>

          {/* ── Uploaded blueprint background ── */}
          {showImage && (
            <image href={blueprintSrc} x={0} y={0} width={svgW} height={svgH}
                   preserveAspectRatio="xMidYMid slice" opacity={0.75}
                   onError={() => setImgError(true)} />
          )}

          {/* ── Fallback grid pattern ── */}
          {!showImage && (
            <>
              {Array.from({ length: cols + 1 }, (_, i) => (
                <line key={`v${i}`} x1={MARGIN + i*(CELL_PX+GAP_PX)} y1={MARGIN}
                      x2={MARGIN + i*(CELL_PX+GAP_PX)} y2={svgH - MARGIN}
                      stroke="#1e3a5f" strokeWidth="0.6" />
              ))}
              {Array.from({ length: rows + 1 }, (_, i) => (
                <line key={`h${i}`} x1={MARGIN} y1={MARGIN + i*(CELL_PX+GAP_PX)}
                      x2={svgW - MARGIN} y2={MARGIN + i*(CELL_PX+GAP_PX)}
                      stroke="#1e3a5f" strokeWidth="0.6" />
              ))}
            </>
          )}

          {/* ── Zone tint per cell (zone = its set of sensors) ── */}
          {Array.from({ length: rows * cols }, (_, i) => {
            const r = Math.floor(i / cols), c = i % cols;
            const z = sensorZone[sensorId(r, c)];
            if (!z) return null;
            return (
              <rect key={`z${i}`}
                x={MARGIN + c*(CELL_PX+GAP_PX) - GAP_PX/2}
                y={MARGIN + r*(CELL_PX+GAP_PX) - GAP_PX/2}
                width={CELL_PX + GAP_PX} height={CELL_PX + GAP_PX}
                fill={z.color} opacity={0.07} />
            );
          })}

          {/* ── Factory boundary ── */}
          <rect x={MARGIN} y={MARGIN} width={gridW} height={gridH}
                fill="none" stroke="#1e3a5f" strokeWidth="1.5" rx={4} />

          {/* ── Sensor cells ── */}
          <foreignObject x={MARGIN} y={MARGIN} width={gridW} height={gridH}>
            <div xmlns="http://www.w3.org/1999/xhtml" style={{
              display: "grid",
              gridTemplateColumns: `repeat(${cols}, ${CELL_PX}px)`,
              gridTemplateRows:    `repeat(${rows}, ${CELL_PX}px)`,
              gap: GAP_PX,
            }}>
              {Array.from({ length: rows * cols }, (_, i) => {
                const sid = sensorId(Math.floor(i / cols), i % cols);
                return (
                  <SensorCell key={sid} sensorId={sid}
                    sensor={sensorMap[sid]} health={healthMap[sid]}
                    assets={assetsBySensor[sid]} config={cfgMap[sid]}
                    zone={sensorZone[sid]}
                    onSelect={setSelected} cellPx={CELL_PX} />
                );
              })}
            </div>
          </foreignObject>

          {/* ── Grid info label ── */}
          <text x={MARGIN + 2} y={MARGIN - 7} fill="#1e3a5f"
                fontSize={9} fontFamily="monospace" fontWeight={700}>
            {cols}×{rows} GRID · {rows * cols} SENSORS
            {zones.length > 0 && ` · ${zones.length} ZONES`}
          </text>

          {!blueprintSrc && (
            <text x={svgW/2} y={svgH - 5} textAnchor="middle" fill="#1e3a5f"
                  fontSize={9} fontFamily="monospace">
              Upload a floor plan in Configuration → Factory Layout
            </text>
          )}
        </svg>
      </div>

      {selected && (
        <SensorDetail sensorId={selected}
          sensor={sensorMap[selected]} health={healthMap[selected]}
          assets={assetsBySensor[selected] || []}
          config={cfgMap[selected]} zone={sensorZone[selected]}
          onClose={() => setSelected(null)} />
      )}
    </>
  );
}
