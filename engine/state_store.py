# =============================================================================
# engine/state_store.py
# Digital Twin — Factory Monitoring System
# In-memory state store for all assets, sensors, and sensor health.
# Rehydrated from PostgreSQL on startup.
# =============================================================================

from datetime import datetime
from typing import Optional

from models.state import (
    AssetState, SensorState, SensorHealthState,
    ZoneRegistry, SensorStatus, EnvStatus, AccessStatus,
)


class StateStore:
    """
    Central in-memory store for the live state of the entire factory.

    Three state dictionaries:
        _assets  : asset_id  → AssetState
        _sensors : sensor_id → SensorState
        _health  : sensor_id → SensorHealthState   (shared with SensorWatchdog)

    The ZoneRegistry resolves sensor_id → zone_id on every update.
    No database queries during normal operation — all reads are O(1) dict lookups.
    """

    def __init__(self, zone_registry: ZoneRegistry):
        self._registry: ZoneRegistry                    = zone_registry
        self._assets:   dict[str, AssetState]           = {}
        self._sensors:  dict[str, SensorState]          = {}
        self._health:   dict[str, SensorHealthState]    = {}

        # Initialise health state for every known sensor (full grid coverage)
        for sensor_id in zone_registry.all_sensors():
            self._health[sensor_id] = SensorHealthState(
                sensor_id            = sensor_id,
                zone_id              = zone_registry.get_zone(sensor_id),
                status               = SensorStatus.OFFLINE,   # unknown until first heartbeat
                last_heartbeat       = None,
                last_reading         = None,
                consecutive_failures = 0,
            )

    # ── Asset updates ─────────────────────────────────────────────────────────

    def update_asset_location(
        self,
        asset_id:  str,
        sensor_id: str,
        timestamp: datetime,
    ) -> AssetState:
        """
        Process a localisation message. Resolves sensor → zone, detects zone
        changes, and recomputes access status.
        """
        prev      = self._assets.get(asset_id)
        zone_id   = self._registry.get_zone(sensor_id)
        health    = self._health.get(sensor_id)

        sensor_changed = (prev is None or prev.current_sensor_id != sensor_id)

        state = AssetState(
            id                   = asset_id,
            asset_type           = prev.asset_type if prev else "unknown",
            current_sensor_id    = sensor_id,
            current_zone_id      = zone_id,
            previous_sensor_id   = prev.current_sensor_id if prev else None,
            previous_zone_id     = prev.current_zone_id   if prev else None,
            time_change_location = timestamp if sensor_changed else (
                                       prev.time_change_location if prev else timestamp),
            allowed_sensors      = prev.allowed_sensors if prev else set(),
            allowed_zones        = prev.allowed_zones   if prev else set(),
        )

        # Recompute access status
        if health:
            state.access_status = state.compute_access_status(health)
        else:
            state.access_status = AccessStatus.UNKNOWN

        self._assets[asset_id] = state
        return state

    def set_asset_authorisations(
        self,
        asset_id:        str,
        allowed_sensors: set[str],
        allowed_zones:   set[str],
    ):
        """Update authorisation sets for an asset (e.g. after a DB change)."""
        if asset_id in self._assets:
            self._assets[asset_id].allowed_sensors = allowed_sensors
            self._assets[asset_id].allowed_zones   = allowed_zones

    # ── Sensor updates ────────────────────────────────────────────────────────

    def update_sensor_reading(
        self,
        sensor_id:    str,
        reading_type: str,
        value,
        timestamp:    datetime,
    ) -> SensorState:
        """
        Process an environmental reading. Carries forward unchanged readings
        from the previous state and recomputes env_status.
        """
        prev    = self._sensors.get(sensor_id)
        zone_id = self._registry.get_zone(sensor_id)

        state = SensorState(
            sensor_id   = sensor_id,
            zone_id     = zone_id,
            temperature = value if reading_type == "temperature" else (
                              prev.temperature if prev else None),
            humidity    = value if reading_type == "humidity"    else (
                              prev.humidity    if prev else None),
            smoke       = bool(value) if reading_type == "smoke" else (
                              prev.smoke       if prev else False),
            env_status  = EnvStatus.NORMAL,    # recomputed below
            last_time_change = timestamp,
        )
        state.env_status = state.compute_env_status()

        self._sensors[sensor_id] = state

        # Update health last_reading timestamp
        if sensor_id in self._health:
            self._health[sensor_id].last_reading = timestamp

        return state

    # ── Health access (used by watchdog) ──────────────────────────────────────

    @property
    def health(self) -> dict[str, SensorHealthState]:
        """Direct reference — shared with SensorWatchdog."""
        return self._health

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_asset(self, asset_id: str) -> Optional[AssetState]:
        return self._assets.get(asset_id)

    def get_sensor(self, sensor_id: str) -> Optional[SensorState]:
        return self._sensors.get(sensor_id)

    def get_health(self, sensor_id: str) -> Optional[SensorHealthState]:
        return self._health.get(sensor_id)

    def all_assets(self)  -> list[AssetState]:
        return list(self._assets.values())

    def all_sensors(self) -> list[SensorState]:
        return list(self._sensors.values())

    def all_health(self)  -> list[SensorHealthState]:
        return list(self._health.values())

    def assets_in_sensor(self, sensor_id: str) -> list[AssetState]:
        """All assets connected to a specific sensor (exact grid cell)."""
        return [a for a in self._assets.values()
                if a.current_sensor_id == sensor_id]

    def assets_in_zone(self, zone_id: str) -> list[AssetState]:
        """All assets in a zone (across all its sensors)."""
        return [a for a in self._assets.values()
                if a.current_zone_id == zone_id]

    # ── Snapshot (for DB persistence on startup/shutdown) ─────────────────────

    def snapshot(self) -> dict:
        return {
            "assets":  {k: v.__dict__ for k, v in self._assets.items()},
            "sensors": {k: v.__dict__ for k, v in self._sensors.items()},
            "health":  {k: v.__dict__ for k, v in self._health.items()},
        }
