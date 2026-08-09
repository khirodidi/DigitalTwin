# =============================================================================
# ai/models/fire_detector.py
#
# FIRE DETECTION AND LOCALISATION
#
# ALGORITHM   ConvLSTM2D encoder + three heads (segmentation, origin, spread)
# INPUT       (T=20, H, W, C=6) grid tensor — the whole factory as a video
# OUTPUT      fire probability map (H,W) · origin cell (row,col) · spread vector
#
# Why spatio-temporal rather than per-sensor thresholds:
#   A machine cell sitting at 32 °C is normal. A corridor cell rising from
#   22 °C to 32 °C in 40 seconds while its neighbours also warm is a fire.
#   The discriminating signal is not the value but its spatial derivative
#   over time — which only a model that sees the whole grid can compute.
#
# The six channels per cell:
#   0  temperature      normalised against that cell's coverage-type baseline
#   1  humidity         z-scored (fire drives humidity down as it drives T up)
#   2  smoke            binary
#   3  dT/dt            temperature rate of change
#   4  laplacian(T)     spatial second derivative — expanding vs static hotspot
#   5  validity mask    0 where the sensor is offline, so the model can ignore it
# =============================================================================

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Architecture constants ────────────────────────────────────────────────────
SEQ_LEN        = 20      # timesteps per window (~40 s at a 2 s publish rate)
N_CHANNELS     = 6
HIDDEN_CH      = 32      # ConvLSTM hidden channels
KERNEL         = 3
DROPOUT        = 0.2

# ── Decision thresholds ───────────────────────────────────────────────────────
CONFIRMED_THRESHOLD = 0.85   # max cell probability → FIRE_CONFIRMED
SUSPECTED_THRESHOLD = 0.60   # max cell probability → FIRE_SUSPECTED
PERSISTENCE_WINDOWS = 2      # consecutive windows required before alerting


# ═══════════════════════════════════════════════════════════════════════════════
#  MODEL
# ═══════════════════════════════════════════════════════════════════════════════

def _build_torch_model(height: int, width: int):
    """
    Construct the ConvLSTM network. Imported lazily so the rest of the system
    runs without PyTorch installed.
    """
    import torch
    import torch.nn as nn

    class ConvLSTMCell(nn.Module):
        """Single ConvLSTM cell — convolutional gates instead of dense ones."""
        def __init__(self, in_ch, hid_ch, kernel):
            super().__init__()
            pad = kernel // 2
            self.hid_ch = hid_ch
            # One conv produces all four gates at once (i, f, o, g)
            self.conv = nn.Conv2d(in_ch + hid_ch, 4 * hid_ch, kernel, padding=pad)

        def forward(self, x, state):
            h, c = state
            gates = self.conv(torch.cat([x, h], dim=1))
            i, f, o, g = torch.chunk(gates, 4, dim=1)
            i, f, o = torch.sigmoid(i), torch.sigmoid(f), torch.sigmoid(o)
            g = torch.tanh(g)
            c_next = f * c + i * g
            h_next = o * torch.tanh(c_next)
            return h_next, c_next

        def init_state(self, batch, h, w, device):
            return (torch.zeros(batch, self.hid_ch, h, w, device=device),
                    torch.zeros(batch, self.hid_ch, h, w, device=device))

    class FireNet(nn.Module):
        def __init__(self, h, w, in_ch=N_CHANNELS, hid=HIDDEN_CH):
            super().__init__()
            self.h, self.w = h, w
            self.cell1 = ConvLSTMCell(in_ch, hid, KERNEL)
            self.cell2 = ConvLSTMCell(hid,   hid, KERNEL)
            self.norm  = nn.BatchNorm2d(hid)
            self.drop  = nn.Dropout2d(DROPOUT)

            # Head 1 — per-cell fire probability (segmentation)
            self.seg_head = nn.Sequential(
                nn.Conv2d(hid, 16, 3, padding=1), nn.ReLU(),
                nn.Conv2d(16, 1, 1),
            )
            # Head 2 — origin coordinates (row, col) normalised to [0,1]
            self.origin_head = nn.Sequential(
                nn.AdaptiveAvgPool2d(1), nn.Flatten(),
                nn.Linear(hid, 32), nn.ReLU(), nn.Linear(32, 2), nn.Sigmoid(),
            )
            # Head 3 — spread vector (dr, dc) and rate in cells/min
            self.spread_head = nn.Sequential(
                nn.AdaptiveAvgPool2d(1), nn.Flatten(),
                nn.Linear(hid, 32), nn.ReLU(), nn.Linear(32, 3),
            )

        def forward(self, x):
            # x: (B, T, C, H, W)
            b, t, _, h, w = x.shape
            dev = x.device
            s1 = self.cell1.init_state(b, h, w, dev)
            s2 = self.cell2.init_state(b, h, w, dev)
            for ti in range(t):
                s1 = self.cell1(x[:, ti], s1)
                s2 = self.cell2(s1[0],    s2)
            feat = self.drop(self.norm(s2[0]))
            return (self.seg_head(feat).squeeze(1),   # (B,H,W) logits
                    self.origin_head(feat),           # (B,2)
                    self.spread_head(feat))           # (B,3)

    return FireNet(height, width)


# ═══════════════════════════════════════════════════════════════════════════════
#  FEATURE BUILDER — raw readings → (T, H, W, 6) tensor
# ═══════════════════════════════════════════════════════════════════════════════

class GridTensorBuilder:
    """
    Converts per-sensor readings into the grid tensor the model expects.
    Maintains a rolling buffer so inference can run on every new reading.
    """

    def __init__(self, cols: int, rows: int, coverage: dict = None,
                 seq_len: int = SEQ_LEN):
        self.cols     = cols
        self.rows     = rows
        self.seq_len  = seq_len
        self.coverage = coverage or {}        # sensor_id → coverage_type
        # Rolling raw buffers, one frame per timestep
        self._frames  = []                    # list of (H,W,3) [temp,hum,smoke]
        self._masks   = []                    # list of (H,W) validity

        # Per-coverage-type baselines used to normalise temperature, so a
        # machine running hot is not mistaken for a fire.
        self.baseline = {"machine": 31.0, "storage": 18.0,
                         "passage": 22.5, "exit": 17.5}

    def _index(self, sensor_id: str):
        n = int("".join(ch for ch in str(sensor_id) if ch.isdigit()) or 1) - 1
        return divmod(n, self.cols)

    def push_frame(self, readings: dict, health: dict = None):
        """
        readings : sensor_id → {temperature, humidity, smoke}
        health   : sensor_id → status string ('online' | 'degraded' | 'offline')
        """
        frame = np.zeros((self.rows, self.cols, 3), dtype=np.float32)
        mask  = np.zeros((self.rows, self.cols),    dtype=np.float32)

        for sid, r in (readings or {}).items():
            row, col = self._index(sid)
            if row >= self.rows or col >= self.cols:
                continue
            status = (health or {}).get(sid, "online")
            if status == "offline":
                continue                       # leave mask 0 — model ignores it
            frame[row, col, 0] = float(r.get("temperature") or 0.0)
            frame[row, col, 1] = float(r.get("humidity")    or 0.0)
            frame[row, col, 2] = 1.0 if r.get("smoke") else 0.0
            mask[row, col]     = 1.0

        self._frames.append(frame)
        self._masks.append(mask)
        if len(self._frames) > self.seq_len:
            self._frames.pop(0)
            self._masks.pop(0)

    def ready(self) -> bool:
        return len(self._frames) >= self.seq_len

    def build(self) -> Optional[np.ndarray]:
        """Returns (T, H, W, 6) or None if not enough frames buffered yet."""
        if not self.ready():
            return None
        return self.frames_to_tensor(np.array(self._frames), np.array(self._masks),
                                     self.coverage, self.cols, self.rows,
                                     self.baseline)

    # ── Static so the training pipeline can reuse the identical transform ────
    @staticmethod
    def frames_to_tensor(frames: np.ndarray, masks: np.ndarray,
                         coverage: dict, cols: int, rows: int,
                         baseline: dict) -> np.ndarray:
        """
        frames : (T, H, W, 3) raw [temp, humidity, smoke]
        masks  : (T, H, W)    1 where the sensor reported
        returns: (T, H, W, 6)
        """
        T, H, W, _ = frames.shape
        out = np.zeros((T, H, W, N_CHANNELS), dtype=np.float32)

        # Per-cell temperature baseline from coverage type
        base = np.full((H, W), 22.5, dtype=np.float32)
        for sid, ctype in (coverage or {}).items():
            n = int("".join(ch for ch in str(sid) if ch.isdigit()) or 1) - 1
            r, c = divmod(n, cols)
            if r < H and c < W:
                base[r, c] = baseline.get(ctype, 22.5)

        temp  = frames[..., 0]
        hum   = frames[..., 1]
        smoke = frames[..., 2]

        # ch0 — temperature excess over this cell's own baseline, scaled
        out[..., 0] = np.clip((temp - base[None]) / 40.0, -1.0, 2.0)
        # ch1 — humidity z-scored around a nominal 55 %
        out[..., 1] = np.clip((hum - 55.0) / 25.0, -2.0, 2.0)
        # ch2 — smoke
        out[..., 2] = smoke
        # ch3 — dT/dt, first frame zero
        d = np.zeros_like(temp)
        d[1:] = temp[1:] - temp[:-1]
        out[..., 3] = np.clip(d / 5.0, -2.0, 2.0)
        # ch4 — spatial Laplacian of temperature (expanding vs static hotspot)
        for t in range(T):
            out[t, ..., 4] = np.clip(_laplacian(temp[t]) / 20.0, -2.0, 2.0)
        # ch5 — validity mask
        out[..., 5] = masks

        return out


def _laplacian(g: np.ndarray) -> np.ndarray:
    """Discrete 4-neighbour Laplacian with edge replication."""
    p = np.pad(g, 1, mode="edge")
    return (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]
            - 4.0 * g)


# ═══════════════════════════════════════════════════════════════════════════════
#  INFERENCE WRAPPER
# ═══════════════════════════════════════════════════════════════════════════════

class FireDetectorInference:
    """
    Loads a trained FireNet and runs detection on rolling grid windows.
    Falls back to a physics-based rule detector when no model is available,
    so fire detection works from the very first minute of deployment.
    """

    def __init__(self, model_path: str = "models/fire_convlstm.pt",
                 cols: int = 6, rows: int = 5, coverage: dict = None):
        self.cols     = cols
        self.rows     = rows
        self.coverage = coverage or {}
        self.model    = None
        self.builder  = GridTensorBuilder(cols, rows, coverage)
        self._streak  = 0            # consecutive positive windows
        self._history = []           # recent fire maps, for origin back-projection

        try:
            import torch
            ck = torch.load(model_path, map_location="cpu", weights_only=False)
            self.model = _build_torch_model(ck.get("rows", rows), ck.get("cols", cols))
            self.model.load_state_dict(ck["state_dict"])
            self.model.eval()
            logger.info(f"Fire model loaded from {model_path}")
        except Exception as e:
            logger.info(f"Fire model unavailable ({e}) — using rule-based detector")

    # ── Public API ───────────────────────────────────────────────────────────

    def update(self, readings: dict, health: dict = None) -> Optional[dict]:
        """
        Push one frame and run detection.
        Returns an alert dict when fire is detected, else None.
        """
        self.builder.push_frame(readings, health)
        if not self.builder.ready():
            return None

        tensor = self.builder.build()
        result = (self._predict_model(tensor) if self.model
                  else self._predict_rules(tensor))

        # Persistence filter — suppress single-frame sensor glitches
        if result["max_prob"] >= SUSPECTED_THRESHOLD:
            self._streak += 1
        else:
            self._streak = 0
            self._history.clear()
            return None

        self._history.append(result["fire_map"])
        if len(self._history) > 10:
            self._history.pop(0)

        if self._streak < PERSISTENCE_WINDOWS:
            return None

        # Refine origin using the earliest window that saw fire
        origin = self._back_project_origin(tensor, result)
        level  = ("critical" if result["max_prob"] >= CONFIRMED_THRESHOLD
                  else "warning")
        status = ("FIRE_CONFIRMED" if result["max_prob"] >= CONFIRMED_THRESHOLD
                  else "FIRE_SUSPECTED")

        return {
            "type":            "fire_detected",
            "level":           level,
            "status":          status,
            "confidence":      round(float(result["max_prob"]), 3),
            "origin_sensor":   origin["sensor_id"],
            "origin_cell":     [origin["row"], origin["col"]],
            "affected_sensors": result["affected"],
            "n_affected":      len(result["affected"]),
            "spread_vector":   result.get("spread", [0.0, 0.0]),
            "spread_rate":     result.get("rate", 0.0),
            "predicted_next":  self._predict_front(origin, result),
            "source":          "convlstm" if self.model else "rules",
            "message":        (f"{status.replace('_',' ').title()} at "
                               f"{origin['sensor_id']} — {len(result['affected'])} "
                               f"cell(s) affected, confidence "
                               f"{result['max_prob']:.0%}"),
            "action":          "evacuate_zone",
        }

    def fire_map(self) -> Optional[np.ndarray]:
        """Latest per-cell fire probability, for the evacuation danger model."""
        return self._history[-1] if self._history else None

    # ── Model inference ──────────────────────────────────────────────────────

    def _predict_model(self, tensor: np.ndarray) -> dict:
        import torch
        x = torch.tensor(tensor, dtype=torch.float32)         # (T,H,W,C)
        x = x.permute(0, 3, 1, 2).unsqueeze(0)                # (1,T,C,H,W)
        with torch.no_grad():
            seg, origin, spread = self.model(x)
            prob = torch.sigmoid(seg)[0].numpy()              # (H,W)
        sp = spread[0].numpy()
        return {
            "fire_map":  prob,
            "max_prob":  float(prob.max()),
            "affected":  self._cells_above(prob, SUSPECTED_THRESHOLD),
            "origin_hint": (float(origin[0][0]) * self.rows,
                            float(origin[0][1]) * self.cols),
            "spread":    [float(sp[0]), float(sp[1])],
            "rate":      float(sp[2]),
        }

    # ── Rule-based fallback (no model yet) ───────────────────────────────────

    def _predict_rules(self, tensor: np.ndarray) -> dict:
        """
        Physics-based detector used until the model is trained.

        Fire signature = high absolute temperature OR sustained positive
        dT/dt, combined with smoke or a positive spatial Laplacian
        (indicating an expanding rather than static hot spot).
        """
        last     = tensor[-1]
        temp_ex  = last[..., 0]          # excess over coverage baseline
        smoke    = last[..., 2]
        dT       = tensor[-5:, ..., 3].mean(axis=0)   # sustained rise
        lap      = last[..., 4]
        mask     = last[..., 5]

        score = np.zeros_like(temp_ex)
        score += np.clip(temp_ex / 0.9,  0, 1) * 0.40   # ~36 °C over baseline
        score += np.clip(dT * 4.0,       0, 1) * 0.25   # rising fast
        score += smoke                            * 0.25
        score += np.clip(lap * 2.0,      0, 1) * 0.10   # expanding hotspot
        score *= mask                                    # ignore offline cells
        score = np.clip(score, 0, 1)

        return {
            "fire_map": score,
            "max_prob": float(score.max()),
            "affected": self._cells_above(score, SUSPECTED_THRESHOLD),
            "spread":   [0.0, 0.0],
            "rate":     0.0,
        }

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _cells_above(self, m: np.ndarray, thr: float) -> list:
        out = []
        for r, c in zip(*np.where(m >= thr)):
            out.append({"sensor_id": self._sid(r, c),
                        "probability": round(float(m[r, c]), 3)})
        return sorted(out, key=lambda x: -x["probability"])

    def _sid(self, row: int, col: int) -> str:
        return f"S{row * self.cols + col + 1:02d}"

    def _back_project_origin(self, tensor: np.ndarray, result: dict) -> dict:
        """
        The origin is where the fire started, not where it is hottest now.
        Weight each cell by (fire probability × cumulative temperature rise)
        and take the centroid — this biases toward the cell that has been
        burning longest.
        """
        prob = result["fire_map"]
        rise = tensor[:, :, :, 3].sum(axis=0)        # total dT over the window
        w    = prob * np.clip(rise, 0, None)
        if w.sum() <= 1e-6:
            r, c = np.unravel_index(int(prob.argmax()), prob.shape)
        else:
            rr, cc = np.mgrid[0:prob.shape[0], 0:prob.shape[1]]
            r = int(round(float((w * rr).sum() / w.sum())))
            c = int(round(float((w * cc).sum() / w.sum())))
        r = max(0, min(self.rows - 1, r))
        c = max(0, min(self.cols - 1, c))
        return {"row": r, "col": c, "sensor_id": self._sid(r, c)}

    def _predict_front(self, origin: dict, result: dict) -> list:
        """Cells the fire is expected to reach next, for pre-emptive routing."""
        prob = result["fire_map"]
        out  = []
        for r, c in zip(*np.where(prob >= SUSPECTED_THRESHOLD)):
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.rows and 0 <= nc < self.cols:
                    if prob[nr, nc] < SUSPECTED_THRESHOLD:
                        sid = self._sid(nr, nc)
                        if sid not in out:
                            out.append(sid)
        return out[:8]
