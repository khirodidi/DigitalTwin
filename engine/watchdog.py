# =============================================================================
# engine/watchdog.py
# Digital Twin — Factory Monitoring System
# Monitors every sensor in the grid for connectivity.
# Detects ONLINE → DEGRADED → OFFLINE transitions and fires alerts.
# Covers the full factory — any silent sensor is flagged immediately.
# =============================================================================

import asyncio
from datetime import datetime, timedelta
from typing import Callable

from models.state import SensorHealthState, SensorStatus


# ─── Thresholds ───────────────────────────────────────────────────────────────

HEARTBEAT_INTERVAL   = 5    # seconds — expected message frequency per sensor
DEGRADED_THRESHOLD   = 2    # missed cycles before DEGRADED
OFFLINE_THRESHOLD    = 5    # missed cycles before OFFLINE


class SensorWatchdog:
    """
    Background async task that polls all sensor health states every
    HEARTBEAT_INTERVAL seconds and transitions status based on missed cycles.

    Status transitions:
        ONLINE  → DEGRADED  after DEGRADED_THRESHOLD missed cycles
        DEGRADED → OFFLINE  after OFFLINE_THRESHOLD  missed cycles
        OFFLINE  → ONLINE   immediately on next message received

    Alerts fire ONLY on status transitions to avoid flooding.
    """

    def __init__(
        self,
        health_store:    dict[str, SensorHealthState],   # shared with StateStore
        alert_callback:  Callable[[dict], None],          # publishes alert events
    ):
        self._health         = health_store
        self._alert_callback = alert_callback

    # ── Called by MQTT handler on every incoming sensor message ───────────────

    def on_message_received(self, sensor_id: str):
        """
        Register a heartbeat for a sensor.
        Resets consecutive_failures and transitions to ONLINE if recovered.
        """
        if sensor_id not in self._health:
            return   # unknown sensor — not in registry

        now  = datetime.utcnow()
        h    = self._health[sensor_id]
        prev = h.status

        h.last_heartbeat       = now
        h.consecutive_failures = 0
        h.status               = SensorStatus.ONLINE

        # Recovered from DEGRADED or OFFLINE → publish recovery event
        if prev != SensorStatus.ONLINE:
            self._alert_callback({
                "type":      "sensor_recovered",
                "level":     "info",
                "sensor_id": sensor_id,
                "zone_id":   h.zone_id,
                "from_status": prev,
                "message":   f"Sensor {sensor_id} (zone {h.zone_id}) recovered — now ONLINE.",
                "timestamp": now.isoformat(),
            })

    # ── Background polling loop ───────────────────────────────────────────────

    async def run(self):
        """
        Runs indefinitely. On every tick, checks all sensors for missed heartbeats
        and transitions their status accordingly.
        """
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            now = datetime.utcnow()

            for sensor_id, h in self._health.items():

                # Sensors not yet seen since startup
                if h.last_heartbeat is None:
                    h.consecutive_failures += 1
                    self._maybe_transition(h, now)
                    continue

                elapsed_secs   = (now - h.last_heartbeat).total_seconds()
                missed_cycles  = int(elapsed_secs // HEARTBEAT_INTERVAL)
                h.consecutive_failures = missed_cycles

                self._maybe_transition(h, now)

    def _maybe_transition(self, h: SensorHealthState, now: datetime):
        prev = h.status

        if h.consecutive_failures >= OFFLINE_THRESHOLD:
            h.status = SensorStatus.OFFLINE
        elif h.consecutive_failures >= DEGRADED_THRESHOLD:
            h.status = SensorStatus.DEGRADED
        # else stays ONLINE (or remains as-is if consecutive_failures < DEGRADED_THRESHOLD)

        if h.status != prev:
            level = "critical" if h.status == SensorStatus.OFFLINE else "warning"
            self._alert_callback({
                "type":        "sensor_status_change",
                "level":       level,
                "sensor_id":   h.sensor_id,
                "zone_id":     h.zone_id,
                "from_status": prev,
                "to_status":   h.status,
                "missed_cycles": h.consecutive_failures,
                "message": (
                    f"Sensor {h.sensor_id} (zone {h.zone_id}) → {h.status.upper()}. "
                    + (
                        "Check or replace the sensor."
                        if h.status == SensorStatus.OFFLINE
                        else "Monitor — possible interference or packet loss."
                    )
                ),
                "action":    "check_sensor" if h.status == SensorStatus.OFFLINE else "monitor",
                "timestamp": now.isoformat(),
            })
