# =============================================================================
# ai/models/system_monitor.py
# Digital Twin — AI Layer
# Model 3: System Monitor
#
# Three sub-models:
#   ① LSTM Autoencoder  — anomaly detection per sensor
#   ② LSTM Regressor    — environmental forecast (5 & 15 min ahead)
#   ③ XGBoost Classifier — sensor failure probability
#
# Retrains: nightly on rolling 30-day window
# Drift detection: PSI on feature distributions triggers retraining
# =============================================================================

import numpy as np
from datetime import datetime
from pathlib import Path

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    from xgboost import XGBClassifier
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False


# ─── ① LSTM Autoencoder — anomaly detection ───────────────────────────────────

if TORCH_AVAILABLE:
    class LSTMAutoencoder(nn.Module):
        """
        Sequence autoencoder for environmental readings.
        Input:  (batch, seq_len, 3)  — [temperature, humidity, smoke]
        Output: (batch, seq_len, 3)  — reconstructed sequence

        Anomaly score = mean squared reconstruction error.
        Trained exclusively on normal-operation data.
        High error → anomalous behaviour.
        """
        def __init__(self, input_dim: int = 3, hidden_dim: int = 32, seq_len: int = 30):
            super().__init__()
            self.seq_len    = seq_len
            self.hidden_dim = hidden_dim

            # Encoder
            self.encoder_lstm = nn.LSTM(input_dim, hidden_dim, batch_first=True)

            # Decoder: repeats latent vector and decodes
            self.decoder_lstm = nn.LSTM(hidden_dim, hidden_dim, batch_first=True)
            self.output_layer = nn.Linear(hidden_dim, input_dim)

        def forward(self, x):
            # Encode
            _, (h, c) = self.encoder_lstm(x)

            # Decode: replicate last hidden state across seq_len steps
            latent = h[-1].unsqueeze(1).repeat(1, self.seq_len, 1)  # (B, seq, H)
            decoded, _ = self.decoder_lstm(latent)
            return self.output_layer(decoded)                         # (B, seq, input_dim)

        def anomaly_score(self, x: torch.Tensor) -> torch.Tensor:
            """Returns per-sample reconstruction error (MSE)."""
            recon = self.forward(x)
            return ((x - recon) ** 2).mean(dim=[1, 2])              # (B,)


def train_autoencoder(
    sequences: np.ndarray,   # (N, seq_len, 3) — NORMAL operation only
    epochs: int = 50,
    lr: float = 1e-3,
    model_path: str = "models/autoencoder.pt",
) -> "LSTMAutoencoder":
    """
    Train the LSTM autoencoder on normal environmental sequences.
    Only feed normal-operation data — the model learns what normal looks like.
    """
    if not TORCH_AVAILABLE:
        raise RuntimeError("PyTorch not installed.")

    X = torch.tensor(sequences, dtype=torch.float32)

    seq_len = sequences.shape[1]
    model   = LSTMAutoencoder(seq_len=seq_len)
    opt     = optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    model.train()
    for epoch in range(epochs):
        opt.zero_grad()
        recon = model(X)
        loss  = loss_fn(recon, X)
        loss.backward()
        opt.step()
        if (epoch + 1) % 10 == 0:
            print(f"  Autoencoder epoch {epoch+1}/{epochs} — loss: {loss.item():.6f}")

    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), model_path)
    print(f"  Autoencoder saved to {model_path}")
    return model


# ─── ② LSTM Regressor — environmental forecast ────────────────────────────────

if TORCH_AVAILABLE:
    class LSTMForecaster(nn.Module):
        """
        Multi-step forecaster for temperature and humidity.
        Input:  (batch, seq_len, 3) — historical readings
        Output: (batch, n_ahead, 2) — predicted [temperature, humidity]

        n_ahead: number of future steps to predict (e.g. 5 = 5 readings ahead)
        """
        def __init__(
            self,
            input_dim:  int = 3,
            hidden_dim: int = 64,
            n_layers:   int = 2,
            n_ahead:    int = 5,
        ):
            super().__init__()
            self.n_ahead = n_ahead
            self.lstm    = nn.LSTM(input_dim, hidden_dim, n_layers, batch_first=True, dropout=0.2)
            self.head    = nn.Sequential(
                nn.Linear(hidden_dim, 32),
                nn.ReLU(),
                nn.Linear(32, n_ahead * 2),   # predict n_ahead steps × 2 outputs
            )

        def forward(self, x):
            _, (h, _) = self.lstm(x)
            out = self.head(h[-1])                          # (B, n_ahead*2)
            return out.view(-1, self.n_ahead, 2)            # (B, n_ahead, 2)


def train_forecaster(
    sequences: np.ndarray,   # (N, seq_len, 3)
    targets:   np.ndarray,   # (N, n_ahead, 2) — future [temp, hum]
    n_ahead:   int = 5,
    epochs:    int = 60,
    lr:        float = 1e-3,
    model_path: str = "models/forecaster.pt",
) -> "LSTMForecaster":
    if not TORCH_AVAILABLE:
        raise RuntimeError("PyTorch not installed.")

    X = torch.tensor(sequences, dtype=torch.float32)
    y = torch.tensor(targets,   dtype=torch.float32)

    model   = LSTMForecaster(n_ahead=n_ahead)
    opt     = optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    model.train()
    for epoch in range(epochs):
        opt.zero_grad()
        pred = model(X)
        loss = loss_fn(pred, y)
        loss.backward()
        opt.step()
        if (epoch + 1) % 10 == 0:
            print(f"  Forecaster epoch {epoch+1}/{epochs} — loss: {loss.item():.6f}")

    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), model_path)
    print(f"  Forecaster saved to {model_path}")
    return model


# ─── ③ XGBoost — sensor failure predictor ─────────────────────────────────────

def train_failure_predictor(
    X: np.ndarray,           # (N, F) — health + reading features
    y: np.ndarray,           # (N,) binary — 0=ok, 1=failed within 24h
    feature_keys: list[str],
    model_path: str = "models/failure_xgb.joblib",
):
    """
    Sensor failure predictor.

    Features:
        - consecutive_failures (from watchdog)
        - reading_variance (last 20 readings)
        - time_since_last_reading
        - temp/hum/smoke mean + std
        - hour, day_of_week

    Label: did the sensor go offline within 24h of this reading?
    """
    if not XGB_AVAILABLE:
        raise RuntimeError("xgboost not installed.")

    import joblib
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report

    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

    model = XGBClassifier(
        n_estimators     = 200,
        max_depth        = 4,
        learning_rate    = 0.05,
        scale_pos_weight = (y == 0).sum() / max((y == 1).sum(), 1),  # handle class imbalance
        random_state     = 42,
        eval_metric      = "logloss",
    )
    model.fit(X_train, y_train,
              eval_set=[(X_val, y_val)],
              verbose=False)

    preds = model.predict(X_val)
    print(classification_report(y_val, preds, target_names=["ok", "failure"]))

    joblib.dump({"model": model, "feature_keys": feature_keys}, model_path)
    print(f"  Failure predictor saved to {model_path}")
    return model


# ─── Inference wrapper (all three sub-models) ─────────────────────────────────

class SystemMonitorInference:
    """
    Loads all three monitor sub-models and provides a unified inference interface.
    Called on every environmental reading update.
    """

    ANOMALY_THRESHOLD   = 0.75     # anomaly_score above this → alert
    FAILURE_THRESHOLD   = 0.70     # failure probability above this → maintenance alert
    CRIT_TEMP_FORECAST  = 58.0     # predicted temperature threshold for pre-alert

    def __init__(
        self,
        autoencoder_path:  str = None,
        forecaster_path:   str = None,
        failure_model_path: str = None,
    ):
        self._autoencoder = None
        self._forecaster  = None
        self._failure     = None

        if TORCH_AVAILABLE:
            if autoencoder_path and Path(autoencoder_path).exists():
                self._autoencoder = LSTMAutoencoder()
                self._autoencoder.load_state_dict(torch.load(autoencoder_path))
                self._autoencoder.eval()
            if forecaster_path and Path(forecaster_path).exists():
                self._forecaster = LSTMForecaster()
                self._forecaster.load_state_dict(torch.load(forecaster_path))
                self._forecaster.eval()

        if XGB_AVAILABLE and failure_model_path and Path(failure_model_path).exists():
            import joblib
            artefact = joblib.load(failure_model_path)
            self._failure        = artefact["model"]
            self._failure_keys   = artefact["feature_keys"]

    def analyse(
        self,
        sensor_id:    str,
        sequence:     np.ndarray,    # (seq_len, 3) — [temp, hum, smoke]
        health_feats: np.ndarray,    # (F,) — health features for failure predictor
    ) -> list[dict]:
        """
        Run all three sub-models for one sensor and return alert events.
        """
        alerts = []
        now    = datetime.utcnow().isoformat()

        # ① Anomaly detection
        if self._autoencoder is not None:
            with torch.no_grad():
                x     = torch.tensor(sequence[np.newaxis], dtype=torch.float32)
                score = float(self._autoencoder.anomaly_score(x)[0])
            if score > self.ANOMALY_THRESHOLD:
                alerts.append({
                    "type":          "env_anomaly",
                    "level":         "warning",
                    "sensor_id":     sensor_id,
                    "anomaly_score": round(score, 4),
                    "message":       f"Unusual environmental pattern detected on sensor {sensor_id} (score={score:.3f})",
                    "action":        "inspect_sensor",
                    "timestamp":     now,
                })

        # ② Forecast
        if self._forecaster is not None:
            with torch.no_grad():
                x   = torch.tensor(sequence[np.newaxis], dtype=torch.float32)
                out = self._forecaster(x)[0].numpy()     # (n_ahead, 2)
            pred_temp = out[-1, 0]    # furthest-ahead temperature prediction
            pred_hum  = out[-1, 1]
            if pred_temp > self.CRIT_TEMP_FORECAST:
                alerts.append({
                    "type":            "predicted_critical_temperature",
                    "level":           "warning",
                    "sensor_id":       sensor_id,
                    "predicted_temp":  round(float(pred_temp), 1),
                    "steps_ahead":     len(out),
                    "message":         f"Temperature forecast: {pred_temp:.1f}°C in ~{len(out)} readings — sensor {sensor_id}",
                    "action":          "preventive_inspection",
                    "timestamp":       now,
                })

        # ③ Failure prediction
        if self._failure is not None:
            prob = float(self._failure.predict_proba(health_feats.reshape(1, -1))[0, 1])
            if prob > self.FAILURE_THRESHOLD:
                alerts.append({
                    "type":                "sensor_failure_predicted",
                    "level":              "warning",
                    "sensor_id":           sensor_id,
                    "failure_probability": round(prob, 3),
                    "message":             f"Sensor {sensor_id} has {prob*100:.0f}% failure probability — schedule maintenance",
                    "action":              "schedule_maintenance",
                    "timestamp":           now,
                })

        return alerts

    def rule_based_fallback(
        self,
        sensor_id: str,
        temperature: float,
        humidity:   float,
        smoke:      bool,
        history_temps: list[float],
    ) -> list[dict]:
        """
        Used when models not yet trained (cold start).
        Replicates the rule-based prediction from the twin engine
        with slightly more nuance.
        """
        alerts = []
        now    = datetime.utcnow().isoformat()

        if smoke:
            alerts.append({
                "type": "env_anomaly", "level": "critical",
                "sensor_id": sensor_id, "anomaly_score": 1.0,
                "message": f"Smoke on sensor {sensor_id} — rule-based detection",
                "action": "evacuate_zone", "timestamp": now,
            })

        if len(history_temps) >= 3:
            rate = (history_temps[-1] - history_temps[0]) / len(history_temps)
            predicted = history_temps[-1] + rate * 5
            if predicted > self.CRIT_TEMP_FORECAST:
                alerts.append({
                    "type": "predicted_critical_temperature", "level": "warning",
                    "sensor_id": sensor_id, "predicted_temp": round(predicted, 1),
                    "message": f"Temp trending up — predicted {predicted:.1f}°C on sensor {sensor_id}",
                    "action": "preventive_inspection", "timestamp": now,
                })

        return alerts
