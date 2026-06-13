import { useState } from "react";

const T = {
  bg:      "#050c1a",
  surface: "#0d1829",
  border:  "rgba(255,255,255,0.06)",
  text:    "#e2e8f0",
  subtle:  "#64748b",
  muted:   "#334155",
  teal:    "#14b8a6",
  blue:    "#3b82f6",
  indigo:  "#6366f1",
  purple:  "#a855f7",
  amber:   "#f59e0b",
  coral:   "#f97316",
  red:     "#ef4444",
  green:   "#22c55e",
  cyan:    "#06b6d4",
  pink:    "#ec4899",
};

const Arrow = ({ x1, y1, x2, y2, col = "#334155", dash = false, label }) => {
  const id = `ar${x1}${y1}${x2}${y2}`.replace(/\./g, "x");
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
  return (
    <g>
      <defs>
        <marker id={id} viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="5" markerHeight="5" orient="auto">
          <path d="M2 2L8 5L2 8" fill="none" stroke={col}
            strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </marker>
      </defs>
      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={col} strokeWidth="1.2"
        strokeDasharray={dash ? "5 3" : "none"} markerEnd={`url(#${id})`} />
      {label && <text x={mx + 4} y={my - 3} fill={col} fontSize={8} opacity="0.85">{label}</text>}
    </g>
  );
};

const APath = ({ d, col = "#334155", dash = false }) => {
  const id = `ap${d.replace(/[^0-9]/g, "").slice(0, 10)}x`;
  return (
    <g>
      <defs>
        <marker id={id} viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="5" markerHeight="5" orient="auto">
          <path d="M2 2L8 5L2 8" fill="none" stroke={col}
            strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </marker>
      </defs>
      <path d={d} fill="none" stroke={col} strokeWidth="1.2"
        strokeDasharray={dash ? "5 3" : "none"} markerEnd={`url(#${id})`} />
    </g>
  );
};

const Box = ({ x, y, w, h, stroke, fill, title, sub, sub2, fs = 10, opacity = 1 }) => (
  <g opacity={opacity}>
    <rect x={x} y={y} width={w} height={h} rx={7}
      fill={fill || T.surface} stroke={stroke} strokeWidth="1.2" />
    <text x={x + w / 2} y={y + (sub ? h / 2 - (sub2 ? 9 : 5) : h / 2 + 1)}
      textAnchor="middle" dominantBaseline="central"
      fill={T.text} fontSize={fs} fontWeight={700}>{title}</text>
    {sub && <text x={x + w / 2} y={y + h / 2 + (sub2 ? 5 : 9)}
      textAnchor="middle" fill={T.subtle} fontSize={fs - 1}>{sub}</text>}
    {sub2 && <text x={x + w / 2} y={y + h / 2 + 18}
      textAnchor="middle" fill={T.subtle} fontSize={fs - 1.5}>{sub2}</text>}
  </g>
);

const Layer = ({ x, y, w, h, stroke, label, children }) => (
  <g>
    <rect x={x} y={y} width={w} height={h} rx={10}
      fill={stroke + "08"} stroke={stroke} strokeWidth="1.3" />
    <rect x={x + 10} y={y - 9} width={label.length * 7 + 16} height={18} rx={4}
      fill={T.bg} stroke={stroke} strokeWidth="1" />
    <text x={x + 18} y={y + 0.5} dominantBaseline="middle"
      fill={stroke} fontSize={9.5} fontWeight={700} letterSpacing="0.5">{label}</text>
    {children}
  </g>
);

const Badge = ({ x, y, text, col }) => (
  <g>
    <rect x={x} y={y} width={text.length * 6 + 10} height={14} rx={3}
      fill={col + "28"} stroke={col} strokeWidth="0.8" />
    <text x={x + 5} y={y + 7} dominantBaseline="middle"
      fill={col} fontSize={7.5} fontWeight={700}>{text}</text>
  </g>
);

// ── Tab: Full AI Architecture ───────────────────────────────────────────────
function ArchTab() {
  return (
    <svg viewBox="0 0 860 1080" width="100%" style={{ display: "block" }}>

      {/* ── Data Sources ───────────────────────────────────────────────────── */}
      <Layer x={10} y={18} w={838} h={90} stroke={T.teal}
        label="DATA SOURCES  (from existing Digital Twin)">
        <Box x={20}  y={28} w={248} h={50} stroke={T.teal}
          title="Localisation Stream"
          sub="[id, cur_sensor, cur_zone, prev_sensor,"
          sub2="prev_zone, authorisation, timestamp]" />
        <Box x={284} y={28} w={220} h={50} stroke={T.cyan}
          title="Environmental Stream"
          sub="[sensor_id, zone_id,"
          sub2="temp | smoke | humidity, timestamp]" />
        <Box x={520} y={28} w={180} h={50} stroke={T.muted}
          title="PostgreSQL History"
          sub="location_events · env_readings"
          sub2="events · system_snapshots" />
        <Box x={716} y={28} w={122} h={50} stroke={T.muted}
          title="ZoneRegistry"
          sub="sensor → zone"
          sub2="grid topology" />
      </Layer>

      {/* Arrow down */}
      <Arrow x1={430} y1={108} x2={430} y2={138} col={T.blue} label="  raw events + history" />

      {/* ── Feature Engineering ─────────────────────────────────────────────── */}
      <Layer x={10} y={140} w={838} h={88} stroke={T.blue}
        label="FEATURE ENGINEERING PIPELINE">
        <Box x={20}  y={28} w={188} h={50} stroke={T.blue}
          title="Movement Features"
          sub="zone dwell time · transition freq"
          sub2="path sequences · backtrack ratio" />
        <Box x={224} y={28} w={188} h={50} stroke={T.blue}
          title="Temporal Features"
          sub="hour · day · shift · week"
          sub2="rolling mean / std (5, 15, 60 min)" />
        <Box x={428} y={28} w={188} h={50} stroke={T.cyan}
          title="Environmental Features"
          sub="per-zone temp/hum/smoke"
          sub2="gradient · trend · cross-zone" />
        <Box x={632} y={28} w={196} h={50} stroke={T.purple}
          title="Graph Features"
          sub="zone adjacency · betweenness"
          sub2="danger proximity score" />
      </Layer>

      <Arrow x1={430} y1={228} x2={430} y2={258} col={T.indigo} label="  feature vectors" />

      {/* ── Three AI Models ─────────────────────────────────────────────────── */}
      <Layer x={10} y={260} w={838} h={370} stroke={T.indigo}
        label="AI MODELS LAYER">

        {/* Model 1 */}
        <rect x={16} y={22} width={256} height={336} rx={8}
          fill={T.amber + "08"} stroke={T.amber} strokeWidth="1" />
        <text x={144} y={40} textAnchor="middle" fill={T.amber}
          fontSize={10} fontWeight={700}>① MOVEMENT OPTIMISER</text>
        <Badge x={30} y={50} text="Reinforcement Learning" col={T.amber} />
        <Badge x={30} y={68} text="Sequence Model" col={T.amber} />

        {[
          { t: "State space",      v: "worker_id · zone_id · task" },
          { t: "Action space",     v: "move to adjacent zone" },
          { t: "Reward",           v: "+task done, −unnecessary move" },
          { t: "Algorithm",        v: "PPO / Q-learning" },
          { t: "Also",             v: "LSTM on zone sequences" },
          { t: "Detects",          v: "backtracking · idle loops" },
          { t: "Output",           v: "movement_score + suggestion" },
          { t: "Label source",     v: "manual annotation or sim" },
          { t: "Retrains",         v: "weekly on new history" },
        ].map((r, i) => (
          <g key={i}>
            <text x={30} y={98 + i * 28} fill={T.subtle} fontSize={8} fontWeight={600}>{r.t}</text>
            <text x={30} y={112 + i * 28} fill={T.text} fontSize={8.5}>{r.v}</text>
          </g>
        ))}

        {/* Model 2 */}
        <rect x={292} y={22} width={256} height={336} rx={8}
          fill={T.red + "08"} stroke={T.red} strokeWidth="1" />
        <text x={420} y={40} textAnchor="middle" fill={T.red}
          fontSize={10} fontWeight={700}>② SMART EVACUATION</text>
        <Badge x={306} y={50} text="Graph + ML" col={T.red} />
        <Badge x={306} y={68} text="Multi-agent planning" col={T.red} />

        {[
          { t: "Input",        v: "asset locations + sensor states" },
          { t: "Danger map",   v: "smoke/temp gradient per zone" },
          { t: "Exits",        v: "registered in ZoneRegistry" },
          { t: "Algorithm",    v: "Dijkstra + danger-weighted edges" },
          { t: "ML part",      v: "danger score predictor (XGBoost)" },
          { t: "Output",       v: "per-asset evacuation route" },
          { t: "Adapts",       v: "re-routes on new sensor alert" },
          { t: "Priority",     v: "smoke zones evacuated first" },
          { t: "Recomputes",   v: "every 2s during emergency" },
        ].map((r, i) => (
          <g key={i}>
            <text x={306} y={98 + i * 28} fill={T.subtle} fontSize={8} fontWeight={600}>{r.t}</text>
            <text x={306} y={112 + i * 28} fill={T.text} fontSize={8.5}>{r.v}</text>
          </g>
        ))}

        {/* Model 3 */}
        <rect x={568} y={22} width={258} height={336} rx={8}
          fill={T.purple + "08"} stroke={T.purple} strokeWidth="1" />
        <text x={697} y={40} textAnchor="middle" fill={T.purple}
          fontSize={10} fontWeight={700}>③ SYSTEM MONITOR</text>
        <Badge x={582} y={50} text="Anomaly Detection" col={T.purple} />
        <Badge x={582} y={68} text="Time-series forecast" col={T.purple} />

        {[
          { t: "Env model",    v: "LSTM autoencoder per sensor" },
          { t: "Trained on",   v: "normal operation history" },
          { t: "Detects",      v: "reconstruction error spike" },
          { t: "Sensor health",v: "heartbeat + reading patterns" },
          { t: "Predicts",     v: "sensor failure before offline" },
          { t: "Forecasts",    v: "temp / smoke 5–15 min ahead" },
          { t: "Output",       v: "anomaly_score · predicted_val" },
          { t: "Alert when",   v: "score > threshold" },
          { t: "Retrains",     v: "nightly on rolling 30-day window" },
        ].map((r, i) => (
          <g key={i}>
            <text x={582} y={98 + i * 28} fill={T.subtle} fontSize={8} fontWeight={600}>{r.t}</text>
            <text x={582} y={112 + i * 28} fill={T.text} fontSize={8.5}>{r.v}</text>
          </g>
        ))}
      </Layer>

      <Arrow x1={144} y1={630} x2={144} y2={660} col={T.amber} />
      <Arrow x1={420} y1={630} x2={420} y2={660} col={T.red} />
      <Arrow x1={697} y1={630} x2={697} y2={660} col={T.purple} />

      {/* ── Inference Engine ────────────────────────────────────────────────── */}
      <Layer x={10} y={662} w={838} h={86} stroke={T.coral}
        label="INFERENCE ENGINE  (runs alongside Twin Engine)">
        <Box x={20}  y={24} w={196} h={48} stroke={T.amber}
          title="movement_score(worker)"
          sub="unnecessary_moves · suggestion" />
        <Box x={232} y={24} w={180} h={48} stroke={T.red}
          title="evacuation_route(assets)"
          sub="ordered zone list per asset" />
        <Box x={428} y={24} w={196} h={48} stroke={T.purple}
          title="anomaly_score(sensor)"
          sub="predicted_temp · failure_risk" />
        <Box x={640} y={24} w={196} h={48} stroke={T.green}
          title="AI alert publisher"
          sub="push to Digital Twin engine" />
        <Arrow x1={216} y1={48} x2={230} y2={48} col={T.amber} />
        <Arrow x1={412} y1={48} x2={426} y2={48} col={T.red} />
        <Arrow x1={624} y1={48} x2={638} y2={48} col={T.purple} />
      </Layer>

      <Arrow x1={430} y1={748} x2={430} y2={778} col={T.green} label="  AI insights" />

      {/* ── Integration with Twin Engine ────────────────────────────────────── */}
      <Layer x={10} y={780} w={838} h={76} stroke={T.green}
        label="INTEGRATION  (Digital Twin Engine)">
        <Box x={20}  y={20} w={188} h={42} stroke={T.green}
          title="AI event bus" sub="ai_alert · ai_suggestion" />
        <Box x={224} y={20} w={188} h={42} stroke={T.green}
          title="Rule enrichment" sub="AI score → rule threshold" />
        <Box x={428} y={20} w={188} h={42} stroke={T.green}
          title="SystemState AI fields" sub="movement_efficiency · risk" />
        <Box x={632} y={20} w={196} h={42} stroke={T.green}
          title="WebSocket push" sub="AI insights to frontend" />
        <Arrow x1={208} y1={41} x2={222} y2={41} col={T.green} />
        <Arrow x1={412} y1={41} x2={426} y2={41} col={T.green} />
        <Arrow x1={616} y1={41} x2={630} y2={41} col={T.green} />
      </Layer>

      <Arrow x1={430} y1={856} x2={430} y2={886} col={T.muted} />

      {/* ── Training Pipeline ───────────────────────────────────────────────── */}
      <Layer x={10} y={888} w={838} h={76} stroke={T.muted}
        label="TRAINING PIPELINE  (offline · scheduled)">
        <Box x={20}  y={20} w={190} h={44} stroke={T.muted}
          title="Data extractor" sub="PostgreSQL → Parquet" />
        <Box x={226} y={20} w={190} h={44} stroke={T.muted}
          title="Feature builder" sub="window · aggregate · label" />
        <Box x={432} y={20} w={190} h={44} stroke={T.muted}
          title="Model trainer" sub="train · evaluate · version" />
        <Box x={638} y={20} w={190} h={44} stroke={T.muted}
          title="Model store" sub="MLflow · joblib · ONNX" />
        <Arrow x1={210} y1={42} x2={224} y2={42} col={T.muted} />
        <Arrow x1={416} y1={42} x2={430} y2={42} col={T.muted} />
        <Arrow x1={622} y1={42} x2={636} y2={42} col={T.muted} />
        {/* Training loop back to inference */}
        <APath d="M 733 20 Q 833 10 838 630 Q 843 750 838 750"
          col={T.muted} dash />
      </Layer>

      {/* Footer */}
      <rect x={10} y={978} width={838} height={22} rx={5}
        fill={T.surface} stroke={T.border} strokeWidth="1" />
      <text x={429} y={993} textAnchor="middle" fill={T.subtle} fontSize={8.5}>
        Data → Features → Train (offline) → Inference (online) → Twin Engine → Frontend — models improve continuously with new data
      </text>
    </svg>
  );
}

// ── Tab: Movement Optimiser detail ─────────────────────────────────────────
function MovementTab() {
  const zones = ["Entry", "Zone A", "Zone B", "Zone C", "Zone D", "Exit"];
  const zx = [60, 60, 220, 380, 220, 380];
  const zy = [80, 180, 180, 180, 300, 300];
  const edges = [
    [0,1,T.teal],[1,2,T.teal],[2,3,T.teal],[1,3,T.amber,true],
    [2,4,T.teal],[4,5,T.teal],[3,5,T.teal],[3,4,T.red,true],
  ];

  return (
    <svg viewBox="0 0 860 680" width="100%" style={{ display: "block" }}>
      <text x={430} y={22} textAnchor="middle" fill={T.text}
        fontSize={14} fontWeight={700}>Movement Optimiser — Design</text>

      {/* ── Feature pipeline ─────────────────────────────────────────────── */}
      <Layer x={10} y={38} w={838} h={76} stroke={T.blue}
        label="INPUT FEATURES  (per worker, per time window)">
        {[
          "zone_sequence (last 20 hops)",
          "dwell_times per zone",
          "backtrack_count",
          "time_of_day · shift_id",
          "task_type (if known)",
          "authorisation_list",
        ].map((f, i) => (
          <g key={i}>
            <rect x={20 + i * 138} y={26} width={128} height={38} rx={5}
              fill={T.blue + "10"} stroke={T.blue} strokeWidth="0.8" />
            <text x={84 + i * 138} y={47} textAnchor="middle"
              fill={T.text} fontSize={8.5}>{f}</text>
          </g>
        ))}
      </Layer>

      {/* Zone graph */}
      <rect x={10} y={128} width={380} height={290} rx={10}
        fill={T.amber + "06"} stroke={T.amber} strokeWidth="1" />
      <text x={200} y={148} textAnchor="middle" fill={T.amber}
        fontSize={10} fontWeight={700}>Zone Transition Graph</text>

      {edges.map(([a, b, col, bad], i) => (
        <Arrow key={i} x1={zx[a] + 40} y1={zy[a] + 20} x2={zx[b] + 40} y2={zy[b] + 20}
          col={col} dash={bad} />
      ))}
      {zones.map((z, i) => (
        <g key={i}>
          <rect x={zx[i]} y={zy[i]} width={80} height={40} rx={6}
            fill={T.surface} stroke={i === 4 ? T.red : T.teal} strokeWidth="1.2" />
          <text x={zx[i] + 40} y={zy[i] + 20} textAnchor="middle"
            dominantBaseline="central" fill={T.text} fontSize={9} fontWeight={600}>{z}</text>
        </g>
      ))}
      <text x={200} y={398} textAnchor="middle" fill={T.subtle} fontSize={8}>
        Red dashed = detected unnecessary transition
      </text>
      <text x={200} y={412} textAnchor="middle" fill={T.amber} fontSize={8}>
        Amber dashed = suboptimal path (backtrack)
      </text>

      {/* Model details */}
      <Layer x={406} y={128} w={442} h={290} stroke={T.amber}
        label="MODEL DETAILS">
        <text x={221} y={36} textAnchor="middle" fill={T.amber}
          fontSize={10} fontWeight={700}>LSTM Sequence Classifier</text>
        {[
          { l: "Input",      v: "sequence of (zone_id, dwell_time) tuples" },
          { l: "Embedding",  v: "zone_id → 16-dim learned embedding" },
          { l: "LSTM",       v: "64 units, 2 layers, dropout 0.2" },
          { l: "Output",     v: "movement_efficiency_score ∈ [0, 1]" },
          { l: "Threshold",  v: "score < 0.6 → trigger suggestion" },
          { l: "",           v: "" },
          { l: "PPO Agent (RL)", v: "" },
          { l: "State",      v: "(worker_id, zone, task, time)" },
          { l: "Action",     v: "next zone to move to" },
          { l: "Reward",     v: "+1 task complete, −0.5 unnecessary hop" },
          { l: "Env",        v: "factory zone graph simulation" },
          { l: "",           v: "" },
          { l: "Cold start", v: "rule-based until 30 days of data" },
        ].map((r, i) => (
          r.l === "" ? null : (
            <g key={i}>
              <text x={16} y={58 + i * 17} fill={T.subtle} fontSize={8} fontWeight={700}>{r.l}</text>
              {r.v && <text x={110} y={58 + i * 17} fill={T.text} fontSize={8}>{r.v}</text>}
            </g>
          )
        ))}
      </Layer>

      {/* Output */}
      <Layer x={10} y={432} w={838} h={76} stroke={T.green}
        label="OUTPUTS">
        {[
          { t: "movement_score",    s: "0.0 (chaotic) → 1.0 (optimal)" },
          { t: "unnecessary_moves", s: "count per shift" },
          { t: "suggested_route",   s: "ordered zone list" },
          { t: "saving_estimate",   s: "time saved (min)" },
        ].map((o, i) => (
          <Box key={i} x={20 + i * 208} y={20} w={196} h={44}
            stroke={T.green} title={o.t} sub={o.s} />
        ))}
      </Layer>

      {/* Feedback loop */}
      <Layer x={10} y={522} w={838} h={76} stroke={T.muted}
        label="CONTINUOUS LEARNING">
        {[
          { t: "Label strategy",    s: "expert feedback + simulation" },
          { t: "Retraining",        s: "weekly · new movement data" },
          { t: "Drift detection",   s: "PSI on zone distributions" },
          { t: "Cold start",        s: "rule-based heuristics first" },
        ].map((o, i) => (
          <Box key={i} x={20 + i * 208} y={20} w={196} h={44}
            stroke={T.muted} title={o.t} sub={o.s} />
        ))}
      </Layer>

      <text x={430} y={618} textAnchor="middle" fill={T.subtle} fontSize={8}>
        Training data: location_events table · feature window: per-shift (8h) · label: supervisor annotation or simulation
      </text>
    </svg>
  );
}

// ── Tab: Smart Evacuation ────────────────────────────────────────────────────
function EvacTab() {
  // grid of zones with danger levels
  const grid = [
    [{ z: "A1", d: 0 }, { z: "A2", d: 0 }, { z: "A3", d: 0.2 }, { z: "A4", d: 0 }],
    [{ z: "B1", d: 0.1 }, { z: "B2", d: 0.9 }, { z: "B3", d: 0.7 }, { z: "B4", d: 0 }],
    [{ z: "C1", d: 0 }, { z: "C2", d: 0.4 }, { z: "C3", d: 0 }, { z: "C4", d: 0 }],
    [{ z: "EXIT", d: 0 }, { z: "EXIT", d: 0 }, { z: "EXIT", d: 0 }, { z: "EXIT", d: 0 }],
  ];
  const GX = 20, GY = 80, CW = 88, CH = 60;
  const dangerColor = (d) => {
    if (d > 0.7) return T.red;
    if (d > 0.3) return T.amber;
    if (d > 0) return T.coral;
    return T.teal;
  };

  // Evacuation path for worker in B1
  const path = [[1,0],[0,0],[0,1],[0,2],[0,3]]; // row,col

  return (
    <svg viewBox="0 0 860 720" width="100%" style={{ display: "block" }}>
      <text x={430} y={22} textAnchor="middle" fill={T.text}
        fontSize={14} fontWeight={700}>Smart Evacuation — Design</text>

      {/* Danger map */}
      <rect x={10} y={38} width={390} height={360} rx={10}
        fill={T.red + "06"} stroke={T.red} strokeWidth="1.2" />
      <text x={205} y={58} textAnchor="middle" fill={T.red}
        fontSize={10} fontWeight={700}>Real-time Danger Map</text>

      {grid.map((row, r) =>
        row.map((cell, c) => {
          const x = GX + c * CW, y = GY + r * CH;
          const isExit = cell.z === "EXIT";
          const isPath = path.some(([pr, pc]) => pr === r && pc === c);
          return (
            <g key={`${r}${c}`}>
              <rect x={x} y={y} width={CW - 4} height={CH - 4} rx={5}
                fill={isExit ? T.green + "30" : dangerColor(cell.d) + "30"}
                stroke={isPath ? T.green : isExit ? T.green : dangerColor(cell.d)}
                strokeWidth={isPath ? 2.5 : 1} />
              <text x={x + (CW - 4) / 2} y={y + (CH - 4) / 2 - 5}
                textAnchor="middle" dominantBaseline="central"
                fill={isExit ? T.green : dangerColor(cell.d)} fontSize={9} fontWeight={700}>{cell.z}</text>
              {!isExit && <text x={x + (CW - 4) / 2} y={y + (CH - 4) / 2 + 9}
                textAnchor="middle" fill={T.subtle} fontSize={7.5}>
                danger: {cell.d.toFixed(1)}</text>}
              {isExit && <text x={x + (CW - 4) / 2} y={y + (CH - 4) / 2 + 9}
                textAnchor="middle" fill={T.green} fontSize={7.5}>EXIT ✓</text>}
            </g>
          );
        })
      )}
      {/* Worker icon */}
      <text x={GX + 0 * CW + 42} y={GY + 1 * CH + 26} textAnchor="middle"
        fontSize={18}>👷</text>

      {/* Path arrow */}
      <path d={`M ${GX + 42} ${GY + 60 + 26}
               L ${GX + 42} ${GY + 26}
               L ${GX + CW + 42} ${GY + 26}
               L ${GX + 2 * CW + 42} ${GY + 26}
               L ${GX + 3 * CW + 42} ${GY + 26}`}
        fill="none" stroke={T.green} strokeWidth="2" strokeDasharray="6 3" />
      <text x={205} y={330} textAnchor="middle" fill={T.green} fontSize={8.5} fontWeight={600}>
        ← Optimal evacuation route (avoids B2, B3, C2)
      </text>
      <text x={205} y={348} textAnchor="middle" fill={T.subtle} fontSize={8}>
        danger-weighted Dijkstra on zone adjacency graph
      </text>

      {/* Model details */}
      <Layer x={416} y={38} w={432} h={360} stroke={T.red}
        label="MODEL DETAILS">
        <text x={216} y={30} textAnchor="middle" fill={T.red}
          fontSize={10} fontWeight={700}>Two-stage approach</text>

        <text x={16} y={50} fill={T.red} fontSize={9} fontWeight={700}>Stage 1 — Danger Score (ML)</text>
        {[
          { l: "Model",   v: "XGBoost regressor per zone" },
          { l: "Input",   v: "temp, humidity, smoke + trends" },
          { l: "Output",  v: "danger_score ∈ [0, 1]" },
          { l: "Trained", v: "on labelled historical incidents" },
          { l: "Updates", v: "every 2s from sensor stream" },
        ].map((r, i) => (
          <g key={i}>
            <text x={20} y={68 + i * 16} fill={T.subtle} fontSize={8} fontWeight={600}>{r.l}:</text>
            <text x={70} y={68 + i * 16} fill={T.text} fontSize={8}>{r.v}</text>
          </g>
        ))}

        <text x={16} y={160} fill={T.red} fontSize={9} fontWeight={700}>Stage 2 — Route Planning (Graph)</text>
        {[
          { l: "Graph",   v: "zone adjacency from ZoneRegistry" },
          { l: "Weights", v: "edge_cost = 1 + danger_score × 10" },
          { l: "Algo",    v: "Dijkstra (shortest safe path)" },
          { l: "Exits",   v: "registered exit zones (nearest)" },
          { l: "Output",  v: "ordered zone list per asset" },
          { l: "Refresh", v: "re-routes when sensor alert fires" },
        ].map((r, i) => (
          <g key={i}>
            <text x={20} y={178 + i * 16} fill={T.subtle} fontSize={8} fontWeight={600}>{r.l}:</text>
            <text x={70} y={178 + i * 16} fill={T.text} fontSize={8}>{r.v}</text>
          </g>
        ))}

        <text x={16} y={284} fill={T.red} fontSize={9} fontWeight={700}>Multi-asset priority</text>
        {[
          "Workers in highest-danger zones evacuated first",
          "Routes avoid crossing other evacuation paths",
          "Mobility-impaired workers flagged for assistance",
        ].map((l, i) => (
          <text key={i} x={20} y={300 + i * 16} fill={T.text} fontSize={8}>• {l}</text>
        ))}
      </Layer>

      {/* Outputs */}
      <Layer x={10} y={412} w={838} h={76} stroke={T.green} label="OUTPUTS per asset">
        {[
          { t: "evacuation_route",   s: "[ zone_id, zone_id, … exit ]" },
          { t: "estimated_time",     s: "seconds to exit" },
          { t: "danger_on_path",     s: "max danger score encountered" },
          { t: "priority_rank",      s: "evacuation order (1 = first)" },
        ].map((o, i) => (
          <Box key={i} x={20 + i * 208} y={20} w={196} h={44}
            stroke={T.green} title={o.t} sub={o.s} />
        ))}
      </Layer>

      {/* Trigger conditions */}
      <Layer x={10} y={502} w={838} h={76} stroke={T.red} label="TRIGGER CONDITIONS">
        {[
          { t: "smoke_detected",       s: "any sensor.smoke = true" },
          { t: "temperature critical", s: "temp > 60°C in any zone" },
          { t: "multi-zone alert",     s: "≥ 2 zones warning simultaneously" },
          { t: "manual trigger",       s: "operator command via dashboard" },
        ].map((o, i) => (
          <Box key={i} x={20 + i * 208} y={20} w={196} h={44}
            stroke={T.red} title={o.t} sub={o.s} />
        ))}
      </Layer>

      <text x={430} y={600} textAnchor="middle" fill={T.subtle} fontSize={8}>
        Training: historical incident logs · exit drill recordings · simulation data (synthetic danger scenarios)
      </text>
    </svg>
  );
}

// ── Tab: System Monitor ──────────────────────────────────────────────────────
function MonitorTab() {
  const readings = [18,19,20,21,22,24,28,35,45,52,61,58];
  const predicted = [18,19,20,21,22,24,29,37,47,54,58,55];
  const anomalyAt = 6;
  const W2 = 420, H2 = 120, PX = 20, PY = 20;
  const minV = 10, maxV = 70;
  const px = (i) => PX + (i / (readings.length - 1)) * (W2 - 40);
  const py = (v) => PY + H2 - ((v - minV) / (maxV - minV)) * H2;

  return (
    <svg viewBox="0 0 860 720" width="100%" style={{ display: "block" }}>
      <text x={430} y={22} textAnchor="middle" fill={T.text}
        fontSize={14} fontWeight={700}>System Monitor — Design</text>

      {/* LSTM Autoencoder diagram */}
      <rect x={10} y={38} width={440} height={180} rx={10}
        fill={T.purple + "06"} stroke={T.purple} strokeWidth="1.2" />
      <text x={230} y={58} textAnchor="middle" fill={T.purple}
        fontSize={10} fontWeight={700}>LSTM Autoencoder (Anomaly Detection)</text>

      {/* Encoder / decoder blocks */}
      {[
        { x: 20,  w: 60, label: "Input\nseq", col: T.teal },
        { x: 96,  w: 70, label: "Encoder\nLSTM", col: T.blue },
        { x: 182, w: 70, label: "Latent\nvector", col: T.purple },
        { x: 268, w: 70, label: "Decoder\nLSTM", col: T.blue },
        { x: 354, w: 74, label: "Recon-\nstructed", col: T.teal },
      ].map((b, i) => (
        <g key={i}>
          <rect x={b.x} y={72} width={b.w} height={60} rx={5}
            fill={b.col + "20"} stroke={b.col} strokeWidth="1" />
          {b.label.split("\n").map((l, j) => (
            <text key={j} x={b.x + b.w / 2} y={97 + j * 14}
              textAnchor="middle" fill={T.text} fontSize={8.5} fontWeight={600}>{l}</text>
          ))}
          {i < 4 && <Arrow x1={b.x + b.w} y1={102} x2={b.x + b.w + 9} y2={102} col={b.col} />}
        </g>
      ))}
      <text x={230} y={158} textAnchor="middle" fill={T.subtle} fontSize={8}>
        Trained on normal operation → high reconstruction error = anomaly
      </text>
      <text x={430} y={172} textAnchor="end" fill={T.muted} fontSize={8}>
        Reconstruction error &gt; threshold → anomaly_score high
      </text>

      {/* Temperature chart */}
      <rect x={10} y={230} width={450} height={180} rx={10}
        fill={T.amber + "06"} stroke={T.amber} strokeWidth="1.2" />
      <text x={235} y={250} textAnchor="middle" fill={T.amber}
        fontSize={10} fontWeight={700}>Temperature Forecast (LSTM regressor)</text>

      {/* Chart background */}
      <rect x={PX + 10} y={PY + 240} width={W2 - 20} height={H2} rx={4}
        fill="#0d1829" />
      {/* Anomaly region */}
      <rect x={px(anomalyAt) - 2} y={PY + 240} width={px(readings.length - 1) - px(anomalyAt) + 4} height={H2}
        fill={T.red + "18"} />
      {/* Actual line */}
      <polyline points={readings.map((v, i) => `${px(i)},${py(v) + 240}`).join(" ")}
        fill="none" stroke={T.blue} strokeWidth="1.5" />
      {/* Predicted line */}
      <polyline points={predicted.map((v, i) => `${px(i)},${py(v) + 240}`).join(" ")}
        fill="none" stroke={T.amber} strokeWidth="1.5" strokeDasharray="5 3" />
      {/* Threshold line */}
      <line x1={PX} y1={py(60) + 240} x2={W2} y2={py(60) + 240}
        stroke={T.red} strokeWidth="1" strokeDasharray="3 3" />
      <text x={W2 + 4} y={py(60) + 240} fill={T.red} fontSize={7.5}>60°C</text>
      {/* Legend */}
      <line x1={PX + 10} y1={PY + 360} x2={PX + 30} y2={PY + 360} stroke={T.blue} strokeWidth="1.5" />
      <text x={PX + 34} y={PY + 364} fill={T.subtle} fontSize={8}>actual</text>
      <line x1={PX + 70} y1={PY + 360} x2={PX + 90} y2={PY + 360}
        stroke={T.amber} strokeWidth="1.5" strokeDasharray="5 3" />
      <text x={PX + 94} y={PY + 364} fill={T.subtle} fontSize={8}>predicted (5 min ahead)</text>
      <text x={PX + 200} y={PY + 364} fill={T.red + "99"} fontSize={8}>█ anomaly region</text>

      {/* Model details */}
      <Layer x={476} y={38} w={372} h={370} stroke={T.purple} label="MODEL DETAILS">
        <text x={186} y={30} textAnchor="middle" fill={T.purple}
          fontSize={10} fontWeight={700}>Three sub-models</text>

        {[
          { title: "① Anomaly Detector", col: T.purple,
            lines: [
              "Model: LSTM Autoencoder per sensor",
              "Input: rolling 60-reading window",
              "Output: anomaly_score ∈ [0,1]",
              "Alert: score > 0.75",
            ]},
          { title: "② Environmental Forecast", col: T.amber,
            lines: [
              "Model: LSTM regressor",
              "Input: last 30 readings + time features",
              "Output: predicted_temp/hum (5, 15 min ahead)",
              "Alert: predicted > threshold",
            ]},
          { title: "③ Sensor Failure Predictor", col: T.red,
            lines: [
              "Model: XGBoost classifier",
              "Input: consecutive_failures + reading variance",
              "Output: failure_probability + time_to_failure",
              "Alert: prob > 0.7 → schedule maintenance",
            ]},
        ].map((m, mi) => (
          <g key={mi}>
            <text x={16} y={56 + mi * 100} fill={m.col} fontSize={9} fontWeight={700}>{m.title}</text>
            {m.lines.map((l, i) => (
              <text key={i} x={20} y={72 + mi * 100 + i * 16}
                fill={i === 0 ? T.subtle : T.text} fontSize={8}>{l}</text>
            ))}
          </g>
        ))}

        <text x={16} y={360} fill={T.subtle} fontSize={8} fontWeight={700}>Training</text>
        <text x={16} y={376} fill={T.text} fontSize={8}>Nightly · rolling 30-day window · MLflow tracking</text>
      </Layer>

      {/* Outputs */}
      <Layer x={10} y={424} w={838} h={76} stroke={T.purple} label="OUTPUTS">
        {[
          { t: "anomaly_score",        s: "per sensor · 0=normal, 1=anomaly" },
          { t: "predicted_temp",       s: "5 and 15 min ahead" },
          { t: "failure_probability",  s: "per sensor · next 24h" },
          { t: "maintenance_alert",    s: "sensor_id + urgency level" },
        ].map((o, i) => (
          <Box key={i} x={20 + i * 208} y={20} w={196} h={44}
            stroke={T.purple} title={o.t} sub={o.s} />
        ))}
      </Layer>

      {/* Training details */}
      <Layer x={10} y={514} w={838} h={76} stroke={T.muted} label="TRAINING DETAILS">
        {[
          { t: "Normal baseline",     s: "> 7 days normal operation data" },
          { t: "Incident labels",     s: "manual annotation of past events" },
          { t: "Synthetic data",      s: "simulated failure scenarios" },
          { t: "Retraining trigger",  s: "drift > PSI 0.2 or weekly" },
        ].map((o, i) => (
          <Box key={i} x={20 + i * 208} y={20} w={196} h={44}
            stroke={T.muted} title={o.t} sub={o.s} />
        ))}
      </Layer>

      <text x={430} y={610} textAnchor="middle" fill={T.subtle} fontSize={8}>
        All three models run continuously in the inference engine alongside the Digital Twin — outputs enrich SystemState and push alerts in real time.
      </text>
    </svg>
  );
}

// ── Tab: Data Pipeline ───────────────────────────────────────────────────────
function PipelineTab() {
  const steps = [
    { title: "Raw data",         sub: "location_events + env_readings\n(PostgreSQL tables)",              col: T.teal },
    { title: "Extract",          sub: "SQLAlchemy query\ntime-windowed Parquet export",                   col: T.blue },
    { title: "Feature build",    sub: "zone sequences · dwell times\nrolling aggregates · embeddings",    col: T.indigo },
    { title: "Label",            sub: "movement: supervisor annotation\nevac: incident logs\nmonitor: normal vs anomaly", col: T.amber },
    { title: "Train / validate", sub: "80/20 split · time-aware\ncross-validation on shifts",             col: T.purple },
    { title: "Evaluate",         sub: "F1 / RMSE / precision-recall\nper model and threshold",            col: T.coral },
    { title: "Register",         sub: "MLflow experiment tracking\nversion + metrics + artefacts",        col: T.red },
    { title: "Serve",            sub: "joblib / ONNX inference\nloaded by Inference Engine",              col: T.green },
  ];

  return (
    <svg viewBox="0 0 860 560" width="100%" style={{ display: "block" }}>
      <text x={430} y={24} textAnchor="middle" fill={T.text}
        fontSize={14} fontWeight={700}>Training & Inference Pipeline</text>

      {/* Offline pipeline */}
      <rect x={10} y={40} width={838} height={220} rx={10}
        fill={T.surface} stroke={T.muted} strokeWidth="1" />
      <text x={40} y={60} fill={T.muted} fontSize={9} fontWeight={700} letterSpacing="0.5">OFFLINE TRAINING  (scheduled nightly)</text>
      {steps.slice(0, 4).map((s, i) => (
        <g key={i}>
          <Box x={24 + i * 204} y={70} w={190} h={80} stroke={s.col}
            title={s.title} sub={s.sub.split("\n")[0]} sub2={s.sub.split("\n")[1]} />
          {i < 3 && <Arrow x1={216 + i * 204} y1={110} x2={222 + i * 204} y2={110} col={s.col} />}
        </g>
      ))}
      {steps.slice(4).map((s, i) => (
        <g key={i}>
          <Box x={24 + i * 204} y={168} w={190} h={80} stroke={s.col}
            title={s.title} sub={s.sub.split("\n")[0]} sub2={s.sub.split("\n")[1]} />
          {i < 3 && <Arrow x1={216 + i * 204} y1={208} x2={222 + i * 204} y2={208} col={s.col} />}
        </g>
      ))}
      {/* Bridge: step 4 → step 5 */}
      <APath d="M 630 150 Q 630 160 24 160 Q 24 168 24 168" col={T.amber} />

      {/* Drift monitor */}
      <Arrow x1={430} y1={262} x2={430} y2={292} col={T.coral} label="  model artefacts" />

      <Layer x={10} y={294} w={838} h={76} stroke={T.coral} label="ONLINE INFERENCE  (runs alongside Twin Engine · real-time)">
        {[
          { t: "Load models",         s: "on startup from MLflow" },
          { t: "Infer on each event", s: "location → movement model\nenv → monitor models" },
          { t: "Evac on trigger",     s: "recompute routes every 2s" },
          { t: "Drift watch",         s: "PSI on feature distributions" },
        ].map((o, i) => (
          <Box key={i} x={20 + i * 208} y={20} w={196} h={44}
            stroke={T.coral} title={o.t} sub={o.s.split("\n")[0]} />
        ))}
      </Layer>

      <Arrow x1={430} y1={370} x2={430} y2={400} col={T.green} />

      <Layer x={10} y={402} w={838} h={76} stroke={T.green} label="AI OUTPUTS → DIGITAL TWIN ENGINE + FRONTEND">
        {[
          { t: "movement_score",      s: "per worker per shift",             col: T.amber },
          { t: "evac_route",          s: "per asset on emergency trigger",   col: T.red },
          { t: "anomaly_score",       s: "per sensor continuously",          col: T.purple },
          { t: "ai_alert events",     s: "pushed via WebSocket to frontend", col: T.green },
        ].map((o, i) => (
          <Box key={i} x={20 + i * 208} y={18} w={196} h={48}
            stroke={o.col} title={o.t} sub={o.s} />
        ))}
      </Layer>

      <text x={430} y={498} textAnchor="middle" fill={T.subtle} fontSize={8.5}>
        Cold start: rule-based heuristics used until ≥ 30 days of data per model · drift triggers automatic retraining
      </text>
      <text x={430} y={514} textAnchor="middle" fill={T.subtle} fontSize={8}>
        All training data: location_events · env_readings · sensor_health_events · events tables
      </text>
    </svg>
  );
}

const TABS = [
  { id: "arch",     label: "Full AI Architecture" },
  { id: "movement", label: "① Movement Optimiser" },
  { id: "evac",     label: "② Smart Evacuation" },
  { id: "monitor",  label: "③ System Monitor" },
  { id: "pipeline", label: "Training Pipeline" },
];

const DIAGS = {
  arch:     ArchTab,
  movement: MovementTab,
  evac:     EvacTab,
  monitor:  MonitorTab,
  pipeline: PipelineTab,
};

export default function App() {
  const [active, setActive] = useState("arch");
  const Diag = DIAGS[active];

  return (
    <div style={{ background: T.bg, minHeight: "100vh", fontFamily: "'IBM Plex Mono', 'Fira Code', monospace" }}>
      {/* Header */}
      <div style={{ padding: "16px 24px 0", borderBottom: `1px solid ${T.border}`,
        background: `linear-gradient(90deg, ${T.surface}, ${T.bg})` }}>
        <div style={{ fontSize: 9, color: T.indigo, letterSpacing: 3, textTransform: "uppercase", marginBottom: 4 }}>
          Digital Twin — AI Layer
        </div>
        <div style={{ fontSize: 17, fontWeight: 700, color: T.text, marginBottom: 14 }}>
          Machine Learning Models & Pipelines
        </div>
        <div style={{ display: "flex", gap: 3 }}>
          {TABS.map(t => (
            <button key={t.id} onClick={() => setActive(t.id)} style={{
              padding: "7px 14px", fontSize: 10, fontWeight: 600, border: "none",
              borderRadius: "6px 6px 0 0", cursor: "pointer", fontFamily: "inherit",
              background: active === t.id ? T.surface : "transparent",
              color: active === t.id ? T.purple : T.subtle,
              borderBottom: active === t.id ? `2px solid ${T.purple}` : "2px solid transparent",
              transition: "all 0.15s",
            }}>{t.label}</button>
          ))}
        </div>
      </div>

      {/* Diagram */}
      <div style={{ padding: "24px 16px" }}>
        <div style={{ background: T.surface, borderRadius: 12, border: `1px solid ${T.border}`,
          padding: 16, maxWidth: 900, margin: "0 auto" }}>
          <Diag />
        </div>
        <div style={{ maxWidth: 900, margin: "12px auto 0", fontSize: 10, color: T.subtle,
          borderLeft: `2px solid ${T.purple}`, paddingLeft: 12, lineHeight: 1.7 }}>
          {{
            arch:     "Three AI models feed from the same two data streams. Feature engineering transforms raw localisation and environmental records into model-ready vectors. Inference runs online alongside the Twin Engine; training runs offline on a schedule.",
            movement: "LSTM sequence model learns normal vs suboptimal movement patterns from zone transition history. A PPO reinforcement learning agent can be layered on top once sufficient simulation data exists. Cold start uses rule-based heuristics.",
            evac:     "Two-stage: XGBoost predicts a danger score per zone from environmental readings, then a danger-weighted Dijkstra finds the safest route to the nearest exit for each asset. Re-routes dynamically as sensor states change.",
            monitor:  "LSTM autoencoder trained on normal operation detects anomalies via reconstruction error. A separate LSTM regressor forecasts temperature 5–15 min ahead. XGBoost classifies sensor failure risk from heartbeat patterns.",
            pipeline: "All three models share the same offline training pipeline: extract from PostgreSQL → engineer features → label → train → evaluate → register in MLflow → serve in the inference engine. Drift detection triggers retraining automatically.",
          }[active]}
        </div>
      </div>
    </div>
  );
}
