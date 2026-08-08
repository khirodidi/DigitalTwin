# ai/training/drift.py — PSI-based feature drift detection

import logging, numpy as np, pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
PSI_BINS=10; PSI_EPSILON=1e-6

def compute_psi_feature(baseline,current,bins=PSI_BINS):
    mn=min(baseline.min(),current.min()); mx=max(baseline.max(),current.max())
    if mx==mn: return 0.0
    edges=np.linspace(mn,mx,bins+1)
    bp=(np.histogram(baseline,bins=edges)[0].astype(float)+PSI_EPSILON)/(baseline.size+PSI_EPSILON*bins)
    cp=(np.histogram(current, bins=edges)[0].astype(float)+PSI_EPSILON)/(current.size +PSI_EPSILON*bins)
    return float(np.sum((cp-bp)*np.log(cp/bp)))

def compute_psi(days_baseline=30,days_current=7):
    from persistence.postgres import get_conn
    import psycopg2.extras
    now=datetime.utcnow()
    b_start=now-timedelta(days=days_baseline+days_current); c_start=now-timedelta(days=days_current)
    conn=get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT sensor_id,reading_type,value,timestamp FROM env_readings WHERE timestamp BETWEEN %s AND %s ORDER BY sensor_id,reading_type,timestamp",(b_start,now))
        rows=cur.fetchall()
    if not rows: return 0.0
    df=pd.DataFrame(rows); df["timestamp"]=pd.to_datetime(df["timestamp"])
    bdf=df[df["timestamp"]<c_start]; cdf=df[df["timestamp"]>=c_start]
    if bdf.empty or cdf.empty: return 0.0
    max_psi=0.0
    for rt in ["temperature","humidity"]:
        bv=bdf[bdf["reading_type"]==rt]["value"].dropna().values
        cv=cdf[cdf["reading_type"]==rt]["value"].dropna().values
        if len(bv)<20 or len(cv)<10: continue
        psi=compute_psi_feature(bv,cv); max_psi=max(max_psi,psi)
    logger.info(f"Drift check max PSI={max_psi:.4f}")
    return max_psi

def check_data_quality():
    from persistence.postgres import get_conn
    conn=get_conn(); issues={}
    with conn.cursor() as cur:
        for table,min_rows in [("env_readings",100),("location_events",50),("sensor_health_events",10)]:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count=cur.fetchone()[0]
            if count<min_rows: issues[f"{table}_count"]=f"Only {count} rows (need >={min_rows})"
        cur.execute("""
            SELECT s.sensor_id FROM sensors s LEFT JOIN
            (SELECT DISTINCT sensor_id FROM env_readings WHERE timestamp>=NOW()-INTERVAL '24 hours') r
            ON r.sensor_id=s.sensor_id WHERE r.sensor_id IS NULL""")
        silent=[row[0] for row in cur.fetchall()]
        if silent: issues["silent_sensors"]=silent
    if issues: logger.warning(f"Data quality issues: {issues}")
    else: logger.info("Data quality check passed.")
    return issues
