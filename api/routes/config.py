# =============================================================================
# api/routes/config.py
# Configuration endpoints — factory layout, sensor metadata, worker management.
# All settings are persisted to PostgreSQL so they survive restarts.
# =============================================================================

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import psycopg2.extras
from persistence.postgres import get_conn

router = APIRouter()


# ─── Pydantic models ──────────────────────────────────────────────────────────

class FactoryConfig(BaseModel):
    factory_name:  Optional[str] = None
    blueprint_url: Optional[str] = None   # filename in frontend/public/
    grid_cols:     Optional[int] = None
    grid_rows:     Optional[int] = None

class ZoneBody(BaseModel):
    zone_id:     str
    name:        str
    description: Optional[str] = ""
    sensor_ids:  list[str] = []           # sensors belonging to this zone

class SensorConfigBody(BaseModel):
    coverage_type: str = "passage"        # 'passage' | 'machine' | 'storage' | 'exit'
    passable:      bool = True            # can workers physically walk through?
    description:   Optional[str] = ""

class WorkerBody(BaseModel):
    asset_id:   str
    asset_type: str = "worker"            # 'worker' | 'forklift' | 'pallet'
    name:       str

class AuthBody(BaseModel):
    allowed_zones:   list[str] = []
    allowed_sensors: list[str] = []


# ─── Factory global config ────────────────────────────────────────────────────

@router.get("/factory")
def get_factory_config():
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT key, value FROM factory_config")
        rows = cur.fetchall()
    return {r["key"]: r["value"] for r in rows}


@router.put("/factory")
def update_factory_config(body: FactoryConfig):
    conn = get_conn()
    updates = {k: v for k, v in body.dict().items() if v is not None}
    with conn.cursor() as cur:
        for key, val in updates.items():
            cur.execute("""
                INSERT INTO factory_config (key, value)
                VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """, (key, str(val)))
    conn.commit()
    return {"status": "updated", "keys": list(updates.keys())}


# ─── Zone management ──────────────────────────────────────────────────────────

@router.get("/zones")
def get_zones():
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT z.zone_id, z.name, z.description,
                   COALESCE(array_agg(s.sensor_id) FILTER (WHERE s.sensor_id IS NOT NULL), '{}') AS sensor_ids
            FROM zones z
            LEFT JOIN sensors s ON s.zone_id = z.zone_id
            GROUP BY z.zone_id, z.name, z.description
            ORDER BY z.zone_id
        """)
        return cur.fetchall()


@router.post("/zones")
def create_zone(body: ZoneBody):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO zones (zone_id, name, description)
            VALUES (%s, %s, %s)
            ON CONFLICT (zone_id) DO UPDATE
              SET name=EXCLUDED.name, description=EXCLUDED.description
        """, (body.zone_id, body.name, body.description))
        # Re-assign sensors to this zone
        if body.sensor_ids:
            cur.execute("UPDATE sensors SET zone_id = %s WHERE sensor_id = ANY(%s)",
                        (body.zone_id, body.sensor_ids))
    conn.commit()
    return {"status": "saved", "zone_id": body.zone_id}


@router.delete("/zones/{zone_id}")
def delete_zone(zone_id: str):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("UPDATE sensors SET zone_id = NULL WHERE zone_id = %s", (zone_id,))
        cur.execute("DELETE FROM zones WHERE zone_id = %s", (zone_id,))
    conn.commit()
    return {"status": "deleted"}


# ─── Sensor metadata ──────────────────────────────────────────────────────────

@router.get("/sensors")
def get_sensors_config():
    """Return all sensors with their coverage metadata."""
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT s.sensor_id, s.zone_id, s.grid_row, s.grid_col,
                   COALESCE(sc.coverage_type, 'passage') AS coverage_type,
                   COALESCE(sc.passable,       TRUE)     AS passable,
                   COALESCE(sc.description,    '')       AS description
            FROM sensors s
            LEFT JOIN sensor_config sc USING (sensor_id)
            ORDER BY s.grid_row, s.grid_col
        """)
        return cur.fetchall()


@router.put("/sensors/{sensor_id}")
def update_sensor_config(sensor_id: str, body: SensorConfigBody):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO sensor_config (sensor_id, coverage_type, passable, description)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (sensor_id) DO UPDATE
              SET coverage_type = EXCLUDED.coverage_type,
                  passable      = EXCLUDED.passable,
                  description   = EXCLUDED.description
        """, (sensor_id, body.coverage_type, body.passable, body.description))
    conn.commit()
    return {"status": "updated", "sensor_id": sensor_id}


# ─── Worker / asset management ────────────────────────────────────────────────

@router.get("/workers")
def get_workers():
    """Return all assets with their authorisations."""
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT a.asset_id, a.asset_type, a.name,
                   COALESCE(
                     json_agg(json_build_object(
                       'type', au.allowed_type, 'id', au.allowed_id
                     )) FILTER (WHERE au.allowed_id IS NOT NULL),
                     '[]'
                   ) AS authorisations
            FROM assets a
            LEFT JOIN authorisations au USING (asset_id)
            GROUP BY a.asset_id, a.asset_type, a.name
            ORDER BY a.asset_type, a.asset_id
        """)
        return cur.fetchall()


@router.post("/workers")
def create_worker(body: WorkerBody):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO assets (asset_id, asset_type, name)
            VALUES (%s, %s, %s)
            ON CONFLICT (asset_id) DO UPDATE
              SET asset_type=EXCLUDED.asset_type, name=EXCLUDED.name
        """, (body.asset_id, body.asset_type, body.name))
    conn.commit()
    return {"status": "created", "asset_id": body.asset_id}


@router.put("/workers/{asset_id}")
def update_worker(asset_id: str, body: WorkerBody):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("UPDATE assets SET asset_type=%s, name=%s WHERE asset_id=%s",
                    (body.asset_type, body.name, asset_id))
    conn.commit()
    return {"status": "updated"}


@router.delete("/workers/{asset_id}")
def delete_worker(asset_id: str):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM authorisations WHERE asset_id=%s", (asset_id,))
        cur.execute("DELETE FROM assets WHERE asset_id=%s", (asset_id,))
    conn.commit()
    return {"status": "deleted"}


@router.get("/workers/{asset_id}/authorisations")
def get_authorisations(asset_id: str):
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT allowed_type, allowed_id
            FROM authorisations WHERE asset_id=%s
            ORDER BY allowed_type, allowed_id
        """, (asset_id,))
        rows = cur.fetchall()
    zones   = [r["allowed_id"] for r in rows if r["allowed_type"] == "zone"]
    sensors = [r["allowed_id"] for r in rows if r["allowed_type"] == "sensor"]
    return {"asset_id": asset_id, "allowed_zones": zones, "allowed_sensors": sensors}


@router.put("/workers/{asset_id}/authorisations")
def set_authorisations(asset_id: str, body: AuthBody):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM authorisations WHERE asset_id=%s", (asset_id,))
        for z in body.allowed_zones:
            cur.execute("INSERT INTO authorisations VALUES (%s,'zone',%s)",   (asset_id, z))
        for s in body.allowed_sensors:
            cur.execute("INSERT INTO authorisations VALUES (%s,'sensor',%s)", (asset_id, s))
    conn.commit()
    return {"status": "updated",
            "zones": len(body.allowed_zones),
            "sensors": len(body.allowed_sensors)}


# ─── Worker trajectory ────────────────────────────────────────────────────────

@router.get("/workers/{asset_id}/trajectory")
def get_trajectory(asset_id: str, limit: int = 100):
    """
    Return the last N location events for a worker, ordered oldest→newest.
    Used by TrajectoryMap to draw the path on the grid.
    """
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT sensor_id, zone_id, access_status, timestamp
            FROM location_events
            WHERE asset_id = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """, (asset_id, limit))
        rows = cur.fetchall()
    # Reverse so oldest first (for drawing path in order)
    return list(reversed(rows))
