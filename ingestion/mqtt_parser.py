# =============================================================================
# ingestion/mqtt_parser.py
# Digital Twin — Factory Monitoring System
# Parses raw WSN payloads from the mother station into structured dicts.
# =============================================================================

from datetime import datetime


# ─── Topic constants ──────────────────────────────────────────────────────────
TOPIC_ENV      = "wsn/env"         # environmental readings
TOPIC_LOCATION = "wsn/location"    # asset localisation


# ─── Parsers ──────────────────────────────────────────────────────────────────

def parse_env_message(raw: list) -> dict:
    """
    WSN environmental message format:
        ['sensor_id', 'temperature|humidity|smoke', value, timestamp]

    Returns a dict ready to be passed to StateStore.update_sensor_reading().

    Examples:
        ['S3', 'temperature', 47.2, '2026-05-17T10:23:00Z']
        ['S3', 'humidity',    61.0, '2026-05-17T10:23:01Z']
        ['S3', 'smoke',       True, '2026-05-17T10:23:02Z']
    """
    if len(raw) != 4:
        raise ValueError(f"Invalid env message length: expected 4, got {len(raw)}: {raw}")

    sensor_id, reading_type, value, ts = raw

    if reading_type not in ("temperature", "humidity", "smoke"):
        raise ValueError(f"Unknown reading_type '{reading_type}' in: {raw}")

    return {
        "sensor_id":    str(sensor_id),
        "reading_type": reading_type,
        "value":        float(value) if reading_type != "smoke" else bool(value),
        "timestamp":    _parse_ts(ts),
    }


def parse_location_message(raw: list) -> dict:
    """
    WSN localisation message format:
        ['worker_id|object_id', 'sensor_id', timestamp]

    Returns a dict ready to be passed to StateStore.update_asset_location().
    current_location = sensor_id of the cell the asset is currently in.

    Examples:
        ['W1',  'S6', '2026-05-17T10:23:00Z']
        ['F1',  'S9', '2026-05-17T10:23:00Z']
    """
    if len(raw) != 3:
        raise ValueError(f"Invalid location message length: expected 3, got {len(raw)}: {raw}")

    asset_id, sensor_id, ts = raw

    return {
        "asset_id":  str(asset_id),
        "sensor_id": str(sensor_id),
        "timestamp": _parse_ts(ts),
    }


def route_message(topic: str, payload: list) -> tuple[str, dict]:
    """
    Routes an incoming MQTT message to the correct parser.
    Returns (message_type, parsed_dict).
    message_type is one of: 'env' | 'location'
    """
    if topic == TOPIC_ENV:
        return "env", parse_env_message(payload)
    elif topic == TOPIC_LOCATION:
        return "location", parse_location_message(payload)
    else:
        raise ValueError(f"Unknown MQTT topic: {topic}")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_ts(ts) -> datetime:
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
