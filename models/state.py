# =============================================================================
# models/state.py
# Digital Twin — Factory Monitoring System
# All state dataclasses, enums, and the ZoneRegistry
# =============================================================================

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


# ─── Status enums ─────────────────────────────────────────────────────────────

class SensorStatus(str, Enum):
    ONLINE   = "online"
    DEGRADED = "degraded"   # sending but readings are noisy/incomplete
    OFFLINE  = "offline"    # no heartbeat within threshold


class EnvStatus(str, Enum):
    NORMAL   = "normal"
    WARNING  = "warning"
    CRITICAL = "critical"


class AccessStatus(str, Enum):
    AUTHORISED = "authorised"
    VIOLATION  = "violation"
    UNKNOWN    = "unknown"    # sensor offline → cannot confirm location


class SystemStatus(str, Enum):
    NOMINAL  = "nominal"    # all green
    DEGRADED = "degraded"   # at least one warning
    CRITICAL = "critical"   # at least one critical condition


# ─── Zone registry ────────────────────────────────────────────────────────────

class ZoneRegistry:
    """
    Static mapping loaded once at startup from the database.
    Represents the factory grid:
      - Each grid cell has exactly one sensor.
      - Each sensor belongs to exactly one zone.
      - A zone can span multiple sensors (grid cells).

    sensor_to_zone : { 'S1': 'zone_A', 'S2': 'zone_A', 'S7': 'zone_C', ... }
    """

    def __init__(self, sensor_to_zone: dict[str, str]):
        self._sensor_to_zone = sensor_to_zone
        # Build reverse mapping: zone_id → list[sensor_id]
        self._zone_to_sensors: dict[str, list[str]] = {}
        for sensor_id, zone_id in sensor_to_zone.items():
            self._zone_to_sensors.setdefault(zone_id, []).append(sensor_id)

    def get_zone(self, sensor_id: str) -> Optional[str]:
        """Resolve sensor_id → zone_id."""
        return self._sensor_to_zone.get(sensor_id)

    def get_sensors(self, zone_id: str) -> list[str]:
        """All sensor_ids belonging to a zone."""
        return self._zone_to_sensors.get(zone_id, [])

    def all_zones(self) -> list[str]:
        return list(self._zone_to_sensors.keys())

    def all_sensors(self) -> list[str]:
        return list(self._sensor_to_zone.keys())


# ─── Sensor health state ──────────────────────────────────────────────────────

@dataclass
class SensorHealthState:
    """
    Tracks the connectivity and operational status of each sensor.
    Updated by the SensorWatchdog independently of environmental readings.
    Covers the full factory grid — every sensor must be accounted for.
    """
    sensor_id:            str
    zone_id:              Optional[str]
    status:               SensorStatus
    last_heartbeat:       Optional[datetime]   # last MQTT message timestamp
    last_reading:         Optional[datetime]   # last env reading timestamp
    consecutive_failures: int = 0              # missed watchdog cycles


# ─── Sensor environmental state ───────────────────────────────────────────────

@dataclass
class SensorState:
    """
    Represents the live environmental readings of one sensor (grid cell).
    The sensor_id is the grid cell identifier and maps to a zone via ZoneRegistry.

    WSN message format:
        ['sensor_id', 'temperature|humidity|smoke', value, timestamp]
    """
    sensor_id:        str
    zone_id:          Optional[str]
    temperature:      Optional[float]   # °C
    humidity:         Optional[float]   # %
    smoke:            bool              # True = smoke detected
    env_status:       EnvStatus
    last_time_change: datetime

    def compute_env_status(
        self,
        temp_warn: float = 50.0,
        temp_crit: float = 60.0,
        hum_warn:  float = 70.0,
        hum_crit:  float = 85.0,
    ) -> EnvStatus:
        """Derive env_status from current readings."""
        if self.smoke:
            return EnvStatus.CRITICAL
        if (self.temperature is not None and self.temperature > temp_crit) or \
           (self.humidity    is not None and self.humidity    > hum_crit):
            return EnvStatus.CRITICAL
        if (self.temperature is not None and self.temperature > temp_warn) or \
           (self.humidity    is not None and self.humidity    > hum_warn):
            return EnvStatus.WARNING
        return EnvStatus.NORMAL


# ─── Asset state ──────────────────────────────────────────────────────────────

@dataclass
class AssetState:
    """
    Represents the live state of a worker or mobile object.

    Location is tracked at two granularities:
      - current_sensor_id  : exact grid cell the asset is connected to
      - current_zone_id    : zone that sensor belongs to (resolved via ZoneRegistry)

    Authorisations are stored as sets of allowed sensor_ids and/or zone_ids.
    An asset is authorised if its current sensor OR zone is in the allowed set.

    WSN message format:
        ['worker_id|object_id', 'sensor_id', timestamp]
    """
    id:                   str
    asset_type:           str                    # 'worker' | 'object'

    # Current location — both granularities
    current_sensor_id:    Optional[str]          # fine-grained (grid cell)
    current_zone_id:      Optional[str]          # coarse (zone)

    # Previous location
    previous_sensor_id:   Optional[str]
    previous_zone_id:     Optional[str]

    time_change_location: Optional[datetime]     # when sensor_id last changed

    # Authorisations
    allowed_sensors:      set[str] = field(default_factory=set)
    allowed_zones:        set[str] = field(default_factory=set)

    access_status:        AccessStatus = AccessStatus.UNKNOWN

    def compute_access_status(
        self,
        sensor_health: SensorHealthState,
    ) -> AccessStatus:
        """
        Evaluate access status given the current sensor's health.
        - If sensor is offline → UNKNOWN (location unconfirmed, not a violation)
        - If sensor is online  → check authorisation sets
        """
        if sensor_health.status == SensorStatus.OFFLINE:
            return AccessStatus.UNKNOWN
        if self.current_sensor_id in self.allowed_sensors or \
           self.current_zone_id   in self.allowed_zones:
            return AccessStatus.AUTHORISED
        return AccessStatus.VIOLATION

    def has_changed_sensor(self) -> bool:
        return self.current_sensor_id != self.previous_sensor_id

    def has_changed_zone(self) -> bool:
        return self.current_zone_id != self.previous_zone_id


# ─── Global system state aggregate ───────────────────────────────────────────

@dataclass
class SystemState:
    """
    A single snapshot of the entire factory state at a given moment.
    Recomputed after every state update and pushed to the frontend over WebSocket.
    Combines:
      - Sensor health  (online / degraded / offline counts)
      - Environmental  (normal / warning / critical zone counts)
      - Access control (authorised / violation / unknown asset counts)
    """
    timestamp:           datetime
    overall_status:      SystemStatus

    # Sensor health
    sensors_online:      int
    sensors_degraded:    int
    sensors_offline:     int
    offline_sensor_ids:  list[str]

    # Environmental
    zones_normal:        int
    zones_warning:       int
    zones_critical:      int
    critical_zone_ids:   list[str]

    # Access
    total_assets:        int
    access_violations:   int
    unknown_locations:   int
    violation_asset_ids: list[str]

    def to_dict(self) -> dict:
        return {
            "timestamp":      self.timestamp.isoformat(),
            "overall_status": self.overall_status,
            "sensors": {
                "online":     self.sensors_online,
                "degraded":   self.sensors_degraded,
                "offline":    self.sensors_offline,
                "offline_ids": self.offline_sensor_ids,
            },
            "environment": {
                "zones_normal":   self.zones_normal,
                "zones_warning":  self.zones_warning,
                "zones_critical": self.zones_critical,
                "critical_ids":   self.critical_zone_ids,
            },
            "access": {
                "total_assets":  self.total_assets,
                "violations":    self.access_violations,
                "unknown":       self.unknown_locations,
                "violation_ids": self.violation_asset_ids,
            },
        }
