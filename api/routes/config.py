# =============================================================================
# api/routes/config.py
# Configuration endpoints — factory layout, blueprint upload, sensors,
# zones (defined by their sensors), workers, authorisations, trajectory,
# working station.
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

def _refresh_engine(section: str):
    """
    Push configuration changes into the running engine.

    Thresholds and authorisations are held in memory on the hot path, so they
    must be re-resolved when the operator changes them — otherwise the change
    only takes effect after a restart.
    """
    try:
        from api.main import engine
        if not engine:
            return
        if section in ("zones", "sensors", "factory", "grid", "all"):
            if hasattr(engine, "reload_thresholds"):
                engine.reload_thresholds()
        if section in ("zones", "authorisations", "workers", "grid", "all"):
            if hasattr(engine, "reload_authorisations"):
                engine.reload_authorisations()
    except Exception:
        pass


async def _notify(section: str, detail: dict = None):
    """
    Push a config_updated event to all connected dashboards so the monitoring
    view reloads the affected part of the configuration immediately.
    """
    _refresh_engine(section)
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
    # Global threshold defaults — the last level of the resolution chain
    temp_warning:      Optional[float] = None
    temp_critical:     Optional[float] = None
    humidity_warning:  Optional[float] = None
    humidity_critical: Optional[float] = None

class ZoneBody(BaseModel):
    zone_id:     str
    name:        str
    description: Optional[str] = ""
    sensor_ids:  list[str] = []       # zone is DEFINED by these sensors
    # Thresholds inherited by every sensor in the zone unless overridden.
    # null = fall through to the global default.
    temp_warning:      Optional[float] = None
    temp_critical:     Optional[float] = None
    humidity_warning:  Optional[float] = None
    humidity_critical: Optional[float] = None

class SensorConfigBody(BaseModel):
    coverage_type: str  = "passage"
    passable:      bool = True
    description:   Optional[str] = ""
    # null = inherit from this sensor's zone
    temp_warning:      Optional[float] = None
    temp_critical:     Optional[float] = None
    humidity_warning:  Optional[float] = None
    humidity_critical: Optional[float] = None

class WorkerBody(BaseModel):
    asset_id:           str
    asset_type:         str = "worker"
    name:               str
    default_trajectory: list[str] = []   # ordered sensors the asset works at
    # Working station — the UNORDERED set of sensors the asset works at most of
    # the time. None means "leave whatever is stored alone", so a client that
    # does not know about stations cannot wipe one; [] explicitly clears it.
    station:            Optional[list[str]] = None

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
    def _f(k, d):
        try:    return float(cfg.get(k, d))
        except (TypeError, ValueError): return d
    return {
        "factory_name":  cfg.get("factory_name", ""),
        "blueprint_url": bp,
        "grid_cols":     cols,
        "grid_rows":     rows,
        "temp_warning":      _f("temp_warning", 50.0),
        "temp_critical":     _f("temp_critical", 60.0),
        "humidity_warning":  _f("humidity_warning", 70.0),
        "humidity_critical": _f("humidity_critical", 85.0),
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
                   z.temp_warning, z.temp_critical,
                   z.humidity_warning, z.humidity_critical,
                   COALESCE(
                     array_agg(s.sensor_id ORDER BY s.grid_row, s.grid_col)
                     FILTER (WHERE s.sensor_id IS NOT NULL), '{}'
                   ) AS sensor_ids
            FROM zones z
            LEFT JOIN sensors s ON s.zone_id = z.zone_id
            GROUP BY z.zone_id, z.name, z.description,
                     z.temp_warning, z.temp_critical,
                     z.humidity_warning, z.humidity_critical
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
            INSERT INTO zones (zone_id, name, description,
                               temp_warning, temp_critical,
                               humidity_warning, humidity_critical)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (zone_id) DO UPDATE
              SET name              = EXCLUDED.name,
                  description       = EXCLUDED.description,
                  temp_warning      = EXCLUDED.temp_warning,
                  temp_critical     = EXCLUDED.temp_critical,
                  humidity_warning  = EXCLUDED.humidity_warning,
                  humidity_critical = EXCLUDED.humidity_critical
        """, (body.zone_id, body.name, body.description,
              body.temp_warning, body.temp_critical,
              body.humidity_warning, body.humidity_critical))

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
                   COALESCE(sc.description,    '')       AS description,
                   sc.temp_warning, sc.temp_critical,
                   sc.humidity_warning, sc.humidity_critical,
                   z.temp_warning      AS zone_temp_warning,
                   z.temp_critical     AS zone_temp_critical,
                   z.humidity_warning  AS zone_humidity_warning,
                   z.humidity_critical AS zone_humidity_critical
            FROM sensors s
            LEFT JOIN sensor_config sc USING (sensor_id)
            LEFT JOIN zones z ON z.zone_id = s.zone_id
            ORDER BY s.grid_row, s.grid_col
        """)
        rows = cur.fetchall()

    # Annotate each sensor with the EFFECTIVE value and where it came from,
    # so the UI can show "inherited from zone" rather than a blank field.
    glob = get_factory_config()
    out = []
    for r in rows:
        d = dict(r)
        eff, src = {}, {}
        for k in ("temp_warning","temp_critical",
                  "humidity_warning","humidity_critical"):
            if r.get(k) is not None:
                eff[k], src[k] = float(r[k]), "sensor"
            elif r.get(f"zone_{k}") is not None:
                eff[k], src[k] = float(r[f"zone_{k}"]), "zone"
            else:
                eff[k], src[k] = float(glob.get(k, 0)), "global"
        d["effective"] = eff
        d["threshold_source"] = src
        out.append(d)
    return out


@router.put("/sensors/{sensor_id}")
async def update_sensor_config(sensor_id: str, body: SensorConfigBody):
    if body.coverage_type not in ("passage", "machine", "storage", "exit"):
        raise HTTPException(400, "coverage_type must be passage|machine|storage|exit")
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO sensor_config
                (sensor_id, coverage_type, passable, description,
                 temp_warning, temp_critical,
                 humidity_warning, humidity_critical)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (sensor_id) DO UPDATE
              SET coverage_type     = EXCLUDED.coverage_type,
                  passable          = EXCLUDED.passable,
                  description       = EXCLUDED.description,
                  temp_warning      = EXCLUDED.temp_warning,
                  temp_critical     = EXCLUDED.temp_critical,
                  humidity_warning  = EXCLUDED.humidity_warning,
                  humidity_critical = EXCLUDED.humidity_critical
        """, (sensor_id, body.coverage_type, body.passable, body.description,
              body.temp_warning, body.temp_critical,
              body.humidity_warning, body.humidity_critical))
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
                     FROM asset_trajectory t
                     JOIN asset_trajectory_active act
                       ON act.asset_id = t.asset_id
                      AND act.source   = t.source
                      AND act.version  = t.version
                     WHERE t.asset_id = a.asset_id
                   ), '[]') AS default_trajectory,
                   COALESCE((SELECT act.source FROM asset_trajectory_active act
                             WHERE act.asset_id = a.asset_id), 'configured')
                     AS trajectory_source,
                   COALESCE((SELECT act.version FROM asset_trajectory_active act
                             WHERE act.asset_id = a.asset_id), 1)
                     AS trajectory_version,
                   -- Working station: unordered set, heaviest cell first so the
                   -- UI can show the primary cell without re-sorting.
                   COALESCE((
                     SELECT json_agg(st.sensor_id ORDER BY st.weight DESC,
                                                           st.sensor_id)
                     FROM asset_station st
                     JOIN asset_station_active sact
                       ON sact.asset_id = st.asset_id
                      AND sact.source   = st.source
                      AND sact.version  = st.version
                     WHERE st.asset_id = a.asset_id
                   ), '[]') AS station,
                   COALESCE((
                     SELECT json_object_agg(st.sensor_id, st.weight)
                     FROM asset_station st
                     JOIN asset_station_active sact
                       ON sact.asset_id = st.asset_id
                      AND sact.source   = st.source
                      AND sact.version  = st.version
                     WHERE st.asset_id = a.asset_id
                   ), '{}') AS station_weights,
                   COALESCE((SELECT sact.source FROM asset_station_active sact
                             WHERE sact.asset_id = a.asset_id), 'configured')
                     AS station_source,
                   COALESCE((SELECT sact.version FROM asset_station_active sact
                             WHERE sact.asset_id = a.asset_id), 1)
                     AS station_version
            FROM assets a
            ORDER BY a.asset_type, a.asset_id
        """)
        rows = cur.fetchall()

        # A zone authorisation implicitly authorises EVERY sensor in that zone.
        # Expand it here so the UI can show exactly which cells are covered
        # without re-deriving the rule in JavaScript.
        cur.execute("SELECT sensor_id, zone_id FROM sensors WHERE zone_id IS NOT NULL")
        zone_sensors = {}
        for r in cur.fetchall():
            zone_sensors.setdefault(r["zone_id"], []).append(r["sensor_id"])

    out = []
    for r in rows:
        d = dict(r)
        auths   = d.get("authorisations") or []
        zones   = [a["id"] for a in auths if a.get("type") == "zone"]
        direct  = [a["id"] for a in auths if a.get("type") == "sensor"]
        implied = sorted({sid for z in zones for sid in zone_sensors.get(z, [])})
        d["allowed_zones"]      = zones
        d["allowed_sensors"]    = direct                      # explicitly granted
        d["implied_sensors"]    = implied                     # via zone membership
        d["effective_sensors"]  = sorted(set(direct) | set(implied))
        out.append(d)
    return out


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
        if body.station is not None:
            _write_station(cur, body.asset_id, body.station)
    conn.commit()
    await _notify("workers", {"asset_id": body.asset_id})
    return {"status": "saved", "asset_id": body.asset_id}


def _write_trajectory(cur, asset_id: str, sensors: list[str],
                      source: str = "configured", confidence: float = 1.0):
    """
    Store a trajectory version and make it active.

    'configured' is the operator's initial route. The AI layer writes
    'learned' versions over time; both are retained so the learned route can
    be compared with, or reverted to, the original.
    """
    cur.execute("""SELECT COALESCE(MAX(version),0)+1 FROM asset_trajectory
                   WHERE asset_id=%s AND source=%s""", (asset_id, source))
    version = cur.fetchone()[0]

    for i, sid in enumerate(sensors or []):
        cur.execute("""INSERT INTO asset_trajectory
                         (asset_id, seq, sensor_id, source, version, confidence)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (asset_id, i, sid, source, version, confidence))

    cur.execute("""INSERT INTO asset_trajectory_active (asset_id, source, version)
                   VALUES (%s,%s,%s)
                   ON CONFLICT (asset_id) DO UPDATE
                     SET source=EXCLUDED.source, version=EXCLUDED.version,
                         updated_at=NOW()""",
                (asset_id, source, version))


def _write_station(cur, asset_id: str, sensors: list[str],
                   source: str = "configured", confidence: float = 1.0,
                   weights: dict = None):
    """
    Store a working-station version and make it active.

    The station is an unordered SET, so duplicates in `sensors` are collapsed.
    `weights` maps sensor_id → share of dwell time (0..1); when omitted every
    cell is weighted equally, which is the right default for an operator who
    is naming a station rather than measuring one.
    """
    cur.execute("""SELECT COALESCE(MAX(version),0)+1 FROM asset_station
                   WHERE asset_id=%s AND source=%s""", (asset_id, source))
    version = cur.fetchone()[0]

    unique = list(dict.fromkeys(sensors or []))     # de-dupe, keep first order
    default_w = round(1.0 / len(unique), 6) if unique else 1.0
    for sid in unique:
        cur.execute("""INSERT INTO asset_station
                         (asset_id, sensor_id, source, version, weight, confidence)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (asset_id, sid, source, version,
                     (weights or {}).get(sid, default_w), confidence))

    cur.execute("""INSERT INTO asset_station_active (asset_id, source, version)
                   VALUES (%s,%s,%s)
                   ON CONFLICT (asset_id) DO UPDATE
                     SET source=EXCLUDED.source, version=EXCLUDED.version,
                         updated_at=NOW()""",
                (asset_id, source, version))


@router.put("/workers/{asset_id}")
async def update_worker(asset_id: str, body: WorkerBody):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("UPDATE assets SET asset_type=%s, name=%s WHERE asset_id=%s",
                    (body.asset_type, body.name, asset_id))
        _write_trajectory(cur, asset_id, body.default_trajectory)
        if body.station is not None:
            _write_station(cur, asset_id, body.station)
    conn.commit()
    await _notify("workers", {"asset_id": asset_id})
    return {"status": "updated"}


@router.delete("/workers/{asset_id}")
async def delete_worker(asset_id: str):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM asset_trajectory WHERE asset_id=%s", (asset_id,))
        cur.execute("DELETE FROM asset_station    WHERE asset_id=%s", (asset_id,))
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


@router.get("/workers/{asset_id}/trajectory-versions")
def trajectory_versions(asset_id: str):
    """
    Every stored trajectory for this asset — the operator's initial route plus
    each version the AI has learned since, with the active one flagged.
    """
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT source, version, MIN(created_at) AS created_at,
                   MAX(confidence) AS confidence,
                   array_agg(sensor_id ORDER BY seq) AS sensors
            FROM asset_trajectory WHERE asset_id=%s
            GROUP BY source, version
            ORDER BY MIN(created_at) DESC
        """, (asset_id,))
        versions = cur.fetchall()
        cur.execute("""SELECT source, version FROM asset_trajectory_active
                       WHERE asset_id=%s""", (asset_id,))
        act = cur.fetchone()
    for v in versions:
        v["active"] = bool(act and v["source"] == act["source"]
                           and v["version"] == act["version"])
    return versions


@router.put("/workers/{asset_id}/trajectory-active")
async def set_active_trajectory(asset_id: str, body: dict):
    """Switch which trajectory version is in force. body: {source, version}"""
    src = body.get("source", "configured")
    ver = int(body.get("version", 1))
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""SELECT 1 FROM asset_trajectory
                       WHERE asset_id=%s AND source=%s AND version=%s LIMIT 1""",
                    (asset_id, src, ver))
        if not cur.fetchone():
            raise HTTPException(404, f"No {src} trajectory version {ver}")
        cur.execute("""INSERT INTO asset_trajectory_active (asset_id, source, version)
                       VALUES (%s,%s,%s)
                       ON CONFLICT (asset_id) DO UPDATE
                         SET source=EXCLUDED.source, version=EXCLUDED.version,
                             updated_at=NOW()""", (asset_id, src, ver))
    conn.commit()
    await _notify("workers", {"asset_id": asset_id, "trajectory": f"{src} v{ver}"})
    return {"status": "active", "source": src, "version": ver}


@router.get("/workers/{asset_id}/station-versions")
def station_versions(asset_id: str):
    """
    Every stored working station for this asset — the operator's initial set
    plus each version model ⑤ has learned since, with the active one flagged.
    """
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT source, version, MIN(created_at) AS created_at,
                   MAX(confidence) AS confidence,
                   array_agg(sensor_id ORDER BY weight DESC, sensor_id) AS sensors,
                   json_object_agg(sensor_id, weight) AS weights
            FROM asset_station WHERE asset_id=%s
            GROUP BY source, version
            ORDER BY MIN(created_at) DESC
        """, (asset_id,))
        versions = cur.fetchall()
        cur.execute("""SELECT source, version FROM asset_station_active
                       WHERE asset_id=%s""", (asset_id,))
        act = cur.fetchone()
    for v in versions:
        v["active"] = bool(act and v["source"] == act["source"]
                           and v["version"] == act["version"])
    return versions


@router.put("/workers/{asset_id}/station-active")
async def set_active_station(asset_id: str, body: dict):
    """Switch which station version is in force. body: {source, version}"""
    src = body.get("source", "configured")
    ver = int(body.get("version", 1))
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""SELECT 1 FROM asset_station
                       WHERE asset_id=%s AND source=%s AND version=%s LIMIT 1""",
                    (asset_id, src, ver))
        if not cur.fetchone():
            raise HTTPException(404, f"No {src} station version {ver}")
        cur.execute("""INSERT INTO asset_station_active (asset_id, source, version)
                       VALUES (%s,%s,%s)
                       ON CONFLICT (asset_id) DO UPDATE
                         SET source=EXCLUDED.source, version=EXCLUDED.version,
                             updated_at=NOW()""", (asset_id, src, ver))
    conn.commit()
    await _notify("workers", {"asset_id": asset_id, "station": f"{src} v{ver}"})
    return {"status": "active", "source": src, "version": ver}


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
