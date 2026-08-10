# =============================================================================
# engine/state_store.py  — FIXED
#
# Changes from previous version:
#   BUG: update_asset_location() computed access status with:
#        `health = self._health.get(sensor_id)` → could be None
#        then → `if health else AccessStatus.UNKNOWN`
#        So any asset whose sensor was not pre-seeded got stuck as UNKNOWN.
#
#   BUG: update_sensor_reading() did not create a health entry for sensors
#        not in the registry, so the frontend showed them as offline/unknown.
#
#   FIX: Both methods now call _ensure_health() which auto-registers the
#        sensor with ONLINE status if it hasn't been registered yet.
#        This makes the system work without running seed_db.sql first.
#
#   NOTE: The watchdog does the same thing in on_message_received(), so
#         between the two fixes, a sensor goes ONLINE the moment its first
#         message arrives regardless of whether the DB was seeded.
# =============================================================================

from datetime import datetime
from typing import Optional
from models.state import (
    AssetState, SensorState, SensorHealthState,
    ZoneRegistry, SensorStatus, EnvStatus, AccessStatus,
)

# Fallback only — real limits come from engine.thresholds.resolver, which
# resolves sensor_config → zones → factory_config for every sensor.
TEMP_WARN  = 50.0
TEMP_CRIT  = 60.0
HUM_WARN   = 70.0
HUM_CRIT   = 85.0


class StateStore:
    def __init__(self, zone_registry: ZoneRegistry):
        self._reg     = zone_registry
        self._assets  : dict[str, AssetState]        = {}
        self._asset_meta: dict[str, dict]            = {}   # id → {name, type}
        # id → (allowed_sensors, allowed_zones). Kept separately from _assets
        # because authorisations are loaded at startup, BEFORE any asset has
        # reported a location — see set_asset_authorisations().
        self._asset_auth: dict[str, tuple[set, set]] = {}
        self._sensors : dict[str, SensorState]       = {}
        self._health  : dict[str, SensorHealthState] = {}

        # Pre-register all sensors from the DB (may be empty if seed not run)
        for sid in zone_registry.all_sensors():
            self._health[sid] = SensorHealthState(
                sensor_id            = sid,
                zone_id              = zone_registry.get_zone(sid),
                status               = SensorStatus.OFFLINE,
                last_heartbeat       = None,
                last_reading         = None,
                consecutive_failures = 0,
            )

    # ── FIX: auto-register sensor on first message ────────────────────────────
    def _ensure_health(self, sensor_id: str) -> SensorHealthState:
        """
        Return (and if needed create) the health record for sensor_id.
        When a sensor sends messages but was never seeded into the DB,
        we create it here as ONLINE so access status resolves correctly.
        """
        if sensor_id not in self._health:
            zone_id = self._reg.get_zone(sensor_id)   # None if not in registry
            self._health[sensor_id] = SensorHealthState(
                sensor_id            = sensor_id,
                zone_id              = zone_id,
                status               = SensorStatus.ONLINE,  # it just sent a message
                last_heartbeat       = datetime.utcnow(),
                last_reading         = datetime.utcnow(),
                consecutive_failures = 0,
            )
        return self._health[sensor_id]

    # ── Asset location update ─────────────────────────────────────────────────
    def update_asset_location(self, asset_id: str, sensor_id: str,
                               timestamp: datetime) -> AssetState:
        prev    = self._assets.get(asset_id)
        zone_id = self._reg.get_zone(sensor_id)
        health  = self._ensure_health(sensor_id)   # FIX: was .get() → could be None
        changed = (prev is None or prev.current_sensor_id != sensor_id)

        # Preserve asset_type and display name from previous state / registry
        asset_type = (prev.asset_type if prev and prev.asset_type != "unknown"
                      else self._asset_meta.get(asset_id, {}).get("type", "worker"))
        asset_name = ((prev.name if prev and prev.name else None)
                      or self._asset_meta.get(asset_id, {}).get("name")
                      or asset_id)

        # Authorisations come from the registry so they survive an asset's
        # first location event; fall back to whatever the previous state held.
        if asset_id in self._asset_auth:
            sensors, zones = self._asset_auth[asset_id]
            auth_sensors, auth_zones = set(sensors), set(zones)
        else:
            auth_sensors = set(prev.allowed_sensors) if prev else set()
            auth_zones   = set(prev.allowed_zones)   if prev else set()

        state = AssetState(
            id                   = asset_id,
            asset_type           = asset_type,
            current_sensor_id    = sensor_id,
            current_zone_id      = zone_id,
            previous_sensor_id   = prev.current_sensor_id if prev else None,
            previous_zone_id     = prev.current_zone_id   if prev else None,
            time_change_location = timestamp if changed else
                                   (prev.time_change_location if prev else timestamp),
            allowed_sensors      = auth_sensors,
            allowed_zones        = auth_zones,
            name                 = asset_name,
        )
        # Access status — never UNKNOWN unless sensor is genuinely OFFLINE
        state.access_status = state.compute_access_status(health)
        self._assets[asset_id] = state
        return state

    # ── Sensor reading update ─────────────────────────────────────────────────
    def update_sensor_reading(self, sensor_id: str, reading_type: str,
                               value, timestamp: datetime) -> SensorState:
        prev    = self._sensors.get(sensor_id)
        zone_id = self._reg.get_zone(sensor_id)
        health  = self._ensure_health(sensor_id)   # FIX: ensure health exists
        health.last_reading = timestamp

        state = SensorState(
            sensor_id        = sensor_id,
            zone_id          = zone_id,
            temperature      = (value if reading_type == "temperature"
                                else (prev.temperature if prev else None)),
            humidity         = (value if reading_type == "humidity"
                                else (prev.humidity    if prev else None)),
            smoke            = (bool(value) if reading_type == "smoke"
                                else (prev.smoke       if prev else False)),
            env_status       = EnvStatus.NORMAL,
            last_time_change = timestamp,
        )
        # Per-sensor thresholds: sensor override → zone → global default
        try:
            from engine.thresholds import resolver
            th = resolver.get(sensor_id, zone_id)
            state.env_status = state.compute_env_status(
                t_warn=th.temp_warning,     t_crit=th.temp_critical,
                h_warn=th.humidity_warning, h_crit=th.humidity_critical,
            )
        except Exception:
            state.env_status = state.compute_env_status(
                t_warn=TEMP_WARN, t_crit=TEMP_CRIT,
                h_warn=HUM_WARN,  h_crit=HUM_CRIT,
            )
        self._sensors[sensor_id] = state
        return state

    # ── Authorisations ────────────────────────────────────────────────────────
    def set_asset_meta(self, asset_id: str, name: str, asset_type: str):
        """Register the display name and type of an asset (loaded from the DB)."""
        self._asset_meta[asset_id] = {"name": name, "type": asset_type}
        if asset_id in self._assets:
            self._assets[asset_id].name       = name
            self._assets[asset_id].asset_type = asset_type

    def set_asset_authorisations(self, asset_id: str,
                                  allowed_sensors: set, allowed_zones: set):
        """
        Record what an asset may access.

        Stored in _asset_auth rather than only on the live AssetState: this is
        called at engine startup and from the config API, both of which can run
        before the asset has ever reported a location. Guarding on
        `asset_id in self._assets` silently dropped every authorisation loaded
        at startup, leaving allowed_zones empty and marking every asset a
        VIOLATION — the "violation storm" that bulk-authorise worked around.
        """
        self._asset_auth[asset_id] = (set(allowed_sensors), set(allowed_zones))
        if asset_id in self._assets:
            self._assets[asset_id].allowed_sensors = set(allowed_sensors)
            self._assets[asset_id].allowed_zones   = set(allowed_zones)
            # Authorisations changed — recompute against the current sensor
            health = self._health.get(self._assets[asset_id].current_sensor_id)
            if health:
                self._assets[asset_id].access_status = \
                    self._assets[asset_id].compute_access_status(health)

    # ── Expose health dict (passed to watchdog) ───────────────────────────────
    @property
    def health(self) -> dict[str, SensorHealthState]:
        return self._health

    # ── Lookups ───────────────────────────────────────────────────────────────
    def get_asset(self,  aid: str) -> Optional[AssetState]:       return self._assets.get(aid)
    def get_sensor(self, sid: str) -> Optional[SensorState]:      return self._sensors.get(sid)
    def get_health(self, sid: str) -> Optional[SensorHealthState]:return self._health.get(sid)

    def all_assets(self)  -> list[AssetState]:        return list(self._assets.values())
    def all_sensors(self) -> list[SensorState]:       return list(self._sensors.values())
    def all_health(self)  -> list[SensorHealthState]: return list(self._health.values())

    def assets_in_zone(self,   zone_id:   str) -> list[AssetState]:
        return [a for a in self._assets.values() if a.current_zone_id   == zone_id]
    def assets_in_sensor(self, sensor_id: str) -> list[AssetState]:
        return [a for a in self._assets.values() if a.current_sensor_id == sensor_id]
