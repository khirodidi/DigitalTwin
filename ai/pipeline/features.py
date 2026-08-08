# ai/pipeline/features.py — feature engineering shared by all three AI models
import numpy as np
import pandas as pd

def build_movement_features(loc_df: pd.DataFrame, asset_id: str) -> dict:
    df = loc_df[loc_df["asset_id"]==asset_id].sort_values("timestamp").copy()
    if df.empty: return {}
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["dwell_time"] = df["timestamp"].diff().dt.total_seconds().fillna(0)
    zone_seq = df["current_zone_id"].tolist()
    backtracks = sum(1 for i in range(2,len(zone_seq)) if zone_seq[i]==zone_seq[i-2])
    idle_loops = sum(1 for i in range(3,len(zone_seq)) if zone_seq[i]==zone_seq[i-1]==zone_seq[i-2]==zone_seq[i-3])
    ts = df["timestamp"].iloc[-1]
    return {"asset_id":asset_id,"zone_sequence":zone_seq,
            "n_transitions":len(zone_seq)-1,"n_unique_zones":len(set(zone_seq)),
            "backtrack_count":backtracks,"backtrack_ratio":backtracks/max(len(zone_seq)-1,1),
            "idle_loop_count":idle_loops,"total_dwell_secs":float(df["dwell_time"].sum()),
            "mean_dwell_secs":float(df["dwell_time"].mean()),"max_dwell_secs":float(df["dwell_time"].max()),
            "hour":ts.hour,"day_of_week":ts.dayofweek,"is_weekend":int(ts.dayofweek>=5),
            "auth_violations":int((df.get("authorisation","authorised")=="violation").sum())}

def build_env_features(env_df: pd.DataFrame, sensor_id: str, window_sizes=[5,15,60]) -> dict:
    df = env_df[env_df["sensor_id"]==sensor_id].sort_values("timestamp")
    if df.empty: return {}
    wide = df.pivot_table(index="timestamp",columns="reading_type",values="value",aggfunc="last").reset_index().sort_values("timestamp")
    feats = {"sensor_id":sensor_id}
    for col in ["temperature","humidity"]:
        if col not in wide.columns: continue
        vals = wide[col].dropna()
        feats.update({f"{col}_last":float(vals.iloc[-1]),f"{col}_mean":float(vals.mean()),
                      f"{col}_std":float(vals.std()),f"{col}_max":float(vals.max()),
                      f"{col}_gradient":float(vals.diff().mean())})
        for w in window_sizes:
            tail = vals.tail(w)
            feats[f"{col}_mean_{w}"] = float(tail.mean())
            feats[f"{col}_slope_{w}"] = float(np.polyfit(range(len(tail)),tail,1)[0] if len(tail)>1 else 0)
    if "smoke" in wide.columns:
        smoke = wide["smoke"].fillna(0)
        feats.update({"smoke_last":float(smoke.iloc[-1]),"smoke_freq_5":float(smoke.tail(5).mean()),
                      "smoke_freq_15":float(smoke.tail(15).mean())})
    ts = pd.to_datetime(wide["timestamp"].iloc[-1])
    feats.update({"hour":ts.hour,"day_of_week":ts.dayofweek})
    return feats

def build_env_sequence(env_df: pd.DataFrame, sensor_id: str, seq_len: int=30) -> np.ndarray:
    df = env_df[env_df["sensor_id"]==sensor_id].sort_values("timestamp")
    wide = df.pivot_table(index="timestamp",columns="reading_type",values="value",aggfunc="last").reset_index().sort_values("timestamp")
    for c in ["temperature","humidity","smoke"]:
        if c not in wide.columns: wide[c]=0.0
    arr = wide[["temperature","humidity","smoke"]].fillna(0).values.astype(np.float32)
    if len(arr)>=seq_len: return arr[-seq_len:]
    return np.vstack([np.zeros((seq_len-len(arr),3),dtype=np.float32), arr])

def build_zone_sequence(loc_df: pd.DataFrame, asset_id: str,
                         zone_vocab: dict, seq_len: int=20) -> np.ndarray:
    df     = loc_df[loc_df["asset_id"]==asset_id].sort_values("timestamp")
    tokens = [zone_vocab.get(z,0) for z in df["current_zone_id"].tolist()]
    if len(tokens)>=seq_len: return np.array(tokens[-seq_len:],dtype=np.int32)
    return np.array([0]*(seq_len-len(tokens))+tokens, dtype=np.int32)
