# api/ws_manager.py — WebSocket manager: broadcasts events to all React clients
import json, logging
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
        if not self._clients: return
        msg  = json.dumps({"event":event,"payload":payload,"ts":datetime.utcnow().isoformat()})
        dead = set()
        for ws in self._clients:
            try:    await ws.send_text(msg)
            except: dead.add(ws)
        for ws in dead: self._clients.discard(ws)

    async def push_system_state(self, s): await self.broadcast("system_state", s)
    async def push_asset_update(self, s): await self.broadcast("asset_update",  s)
    async def push_sensor_update(self,s): await self.broadcast("sensor_update", s)
    async def push_health_update(self,s): await self.broadcast("health_update", s)
    async def push_alert(self, s):        await self.broadcast("alert",         s)
    async def push_ai_insight(self, s):   await self.broadcast("ai_insight",    s)

    @property
    def count(self) -> int: return len(self._clients)
