// =============================================================================
// frontend/src/components/FactoryMap.jsx  — FIXED
//
// Changes from previous version:
//   1. Blueprint image now uses SVG <image> element (not HTML <img>).
//      HTML <img> inside <svg> is silently ignored by browsers.
//   2. Opacity raised from 0.18 → 0.30 so the blueprint is visible.
//   3. Image href built correctly: /filename from env var.
//   4. Falls back to grid-line pattern when no image is configured.
// =============================================================================

import { useState, useMemo } from "react";
import SensorCell   from "./SensorCell";
import SensorDetail from "./SensorDetail";

const GRID_COLS = parseInt(process.env.REACT_APP_GRID_COLS,  10) || 6;
const GRID_ROWS = parseInt(process.env.REACT_APP_GRID_ROWS,  10) || 5;
const SENSOR_COUNT = parseInt(process.env.REACT_APP_SENSOR_COUNT, 10) || GRID_COLS * GRID_ROWS;

// ── FIX: read image filename from env var ─────────────────────────────────────
const FACTORY_IMAGE = process.env.REACT_APP_FACTORY_IMAGE || null;

const CELL_PX = 96;
const GAP_PX  = 4;
const MARGIN  = 20;

function sensorId(row, col) {
  return `S${String(row * GRID_COLS + col + 1).padStart(2, "0")}`;
}

export default function FactoryMap({ sensors, health, assets }) {
  const [selected, setSelected] = useState(null);
  const [imgError, setImgError] = useState(false);

  const sensorMap = useMemo(() =>
    Object.fromEntries((sensors || []).map(s => [s.sensor_id, s])), [sensors]);
  const healthMap = useMemo(() =>
    Object.fromEntries((health  || []).map(h => [h.sensor_id, h])), [health]);
  const assetsBySensor = useMemo(() => {
    const m = {};
    (assets || []).forEach(a => {
      const sid = a.current_sensor_id;
      if (!sid) return;
      if (!m[sid]) m[sid] = [];
      m[sid].push(a);
    });
    return m;
  }, [assets]);

  const svgW = MARGIN * 2 + GRID_COLS * CELL_PX + (GRID_COLS - 1) * GAP_PX;
  const svgH = MARGIN * 2 + GRID_ROWS * CELL_PX + (GRID_ROWS - 1) * GAP_PX;

  const showImage = FACTORY_IMAGE && !imgError;

  return (
    <>
      <div style={{ width: "100%", overflowX: "auto" }}>
        <svg
          viewBox={`0 0 ${svgW} ${svgH}`}
          width="100%"
          style={{ display: "block", background: "#0a1628", borderRadius: 12 }}
        >
          {/* ── FIX 1: Blueprint — SVG <image> element, not HTML <img> ─────── */}
          {showImage && (
            <image
              href={`/${FACTORY_IMAGE}`}
              x={0} y={0}
              width={svgW} height={svgH}
              preserveAspectRatio="xMidYMid slice"
              opacity={0.30}          /* FIX 2: was 0.18 — too faint to see */
              onError={() => setImgError(true)}
            />
          )}

          {/* ── Fallback: grid-line pattern when no image ───────────────────── */}
          {!showImage && (
            <>
              {Array.from({ length: GRID_COLS + 1 }, (_, i) => (
                <line key={`v${i}`}
                  x1={MARGIN + i * (CELL_PX + GAP_PX)} y1={MARGIN}
                  x2={MARGIN + i * (CELL_PX + GAP_PX)} y2={svgH - MARGIN}
                  stroke="#1e3a5f" strokeWidth="0.6" />
              ))}
              {Array.from({ length: GRID_ROWS + 1 }, (_, i) => (
                <line key={`h${i}`}
                  x1={MARGIN} y1={MARGIN + i * (CELL_PX + GAP_PX)}
                  x2={svgW - MARGIN} y2={MARGIN + i * (CELL_PX + GAP_PX)}
                  stroke="#1e3a5f" strokeWidth="0.6" />
              ))}
            </>
          )}

          {/* ── Factory boundary ─────────────────────────────────────────────── */}
          <rect x={MARGIN} y={MARGIN}
            width={GRID_COLS * CELL_PX + (GRID_COLS - 1) * GAP_PX}
            height={GRID_ROWS * CELL_PX + (GRID_ROWS - 1) * GAP_PX}
            fill="none" stroke="#1e3a5f" strokeWidth="1.5" rx={4} />

          {/* ── Sensor grid (foreignObject so SensorCell uses HTML/CSS) ─────── */}
          <foreignObject
            x={MARGIN} y={MARGIN}
            width={GRID_COLS * CELL_PX + (GRID_COLS - 1) * GAP_PX}
            height={GRID_ROWS * CELL_PX + (GRID_ROWS - 1) * GAP_PX}
          >
            <div
              xmlns="http://www.w3.org/1999/xhtml"
              style={{
                display: "grid",
                gridTemplateColumns: `repeat(${GRID_COLS}, ${CELL_PX}px)`,
                gridTemplateRows:    `repeat(${GRID_ROWS}, ${CELL_PX}px)`,
                gap: GAP_PX,
              }}
            >
              {Array.from({ length: Math.min(SENSOR_COUNT, GRID_COLS * GRID_ROWS) }, (_, i) => {
                const row = Math.floor(i / GRID_COLS);
                const col = i % GRID_COLS;
                const sid = sensorId(row, col);
                return (
                  <SensorCell
                    key={sid}
                    sensorId={sid}
                    sensor={sensorMap[sid]}
                    health={healthMap[sid]}
                    assets={assetsBySensor[sid]}
                    onSelect={setSelected}
                    cellPx={CELL_PX}
                  />
                );
              })}
            </div>
          </foreignObject>

          {/* ── Image config hint when env var not set ───────────────────────── */}
          {!FACTORY_IMAGE && (
            <text x={svgW / 2} y={svgH - 6} textAnchor="middle"
              fill="#1e3a5f" fontSize={9} fontFamily="monospace">
              Set REACT_APP_FACTORY_IMAGE=filename.png to show blueprint
            </text>
          )}
        </svg>
      </div>

      {/* ── Sensor detail panel ───────────────────────────────────────────────── */}
      {selected && (
        <SensorDetail
          sensorId={selected}
          sensor={sensorMap[selected]}
          health={healthMap[selected]}
          assets={assetsBySensor[selected] || []}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
