# =============================================================================
# tests/test_ai.py
# Unit tests for AI pipeline:
#   - Feature engineering (movement, environment)
#   - Heuristic label generation
#   - Danger score rule-based fallback
#   - Drift PSI computation
# Run with: pytest tests/test_ai.py -v
# =============================================================================

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _loc_df(asset_id="W01", zones=None, n=20):
    """Build a synthetic location_events DataFrame."""
    if zones is None:
        zones = ["zone_A", "zone_B", "zone_A", "zone_C"] * (n // 4 + 1)
    now = datetime.utcnow()
    rows = []
    for i in range(n):
        rows.append({
            "asset_id":        asset_id,
            "current_zone_id": zones[i % len(zones)],
            "current_sensor_id": f"S{i % 10:02d}",
            "authorisation":   "authorised",
            "timestamp":       now + timedelta(minutes=i * 5),
        })
    return pd.DataFrame(rows)


def _env_df(sensor_id="S01", n=60, base_temp=25.0, temp_drift=0.0):
    """Build a synthetic env_readings DataFrame."""
    now = datetime.utcnow()
    rows = []
    for i in range(n):
        rows.append({
            "sensor_id":    sensor_id,
            "zone_id":      "zone_A",
            "reading_type": "temperature",
            "value":        base_temp + i * temp_drift,
            "timestamp":    now + timedelta(minutes=i),
        })
        rows.append({
            "sensor_id":    sensor_id,
            "zone_id":      "zone_A",
            "reading_type": "humidity",
            "value":        55.0,
            "timestamp":    now + timedelta(minutes=i),
        })
        rows.append({
            "sensor_id":    sensor_id,
            "zone_id":      "zone_A",
            "reading_type": "smoke",
            "value":        0.0,
            "timestamp":    now + timedelta(minutes=i),
        })
    return pd.DataFrame(rows)


# ─── Movement Features ────────────────────────────────────────────────────────

class TestMovementFeatures:

    def test_basic_features_present(self):
        from ai.pipeline.features import build_movement_features
        df    = _loc_df("W01", n=20)
        feats = build_movement_features(df, "W01")
        assert "backtrack_ratio"  in feats
        assert "n_transitions"    in feats
        assert "idle_loop_count"  in feats
        assert "mean_dwell_secs"  in feats

    def test_backtrack_detected(self):
        from ai.pipeline.features import build_movement_features
        # A-B-A-B-A — heavy backtracking
        zones = ["zone_A", "zone_B"] * 10
        df    = _loc_df("W01", zones=zones, n=20)
        feats = build_movement_features(df, "W01")
        assert feats["backtrack_count"] > 0
        assert feats["backtrack_ratio"] > 0

    def test_no_backtrack_efficient(self):
        from ai.pipeline.features import build_movement_features
        # Straight path: A → B → C → D
        zones = ["zone_A"] * 5 + ["zone_B"] * 5 + ["zone_C"] * 5 + ["zone_D"] * 5
        df    = _loc_df("W01", zones=zones, n=20)
        feats = build_movement_features(df, "W01")
        assert feats["backtrack_count"] == 0
        assert feats["backtrack_ratio"] == 0

    def test_empty_asset_returns_empty(self):
        from ai.pipeline.features import build_movement_features
        df    = _loc_df("W01", n=10)
        feats = build_movement_features(df, "W99")  # unknown asset
        assert feats == {}


# ─── Environment Features ─────────────────────────────────────────────────────

class TestEnvFeatures:

    def test_feature_keys_present(self):
        from ai.pipeline.features import build_env_features
        df    = _env_df("S01", n=30)
        feats = build_env_features(df, "S01", window_sizes=[5])
        assert "temp_last"    in feats
        assert "temp_mean"    in feats
        assert "temp_slope_5" in feats
        assert "smoke_last"   in feats

    def test_rising_temp_has_positive_slope(self):
        from ai.pipeline.features import build_env_features
        df    = _env_df("S01", n=30, base_temp=20.0, temp_drift=1.0)
        feats = build_env_features(df, "S01", window_sizes=[10])
        assert feats["temp_slope_10"] > 0

    def test_stable_temp_near_zero_slope(self):
        from ai.pipeline.features import build_env_features
        df    = _env_df("S01", n=30, base_temp=25.0, temp_drift=0.0)
        feats = build_env_features(df, "S01", window_sizes=[10])
        assert abs(feats["temp_slope_10"]) < 0.5

    def test_unknown_sensor_returns_empty(self):
        from ai.pipeline.features import build_env_features
        df    = _env_df("S01", n=30)
        feats = build_env_features(df, "S99")
        assert feats == {}


# ─── Sequence Builder ─────────────────────────────────────────────────────────

class TestSequenceBuilders:

    def test_env_sequence_shape(self):
        from ai.pipeline.features import build_env_sequence
        df  = _env_df("S01", n=40)
        seq = build_env_sequence(df, "S01", seq_len=30)
        assert seq.shape == (30, 3)
        assert seq.dtype == np.float32

    def test_env_sequence_pads_short(self):
        from ai.pipeline.features import build_env_sequence
        df  = _env_df("S01", n=5)
        seq = build_env_sequence(df, "S01", seq_len=30)
        assert seq.shape == (30, 3)
        # First rows should be zero padding
        assert np.all(seq[:25] == 0)

    def test_zone_sequence_shape(self):
        from ai.pipeline.features import build_zone_sequence
        df    = _loc_df("W01", n=25)
        vocab = {"zone_A": 1, "zone_B": 2, "zone_C": 3}
        seq   = build_zone_sequence(df, "W01", vocab, seq_len=20)
        assert seq.shape == (20,)
        assert seq.dtype == np.int32

    def test_zone_sequence_pads_short(self):
        from ai.pipeline.features import build_zone_sequence
        df    = _loc_df("W01", n=5)
        vocab = {"zone_A": 1, "zone_B": 2, "zone_C": 3}
        seq   = build_zone_sequence(df, "W01", vocab, seq_len=20)
        assert seq.shape == (20,)
        assert seq[0] == 0   # padding


# ─── Heuristic Labels ─────────────────────────────────────────────────────────

class TestHeuristicLabels:

    def test_efficient_worker_high_score(self):
        from ai.training.movement import _heuristic_label
        feats = {"backtrack_ratio": 0.0, "idle_loop_count": 0, "auth_violations": 0}
        score = _heuristic_label(feats)
        assert score == 1.0

    def test_heavy_backtracker_low_score(self):
        from ai.training.movement import _heuristic_label
        feats = {"backtrack_ratio": 0.8, "idle_loop_count": 5, "auth_violations": 2}
        score = _heuristic_label(feats)
        assert score < 0.3

    def test_score_clamped_to_zero(self):
        from ai.training.movement import _heuristic_label
        feats = {"backtrack_ratio": 1.0, "idle_loop_count": 20, "auth_violations": 10}
        score = _heuristic_label(feats)
        assert score >= 0.0

    def test_score_in_range(self):
        from ai.training.movement import _heuristic_label
        for br in [0.0, 0.3, 0.6, 1.0]:
            feats = {"backtrack_ratio": br, "idle_loop_count": 0, "auth_violations": 0}
            score = _heuristic_label(feats)
            assert 0.0 <= score <= 1.0


# ─── Danger Score Rules ───────────────────────────────────────────────────────

class TestDangerLabels:

    def test_smoke_gives_high_danger(self):
        from ai.training.evacuation import _assign_label
        feats = {"smoke_last": 1.0, "temp_last": 25.0, "hum_last": 50.0}
        label = _assign_label("S01", datetime.utcnow(), feats, pd.DataFrame())
        assert label >= 0.85

    def test_critical_temp_high_danger(self):
        from ai.training.evacuation import _assign_label
        feats = {"smoke_last": 0.0, "temp_last": 65.0, "hum_last": 50.0}
        label = _assign_label("S01", datetime.utcnow(), feats, pd.DataFrame())
        assert label >= 0.70

    def test_warning_temp_medium_danger(self):
        from ai.training.evacuation import _assign_label
        feats = {"smoke_last": 0.0, "temp_last": 55.0, "hum_last": 50.0}
        label = _assign_label("S01", datetime.utcnow(), feats, pd.DataFrame())
        assert 0.2 <= label <= 0.6

    def test_normal_gives_zero_danger(self):
        from ai.training.evacuation import _assign_label
        feats = {"smoke_last": 0.0, "temp_last": 22.0, "hum_last": 50.0}
        label = _assign_label("S01", datetime.utcnow(), feats, pd.DataFrame())
        assert label == 0.0


# ─── PSI Drift Detection ──────────────────────────────────────────────────────

class TestPSI:

    def test_identical_distributions_zero_psi(self):
        from ai.training.drift import compute_psi_feature
        baseline = np.random.default_rng(0).normal(25, 3, 1000)
        current  = np.random.default_rng(1).normal(25, 3, 1000)
        psi = compute_psi_feature(baseline, current)
        assert psi < 0.10   # negligible drift

    def test_shifted_distribution_high_psi(self):
        from ai.training.drift import compute_psi_feature
        baseline = np.random.default_rng(0).normal(25, 3, 1000)
        current  = np.random.default_rng(1).normal(60, 5, 1000)   # huge shift
        psi = compute_psi_feature(baseline, current)
        assert psi > 0.20   # significant drift

    def test_constant_feature_zero_psi(self):
        from ai.training.drift import compute_psi_feature
        baseline = np.full(100, 25.0)
        current  = np.full(100, 25.0)
        psi = compute_psi_feature(baseline, current)
        assert psi == 0.0


# ─── Synthetic Data ───────────────────────────────────────────────────────────

class TestSyntheticData:

    def test_synthetic_samples_shape(self):
        from ai.training.evacuation import generate_synthetic_samples
        X, y = generate_synthetic_samples(n_fire=50, n_normal=100)
        assert X.shape == (150, 12)
        assert y.shape == (150,)

    def test_fire_samples_high_danger(self):
        from ai.training.evacuation import generate_synthetic_samples
        X, y = generate_synthetic_samples(n_fire=100, n_normal=0)
        assert y.mean() > 0.3   # fire samples should have elevated danger

    def test_normal_samples_low_danger(self):
        from ai.training.evacuation import generate_synthetic_samples
        X, y = generate_synthetic_samples(n_fire=0, n_normal=100)
        assert float(y.max()) == 0.0   # all normal = danger 0
