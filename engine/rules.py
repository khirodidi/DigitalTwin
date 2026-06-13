# =============================================================================
# engine/rules.py
# Digital Twin — Factory Monitoring System
# Three rule modules:
#   1. Access authorisation check
#   2. If-else environmental / safety scenarios
#   3. Predictive default & critical state detection
# =============================================================================

from datetime import datetime
from models.state import AssetState, SensorState, SensorHealthState, AccessStatus


# ─── 1. ACCESS AUTHORISATION ──────────────────────────────────────────────────

def check_access(asset: AssetState) -> dict | None:
    """
    Fires on every location update.
    Returns a violation event dict if the asset entered an unauthorised zone,
    or None if authorised or no zone change occurred.

    Note: UNKNOWN status (offline sensor) is NOT treated as a violation.
    """
    if asset.access_status == AccessStatus.VIOLATION and asset.has_changed_sensor():
        return {
            "type":              "access_violation",
            "level":             "critical",
            "asset_id":          asset.id,
            "asset_type":        asset.asset_type,
            "sensor_id":         asset.current_sensor_id,
            "zone_id":           asset.current_zone_id,
            "previous_zone_id":  asset.previous_zone_id,
            "timestamp":         datetime.utcnow().isoformat(),
            "message": (
                f"{asset.id} ({asset.asset_type}) entered unauthorised "
                f"zone {asset.current_zone_id} / sensor {asset.current_sensor_id}"
            ),
            "action": "alert_security",
        }
    return None


# ─── 2. IF-ELSE SCENARIOS ─────────────────────────────────────────────────────
#
# Each scenario is a dict with:
#   condition : callable(SensorState, list[AssetState]) → bool
#   level     : 'warning' | 'critical'
#   type      : event type string
#   message   : callable(SensorState, list[AssetState]) → str
#   action    : suggested system action

SCENARIOS: list[dict] = [
    {
        "id":        "smoke_detected",
        "condition": lambda s, _assets: s.smoke,
        "level":     "critical",
        "type":      "smoke_detected",
        "message":   lambda s, _: f"Smoke detected in zone {s.zone_id} (sensor {s.sensor_id})",
        "action":    "evacuate_zone",
    },
    {
        "id":        "high_temperature",
        "condition": lambda s, _: s.temperature is not None and s.temperature > 60,
        "level":     "critical",
        "type":      "high_temperature",
        "message":   lambda s, _: f"Critical temperature {s.temperature}°C in zone {s.zone_id}",
        "action":    "inspect_zone",
    },
    {
        "id":        "temperature_warning",
        "condition": lambda s, _: s.temperature is not None and 50 < s.temperature <= 60,
        "level":     "warning",
        "type":      "temperature_warning",
        "message":   lambda s, _: f"Elevated temperature {s.temperature}°C in zone {s.zone_id}",
        "action":    "monitor_zone",
    },
    {
        "id":        "high_humidity",
        "condition": lambda s, _: s.humidity is not None and s.humidity > 85,
        "level":     "warning",
        "type":      "high_humidity",
        "message":   lambda s, _: f"High humidity {s.humidity}% in zone {s.zone_id}",
        "action":    "check_ventilation",
    },
    {
        "id":        "workers_in_smoke_zone",
        "condition": lambda s, assets: s.smoke and len(assets) > 0,
        "level":     "critical",
        "type":      "workers_in_danger",
        "message":   lambda s, assets: (
            f"{len(assets)} asset(s) in zone {s.zone_id} with active smoke alert: "
            f"{[a.id for a in assets]}"
        ),
        "action":    "emergency_alert",
    },
    {
        "id":        "workers_in_critical_temp_zone",
        "condition": lambda s, assets: (
            s.temperature is not None and s.temperature > 60 and len(assets) > 0
        ),
        "level":     "critical",
        "type":      "workers_in_high_temp_zone",
        "message":   lambda s, assets: (
            f"{len(assets)} asset(s) in zone {s.zone_id} at {s.temperature}°C: "
            f"{[a.id for a in assets]}"
        ),
        "action":    "emergency_alert",
    },
]


def evaluate_scenarios(
    sensor: SensorState,
    assets_in_zone: list[AssetState],
) -> list[dict]:
    """
    Evaluate all if-else scenarios against the current sensor state and
    the assets currently in the sensor's zone.
    Returns a list of triggered event dicts.
    """
    events = []
    for scenario in SCENARIOS:
        if scenario["condition"](sensor, assets_in_zone):
            events.append({
                "type":      scenario["type"],
                "level":     scenario["level"],
                "sensor_id": sensor.sensor_id,
                "zone_id":   sensor.zone_id,
                "message":   scenario["message"](sensor, assets_in_zone),
                "action":    scenario["action"],
                "timestamp": datetime.utcnow().isoformat(),
            })
    return events


# ─── 3. PREDICTION — DEFAULT & CRITICAL STATES ────────────────────────────────

def predict_critical_states(
    sensor:  SensorState,
    history: list[SensorState],   # ordered oldest → newest, max 20 readings
) -> list[dict]:
    """
    Trend-based prediction on recent sensor history.
    Detects:
      - Rising temperature trending toward critical threshold
      - Intermittent smoke (appeared in recent history but not currently active)
      - Rapid humidity increase

    Replace with an ML model when sufficient historical data is available.
    """
    predictions = []

    if len(history) < 3:
        return predictions

    # ── Temperature trend ─────────────────────────────────────────────────────
    temps = [s.temperature for s in history if s.temperature is not None]
    if len(temps) >= 3:
        rate = (temps[-1] - temps[0]) / len(temps)     # °C per reading interval
        if rate > 1.5:                                  # rising fast
            predicted = temps[-1] + rate * 5            # 5 readings ahead
            if predicted > 60:
                predictions.append({
                    "type":            "predicted_critical_temperature",
                    "level":           "warning",
                    "sensor_id":       sensor.sensor_id,
                    "zone_id":         sensor.zone_id,
                    "current_value":   temps[-1],
                    "predicted_value": round(predicted, 1),
                    "trend_rate":      round(rate, 2),
                    "message": (
                        f"Temperature rising at {rate:.1f}°C/reading in zone {sensor.zone_id}. "
                        f"Predicted {predicted:.1f}°C — critical threshold may be reached soon."
                    ),
                    "action":    "preventive_inspection",
                    "timestamp": datetime.utcnow().isoformat(),
                })

    # ── Intermittent smoke ────────────────────────────────────────────────────
    recent_smoke = [s.smoke for s in history[-5:]]
    if any(recent_smoke) and not sensor.smoke:
        predictions.append({
            "type":      "intermittent_smoke",
            "level":     "warning",
            "sensor_id": sensor.sensor_id,
            "zone_id":   sensor.zone_id,
            "message": (
                f"Intermittent smoke detected in zone {sensor.zone_id} "
                f"({sum(recent_smoke)}/5 recent readings) — monitor closely."
            ),
            "action":    "inspect_zone",
            "timestamp": datetime.utcnow().isoformat(),
        })

    # ── Rapid humidity increase ───────────────────────────────────────────────
    hums = [s.humidity for s in history if s.humidity is not None]
    if len(hums) >= 3:
        hum_rate = (hums[-1] - hums[0]) / len(hums)
        if hum_rate > 3.0 and hums[-1] > 60:
            predictions.append({
                "type":            "rising_humidity",
                "level":           "warning",
                "sensor_id":       sensor.sensor_id,
                "zone_id":         sensor.zone_id,
                "current_value":   hums[-1],
                "trend_rate":      round(hum_rate, 2),
                "message": (
                    f"Humidity rising at {hum_rate:.1f}%/reading in zone {sensor.zone_id}. "
                    f"Current: {hums[-1]:.1f}% — check ventilation."
                ),
                "action":    "check_ventilation",
                "timestamp": datetime.utcnow().isoformat(),
            })

    return predictions
