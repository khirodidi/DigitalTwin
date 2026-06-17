// =============================================================================
// Factory grid layout — edit this to match your physical deployment
// Each sensor occupies one grid cell; zones span one or more cells.
// =============================================================================

export const FACTORY = {
  name: "Factory Floor A",
  grid: { cols: 4, rows: 4, cellW: 160, cellH: 130 },

  zones: [
    { id: "zone_A", name: "Assembly A",  color: "#14b8a6", colStart: 0, colEnd: 1, rowStart: 0, rowEnd: 1 },
    { id: "zone_B", name: "Assembly B",  color: "#3b82f6", colStart: 2, colEnd: 3, rowStart: 0, rowEnd: 1 },
    { id: "zone_C", name: "Storage",     color: "#f59e0b", colStart: 0, colEnd: 0, rowStart: 2, rowEnd: 3 },
    { id: "zone_D", name: "Production",  color: "#a855f7", colStart: 1, colEnd: 3, rowStart: 2, rowEnd: 3 },
  ],

  sensors: [
    { id: "S1",  col: 0, row: 0, zone: "zone_A" },
    { id: "S2",  col: 1, row: 0, zone: "zone_A" },
    { id: "S3",  col: 2, row: 0, zone: "zone_B" },
    { id: "S4",  col: 3, row: 0, zone: "zone_B" },
    { id: "S5",  col: 0, row: 1, zone: "zone_A" },
    { id: "S6",  col: 1, row: 1, zone: "zone_A" },
    { id: "S7",  col: 2, row: 1, zone: "zone_B" },
    { id: "S8",  col: 3, row: 1, zone: "zone_B" },
    { id: "S9",  col: 0, row: 2, zone: "zone_C" },
    { id: "S10", col: 1, row: 2, zone: "zone_D" },
    { id: "S11", col: 2, row: 2, zone: "zone_D" },
    { id: "S12", col: 3, row: 2, zone: "zone_D" },
    { id: "S13", col: 0, row: 3, zone: "zone_C" },
    { id: "S14", col: 1, row: 3, zone: "zone_D" },
    { id: "S15", col: 2, row: 3, zone: "zone_D" },
    { id: "S16", col: 3, row: 3, zone: "zone_D" },
  ],

  exits: ["S4", "S8", "S12", "S16"],
};

// Helper: pixel coordinates for a grid cell
export const cellPixels = (col, row, pad = 60) => ({
  x: pad + col * FACTORY.grid.cellW,
  y: pad + row * FACTORY.grid.cellH,
  cx: pad + col * FACTORY.grid.cellW + FACTORY.grid.cellW / 2,
  cy: pad + row * FACTORY.grid.cellH + FACTORY.grid.cellH / 2,
});

export const SVG_W = FACTORY.grid.cols * FACTORY.grid.cellW + 120;
export const SVG_H = FACTORY.grid.rows * FACTORY.grid.cellH + 120;

// Status → colour map
export const STATUS_COLOR = {
  // health
  online:    "#14b8a6",
  degraded:  "#f59e0b",
  offline:   "#6b7280",
  // env
  normal:    "#14b8a6",
  warning:   "#f59e0b",
  critical:  "#ef4444",
  // access
  authorised: "#14b8a6",
  violation:  "#ef4444",
  unknown:    "#6b7280",
  // overall
  nominal:   "#14b8a6",
  NOMINAL:   "#14b8a6",
  DEGRADED:  "#f59e0b",
  CRITICAL:  "#ef4444",
};
