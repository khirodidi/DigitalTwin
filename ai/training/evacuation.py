# ai/training/evacuation.py
# Smart Evacuation — XGBoost danger score predictor training

import logging, numpy as np, pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
N_ESTIMATORS=300; MAX_DEPTH=4; LEARNING_RATE=0.05

def extract_env_data(days=90):
    from persistence.postgres import get_conn
    import psycopg2.extras
    conn=get_conn(); cutoff=datetime.utcnow()-timedelta(days=days)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT sensor_id,zone_id,reading_type,value,timestamp FROM env_readings WHERE timestamp>=%s ORDER BY sensor_id,timestamp",(cutoff,))
        rows=cur.fetchall()
    df=pd.DataFrame(rows)
    if not df.empty: df["timestamp"]=pd.to_datetime(df["timestamp"])
    logger.info(f"Extracted {len(df)} env readings.")
    return df

def extract_incident_labels():
    from persistence.postgres import get_conn
    import psycopg2.extras
    conn=get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT sensor_id,zone_id,event_type,timestamp FROM events WHERE event_type IN ('smoke_detected','high_temperature','workers_in_danger') ORDER BY timestamp")
        rows=cur.fetchall()
    df=pd.DataFrame(rows)
    if not df.empty:
        df["timestamp"]=pd.to_datetime(df["timestamp"])
        df["danger_score"]=df["event_type"].map({"smoke_detected":1.0,"workers_in_danger":1.0,"high_temperature":0.75}).fillna(0.5)
    return df

def _assign_label(sensor_id,ts,feats,incidents,window_min=15):
    if not incidents.empty:
        nearby=incidents[(incidents["sensor_id"]==sensor_id)&(abs((incidents["timestamp"]-ts).dt.total_seconds())<=window_min*60)]
        if not nearby.empty: return float(nearby["danger_score"].max())
    if feats["smoke_last"]>0.5: return 0.90
    if feats["temp_last"]>60: return 0.75
    if feats["temp_last"]>50: return 0.40
    if feats["hum_last"]>85: return 0.30
    return 0.0

def build_danger_dataset(env_df,incidents,window=10):
    rows_X,rows_y,feature_names=[],[],None
    for sid,grp in env_df.groupby("sensor_id"):
        grp=grp.sort_values("timestamp")
        wide=grp.pivot_table(index="timestamp",columns="reading_type",values="value",aggfunc="last").reset_index().sort_values("timestamp")
        for col in ["temperature","humidity","smoke"]:
            if col not in wide.columns: wide[col]=0.0
        wide=wide.fillna(method="ffill").fillna(0)
        n=len(wide)
        if n<window+1: continue
        for i in range(window,n):
            ts=wide["timestamp"].iloc[i]; seg=wide.iloc[i-window:i+1]
            temp=seg["temperature"].values; hum=seg["humidity"].values; smoke=seg["smoke"].values
            feats={"temp_last":float(temp[-1]),"hum_last":float(hum[-1]),"smoke_last":float(smoke[-1]),
                   "temp_mean_10":float(np.mean(temp)),"temp_std_10":float(np.std(temp)),"temp_max_10":float(np.max(temp)),
                   "hum_mean_10":float(np.mean(hum)),"smoke_freq_10":float(np.mean(smoke>0.5)),
                   "temp_slope":float(np.polyfit(range(len(temp)),temp,1)[0]),
                   "hum_slope":float(np.polyfit(range(len(hum)),hum,1)[0]),
                   "hour":float(ts.hour),"day_of_week":float(ts.dayofweek)}
            if feature_names is None: feature_names=sorted(feats.keys())
            rows_X.append([feats[k] for k in feature_names])
            rows_y.append(_assign_label(sid,ts,feats,incidents))
    if not rows_X: raise ValueError("No evacuation samples built.")
    return np.array(rows_X,dtype=np.float32),np.array(rows_y,dtype=np.float32),feature_names

def generate_synthetic_samples(n_fire=200,n_normal=500):
    rng=np.random.default_rng(42); X,y=[],[]
    for _ in range(n_fire):
        base=rng.uniform(20,35); rise=rng.uniform(5,40); tl=base+rise
        smoke=float(rng.random()<0.85)
        danger=min(1.0,0.5*smoke+0.4*(tl>60)+0.3*(tl>50))
        X.append([tl,rng.uniform(40,90),smoke,base+rise/2,rng.uniform(2,10),tl,rng.uniform(50,90),smoke*rng.uniform(0.5,1),rise/10,rng.uniform(-1,1),float(rng.integers(0,24)),float(rng.integers(0,7))])
        y.append(float(min(1.0,danger)))
    for _ in range(n_normal):
        temp=rng.uniform(15,45)
        X.append([temp,rng.uniform(30,70),0.0,temp+rng.uniform(-3,3),rng.uniform(0.5,3),temp+rng.uniform(-1,5),rng.uniform(30,70),0.0,rng.uniform(-0.5,0.5),rng.uniform(-0.5,0.5),float(rng.integers(0,24)),float(rng.integers(0,7))])
        y.append(0.0)
    return np.array(X,dtype=np.float32),np.array(y,dtype=np.float32)

def train_danger_model(days=90,model_path="models/danger_xgb.joblib",val_ratio=0.20):
    try: from xgboost import XGBRegressor
    except ImportError: logger.error("xgboost not installed."); return {}
    import joblib
    from sklearn.metrics import mean_squared_error,mean_absolute_error
    logger.info("=== Smart evacuation danger model training ===")
    env_df=extract_env_data(days=days); incidents=extract_incident_labels()
    if env_df.empty: logger.warning("No env data."); return {}
    X_real,y_real,feature_names=build_danger_dataset(env_df,incidents)
    X_syn,y_syn=generate_synthetic_samples()
    if X_syn.shape[1]!=X_real.shape[1]: X_syn=X_syn[:,:X_real.shape[1]]
    n=len(y_real); cut=int(n*(1-val_ratio))
    X_tr=np.vstack([X_real[:cut],X_syn]); y_tr=np.concatenate([y_real[:cut],y_syn])
    X_val,y_val=X_real[cut:],y_real[cut:]
    if len(y_val)<10: X_val,y_val=X_real[-20:],y_real[-20:]
    model=XGBRegressor(n_estimators=N_ESTIMATORS,max_depth=MAX_DEPTH,learning_rate=LEARNING_RATE,
                       subsample=0.8,colsample_bytree=0.8,random_state=42,tree_method="hist")
    model.fit(X_tr,y_tr,eval_set=[(X_val,y_val)],verbose=False)
    preds=model.predict(X_val).clip(0,1)
    rmse=float(mean_squared_error(y_val,preds)**0.5); mae=float(mean_absolute_error(y_val,preds))
    recall_danger=float(sum((y_val>0.5)&(preds>0.5))/max(sum(y_val>0.5),1))
    logger.info(f"  RMSE={rmse:.4f} | MAE={mae:.4f} | Recall@0.5={recall_danger:.3f}")
    Path(model_path).parent.mkdir(parents=True,exist_ok=True)
    joblib.dump({"model":model,"feature_keys":feature_names,"metrics":{"rmse":rmse},"trained_at":datetime.utcnow().isoformat()},model_path)
    logger.info(f"  Saved → {model_path}")
    return {"rmse":rmse,"mae":mae,"recall_danger":recall_danger}
