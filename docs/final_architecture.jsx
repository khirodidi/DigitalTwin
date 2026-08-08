// docs/final_architecture.jsx
// Final system architecture — all layers, components, and data flows
// for the scientific paper Digital Twin for Factory Monitoring
import { useState } from "react";

const C = {
  bg:"#050c1a", surface:"#0d1829", border:"rgba(255,255,255,0.07)",
  text:"#e2e8f0", muted:"#64748b", subtle:"#334155",
  teal:"#14b8a6", blue:"#3b82f6", indigo:"#6366f1",
  purple:"#a855f7", amber:"#f59e0b", red:"#ef4444",
  green:"#22c55e", coral:"#f97316", cyan:"#06b6d4",
};

const TABS = [
  { id:"full",     label:"Full Architecture"         },
  { id:"dt",       label:"Digital Twin Engine"       },
  { id:"ai",       label:"AI Layer"                  },
  { id:"frontend", label:"Frontend"                  },
  { id:"data",     label:"Data & DB Schema"          },
  { id:"deploy",   label:"Deployment"                },
];

// ─── Shared SVG primitives ────────────────────────────────────────────────────
function Rect({x,y,w,h,r=8,fill,stroke,opacity=1}){
  return <rect x={x} y={y} width={w} height={h} rx={r}
    fill={fill||"none"} stroke={stroke} strokeWidth="1.2" opacity={opacity}/>;
}
function Txt({x,y,s=10,c=C.text,fw=600,anchor="middle",children}){
  return <text x={x} y={y} textAnchor={anchor} dominantBaseline="central"
    fill={c} fontSize={s} fontWeight={fw} fontFamily="monospace">{children}</text>;
}
function Arrow({x1,y1,x2,y2,col=C.subtle,dash=false,label}){
  const id=`a${x1}${y1}${x2}${y2}`.replace(/\./g,"");
  const mx=(x1+x2)/2, my=(y1+y2)/2;
  return(<g>
    <defs><marker id={id} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto">
      <path d="M2 2L8 5L2 8" fill="none" stroke={col} strokeWidth="1.5" strokeLinecap="round"/>
    </marker></defs>
    <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={col} strokeWidth="1.3"
      strokeDasharray={dash?"5 3":"none"} markerEnd={`url(#${id})`}/>
    {label&&<text x={mx+4} y={my-4} fill={col} fontSize={8} fontFamily="monospace">{label}</text>}
  </g>);
}
function Box({x,y,w,h=40,stroke,title,sub,r=7}){
  return(<g>
    <Rect x={x} y={y} w={w} h={h} r={r} fill={stroke+"10"} stroke={stroke}/>
    <Txt x={x+w/2} y={y+(sub?h/2-7:h/2+1)} s={10} fw={700}>{title}</Txt>
    {sub&&<Txt x={x+w/2} y={y+h/2+9} s={8} c={C.muted}>{sub}</Txt>}
  </g>);
}
function Layer({x,y,w,h,stroke,label,children}){
  return(<g>
    <Rect x={x} y={y} w={w} h={h} r={10} fill={stroke+"08"} stroke={stroke}/>
    <rect x={x+10} y={y-9} width={label.length*6.8+14} height={18} rx={4} fill={C.bg}/>
    <Txt x={x+17} y={y+0.5} s={9} fw={700} c={stroke} anchor="start">{label}</Txt>
    {children}
  </g>);
}

// ─── Tab 1: Full Architecture ─────────────────────────────────────────────────
function FullArch(){
  return(
  <svg viewBox="0 0 800 900" width="100%" style={{display:"block"}}>

    {/* L1 Physical */}
    <Layer x={10} y={18} w={778} h={80} stroke={C.teal} label="L1 · PHYSICAL — WSN sensors & tags (full factory grid coverage)">
      <Box x={20}  y={32} w={180} h={48} stroke={C.teal} title="Worker tags" sub="UWB / BLE beacons"/>
      <Box x={210} y={32} w={180} h={48} stroke={C.teal} title="Mobile object tags" sub="Forklifts · pallets"/>
      <Box x={400} y={32} w={180} h={48} stroke={C.teal} title="Env sensors / cell" sub="Temp · humidity · smoke"/>
      <Box x={590} y={32} w={182} h={48} stroke={C.muted} title="Grid: N×M cells" sub="1 sensor per cell · full coverage"/>
    </Layer>

    <Arrow x1={400} y1={98} x2={400} y2={126} col={C.teal} label="  short-range wireless"/>

    {/* L2 Gateway */}
    <Layer x={10} y={128} w={778} h={60} stroke={C.cyan} label="L2 · MOTHER STATION — single network gateway">
      <Box x={20}  y={24} w={230} h={32} stroke={C.cyan} title="Zone detection (tag→sensor_id)" r={5}/>
      <Box x={266} y={24} w={230} h={32} stroke={C.cyan} title="Protocol aggregation → MQTT"     r={5}/>
      <Box x={512} y={24} w={258} h={32} stroke={C.red}  title="Single-point watchdog required"  r={5}/>
    </Layer>

    <Arrow x1={400} y1={188} x2={400} y2={216} col={C.blue} label="  MQTT / TCP-IP"/>

    {/* L3 Broker */}
    <Layer x={10} y={218} w={778} h={56} stroke={C.blue} label="L3 · MQTT BROKER (Mosquitto) — QoS 1">
      <Box x={20}  y={20} w={360} h={30} stroke={C.blue} title="wsn/env  →  [sensor_id, temperature|humidity|smoke, value, ts]" r={5}/>
      <Box x={396} y={20} w={376} h={30} stroke={C.blue} title="wsn/location  →  [worker_id|object_id, sensor_id, ts]"         r={5}/>
    </Layer>

    <Arrow x1={400} y1={274} x2={400} y2={302} col={C.indigo} label="  subscribe"/>

    {/* L4 Engine */}
    <Layer x={10} y={304} w={778} h={290} stroke={C.indigo} label="L4 · DIGITAL TWIN ENGINE">

      {/* Ingestion row */}
      <Box x={18}  y={22} w={170} h={38} stroke={C.indigo} title="MQTT consumer"      sub="paho-mqtt"/>
      <Box x={198} y={22} w={170} h={38} stroke={C.indigo} title="mqtt_parser"         sub="route_message()"/>
      <Box x={378} y={22} w={170} h={38} stroke={C.cyan}   title="ZoneRegistry"        sub="sensor→zone"/>
      <Box x={558} y={22} w={212} h={38} stroke={C.amber}  title="SensorWatchdog"      sub="heartbeat · async loop"/>
      <Arrow x1={188} y1={41} x2={196} y2={41} col={C.indigo}/>
      <Arrow x1={368} y1={41} x2={376} y2={41} col={C.indigo}/>

      {/* State store */}
      <Rect x={18} y={72} w={752} h={100} r={8} fill={C.purple+"08"} stroke={C.purple}/>
      <Txt x={28} y={84} s={8} fw={700} c={C.purple} anchor="start">STATE STORE (in-memory · O(1) · rehydrated from DB on startup)</Txt>
      <Box x={26}  y={90} w={180} h={72} stroke={C.purple} title="AssetState" sub="id · sensor_id · zone_id&#10;prev_sensor · prev_zone&#10;allowed_sensors · allowed_zones&#10;access_status · ts"/>
      <Box x={218} y={90} w={170} h={72} stroke={C.teal}   title="SensorState" sub="sensor_id · zone_id&#10;temperature · humidity&#10;smoke · env_status&#10;last_time_change"/>
      <Box x={400} y={90} w={180} h={72} stroke={C.amber}  title="SensorHealthState" sub="sensor_id · zone_id&#10;status: ONLINE|DEGRADED|OFFLINE&#10;last_heartbeat · last_reading&#10;consecutive_failures"/>
      <Box x={592} y={90} w={172} h={72} stroke={C.green}  title="SystemState" sub="overall_status&#10;sensor counts&#10;zone counts&#10;access counts"/>

      {/* Rule engine */}
      <Rect x={18} y={182} w={752} h={80} r={8} fill={C.amber+"08"} stroke={C.amber}/>
      <Txt x={28} y={194} s={8} fw={700} c={C.amber} anchor="start">RULE ENGINE + AI INFERENCE</Txt>
      <Box x={26}  y={200} w={178} h={52} stroke={C.red}    title="Access control" sub="sensor/zone auth check&#10;UNKNOWN if sensor offline"/>
      <Box x={216} y={200} w={178} h={52} stroke={C.amber}  title="If-else scenarios" sub="smoke→evacuate&#10;temp→inspect · hum→ventilate"/>
      <Box x={406} y={200} w={178} h={52} stroke={C.purple} title="Prediction" sub="temp trend · smoke freq&#10;rising humidity"/>
      <Box x={596} y={200} w={168} h={52} stroke={C.green}  title="AI inference" sub="movement score&#10;danger routes · anomaly"/>

      {/* compute_system_state */}
      <Box x={18} y={262} w={752} h={24} stroke={C.green} title="compute_system_state() → SystemState → push to all WebSocket clients" r={5}/>
    </Layer>

    {/* Arrows to DB and API */}
    <Arrow x1={200} y1={594} x2={200} y2={622} col={C.subtle}/>
    <Arrow x1={600} y1={594} x2={600} y2={622} col={C.coral}/>

    {/* L5 Persistence */}
    <Layer x={10} y={624} w={370} h={68} stroke={C.subtle} label="L5 · POSTGRESQL (persistence)">
      <Box x={18}  y={22} w={154} h={36} stroke={C.subtle} title="location_events" sub="env_readings · events" r={5}/>
      <Box x={184} y={22} w={182} h={36} stroke={C.subtle} title="zones · sensors · assets" sub="authorisations · snapshots" r={5}/>
    </Layer>

    {/* L6 API */}
    <Layer x={400} y={624} w={388} h={68} stroke={C.coral} label="L6 · API GATEWAY (FastAPI)">
      <Box x={408} y={22} w={174} h={36} stroke={C.coral} title="REST /api/*"   sub="assets · sensors · events" r={5}/>
      <Box x={594} y={22} w={184} h={36} stroke={C.coral} title="WebSocket /ws" sub="real-time push · 6 event types" r={5}/>
    </Layer>

    <Arrow x1={600} y1={692} x2={600} y2={720} col={C.green}/>

    {/* L7 Frontend */}
    <Layer x={10} y={722} w={778} h={90} stroke={C.green} label="L7 · REACT FRONTEND (configurable via env vars)">
      <Box x={18}  y={22} w={180} h={56} stroke={C.teal}   title="FactoryMap"     sub="Blueprint image&#10;N×M sensor grid overlay"/>
      <Box x={210} y={22} w={140} h={56} stroke={C.amber}  title="SensorCell"     sub="Status colour&#10;readings + asset counts"/>
      <Box x={362} y={22} w={150} h={56} stroke={C.purple} title="SensorDetail"   sub="Click panel&#10;assets grouped by type"/>
      <Box x={524} y={22} w={128} h={56} stroke={C.red}    title="AlertPanel"     sub="Rules + AI&#10;live alert feed"/>
      <Box x={664} y={22} w={116} h={56} stroke={C.coral}  title="StatusBar"      sub="NOMINAL/DEGRADED&#10;/CRITICAL banner"/>
    </Layer>

    {/* AI Training loop (right rail) */}
    <Rect x={750} y={304} w={38} h={290} r={6} fill={C.amber+"0a"} stroke={C.amber} opacity={0.5}/>
    <text x={769} y={449} textAnchor="middle" dominantBaseline="central"
      fill={C.amber} fontSize={8} fontWeight={700} fontFamily="monospace"
      transform="rotate(-90,769,449)">AI TRAINING LOOP (nightly · APScheduler)</text>

    {/* Data flow label */}
    <Rect x={10} y={820} w={778} h={22} r={5} fill={C.surface} stroke={C.border}/>
    <Txt x={399} y={831} s={9} c={C.muted}>
      WSN → Mother Station → MQTT → Engine → PostgreSQL + WebSocket → React Dashboard
    </Txt>
  </svg>);
}

// ─── Tab 2: Digital Twin Engine detail ───────────────────────────────────────
function DTEngine(){
  return(
  <svg viewBox="0 0 800 640" width="100%" style={{display:"block"}}>
    <Txt x={400} y={18} s={14} fw={700}>Digital Twin Engine — internal components & event flow</Txt>

    {/* Event flow */}
    {[
      {x:240,y:38, w:320, h:46, stroke:C.teal,   title:"Incoming WSN event",         sub:"[asset_id|sensor_id, type, value, ts]"},
      {x:240,y:108,w:320, h:40, stroke:C.subtle,  title:"Validate & deserialise",     sub:"mqtt_parser.route_message(topic, payload)"},
      {x:240,y:172,w:320, h:40, stroke:C.cyan,    title:"Watchdog heartbeat",         sub:"SensorWatchdog.on_message_received(sensor_id)"},
      {x:240,y:236,w:320, h:40, stroke:C.blue,    title:"Update StateStore",          sub:"update_sensor_reading() | update_asset_location()"},
      {x:240,y:300,w:320, h:40, stroke:C.amber,   title:"Evaluate rules",             sub:"check_access · evaluate_scenarios · predict"},
    ].map((b,i)=>(
      <g key={i}>
        <Box x={b.x} y={b.y} w={b.w} h={b.h} stroke={b.stroke} title={b.title} sub={b.sub}/>
        {i<4&&<Arrow x1={400} y1={b.y+b.h} x2={400} y2={b.y+b.h+28} col={b.stroke}/>}
      </g>
    ))}

    {/* Alert branch */}
    <polygon points="400,352 450,374 400,396 350,374" fill={C.bg} stroke={C.amber} strokeWidth="1.2"/>
    <Txt x={400} y={374} s={9} fw={600} c={C.amber}>alert?</Txt>
    <Arrow x1={400} y1={340} x2={400} y2={350} col={C.amber}/>
    <Arrow x1={450} y1={374} x2={560} y2={374} col={C.red} label="yes"/>
    <Box x={562} y={354} w={148} h={40} stroke={C.red} title="save_event()" sub="push_alert() → WS"/>
    <Arrow x1={400} y1={396} x2={400} y2={424} col={C.subtle} label=" always"/>
    <Box x={240} y={426} w={320} h={40} stroke={C.green} title="persist + push_system_state()" sub="PostgreSQL · WebSocket broadcast"/>

    {/* Alert also persisted */}
    <path d="M636 394 Q680 430 562 446" fill="none" stroke={C.red} strokeWidth="1" strokeDasharray="4 3"
      markerEnd="url(#ae)"/>
    <defs><marker id="ae" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto">
      <path d="M2 2L8 5L2 8" fill="none" stroke={C.red} strokeWidth="1.5"/>
    </marker></defs>

    {/* State classes detail */}
    <Rect x={10} y={490} w={778} h={136} r={8} fill={C.surface} stroke={C.border}/>
    <Txt x={399} y={504} s={10} fw={700} c={C.muted}>State class fields</Txt>
    {[
      {x:18,  stroke:C.purple, title:"AssetState",        lines:["id · asset_type","current_sensor_id · current_zone_id","previous_sensor_id · previous_zone_id","time_change_location","allowed_sensors (set) · allowed_zones (set)","access_status: AUTHORISED|VIOLATION|UNKNOWN"]},
      {x:206, stroke:C.teal,   title:"SensorState",       lines:["sensor_id · zone_id","temperature (°C)","humidity (%)","smoke (bool)","env_status: NORMAL|WARNING|CRITICAL","last_time_change"]},
      {x={394},stroke:C.amber, title:"SensorHealthState", lines:["sensor_id · zone_id","status: ONLINE|DEGRADED|OFFLINE","last_heartbeat · last_reading","consecutive_failures","(updated by SensorWatchdog"," independently of readings)"]},
      {x:582, stroke:C.green,  title:"SystemState",       lines:["overall_status","sensors_online/degraded/offline","offline_sensor_ids","zones_normal/warning/critical","critical_zone_ids","access_violations · violation_ids"]},
    ].map((col,i)=>(
      <g key={i}>
        <Txt x={col.x+90} y={516} s={9} fw={700} c={col.stroke}>{col.title}</Txt>
        {col.lines.map((l,j)=>(
          <Txt key={j} x={col.x+10} y={528+j*14} s={8} c={C.muted} anchor="start">{l}</Txt>
        ))}
      </g>
    ))}
  </svg>);
}

// ─── Tab 3: AI Layer ─────────────────────────────────────────────────────────
function AILayer(){
  const models=[
    {title:"Movement Optimiser", color:C.amber, x:10,
     algo:"LSTM sequence classifier + PPO RL",
     input:"Zone sequence (last 20 hops) + tabular features",
     output:"movement_score ∈[0,1] + suggestions",
     label:"score < 0.6 → inefficient",
     train:"Weekly · heuristic labels · 30 days min",
     cold:"Rule-based backtrack ratio"},
    {title:"Smart Evacuation", color:C.red, x:270,
     algo:"XGBoost (danger score) + Dijkstra (routing)",
     input:"env features per zone + asset locations",
     output:"danger_score per zone + route per asset",
     label:"cost = 15s × (1 + danger×10)",
     train:"On new incidents · synthetic augmentation",
     cold:"Threshold rules (smoke→0.9, temp>60→0.75)"},
    {title:"System Monitor", color:C.indigo, x:530,
     algo:"LSTM Autoencoder + LSTM Forecaster + XGBoost",
     input:"Rolling 30-reading window [temp,hum,smoke]",
     output:"anomaly_score · predicted_temp · failure_prob",
     label:"AE: recon error > 95th pct → anomaly",
     train:"Nightly · normal data only for AE · 7 days min",
     cold:"Linear trend + threshold rules"},
  ];
  return(
  <svg viewBox="0 0 800 580" width="100%" style={{display:"block"}}>
    <Txt x={400} y={18} s={14} fw={700}>AI layer — three models, shared data streams</Txt>

    {/* Data inputs */}
    <Layer x={10} y={34} w={778} h={52} stroke={C.teal} label="Data streams (from Digital Twin Engine)">
      <Box x={18}  y={16} w={360} h={26} stroke={C.teal}   title="wsn/location → location_events → zone sequences + movement features" r={4}/>
      <Box x={392} y={16} w={386} h={26} stroke={C.cyan}   title="wsn/env → env_readings → rolling windows + trend features" r={4}/>
    </Layer>
    <Arrow x1={200} y1={86} x2={80}  y2={126} col={C.amber}/>
    <Arrow x1={400} y1={86} x2={400} y2={126} col={C.red}/>
    <Arrow x1={600} y1={86} x2={660} y2={126} col={C.indigo}/>

    {/* Three model cards */}
    {models.map(m=>(
      <g key={m.title}>
        <Rect x={m.x} y={128} w={250} h={260} r={10} fill={m.color+"08"} stroke={m.color}/>
        <Txt x={m.x+125} y={146} s={10} fw={700} c={m.color}>{m.title}</Txt>
        {[
          {lbl:"Algorithm", val:m.algo},
          {lbl:"Input",     val:m.input},
          {lbl:"Output",    val:m.output},
          {lbl:"Decision",  val:m.label},
          {lbl:"Retrains",  val:m.train},
          {lbl:"Cold start",val:m.cold},
        ].map((r,i)=>(
          <g key={i}>
            <Txt x={m.x+12} y={164+i*36}   s={8} fw={700} c={C.muted}  anchor="start">{r.lbl}</Txt>
            <Txt x={m.x+12} y={178+i*36}   s={8} fw={400} c={C.text}   anchor="start">{r.val}</Txt>
          </g>
        ))}
      </g>
    ))}

    {/* Outputs */}
    <Arrow x1={80}  y1={388} x2={200} y2={428} col={C.amber}/>
    <Arrow x1={400} y1={388} x2={400} y2={428} col={C.red}/>
    <Arrow x1={660} y1={388} x2={600} y2={428} col={C.indigo}/>

    <Layer x={10} y={430} w={778} h={56} stroke={C.green} label="AI outputs → Digital Twin Engine → WebSocket → Dashboard">
      <Box x={18}  y={16} w={180} h={28} stroke={C.amber}  title="movement_score + suggestions"      r={4}/>
      <Box x={210} y={16} w={180} h={28} stroke={C.red}    title="evacuation_route per asset"        r={4}/>
      <Box x={402} y={16} w={180} h={28} stroke={C.indigo} title="anomaly_score + predicted_temp"    r={4}/>
      <Box x={594} y={16} w={184} h={28} stroke={C.green}  title="ai_insight WebSocket event"        r={4}/>
    </Layer>

    {/* Training pipeline */}
    <Layer x={10} y={498} w={778} h={56} stroke={C.subtle} label="Training pipeline (offline · APScheduler · nightly 02:00 + drift PSI>0.20)">
      {["Extract (PostgreSQL)","Feature engineering","Label generation","Train + evaluate","MLflow register","Reload engine"].map((s,i)=>(
        <g key={i}>
          <Box x={18+i*127} y={16} w={118} h={28} stroke={C.subtle} title={s} r={4}/>
          {i<5&&<Arrow x1={138+i*127} y1={30} x2={144+i*127} y2={30} col={C.subtle}/>}
        </g>
      ))}
    </Layer>
  </svg>);
}

// ─── Tab 4: Frontend ─────────────────────────────────────────────────────────
function Frontend(){
  return(
  <svg viewBox="0 0 800 560" width="100%" style={{display:"block"}}>
    <Txt x={400} y={18} s={14} fw={700}>Frontend — configurable React dashboard</Txt>

    {/* Env vars */}
    <Layer x={10} y={34} w={778} h={62} stroke={C.cyan} label="Environment variables (docker-compose args or frontend/.env)">
      {[
        "REACT_APP_FACTORY_IMAGE","REACT_APP_GRID_COLS","REACT_APP_GRID_ROWS",
        "REACT_APP_SENSOR_COUNT","REACT_APP_FACTORY_NAME",
      ].map((v,i)=>(
        <g key={v}>
          <Rect x={18+i*152} y={18} w={144} h={34} r={5} fill={C.cyan+"10"} stroke={C.cyan}/>
          <Txt x={90+i*152} y={28} s={7.5} fw={700} c={C.cyan}>{v.replace("REACT_APP_","")}</Txt>
          <Txt x={90+i*152} y={42} s={8} fw={400} c={C.muted}>
            {["blueprint.png","6","5","30","Factory A"][i]}
          </Txt>
        </g>
      ))}
    </Layer>

    {/* Component tree */}
    <Layer x={10} y={110} w={778} h={310} stroke={C.green} label="Component tree">
      {/* App */}
      <Box x={300} y={20} w={200} h={40} stroke={C.green} title="App.jsx" sub="useReducer state · useWebSocket · layout"/>
      <Arrow x1={400} y1={60} x2={120} y2={100} col={C.green}/>
      <Arrow x1={400} y1={60} x2={400} y2={100} col={C.green}/>
      <Arrow x1={400} y1={60} x2={680} y2={100} col={C.green}/>

      {/* Level 2 */}
      <Box x={18}  y={100} w={200} h={40} stroke={C.teal}   title="FactoryMap.jsx"  sub="blueprint bg + grid overlay"/>
      <Box x={300} y={100} w={200} h={40} stroke={C.amber}  title="StatusBar.jsx"   sub="system status banner"/>
      <Box x={580} y={100} w={190} h={40} stroke={C.red}    title="AlertPanel.jsx"  sub="live alert feed + AI tab"/>
      <Arrow x1={118} y1={140} x2={80}  y2={180} col={C.teal}/>
      <Arrow x1={118} y1={140} x2={200} y2={180} col={C.teal}/>

      {/* Level 3 */}
      <Box x={18}  y={180} w={148} h={40} stroke={C.amber}  title="SensorCell.jsx"  sub="status colour + readings"/>
      <Box x={178} y={180} w={148} h={40} stroke={C.purple} title="SensorDetail.jsx" sub="click panel · assets by type"/>
      <Box x={340} y={180} w={148} h={40} stroke={C.teal}   title="AssetList.jsx"   sub="sidebar asset list"/>

      {/* SensorCell detail */}
      <Rect x={18} y={236} w={308} h={60} r={6} fill={C.amber+"08"} stroke={C.amber} opacity={0.7}/>
      <Txt x={26} y={250} s={8} fw={700} c={C.amber} anchor="start">SensorCell shows (before click):</Txt>
      <Txt x={26} y={264} s={8} c={C.text} anchor="start">• Background = statusBg(health.status, env_status)</Txt>
      <Txt x={26} y={278} s={8} c={C.text} anchor="start">• Temp · humidity · smoke reading   • 👷×2 🚜×1 (asset counts by type)</Txt>

      {/* SensorDetail */}
      <Rect x={340} y={236} w={430} h={60} r={6} fill={C.purple+"08"} stroke={C.purple} opacity={0.7}/>
      <Txt x={348} y={250} s={8} fw={700} c={C.purple} anchor="start">SensorDetail shows (on click):</Txt>
      <Txt x={348} y={264} s={8} c={C.text} anchor="start">• Sensor ID, zone, health status, last heartbeat, consecutive failures</Txt>
      <Txt x={348} y={278} s={8} c={C.text} anchor="start">• Temp / humidity / smoke   • All assets grouped by type with access badge</Txt>
    </Layer>

    {/* WebSocket events */}
    <Layer x={10} y={432} w={778} h={56} stroke={C.coral} label="WebSocket event types (6) → useWebSocket hook → useReducer dispatch">
      {["snapshot","system_state","sensor_update","health_update","asset_update","alert / ai_insight"].map((ev,i)=>(
        <Box key={ev} x={18+i*128} y={16} w={120} h={28} stroke={C.coral} title={ev} r={4}/>
      ))}
    </Layer>

    <Rect x={10} y={500} w={778} h={42} r={6} fill={C.surface} stroke={C.border}/>
    <Txt x={399} y={512} s={9} fw={700} c={C.muted}>Hooks</Txt>
    <Txt x={399} y={526} s={8} c={C.muted}>useWebSocket.js — auto-reconnect · keep-alive ping · 3s reconnect delay     |     useApi.js — REST fetcher with loading/error state</Txt>
  </svg>);
}

// ─── Tab 5: Data & DB Schema ─────────────────────────────────────────────────
function DataSchema(){
  const tables=[
    {name:"zones",              cols:["zone_id PK","name","description"],                                                         color:C.teal},
    {name:"sensors",            cols:["sensor_id PK","zone_id FK","grid_row","grid_col","installed_at"],                          color:C.teal},
    {name:"assets",             cols:["asset_id PK","asset_type","name","created_at"],                                            color:C.blue},
    {name:"authorisations",     cols:["asset_id FK","allowed_type (sensor|zone)","allowed_id"],                                   color:C.blue},
    {name:"location_events",    cols:["id BIGSERIAL","asset_id FK","sensor_id FK","zone_id FK","previous_sensor_id","previous_zone_id","access_status","timestamp↓"],color:C.purple},
    {name:"env_readings",       cols:["id BIGSERIAL","sensor_id FK","zone_id","reading_type","value","env_status","timestamp↓"],   color:C.amber},
    {name:"sensor_health_events",cols:["id BIGSERIAL","sensor_id FK","zone_id","status","consecutive_failures","timestamp↓"],     color:C.amber},
    {name:"events",             cols:["id BIGSERIAL","event_type","level","sensor_id","zone_id","asset_id","message","payload JSONB","timestamp↓"],color:C.red},
    {name:"system_snapshots",   cols:["id BIGSERIAL","overall_status","sensor counts","zone counts","access counts","payload JSONB","timestamp↓"],color:C.green},
  ];
  const cols=3, rows=Math.ceil(tables.length/cols);
  const TW=246, TH=116, GAP=8, PX=10;
  return(
  <svg viewBox={`0 0 800 ${PX*2+rows*(TH+GAP)+60}`} width="100%" style={{display:"block"}}>
    <Txt x={400} y={18} s={14} fw={700}>PostgreSQL schema — 9 tables</Txt>
    <Txt x={400} y={34} s={9} c={C.muted}>↓ = time-series column indexed (sensor_id, timestamp DESC) for fast history queries</Txt>
    {tables.map((t,i)=>{
      const col=i%cols, row=Math.floor(i/cols);
      const x=PX+col*(TW+GAP), y=PX+50+row*(TH+GAP);
      return(<g key={t.name}>
        <Rect x={x} y={y} w={TW} h={TH} r={7} fill={t.color+"08"} stroke={t.color}/>
        <Rect x={x} y={y} w={TW} h={22} r={7} fill={t.color+"30"} stroke="none"/>
        <Rect x={x} y={y+16} w={TW} h={6}  r={0} fill={t.color+"30"} stroke="none"/>
        <Txt  x={x+TW/2} y={y+11} s={10} fw={700} c={t.color}>{t.name}</Txt>
        {t.cols.map((c,j)=>(
          <Txt key={j} x={x+10} y={y+32+j*13} s={8} c={j===0?C.text:C.muted} fw={j===0?600:400} anchor="start">{c}</Txt>
        ))}
      </g>);
    })}
  </svg>);
}

// ─── Tab 6: Deployment ───────────────────────────────────────────────────────
function Deploy(){
  return(
  <svg viewBox="0 0 800 540" width="100%" style={{display:"block"}}>
    <Txt x={400} y={18} s={14} fw={700}>Deployment — Docker Compose (4 services + optional simulator)</Txt>
    <Rect x={10} y={32} w={778} h={474} r={12} fill="none" stroke={C.subtle} strokeDasharray="6 4"/>
    <Txt x={50} y={44} s={9} c={C.subtle} fw={700} anchor="start">docker-compose.yml</Txt>

    {[
      {name:"postgres :5432",     color:C.subtle,  x:20,  y:60,  w:180, h:280,
       lines:["postgres:16-alpine","Volumes: postgres_data","Healthcheck: pg_isready","─────────","Tables:","• zones + sensors","• assets + authorisations","• location_events","• env_readings","• sensor_health_events","• events","• system_snapshots"]},
      {name:"mosquitto :1883",    color:C.blue,    x:210, y:60,  w:160, h:180,
       lines:["eclipse-mosquitto:2","Topics:","wsn/env (QoS 1)","wsn/location (QoS 1)","wsn/alerts","Port 9001: WS-MQTT","Volume: mosquitto_data"]},
      {name:"backend :8000",      color:C.indigo,  x:380, y:60,  w:200, h:280,
       lines:["python:3.12-slim","FastAPI + Uvicorn","─────────","Startup:","• load ZoneRegistry","• rehydrate StateStore","• connect MQTT","• start Watchdog async","• load AI models","─────────","APScheduler:","• nightly retrain 02:00","• hourly drift check"]},
      {name:"frontend :3000",     color:C.green,   x:590, y:60,  w:185, h:280,
       lines:["node:20-alpine → build","nginx:alpine → serve","─────────","Build args:","FACTORY_IMAGE","GRID_COLS / GRID_ROWS","SENSOR_COUNT","FACTORY_NAME","API_URL / WS_URL","─────────","Nginx proxies:","• /api/ → backend","• /ws   → backend WS"]},
      {name:"simulator (profile:sim)", color:C.amber, x:210, y:250, w:160, h:90,
       lines:["python:3.12-slim","simulate_wsn.py","--cols 6 --rows 5","--interval 2","Moves assets to","adjacent sensors only"]},
    ].map(s=>(
      <g key={s.name}>
        <Rect x={s.x} y={s.y} w={s.w} h={s.h} r={8} fill={s.color+"08"} stroke={s.color}/>
        <Txt  x={s.x+s.w/2} y={s.y+13} s={10} fw={700} c={s.color}>{s.name}</Txt>
        {s.lines.map((l,i)=>(
          <Txt key={i} x={s.x+10} y={s.y+28+i*15} s={8} c={l.startsWith("•")?C.text:l.startsWith("─")?C.subtle:C.muted} anchor="start" fw={l.startsWith("•")?500:400}>{l}</Txt>
        ))}
      </g>
    ))}

    {/* Arrows */}
    <Arrow x1={200} y1={200} x2={210} y2={200} col={C.subtle} label="SQL"/>
    <Arrow x1={370} y1={200} x2={380} y2={200} col={C.blue}   label="MQTT"/>
    <Arrow x1={580} y1={200} x2={590} y2={200} col={C.coral}  label="HTTP/WS"/>
    <Arrow x1={290} y1={250} x2={290} y2={248} col={C.amber}/>

    {/* Deploy commands */}
    <Rect x={20} y={358} w={350} h={120} r={6} fill={C.surface} stroke={C.border}/>
    <Txt  x={30} y={372} s={9} fw={700} c={C.muted} anchor="start">Quick start</Txt>
    {[
      "docker compose up --build",
      "",
      "# Seed database",
      "docker exec -i dt_postgres psql \\",
      "  -U dt_user -d digital_twin \\",
      "  < scripts/seed_db.sql",
      "",
      "# With simulator",
      "docker compose --profile sim up",
    ].map((l,i)=>(
      <Txt key={i} x={30} y={384+i*12} s={8} c={l.startsWith("#")?C.teal:C.text} anchor="start" fw={l.startsWith("#")?400:500}>{l}</Txt>
    ))}

    {/* Test command */}
    <Rect x={390} y={358} w={385} h={120} r={6} fill={C.surface} stroke={C.border}/>
    <Txt  x={400} y={372} s={9} fw={700} c={C.muted} anchor="start">Tests & training</Txt>
    {[
      "# Run unit tests",
      "pytest tests/ -v",
      "",
      "# Train all AI models manually",
      "python -m ai.training.train_all",
      "",
      "# Single model",
      "python -m ai.training.train_all \\",
      "  --model monitor --days 30",
    ].map((l,i)=>(
      <Txt key={i} x={400} y={384+i*12} s={8} c={l.startsWith("#")?C.teal:C.text} anchor="start" fw={l.startsWith("#")?400:500}>{l}</Txt>
    ))}
  </svg>);
}

const DIAGRAMS={full:FullArch, dt:DTEngine, ai:AILayer, frontend:Frontend, data:DataSchema, deploy:Deploy};

export default function App(){
  const [tab,setTab]=useState("full");
  const D=DIAGRAMS[tab];
  return(
  <div style={{background:C.bg,minHeight:"100vh",fontFamily:"'IBM Plex Mono','Fira Code',monospace"}}>
    <div style={{padding:"14px 24px 0",borderBottom:`1px solid ${C.border}`,background:C.surface}}>
      <div style={{fontSize:8,color:C.indigo,letterSpacing:3,textTransform:"uppercase",marginBottom:3}}>
        Scientific Paper — Digital Twin for Factory Monitoring
      </div>
      <div style={{fontSize:17,fontWeight:700,color:C.text,marginBottom:12}}>
        Final System Architecture
      </div>
      <div style={{display:"flex",gap:3,flexWrap:"wrap"}}>
        {TABS.map(t=>(
          <button key={t.id} onClick={()=>setTab(t.id)} style={{
            padding:"6px 14px",fontSize:10,fontWeight:600,border:"none",
            borderRadius:"6px 6px 0 0",cursor:"pointer",fontFamily:"inherit",
            background:tab===t.id?C.surface:"transparent",
            color:tab===t.id?C.purple:C.muted,
            borderBottom:tab===t.id?`2px solid ${C.purple}`:"2px solid transparent",
          }}>{t.label}</button>
        ))}
      </div>
    </div>
    <div style={{padding:"20px 16px"}}>
      <div style={{background:C.surface,borderRadius:10,border:`1px solid ${C.border}`,
        padding:16,maxWidth:840,margin:"0 auto"}}>
        <D/>
      </div>
    </div>
  </div>);
}
