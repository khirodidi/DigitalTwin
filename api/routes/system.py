from fastapi import APIRouter
from persistence.postgres import get_conn
import psycopg2.extras
router = APIRouter()

@router.get("/state")
def system_state():
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM system_snapshots ORDER BY timestamp DESC LIMIT 1")
        row = cur.fetchone()
    return row or {"overall_status":"unknown"}

@router.get("/layout")
def factory_layout():
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM zones ORDER BY zone_id")
        zones = cur.fetchall()
        cur.execute("SELECT * FROM sensors ORDER BY sensor_id")
        sensors = cur.fetchall()
    return {"zones":zones,"sensors":sensors}

@router.post("/reload-models")
async def reload_models():
    from api.main import engine
    if engine:
        engine.reload_ai_models()
        return {"status":"models reloaded"}
    return {"status":"engine not running"}
