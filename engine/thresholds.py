# =============================================================================
# engine/thresholds.py
#
# Environmental threshold resolution.
#
# A sensor's warning/critical limits are resolved through a three-level chain:
#
#     sensor_config  →  zones  →  factory_config (global default)
#
# A NULL at one level falls through to the next. This lets an operator say
# "the whole furnace zone runs hot, warn at 70 °C" once, while still being able
# to single out one sensor next to the door that should warn at 45 °C.
#
# The resolved table is cached in memory and refreshed whenever the
# configuration changes, so the hot path costs a dict lookup rather than a
# database round-trip.
# =============================================================================

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Used only when neither the sensor, its zone, nor factory_config specify one
HARD_DEFAULTS = {
    "temp_warning":      50.0,
    "temp_critical":     60.0,
    "humidity_warning":  70.0,
    "humidity_critical": 85.0,
}


@dataclass
class Thresholds:
    temp_warning:      float
    temp_critical:     float
    humidity_warning:  float
    humidity_critical: float
    # Where each value came from, for display in the dashboard
    source: dict = None

    def classify(self, temperature: Optional[float],
                 humidity: Optional[float], smoke: bool) -> str:
        """Return 'critical' | 'warning' | 'normal' for these readings."""
        if smoke:
            return "critical"
        t = temperature if temperature is not None else -999.0
        h = humidity    if humidity    is not None else -999.0
        if t >= self.temp_critical or h >= self.humidity_critical:
            return "critical"
        if t >= self.temp_warning or h >= self.humidity_warning:
            return "warning"
        return "normal"

    def to_dict(self) -> dict:
        return {
            "temp_warning":      self.temp_warning,
            "temp_critical":     self.temp_critical,
            "humidity_warning":  self.humidity_warning,
            "humidity_critical": self.humidity_critical,
            "source":            self.source or {},
        }


class ThresholdResolver:
    """Builds and caches the resolved threshold table for every sensor."""

    KEYS = ("temp_warning", "temp_critical",
            "humidity_warning", "humidity_critical")

    def __init__(self):
        self._by_sensor: dict[str, Thresholds] = {}
        self._global:    dict[str, float]      = dict(HARD_DEFAULTS)
        self._zone:      dict[str, dict]       = {}

    # ── Loading ──────────────────────────────────────────────────────────────

    def reload(self):
        """Re-read everything from the database and rebuild the cache."""
        try:
            from persistence.postgres import get_conn
            import psycopg2.extras
            conn = get_conn()

            # Level 3 — global defaults
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT key, value FROM factory_config")
                cfg = {r["key"]: r["value"] for r in cur.fetchall()}
            self._global = {}
            for k in self.KEYS:
                try:
                    self._global[k] = float(cfg.get(k, HARD_DEFAULTS[k]))
                except (TypeError, ValueError):
                    self._global[k] = HARD_DEFAULTS[k]

            # Level 2 — per zone
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""SELECT zone_id, temp_warning, temp_critical,
                                      humidity_warning, humidity_critical
                               FROM zones""")
                self._zone = {r["zone_id"]: {k: r[k] for k in self.KEYS}
                              for r in cur.fetchall()}

            # Level 1 — per sensor, joined to its zone
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT s.sensor_id, s.zone_id,
                           sc.temp_warning, sc.temp_critical,
                           sc.humidity_warning, sc.humidity_critical
                    FROM sensors s
                    LEFT JOIN sensor_config sc USING (sensor_id)
                """)
                rows = cur.fetchall()

            self._by_sensor = {}
            for r in rows:
                self._by_sensor[r["sensor_id"]] = self._resolve(
                    {k: r[k] for k in self.KEYS}, r["zone_id"])

            logger.info(f"Thresholds resolved for {len(self._by_sensor)} sensors "
                        f"({len(self._zone)} zones, global "
                        f"T{self._global['temp_warning']:.0f}/"
                        f"{self._global['temp_critical']:.0f})")
        except Exception as e:
            logger.warning(f"Threshold reload failed, using defaults: {e}")

    def _resolve(self, sensor_vals: dict, zone_id: Optional[str]) -> Thresholds:
        zone_vals = self._zone.get(zone_id or "", {})
        out, src = {}, {}
        for k in self.KEYS:
            if sensor_vals.get(k) is not None:
                out[k], src[k] = float(sensor_vals[k]), "sensor"
            elif zone_vals.get(k) is not None:
                out[k], src[k] = float(zone_vals[k]), "zone"
            else:
                out[k], src[k] = float(self._global.get(k, HARD_DEFAULTS[k])), "global"
        return Thresholds(**out, source=src)

    # ── Lookup ───────────────────────────────────────────────────────────────

    def get(self, sensor_id: str, zone_id: Optional[str] = None) -> Thresholds:
        """Resolved thresholds for a sensor. Unknown sensors get the defaults."""
        t = self._by_sensor.get(sensor_id)
        if t is not None:
            return t
        # Sensor not in the cache (e.g. auto-registered) — resolve on the fly
        t = self._resolve({k: None for k in self.KEYS}, zone_id)
        self._by_sensor[sensor_id] = t
        return t

    def all(self) -> dict:
        return {sid: t.to_dict() for sid, t in self._by_sensor.items()}


# Module-level singleton used by the engine
resolver = ThresholdResolver()
