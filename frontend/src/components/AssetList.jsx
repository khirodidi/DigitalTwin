// components/AssetList.jsx — sidebar list of all assets with live status
export default function AssetList({ assets }) {
  const assetIcon = (type) => type === "worker" ? "👷" : "🚜";
  const accessColor = { authorised: "#4ade80", violation: "#f87171", unknown: "#f59e0b" };

  return (
    <div style={{ background: "#0d1829", fontFamily: "monospace" }}>
      <div style={{ padding: "10px 14px", borderBottom: "1px solid #1e293b",
        fontSize: 10, fontWeight: 700, color: "#64748b", letterSpacing: 1 }}>
        ASSETS ({(assets || []).length})
      </div>
      <div style={{ maxHeight: 280, overflowY: "auto" }}>
        {(assets || []).map(a => (
          <div key={a.id} style={{
            padding: "7px 14px", borderBottom: "1px solid #0f172a",
            display: "flex", alignItems: "center", gap: 10,
          }}>
            <span style={{ fontSize: 16 }}>{assetIcon(a.asset_type)}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#e2e8f0" }}>{a.id}</div>
              <div style={{ fontSize: 8, color: "#475569" }}>
                {a.current_zone_id || "—"} / {a.current_sensor_id || "—"}
              </div>
            </div>
            <div style={{
              fontSize: 8, padding: "2px 6px", borderRadius: 3,
              color: accessColor[a.access_status] || "#94a3b8",
              border: `1px solid ${accessColor[a.access_status] || "#334155"}44`,
            }}>
              {a.access_status || "unknown"}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
