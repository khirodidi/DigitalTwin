# ingestion/mqtt_parser.py — parse WSN messages from the mother station
from datetime import datetime

TOPIC_ENV      = "wsn/env"
TOPIC_LOCATION = "wsn/location"

def parse_env_message(raw: list) -> dict:
    """['sensor_id','temperature|humidity|smoke', value, timestamp]"""
    if len(raw) != 4:
        raise ValueError(f"Invalid env message length: {len(raw)}: {raw}")
    sensor_id, reading_type, value, ts = raw
    if reading_type not in ("temperature","humidity","smoke"):
        raise ValueError(f"Unknown reading_type '{reading_type}'")
    return {"sensor_id":str(sensor_id),"reading_type":reading_type,
            "value":float(value) if reading_type!="smoke" else bool(value),
            "timestamp":_parse_ts(ts)}

def parse_location_message(raw: list) -> dict:
    """['worker_id|object_id','sensor_id', timestamp]"""
    if len(raw) != 3:
        raise ValueError(f"Invalid location message length: {len(raw)}: {raw}")
    asset_id, sensor_id, ts = raw
    return {"asset_id":str(asset_id),"sensor_id":str(sensor_id),"timestamp":_parse_ts(ts)}

def route_message(topic: str, payload: list) -> tuple[str, dict]:
    if topic == TOPIC_ENV:      return "env",      parse_env_message(payload)
    if topic == TOPIC_LOCATION: return "location", parse_location_message(payload)
    raise ValueError(f"Unknown MQTT topic: {topic}")

def _parse_ts(ts) -> datetime:
    if isinstance(ts, datetime): return ts
    return datetime.fromisoformat(str(ts).replace("Z","+00:00"))
