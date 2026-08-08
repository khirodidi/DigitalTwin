import { useState } from "react";

const TABS = [
  { id: "arch",   label: "System Architecture" },
  { id: "grid",   label: "Factory Grid" },
  { id: "engine", label: "Twin Engine" },
  { id: "flow",   label: "Event Flow" },
  { id: "state",  label: "System State" },
];

const C = {
  teal:   { fill: "#0d9488", text: "#f0fdfa" },
  blue:   { fill: "#1d6eb5", text: "#eff6ff" },
  purple: { fill: "#6d28d9", text: "#f5f3ff" },
  amber:  { fill: "#b45309", text: "#fffbeb" },
  coral:  { fill: "#c94f3a", text: "#fff7f5" },
  gray:   { fill: "#374151", text: "#f9fafb" },
  red:    { fill: "#b91c1c", text: "#fef2f2" },
  green:  { fill: "#15803d", text: "#f0fdf4" },
};

const Box = ({ x, y, w, h, r = 8, color, title, sub, onClick }) => (
  <g onClick={onClick} style={onClick ? { cursor: "pointer" } : {}}>
    <rect x={x} y={y} width={w} height={h} rx={r}
      fill={color.fill} stroke="rgba(255,255,255,0.15)" strokeWidth="1" />
    <text x={x + w / 2} y={y + (sub ? h / 2 - 7 : h / 2 + 1)}
      textAnchor="middle" fill={color.text} fontSize="12" fontWeight="600">{title}</text>
    {sub && <text x={x + w / 2} y={y + h / 2 + 10}
      textAnchor="middle" fill={color.text} fontSize="10" opacity="0.8">{sub}</text>}
  </g>
);

const Arrow = ({ x1, y1, x2, y2, label, color = "#94a3b8" }) => {
  const dx = x2 - x1, dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
  return (
    <g>
      <defs>
        <marker id={`arr-${x1}-${y1}`} viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="6" markerHeight="6" orient="auto">
          <path d="M2 1L8 5L2 9" fill="none" stroke={color} strokeWidth="1.5"
            strokeLinecap="round" strokeLinejoin="round" />
        </marker>
      </defs>
      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={color} strokeWidth="1.5"
        markerEnd={`url(#arr-${x1}-${y1})`} />
      {label && <text x={mx + 4} y={my - 4} fill="#94a3b8" fontSize="9">{label}</text>}
    </g>
  );
};

// ── Diagram 1: System Architecture ───────────────────────────────────────────
function ArchDiagram() {
  return (
    <svg viewBox="0 0 660 520" width="100%" style={{ display: "block" }}>
      <Box x={205} y={20}  w={250} h={54} color={C.teal}   title="WSN Sensors & Tags" sub="Environmental · Localisation" />
      <Arrow x1={330} y1={74} x2={330} y2={108} label="wireless" />
      <Box x={205} y={110} w={250} h={54} color={C.teal}   title="Mother Station" sub="Single network gateway" />
      <Arrow x1={330} y1={164} x2={330} y2={198} label="MQTT" />
      <Box x={205} y={200} w={250} h={54} color={C.blue}   title="MQTT Broker (Mosquitto)" sub="wsn/env · wsn/location" />

      {/* split arrows */}
      <Arrow x1={280} y1={254} x2={140} y2={308} color="#60a5fa" label="persist" />
      <Arrow x1={380} y1={254} x2={520} y2={308} color="#60a5fa" label="update" />

      <Box x={30}  y={310} w={220} h={64} color={C.gray}   title="PostgreSQL" sub="Raw events · State history · Snapshots" />
      <Box x={400} y={310} w={230} h={64} color={C.purple} title="Digital Twin Engine" sub="State · Rules · Watchdog · Predictor" />

      {/* engine → 3 responsibilities */}
      <Arrow x1={440} y1={374} x2={380} y2={420} color="#a78bfa" />
      <Arrow x1={515} y1={374} x2={515} y2={420} color="#a78bfa" />
      <Arrow x1={590} y1={374} x2={640} y2={420} color="#a78bfa" />

      <Box x={300} y={422} w={150} h={50} color={C.purple} title="Monitor & Access" sub="Authorisation rules" />
      <Box x={460} y={422} w={150} h={50} color={C.amber}  title="If-Else Scenarios" sub="Reactive rules" />
      <Box x={570} y={422} w={80}  h={50} color={C.coral}  title="Predict" sub="Defaults" />

      {/* engine → DB (state snapshots) */}
      <path d="M400 450 Q200 490 140 376" fill="none" stroke="#6d28d9"
        strokeWidth="1" strokeDasharray="5 3"
        markerEnd="url(#arr-400-450)" />
      <defs>
        <marker id="arr-400-450" viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="5" markerHeight="5" orient="auto">
          <path d="M2 1L8 5L2 9" fill="none" stroke="#6d28d9" strokeWidth="1.5"
            strokeLinecap="round" />
        </marker>
      </defs>

      {/* output bar */}
      <Box x={30} y={490} w={600} h={24} r={6} color={C.gray}
        title="Frontend Dashboard · Alert Notifications · Actuator Commands" />
      <Arrow x1={140} y1={374} x2={200} y2={488} color="#6b7280" />
      <Arrow x1={460} y1={472} x2={360} y2={488} color="#6d28d9" />
    </svg>
  );
}

// ── Diagram 2: Factory Grid ───────────────────────────────────────────────────
function GridDiagram() {
  const zones = [
    { id: "A", col: 0, row: 0, cols: 2, rows: 2, color: "#0d948822" },
    { id: "B", col: 2, row: 0, cols: 2, rows: 2, color: "#1d6eb522" },
    { id: "C", col: 0, row: 2, cols: 1, rows: 2, color: "#b4530922" },
    { id: "D", col: 1, row: 2, cols: 3, rows: 2, color: "#6d28d922" },
  ];
  const sensors = [
    { id: "S1",  col: 0, row: 0, zone: "A" },
    { id: "S2",  col: 1, row: 0, zone: "A" },
    { id: "S3",  col: 2, row: 0, zone: "B" },
    { id: "S4",  col: 3, row: 0, zone: "B" },
    { id: "S5",  col: 0, row: 1, zone: "A" },
    { id: "S6",  col: 1, row: 1, zone: "A" },
    { id: "S7",  col: 2, row: 1, zone: "B" },
    { id: "S8",  col: 3, row: 1, zone: "B" },
    { id: "S9",  col: 0, row: 2, zone: "C" },
    { id: "S10", col: 1, row: 2, zone: "D" },
    { id: "S11", col: 2, row: 2, zone: "D" },
    { id: "S12", col: 3, row: 2, zone: "D" },
    { id: "S13", col: 0, row: 3, zone: "C" },
    { id: "S14", col: 1, row: 3, zone: "D" },
    { id: "S15", col: 2, row: 3, zone: "D" },
    { id: "S16", col: 3, row: 3, zone: "D" },
  ];
  const zoneColors = { A: "#0d9488", B: "#1d6eb5", C: "#b45309", D: "#6d28d9" };
  const GX = 40, GY = 40, CELL = 90;

  return (
    <svg viewBox="0 0 660 460" width="100%" style={{ display: "block" }}>
      {/* Zone fills */}
      {zones.map(z => (
        <rect key={z.id}
          x={GX + z.col * CELL} y={GY + z.row * CELL}
          width={z.cols * CELL} height={z.rows * CELL}
          fill={z.color} stroke={zoneColors[z.id]} strokeWidth="2" rx="4" />
      ))}
      {/* Zone labels */}
      {zones.map(z => (
        <text key={z.id + "l"}
          x={GX + z.col * CELL + (z.cols * CELL) / 2}
          y={GY + z.row * CELL + 16}
          textAnchor="middle" fill={zoneColors[z.id]}
          fontSize="13" fontWeight="700" opacity="0.8">
          Zone {z.id}
        </text>
      ))}
      {/* Grid lines */}
      {[1, 2, 3].map(c => (
        <line key={"v" + c} x1={GX + c * CELL} y1={GY} x2={GX + c * CELL} y2={GY + 4 * CELL}
          stroke="rgba(255,255,255,0.15)" strokeWidth="1" strokeDasharray="4 3" />
      ))}
      {[1, 2, 3].map(r => (
        <line key={"h" + r} x1={GX} y1={GY + r * CELL} x2={GX + 4 * CELL} y2={GY + r * CELL}
          stroke="rgba(255,255,255,0.15)" strokeWidth="1" strokeDasharray="4 3" />
      ))}
      {/* Sensors */}
      {sensors.map(s => {
        const cx = GX + s.col * CELL + CELL / 2;
        const cy = GY + s.row * CELL + CELL / 2;
        return (
          <g key={s.id}>
            <circle cx={cx} cy={cy} r={22}
              fill={zoneColors[s.zone]} opacity="0.9"
              stroke="rgba(255,255,255,0.3)" strokeWidth="1" />
            <text x={cx} y={cy + 1} textAnchor="middle" dominantBaseline="central"
              fill="white" fontSize="10" fontWeight="700">{s.id}</text>
          </g>
        );
      })}
      {/* Worker asset */}
      <rect x={GX + 1 * CELL + 30} y={GY + 1 * CELL + 28} width={32} height={32} rx={4}
        fill="#1e293b" stroke="#f59e0b" strokeWidth="2" />
      <text x={GX + 1 * CELL + 46} y={GY + 1 * CELL + 44}
        textAnchor="middle" dominantBaseline="central" fontSize="16">👷</text>
      <text x={GX + 1 * CELL + 46} y={GY + 1 * CELL + 68}
        textAnchor="middle" fill="#f59e0b" fontSize="9" fontWeight="600">W1→S6</text>

      {/* Forklift asset */}
      <rect x={GX + 2 * CELL + 30} y={GY + 2 * CELL + 28} width={32} height={32} rx={4}
        fill="#1e293b" stroke="#a78bfa" strokeWidth="2" />
      <text x={GX + 2 * CELL + 46} y={GY + 2 * CELL + 44}
        textAnchor="middle" dominantBaseline="central" fontSize="16">🚜</text>
      <text x={GX + 2 * CELL + 46} y={GY + 2 * CELL + 68}
        textAnchor="middle" fill="#a78bfa" fontSize="9" fontWeight="600">F1→S11</text>

      {/* Legend */}
      <rect x={420} y={40} width={220} height={310} rx={8}
        fill="#1e293b" stroke="rgba(255,255,255,0.1)" strokeWidth="1" />
      <text x={530} y={62} textAnchor="middle" fill="white" fontSize="13" fontWeight="700">Legend</text>
      {Object.entries(zoneColors).map(([z, c], i) => (
        <g key={z}>
          <rect x={436} y={76 + i * 36} width={14} height={14} rx={2} fill={c} />
          <text x={458} y={87 + i * 36} fill="#94a3b8" fontSize="11">Zone {z}</text>
        </g>
      ))}
      <line x1={436} y1={226} x2={624} y2={226} stroke="rgba(255,255,255,0.1)" strokeWidth="1" />
      <text x={530} y={246} textAnchor="middle" fill="white" fontSize="11" fontWeight="600">Auth examples</text>
      <text x={436} y={266} fill="#94a3b8" fontSize="10">W1: zones [A,B] = sensors</text>
      <text x={436} y={280} fill="#94a3b8" fontSize="10">[S1,S2,S3,S4,S5,S6,S7,S8]</text>
      <text x={436} y={300} fill="#94a3b8" fontSize="10">F1: zones [D] = sensors</text>
      <text x={436} y={314} fill="#94a3b8" fontSize="10">[S10,S11,S14,S15,S16]</text>

      {/* Key */}
      <rect x={40} y={410} width={360} height={34} rx={6} fill="#1e293b" stroke="rgba(255,255,255,0.1)" strokeWidth="1" />
      <text x={220} y={431} textAnchor="middle" fill="#94a3b8" fontSize="10">
        asset connects to sensor → sensor maps to zone → check authorisation
      </text>
    </svg>
  );
}

// ── Diagram 3: Engine Internals ───────────────────────────────────────────────
function EngineDiagram() {
  return (
    <svg viewBox="0 0 660 500" width="100%" style={{ display: "block" }}>
      {/* Container */}
      <rect x={20} y={20} width={620} height={390} rx={12}
        fill="#1e293b" stroke="#6d28d9" strokeWidth="1.5" />
      <text x={330} y={44} textAnchor="middle" fill="#a78bfa" fontSize="14" fontWeight="700">
        Digital Twin Engine
      </text>

      {/* Row 1 */}
      <Box x={40}  y={60} w={160} h={56} color={C.teal}   title="MQTT Consumer" sub="Event ingestion" />
      <Box x={220} y={60} w={160} h={56} color={C.blue}   title="Asset State Mgr" sub="In-memory store" />
      <Box x={400} y={60} w={160} h={56} color={C.amber}  title="Rule Engine" sub="Threshold evaluator" />
      <Arrow x1={200} y1={88} x2={218} y2={88} color="#60a5fa" />
      <Arrow x1={380} y1={88} x2={398} y2={88} color="#60a5fa" />

      {/* Row 2 */}
      <Box x={40}  y={170} w={160} h={56} color={C.teal}   title="Zone Resolver" sub="sensor → zone" />
      <Box x={220} y={170} w={160} h={56} color={C.blue}   title="Env Aggregator" sub="temp, humidity, smoke" />
      <Box x={400} y={170} w={160} h={56} color={C.purple} title="Watchdog" sub="Sensor health polling" />

      <Arrow x1={120} y1={170} x2={120} y2={118} color="#0d9488" />
      <Arrow x1={300} y1={170} x2={300} y2={118} color="#1d6eb5" />
      <Arrow x1={480} y1={116} x2={480} y2={168} color="#6d28d9" />

      {/* Row 3 */}
      <Box x={40}  y={280} w={160} h={56} color={C.coral}  title="Predictor" sub="Trend detection" />
      <Box x={220} y={280} w={160} h={56} color={C.amber}  title="Access Control" sub="Authorisation check" />
      <Box x={400} y={280} w={160} h={56} color={C.gray}   title="Publisher" sub="WebSocket · alerts" />

      <Arrow x1={200} y1={198} x2={130} y2={278} color="#94a3b8" />
      <Arrow x1={300} y1={226} x2={300} y2={278} color="#94a3b8" />
      <Arrow x1={400} y1={198} x2={400} y2={278} color="#94a3b8" />
      <Arrow x1={380} y1={308} x2={400} y2={308} color="#94a3b8" />
      <Arrow x1={200} y1={308} x2={218} y2={308} color="#94a3b8" />

      {/* Persistence bar */}
      <Box x={40} y={360} w={560} h={40} r={6} color={C.gray}
        title="Persistence — PostgreSQL (events, snapshots) · State history" />
      <Arrow x1={300} y1={336} x2={300} y2={358} color="#6b7280" />

      {/* External labels */}
      <rect x={20} y={420} width={140} height={30} rx={6} fill="#0f172a" stroke="rgba(255,255,255,0.1)" strokeWidth="1" />
      <text x={90} y={439} textAnchor="middle" fill="#94a3b8" fontSize="10">WSN / MQTT events</text>
      <Arrow x1={90} y1={420} x2={90} y2={118} color="#0d9488" />

      <rect x={500} y={420} width={140} height={30} rx={6} fill="#0f172a" stroke="rgba(255,255,255,0.1)" strokeWidth="1" />
      <text x={570} y={439} textAnchor="middle" fill="#94a3b8" fontSize="10">Frontend · Alerts</text>
      <Arrow x1={480} y1={420} x2={490} y2={338} color="#6b7280" />
    </svg>
  );
}

// ── Diagram 4: Event Flow ─────────────────────────────────────────────────────
function FlowDiagram() {
  const steps = [
    { color: C.teal,   title: "Incoming WSN message",      sub: "['asset_id'|'sensor_id', 'reading_type', value, ts]" },
    { color: C.gray,   title: "Validate & deserialise",    sub: "mqtt_parser.route_message(topic, payload)" },
    { color: C.blue,   title: "Watchdog heartbeat",        sub: "watchdog.on_message_received(sensor_id)" },
    { color: C.blue,   title: "Update state",              sub: "store.update_sensor_reading() or update_asset_location()" },
    { color: C.amber,  title: "Evaluate rules",            sub: "check_access · evaluate_scenarios · predict" },
  ];
  const Y0 = 30, STEP = 84;
  return (
    <svg viewBox="0 0 660 520" width="100%" style={{ display: "block" }}>
      {steps.map((s, i) => (
        <g key={i}>
          <Box x={205} y={Y0 + i * STEP} w={250} h={56} color={s.color} title={s.title} sub={s.sub} />
          {i < steps.length - 1 && <Arrow x1={330} y1={Y0 + i * STEP + 56} x2={330} y2={Y0 + (i + 1) * STEP} />}
        </g>
      ))}

      {/* Diamond: alert? */}
      <polygon points="330,456 390,476 330,496 270,476"
        fill="#1e293b" stroke="#f59e0b" strokeWidth="1.5" />
      <text x={330} y={480} textAnchor="middle" dominantBaseline="central" fill="#fbbf24" fontSize="11" fontWeight="600">alert?</text>
      <Arrow x1={330} y1={448} x2={330} y2={454} />

      {/* Yes: alert */}
      <Arrow x1={390} y1={476} x2={490} y2={476} color="#ef4444" label="yes" />
      <Box x={492} y={456} w={140} h={42} r={6} color={C.red} title="Publish alert" sub="save_event + push" />
      <text x={432} y={470} fill="#ef4444" fontSize="9">yes</text>

      {/* No: persist + push */}
      <Arrow x1={330} y1={496} x2={330} y2={516} label="always" />
      <Box x={205} y={518} w={250} h={0} color={C.purple} title="" />

      {/* Always branch */}
      <rect x={130} y={498} width={400} height={16} rx={4}
        fill="#6d28d9" opacity="0.15" />
      <text x={330} y={510} textAnchor="middle" fill="#a78bfa" fontSize="9">
        persist state → push sensor/asset update → compute &amp; push SystemState
      </text>

      {/* Alert also → persist */}
      <path d="M562 498 L562 508 L332 508" fill="none" stroke="#b91c1c"
        strokeWidth="1" strokeDasharray="4 3" />
    </svg>
  );
}

// ── Diagram 5: System State Model ─────────────────────────────────────────────
function StateDiagram() {
  const pillars = [
    {
      title: "Sensor Health", color: C.teal, x: 20,
      states: [
        { label: "● Online",    sub: "Heartbeat within threshold", c: C.green },
        { label: "◑ Degraded",  sub: "Noisy / packet loss",        c: C.amber },
        { label: "○ Offline",   sub: "No heartbeat — check/replace", c: C.red },
      ],
      fields: "sensor_id · zone_id · status\nlast_heartbeat · consecutive_failures",
    },
    {
      title: "Environmental", color: C.blue, x: 236,
      states: [
        { label: "● Normal",   sub: "All readings in safe range",  c: C.green },
        { label: "◑ Warning",  sub: "Trending toward threshold",   c: C.amber },
        { label: "● Critical", sub: "Smoke / threshold breach",    c: C.red },
      ],
      fields: "sensor_id · zone_id · temp\nhumidity · smoke · env_status",
    },
    {
      title: "Access Control", color: C.purple, x: 452,
      states: [
        { label: "● Authorised", sub: "In allowed sensor/zone",      c: C.green },
        { label: "◑ Unknown",    sub: "Sensor offline — unconfirmed", c: C.amber },
        { label: "● Violation",  sub: "Unauthorised zone entered",    c: C.red },
      ],
      fields: "asset_id · sensor_id · zone_id\nallowed_sensors · allowed_zones",
    },
  ];

  return (
    <svg viewBox="0 0 660 500" width="100%" style={{ display: "block" }}>
      {pillars.map((p) => (
        <g key={p.title}>
          <rect x={p.x} y={20} width={196} height={290} rx={10}
            fill={p.color.fill} opacity="0.12"
            stroke={p.color.fill} strokeWidth="1.5" />
          <text x={p.x + 98} y={42} textAnchor="middle"
            fill={p.color.fill} fontSize="12" fontWeight="700">{p.title}</text>
          {p.states.map((s, i) => (
            <g key={i}>
              <rect x={p.x + 10} y={54 + i * 68} width={176} height={54} rx={6}
                fill={s.c.fill} opacity="0.85"
                stroke="rgba(255,255,255,0.15)" strokeWidth="1" />
              <text x={p.x + 98} y={76 + i * 68} textAnchor="middle"
                fill={s.c.text} fontSize="11" fontWeight="600">{s.label}</text>
              <text x={p.x + 98} y={93 + i * 68} textAnchor="middle"
                fill={s.c.text} fontSize="9" opacity="0.85">{s.sub}</text>
            </g>
          ))}
          {/* Fields box */}
          <rect x={p.x + 10} y={260} width={176} height={44} rx={6}
            fill="#1e293b" stroke="rgba(255,255,255,0.1)" strokeWidth="1" />
          {p.fields.split("\n").map((line, i) => (
            <text key={i} x={p.x + 98} y={277 + i * 14} textAnchor="middle"
              fill="#94a3b8" fontSize="9">{line}</text>
          ))}
        </g>
      ))}

      {/* Arrows down to SystemState */}
      <Arrow x1={118} y1={312} x2={180} y2={358} />
      <Arrow x1={334} y1={312} x2={334} y2={358} />
      <Arrow x1={550} y1={312} x2={488} y2={358} />

      {/* SystemState box */}
      <Box x={30} y={360} w={600} h={68} color={C.gray}
        title="SystemState — global aggregate (real-time)"
        sub="sensors_online/degraded/offline · zones_normal/warning/critical · violations · overall_status" />

      {/* Status indicators */}
      {[
        { label: "NOMINAL",  color: "#15803d", x: 80  },
        { label: "DEGRADED", color: "#b45309", x: 280 },
        { label: "CRITICAL", color: "#b91c1c", x: 480 },
      ].map(s => (
        <g key={s.label}>
          <rect x={s.x} y={444} width={100} height={28} rx={4} fill={s.color} opacity="0.9" />
          <text x={s.x + 50} y={462} textAnchor="middle" fill="white"
            fontSize="11" fontWeight="700">{s.label}</text>
        </g>
      ))}
      <Arrow x1={334} y1={430} x2={334} y2={442} />

      {/* Frontend */}
      <Box x={30} y={480} w={600} h={18} r={4} color={{ fill: "#0f172a", text: "#94a3b8" }}
        title="→ Frontend WebSocket push on every state change" />
    </svg>
  );
}

const DIAGRAMS = { arch: ArchDiagram, grid: GridDiagram, engine: EngineDiagram, flow: FlowDiagram, state: StateDiagram };

export default function App() {
  const [active, setActive] = useState("arch");
  const Diagram = DIAGRAMS[active];

  return (
    <div style={{
      background: "#0f172a", minHeight: "100vh", color: "white",
      fontFamily: "'DM Mono', 'Fira Code', monospace",
      padding: "0",
    }}>
      {/* Header */}
      <div style={{
        borderBottom: "1px solid rgba(255,255,255,0.08)",
        padding: "20px 28px 0",
        background: "linear-gradient(180deg, #1e293b 0%, #0f172a 100%)",
      }}>
        <div style={{ fontSize: 11, color: "#6d28d9", letterSpacing: 3, textTransform: "uppercase", marginBottom: 6 }}>
          Factory Digital Twin
        </div>
        <div style={{ fontSize: 20, fontWeight: 700, color: "#f1f5f9", marginBottom: 16 }}>
          System Architecture & Design
        </div>
        {/* Tabs */}
        <div style={{ display: "flex", gap: 4 }}>
          {TABS.map(t => (
            <button key={t.id} onClick={() => setActive(t.id)} style={{
              padding: "8px 16px", fontSize: 11, fontWeight: 600,
              border: "none", borderRadius: "6px 6px 0 0", cursor: "pointer",
              background: active === t.id ? "#1e293b" : "transparent",
              color: active === t.id ? "#a78bfa" : "#64748b",
              borderBottom: active === t.id ? "2px solid #6d28d9" : "2px solid transparent",
              transition: "all 0.15s",
              fontFamily: "inherit",
            }}>{t.label}</button>
          ))}
        </div>
      </div>

      {/* Diagram area */}
      <div style={{
        padding: "28px",
        background: "#0f172a",
        minHeight: "calc(100vh - 120px)",
      }}>
        <div style={{
          background: "#1e293b",
          borderRadius: 12,
          border: "1px solid rgba(255,255,255,0.07)",
          padding: "20px",
          maxWidth: 700,
          margin: "0 auto",
        }}>
          <Diagram />
        </div>

        {/* Captions */}
        <div style={{
          maxWidth: 700, margin: "16px auto 0",
          fontSize: 11, color: "#475569", lineHeight: 1.6,
          borderLeft: "2px solid #6d28d9", paddingLeft: 12,
        }}>
          {{
            arch:   "WSN → Mother Station → MQTT Broker → PostgreSQL + Digital Twin Engine. The engine drives state, rules, watchdog, and predictor. All outputs flow to the frontend via WebSocket.",
            grid:   "Full factory coverage: every grid cell has exactly one sensor. Zones span one or more cells. Assets are located by sensor connection; authorisation is checked at both sensor and zone level.",
            engine: "Five internal subsystems: ingestion, state management, zone resolution, rule evaluation, and persistence. The watchdog runs as a background async loop independently of the MQTT handler.",
            flow:   "Every incoming WSN message follows this path: validate → heartbeat → state update → rule evaluation → conditional alert → always persist + push SystemState to frontend.",
            state:  "Three real-time pillars combine into a single SystemState aggregate. Overall status is CRITICAL if any pillar has a critical condition, DEGRADED if any warning, NOMINAL otherwise.",
          }[active]}
        </div>
      </div>
    </div>
  );
}
