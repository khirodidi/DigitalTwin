# ai/training/monitor.py — System Monitor: Autoencoder + Forecaster + Failure XGB

import logging, numpy as np, pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
SEQ_LEN=30; N_AHEAD=5; AE_EPOCHS=50; FC_EPOCHS=60

def extract_env_wide(days, normal_only=False):
    from persistence.postgres import get_conn
    import psycopg2.extras
    conn=get_conn(); cutoff=datetime.utcnow()-timedelta(days=days)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT sensor_id,zone_id,reading_type,value,timestamp FROM env_readings WHERE timestamp>=%s ORDER BY sensor_id,timestamp",(cutoff,))
        rows=cur.fetchall()
    if not rows: return pd.DataFrame()
    df=pd.DataFrame(rows); df["timestamp"]=pd.to_datetime(df["timestamp"])
    wide=df.pivot_table(index=["sensor_id","zone_id","timestamp"],columns="reading_type",values="value",aggfunc="last").reset_index()
    wide.columns.name=None
    for c in ["temperature","humidity","smoke"]:
        if c not in wide.columns: wide[c]=0.0
    wide=wide.sort_values(["sensor_id","timestamp"])
    wide[["temperature","humidity","smoke"]]=wide[["temperature","humidity","smoke"]].fillna(method="ffill").fillna(0)
    if normal_only:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT sensor_id,timestamp FROM events WHERE level IN ('critical','warning')")
            alerts=pd.DataFrame(cur.fetchall())
        if not alerts.empty:
            alerts["timestamp"]=pd.to_datetime(alerts["timestamp"]); margin=pd.Timedelta(minutes=30)
            keep=pd.Series(True,index=wide.index)
            for _,row in alerts.iterrows():
                keep&=~((wide["sensor_id"]==row["sensor_id"])&(abs(wide["timestamp"]-row["timestamp"])<=margin))
            wide=wide[keep]
    logger.info(f"Extracted {len(wide)} env readings ({'normal' if normal_only else 'all'}).")
    return wide

def fit_scalers(wide):
    scalers={}
    for sid,grp in wide.groupby("sensor_id"):
        scalers[sid]={"temp_mean":float(grp["temperature"].mean()),"temp_std":float(grp["temperature"].std() or 1),
                      "hum_mean":float(grp["humidity"].mean()),"hum_std":float(grp["humidity"].std() or 1)}
    return scalers

def normalise(wide,scalers):
    w=wide.copy()
    for sid,sc in scalers.items():
        m=w["sensor_id"]==sid
        w.loc[m,"temperature"]=(w.loc[m,"temperature"]-sc["temp_mean"])/sc["temp_std"]
        w.loc[m,"humidity"]=(w.loc[m,"humidity"]-sc["hum_mean"])/sc["hum_std"]
    return w

def build_sequences(wide,seq_len=SEQ_LEN):
    seqs=[]
    for _,grp in wide.groupby("sensor_id"):
        arr=grp[["temperature","humidity","smoke"]].values.astype(np.float32)
        if len(arr)<seq_len: continue
        for i in range(len(arr)-seq_len+1): seqs.append(arr[i:i+seq_len])
    return np.array(seqs,dtype=np.float32)

def build_forecast_pairs(wide,seq_len=SEQ_LEN,n_ahead=N_AHEAD):
    X,y=[],[]
    for _,grp in wide.groupby("sensor_id"):
        arr=grp[["temperature","humidity","smoke"]].values.astype(np.float32)
        th=grp[["temperature","humidity"]].values.astype(np.float32)
        total=seq_len+n_ahead
        if len(arr)<total: continue
        for i in range(len(arr)-total+1):
            X.append(arr[i:i+seq_len]); y.append(th[i+seq_len:i+total])
    return np.array(X,dtype=np.float32),np.array(y,dtype=np.float32)

def _train_ae(seqs,model_path,scalers,epochs=AE_EPOCHS):
    import torch,torch.nn as nn,torch.optim as optim,joblib
    from ai.models.system_monitor import LSTMAutoencoder
    n=len(seqs); cut=int(n*0.85)
    Xtr=torch.tensor(seqs[:cut],dtype=torch.float32); Xv=torch.tensor(seqs[cut:],dtype=torch.float32)
    model=LSTMAutoencoder(3,32,seqs.shape[1]); opt=optim.Adam(model.parameters(),lr=1e-3); loss_fn=nn.MSELoss()
    best_val=float("inf"); best_state=None
    model.train()
    for e in range(epochs):
        opt.zero_grad(); loss=loss_fn(model(Xtr),Xtr); loss.backward(); opt.step()
        model.eval()
        with torch.no_grad(): vl=loss_fn(model(Xv),Xv).item()
        model.train()
        if vl<best_val: best_val=vl; best_state={k:v.clone() for k,v in model.state_dict().items()}
        if (e+1)%10==0: logger.info(f"  AE epoch {e+1}/{epochs} val={vl:.6f}")
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad(): scores=model.anomaly_score(Xv).numpy()
    threshold=float(np.percentile(scores,95))
    torch.save({"state_dict":model.state_dict(),"seq_len":seqs.shape[1],"threshold":threshold,
                "scalers":scalers,"trained_at":datetime.utcnow().isoformat()},model_path)
    logger.info(f"  AE saved → {model_path} (threshold={threshold:.6f})")
    return best_val

def _train_forecaster(X,y,model_path,scalers,epochs=FC_EPOCHS):
    import torch,torch.nn as nn,torch.optim as optim
    from ai.models.system_monitor import LSTMForecaster
    n=len(X); cut=int(n*0.85)
    Xtr=torch.tensor(X[:cut],dtype=torch.float32); ytr=torch.tensor(y[:cut],dtype=torch.float32)
    Xv=torch.tensor(X[cut:],dtype=torch.float32);  yv=torch.tensor(y[cut:],dtype=torch.float32)
    model=LSTMForecaster(3,64,2,N_AHEAD); opt=optim.Adam(model.parameters(),lr=1e-3); loss_fn=nn.MSELoss()
    best_val=float("inf"); best_state=None
    model.train()
    for e in range(epochs):
        opt.zero_grad(); loss=loss_fn(model(Xtr),ytr); loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(),1.0); opt.step()
        model.eval()
        with torch.no_grad(): vl=loss_fn(model(Xv),yv).item()
        model.train()
        if vl<best_val: best_val=vl; best_state={k:v.clone() for k,v in model.state_dict().items()}
        if (e+1)%10==0: logger.info(f"  FC epoch {e+1}/{epochs} val={vl:.6f}")
    model.load_state_dict(best_state)
    torch.save({"state_dict":model.state_dict(),"n_ahead":N_AHEAD,"scalers":scalers,
                "val_rmse":best_val**0.5,"trained_at":datetime.utcnow().isoformat()},model_path)
    logger.info(f"  Forecaster saved → {model_path}")
    return best_val**0.5

def train_monitor_models(days=30,model_dir="models"):
    logger.info("=== System monitor training ===")
    metrics={}; mdir=Path(model_dir); mdir.mkdir(exist_ok=True)
    normal_wide=extract_env_wide(days=max(days,7),normal_only=True)
    all_wide=extract_env_wide(days=days,normal_only=False)
    if all_wide.empty: logger.warning("Not enough data."); return {}
    scalers=fit_scalers(all_wide)
    import joblib; joblib.dump(scalers,mdir/"monitor_scalers.joblib")
    # Autoencoder
    if not normal_wide.empty:
        seqs=build_sequences(normalise(normal_wide,scalers))
        if len(seqs)>=50: metrics["autoencoder_mse"]=_train_ae(seqs,str(mdir/"autoencoder.pt"),scalers)
        else: logger.warning("Not enough normal seqs for AE.")
    # Forecaster
    X,y=build_forecast_pairs(normalise(all_wide,scalers))
    if len(X)>=100: metrics["forecaster_rmse"]=_train_forecaster(X,y,str(mdir/"forecaster.pt"),scalers)
    else: logger.warning("Not enough data for forecaster.")
    logger.info(f"=== Monitor training done. {metrics} ===")
    return metrics
