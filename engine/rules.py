# engine/rules.py — access control, if-else scenarios, trend prediction
from datetime import datetime
from models.state import AssetState, SensorState, AccessStatus

SCENARIOS = [
    {"id":"smoke_detected",      "condition":lambda s,_: s.smoke,
     "level":"critical","type":"smoke_detected","message":lambda s,_: f"Smoke in zone {s.zone_id} sensor {s.sensor_id}","action":"evacuate_zone"},
    {"id":"high_temperature",    "condition":lambda s,_: (s.temperature or 0)>60,
     "level":"critical","type":"high_temperature","message":lambda s,_: f"Temp {s.temperature:.1f}°C in zone {s.zone_id}","action":"inspect_zone"},
    {"id":"temperature_warning", "condition":lambda s,_: 50<(s.temperature or 0)<=60,
     "level":"warning", "type":"temperature_warning","message":lambda s,_: f"Elevated temp {s.temperature:.1f}°C zone {s.zone_id}","action":"monitor_zone"},
    {"id":"high_humidity",       "condition":lambda s,_: (s.humidity or 0)>85,
     "level":"warning", "type":"high_humidity","message":lambda s,_: f"Humidity {s.humidity:.1f}% zone {s.zone_id}","action":"check_ventilation"},
    {"id":"workers_in_smoke",    "condition":lambda s,a: s.smoke and len(a)>0,
     "level":"critical","type":"workers_in_danger","message":lambda s,a: f"{len(a)} asset(s) in zone {s.zone_id} with smoke: {[x.name or x.id for x in a]}","action":"emergency_alert"},
    {"id":"workers_high_temp",   "condition":lambda s,a: (s.temperature or 0)>60 and len(a)>0,
     "level":"critical","type":"workers_in_high_temp","message":lambda s,a: f"{len(a)} asset(s) in zone {s.zone_id} at {s.temperature:.1f}°C","action":"emergency_alert"},
]

def check_access(asset: AssetState) -> dict | None:
    if asset.access_status == AccessStatus.VIOLATION and asset.has_changed_sensor():
        return {"type":"access_violation","level":"critical","asset_id":asset.id,
                "asset_type":asset.asset_type,"sensor_id":asset.current_sensor_id,
                "zone_id":asset.current_zone_id,"previous_zone_id":asset.previous_zone_id,
                "message":f"{asset.name or asset.id} ({asset.asset_type}) entered unauthorised zone {asset.current_zone_id} / sensor {asset.current_sensor_id}",
                "action":"alert_security","timestamp":datetime.utcnow().isoformat()}
    return None

def evaluate_scenarios(sensor: SensorState, assets: list) -> list[dict]:
    out = []
    for sc in SCENARIOS:
        if sc["condition"](sensor, assets):
            out.append({"type":sc["type"],"level":sc["level"],"sensor_id":sensor.sensor_id,
                        "zone_id":sensor.zone_id,"message":sc["message"](sensor,assets),
                        "action":sc["action"],"timestamp":datetime.utcnow().isoformat()})
    return out

def predict_critical_states(sensor: SensorState, history: list) -> list[dict]:
    preds = []
    if len(history) < 3: return preds
    temps = [s.temperature for s in history if s.temperature is not None]
    if len(temps) >= 3:
        rate = (temps[-1] - temps[0]) / len(temps)
        if rate > 1.5:
            predicted = temps[-1] + rate * 5
            if predicted > 60:
                preds.append({"type":"predicted_critical_temperature","level":"warning",
                              "sensor_id":sensor.sensor_id,"zone_id":sensor.zone_id,
                              "predicted_value":round(predicted,1),"trend_rate":round(rate,2),
                              "message":f"Temp rising {rate:.1f}°C/reading in zone {sensor.zone_id}. Predicted {predicted:.1f}°C.",
                              "action":"preventive_inspection","timestamp":datetime.utcnow().isoformat()})
    recent_smoke = [s.smoke for s in history[-5:]]
    if any(recent_smoke) and not sensor.smoke:
        preds.append({"type":"intermittent_smoke","level":"warning",
                      "sensor_id":sensor.sensor_id,"zone_id":sensor.zone_id,
                      "message":f"Intermittent smoke in zone {sensor.zone_id} ({sum(recent_smoke)}/5 readings).",
                      "action":"inspect_zone","timestamp":datetime.utcnow().isoformat()})
    hums = [s.humidity for s in history if s.humidity is not None]
    if len(hums) >= 3:
        hr = (hums[-1] - hums[0]) / len(hums)
        if hr > 3.0 and hums[-1] > 60:
            preds.append({"type":"rising_humidity","level":"warning",
                          "sensor_id":sensor.sensor_id,"zone_id":sensor.zone_id,
                          "current_value":hums[-1],"trend_rate":round(hr,2),
                          "message":f"Humidity rising {hr:.1f}%/reading in zone {sensor.zone_id}.",
                          "action":"check_ventilation","timestamp":datetime.utcnow().isoformat()})
    return preds
