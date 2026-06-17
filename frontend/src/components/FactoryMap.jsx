// =============================================================================
// frontend/src/components/FactoryMap.jsx
// Factory floor plan with:
//   - SVG grid blueprint (zones + walls)
//   - Sensor circles showing state & readings (color-coded)
//   - Moving asset icons (workers 👷, objects 🚜) with smooth transitions
//   - Tooltip on sensor hover showing all readings
// =============================================================================

import { useState, useCallback } from "react";

// ─── Config ───────────────────────────────────────────────────────────────────
const CELL   = 90;    // px per grid cell
const RADIUS = 26;    // sensor circle radius
const COLS   = 6;
const ROWS   = 5;

// ─── Color helpers ────────────────────────────────────────────────────────────
const sensorColor = (health, env) => {
  if (health === "offline")  return { fill: "#1f2937", stroke: "#6b7280", text: "#9ca3af" };
  if (health === "degraded") return { fill: "#78350f", stroke: "#f59e0b", text: "#fcd34d" };
  if (env   === "critical")  return { fill: "#7f1d1d", stroke: "#ef4444", text: "#fca5a5" };
  if (env   === "warning")   return { fill: "#78350f", stroke: "#f97316", text: "#fdba74" };
  return { fill: "#064e3b", stroke: "#10b981", text: "#6ee7b7" };
};

const assetIcon = (type) => type === "worker" ? "👷" : "🚜";

// ─── Tooltip ──────────────────────────────────────────────────────────────────
function SensorTooltip({ sensor, health, x, y }) {
  if (!sensor) return null;
  const col = sensorColor(health?.status, sensor.env_status);
  return (
    <g>
      <rect x={x - 5} y={y - 5} width={150} height={90} rx={6}
        fill="#0f172a" stroke={col.stroke} strokeWidth="1" opacity="0.97" />
      <text x={x + 70} y={y + 12} textAnchor="middle" fill={col.stroke}
        fontSize={10} fontWeight={700} fontFamily="monospace">{sensor.sensor_id}</text>
      <text x={x + 10} y={y + 28} fill="#94a3b8" fontSize={9} fontFamily="monospace">
        Zone: {sensor.zone_id}
      </text>
      <text x={x + 10} y={y + 42} fill="#94a3b8" fontSize={9} fontFamily="monospace">
        Temp: {sensor.temperature != null ? `${sensor.temperature.toFixed(1)}°C` : "—"}
      </text>
      <text x={x + 10} y={y + 55} fill="#94a3b8" fontSize={9} fontFamily="monospace">
        Humidity: {sensor.humidity != null ? `${sensor.humidity.toFixed(1)}%` : "—"}
      </text>
      <text x={x + 10} y={y + 68}
        fill={sensor.smoke ? "#ef4444" : "#64748b"} fontSize={9} fontFamily="monospace" fontWeight={sensor.smoke ? 700 : 400}>
        Smoke: {sensor.smoke ? "⚠ DETECTED" : "clear"}
      </text>
      <text x={x + 10} y={y + 81}
        fill={health?.status === "offline" ? "#6b7280" : health?.status === "degraded" ? "#f59e0b" : "#10b981"}
        fontSize={8} fontFamily="monospace">
        Status: {health?.status || "unknown"}
      </text>
    </g>
  );
}

// ─── Zone regions ─────────────────────────────────────────────────────────────
const ZONES = [
  { id: "zone_A", col: 0, row: 0, cols: 2, rows: 2, color: "#14b8a6" },
  { id: "zone_B", col: 2, row: 0, cols: 2, rows: 2, color: "#3b82f6" },
  { id: "zone_C", col: 4, row: 0, cols: 2, rows: 2, color: "#8b5cf6" },
  { id: "zone_D", col: 0, row: 2, cols: 3, rows: 3, color: "#f59e0b" },
  { id: "zone_E", col: 3, row: 2, cols: 3, rows: 3, color: "#ec4899" },
];

// ─── Main component ───────────────────────────────────────────────────────────
export default function FactoryMap({ sensors, health, assets, layout }) {
  const [tooltip, setTooltip] = useState(null);

  // Build lookup maps
  const sensorMap = Object.fromEntries((sensors || []).map(s => [s.sensor_id, s]));
  const healthMap = Object.fromEntries((health  || []).map(h => [h.sensor_id, h]));
  const assetsBySensor = {};
  (assets || []).forEach(a => {
    if (a.current_sensor_id) {
      if (!assetsBySensor[a.current_sensor_id]) assetsBySensor[a.current_sensor_id] = [];
      assetsBySensor[a.current_sensor_id].push(a);
    }
  });

  // Grid sensors from layout (or fallback)
  const gridSensors = layout?.sensors || [];

  const svgW = COLS * CELL + 60;
  const svgH = ROWS * CELL + 60;

  return (
    <div style={{ width: "100%", overflow: "auto" }}>
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        width="100%"
        style={{ display: "block", background: "#0a1628", borderRadius: 12 }}
      >
        {/* ── Factory boundary ── */}
        <rect x={20} y={20} width={COLS * CELL} height={ROWS * CELL}
          fill="none" stroke="#1e3a5f" strokeWidth="2" rx={4} />

        {/* ── Zone fills ── */}
        {ZONES.map(z => (
          <rect key={z.id}
            x={20 + z.col * CELL} y={20 + z.row * CELL}
            width={z.cols * CELL} height={z.rows * CELL}
            fill={z.color + "0d"} stroke={z.color} strokeWidth="1"
            strokeDasharray="none" rx={2} />
        ))}

        {/* ── Zone labels ── */}
        {ZONES.map(z => (
          <text key={z.id + "l"}
            x={20 + z.col * CELL + (z.cols * CELL) / 2}
            y={20 + z.row * CELL + 14}
            textAnchor="middle" fill={z.color}
            fontSize={9} fontWeight={700} fontFamily="monospace" opacity={0.6}>
            {z.id.replace("_", " ").toUpperCase()}
          </text>
        ))}

        {/* ── Grid lines ── */}
        {Array.from({ length: COLS - 1 }, (_, i) => (
          <line key={"v" + i}
            x1={20 + (i + 1) * CELL} y1={20}
            x2={20 + (i + 1) * CELL} y2={20 + ROWS * CELL}
            stroke="#1e3a5f" strokeWidth="0.5" />
        ))}
        {Array.from({ length: ROWS - 1 }, (_, i) => (
          <line key={"h" + i}
            x1={20} y1={20 + (i + 1) * CELL}
            x2={20 + COLS * CELL} y2={20 + (i + 1) * CELL}
            stroke="#1e3a5f" strokeWidth="0.5" />
        ))}

        {/* ── Sensors ── */}
        {gridSensors.map(s => {
          const cx  = 20 + s.grid_col * CELL + CELL / 2;
          const cy  = 20 + s.grid_row * CELL + CELL / 2;
          const sd  = sensorMap[s.sensor_id];
          const hd  = healthMap[s.sensor_id];
          const col = sensorColor(hd?.status, sd?.env_status);
          const assetsHere = assetsBySensor[s.sensor_id] || [];

          return (
            <g key={s.sensor_id}
              onMouseEnter={() => setTooltip({ sid: s.sensor_id, cx, cy })}
              onMouseLeave={() => setTooltip(null)}
              style={{ cursor: "pointer" }}>
              {/* Pulse ring when critical */}
              {sd?.env_status === "critical" && (
                <circle cx={cx} cy={cy} r={RADIUS + 6}
                  fill="none" stroke="#ef4444" strokeWidth="1.5" opacity={0.4}>
                  <animate attributeName="r" values={`${RADIUS + 4};${RADIUS + 12};${RADIUS + 4}`}
                    dur="2s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.5;0;0.5" dur="2s" repeatCount="indefinite" />
                </circle>
              )}

              {/* Sensor circle */}
              <circle cx={cx} cy={cy} r={RADIUS}
                fill={col.fill} stroke={col.stroke} strokeWidth="1.5" />

              {/* Sensor ID */}
              <text x={cx} y={cy - 4} textAnchor="middle" dominantBaseline="central"
                fill={col.text} fontSize={9} fontWeight={700} fontFamily="monospace">
                {s.sensor_id}
              </text>

              {/* Temperature reading */}
              {sd?.temperature != null && (
                <text x={cx} y={cy + 10} textAnchor="middle" dominantBaseline="central"
                  fill={col.text} fontSize={7.5} fontFamily="monospace">
                  {sd.temperature.toFixed(1)}°C
                </text>
              )}

              {/* Smoke indicator */}
              {sd?.smoke && (
                <text x={cx} y={cy + 20} textAnchor="middle"
                  fill="#ef4444" fontSize={9} fontFamily="monospace" fontWeight={700}>💨</text>
              )}

              {/* Asset icons above sensor */}
              {assetsHere.map((a, i) => (
                <text key={a.id}
                  x={cx - 14 + i * 18} y={cy - RADIUS - 8}
                  textAnchor="middle" fontSize={14}
                  style={{ transition: "all 0.6s ease" }}>
                  {assetIcon(a.asset_type)}
                </text>
              ))}

              {/* Asset count badge */}
              {assetsHere.length > 0 && (
                <g>
                  <circle cx={cx + RADIUS - 6} cy={cy - RADIUS + 6} r={8}
                    fill="#1e40af" stroke="#3b82f6" strokeWidth="1" />
                  <text x={cx + RADIUS - 6} y={cy - RADIUS + 6}
                    textAnchor="middle" dominantBaseline="central"
                    fill="white" fontSize={8} fontWeight={700}>
                    {assetsHere.length}
                  </text>
                </g>
              )}
            </g>
          );
        })}

        {/* ── Tooltip ── */}
        {tooltip && (
          <SensorTooltip
            sensor={sensorMap[tooltip.sid]}
            health={healthMap[tooltip.sid]}
            x={Math.min(tooltip.cx + RADIUS + 4, svgW - 160)}
            y={Math.max(tooltip.cy - 45, 4)}
          />
        )}

        {/* ── Legend (bottom bar) ── */}
        <g transform={`translate(20, ${20 + ROWS * CELL + 8})`}>
          {[
            { col: "#10b981", label: "Normal" },
            { col: "#f97316", label: "Warning" },
            { col: "#ef4444", label: "Critical" },
            { col: "#f59e0b", label: "Degraded" },
            { col: "#6b7280", label: "Offline" },
          ].map((l, i) => (
            <g key={l.label} transform={`translate(${i * 108}, 0)`}>
              <circle cx={8} cy={8} r={6} fill={l.col + "33"} stroke={l.col} strokeWidth="1.2" />
              <text x={18} y={12} fill="#64748b" fontSize={8} fontFamily="monospace">{l.label}</text>
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
}
