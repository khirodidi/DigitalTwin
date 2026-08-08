import { useState } from "react";
const LEVEL = {
  critical:{ border:"#ef4444", bg:"#7f1d1d22", text:"#fca5a5", icon:"🔴" },
  warning: { border:"#f59e0b", bg:"#78350f22", text:"#fcd34d", icon:"🟡" },
  info:    { border:"#3b82f6", bg:"#1e3a5f22", text:"#93c5fd", icon:"🔵" },
};
export default function AlertPanel({ alerts, aiInsights }) {
  const [filter, setFilter] = useState("all");
  const all = [
    ...(aiInsights||[]).map(a=>({...a,_src:"ai"})),
    ...(alerts    ||[]).map(a=>({...a,_src:"rule"})),
  ].sort((a,b)=>b._ts-a._ts).slice(0,80);
  const shown = filter==="all"?all : filter==="ai"?all.filter(a=>a._src==="ai") : all.filter(a=>a.level===filter);
  return (
    <div style={{ display:"flex", flexDirection:"column", height:"100%", background:"#0d1829", borderLeft:"1px solid #1e293b" }}>
      <div style={{ padding:"10px 14px", borderBottom:"1px solid #1e293b",
        display:"flex", alignItems:"center", justifyContent:"space-between" }}>
        <span style={{ fontSize:10, fontWeight:700, color:"#94a3b8", letterSpacing:1 }}>ALERTS</span>
        <span style={{ fontSize:9, padding:"1px 7px", borderRadius:10,
          background:"#7f1d1d", color:"#fca5a5", fontWeight:700 }}>
          {all.filter(a=>a.level==="critical").length} critical
        </span>
      </div>
      <div style={{ display:"flex", gap:2, padding:"6px 8px", borderBottom:"1px solid #1e293b" }}>
        {["all","critical","warning","ai"].map(f=>(
          <button key={f} onClick={()=>setFilter(f)} style={{
            padding:"2px 8px", fontSize:8, fontWeight:600, borderRadius:3,
            border:"none", cursor:"pointer", fontFamily:"monospace",
            background:filter===f?"#1e40af":"#1e293b",
            color:filter===f?"#93c5fd":"#64748b",
          }}>{f.toUpperCase()}</button>
        ))}
      </div>
      <div style={{ flex:1, overflowY:"auto", padding:6 }}>
        {shown.length===0&&<div style={{ padding:20, textAlign:"center", color:"#334155", fontSize:11 }}>No alerts</div>}
        {shown.map((a,i)=>{
          const st=LEVEL[a.level]||LEVEL.info;
          return (
            <div key={i} style={{ marginBottom:5, padding:"6px 9px", borderRadius:5,
              border:`1px solid ${st.border}33`, background:st.bg, fontFamily:"monospace" }}>
              <div style={{ display:"flex", alignItems:"center", gap:5, marginBottom:2 }}>
                <span style={{ fontSize:9 }}>{st.icon}</span>
                <span style={{ fontSize:8, fontWeight:700, color:st.text }}>
                  {(a.type||"").replace(/_/g," ").toUpperCase()}
                </span>
                {a._src==="ai"&&<span style={{ fontSize:7, padding:"1px 4px", borderRadius:2,
                  background:"#7c3aed", color:"#c4b5fd", fontWeight:700, marginLeft:"auto" }}>AI</span>}
                <span style={{ fontSize:7, color:"#475569", marginLeft:"auto" }}>
                  {a._ts ? new Date(a._ts).toLocaleTimeString() : ""}
                </span>
              </div>
              <div style={{ fontSize:8.5, color:"#94a3b8", lineHeight:1.4 }}>{a.message}</div>
              {a.action&&<div style={{ fontSize:7.5, color:"#475569", marginTop:2 }}>→ {a.action}</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
