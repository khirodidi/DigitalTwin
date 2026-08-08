const ICON = { worker:"👷", forklift:"🚜", pallet:"📦", object:"📍" };
const ACC  = { authorised:"#4ade80", violation:"#f87171", unknown:"#fbbf24" };
export default function AssetList({ assets }) {
  return (
    <div style={{ background:"#0d1829", fontFamily:"monospace" }}>
      <div style={{ padding:"9px 12px", borderBottom:"1px solid #1e293b",
        fontSize:9, fontWeight:700, color:"#64748b", letterSpacing:1 }}>
        ASSETS ({(assets||[]).length})
      </div>
      <div style={{ maxHeight:"calc(100vh - 120px)", overflowY:"auto" }}>
        {(assets||[]).map(a=>(
          <div key={a.id} style={{ padding:"6px 12px", borderBottom:"1px solid #0f172a",
            display:"flex", alignItems:"center", gap:8 }}>
            <span style={{ fontSize:14 }}>{ICON[a.asset_type]||"📍"}</span>
            <div style={{ flex:1, minWidth:0 }}>
              <div style={{ fontSize:10, fontWeight:700, color:"#e2e8f0" }}>{a.id}</div>
              <div style={{ fontSize:8, color:"#475569", overflow:"hidden", textOverflow:"ellipsis" }}>
                {a.current_zone_id||"—"} / {a.current_sensor_id||"—"}
              </div>
            </div>
            <div style={{ fontSize:8, padding:"1px 5px", borderRadius:3,
              color:ACC[a.access_status]||"#94a3b8",
              border:`0.5px solid ${(ACC[a.access_status]||"#334155")}44` }}>
              {a.access_status||"?"}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
