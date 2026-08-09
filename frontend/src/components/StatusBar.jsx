const S_CFG = {
  nominal:  { bg:"#052e16", border:"#16a34a", text:"#4ade80", icon:"✓", label:"NOMINAL"  },
  degraded: { bg:"#431407", border:"#ea580c", text:"#fb923c", icon:"⚠", label:"DEGRADED" },
  critical: { bg:"#450a0a", border:"#dc2626", text:"#f87171", icon:"✕", label:"CRITICAL" },
};
export default function StatusBar({ systemState, wsConnected }) {
  const status = systemState?.overall_status || "unknown";
  const cfg    = S_CFG[status] || { bg:"#0f172a", border:"#334155", text:"#64748b", icon:"?", label:"UNKNOWN" };
  return (
    <div style={{ display:"flex", alignItems:"center", gap:14, padding:"8px 18px",
      background:cfg.bg, borderBottom:`1px solid ${cfg.border}`, flexShrink:0, flexWrap:"wrap" }}>
      <div style={{ display:"flex", alignItems:"center", gap:7, padding:"3px 12px",
        borderRadius:5, border:`1px solid ${cfg.border}`, background:cfg.border+"22" }}>
        <span style={{ fontSize:13, color:cfg.text }}>{cfg.icon}</span>
        <span style={{ fontSize:10, fontWeight:700, color:cfg.text, letterSpacing:1.5 }}>{cfg.label}</span>
      </div>
      <div style={{ display:"flex", gap:10, fontSize:10, color:"#94a3b8", flexWrap:"wrap" }}>
        <span>Sensors:
          <span style={{ color:"#4ade80", marginLeft:4 }}>{systemState?.sensors?.online??0} online</span>
          {" · "}<span style={{ color:"#fb923c" }}>{systemState?.sensors?.degraded??0} degraded</span>
          {" · "}<span style={{ color:"#f87171" }}>{systemState?.sensors?.offline??0} offline</span>
        </span>
        <span>|</span>
        <span>Env:
          <span style={{ color:"#4ade80", marginLeft:4 }}>{systemState?.environment?.zones_normal??0} normal</span>
          {" · "}<span style={{ color:"#f87171" }}>{systemState?.environment?.zones_critical??0} critical</span>
        </span>
        <span>|</span>
        <span>Violations: <span style={{ color:systemState?.access?.violations>0?"#f87171":"#4ade80", marginLeft:4 }}>{systemState?.access?.violations??0}</span></span>
      </div>
      <div style={{ marginLeft:"auto", display:"flex", gap:8, alignItems:"center" }}>
        <span style={{ fontSize:9, fontWeight:700, padding:"2px 8px", borderRadius:4,
          border:`1px solid ${wsConnected?"#16a34a":"#6b7280"}`,
          color:wsConnected?"#4ade80":"#9ca3af",
          background:wsConnected?"#16a34a22":"#33415522" }}>
          {wsConnected ? "⬤ LIVE" : "○ DISCONNECTED"}
        </span>
      </div>
    </div>
  );
}
