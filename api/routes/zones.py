from fastapi import APIRouter
from persistence.postgres import get_conn
import psycopg2.extras

router = APIRouter()

@router.get("/")
def list_zones():
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT z.*, array_agg(s.sensor_id) as sensor_ids
            FROM zones z LEFT JOIN sensors s ON s.zone_id = z.zone_id
            GROUP BY z.zone_id ORDER BY z.zone_id
        """)
        return cur.fetchall()
