from fastapi import APIRouter
from persistence.postgres import get_conn
import psycopg2.extras

router = APIRouter()

@router.get("/")
def list_assets():
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM assets ORDER BY asset_id")
        return cur.fetchall()

@router.get("/{asset_id}/history")
def asset_history(asset_id: str, limit: int = 50):
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT * FROM location_events WHERE asset_id = %s
            ORDER BY timestamp DESC LIMIT %s
        """, (asset_id, limit))
        return cur.fetchall()

@router.put("/{asset_id}/authorisations")
def update_authorisations(asset_id: str, body: dict):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM authorisations WHERE asset_id = %s", (asset_id,))
        for sid in body.get("allowed_sensors", []):
            cur.execute("INSERT INTO authorisations VALUES (%s,'sensor',%s)", (asset_id, sid))
        for zid in body.get("allowed_zones", []):
            cur.execute("INSERT INTO authorisations VALUES (%s,'zone',%s)", (asset_id, zid))
    conn.commit()
    return {"status": "updated"}
