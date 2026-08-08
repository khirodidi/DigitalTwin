# =============================================================================
# engine/watchdog.py  — FIXED
#
# Changes from previous version:
#   BUG: on_message_received() had `if sensor_id not in self._health: return`
#        This silently dropped every message from sensors that were not
#        pre-seeded in the database, so they stayed OFFLINE forever and every
#        asset located on them got AccessStatus.UNKNOWN.
#
#   FIX: When a sensor is seen for the first time, auto-register it as ONLINE
#        so the state store can compute access status correctly without
#        requiring the DB to be pre-seeded.
# =============================================================================

import asyncio
from datetime import datetime
from typing import Callable
from models.state import SensorHealthState, SensorStatus

HEARTBEAT_INTERVAL = 5     # seconds between watchdog ticks
DEGRADED_THRESHOLD = 2     # missed cycles before DEGRADED
OFFLINE_THRESHOLD  = 5     # missed cycles before OFFLINE


class SensorWatchdog:
    def __init__(self, health_store: dict[str, SensorHealthState],
                 alert_callback: Callable[[dict], None]):
        self._health   = health_store
        self._alert    = alert_callback

    # ── FIX: auto-register sensor if not pre-seeded ───────────────────────────
    def _get_or_register(self, sensor_id: str) -> SensorHealthState:
        """
        Return health state for sensor_id.
        If the sensor was never loaded from the DB (e.g. seed was not run),
        create an entry on the fly so the sensor can go ONLINE immediately.
        """
        if sensor_id not in self._health:
            self._health[sensor_id] = SensorHealthState(
                sensor_id            = sensor_id,
                zone_id              = None,   # will be resolved later
                status               = SensorStatus.OFFLINE,
                last_heartbeat       = None,
                last_reading         = None,
                consecutive_failures = 0,
            )
        return self._health[sensor_id]

    def on_message_received(self, sensor_id: str):
        """Call this every time ANY message arrives from sensor_id."""
        now  = datetime.utcnow()
        h    = self._get_or_register(sensor_id)   # FIX: was `if not in: return`
        prev = h.status

        h.last_heartbeat       = now
        h.consecutive_failures = 0
        h.status               = SensorStatus.ONLINE

        if prev != SensorStatus.ONLINE:
            self._alert({
                "type":       "sensor_recovered",
                "level":      "info",
                "sensor_id":  sensor_id,
                "zone_id":    h.zone_id,
                "from_status": prev,
                "message":    f"Sensor {sensor_id} back ONLINE.",
                "timestamp":  now.isoformat(),
            })

    def _maybe_transition(self, h: SensorHealthState, now: datetime):
        prev = h.status
        if   h.consecutive_failures >= OFFLINE_THRESHOLD:  h.status = SensorStatus.OFFLINE
        elif h.consecutive_failures >= DEGRADED_THRESHOLD: h.status = SensorStatus.DEGRADED
        if h.status != prev:
            self._alert({
                "type":              "sensor_status_change",
                "level":             "critical" if h.status == SensorStatus.OFFLINE else "warning",
                "sensor_id":         h.sensor_id,
                "zone_id":           h.zone_id,
                "from_status":       prev,
                "to_status":         h.status,
                "missed_cycles":     h.consecutive_failures,
                "message":          (f"Sensor {h.sensor_id} → {h.status.upper()}. "
                                     + ("Check hardware." if h.status == SensorStatus.OFFLINE
                                        else "Monitoring.")),
                "action":            "check_sensor" if h.status == SensorStatus.OFFLINE else "monitor",
                "timestamp":         now.isoformat(),
            })

    async def run(self):
        """Background loop — ticks every HEARTBEAT_INTERVAL seconds."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            now = datetime.utcnow()
            for h in list(self._health.values()):
                if h.last_heartbeat is None:
                    h.consecutive_failures += 1
                else:
                    elapsed = (now - h.last_heartbeat).total_seconds()
                    h.consecutive_failures = int(elapsed // HEARTBEAT_INTERVAL)
                self._maybe_transition(h, now)
