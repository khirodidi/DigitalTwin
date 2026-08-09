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


# =============================================================================
# TRAJECTORY-AWARE MOVEMENT FEATURES  (added with the config-driven AI update)
#
# The movement model now has ground truth: each asset's configured
# default_trajectory. Instead of scoring movement with a hand-tuned heuristic,
# we measure how far the actual path deviates from the planned route.
# =============================================================================

def dtw_distance(seq_a: list, seq_b: list, pos_fn) -> float:
    """
    Dynamic Time Warping between two cell sequences.

    Why DTW rather than a direct comparison: a worker who visits the right
    stops in the right order but lingers at one machine should not be
    penalised. DTW aligns sequences of unequal length and absorbs timing
    differences, measuring only route shape.

    pos_fn maps a sensor_id to (row, col) so the cost is real grid distance.
    """
    if not seq_a or not seq_b:
        return float(len(seq_a) + len(seq_b))

    n, m = len(seq_a), len(seq_b)
    INF  = float("inf")
    prev = [INF] * (m + 1)
    prev[0] = 0.0

    for i in range(1, n + 1):
        cur = [INF] * (m + 1)
        ra, ca = pos_fn(seq_a[i - 1])
        for j in range(1, m + 1):
            rb, cb = pos_fn(seq_b[j - 1])
            cost = abs(ra - rb) + abs(ca - cb)          # manhattan on the grid
            cur[j] = cost + min(prev[j], cur[j - 1], prev[j - 1])
        prev = cur
    return float(prev[m])


def build_trajectory_features(cell_sequence: list, planned: list,
                              pos_fn, coverage: dict = None) -> dict:
    """
    Compare an actual movement sequence against the configured trajectory.

    cell_sequence : sensors the asset actually visited, in order
    planned       : the asset's default_trajectory from configuration
    pos_fn        : sensor_id → (row, col)
    coverage      : sensor_id → coverage_type, for dwell breakdown

    Returns the 11 tabular features consumed by the movement LSTM.
    """
    coverage = coverage or {}
    n_actual = len(cell_sequence)

    if not planned or n_actual == 0:
        return {
            "dtw_distance": 0.0, "route_adherence": 1.0, "extra_cells": 0.0,
            "path_efficiency": 1.0, "machine_dwell_ratio": 0.0,
            "passage_transit_ratio": 0.0, "has_planned_route": 0.0,
        }

    # How much the actual path deviates from the plan, length-normalised
    raw_dtw = dtw_distance(cell_sequence, planned, pos_fn)
    norm    = raw_dtw / max(2.0 * len(planned), 1.0)

    # Were the planned waypoints visited, and in the right order?
    hit, idx = 0, 0
    for cell in cell_sequence:
        if idx < len(planned) and cell == planned[idx]:
            hit += 1; idx += 1
    adherence = hit / max(len(planned), 1)

    planned_set = set(planned)
    extra = sum(1 for c in cell_sequence if c not in planned_set)

    # Shortest possible path through the planned waypoints vs steps taken
    ideal = 0.0
    for a, b in zip(planned, planned[1:]):
        ra, ca = pos_fn(a); rb, cb = pos_fn(b)
        ideal += abs(ra - rb) + abs(ca - cb)
    efficiency = min(ideal / max(n_actual - 1, 1), 1.0) if ideal else 1.0

    # Where the time went, by what the sensor covers
    machine = sum(1 for c in cell_sequence if coverage.get(c) == "machine")
    passage = sum(1 for c in cell_sequence if coverage.get(c, "passage") == "passage")

    return {
        "dtw_distance":          float(min(norm, 3.0)),
        "route_adherence":       float(adherence),
        "extra_cells":           float(extra / max(n_actual, 1)),
        "path_efficiency":       float(efficiency),
        "machine_dwell_ratio":   float(machine / max(n_actual, 1)),
        "passage_transit_ratio": float(passage / max(n_actual, 1)),
        "has_planned_route":     1.0,
    }


def trajectory_efficiency_label(feats: dict) -> float:
    """
    Ground-truth efficiency derived from route deviation.

    A worker following their configured route scores 1.0. Deviation costs
    proportionally, with adherence and wandering weighted separately so the
    model can distinguish "took a detour" from "never did the job".
    """
    if not feats.get("has_planned_route"):
        return None                      # caller falls back to the heuristic

    score  = 1.0
    score -= min(feats.get("dtw_distance", 0.0) * 0.45, 0.50)
    score -= (1.0 - feats.get("route_adherence", 1.0)) * 0.30
    score -= min(feats.get("extra_cells", 0.0) * 0.40, 0.20)
    return float(max(0.0, min(1.0, round(score, 4))))
