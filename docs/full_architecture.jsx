import { useState } from "react";

/* ─── Design tokens ─────────────────────────────────────────────────────────── */
const T = {
  bg:       "#050c1a",
  surface:  "#0d1829",
  border:   "rgba(255,255,255,0.06)",
  muted:    "#334155",
  text:     "#e2e8f0",
  subtle:   "#64748b",
  teal:     "#14b8a6",
  blue:     "#3b82f6",
  indigo:   "#6366f1",
  purple:   "#a855f7",
  amber:    "#f59e0b",
  coral:    "#f97316",
  red:      "#ef4444",
  green:    "#22c55e",
  cyan:     "#06b6d4",
};

/* ─── Layer colour map ───────────────────────────────────────────────────────── */
const LC = {
  wsn:        { stroke: T.teal,   fill: "#14b8a608", label: "#14b8a6" },
  gateway:    { stroke: T.cyan,   fill: "#06b6d408", label: "#06b6d4" },
  mqtt:       { stroke: T.blue,   fill: "#3b82f608", label: "#3b82f6" },
  engine:     { stroke: T.indigo, fill: "#6366f110", label: "#a5b4fc" },
  store:      { stroke: T.purple, fill: "#a855f710", label: "#d8b4fe" },
  rules:      { stroke: T.amber,  fill: "#f59e0b10", label: "#fcd34d" },
  persist:    { stroke: T.muted,  fill: "#33415510", label: "#94a3b8" },
  api:        { stroke: T.coral,  fill: "#f9731608", label: "#fdba74" },
  frontend:   { stroke: T.green,  fill: "#22c55e08", label: "#86efac" },
};

/* ─── Reusable SVG primitives ────────────────────────────────────────────────── */
const Chip = ({ x, y, w, h = 36, rx = 6, fill, stroke, title, sub, fs = 10, fw = 600 }) => (
  <g>
    <rect x={x} y={y} width={w} height={h} rx={rx}
      fill={fill || "rgba(255,255,255,0.04)"}
      stroke={stroke || "rgba(255,255,255,0.1)"} strokeWidth="1" />
    <text x={x + w / 2} y={y + (sub ? h / 2 - 5 : h / 2 + 1)}
      textAnchor="middle" dominantBaseline="central"
      fill={T.text} fontSize={fs} fontWeight={fw}>{title}</text>
    {sub && <text x={x + w / 2} y={y + h / 2 + 9}
      textAnchor="middle" fill={T.subtle} fontSize={fs - 1}>{sub}</text>}
  </g>
);

const LayerBox = ({ x, y, w, h, lc, label, children }) => (
  <g>
    <rect x={x} y={y} width={w} height={h} rx={10}
      fill={lc.fill} stroke={lc.stroke} strokeWidth="1.2" />
    <rect x={x + 10} y={y - 9} width={label.length * 7.2 + 16} height={18} rx={4}
      fill={T.bg} stroke={lc.stroke} strokeWidth="1" />
    <text x={x + 18} y={y + 0.5} dominantBaseline="middle"
      fill={lc.label} fontSize={9.5} fontWeight={700} letterSpacing="0.5">{label}</text>
    {children}
  </g>
);

const flow = (x1, y1, x2, y2, col = T.muted, dash = false) => {
  const id = `a${x1}${y1}${x2}${y2}`.replace(/\./g, "");
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
    </g>
  );
};

const flowPath = (d, col = T.muted, dash = false) => {
  const id = `p${d.replace(/[^0-9]/g, "").slice(0, 12)}`;
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

const Tag = ({ x, y, text, col }) => (
  <g>
    <rect x={x} y={y} width={text.length * 6.4 + 10} height={15} rx={3}
      fill={col + "22"} stroke={col} strokeWidth="0.8" />
    <text x={x + 5} y={y + 8} dominantBaseline="middle"
      fill={col} fontSize={8} fontWeight={700}>{text}</text>
  </g>
);

/* ─── Legend ──────────────────────────────────────────────────────────────────── */
const Legend = ({ x, y }) => {
  const items = [
    { col: T.teal,   label: "WSN / Physical" },
    { col: T.cyan,   label: "Gateway" },
    { col: T.blue,   label: "Messaging" },
    { col: T.indigo, label: "Twin Engine" },
    { col: T.purple, label: "State Store" },
    { col: T.amber,  label: "Rule Engine" },
    { col: T.muted,  label: "Persistence" },
    { col: T.coral,  label: "API Layer" },
    { col: T.green,  label: "Frontend" },
  ];
  return (
    <g>
      <rect x={x} y={y} width={148} height={items.length * 18 + 22} rx={8}
        fill={T.surface} stroke={T.border} strokeWidth="1" />
      <text x={x + 74} y={y + 13} textAnchor="middle"
        fill={T.subtle} fontSize={9} fontWeight={700} letterSpacing="0.5">LEGEND</text>
      {items.map((it, i) => (
        <g key={i}>
          <rect x={x + 12} y={y + 22 + i * 18} width={10} height={10} rx={2} fill={it.col + "44"} stroke={it.col} strokeWidth="1" />
          <text x={x + 28} y={y + 27 + i * 18} dominantBaseline="middle"
            fill={T.subtle} fontSize={9}>{it.label}</text>
        </g>
      ))}
    </g>
  );
};

/* ─── Main diagram ────────────────────────────────────────────────────────────── */
export default function App() {
  const [hover, setHover] = useState(null);
  const W = 860;

  return (
    <div style={{
      background: T.bg, minHeight: "100vh",
      fontFamily: "'IBM Plex Mono', 'Fira Code', monospace",
      padding: "0",
    }}>
      {/* Header */}
      <div style={{
        padding: "18px 28px", borderBottom: `1px solid ${T.border}`,
        background: `linear-gradient(90deg, ${T.surface} 0%, ${T.bg} 100%)`,
        display: "flex", alignItems: "center", gap: 20,
      }}>
        <div>
          <div style={{ fontSize: 9, color: T.indigo, letterSpacing: 3, textTransform: "uppercase", marginBottom: 4 }}>
            Factory Monitoring System
          </div>
          <div style={{ fontSize: 18, fontWeight: 700, color: T.text }}>
            Digital Twin — Full System Architecture
          </div>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 12 }}>
          {[
            { col: T.green,  label: "NOMINAL" },
            { col: T.amber,  label: "DEGRADED" },
            { col: T.red,    label: "CRITICAL" },
          ].map(s => (
            <div key={s.label} style={{
              padding: "4px 10px", borderRadius: 4, fontSize: 9, fontWeight: 700,
              background: s.col + "22", border: `1px solid ${s.col}`, color: s.col,
              letterSpacing: 1,
            }}>{s.label}</div>
          ))}
        </div>
      </div>

      {/* Diagram */}
      <div style={{ overflowX: "auto", padding: "24px 16px" }}>
        <svg viewBox={`0 0 ${W} 1340`} width="100%"
          style={{ display: "block", minWidth: 700, maxWidth: 900, margin: "0 auto" }}>

          {/* ── LAYER 1: WSN Physical ────────────────────────────────────────── */}
          <LayerBox x={10} y={18} w={W - 20} h={112} lc={LC.wsn} label="LAYER 1 — PHYSICAL / WSN  (full factory grid coverage)">

            {/* Worker tags */}
            <Chip x={24} y={34} w={152} h={52} stroke={T.teal}
              title="Worker Tags" sub="UWB / BLE beacons" />
            <text x={100} y={96} textAnchor="middle" fill={T.subtle} fontSize={8}>W1, W2 … Wn</text>

            {/* Object tags */}
            <Chip x={192} y={34} w={152} h={52} stroke={T.teal}
              title="Mobile Object Tags" sub="Forklifts · Pallets · Carts" />
            <text x={268} y={96} textAnchor="middle" fill={T.subtle} fontSize={8}>F1, P1 … On</text>

            {/* Env sensors */}
            <Chip x={360} y={34} w={168} h={52} stroke={T.teal}
              title="Temp / Humidity Sensors" sub="DHT22 · SHT31" />
            <text x={444} y={96} textAnchor="middle" fill={T.subtle} fontSize={8}>S1 … Sn (grid cells)</text>

            {/* Smoke sensors */}
            <Chip x={544} y={34} w={140} h={52} stroke={T.red}
              title="Smoke Sensors" sub="MQ-2 · MQ-9" />
            <text x={614} y={96} textAnchor="middle" fill={T.subtle} fontSize={8}>co-located with Sn</text>

            {/* WSN grid note */}
            <Chip x={700} y={34} w={148} h={52} stroke={T.muted}
              title="Factory Grid" sub="Every cell = 1 sensor" />
            <text x={774} y={96} textAnchor="middle" fill={T.subtle} fontSize={8}>Full coverage · no blind spots</text>
          </LayerBox>

          {/* Arrows: WSN → mother station */}
          {flow(100, 130, 100, 166, T.teal)}
          {flow(268, 130, 268, 166, T.teal)}
          {flow(444, 130, 444, 166, T.teal)}
          {flow(614, 130, 614, 166, T.teal)}
          {flow(774, 130, 774, 166, T.teal)}
          <text x={430} y={152} textAnchor="middle" fill={T.teal} fontSize={8} opacity="0.7">short-range wireless</text>

          {/* ── LAYER 2: Mother Station ──────────────────────────────────────── */}
          <LayerBox x={10} y={168} w={W - 20} h={72} lc={LC.gateway} label="LAYER 2 — MOTHER STATION  (single network gateway)">
            <Chip x={24}  y={34} w={180} h={36} stroke={T.cyan} title="Zone detection" sub="tag → sensor_id" />
            <Chip x={220} y={34} w={180} h={36} stroke={T.cyan} title="Protocol aggregation" sub="proprietary → MQTT" />
            <Chip x={416} y={34} w={180} h={36} stroke={T.cyan} title="Message formatting" sub="['id','type',val,ts]" />
            <Chip x={612} y={34} w={220} h={36} stroke={T.red}  title="Single point — watchdog required" sub="connectivity alert if silent > Ns" />
          </LayerBox>

          {/* Arrow: mother station → MQTT */}
          {flow(430, 240, 430, 274, T.blue)}
          <text x={450} y={260} fill={T.blue} fontSize={8} opacity="0.8">MQTT / TCP-IP</text>

          {/* ── LAYER 3: MQTT Broker ─────────────────────────────────────────── */}
          <LayerBox x={10} y={276} w={W - 20} h={72} lc={LC.mqtt} label="LAYER 3 — MQTT BROKER  (Mosquitto)">
            <Chip x={24}  y={30} w={200} h={36} stroke={T.blue} title="Topic: wsn/env" sub="['sensor_id','temp|hum|smoke',val,ts]" />
            <Chip x={240} y={30} w={220} h={36} stroke={T.blue} title="Topic: wsn/location" sub="['worker_id|object_id','sensor_id',ts]" />
            <Chip x={476} y={30} w={160} h={36} stroke={T.blue} title="QoS Level 1" sub="at-least-once delivery" />
            <Chip x={652} y={30} w={186} h={36} stroke={T.muted} title="wsn/alerts (optional)" sub="station-level alerts" />
          </LayerBox>

          {/* Arrow: MQTT → Engine */}
          {flow(430, 348, 430, 382, T.indigo)}
          <text x={450} y={368} fill={T.indigo} fontSize={8} opacity="0.8">subscribe</text>

          {/* ── LAYER 4: Digital Twin Engine ─────────────────────────────────── */}
          <LayerBox x={10} y={384} w={W - 20} h={470} lc={LC.engine} label="LAYER 4 — DIGITAL TWIN ENGINE">

            {/* ─ 4a: Ingestion row */}
            <text x={20} y={28} fill={LC.engine.label} fontSize={8} fontWeight={700} opacity="0.7">INGESTION</text>
            <Chip x={20}  y={36} w={178} h={40} stroke={T.indigo} title="MQTT Consumer" sub="paho.mqtt · loop_forever()" />
            <Chip x={214} y={36} w={178} h={40} stroke={T.indigo} title="mqtt_parser" sub="route_message(topic, payload)" />
            <Chip x={408} y={36} w={178} h={40} stroke={T.indigo} title="ZoneRegistry" sub="sensor_id → zone_id" />
            <Chip x={602} y={36} w={230} h={40} stroke={T.cyan}   title="SensorWatchdog" sub="heartbeat per sensor · async loop" />

            {flow(198, 56, 212, 56, T.indigo)}
            {flow(392, 56, 406, 56, T.indigo)}
            {flow(602, 56, 586, 56, T.cyan)}

            {/* ─ 4b: State store */}
            <rect x={10} y={92} width={W - 40} height={118} rx={8}
              fill="#a855f706" stroke={T.purple} strokeWidth="0.8" />
            <text x={20} y={108} fill={LC.store.label} fontSize={8} fontWeight={700} opacity="0.8">STATE STORE  (in-memory · O(1) reads · rehydrated from DB on startup)</text>

            {/* AssetState */}
            <Chip x={20} y={114} w={192} h={88} stroke={T.purple}
              title="AssetState" fs={10} fw={700} />
            {[
              "id · asset_type",
              "current_sensor_id",
              "current_zone_id",
              "previous_sensor_id",
              "previous_zone_id",
              "time_change_location",
              "allowed_sensors (set)",
              "allowed_zones (set)",
              "access_status",
            ].map((line, i) => (
              <text key={i} x={116} y={133 + i * 9.6} textAnchor="middle"
                fill={T.subtle} fontSize={8}>{line}</text>
            ))}

            {/* SensorState */}
            <Chip x={228} y={114} w={180} h={88} stroke={T.teal} title="SensorState" fs={10} fw={700} />
            {[
              "sensor_id",
              "zone_id",
              "temperature (°C)",
              "humidity (%)",
              "smoke (bool)",
              "env_status",
              "last_time_change",
            ].map((line, i) => (
              <text key={i} x={318} y={133 + i * 11.2} textAnchor="middle"
                fill={T.subtle} fontSize={8}>{line}</text>
            ))}

            {/* SensorHealthState */}
            <Chip x={424} y={114} w={198} h={88} stroke={T.amber} title="SensorHealthState" fs={10} fw={700} />
            {[
              "sensor_id · zone_id",
              "status: ONLINE",
              "       DEGRADED",
              "       OFFLINE",
              "last_heartbeat",
              "last_reading",
              "consecutive_failures",
            ].map((line, i) => (
              <text key={i} x={523} y={133 + i * 11.2} textAnchor="middle"
                fill={T.subtle} fontSize={8}>{line}</text>
            ))}

            {/* SystemState */}
            <Chip x={638} y={114} w={194} h={88} stroke={T.green} title="SystemState" fs={10} fw={700} />
            {[
              "overall_status",
              "sensors_online/degraded",
              "sensors_offline",
              "zones_normal/warning",
              "zones_critical",
              "access_violations",
              "unknown_locations",
            ].map((line, i) => (
              <text key={i} x={735} y={133 + i * 11.2} textAnchor="middle"
                fill={T.subtle} fontSize={8}>{line}</text>
            ))}

            {/* ─ 4c: Rule engine row */}
            <rect x={10} y={224} width={W - 40} height={110} rx={8}
              fill="#f59e0b06" stroke={T.amber} strokeWidth="0.8" />
            <text x={20} y={240} fill={LC.rules.label} fontSize={8} fontWeight={700} opacity="0.8">RULE ENGINE</text>

            {/* Access control */}
            <Chip x={20} y={248} w={190} h={78} stroke={T.red} title="Access Control" fs={10} fw={700} />
            <text x={115} y={268} textAnchor="middle" fill={T.subtle} fontSize={8}>check_access(asset)</text>
            <text x={115} y={280} textAnchor="middle" fill={T.subtle} fontSize={8}>sensor offline → UNKNOWN</text>
            <text x={115} y={292} textAnchor="middle" fill={T.subtle} fontSize={8}>sensor_id ∈ allowed_sensors?</text>
            <text x={115} y={304} textAnchor="middle" fill={T.subtle} fontSize={8}>zone_id ∈ allowed_zones?</text>
            <text x={115} y={316} textAnchor="middle" fill={T.red} fontSize={8} fontWeight={700}>→ VIOLATION alert</text>

            {/* If-else scenarios */}
            <Chip x={226} y={248} w={214} h={78} stroke={T.amber} title="If-Else Scenarios" fs={10} fw={700} />
            {[
              "smoke_detected → evacuate_zone",
              "high_temperature → inspect",
              "temp_warning → monitor",
              "high_humidity → ventilation",
              "workers_in_smoke → emergency",
              "workers_in_high_temp → emergency",
            ].map((line, i) => (
              <text key={i} x={333} y={266 + i * 10.2} textAnchor="middle"
                fill={T.subtle} fontSize={7.5}>{line}</text>
            ))}

            {/* Predictor */}
            <Chip x={456} y={248} w={198} h={78} stroke={T.purple} title="Predictor" fs={10} fw={700} />
            {[
              "predict_critical_states(sensor, history)",
              "• temp trend → predicted_critical",
              "• intermittent_smoke → warning",
              "• rapid humidity rise → warning",
              "rolling history (last 20 readings)",
              "→ replace with ML model later",
            ].map((line, i) => (
              <text key={i} x={555} y={266 + i * 10.2} textAnchor="middle"
                fill={T.subtle} fontSize={7.5}>{line}</text>
            ))}

            {/* compute_system_state */}
            <Chip x={670} y={248} w={162} h={78} stroke={T.green} title="compute_system_state()" fs={9} fw={700} />
            {[
              "assets + sensors + health",
              "→ SystemState aggregate",
              "called after every update:",
              "• env reading",
              "• location update",
              "• watchdog tick",
            ].map((line, i) => (
              <text key={i} x={751} y={266 + i * 10.5} textAnchor="middle"
                fill={T.subtle} fontSize={7.5}>{line}</text>
            ))}

            {/* ─ 4d: Publisher row */}
            <text x={20} y={360} fill={LC.engine.label} fontSize={8} fontWeight={700} opacity="0.7">PUBLISHER</text>
            <Chip x={20}  y={368} w={190} h={40} stroke={T.coral}
              title="WebSocket Publisher" sub="broadcast to all clients" />
            <Chip x={226} y={368} w={190} h={40} stroke={T.coral}
              title="push_system_state()" sub="on every tick" />
            <Chip x={432} y={368} w={190} h={40} stroke={T.coral}
              title="push_asset_update()" sub="on location change" />
            <Chip x={638} y={368} w={190} h={40} stroke={T.coral}
              title="push_alert()" sub="rule / scenario / prediction" />

            {flow(210, 388, 224, 388, T.coral)}
            {flow(416, 388, 430, 388, T.coral)}
            {flow(622, 388, 636, 388, T.coral)}

            {/* ─ 4e: Event flow row */}
            <text x={20} y={428} fill={LC.engine.label} fontSize={8} fontWeight={700} opacity="0.5">EVENT FLOW</text>
            {[
              "MQTT msg arrives",
              "validate + parse",
              "watchdog heartbeat",
              "update state store",
              "evaluate rules",
              "persist + push",
            ].map((label, i) => (
              <g key={i}>
                <Chip x={20 + i * 140} y={434} w={132} h={26}
                  stroke={i < 3 ? T.indigo : i < 5 ? T.amber : T.green}
                  title={label} fs={8} fw={600} />
                {i < 5 && flow(154 + i * 140, 447, 160 + i * 140, 447,
                  i < 3 ? T.indigo : i < 5 ? T.amber : T.green)}
              </g>
            ))}
          </LayerBox>

          {/* Arrow: Engine ↔ Persistence */}
          {flow(200, 854, 200, 888, T.muted)}
          {flow(430, 854, 430, 888, T.muted)}
          {flow(660, 888, 660, 854, T.muted, true)}
          <text x={310} y={874} textAnchor="middle" fill={T.muted} fontSize={8}>persist events · read history</text>
          <text x={700} y={874} fill={T.muted} fontSize={8} opacity="0.7">load on startup</text>

          {/* ── LAYER 5: Persistence ─────────────────────────────────────────── */}
          <LayerBox x={10} y={890} w={W - 20} h={134} lc={LC.persist} label="LAYER 5 — PERSISTENCE  (PostgreSQL)">
            {/* Tables row 1 */}
            {[
              { t: "zones",              s: "zone_id · name" },
              { t: "sensors",            s: "sensor_id · zone_id · grid_row · grid_col" },
              { t: "assets",             s: "asset_id · asset_type · name" },
              { t: "authorisations",     s: "asset_id · allowed_type · allowed_id" },
            ].map((tb, i) => (
              <Chip key={i} x={20 + i * 206} y={28} w={196} h={38} stroke={T.muted}
                title={tb.t} sub={tb.s} />
            ))}
            {/* Tables row 2 */}
            {[
              { t: "location_events",      s: "asset_id · sensor_id · zone_id · access_status · ts" },
              { t: "env_readings",         s: "sensor_id · reading_type · value · env_status · ts" },
              { t: "sensor_health_events", s: "sensor_id · status · consecutive_failures · ts" },
              { t: "events",               s: "type · level · message · payload (JSONB) · ts" },
              { t: "system_snapshots",     s: "overall_status · counts · payload · ts" },
            ].map((tb, i) => (
              <Chip key={i} x={20 + i * 165} y={80} w={156} h={38} stroke={T.muted}
                title={tb.t} sub={tb.s} fs={8.5} />
            ))}
          </LayerBox>

          {/* Arrow: Engine → API, Persistence → API */}
          {flow(430, 1024, 430, 1058, T.coral)}
          <text x={450} y={1044} fill={T.coral} fontSize={8} opacity="0.8">REST + WS</text>

          {/* ── LAYER 6: API ─────────────────────────────────────────────────── */}
          <LayerBox x={10} y={1060} w={W - 20} h={72} lc={LC.api} label="LAYER 6 — API GATEWAY">
            <Chip x={24}  y={28} w={210} h={36} stroke={T.coral}
              title="REST API" sub="GET /assets · /zones · /sensors · /events" />
            <Chip x={250} y={28} w={210} h={36} stroke={T.coral}
              title="WebSocket" sub="real-time push to frontend" />
            <Chip x={476} y={28} w={166} h={36} stroke={T.coral}
              title="Event types pushed" sub="system_state · asset_update · alert" />
            <Chip x={658} y={28} w={180} h={36} stroke={T.muted}
              title="Auth (future)" sub="JWT · role-based access" />
          </LayerBox>

          {/* Arrow: API → Frontend */}
          {flow(430, 1132, 430, 1166, T.green)}
          <text x={450} y={1152} fill={T.green} fontSize={8} opacity="0.8">WebSocket push</text>

          {/* ── LAYER 7: Frontend ────────────────────────────────────────────── */}
          <LayerBox x={10} y={1168} w={W - 20} h={130} lc={LC.frontend} label="LAYER 7 — FRONTEND DASHBOARD  (React + Three.js / WebSocket)">
            {/* Row 1 */}
            {[
              { t: "Factory Grid Map",     s: "Live asset positions on sensor grid", col: T.teal },
              { t: "Sensor Health Panel",  s: "Online / Degraded / Offline per cell", col: T.amber },
              { t: "Env Heatmap",          s: "Temp · humidity · smoke per zone", col: T.red },
            ].map((p, i) => (
              <Chip key={i} x={20 + i * 280} y={24} w={268} h={40}
                stroke={p.col} title={p.t} sub={p.s} />
            ))}
            {/* Row 2 */}
            {[
              { t: "Access Log",          s: "Real-time authorisation events", col: T.purple },
              { t: "Alert Panel",         s: "All warnings · criticals · predictions", col: T.red },
              { t: "System Status Banner",s: "NOMINAL / DEGRADED / CRITICAL", col: T.green },
            ].map((p, i) => (
              <Chip key={i} x={20 + i * 280} y={76} w={268} h={40}
                stroke={p.col} title={p.t} sub={p.s} />
            ))}
          </LayerBox>

          {/* ── Cross-cutting arrows ─────────────────────────────────────────── */}
          {/* Engine → persistence (detailed) */}
          {flowPath("M 800 854 Q 840 870 840 940 Q 840 1010 800 1024", T.muted, true)}

          {/* Legend */}
          <Legend x={706} y={1174} />

          {/* Data flow labels on the right rail */}
          {[
            { y: 148,  label: "short-range wireless (proprietary RF / UWB / BLE)" },
            { y: 260,  label: "MQTT / TCP-IP" },
            { y: 368,  label: "MQTT subscribe (wsn/env · wsn/location)" },
            { y: 872,  label: "psycopg2 · SQL read/write" },
            { y: 1044, label: "REST (queries) + WebSocket (push)" },
            { y: 1152, label: "WebSocket events · REST polling" },
          ].map((f, i) => (
            <text key={i} x={W - 14} y={f.y} textAnchor="end"
              fill={T.muted} fontSize={7.5} fontStyle="italic">{f.label}</text>
          ))}

          {/* Title card */}
          <rect x={10} y={1304} width={W - 20} height={28} rx={6}
            fill={T.surface} stroke={T.border} strokeWidth="1" />
          <text x={(W) / 2} y={1322} textAnchor="middle"
            fill={T.subtle} fontSize={9}>
            WSN → Mother Station → MQTT Broker → Digital Twin Engine
            (State · Rules · Watchdog · Predictor · Publisher) → PostgreSQL → API → Frontend
          </text>
        </svg>
      </div>
    </div>
  );
}
