# engine/system_state.py — global system state aggregator
from datetime import datetime
from models.state import (AssetState, SensorState, SensorHealthState,
                           SystemState, SystemStatus, SensorStatus, EnvStatus, AccessStatus)

def compute_system_state(assets: list[AssetState], sensors: list[SensorState],
                          health: list[SensorHealthState]) -> SystemState:
    s_online   = [h for h in health if h.status == SensorStatus.ONLINE]
    s_degraded = [h for h in health if h.status == SensorStatus.DEGRADED]
    s_offline  = [h for h in health if h.status == SensorStatus.OFFLINE]
    offline_ids= {h.sensor_id for h in s_offline}
    active     = [s for s in sensors if s.sensor_id not in offline_ids]
    z_normal   = [s for s in active if s.env_status == EnvStatus.NORMAL]
    z_warning  = [s for s in active if s.env_status == EnvStatus.WARNING]
    z_critical = [s for s in active if s.env_status == EnvStatus.CRITICAL]
    violations = [a for a in assets if a.access_status == AccessStatus.VIOLATION]
    unknown    = [a for a in assets if a.access_status == AccessStatus.UNKNOWN]
    if z_critical or violations or s_offline:
        overall = SystemStatus.CRITICAL
    elif z_warning or s_degraded or unknown:
        overall = SystemStatus.DEGRADED
    else:
        overall = SystemStatus.NOMINAL
    return SystemState(
        timestamp=datetime.utcnow(), overall_status=overall,
        sensors_online=len(s_online), sensors_degraded=len(s_degraded), sensors_offline=len(s_offline),
        offline_sensor_ids=[h.sensor_id for h in s_offline],
        zones_normal=len(z_normal), zones_warning=len(z_warning), zones_critical=len(z_critical),
        critical_zone_ids=[s.sensor_id for s in z_critical],
        total_assets=len(assets), access_violations=len(violations), unknown_locations=len(unknown),
        violation_asset_ids=[a.id for a in violations],
    )
