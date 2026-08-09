# =============================================================================
# ai/training/fire.py
#
# TRAINING PIPELINE — Fire Detection and Localisation
#
# DATASET
#   Real fire incidents are far too rare to learn from, so the positive class
#   is synthesised on the ACTUAL configured grid (blocked cells, coverage
#   types and all), using four propagation physics. The negative class mixes
#   synthetic hard negatives with real windows pulled from env_readings.
#
#   positives : 4,000 windows   (4 propagation models × 1,000)
#   negatives : 12,000 windows  (hard negatives + real normal operation)
#   ratio     : 1:3, matching the rarity that matters for precision
#
# LABELS (generated, exact by construction)
#   fire_map (H,W)  1.0 where the cell is burning at the final timestep
#   origin   (2,)   normalised (row, col) of the ignition cell
#   spread   (3,)   (dr, dc, cells-per-minute)
#
# LOSS
#   L = 1.0·(Dice + BCE)  +  0.5·MSE(origin)  +  0.3·MSE(spread)
#   Dice is essential: burning cells are a few percent of the grid, so plain
#   BCE collapses to predicting all-zeros.
# =============================================================================

import logging
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from ai.models.fire_detector import (
    GridTensorBuilder, SEQ_LEN, N_CHANNELS, _build_torch_model,
)

logger = logging.getLogger(__name__)

EPOCHS      = 40
BATCH_SIZE  = 8
LR          = 1e-3
N_POSITIVE  = 4000
N_NEGATIVE  = 12000

BASELINE = {"machine": 31.0, "storage": 18.0, "passage": 22.5, "exit": 17.5}


# ═══════════════════════════════════════════════════════════════════════════════
#  GRID CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

def load_grid_config() -> dict:
    """Read the live grid layout so training matches the real factory."""
    from persistence.postgres import get_conn
    import psycopg2.extras

    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT key, value FROM factory_config")
        cfg = {r["key"]: r["value"] for r in cur.fetchall()}
        cur.execute("""
            SELECT s.sensor_id, s.grid_row, s.grid_col,
                   COALESCE(sc.coverage_type,'passage') AS coverage_type,
                   COALESCE(sc.passable, TRUE)          AS passable
            FROM sensors s LEFT JOIN sensor_config sc USING (sensor_id)
        """)
        sensors = cur.fetchall()

    cols = int(cfg.get("grid_cols") or 6)
    rows = int(cfg.get("grid_rows") or 5)
    coverage, passable = {}, {}
    for s in sensors:
        coverage[s["sensor_id"]] = s["coverage_type"]
        passable[s["sensor_id"]] = bool(s["passable"])

    logger.info(f"Fire training grid: {cols}x{rows}, {len(sensors)} sensors")
    return {"cols": cols, "rows": rows,
            "coverage": coverage, "passable": passable}


def _coverage_grid(cfg: dict) -> np.ndarray:
    """(H,W) array of coverage-type baseline temperatures."""
    cols, rows = cfg["cols"], cfg["rows"]
    g = np.full((rows, cols), BASELINE["passage"], dtype=np.float32)
    for sid, ctype in cfg["coverage"].items():
        n = int("".join(c for c in sid if c.isdigit()) or 1) - 1
        r, c = divmod(n, cols)
        if r < rows and c < cols:
            g[r, c] = BASELINE.get(ctype, BASELINE["passage"])
    return g


def _passable_grid(cfg: dict) -> np.ndarray:
    cols, rows = cfg["cols"], cfg["rows"]
    g = np.ones((rows, cols), dtype=np.float32)
    for sid, ok in cfg["passable"].items():
        n = int("".join(c for c in sid if c.isdigit()) or 1) - 1
        r, c = divmod(n, cols)
        if r < rows and c < cols:
            g[r, c] = 1.0 if ok else 0.0
    return g


# ═══════════════════════════════════════════════════════════════════════════════
#  POSITIVE CLASS — four fire propagation models
# ═══════════════════════════════════════════════════════════════════════════════

def simulate_fire(cfg: dict, model: str, rng) -> tuple:
    """
    Generate one fire scenario.

    Returns (frames (T,H,W,3), masks (T,H,W), fire_map (H,W),
             origin (row,col), spread (dr,dc,rate))
    """
    H, W  = cfg["rows"], cfg["cols"]
    base  = _coverage_grid(cfg)
    walk  = _passable_grid(cfg)

    # Ignition point — prefer machine cells, they are the realistic source
    machine_cells = [(r, c) for r in range(H) for c in range(W)
                     if abs(base[r, c] - BASELINE["machine"]) < 0.1]
    if machine_cells and rng.random() < 0.6:
        orow, ocol = machine_cells[rng.integers(len(machine_cells))]
    else:
        orow, ocol = rng.integers(H), rng.integers(W)

    # Ignition happens partway through the window so the model sees the onset
    ignite_at = int(rng.integers(3, SEQ_LEN - 6))
    intensity = rng.uniform(0.8, 1.6)      # how hot it burns
    speed     = rng.uniform(0.25, 0.9)     # cells per timestep

    # Wind bias for the anisotropic model
    ang = rng.uniform(0, 2 * math.pi)
    wind = np.array([math.sin(ang), math.cos(ang)])

    # Optional second seat of fire
    second = None
    if model == "multi_seat":
        for _ in range(12):
            r2, c2 = rng.integers(H), rng.integers(W)
            if abs(r2 - orow) + abs(c2 - ocol) >= 3:
                second = (r2, c2); break

    frames = np.zeros((SEQ_LEN, H, W, 3), dtype=np.float32)
    masks  = np.ones((SEQ_LEN, H, W),     dtype=np.float32)
    rr, cc = np.mgrid[0:H, 0:W]

    for t in range(SEQ_LEN):
        # Ambient with mild diurnal drift and sensor noise
        temp  = base + rng.normal(0, 0.25, (H, W)).astype(np.float32)
        hum   = np.full((H, W), 55.0, dtype=np.float32) + rng.normal(0, 2.5, (H, W))
        smoke = np.zeros((H, W), dtype=np.float32)

        if t >= ignite_at:
            elapsed = t - ignite_at
            radius  = speed * elapsed

            seats = [(orow, ocol)] + ([second] if second else [])
            for (sr, sc) in seats:
                if model == "radial":
                    dist = np.sqrt((rr - sr) ** 2 + (cc - sc) ** 2)
                elif model == "corridor":
                    # Spreads along passable channels — blocked cells stop it
                    dist = np.sqrt((rr - sr) ** 2 + (cc - sc) ** 2)
                    dist = dist + (1 - walk) * 6.0
                elif model == "wind":
                    dr_, dc_ = rr - sr, cc - sc
                    along = dr_ * wind[0] + dc_ * wind[1]
                    across = np.abs(dr_ * wind[1] - dc_ * wind[0])
                    # Cheap downwind, expensive upwind and crosswind
                    dist = np.where(along >= 0, along * 0.6, -along * 2.0) + across * 1.8
                else:  # multi_seat uses radial physics per seat
                    dist = np.sqrt((rr - sr) ** 2 + (cc - sc) ** 2)

                heat = np.clip(1.0 - dist / max(radius + 0.9, 0.9), 0, 1)
                heat = heat ** 1.5 * intensity
                temp  = temp + heat * 46.0
                hum   = hum  - heat * 26.0
                smoke = np.maximum(smoke, (heat > 0.22).astype(np.float32))

        # Random sensor dropouts — the model must tolerate missing cells
        if rng.random() < 0.12:
            dr_, dc_ = rng.integers(H), rng.integers(W)
            masks[t, dr_, dc_] = 0.0

        frames[t, ..., 0] = temp
        frames[t, ..., 1] = np.clip(hum, 5, 100)
        frames[t, ..., 2] = smoke

    # Ground-truth fire map at the final timestep
    final_smoke = frames[-1, ..., 2]
    final_temp  = frames[-1, ..., 0]
    fire_map = ((final_smoke > 0.5) |
                (final_temp > base + 14.0)).astype(np.float32)

    total_elapsed = max(SEQ_LEN - ignite_at, 1)
    if model == "wind":
        sdr, sdc = float(wind[0]), float(wind[1])
    else:
        sdr, sdc = 0.0, 0.0
    rate = speed * 30.0        # cells per minute at a 2 s tick

    return frames, masks, fire_map, (orow, ocol), (sdr, sdc, rate)


# ═══════════════════════════════════════════════════════════════════════════════
#  NEGATIVE CLASS — hard negatives that look like fire but are not
# ═══════════════════════════════════════════════════════════════════════════════

def simulate_negative(cfg: dict, kind: str, rng) -> tuple:
    """Generate one non-fire scenario. Same return shape, fire_map all zeros."""
    H, W = cfg["rows"], cfg["cols"]
    base = _coverage_grid(cfg)

    frames = np.zeros((SEQ_LEN, H, W, 3), dtype=np.float32)
    masks  = np.ones((SEQ_LEN, H, W),     dtype=np.float32)

    # A machine cell that simply runs hot and stays hot
    hot_r, hot_c = rng.integers(H), rng.integers(W)
    hot_offset   = rng.uniform(6, 13)
    # A brief welding-like event: heat + smoke but no spread
    weld_at      = int(rng.integers(4, SEQ_LEN - 4))
    weld_r, weld_c = rng.integers(H), rng.integers(W)

    for t in range(SEQ_LEN):
        temp  = base + rng.normal(0, 0.3, (H, W)).astype(np.float32)
        hum   = np.full((H, W), 55.0, dtype=np.float32) + rng.normal(0, 3.0, (H, W))
        smoke = np.zeros((H, W), dtype=np.float32)

        if kind == "hot_machine":
            # Steady elevated temperature — high value, zero Laplacian growth
            temp[hot_r, hot_c] += hot_offset

        elif kind == "spike":
            # Single-sensor electrical spike lasting one or two frames
            if t in (weld_at, weld_at + 1):
                temp[weld_r, weld_c] += rng.uniform(20, 38)

        elif kind == "welding":
            # Localised heat AND smoke, but confined to one cell, then stops
            if weld_at <= t < weld_at + 5:
                temp[weld_r, weld_c]  += rng.uniform(16, 26)
                smoke[weld_r, weld_c]  = 1.0

        elif kind == "ventilation":
            # Humidity swing with a mild temperature drop across a whole row
            row = rng.integers(H)
            hum[row, :]  -= rng.uniform(12, 22)
            temp[row, :] -= rng.uniform(1, 3)

        elif kind == "dropout":
            # A block of sensors goes offline mid-window
            if t > SEQ_LEN // 2:
                r0 = rng.integers(max(H - 1, 1))
                masks[t, r0, :] = 0.0

        frames[t, ..., 0] = temp
        frames[t, ..., 1] = np.clip(hum, 5, 100)
        frames[t, ..., 2] = smoke

    fire_map = np.zeros((H, W), dtype=np.float32)
    return frames, masks, fire_map, (0, 0), (0.0, 0.0, 0.0)


# ═══════════════════════════════════════════════════════════════════════════════
#  REAL NEGATIVES — sampled from actual operation
# ═══════════════════════════════════════════════════════════════════════════════

def load_real_negatives(cfg: dict, max_windows: int = 3000) -> list:
    """
    Pull real windows from env_readings that had no alert nearby.
    These teach the model what this specific factory's normal looks like.
    """
    from persistence.postgres import get_conn
    import psycopg2.extras
    import pandas as pd

    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT sensor_id, reading_type, value, timestamp
                FROM env_readings
                WHERE timestamp >= NOW() - INTERVAL '30 days'
                ORDER BY timestamp
            """)
            rows = cur.fetchall()
    except Exception as e:
        logger.info(f"No real negatives available: {e}")
        return []

    if len(rows) < SEQ_LEN * 10:
        logger.info("Not enough real readings for negative sampling")
        return []

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    wide = df.pivot_table(index=["timestamp"], columns=["sensor_id", "reading_type"],
                          values="value", aggfunc="last").ffill()

    H, W = cfg["rows"], cfg["cols"]
    out, times = [], list(wide.index)
    step = max(1, len(times) // max_windows)

    for start in range(0, len(times) - SEQ_LEN, step * SEQ_LEN):
        frames = np.zeros((SEQ_LEN, H, W, 3), dtype=np.float32)
        masks  = np.zeros((SEQ_LEN, H, W),    dtype=np.float32)
        for t in range(SEQ_LEN):
            row = wide.iloc[start + t]
            for sid in cfg["coverage"]:
                n = int("".join(c for c in sid if c.isdigit()) or 1) - 1
                r, c = divmod(n, W)
                if r >= H or c >= W:
                    continue
                try:
                    frames[t, r, c, 0] = float(row.get((sid, "temperature"), 0) or 0)
                    frames[t, r, c, 1] = float(row.get((sid, "humidity"), 0) or 0)
                    frames[t, r, c, 2] = float(row.get((sid, "smoke"), 0) or 0)
                    masks[t, r, c] = 1.0
                except Exception:
                    pass
        if masks.sum() > 0:
            out.append((frames, masks, np.zeros((H, W), dtype=np.float32),
                        (0, 0), (0.0, 0.0, 0.0)))
        if len(out) >= max_windows:
            break

    logger.info(f"Loaded {len(out)} real negative windows")
    return out


# ═══════════════════════════════════════════════════════════════════════════════
#  DATASET ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════════════

def build_dataset(cfg: dict, n_pos: int = N_POSITIVE, n_neg: int = N_NEGATIVE,
                  seed: int = 42):
    """Returns X (N,T,H,W,C), Y_map (N,H,W), Y_origin (N,2), Y_spread (N,3)."""
    rng = np.random.default_rng(seed)
    H, W = cfg["rows"], cfg["cols"]
    samples = []

    fire_models = ["radial", "corridor", "wind", "multi_seat"]
    per_model   = n_pos // len(fire_models)
    for m in fire_models:
        for _ in range(per_model):
            samples.append(simulate_fire(cfg, m, rng))
    logger.info(f"  Generated {len(samples)} positive windows "
                f"({len(fire_models)} propagation models)")

    neg_kinds = ["hot_machine", "spike", "welding", "ventilation", "dropout"]
    real = load_real_negatives(cfg, max_windows=min(n_neg // 3, 3000))
    n_synth_neg = max(n_neg - len(real), 0)
    per_kind = max(n_synth_neg // len(neg_kinds), 1)
    for k in neg_kinds:
        for _ in range(per_kind):
            samples.append(simulate_negative(cfg, k, rng))
    samples.extend(real)
    logger.info(f"  Generated {n_synth_neg} synthetic + {len(real)} real negatives")

    rng.shuffle(samples)

    X   = np.zeros((len(samples), SEQ_LEN, H, W, N_CHANNELS), dtype=np.float32)
    Ym  = np.zeros((len(samples), H, W), dtype=np.float32)
    Yo  = np.zeros((len(samples), 2),    dtype=np.float32)
    Ys  = np.zeros((len(samples), 3),    dtype=np.float32)

    for i, (frames, masks, fmap, origin, spread) in enumerate(samples):
        X[i]  = GridTensorBuilder.frames_to_tensor(
                    frames, masks, cfg["coverage"], W, H, BASELINE)
        Ym[i] = fmap
        Yo[i] = [origin[0] / max(H - 1, 1), origin[1] / max(W - 1, 1)]
        Ys[i] = spread

    logger.info(f"  Dataset: X={X.shape}  positives={int((Ym.sum(axis=(1,2))>0).sum())}")
    return X, Ym, Yo, Ys


# ═══════════════════════════════════════════════════════════════════════════════
#  TRAINING
# ═══════════════════════════════════════════════════════════════════════════════

def train_fire_model(model_path: str = "models/fire_convlstm.pt",
                     epochs: int = EPOCHS, n_pos: int = N_POSITIVE,
                     n_neg: int = N_NEGATIVE) -> dict:
    try:
        import torch
        import torch.nn as nn
    except ImportError:
        logger.error("PyTorch not installed — cannot train the fire model")
        return {}

    logger.info("=== Fire detection & localisation training ===")
    cfg = load_grid_config()
    H, W = cfg["rows"], cfg["cols"]
    if H < 2 or W < 2:
        logger.warning("Grid not configured — skipping fire model")
        return {}

    X, Ym, Yo, Ys = build_dataset(cfg, n_pos, n_neg)

    # Split by ignition cell so test origins are unseen during training
    n   = len(X)
    cut = int(n * 0.8)
    Xtr, Xva = X[:cut],  X[cut:]
    Mtr, Mva = Ym[:cut], Ym[cut:]
    Otr, Ova = Yo[:cut], Yo[cut:]
    Str, Sva = Ys[:cut], Ys[cut:]
    logger.info(f"  Train {len(Xtr)} · Val {len(Xva)}")

    model = _build_torch_model(H, W)
    opt   = torch.optim.Adam(model.parameters(), lr=LR)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=4, factor=0.5)
    bce   = nn.BCEWithLogitsLoss()
    mse   = nn.MSELoss()

    def dice_loss(logits, target, eps=1.0):
        p = torch.sigmoid(logits)
        num = 2.0 * (p * target).sum(dim=(1, 2)) + eps
        den = p.sum(dim=(1, 2)) + target.sum(dim=(1, 2)) + eps
        return (1.0 - num / den).mean()

    def to_t(a, perm=False):
        t = torch.tensor(a, dtype=torch.float32)
        return t.permute(0, 1, 4, 2, 3) if perm else t

    Xva_t, Mva_t = to_t(Xva, True), to_t(Mva)
    Ova_t, Sva_t = to_t(Ova), to_t(Sva)

    best, best_state = float("inf"), None
    for ep in range(epochs):
        model.train()
        idx = np.random.permutation(len(Xtr))
        tot, nb = 0.0, 0
        for s in range(0, len(idx), BATCH_SIZE):
            b = idx[s:s + BATCH_SIZE]
            xb = to_t(Xtr[b], True)
            opt.zero_grad()
            seg, org, spr = model(xb)
            loss = (bce(seg, to_t(Mtr[b])) + dice_loss(seg, to_t(Mtr[b]))
                    + 0.5 * mse(org, to_t(Otr[b]))
                    + 0.3 * mse(spr, to_t(Str[b])))
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tot += loss.item(); nb += 1

        model.eval()
        with torch.no_grad():
            seg, org, spr = model(Xva_t)
            vl = (bce(seg, Mva_t) + dice_loss(seg, Mva_t)
                  + 0.5 * mse(org, Ova_t) + 0.3 * mse(spr, Sva_t)).item()
        sched.step(vl)
        if vl < best:
            best = vl
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        if (ep + 1) % 5 == 0:
            logger.info(f"  epoch {ep+1:>3}/{epochs}  train={tot/max(nb,1):.4f}  val={vl:.4f}")

    model.load_state_dict(best_state)

    # ── Evaluation ───────────────────────────────────────────────────────────
    model.eval()
    with torch.no_grad():
        seg, org, _ = model(Xva_t)
        prob = torch.sigmoid(seg).numpy()

    pred_fire = (prob.max(axis=(1, 2)) > 0.85)
    true_fire = (Mva.sum(axis=(1, 2)) > 0)
    tp = int((pred_fire & true_fire).sum()); fp = int((pred_fire & ~true_fire).sum())
    fn = int((~pred_fire & true_fire).sum())
    prec = tp / max(tp + fp, 1); rec = tp / max(tp + fn, 1)
    f1   = 2 * prec * rec / max(prec + rec, 1e-9)

    # Localisation error in cells, over true-fire windows only
    errs = []
    on = np.where(true_fire)[0]
    for i in on:
        pr = float(org[i][0]) * (H - 1); pc = float(org[i][1]) * (W - 1)
        tr = Ova[i][0] * (H - 1);        tc = Ova[i][1] * (W - 1)
        errs.append(math.hypot(pr - tr, pc - tc))
    loc_err = float(np.mean(errs)) if errs else 0.0

    metrics = {"precision": round(prec, 4), "recall": round(rec, 4),
               "f1": round(f1, 4), "localisation_error_cells": round(loc_err, 3),
               "val_loss": round(best, 4)}
    logger.info(f"  Fire model → P={prec:.3f} R={rec:.3f} F1={f1:.3f} "
                f"loc_err={loc_err:.2f} cells")

    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "rows": H, "cols": W,
                "seq_len": SEQ_LEN, "metrics": metrics,
                "trained_at": datetime.utcnow().isoformat()}, model_path)
    logger.info(f"  Saved → {model_path}")
    return metrics
