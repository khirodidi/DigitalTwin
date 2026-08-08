// =============================================================================
// frontend/src/config/factory.js
// All factory configuration read from environment variables.
// Set values in frontend/.env (copy from .env.example).
// =============================================================================

export const FACTORY_NAME  = process.env.REACT_APP_FACTORY_NAME  || "Factory";
export const FACTORY_IMAGE = process.env.REACT_APP_FACTORY_IMAGE || null;
export const GRID_COLS     = parseInt(process.env.REACT_APP_GRID_COLS,  10) || 6;
export const GRID_ROWS     = parseInt(process.env.REACT_APP_GRID_ROWS,  10) || 5;
export const SENSOR_COUNT  = parseInt(process.env.REACT_APP_SENSOR_COUNT, 10) || GRID_COLS * GRID_ROWS;

// Sensor at position (row, col) → sensor ID  e.g. "S01"
export function sensorId(row, col) {
  return `S${String(row * GRID_COLS + col + 1).padStart(2, "0")}`;
}

// Sensor ID → grid position { row, col }
export function sensorPos(id) {
  const n   = parseInt(id.replace(/\D/g, ""), 10) - 1;
  return { row: Math.floor(n / GRID_COLS), col: n % GRID_COLS };
}

// All neighbours of a sensor (grid adjacency — N/S/E/W only)
export function neighbours(id) {
  const { row, col } = sensorPos(id);
  return [
    row > 0             && sensorId(row - 1, col),
    row < GRID_ROWS - 1 && sensorId(row + 1, col),
    col > 0             && sensorId(row, col - 1),
    col < GRID_COLS - 1 && sensorId(row, col + 1),
  ].filter(Boolean);
}

// Status → CSS background colour (for sensor cells)
export function statusBg(sensorStatus, envStatus) {
  if (sensorStatus === "offline")  return { bg: "#111827", border: "#374151", text: "#6b7280" };
  if (sensorStatus === "degraded") return { bg: "#1c1408", border: "#d97706", text: "#fbbf24" };
  if (envStatus    === "critical") return { bg: "#1a0808", border: "#dc2626", text: "#f87171" };
  if (envStatus    === "warning")  return { bg: "#1a0f04", border: "#f97316", text: "#fb923c" };
  return                                  { bg: "#041a10", border: "#10b981", text: "#34d399" };
}

// Asset type → icon
export const ASSET_ICONS = {
  worker:  "👷",
  object:  "📦",
  forklift:"🚜",
  pallet:  "📦",
};
export function assetIcon(type) { return ASSET_ICONS[type] || "📍"; }

// All sensor IDs (S01 … S30)
export const ALL_SENSORS = Array.from({ length: SENSOR_COUNT },
  (_, i) => `S${String(i + 1).padStart(2, "0")}`
);
