// =============================================================================
// frontend/src/hooks/useConfig.js
//
// Loads the factory configuration from the API AT RUNTIME (not build time),
// so changing grid size or uploading a blueprint takes effect immediately
// without rebuilding the frontend container.
//
// Exposes a refresh() that the WebSocket `config_updated` handler calls, so
// the monitoring view updates the instant a change is saved in the Config page.
// =============================================================================

import { useState, useEffect, useCallback, useRef } from "react";

export const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

// No layout defaults from env vars — the factory MUST be configured at runtime.
// grid_cols / grid_rows of 0 mean "not configured yet".
const UNCONFIGURED = {
  factory_name:  "",
  blueprint_url: "",
  grid_cols:     0,
  grid_rows:     0,
};

export function useConfig() {
  const [config,  setConfig]  = useState(UNCONFIGURED);
  const [sensors, setSensors] = useState([]);
  const [zones,   setZones]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);   // bumps on every refresh
  const mounted = useRef(true);

  const refresh = useCallback(async (section = "all") => {
    try {
      const jobs = [];

      if (section === "all" || section === "factory" ||
          section === "grid" || section === "blueprint") {
        jobs.push(
          fetch(`${API}/api/config/factory`)
            .then(r => r.json())
            .then(d => { if (mounted.current) setConfig({ ...UNCONFIGURED, ...d }); })
        );
      }
      if (section === "all" || section === "sensors" || section === "grid") {
        jobs.push(
          fetch(`${API}/api/config/sensors`)
            .then(r => r.json())
            .then(d => { if (mounted.current) setSensors(Array.isArray(d) ? d : []); })
        );
      }
      if (section === "all" || section === "zones" || section === "grid") {
        jobs.push(
          fetch(`${API}/api/config/zones`)
            .then(r => r.json())
            .then(d => { if (mounted.current) setZones(Array.isArray(d) ? d : []); })
        );
      }

      await Promise.all(jobs);
      if (mounted.current) setVersion(v => v + 1);
    } catch (e) {
      console.warn("[useConfig] refresh failed:", e);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    refresh("all");
    return () => { mounted.current = false; };
  }, [refresh]);

  // Absolute URL for the uploaded blueprint (served by the backend)
  const blueprintSrc = config.blueprint_url
    ? (config.blueprint_url.startsWith("http")
        ? config.blueprint_url
        : `${API}${config.blueprint_url}`)
    : null;

  // The factory is usable only once grid size AND a blueprint exist
  const configured = Boolean(
    config.grid_cols > 0 && config.grid_rows > 0 && config.blueprint_url
  );

  return {
    config, sensors, zones, loading, version, refresh,
    blueprintSrc, configured,
    cols: config.grid_cols,
    rows: config.grid_rows,
  };
}
