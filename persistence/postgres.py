# =============================================================================
# persistence/postgres.py
# Digital Twin — Factory Monitoring System
# All database read/write operations.
# Uses psycopg2 (sync) for simplicity; swap for asyncpg for async I/O.
# =============================================================================

import json
import logging
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras

from models.state import (
    AssetState, SensorState, SensorHealthState,
    ZoneRegistry, SystemState, SensorStatus, EnvStatus, AccessStatus,
)

logger = logging.getLogger(__name__)

# ─── Connection ───────────────────────────────────────────────────────────────

_conn = None

def get_conn(dsn: str = "postgresql://localhost/digital_twin"):
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(dsn)
        _conn.autocommit = False
    return _conn


# ─── Schema creation ──────────────────────────────────────────────────────────

CREATE_TABLES = """
-- Zone registry: static factory grid topology
CREATE TABLE IF NOT EXISTS zones (
    zone_id     TEXT PRIMARY KEY,
    name        TEXT,
    description TEXT
);

-- Sensor registry: one row per grid cell
CREATE TABLE IF NOT EXISTS sensors (
    sensor_id   TEXT PRIMARY KEY,
    zone_id     TEXT REFERENCES zones(zone_id),
    grid_row    INT,                  -- grid position row
    grid_col    INT,                  -- grid position column
    installed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Asset registry: workers and mobile objects
CREATE TABLE IF NOT EXISTS assets (
    asset_id    TEXT PRIMARY KEY,
    asset_type  TEXT NOT NULL,        -- 'worker' | 'object'
    name        TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Authorisations: allowed sensor_ids and zone_ids per asset
CREATE TABLE IF NOT EXISTS authorisations (
    asset_id        TEXT REFERENCES assets(asset_id),
    allowed_type    TEXT NOT NULL,    -- 'sensor' | 'zone'
    allowed_id      TEXT NOT NULL,    -- sensor_id or zone_id
    PRIMARY KEY (asset_id, allowed_type, allowed_id)
);

-- Asset location events: every zone/sensor change
CREATE TABLE IF NOT EXISTS location_events (
    id                  BIGSERIAL PRIMARY KEY,
    asset_id            TEXT REFERENCES assets(asset_id),
    sensor_id           TEXT REFERENCES sensors(sensor_id),
    zone_id             TEXT REFERENCES zones(zone_id),
    previous_sensor_id  TEXT,
    previous_zone_id    TEXT,
    access_status       TEXT,
    timestamp           TIMESTAMPTZ NOT NULL
);

-- Environmental readings: raw time-series
CREATE TABLE IF NOT EXISTS env_readings (
    id           BIGSERIAL PRIMARY KEY,
    sensor_id    TEXT REFERENCES sensors(sensor_id),
    zone_id      TEXT,
    reading_type TEXT NOT NULL,       -- 'temperature' | 'humidity' | 'smoke'
    value        DOUBLE PRECISION,
    env_status   TEXT,
    timestamp    TIMESTAMPTZ NOT NULL
);

-- Sensor health events: status transitions
CREATE TABLE IF NOT EXISTS sensor_health_events (
    id                  BIGSERIAL PRIMARY KEY,
    sensor_id           TEXT REFERENCES sensors(sensor_id),
    zone_id             TEXT,
    status              TEXT NOT NULL,
    consecutive_failures INT,
    timestamp           TIMESTAMPTZ NOT NULL
);

-- Alert / event log: all triggered rules, scenarios, predictions
CREATE TABLE IF NOT EXISTS events (
    id          BIGSERIAL PRIMARY KEY,
    event_type  TEXT NOT NULL,
    level       TEXT NOT NULL,        -- 'info' | 'warning' | 'critical'
    sensor_id   TEXT,
    zone_id     TEXT,
    asset_id    TEXT,
    action      TEXT,
    message     TEXT,
    payload     JSONB,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- System state snapshots: global state at each tick
CREATE TABLE IF NOT EXISTS system_snapshots (
    id               BIGSERIAL PRIMARY KEY,
    overall_status   TEXT NOT NULL,
    sensors_online   INT,
    sensors_degraded INT,
    sensors_offline  INT,
    zones_normal     INT,
    zones_warning    INT,
    zones_critical   INT,
    access_violations INT,
    unknown_locations INT,
    payload          JSONB,
    timestamp        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for time-series queries
CREATE INDEX IF NOT EXISTS idx_env_readings_sensor_ts    ON env_readings    (sensor_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_location_events_asset_ts  ON location_events (asset_id,  timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_level_ts           ON events          (level,      timestamp DESC);
"""

def create_schema(dsn: str):
    conn = get_conn(dsn)
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLES)
    conn.commit()
    logger.info("Schema created / verified.")


# ─── Zone registry loader ─────────────────────────────────────────────────────

def load_zone_registry() -> ZoneRegistry:
    """Load the sensor → zone mapping from the database at startup."""
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT sensor_id, zone_id FROM sensors;")
        rows = cur.fetchall()
    mapping = {row["sensor_id"]: row["zone_id"] for row in rows}
    return ZoneRegistry(mapping)


# ─── Asset authorisation loader ───────────────────────────────────────────────

def load_authorisations() -> dict[str, tuple[set, set]]:
    """
    Returns { asset_id: (allowed_sensors, allowed_zones) } for all assets.
    Called at startup to populate StateStore.
    """
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT asset_id, allowed_type, allowed_id FROM authorisations;")
        rows = cur.fetchall()

    result: dict[str, tuple[set, set]] = {}
    for row in rows:
        sensors, zones = result.setdefault(row["asset_id"], (set(), set()))
        if row["allowed_type"] == "sensor":
            sensors.add(row["allowed_id"])
        elif row["allowed_type"] == "zone":
            zones.add(row["allowed_id"])
    return result


# ─── Persistence writers ──────────────────────────────────────────────────────

def save_location_event(asset: AssetState):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO location_events
              (asset_id, sensor_id, zone_id, previous_sensor_id,
               previous_zone_id, access_status, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            asset.id,
            asset.current_sensor_id,
            asset.current_zone_id,
            asset.previous_sensor_id,
            asset.previous_zone_id,
            asset.access_status,
            asset.time_change_location or datetime.utcnow(),
        ))
    conn.commit()


def save_env_reading(sensor: SensorState, reading_type: str, value):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO env_readings
              (sensor_id, zone_id, reading_type, value, env_status, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            sensor.sensor_id,
            sensor.zone_id,
            reading_type,
            float(value) if reading_type != "smoke" else None,
            sensor.env_status,
            sensor.last_time_change,
        ))
    conn.commit()


def save_sensor_health_event(health: SensorHealthState):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO sensor_health_events
              (sensor_id, zone_id, status, consecutive_failures, timestamp)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            health.sensor_id,
            health.zone_id,
            health.status,
            health.consecutive_failures,
            datetime.utcnow(),
        ))
    conn.commit()


def save_event(event: dict):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO events
              (event_type, level, sensor_id, zone_id, asset_id,
               action, message, payload, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            event.get("type"),
            event.get("level", "info"),
            event.get("sensor_id"),
            event.get("zone_id"),
            event.get("asset_id"),
            event.get("action"),
            event.get("message"),
            json.dumps(event),
            event.get("timestamp", datetime.utcnow().isoformat()),
        ))
    conn.commit()


def save_system_snapshot(state: SystemState):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO system_snapshots
              (overall_status, sensors_online, sensors_degraded, sensors_offline,
               zones_normal, zones_warning, zones_critical,
               access_violations, unknown_locations, payload, timestamp)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            state.overall_status,
            state.sensors_online,
            state.sensors_degraded,
            state.sensors_offline,
            state.zones_normal,
            state.zones_warning,
            state.zones_critical,
            state.access_violations,
            state.unknown_locations,
            json.dumps(state.to_dict()),
            state.timestamp,
        ))
    conn.commit()


# ─── History reader (for prediction) ─────────────────────────────────────────

def load_sensor_history(sensor_id: str, limit: int = 20) -> list[dict]:
    """Load the last N env readings for a sensor (for the prediction module)."""
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT reading_type, value, env_status, timestamp
            FROM   env_readings
            WHERE  sensor_id = %s
            ORDER  BY timestamp DESC
            LIMIT  %s
        """, (sensor_id, limit))
        rows = cur.fetchall()
    return [dict(r) for r in reversed(rows)]   # oldest first
