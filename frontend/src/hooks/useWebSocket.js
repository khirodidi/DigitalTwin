// hooks/useWebSocket.js — auto-reconnecting WS hook
import { useEffect, useRef, useCallback } from "react";
const WS_URL = process.env.REACT_APP_WS_URL || "ws://localhost:8000/ws";
const RECONNECT_DELAY = 3000;

export function useWebSocket(onEvent) {
  const ws = useRef(null);
  const timer = useRef(null);
  const mounted = useRef(true);

  const connect = useCallback(() => {
    if (!mounted.current) return;
    const socket = new WebSocket(WS_URL);
    ws.current = socket;
    socket.onopen = () => {
      clearTimeout(timer.current);
      const ping = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN)
          socket.send(JSON.stringify({ type: "ping" }));
      }, 20000);
      socket._ping = ping;
    };
    socket.onmessage = (e) => {
      try { const m = JSON.parse(e.data); if (m.type !== "pong") onEvent(m); } catch {}
    };
    socket.onclose = () => {
      clearInterval(socket._ping);
      if (mounted.current) timer.current = setTimeout(connect, RECONNECT_DELAY);
    };
    socket.onerror = () => socket.close();
  }, [onEvent]);

  useEffect(() => {
    mounted.current = true;
    connect();
    return () => { mounted.current = false; clearTimeout(timer.current); ws.current?.close(); };
  }, [connect]);
}
