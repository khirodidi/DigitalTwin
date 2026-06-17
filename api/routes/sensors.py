from fastapi import APIRouter
from persistence.postgres import get_conn
import psycopg2.extras

router = APIRouter()

@router.get("/")
def list_sensors():
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM sensors ORDER BY sensor_id")
        return cur.fetchall()

@router.get("/{sensor_id}/readings")
def sensor_readings(sensor_id: str, limit: int = 60):
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT * FROM env_readings WHERE sensor_id = %s
            ORDER BY timestamp DESC LIMIT %s
        """, (sensor_id, limit))
        return cur.fetchall()
