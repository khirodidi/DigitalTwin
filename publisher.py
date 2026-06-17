# =============================================================================
# publisher.py
# Thin shim kept for backward compatibility.
# All real broadcasting is done by api/ws_manager.py.
# The engine receives ws_manager directly and calls it;
# this file is only used in standalone/test contexts.
# =============================================================================

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class Publisher:
    """
    Standalone publisher used outside of FastAPI (e.g. tests, CLI runs).
    In the deployed app, DigitalTwinEngine uses WebSocketManager directly.
    """

    def __init__(self):
        self._callbacks: list = []

    def register_callback(self, fn):
        """Register a callable that receives (event_type, payload)."""
        self._callbacks.append(fn)

    def push(self, event_type: str, payload: dict):
        envelope = {
            "event":   event_type,
            "payload": payload,
            "ts":      datetime.utcnow().isoformat(),
        }
        for fn in self._callbacks:
            try:
                fn(envelope)
            except Exception as e:
                logger.error(f"Publisher callback error: {e}")

    def push_system_state(self, state):
        self.push("system_state", state if isinstance(state, dict) else state.to_dict())

    def push_asset_update(self, asset):
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

    def push_sensor_update(self, sensor):
        self.push("sensor_update", {
            "sensor_id":        sensor.sensor_id,
            "zone_id":          sensor.zone_id,
            "temperature":      sensor.temperature,
            "humidity":         sensor.humidity,
            "smoke":            sensor.smoke,
            "env_status":       sensor.env_status,
            "last_time_change": sensor.last_time_change.isoformat(),
        })

    def push_alert(self, alert: dict):
        self.push("alert", alert)

    def push_ai_insight(self, insight: dict):
        self.push("ai_insight", insight)
