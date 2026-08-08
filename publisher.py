# publisher.py — standalone publisher for non-FastAPI contexts (tests/CLI)
import logging
from datetime import datetime
logger = logging.getLogger(__name__)

class Publisher:
    def __init__(self):
        self._callbacks = []

    def register_callback(self, fn):
        self._callbacks.append(fn)

    def push(self, event_type: str, payload: dict):
        envelope = {"event":event_type,"payload":payload,"ts":datetime.utcnow().isoformat()}
        for fn in self._callbacks:
            try: fn(envelope)
            except Exception as e: logger.error(f"Callback error: {e}")

    def push_system_state(self, s):  self.push("system_state", s if isinstance(s,dict) else s.to_dict())
    def push_asset_update(self, a):  self.push("asset_update",  {"id":a.id,"current_sensor_id":a.current_sensor_id,"current_zone_id":a.current_zone_id,"access_status":a.access_status})
    def push_sensor_update(self, s): self.push("sensor_update", {"sensor_id":s.sensor_id,"zone_id":s.zone_id,"temperature":s.temperature,"humidity":s.humidity,"smoke":s.smoke,"env_status":s.env_status})
    def push_alert(self, a):         self.push("alert",     a)
    def push_ai_insight(self, i):    self.push("ai_insight",i)
