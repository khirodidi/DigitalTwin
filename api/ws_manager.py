# =============================================================================
# api/ws_manager.py
# Manages all active WebSocket connections and broadcasts events.
# =============================================================================

import json
import logging
from datetime import datetime
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.add(ws)
        logger.info(f"WS client connected. Total: {len(self._clients)}")

    def disconnect(self, ws: WebSocket):
        self._clients.discard(ws)
        logger.info(f"WS client disconnected. Total: {len(self._clients)}")

    async def broadcast(self, event: str, payload: dict):
        """Send event to every connected React client."""
        if not self._clients:
            return
        message = json.dumps({
            "event":   event,
            "payload": payload,
            "ts":      datetime.utcnow().isoformat(),
        })
        dead = set()
        for ws in self._clients:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._clients.discard(ws)

    # ── Typed broadcast helpers ────────────────────────────────────────────────

    async def push_system_state(self, state: dict):
        await self.broadcast("system_state", state)

    async def push_asset_update(self, asset: dict):
        await self.broadcast("asset_update", asset)

    async def push_sensor_update(self, sensor: dict):
        await self.broadcast("sensor_update", sensor)

    async def push_health_update(self, health: dict):
        await self.broadcast("health_update", health)

    async def push_alert(self, alert: dict):
        await self.broadcast("alert", alert)

    async def push_ai_insight(self, insight: dict):
        await self.broadcast("ai_insight", insight)

    @property
    def count(self) -> int:
        return len(self._clients)
