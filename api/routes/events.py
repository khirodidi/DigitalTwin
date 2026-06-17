from fastapi import APIRouter, Query
from persistence.postgres import get_conn
import psycopg2.extras

router = APIRouter()

@router.get("/")
def list_events(level: str = None, limit: int = 100):
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if level:
            cur.execute("""
                SELECT * FROM events WHERE level = %s
                ORDER BY timestamp DESC LIMIT %s
            """, (level, limit))
        else:
            cur.execute("SELECT * FROM events ORDER BY timestamp DESC LIMIT %s", (limit,))
        return cur.fetchall()
