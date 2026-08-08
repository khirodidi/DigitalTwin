# =============================================================================
# models/state.py  —  Digital Twin: all state dataclasses, enums, ZoneRegistry
# =============================================================================
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum

class SensorStatus(str, Enum):
    ONLINE   = "online"
    DEGRADED = "degraded"
    OFFLINE  = "offline"

class EnvStatus(str, Enum):
    NORMAL   = "normal"
    WARNING  = "warning"
    CRITICAL = "critical"

class AccessStatus(str, Enum):
    AUTHORISED = "authorised"
    VIOLATION  = "violation"
    UNKNOWN    = "unknown"

class SystemStatus(str, Enum):
    NOMINAL  = "nominal"
    DEGRADED = "degraded"
    CRITICAL = "critical"

class ZoneRegistry:
    """
    Static sensor→zone mapping loaded at startup from the database.
    Grid topology: each cell = one sensor, one zone can span N cells.
    """
    def __init__(self, sensor_to_zone: dict[str, str]):
        self._s2z = sensor_to_zone
        self._z2s: dict[str, list[str]] = {}
        for sid, zid in sensor_to_zone.items():
            self._z2s.setdefault(zid, []).append(sid)

    def get_zone(self, sensor_id: str) -> Optional[str]:
        return self._s2z.get(sensor_id)

    def get_sensors(self, zone_id: str) -> list[str]:
        return self._z2s.get(zone_id, [])

    def all_zones(self)   -> list[str]: return list(self._z2s.keys())
    def all_sensors(self) -> list[str]: return list(self._s2z.keys())


@dataclass
class SensorHealthState:
    sensor_id:            str
    zone_id:              Optional[str]
    status:               SensorStatus
    last_heartbeat:       Optional[datetime]
    last_reading:         Optional[datetime]
    consecutive_failures: int = 0


@dataclass
class SensorState:
    sensor_id:        str
    zone_id:          Optional[str]
    temperature:      Optional[float]
    humidity:         Optional[float]
    smoke:            bool
    env_status:       EnvStatus
    last_time_change: datetime

    def compute_env_status(self, t_warn=50.0, t_crit=60.0,
                            h_warn=70.0, h_crit=85.0) -> EnvStatus:
        if self.smoke: return EnvStatus.CRITICAL
        if (self.temperature or 0) > t_crit or (self.humidity or 0) > h_crit:
            return EnvStatus.CRITICAL
        if (self.temperature or 0) > t_warn or (self.humidity or 0) > h_warn:
            return EnvStatus.WARNING
        return EnvStatus.NORMAL


@dataclass
class AssetState:
    """
    Live state of a worker or mobile object.
    Location stored at two granularities:
      current_sensor_id — exact grid cell
      current_zone_id   — zone the cell belongs to
    Authorisations stored as sets; checked at both levels.
    """
    id:                   str
    asset_type:           str           # 'worker' | 'object' | 'forklift' | 'pallet'
    current_sensor_id:    Optional[str]
    current_zone_id:      Optional[str]
    previous_sensor_id:   Optional[str]
    previous_zone_id:     Optional[str]
    time_change_location: Optional[datetime]
    allowed_sensors:      set[str] = field(default_factory=set)
    allowed_zones:        set[str] = field(default_factory=set)
    access_status:        AccessStatus = AccessStatus.UNKNOWN

    def compute_access_status(self, health: SensorHealthState) -> AccessStatus:
        if health.status == SensorStatus.OFFLINE:
            return AccessStatus.UNKNOWN
        if (self.current_sensor_id in self.allowed_sensors or
                self.current_zone_id in self.allowed_zones):
            return AccessStatus.AUTHORISED
        return AccessStatus.VIOLATION

    def has_changed_sensor(self) -> bool:
        return self.current_sensor_id != self.previous_sensor_id

    def has_changed_zone(self) -> bool:
        return self.current_zone_id != self.previous_zone_id


@dataclass
class SystemState:
    """
    Global factory snapshot recomputed after every state update.
    Pushed to all React clients over WebSocket.
    """
    timestamp:           datetime
    overall_status:      SystemStatus
    sensors_online:      int
    sensors_degraded:    int
    sensors_offline:     int
    offline_sensor_ids:  list[str]
    zones_normal:        int
    zones_warning:       int
    zones_critical:      int
    critical_zone_ids:   list[str]
    total_assets:        int
    access_violations:   int
    unknown_locations:   int
    violation_asset_ids: list[str]

    def to_dict(self) -> dict:
        return {
            "timestamp":      self.timestamp.isoformat(),
            "overall_status": self.overall_status,
            "sensors": {
                "online":   self.sensors_online,
                "degraded": self.sensors_degraded,
                "offline":  self.sensors_offline,
                "offline_ids": self.offline_sensor_ids,
            },
            "environment": {
                "zones_normal":   self.zones_normal,
                "zones_warning":  self.zones_warning,
                "zones_critical": self.zones_critical,
                "critical_ids":   self.critical_zone_ids,
            },
            "access": {
                "total_assets": self.total_assets,
                "violations":   self.access_violations,
                "unknown":      self.unknown_locations,
                "violation_ids":self.violation_asset_ids,
            },
        }
