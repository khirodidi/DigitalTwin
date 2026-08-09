// =============================================================================
// frontend/src/components/SensorGridPicker.jsx
//
// Reusable sensor selector rendered over the factory blueprint, so choosing
// cells for a zone, an authorisation or a trajectory looks exactly like the
// monitoring view rather than an abstract grid of numbers.
//
// Modes
//   "select"     plain multi-select (zone membership, sensor authorisations)
//   "ordered"    click order matters and is numbered (trajectories)
//
// Cell states rendered
//   selected     chosen in this editor
//   implied      covered indirectly — e.g. a sensor inside an authorised zone
//   owned        already belongs to another zone
//   blocked      passable = false
// =============================================================================

import { useState, useMemo } from "react";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

const COVER_ICON = { machine: "⚙", storage: "📦", exit: "🚪", passage: "" };
const PALETTE = ["#14b8a6","#3b82f6","#8b5cf6","#f59e0b",
                 "#ec4899","#ef4444","#22c55e","#f97316"];

export default function SensorGridPicker({
  sensors = [],            // [{sensor_id, grid_row, grid_col, zone_id, coverage_type, passable}]
  zones = [],
  cols = 6,
  rows = 5,
  blueprintUrl = "",
  selected = [],           // explicitly selected sensor ids
  implied = [],            // covered indirectly (zone authorisation)
  onToggle,                // (sensor_id) => void
  mode = "select",         // "select" | "ordered"
  accent = "#6366f1",
  cellPx = 54,
  showLegend = true,
  highlightZone = null,    // zone_id being edited, if any
}) {
  const [hover, setHover] = useState(null);

  const src = blueprintUrl
    ? (blueprintUrl.startsWith("http") ? blueprintUrl : `${API}${blueprintUrl}`)
    : null;

  const byId = useMemo(
    () => Object.fromEntries(sensors.map(s => [s.sensor_id, s])), [sensors]);

  // sensor → owning zone colour
  const zoneOf = useMemo(() => {
    const m = {};
    zones.forEach((z, i) => {
      const c = PALETTE[i % PALETTE.length];
      (z.sensor_ids || []).forEach(sid => {
        m[sid] = { color: c, zone_id: z.zone_id, name: z.name };
      });
    });
    return m;
  }, [zones]);

  const sid = (r, c) => `S${String(r * cols + c + 1).padStart(2, "0")}`;
  const selSet = new Set(selected);
  const impSet = new Set(implied);

  const GAP = 3, PAD = 8;
  const W = PAD * 2 + cols * cellPx + (cols - 1) * GAP;
  const H = PAD * 2 + rows * cellPx + (rows - 1) * GAP;

  return (
    <div>
      <div style={{ overflowX: "auto", maxWidth: "100%", paddingBottom: 4 }}>
        <div style={{
          position: "relative", width: W, height: H,
          borderRadius: 8, border: "1px solid #1e3a5f",
          background: "#0a1628", overflow: "hidden", flexShrink: 0,
        }}>
          {/* Factory blueprint, same as the monitoring view */}
          {src && (
            <img src={src} alt=""
              style={{ position: "absolute", inset: 0, width: "100%",
                height: "100%", objectFit: "cover", opacity: 0.55,
                pointerEvents: "none" }} />
          )}

          {/* Cell grid */}
          <div style={{
            position: "absolute", inset: PAD,
            display: "grid",
            gridTemplateColumns: `repeat(${cols}, ${cellPx}px)`,
            gridTemplateRows: `repeat(${rows}, ${cellPx}px)`,
            gap: GAP,
          }}>
            {Array.from({ length: rows * cols }, (_, i) => {
              const id   = sid(Math.floor(i / cols), i % cols);
              const s    = byId[id] || {};
              const z    = zoneOf[id];
              const on   = selSet.has(id);
              const imp  = !on && impSet.has(id);
              const order = mode === "ordered" ? selected.indexOf(id) : -1;
              const blocked = s.passable === false;
              const otherZone = z && highlightZone && z.zone_id !== highlightZone;

              const border = on ? accent
                : imp ? "#22c55e"
                : otherZone ? z.color + "77"
                : z ? z.color + "55"
                : "#1e293b";
              const bg = on ? accent + "44"
                : imp ? "#22c55e22"
                : "rgba(5,12,26,0.35)";

              return (
                <button key={id}
                  onClick={() => onToggle && onToggle(id)}
                  onMouseEnter={() => setHover(id)}
                  onMouseLeave={() => setHover(null)}
                  title={`${id}${z ? ` · ${z.name}` : " · unassigned"}` +
                         `${s.coverage_type ? ` · ${s.coverage_type}` : ""}` +
                         `${blocked ? " · NOT PASSABLE" : ""}` +
                         `${imp ? " · covered by zone authorisation" : ""}`}
                  style={{
                    border: `1.5px solid ${border}`,
                    borderStyle: blocked ? "dashed" : "solid",
                    borderRadius: 5,
                    background: bg,
                    backdropFilter: "blur(1px)",
                    cursor: "pointer", position: "relative",
                    display: "flex", flexDirection: "column",
                    alignItems: "center", justifyContent: "center",
                    fontFamily: "monospace", padding: 0,
                    transition: "all .12s",
                    transform: hover === id ? "scale(1.07)" : "none",
                    zIndex: hover === id ? 2 : 1,
                  }}>
                  <span style={{
                    fontSize: 9.5, fontWeight: 700,
                    color: on ? accent : imp ? "#4ade80" : z ? z.color : "#475569",
                    textShadow: "0 1px 3px rgba(0,0,0,.95)",
                  }}>
                    {id.replace("S", "")}
                    {COVER_ICON[s.coverage_type] &&
                      <span style={{ marginLeft: 2 }}>{COVER_ICON[s.coverage_type]}</span>}
                  </span>

                  {/* Order badge for trajectories */}
                  {order >= 0 && (
                    <span style={{
                      position: "absolute", top: -5, right: -5,
                      width: 15, height: 15, borderRadius: "50%",
                      background: accent, color: "#050c1a",
                      fontSize: 8.5, fontWeight: 700, lineHeight: "15px",
                    }}>{order + 1}</span>
                  )}

                  {/* Implied-by-zone marker */}
                  {imp && (
                    <span style={{ position: "absolute", bottom: 1, right: 3,
                      fontSize: 8, color: "#4ade80" }}>◈</span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {showLegend && (
        <div style={{ display: "flex", gap: 12, marginTop: 7, flexWrap: "wrap",
          fontSize: 9.5, color: "#475569", fontFamily: "monospace" }}>
          <Chip c={accent}    label={mode === "ordered" ? "in route" : "selected"} />
          {implied.length > 0 && <Chip c="#22c55e" label="◈ covered by zone" />}
          <Chip c="#64748b"  label="⚙ machine · 📦 storage · 🚪 exit" plain />
          <Chip c="#ef4444"  label="dashed = not passable" plain />
          <span style={{ marginLeft: "auto" }}>
            {selected.length} selected
            {implied.length > 0 && ` · ${implied.length} via zone`}
          </span>
        </div>
      )}
    </div>
  );
}

function Chip({ c, label, plain }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      {!plain && (
        <span style={{ width: 10, height: 10, borderRadius: 3,
          border: `1.5px solid ${c}`, background: c + "44" }} />
      )}
      <span style={{ color: plain ? "#475569" : c }}>{label}</span>
    </span>
  );
}
