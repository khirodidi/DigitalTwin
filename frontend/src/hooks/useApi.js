// hooks/useApi.js — REST fetcher with loading/error state
import { useState, useEffect } from "react";
const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

export function useApi(path) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${API}${path}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e); setLoading(false); });
  }, [path]);

  return { data, loading, error };
}
