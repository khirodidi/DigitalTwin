# =============================================================================
# api/routes/config.py
# Configuration endpoints — factory layout, blueprint upload, sensors,
# zones (defined by their sensors), workers, authorisations, trajectory.
#
# Every mutating endpoint broadcasts a `config_updated` WebSocket event so the
# monitoring dashboard refreshes immediately without a page reload.
# =============================================================================

import os, shutil, uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
import psycopg2.extras

from persistence.postgres import get_conn

router = APIRouter()

# Where uploaded blueprints are stored inside the backend container.
# Served publicly at /static/blueprints/<filename> (mounted in api/main.py).
BLUEPRINT_DIR = Path(os.getenv("BLUEPRINT_DIR", "/app/static/blueprints"))
BLUEPRINT_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
MAX_BYTES   = 10 * 1024 * 1024   # 10 MB


# ─── Broadcast helper ─────────────────────────────────────────────────────────

async def _notify(section: str, detail: dict = None):
    """
    Push a config_updated event to all connected dashboards so the monitoring
    view reloads the affected part of the configuration immediately.
    """
    try:
        from api.main import ws_manager
        await ws_manager.broadcast("config_updated",
                                   {"section": section, **(detail or {})})
    except Exception:
        pass   # never let a broadcast failure break the API call


# ─── Models ───────────────────────────────────────────────────────────────────

class FactoryConfig(BaseModel):
    factory_name:  Optional[str] = None
    blueprint_url: Optional[str] = None
    grid_cols:     Optional[int] = None
    grid_rows:     Optional[int] = None

class ZoneBody(BaseModel):
    zone_id:     str
    name:        str
    description: Optional[str] = ""
    sensor_ids:  list[str] = []       # zone is DEFINED by these sensors

class SensorConfigBody(BaseModel):
    coverage_type: str  = "passage"
    passable:      bool = True
    description:   Optional[str] = ""

class WorkerBody(BaseModel):
    asset_id:           str
    asset_type:         str = "worker"
    name:               str
    default_trajectory: list[str] = []   # ordered sensors the asset works at

class AuthBody(BaseModel):
    allowed_zones:   list[str] = []
    allowed_sensors: list[str] = []


# ═══════════════════════════════════════════════════════════════════════════════
#  FACTORY CONFIG  (grid size lives here — read at runtime by the frontend)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/factory")
def get_factory_config():
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT key, value FROM factory_config")
        rows = cur.fetchall()
    cfg = {r["key"]: r["value"] for r in rows}
    # Coerce numeric fields so the frontend gets real numbers
    cols = int(cfg.get("grid_cols") or 0)
    rows = int(cfg.get("grid_rows") or 0)
    bp   = cfg.get("blueprint_url", "")
    return {
        "factory_name":  cfg.get("factory_name", ""),
        "blueprint_url": bp,
        "grid_cols":     cols,
        "grid_rows":     rows,
        # Mandatory before the dashboard will render anything
        "configured":    bool(cols > 0 and rows > 0 and bp),
    }


@router.put("/factory")
async def update_factory_config(body: FactoryConfig):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        return {"status": "no changes"}

    # Validate grid bounds
    for key in ("grid_cols", "grid_rows"):
        if key in updates and not (0 <= int(updates[key]) <= 30):
            raise HTTPException(400, f"{key} must be between 1 and 30")

    conn = get_conn()
    with conn.cursor() as cur:
        for key, val in updates.items():
            cur.execute("""
                INSERT INTO factory_config (key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """, (key, str(val)))
    conn.commit()

    # If the grid changed, regenerate the sensor rows to match
    if "grid_cols" in updates or "grid_rows" in updates:
        cur_cfg = get_factory_config()
        _regenerate_sensors(cur_cfg["grid_cols"], cur_cfg["grid_rows"])
        await _notify("grid", {"cols": cur_cfg["grid_cols"], "rows": cur_cfg["grid_rows"]})
    else:
        await _notify("factory")

    return {"status": "updated", "keys": list(updates.keys())}


def _regenerate_sensors(cols: int, rows: int):
    """
    Create sensor rows for an N×M grid.
    Existing sensors keep their zone and config; extra sensors beyond the new
    grid are deleted; missing ones are inserted.
    """
    conn = get_conn()
    wanted = {f"S{r*cols + c + 1:02d}": (r, c)
              for r in range(rows) for c in range(cols)}
    with conn.cursor() as cur:
        cur.execute("SELECT sensor_id FROM sensors")
        existing = {r[0] for r in cur.fetchall()}

        # Delete sensors that fall outside the new grid
        stale = existing - wanted.keys()
        if stale:
            cur.execute("DELETE FROM sensors WHERE sensor_id = ANY(%s)", (list(stale),))

        # Insert or update positions
        for sid, (r, c) in wanted.items():
            cur.execute("""
                INSERT INTO sensors (sensor_id, zone_id, grid_row, grid_col)
                VALUES (%s, NULL, %s, %s)
                ON CONFLICT (sensor_id) DO UPDATE
                  SET grid_row = EXCLUDED.grid_row, grid_col = EXCLUDED.grid_col
            """, (sid, r, c))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════════════════
#  BLUEPRINT UPLOAD
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/factory/blueprint")
async def upload_blueprint(file: UploadFile = File(...)):
    """
    Upload a factory floor plan image.
    Stored in BLUEPRINT_DIR and served at /static/blueprints/<filename>.
    The resulting URL is saved into factory_config.blueprint_url.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400,
            f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXT))}")

    # Fail fast and loudly if the storage directory is not usable, instead of
    # letting the request hang or die mid-write.
    try:
        BLUEPRINT_DIR.mkdir(parents=True, exist_ok=True)
        probe = BLUEPRINT_DIR / ".write_test"
        probe.write_text("ok"); probe.unlink()
    except Exception as e:
        raise HTTPException(500,
            f"Blueprint directory {BLUEPRINT_DIR} is not writable: {e}")

    # Unique filename so browsers don't serve a stale cached image
    fname = f"blueprint_{uuid.uuid4().hex[:10]}{ext}"
    dest  = BLUEPRINT_DIR / fname

    size = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 256)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BYTES:
                    out.close(); dest.unlink(missing_ok=True)
                    raise HTTPException(400,
                        f"File too large ({size/1e6:.1f} MB) — maximum is "
                        f"{MAX_BYTES/1e6:.0f} MB")
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(500, f"Could not save the image: {e}")

    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "The uploaded file was empty")

    url = f"/static/blueprints/{fname}"

    # Remove the previously uploaded blueprint to avoid filling the volume
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT value FROM factory_config WHERE key='blueprint_url'")
        row = cur.fetchone()
        if row and row[0] and row[0].startswith("/static/blueprints/"):
            old = BLUEPRINT_DIR / Path(row[0]).name
            if old.exists() and old != dest:
                old.unlink(missing_ok=True)

        cur.execute("""
            INSERT INTO factory_config (key, value) VALUES ('blueprint_url', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, (url,))
    conn.commit()

    await _notify("blueprint", {"blueprint_url": url})
    return {"status": "uploaded", "blueprint_url": url,
            "filename": fname, "size_bytes": size}


@router.get("/factory/blueprint/status")
def blueprint_status():
    """Diagnostics for upload problems — writability, disk contents, limits."""
    writable, err = True, None
    try:
        BLUEPRINT_DIR.mkdir(parents=True, exist_ok=True)
        probe = BLUEPRINT_DIR / ".write_test"
        probe.write_text("ok"); probe.unlink()
    except Exception as e:
        writable, err = False, str(e)
    files = []
    try:
        files = [f.name for f in BLUEPRINT_DIR.iterdir() if f.is_file()]
    except Exception:
        pass
    return {"directory": str(BLUEPRINT_DIR), "writable": writable,
            "error": err, "files": files,
            "max_bytes": MAX_BYTES,
            "allowed": sorted(ALLOWED_EXT)}


@router.delete("/factory/blueprint")
async def delete_blueprint():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT value FROM factory_config WHERE key='blueprint_url'")
        row = cur.fetchone()
        if row and row[0] and row[0].startswith("/static/blueprints/"):
            f = BLUEPRINT_DIR / Path(row[0]).name
            f.unlink(missing_ok=True)
        cur.execute("""
            INSERT INTO factory_config (key, value) VALUES ('blueprint_url', '')
            ON CONFLICT (key) DO UPDATE SET value = ''
        """)
    conn.commit()
    await _notify("blueprint", {"blueprint_url": ""})
    return {"status": "removed"}


# ═══════════════════════════════════════════════════════════════════════════════
#  ZONES — a zone IS its set of sensors
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/zones")
def get_zones():
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT z.zone_id, z.name, z.description,
                   COALESCE(
                     array_agg(s.sensor_id ORDER BY s.grid_row, s.grid_col)
                     FILTER (WHERE s.sensor_id IS NOT NULL), '{}'
                   ) AS sensor_ids
            FROM zones z
            LEFT JOIN sensors s ON s.zone_id = z.zone_id
            GROUP BY z.zone_id, z.name, z.description
            ORDER BY z.zone_id
        """)
        return cur.fetchall()


@router.post("/zones")
async def save_zone(body: ZoneBody):
    """
    Create or update a zone AND set exactly which sensors belong to it.
    Sensors previously in this zone but not in sensor_ids become unassigned.
    """
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO zones (zone_id, name, description) VALUES (%s,%s,%s)
            ON CONFLICT (zone_id) DO UPDATE
              SET name = EXCLUDED.name, description = EXCLUDED.description
        """, (body.zone_id, body.name, body.description))

        # Release sensors that are no longer part of this zone
        cur.execute("""
            UPDATE sensors SET zone_id = NULL
            WHERE zone_id = %s AND NOT (sensor_id = ANY(%s))
        """, (body.zone_id, body.sensor_ids or []))

        # Claim the listed sensors (moves them out of any other zone)
        if body.sensor_ids:
            cur.execute("UPDATE sensors SET zone_id = %s WHERE sensor_id = ANY(%s)",
                        (body.zone_id, body.sensor_ids))
    conn.commit()
    await _notify("zones", {"zone_id": body.zone_id})
    return {"status": "saved", "zone_id": body.zone_id,
            "sensor_count": len(body.sensor_ids)}


@router.delete("/zones/{zone_id}")
async def delete_zone(zone_id: str):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("UPDATE sensors SET zone_id = NULL WHERE zone_id = %s", (zone_id,))
        cur.execute("DELETE FROM zones WHERE zone_id = %s", (zone_id,))
    conn.commit()
    await _notify("zones", {"zone_id": zone_id, "deleted": True})
    return {"status": "deleted"}


# ═══════════════════════════════════════════════════════════════════════════════
#  SENSORS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/sensors")
def get_sensors_config():
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
async def update_sensor_config(sensor_id: str, body: SensorConfigBody):
    if body.coverage_type not in ("passage", "machine", "storage", "exit"):
        raise HTTPException(400, "coverage_type must be passage|machine|storage|exit")
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO sensor_config (sensor_id, coverage_type, passable, description)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (sensor_id) DO UPDATE
              SET coverage_type = EXCLUDED.coverage_type,
                  passable      = EXCLUDED.passable,
                  description   = EXCLUDED.description
        """, (sensor_id, body.coverage_type, body.passable, body.description))
    conn.commit()
    await _notify("sensors", {"sensor_id": sensor_id})
    return {"status": "updated", "sensor_id": sensor_id}


# ═══════════════════════════════════════════════════════════════════════════════
#  WORKERS + AUTHORISATIONS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/workers")
def get_workers():
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT a.asset_id, a.asset_type, a.name,
                   COALESCE((
                     SELECT json_agg(json_build_object('type', au.allowed_type,
                                                       'id',   au.allowed_id))
                     FROM authorisations au WHERE au.asset_id = a.asset_id
                   ), '[]') AS authorisations,
                   COALESCE((
                     SELECT json_agg(t.sensor_id ORDER BY t.seq)
                     FROM asset_trajectory t WHERE t.asset_id = a.asset_id
                   ), '[]') AS default_trajectory
            FROM assets a
            ORDER BY a.asset_type, a.asset_id
        """)
        return cur.fetchall()


@router.post("/workers")
async def create_worker(body: WorkerBody):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO assets (asset_id, asset_type, name) VALUES (%s,%s,%s)
            ON CONFLICT (asset_id) DO UPDATE
              SET asset_type = EXCLUDED.asset_type, name = EXCLUDED.name
        """, (body.asset_id, body.asset_type, body.name))
        _write_trajectory(cur, body.asset_id, body.default_trajectory)
    conn.commit()
    await _notify("workers", {"asset_id": body.asset_id})
    return {"status": "saved", "asset_id": body.asset_id}


def _write_trajectory(cur, asset_id: str, sensors: list[str]):
    """Replace an asset's default trajectory with the given ordered list."""
    cur.execute("DELETE FROM asset_trajectory WHERE asset_id=%s", (asset_id,))
    for i, sid in enumerate(sensors or []):
        cur.execute(
            "INSERT INTO asset_trajectory (asset_id, seq, sensor_id) VALUES (%s,%s,%s)",
            (asset_id, i, sid))


@router.put("/workers/{asset_id}")
async def update_worker(asset_id: str, body: WorkerBody):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("UPDATE assets SET asset_type=%s, name=%s WHERE asset_id=%s",
                    (body.asset_type, body.name, asset_id))
        _write_trajectory(cur, asset_id, body.default_trajectory)
    conn.commit()
    await _notify("workers", {"asset_id": asset_id})
    return {"status": "updated"}


@router.delete("/workers/{asset_id}")
async def delete_worker(asset_id: str):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM asset_trajectory WHERE asset_id=%s", (asset_id,))
        cur.execute("DELETE FROM authorisations WHERE asset_id=%s", (asset_id,))
        cur.execute("DELETE FROM assets WHERE asset_id=%s", (asset_id,))
    conn.commit()
    await _notify("workers", {"asset_id": asset_id, "deleted": True})
    return {"status": "deleted"}


@router.get("/workers/{asset_id}/authorisations")
def get_authorisations(asset_id: str):
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""SELECT allowed_type, allowed_id FROM authorisations
                       WHERE asset_id=%s ORDER BY allowed_type, allowed_id""",
                    (asset_id,))
        rows = cur.fetchall()
    return {
        "asset_id": asset_id,
        "allowed_zones":   [r["allowed_id"] for r in rows if r["allowed_type"] == "zone"],
        "allowed_sensors": [r["allowed_id"] for r in rows if r["allowed_type"] == "sensor"],
    }


@router.put("/workers/{asset_id}/authorisations")
async def set_authorisations(asset_id: str, body: AuthBody):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM authorisations WHERE asset_id=%s", (asset_id,))
        for z in body.allowed_zones:
            cur.execute("INSERT INTO authorisations VALUES (%s,'zone',%s)",   (asset_id, z))
        for s in body.allowed_sensors:
            cur.execute("INSERT INTO authorisations VALUES (%s,'sensor',%s)", (asset_id, s))
    conn.commit()

    # Push new authorisations into the running engine so access status
    # is recomputed on the very next location message.
    try:
        from api.main import engine
        if engine and getattr(engine, "_store", None):
            engine._store.set_asset_authorisations(
                asset_id, set(body.allowed_sensors), set(body.allowed_zones))
    except Exception:
        pass

    await _notify("authorisations", {"asset_id": asset_id})
    return {"status": "updated",
            "zones": len(body.allowed_zones),
            "sensors": len(body.allowed_sensors)}


@router.post("/workers/bulk-authorise")
async def bulk_authorise(body: dict):
    """
    Grant the same authorisations to many assets at once.

    body = { "asset_ids": ["W01","W02"] | "all",
             "allowed_zones": [...], "allowed_sensors": [...],
             "mode": "replace" | "add" }

    Use asset_ids="all" + allowed_zones=<every zone> to clear a violation storm
    caused by assets that have no authorisations at all.
    """
    ids   = body.get("asset_ids", [])
    zones = body.get("allowed_zones", [])
    sens  = body.get("allowed_sensors", [])
    mode  = body.get("mode", "replace")

    conn = get_conn()
    with conn.cursor() as cur:
        if ids == "all" or ids == ["all"]:
            cur.execute("SELECT asset_id FROM assets")
            ids = [r[0] for r in cur.fetchall()]

        for aid in ids:
            if mode == "replace":
                cur.execute("DELETE FROM authorisations WHERE asset_id=%s", (aid,))
            for z in zones:
                cur.execute("""INSERT INTO authorisations VALUES (%s,'zone',%s)
                               ON CONFLICT DO NOTHING""", (aid, z))
            for sd in sens:
                cur.execute("""INSERT INTO authorisations VALUES (%s,'sensor',%s)
                               ON CONFLICT DO NOTHING""", (aid, sd))
    conn.commit()

    # Push into the running engine so status recomputes immediately
    try:
        from api.main import engine
        if engine and getattr(engine, "_store", None):
            for aid in ids:
                engine._store.set_asset_authorisations(aid, set(sens), set(zones))
    except Exception:
        pass

    await _notify("authorisations", {"bulk": True, "count": len(ids)})
    return {"status": "updated", "assets": len(ids),
            "zones": len(zones), "sensors": len(sens)}


@router.get("/workers/{asset_id}/trajectory")
def get_trajectory(asset_id: str, limit: int = 100):
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT sensor_id, zone_id, access_status, timestamp
            FROM location_events WHERE asset_id=%s
            ORDER BY timestamp DESC LIMIT %s
        """, (asset_id, limit))
        rows = cur.fetchall()
    return list(reversed(rows))
