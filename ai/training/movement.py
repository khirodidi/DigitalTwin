# ai/training/movement.py
# Movement Optimiser — full training pipeline
# Algorithm: LSTM sequence classifier
# Labels: auto-generated via heuristic or supervisor annotation
# Retrains: weekly on last 30 days of location_events

import logging, numpy as np, pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
SEQ_LEN=20; EMBED_DIM=16; HIDDEN_DIM=64; N_LAYERS=2
DROPOUT=0.2; EPOCHS=40; LR=1e-3; BATCH_SIZE=32; MIN_HOPS=5

def extract_location_data(days=30):
    from persistence.postgres import get_conn
    import psycopg2.extras
    cutoff = datetime.utcnow() - timedelta(days=days)
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT le.asset_id, a.asset_type, le.sensor_id,
                   le.zone_id AS current_zone_id, le.access_status, le.timestamp
            FROM location_events le JOIN assets a ON a.asset_id=le.asset_id
            WHERE le.timestamp >= %s ORDER BY le.asset_id, le.timestamp
        """, (cutoff,))
        rows = cur.fetchall()
    df = pd.DataFrame(rows)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    logger.info(f"Extracted {len(df)} location events.")
    return df

def build_zone_vocab(df):
    zones = sorted(df["current_zone_id"].dropna().unique())
    return {z: i+1 for i, z in enumerate(zones)}

def _heuristic_label(feats):
    score = 1.0
    score -= min(feats.get("backtrack_ratio",0)*1.5, 0.50)
    score -= min(feats.get("idle_loop_count",0)*0.05, 0.30)
    score -= min(feats.get("auth_violations",0)*0.10, 0.20)
    return float(max(0.0, round(score,4)))

def build_samples(df, zone_vocab):
    from ai.pipeline.features import build_movement_features
    zone_seqs, tabular_feats, labels = [], [], []
    df = df.copy()
    df["shift_start"] = pd.to_datetime(df["timestamp"]).dt.floor("8h")
    df["shift_id"] = df["asset_id"] + "_" + df["shift_start"].astype(str)
    for sid, grp in df.groupby("shift_id"):
        grp = grp.sort_values("timestamp")
        if len(grp) < MIN_HOPS: continue
        asset_id = grp["asset_id"].iloc[0]
        feats = build_movement_features(grp, asset_id)
        if not feats: continue
        zones = grp["current_zone_id"].tolist()
        tokens = [zone_vocab.get(z,0) for z in zones]
        tokens = tokens[-SEQ_LEN:] if len(tokens)>=SEQ_LEN else [0]*(SEQ_LEN-len(tokens))+tokens
        tab = np.array([
            feats.get("backtrack_ratio",0.0), feats.get("idle_loop_count",0.0),
            feats.get("auth_violations",0.0), feats.get("mean_dwell_secs",0.0)/3600,
            feats.get("hour",0.0)/23, feats.get("day_of_week",0.0)/6,
        ], dtype=np.float32)
        zone_seqs.append(tokens); tabular_feats.append(tab)
        labels.append(_heuristic_label(feats))
    if not zone_seqs: raise ValueError("No training samples built.")
    return np.array(zone_seqs,dtype=np.int32), np.array(tabular_feats,dtype=np.float32), np.array(labels,dtype=np.float32)

def train_movement_model(days=30, model_path="models/movement_lstm.pt", epochs=EPOCHS):
    try: import torch, torch.nn as nn, torch.optim as optim
    except ImportError: logger.error("PyTorch not installed."); return {}
    from ai.models.movement_optimiser import MovementLSTM
    logger.info("=== Movement optimiser training ===")
    df = extract_location_data(days=days)
    if df.empty or len(df)<50: logger.warning("Not enough data."); return {}
    zone_vocab = build_zone_vocab(df)
    zone_seqs, tabular, labels = build_samples(df, zone_vocab)
    logger.info(f"  Built {len(labels)} shift samples.")
    n=len(labels); cut=int(n*0.8)
    Xs_tr,Xt_tr,y_tr = zone_seqs[:cut],tabular[:cut],labels[:cut]
    Xs_v,Xt_v,y_v   = zone_seqs[cut:],tabular[cut:],labels[cut:]
    model = MovementLSTM(vocab_size=len(zone_vocab), embed_dim=EMBED_DIM,
                         hidden_dim=HIDDEN_DIM, n_layers=N_LAYERS,
                         n_tabular=tabular.shape[1], dropout=DROPOUT)
    opt=optim.Adam(model.parameters(),lr=LR); loss_fn=nn.MSELoss()
    Xst=torch.tensor(Xs_tr,dtype=torch.long); Xtt=torch.tensor(Xt_tr,dtype=torch.float32)
    yt=torch.tensor(y_tr,dtype=torch.float32)
    Xsv=torch.tensor(Xs_v,dtype=torch.long); Xtv=torch.tensor(Xt_v,dtype=torch.float32)
    yv=torch.tensor(y_v,dtype=torch.float32)
    best_val=float("inf"); best_state=None
    model.train()
    for epoch in range(epochs):
        opt.zero_grad(); pred=model(Xst,Xtt); loss=loss_fn(pred,yt)
        loss.backward(); opt.step()
        model.eval()
        with torch.no_grad(): val=loss_fn(model(Xsv,Xtv),yv).item()
        model.train()
        if val<best_val: best_val=val; best_state={k:v.clone() for k,v in model.state_dict().items()}
        if (epoch+1)%10==0: logger.info(f"  Epoch {epoch+1}/{epochs} val={val:.5f}")
    model.load_state_dict(best_state)
    Path(model_path).parent.mkdir(parents=True,exist_ok=True)
    torch.save({"state_dict":model.state_dict(),"vocab_size":len(zone_vocab),
                "val_mse":best_val,"trained_at":datetime.utcnow().isoformat()}, model_path)
    import json; Path(model_path).with_suffix(".vocab.json").write_text(json.dumps(zone_vocab))
    logger.info(f"  Saved → {model_path} (val MSE={best_val:.5f})")
    mse=float(np.mean((model(Xsv,Xtv).detach().numpy()-y_v)**2))
    return {"mse":mse,"val_mse":best_val}
