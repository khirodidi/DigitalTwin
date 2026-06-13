# =============================================================================
# ai/models/movement_optimiser.py
# Digital Twin — AI Layer
# Model 1: Movement Optimiser
# Learns worker movement patterns and detects unnecessary movements.
#
# Architecture: LSTM sequence classifier
# Input:  zone_id sequence (last 20 hops) + tabular features
# Output: movement_efficiency_score ∈ [0, 1] + flagged unnecessary moves
#
# Cold start: rule-based heuristics until ≥ 30 days of data
# Retraining: weekly on new location_events history
# =============================================================================

import numpy as np
import pickle
from pathlib import Path
from datetime import datetime

# ── Optional torch (falls back gracefully if not installed) ───────────────────
try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


# ─── LSTM model definition ────────────────────────────────────────────────────

if TORCH_AVAILABLE:
    class MovementLSTM(nn.Module):
        """
        Sequence classifier for worker zone transitions.

        Input:
          - zone_seq : (batch, seq_len) integer zone tokens
          - tabular  : (batch, n_tabular_features) float features

        Output:
          - score: (batch, 1) movement efficiency ∈ [0, 1]
        """
        def __init__(
            self,
            vocab_size: int,
            embed_dim:  int = 16,
            hidden_dim: int = 64,
            n_layers:   int = 2,
            n_tabular:  int = 10,
            dropout:    float = 0.2,
        ):
            super().__init__()
            self.embedding = nn.Embedding(vocab_size + 1, embed_dim, padding_idx=0)
            self.lstm = nn.LSTM(
                input_size  = embed_dim,
                hidden_size = hidden_dim,
                num_layers  = n_layers,
                batch_first = True,
                dropout     = dropout if n_layers > 1 else 0.0,
            )
            self.head = nn.Sequential(
                nn.Linear(hidden_dim + n_tabular, 64),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(64, 1),
                nn.Sigmoid(),
            )

        def forward(self, zone_seq, tabular):
            emb = self.embedding(zone_seq)           # (B, seq, embed_dim)
            _, (h, _) = self.lstm(emb)               # h: (layers, B, hidden)
            h_last = h[-1]                            # (B, hidden)
            combined = torch.cat([h_last, tabular], dim=1)
            return self.head(combined).squeeze(-1)   # (B,)


# ─── Training ─────────────────────────────────────────────────────────────────

def train(
    zone_sequences: np.ndarray,   # (N, seq_len) int
    tabular_feats:  np.ndarray,   # (N, F) float
    labels:         np.ndarray,   # (N,) float ∈ [0,1] — efficiency score
    vocab_size:     int,
    epochs:         int = 30,
    lr:             float = 1e-3,
    model_path:     str = "models/movement_lstm.pt",
):
    """
    Train the LSTM movement efficiency model.

    Labels:
        1.0 = perfectly efficient movement
        0.0 = highly unnecessary movement (backtracking, idle loops)

    Label strategy:
        - Expert annotation of historical shifts
        - Or: automated heuristic (backtrack_ratio → label via threshold)
    """
    if not TORCH_AVAILABLE:
        raise RuntimeError("PyTorch not installed. Run: pip install torch")

    import torch.optim as optim

    X_seq = torch.tensor(zone_sequences, dtype=torch.long)
    X_tab = torch.tensor(tabular_feats,  dtype=torch.float32)
    y     = torch.tensor(labels,         dtype=torch.float32)

    n_tabular = tabular_feats.shape[1]
    model = MovementLSTM(vocab_size=vocab_size, n_tabular=n_tabular)
    opt   = optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.BCELoss()

    model.train()
    for epoch in range(epochs):
        opt.zero_grad()
        pred = model(X_seq, X_tab)
        loss = loss_fn(pred, y)
        loss.backward()
        opt.step()
        if (epoch + 1) % 10 == 0:
            print(f"  Epoch {epoch+1}/{epochs} — loss: {loss.item():.4f}")

    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), model_path)
    print(f"  Model saved to {model_path}")
    return model


# ─── Inference ────────────────────────────────────────────────────────────────

class MovementOptimiserInference:
    """
    Inference wrapper. Loads trained model and scores worker movements.
    Falls back to rule-based heuristics if model not available.
    """

    SCORE_THRESHOLD = 0.6          # below this → flag as inefficient
    BACKTRACK_LIMIT = 3            # rule-based: max backtracks per shift

    def __init__(self, model_path: str = None, zone_vocab: dict = None):
        self.model_path = model_path
        self.zone_vocab = zone_vocab or {}
        self._model = None

        if TORCH_AVAILABLE and model_path and Path(model_path).exists():
            self._load_model()

    def _load_model(self):
        # Load model (vocab_size and n_tabular must match training)
        # For production: save/load model config alongside weights
        print(f"[MovementOptimiser] Loading model from {self.model_path}")

    def score(self, features: dict) -> dict:
        """
        Score a worker's movement efficiency for a time window.

        Args:
            features: output of build_movement_features()

        Returns:
            {
              movement_score:   float ∈ [0, 1],
              is_inefficient:   bool,
              unnecessary_moves: int,
              suggestions:      list[str],
            }
        """
        # Rule-based scoring (always computed, ML overrides when available)
        backtrack_ratio  = features.get("backtrack_ratio", 0)
        idle_loop_count  = features.get("idle_loop_count", 0)
        auth_violations  = features.get("auth_violations", 0)

        rule_score = max(0.0, 1.0 - backtrack_ratio * 2 - idle_loop_count * 0.1)

        # ML score (if model available)
        if self._model is not None and TORCH_AVAILABLE:
            # placeholder: call model forward pass
            score = rule_score   # replace with model output
        else:
            score = rule_score

        suggestions = []
        if backtrack_ratio > 0.3:
            suggestions.append("Worker is frequently backtracking — review task assignment order.")
        if idle_loop_count > 2:
            suggestions.append("Worker is circling between zones — possible task confusion or waiting.")
        if auth_violations > 0:
            suggestions.append(f"Worker entered {auth_violations} unauthorised zone(s) this shift.")
        if score > self.SCORE_THRESHOLD and not suggestions:
            suggestions.append("Movement pattern is efficient.")

        return {
            "asset_id":         features.get("asset_id"),
            "movement_score":   round(score, 3),
            "is_inefficient":   score < self.SCORE_THRESHOLD,
            "unnecessary_moves": features.get("backtrack_count", 0) + idle_loop_count,
            "suggestions":      suggestions,
            "timestamp":        datetime.utcnow().isoformat(),
        }


# ─── Heuristic label generator (for cold start / bootstrapping) ───────────────

def heuristic_label(features: dict) -> float:
    """
    Generate a weak movement efficiency label from heuristics.
    Use this to bootstrap the model before expert annotation is available.
    Score 1.0 = perfect, 0.0 = chaotic.
    """
    score = 1.0
    score -= min(features.get("backtrack_ratio", 0) * 1.5, 0.5)
    score -= min(features.get("idle_loop_count", 0) * 0.05, 0.3)
    score -= min(features.get("auth_violations", 0) * 0.1, 0.2)
    return max(0.0, round(score, 3))
