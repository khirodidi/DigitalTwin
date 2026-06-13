# =============================================================================
# ai/pipeline/features.py
# Digital Twin — AI Layer
# Feature engineering from raw localisation + environmental records.
# Shared by all three models.
# =============================================================================

import numpy as np
import pandas as pd
from datetime import datetime


# ─── Localisation record schema ───────────────────────────────────────────────
# [id_worker|id_object, current_sensor_id, current_zone_id,
#  previous_sensor_id, previous_zone_id, authorisation, timestamp]
LOC_COLS = [
    "asset_id", "current_sensor_id", "current_zone_id",
    "previous_sensor_id", "previous_zone_id", "authorisation", "timestamp",
]

# Environmental record schema
# [sensor_id, zone_id, reading_type, value, timestamp]
ENV_COLS = ["sensor_id", "zone_id", "reading_type", "value", "timestamp"]


# ─── Movement feature builder ──────────────────────────────────────────────────

def build_movement_features(
    loc_df: pd.DataFrame,
    asset_id: str,
    window: str = "8h",
) -> dict:
    """
    Compute movement features for one asset over a time window.
    Input: location_events rows for this asset, sorted by timestamp.

    Returns a feature dict ready for the movement optimiser model.
    """
    df = (
        loc_df[loc_df["asset_id"] == asset_id]
        .sort_values("timestamp")
        .copy()
    )
    if df.empty:
        return {}

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["dwell_time"] = df["timestamp"].diff().dt.total_seconds().fillna(0)

    # Zone transition sequence
    zone_seq = df["current_zone_id"].tolist()
    sensor_seq = df["current_sensor_id"].tolist()

    # Backtrack: zone appears again within 3 hops
    backtracks = 0
    for i in range(2, len(zone_seq)):
        if zone_seq[i] == zone_seq[i - 2]:
            backtracks += 1

    # Idle loops: same zone repeated > 3 consecutive times
    idle_loops = sum(
        1 for i in range(3, len(zone_seq))
        if zone_seq[i] == zone_seq[i-1] == zone_seq[i-2] == zone_seq[i-3]
    )

    # Unique zones visited
    unique_zones = len(set(zone_seq))

    # Dwell time stats per zone
    dwell_by_zone = df.groupby("current_zone_id")["dwell_time"].agg(["mean", "sum", "count"])

    # Temporal features
    ts = df["timestamp"].iloc[-1]
    hour = ts.hour
    day_of_week = ts.dayofweek
    is_weekend = int(day_of_week >= 5)

    # Authorisation violations in window
    violations = int((df["authorisation"] == "violation").sum())

    return {
        "asset_id":           asset_id,
        "zone_sequence":      zone_seq,         # used by LSTM (tokenised separately)
        "sensor_sequence":    sensor_seq,
        "n_transitions":      len(zone_seq) - 1,
        "n_unique_zones":     unique_zones,
        "backtrack_count":    backtracks,
        "backtrack_ratio":    backtracks / max(len(zone_seq) - 1, 1),
        "idle_loop_count":    idle_loops,
        "total_dwell_secs":   float(df["dwell_time"].sum()),
        "mean_dwell_secs":    float(df["dwell_time"].mean()),
        "max_dwell_secs":     float(df["dwell_time"].max()),
        "hour":               hour,
        "day_of_week":        day_of_week,
        "is_weekend":         is_weekend,
        "auth_violations":    violations,
    }


# ─── Environmental feature builder ────────────────────────────────────────────

def build_env_features(
    env_df: pd.DataFrame,
    sensor_id: str,
    window_sizes: list[int] = [5, 15, 60],
) -> dict:
    """
    Compute environmental features for one sensor over multiple rolling windows.
    Input: env_readings rows for this sensor, sorted by timestamp.

    Returns a feature dict for the system monitor model.
    """
    df = (
        env_df[env_df["sensor_id"] == sensor_id]
        .sort_values("timestamp")
        .pivot_table(index="timestamp", columns="reading_type", values="value", aggfunc="last")
        .reset_index()
        .sort_values("timestamp")
    )
    if df.empty:
        return {}

    feats = {"sensor_id": sensor_id}

    for col in ["temperature", "humidity"]:
        if col in df.columns:
            vals = df[col].dropna()
            feats[f"{col}_last"]     = float(vals.iloc[-1]) if len(vals) else np.nan
            feats[f"{col}_mean"]     = float(vals.mean())
            feats[f"{col}_std"]      = float(vals.std())
            feats[f"{col}_max"]      = float(vals.max())
            feats[f"{col}_gradient"] = float(vals.diff().mean())   # rate of change

            for w in window_sizes:
                tail = vals.tail(w)
                feats[f"{col}_mean_{w}"]  = float(tail.mean())
                feats[f"{col}_slope_{w}"] = float(
                    np.polyfit(range(len(tail)), tail, 1)[0]
                    if len(tail) > 1 else 0
                )

    if "smoke" in df.columns:
        smoke = df["smoke"].fillna(0)
        feats["smoke_last"]       = float(smoke.iloc[-1])
        feats["smoke_freq_5"]     = float(smoke.tail(5).mean())
        feats["smoke_freq_15"]    = float(smoke.tail(15).mean())

    # Temporal
    ts = pd.to_datetime(df["timestamp"].iloc[-1])
    feats["hour"]        = ts.hour
    feats["day_of_week"] = ts.dayofweek

    return feats


# ─── Sequence builder for LSTM (fixed-length padded windows) ──────────────────

def build_env_sequence(
    env_df: pd.DataFrame,
    sensor_id: str,
    seq_len: int = 30,
) -> np.ndarray:
    """
    Returns a (seq_len, 3) numpy array of [temperature, humidity, smoke]
    readings, oldest first, padded with zeros if insufficient history.
    Used by the LSTM autoencoder and forecaster.
    """
    df = (
        env_df[env_df["sensor_id"] == sensor_id]
        .sort_values("timestamp")
        .pivot_table(index="timestamp", columns="reading_type", values="value", aggfunc="last")
        .reset_index()
        .sort_values("timestamp")
    )

    cols_needed = ["temperature", "humidity", "smoke"]
    for col in cols_needed:
        if col not in df.columns:
            df[col] = 0.0

    arr = df[cols_needed].fillna(0).values.astype(np.float32)

    # Pad or trim to seq_len
    if len(arr) >= seq_len:
        return arr[-seq_len:]
    else:
        pad = np.zeros((seq_len - len(arr), 3), dtype=np.float32)
        return np.vstack([pad, arr])


def build_zone_sequence(
    loc_df: pd.DataFrame,
    asset_id: str,
    zone_vocab: dict[str, int],
    seq_len: int = 20,
) -> np.ndarray:
    """
    Returns a (seq_len,) integer array of zone IDs (tokenised).
    Used by the LSTM movement optimiser.
    """
    df = (
        loc_df[loc_df["asset_id"] == asset_id]
        .sort_values("timestamp")
    )
    zones = df["current_zone_id"].tolist()
    tokens = [zone_vocab.get(z, 0) for z in zones]

    if len(tokens) >= seq_len:
        return np.array(tokens[-seq_len:], dtype=np.int32)
    else:
        pad = [0] * (seq_len - len(tokens))
        return np.array(pad + tokens, dtype=np.int32)


# ─── Evacuation feature builder ───────────────────────────────────────────────

def build_danger_features(
    env_df: pd.DataFrame,
    sensor_id: str,
) -> np.ndarray:
    """
    Returns a flat feature vector for the danger score predictor.
    Covers the last reading + rolling statistics.
    """
    feats = build_env_features(env_df, sensor_id, window_sizes=[5, 15])
    feats.pop("sensor_id", None)
    feats.pop("hour", None)
    feats.pop("day_of_week", None)

    # Return consistent ordered vector
    keys = sorted(feats.keys())
    return np.array([feats.get(k, 0.0) for k in keys], dtype=np.float32), keys
