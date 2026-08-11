# persistence/postgres.py — PostgreSQL schema + all read/write operations
import json, logging, os
from datetime import datetime
from typing import Optional
import psycopg2, psycopg2.extras
from models.state import (AssetState, SensorState, SensorHealthState,
                           ZoneRegistry, SystemState, SensorStatus, EnvStatus)

logger = logging.getLogger(__name__)
_conn  = None

def get_conn(dsn: str = None):
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(dsn or os.getenv("POSTGRES_DSN","postgresql://localhost/digital_twin"))
        _conn.autocommit = False
    return _conn

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS zones (
    zone_id TEXT PRIMARY KEY, name TEXT, description TEXT,
    -- Environmental thresholds for this zone. Sensors inherit these unless
    -- they define their own. NULL means "fall back to the global default".
    temp_warning      DOUBLE PRECISION,
    temp_critical     DOUBLE PRECISION,
    humidity_warning  DOUBLE PRECISION,
    humidity_critical DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS sensors (
    sensor_id TEXT PRIMARY KEY, zone_id TEXT REFERENCES zones(zone_id),
    grid_row INT, grid_col INT, installed_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY, asset_type TEXT NOT NULL, name TEXT, created_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS authorisations (
    asset_id TEXT REFERENCES assets(asset_id), allowed_type TEXT NOT NULL, allowed_id TEXT NOT NULL,
    PRIMARY KEY (asset_id, allowed_type, allowed_id));
CREATE TABLE IF NOT EXISTS location_events (
    id BIGSERIAL PRIMARY KEY, asset_id TEXT REFERENCES assets(asset_id),
    sensor_id TEXT, zone_id TEXT, previous_sensor_id TEXT, previous_zone_id TEXT,
    access_status TEXT, timestamp TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS env_readings (
    id BIGSERIAL PRIMARY KEY, sensor_id TEXT, zone_id TEXT,
    reading_type TEXT NOT NULL, value DOUBLE PRECISION, env_status TEXT,
    timestamp TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS sensor_health_events (
    id BIGSERIAL PRIMARY KEY, sensor_id TEXT, zone_id TEXT,
    status TEXT NOT NULL, consecutive_failures INT, timestamp TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY, event_type TEXT NOT NULL, level TEXT NOT NULL,
    sensor_id TEXT, zone_id TEXT, asset_id TEXT, action TEXT, message TEXT,
    payload JSONB, timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS system_snapshots (
    id BIGSERIAL PRIMARY KEY, overall_status TEXT NOT NULL,
    sensors_online INT, sensors_degraded INT, sensors_offline INT,
    zones_normal INT, zones_warning INT, zones_critical INT,
    access_violations INT, unknown_locations INT,
    payload JSONB, timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE INDEX IF NOT EXISTS idx_env_readings_sensor_ts  ON env_readings    (sensor_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_location_events_asset_ts ON location_events (asset_id,  timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_level_ts          ON events          (level,      timestamp DESC);

-- ── Configuration tables (used by the Configuration page) ────────────────────
CREATE TABLE IF NOT EXISTS factory_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Default trajectory: ordered list of sensors an asset is supposed to work at
-- Trajectories are versioned. The operator sets an INITIAL route at
-- configuration time; the AI layer periodically learns an updated one from
-- observed movement. Both are kept so the learned route can be compared with,
-- or reverted to, the original.
CREATE TABLE IF NOT EXISTS asset_trajectory (
    asset_id   TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
    seq        INT  NOT NULL,
    sensor_id  TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'configured',   -- 'configured' | 'learned'
    version    INT  NOT NULL DEFAULT 1,
    confidence DOUBLE PRECISION DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (asset_id, source, version, seq)
);

-- One row per asset naming which trajectory version is currently active
CREATE TABLE IF NOT EXISTS asset_trajectory_active (
    asset_id   TEXT PRIMARY KEY REFERENCES assets(asset_id) ON DELETE CASCADE,
    source     TEXT NOT NULL DEFAULT 'configured',
    version    INT  NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_traj_asset_src
    ON asset_trajectory (asset_id, source, version, seq);

-- Working station: the SET of sensors an asset actually works at, as opposed
-- to asset_trajectory which is the ORDERED route walked between them.
-- A worker is assigned to a station (a machine and the cells around it); the
-- trajectory is how they move across stations. Unordered by design — `weight`
-- carries how much of the asset's time is spent at that cell (0..1), so the
-- station is "where it works most of the time" rather than a bare list.
-- Versioned exactly like asset_trajectory: the operator sets an INITIAL set,
-- and model ⑤ learns an updated one from observed dwell. The operator's
-- 'configured' v1 is never deleted.
CREATE TABLE IF NOT EXISTS asset_station (
    asset_id   TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
    sensor_id  TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'configured',   -- 'configured' | 'learned'
    version    INT  NOT NULL DEFAULT 1,
    weight     DOUBLE PRECISION DEFAULT 1.0,   -- share of dwell time at this cell
    confidence DOUBLE PRECISION DEFAULT 1.0,   -- confidence in the version as a whole
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (asset_id, source, version, sensor_id)
);

-- One row per asset naming which station version is currently active
CREATE TABLE IF NOT EXISTS asset_station_active (
    asset_id   TEXT PRIMARY KEY REFERENCES assets(asset_id) ON DELETE CASCADE,
    source     TEXT NOT NULL DEFAULT 'configured',
    version    INT  NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_station_asset_src
    ON asset_station (asset_id, source, version);

CREATE TABLE IF NOT EXISTS sensor_config (
    sensor_id     TEXT PRIMARY KEY REFERENCES sensors(sensor_id) ON DELETE CASCADE,
    coverage_type TEXT    NOT NULL DEFAULT 'passage',
    passable      BOOLEAN NOT NULL DEFAULT TRUE,
    description   TEXT             DEFAULT '',
    -- Sensor-level thresholds. NULL = inherit from the zone, which in turn
    -- falls back to the global default. Resolution order:
    --     sensor_config → zones → global env defaults
    temp_warning      DOUBLE PRECISION,
    temp_critical     DOUBLE PRECISION,
    humidity_warning  DOUBLE PRECISION,
    humidity_critical DOUBLE PRECISION
);

"""

DEFAULT_CONFIG_SQL = """
INSERT INTO factory_config (key, value) VALUES
  ('factory_name',  ''),
  ('blueprint_url', ''),
  ('grid_cols',     '0'),
  ('grid_rows',     '0'),
  ('temp_warning',      '50'),
  ('temp_critical',     '60'),
  ('humidity_warning',  '70'),
  ('humidity_critical', '85')
ON CONFLICT (key) DO NOTHING;
"""

def create_schema(dsn: str = None):
    conn = get_conn(dsn)
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLES)
        cur.execute(DEFAULT_CONFIG_SQL)
    conn.commit()
    logger.info("Schema ready.")

def load_zone_registry() -> ZoneRegistry:
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT sensor_id, zone_id FROM sensors")
        rows = cur.fetchall()
    return ZoneRegistry({r["sensor_id"]: r["zone_id"] for r in rows})

def load_authorisations() -> dict[str, tuple[set, set]]:
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT asset_id, allowed_type, allowed_id FROM authorisations")
        rows = cur.fetchall()
    result: dict[str, tuple[set, set]] = {}
    for r in rows:
        sensors, zones = result.setdefault(r["asset_id"], (set(), set()))
        if r["allowed_type"] == "sensor": sensors.add(r["allowed_id"])
        else:                             zones.add(r["allowed_id"])
    return result

def load_asset_meta() -> dict[str, dict]:
    """asset_id → {name, asset_type} for display purposes."""
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT asset_id, name, asset_type FROM assets")
        rows = cur.fetchall()
    return {r["asset_id"]: {"name": r["name"] or r["asset_id"],
                            "asset_type": r["asset_type"]} for r in rows}


def load_active_stations() -> dict[str, dict[str, float]]:
    """
    asset_id → {sensor_id: weight} for the station version currently in force.

    Assets with no station configured are simply absent from the result.
    """
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT s.asset_id, s.sensor_id, s.weight
            FROM asset_station s
            JOIN asset_station_active a
              ON a.asset_id = s.asset_id
             AND a.source   = s.source
             AND a.version  = s.version
        """)
        rows = cur.fetchall()
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        out.setdefault(r["asset_id"], {})[r["sensor_id"]] = (
            float(r["weight"]) if r["weight"] is not None else 1.0)
    return out


def save_location_event(asset: AssetState):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO location_events
            (asset_id,sensor_id,zone_id,previous_sensor_id,previous_zone_id,access_status,timestamp)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (asset.id, asset.current_sensor_id, asset.current_zone_id,
             asset.previous_sensor_id, asset.previous_zone_id,
             asset.access_status, asset.time_change_location or datetime.utcnow()))
    conn.commit()

def save_env_reading(sensor: SensorState, reading_type: str, value):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO env_readings
            (sensor_id,zone_id,reading_type,value,env_status,timestamp)
            VALUES (%s,%s,%s,%s,%s,%s)""",
            (sensor.sensor_id, sensor.zone_id, reading_type,
             float(value) if reading_type!="smoke" else None,
             sensor.env_status, sensor.last_time_change))
    conn.commit()

def save_sensor_health_event(health: SensorHealthState):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO sensor_health_events
            (sensor_id,zone_id,status,consecutive_failures,timestamp) VALUES (%s,%s,%s,%s,%s)""",
            (health.sensor_id, health.zone_id, health.status,
             health.consecutive_failures, datetime.utcnow()))
    conn.commit()

def save_event(event: dict):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO events
            (event_type,level,sensor_id,zone_id,asset_id,action,message,payload,timestamp)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (event.get("type"), event.get("level","info"), event.get("sensor_id"),
             event.get("zone_id"), event.get("asset_id"), event.get("action"),
             event.get("message"), json.dumps(event),
             event.get("timestamp", datetime.utcnow().isoformat())))
    conn.commit()

def save_system_snapshot(state: SystemState):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO system_snapshots
            (overall_status,sensors_online,sensors_degraded,sensors_offline,
             zones_normal,zones_warning,zones_critical,access_violations,unknown_locations,payload,timestamp)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (state.overall_status, state.sensors_online, state.sensors_degraded,
             state.sensors_offline, state.zones_normal, state.zones_warning,
             state.zones_critical, state.access_violations, state.unknown_locations,
             json.dumps(state.to_dict()), state.timestamp))
    conn.commit()

def load_sensor_history(sensor_id: str, limit: int = 20) -> list[dict]:
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""SELECT reading_type,value,env_status,timestamp FROM env_readings
            WHERE sensor_id=%s ORDER BY timestamp DESC LIMIT %s""", (sensor_id, limit))
        rows = cur.fetchall()
    return [dict(r) for r in reversed(rows)]
