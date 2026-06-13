# =============================================================================
# engine/system_state.py
# Digital Twin — Factory Monitoring System
# Recomputes the global SystemState after every state update.
# This is what gets pushed to the frontend over WebSocket on every tick.
# =============================================================================

from datetime import datetime

from models.state import (
    AssetState, SensorState, SensorHealthState,
    SystemState, SystemStatus,
    SensorStatus, EnvStatus, AccessStatus,
)


def compute_system_state(
    assets:  list[AssetState],
    sensors: list[SensorState],
    health:  list[SensorHealthState],
) -> SystemState:
    """
    Aggregates the live state of all assets, sensors, and sensor health into
    a single SystemState snapshot.

    Called after every:
      - Environmental reading update
      - Asset location update
      - Watchdog status transition

    Rules for overall_status:
      CRITICAL  if any sensor is offline, any zone is critical, or any access violation
      DEGRADED  if any sensor is degraded, any zone is warning, or any unknown location
      NOMINAL   otherwise
    """

    # ── Sensor health ──────────────────────────────────────────────────────────
    s_online   = [h for h in health if h.status == SensorStatus.ONLINE]
    s_degraded = [h for h in health if h.status == SensorStatus.DEGRADED]
    s_offline  = [h for h in health if h.status == SensorStatus.OFFLINE]
    offline_ids = {h.sensor_id for h in s_offline}

    # ── Environmental ──────────────────────────────────────────────────────────
    # Readings from offline sensors are stale — exclude from status computation
    active_sensors = [s for s in sensors if s.sensor_id not in offline_ids]

    z_normal   = [s for s in active_sensors if s.env_status == EnvStatus.NORMAL]
    z_warning  = [s for s in active_sensors if s.env_status == EnvStatus.WARNING]
    z_critical = [s for s in active_sensors if s.env_status == EnvStatus.CRITICAL]

    # ── Access ─────────────────────────────────────────────────────────────────
    violations = [a for a in assets if a.access_status == AccessStatus.VIOLATION]
    unknown    = [a for a in assets if a.access_status == AccessStatus.UNKNOWN]

    # ── Overall status ─────────────────────────────────────────────────────────
    if z_critical or violations or s_offline:
        overall = SystemStatus.CRITICAL
    elif z_warning or s_degraded or unknown:
        overall = SystemStatus.DEGRADED
    else:
        overall = SystemStatus.NOMINAL

    return SystemState(
        timestamp            = datetime.utcnow(),
        overall_status       = overall,
        sensors_online       = len(s_online),
        sensors_degraded     = len(s_degraded),
        sensors_offline      = len(s_offline),
        offline_sensor_ids   = [h.sensor_id for h in s_offline],
        zones_normal         = len(z_normal),
        zones_warning        = len(z_warning),
        zones_critical       = len(z_critical),
        critical_zone_ids    = [s.sensor_id for s in z_critical],
        total_assets         = len(assets),
        access_violations    = len(violations),
        unknown_locations    = len(unknown),
        violation_asset_ids  = [a.id for a in violations],
    )
