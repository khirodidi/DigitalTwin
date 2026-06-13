# =============================================================================
# publisher.py
# Digital Twin — Factory Monitoring System
# Publishes state updates and alerts to connected WebSocket clients.
# Decoupled from the engine — swap for any async transport (Redis pub/sub, etc.)
# =============================================================================

import json
import asyncio
import logging
from datetime import datetime
from dataclasses import asdict

from models.state import AssetState, SensorState, SensorHealthState, SystemState

logger = logging.getLogger(__name__)


class Publisher:
    """
    Maintains a set of active WebSocket connections and broadcasts
    events to all of them.

    Event types pushed to the frontend:
        'system_state'   → full SystemState after every update
        'asset_update'   → single AssetState change
        'sensor_update'  → single SensorState change
        'health_update'  → single SensorHealthState change
        'alert'          → any triggered rule, scenario, or prediction event
    """

    def __init__(self):
        self._clients: set = set()   # set of WebSocket connection objects

    # ── Connection management ─────────────────────────────────────────────────

    def register(self, ws):
        self._clients.add(ws)
        logger.info(f"Client connected. Total: {len(self._clients)}")

    def unregister(self, ws):
        self._clients.discard(ws)
        logger.info(f"Client disconnected. Total: {len(self._clients)}")

    # ── Publish helpers ───────────────────────────────────────────────────────

    async def broadcast(self, event_type: str, payload: dict):
        """Send a JSON message to all connected clients."""
        if not self._clients:
            return
        message = json.dumps({
            "event":     event_type,
            "payload":   payload,
            "server_ts": datetime.utcnow().isoformat(),
        })
        dead = set()
        for ws in self._clients:
            try:
                await ws.send(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._clients.discard(ws)

    def push(self, event_type: str, payload: dict):
        """Sync wrapper — schedules broadcast on the running event loop."""
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(self.broadcast(event_type, payload))
        except RuntimeError:
            pass   # no event loop running (e.g. during tests)

    # ── Typed publishers ──────────────────────────────────────────────────────

    def push_system_state(self, system_state: SystemState):
        self.push("system_state", system_state.to_dict())

    def push_asset_update(self, asset: AssetState):
        self.push("asset_update", {
            "id":                   asset.id,
            "asset_type":           asset.asset_type,
            "current_sensor_id":    asset.current_sensor_id,
            "current_zone_id":      asset.current_zone_id,
            "previous_sensor_id":   asset.previous_sensor_id,
            "previous_zone_id":     asset.previous_zone_id,
            "time_change_location": asset.time_change_location.isoformat()
                                    if asset.time_change_location else None,
            "access_status":        asset.access_status,
        })

    def push_sensor_update(self, sensor: SensorState):
        self.push("sensor_update", {
            "sensor_id":        sensor.sensor_id,
            "zone_id":          sensor.zone_id,
            "temperature":      sensor.temperature,
            "humidity":         sensor.humidity,
            "smoke":            sensor.smoke,
            "env_status":       sensor.env_status,
            "last_time_change": sensor.last_time_change.isoformat(),
        })

    def push_health_update(self, health):
        self.push("health_update", {
            "sensor_id":            health.sensor_id,
            "zone_id":              health.zone_id,
            "status":               health.status,
            "last_heartbeat":       health.last_heartbeat.isoformat()
                                    if health.last_heartbeat else None,
            "consecutive_failures": health.consecutive_failures,
        })

    def push_alert(self, alert: dict):
        self.push("alert", alert)
