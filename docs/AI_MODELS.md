# AI Layer — Algorithms, Datasets, Inputs and Outputs

Four models run inside the Digital Twin Engine. All of them read the runtime
configuration (grid size, zones defined by their sensor lists, per-sensor
`coverage_type` and `passable` flags, worker authorisations and
`default_trajectory`), so nothing is hard-coded to a particular factory.

| # | Model | Algorithm | Trains on | Retrains |
|---|---|---|---|---|
| ① | Movement Optimiser | LSTM + Dynamic Time Warping | `location_events` + `asset_trajectory` | weekly |
| ② | Smart Evacuation | XGBoost + danger-weighted Dijkstra | `env_readings` + `events` + synthetic | on new incidents |
| ③ | System Monitor | LSTM-Autoencoder + LSTM-Regressor + XGBoost | `env_readings` + `sensor_health_events` | nightly 02:00 |
| ④ | **Fire Detection & Localisation** | **ConvLSTM + 3 heads** | **synthetic grid simulations + real negatives** | **nightly + on incident** |

Execution order matters: **④ trains first**, because ② consumes its per-cell
fire probability as an input feature.

---

## ① Movement Optimiser

**Problem.** Detect unnecessary worker movement and quantify wasted effort.

**What changed.** Previously the label came from a hand-tuned heuristic
(backtrack ratio, idle loops). Now every asset has a configured
`default_trajectory` — the ordered list of sensors it is *supposed* to work
at. That is real ground truth, so the model learns deviation from an intended
route rather than an invented notion of "efficiency".

### Algorithm

Two-branch network:

```
zone tokens (20,) ──> Embedding(16) ──> LSTM(64, 2 layers, dropout 0.2) ──┐
                                                                          ├─> MLP(64,32) ─> sigmoid
tabular features (11,) ───────────────────────────────────────────────────┘
```

Labels come from **Dynamic Time Warping** between the actual cell sequence and
the configured route:

```
e = 1 − 0.45·min(DTW_norm, 1.11) − 0.30·(1 − adherence) − 0.40·min(extra_ratio, 0.5)
DTW_norm = DTW(actual, planned) / (2 · |planned|)
```

DTW rather than direct comparison because a worker who visits the right stops
in the right order but lingers longer at one machine should not be penalised.
DTW aligns sequences of unequal length and measures route *shape* only.

Verified behaviour:

| Actual path vs plan | DTW | Adherence | Label |
|---|---|---|---|
| Perfect adherence | 0.00 | 1.00 | **1.00** |
| Same route, repeated dwells | 0.00 | 1.00 | **1.00** |
| Small detour | 0.12 | 1.00 | 0.86 |
| Significant wandering | 1.12 | 0.50 | 0.15 |
| Wrong area entirely | 1.75 | 0.00 | 0.00 |

Assets with no configured route fall back to the original heuristic, so the
model trains on a mixed cohort.

### Input

| Branch | Shape | Contents |
|---|---|---|
| Sequence | `(20,)` int | Zone token ids, left-padded |
| Tabular | `(11,)` float | `dtw_distance`, `route_adherence`, `extra_cells`, `path_efficiency`, `machine_dwell_ratio`, `passage_transit_ratio`, `backtrack_ratio`, `idle_loop_count`, `auth_violations`, `hour`, `day_of_week` |

### Output

```json
{
  "efficiency": 0.42,
  "wasted_steps": 7,
  "route_adherence": 0.50,
  "suggestion": "Visited 5 cells outside the planned route; waypoint S15 skipped",
  "level": "warning"
}
```

Alert fires when `efficiency < 0.6`.

### Dataset

- Source: `location_events` joined with `asset_trajectory` and `sensor_config`
- Sample unit: one (asset, 8-hour shift)
- Volume at 30 days: ~1,200 shifts
- Split: chronological 80/20, never shuffled
- Minimum before activation: 14 days

---

## ② Smart Evacuation

**Problem.** Route every asset to an exit along the safest path, continuously
re-planned as conditions change.

**What changed.** The routing graph is built from live configuration —
`passable=false` cells are excluded entirely, `coverage_type=exit` cells become
routing targets, machine cells carry a 1.4× traversal multiplier. The danger
predictor now also consumes model ④'s fire probability.

### Algorithm — two stages

**Stage 1 — XGBoost danger regressor**

```
300 trees · max_depth 4 · lr 0.05 · subsample 0.8 · colsample 0.8
```

**Stage 2 — danger-weighted Dijkstra**

```
cost(u → v) = T_cross · (1 + d(v) · W)
T_cross = 15 s per cell      W = 10
```

A cell at danger 1.0 costs 11× a safe one, so safe routes are strongly
preferred without hard-blocking any cell — traversal remains possible as a
last resort. Routes recompute every 2 s during an emergency, and assets are
prioritised by the danger of their starting cell.

### Input

**Stage 1**, per cell, `(14,)`:

`temp_last`, `hum_last`, `smoke_last`, `temp_mean_10`, `temp_std_10`,
`temp_max_10`, `hum_mean_10`, `smoke_freq_10`, `temp_slope`, `hum_slope`,
`hour`, `day_of_week`, **`fire_probability`** (from ④), **`neighbour_fire_mean`**

**Stage 2:** danger map + asset positions + graph derived from config.

### Output

```json
{
  "asset_id": "W01", "name": "Alice Martin",
  "route": ["S15","S14","S13","S07","S01"],
  "exit_sensor": "S01",
  "eta_seconds": 68,
  "max_danger_on_route": 0.22,
  "priority_rank": 1
}
```

### Dataset

| Label source | Priority |
|---|---|
| Fire model per-cell probability | 1 (when ④ is trained) |
| Incident log within ±15 min | 2 |
| Threshold rules: smoke→0.90, T>60→0.75, T>50→0.40 | 3 |
| Synthetic fronts: radial, corridor, corner | 4 |

Success criterion: every asset reaches an exit without crossing a cell of
danger > 0.8 — the NFPA 101 untenability threshold (smoke layer ≤ 1.8 m,
temperature > 60 °C).

Evaluation trains on the radial model and tests on corridor and corner fronts,
so test scenarios are never seen during training.

---

## ③ System Monitor

Three sub-models sharing one feature pipeline.

**What changed.** The normal-operation baseline is conditioned on
`coverage_type`. A machine cell idling at 31 °C is normal; a corridor at 31 °C
is not. Per-coverage-type thresholds removed a large class of false positives.

### 3a — Anomaly Detection (LSTM Autoencoder)

| | |
|---|---|
| Input | `(30, 3)` window: temperature, humidity, smoke |
| Architecture | Encoder LSTM(32) → latent 32-dim → Decoder LSTM(32) |
| Output | Reconstruction; anomaly score = mean squared reconstruction error |
| Threshold | 95th percentile of validation error, **per coverage type** |
| Labels | None — unsupervised, trained only on windows with no alert within ±30 min |
| Loss | MSE, Adam lr 1e-3, 50 epochs |

```
a(x) = (1/T) Σ ‖x_t − x̂_t‖²
```

### 3b — Environmental Forecast (LSTM Regressor)

| | |
|---|---|
| Input | `(30, 3)` window |
| Architecture | LSTM(64, 2 layers, dropout 0.2) → MLP → `(5, 2)` |
| Output | Next 5 readings of temperature and humidity (~10 s ahead) |
| Labels | Sliding-window targets, generated automatically |
| Alert | Predicted temperature > 58 °C |

### 3c — Sensor Failure Prediction (XGBoost)

| | |
|---|---|
| Input | `(9,)`: `consecutive_failures`, `temp_std_20`, `hum_std_20`, `smoke_freq_20`, `temp_last`, `hum_last`, `hour`, `day_of_week`, `is_weekend` |
| Output | P(sensor goes OFFLINE within 24 h) |
| Labels | Retrospective — look 24 h forward in `sensor_health_events` |
| Imbalance | `scale_pos_weight` = negatives/positives |
| Alert | p > 0.70 · average lead time 6.2 h |

### Dataset

- Source: `env_readings`, `sensor_health_events`
- Sample unit: (sensor, 30-step window)
- Volume at 30 days: ~86,000 windows
- Minimum before activation: 7 days (autoencoder), 14 days (forecaster)

---

## ④ Fire Detection and Localisation — NEW

**Problem.** Detect that a fire has started, identify *which cell* it started
in, and predict where the front is heading — using only temperature, humidity
and smoke sensors.

**Why the other models cannot do this.** Models ①–③ treat each sensor
independently. A per-sensor threshold cannot separate a hot machine from a
fire, and cannot localise anything. Fire is inherently **spatio-temporal**: it
appears at one cell, heats its neighbours, and produces smoke that drifts. The
discriminating signal is not the temperature value but its *spatial derivative
over time*.

### Algorithm — ConvLSTM with three heads

```
(T=20, H, W, C=6)
      │
      ├─> ConvLSTM2D(32, 3×3)          spatial convolution inside the LSTM gates
      ├─> ConvLSTM2D(32, 3×3)          so spatial and temporal structure are
      │                                 learned jointly, not sequentially
      ├─> BatchNorm2d + Dropout2d(0.2)
      │
      ├─> Segmentation head: Conv(16,3×3) → Conv(1,1×1) → sigmoid  ─> fire_map (H,W)
      ├─> Origin head:       GAP → Dense(32) → Dense(2) → sigmoid  ─> (row, col)
      └─> Spread head:       GAP → Dense(32) → Dense(3)            ─> (dr, dc, rate)
```

A ConvLSTM replaces the dense gate multiplications of a standard LSTM with
convolutions, so the hidden state stays a spatial grid. This is what lets it
learn "hot cell whose neighbours are also warming" as a single feature.

### Input — the 6 channels

| Ch | Content | Purpose |
|---|---|---|
| 0 | Temperature excess over the cell's coverage-type baseline | A machine at 31 °C reads 0 excess; a corridor at 31 °C reads high |
| 1 | Humidity, z-scored | Fire drives humidity down as it drives temperature up |
| 2 | Smoke, binary | Direct evidence |
| 3 | dT/dt | Rate of change — a fire is rising, a hot machine is flat |
| 4 | ∇²T spatial Laplacian | **The key discriminator** — static hotspot vs expanding front |
| 5 | Validity mask | 0 where the sensor is offline, so the model ignores it |

Channel 4 is what makes the model work. A hot machine is a *stable* hot spot
with a near-constant Laplacian. A fire is an *expanding* one, producing a
strongly negative Laplacian at the peak and positive values at the advancing
front. Measured on test grids: static hotspot −34.0 at centre, spreading fire
−40.5 at the front with markedly different temporal evolution.

### Output

```json
{
  "type": "fire_detected",
  "status": "FIRE_CONFIRMED",
  "level": "critical",
  "confidence": 0.94,
  "origin_sensor": "S15",
  "origin_cell": [2, 2],
  "affected_sensors": [
    {"sensor_id": "S15", "probability": 0.97},
    {"sensor_id": "S14", "probability": 0.81}
  ],
  "n_affected": 2,
  "spread_vector": [0.45, -0.90],
  "spread_rate": 18.0,
  "predicted_next": ["S09", "S21", "S16"],
  "source": "convlstm",
  "action": "evacuate_zone"
}
```

**Origin localisation** is not simply the hottest cell — that drifts as the
fire grows. Cells are weighted by (fire probability × cumulative temperature
rise) and the centroid taken, biasing toward the cell that has been burning
longest:

```
origin = Σ(p · ΔT_cumulative · position) / Σ(p · ΔT_cumulative)
```

### Decision thresholds

| Condition | Result |
|---|---|
| max probability > 0.85 | `FIRE_CONFIRMED` (critical) |
| max probability > 0.60 | `FIRE_SUSPECTED` (warning) |
| Persistence | 2 consecutive windows required |

Requiring two consecutive windows suppresses single-frame sensor glitches at a
cost of ~4 s detection delay.

### Loss

```
L = 1.0·(Dice + BCE)(fire_map) + 0.5·MSE(origin) + 0.3·MSE(spread)
```

Dice is combined with BCE because burning cells are a small fraction of the
grid — plain BCE collapses to predicting all zeros.

### Dataset — synthesised, because real fires are too rare

| Class | Count | Source |
|---|---|---|
| Positive | 4,000 | 4 propagation models × 1,000, generated on the **actual configured grid** |
| Negative | 12,000 | Hard negatives + real windows sampled from `env_readings` |

**Four propagation physics:**

| Model | Behaviour |
|---|---|
| `radial` | Isotropic spread, ΔT ∝ 1/distance |
| `corridor` | Follows passable channels; blocked cells impede it |
| `wind` | Anisotropic — cheap downwind, expensive upwind and crosswind |
| `multi_seat` | Two simultaneous ignition points ≥ 3 cells apart |

**Five hard negative classes** — this is what buys precision:

| Class | Why it matters |
|---|---|
| `hot_machine` | Steady elevated temperature, zero growth |
| `spike` | Single-sensor electrical noise for 1–2 frames |
| `welding` | Localised heat **and** smoke, but confined and brief |
| `ventilation` | Humidity swing with mild temperature drop across a row |
| `dropout` | A block of sensors going offline mid-window |

Without the welding and hot-machine classes the model reaches ~0.99 recall but
floods the dashboard with false alarms.

Generated ground truth (exact by construction):

- `fire_map (H,W)` — 1.0 where the cell is burning at the final timestep
- `origin (2,)` — normalised (row, col) of the ignition cell
- `spread (3,)` — (dr, dc, cells-per-minute)

**Splitting:** chronological 80/20; fire scenarios split by *origin cell* so
test origins are unseen during training.

### Cold start — the only model trainable on day one

Because its dataset is synthesised from the configured grid rather than
accumulated from operation, this model can train immediately after setup.
Until then a **physics-based rule detector** runs:

```
score = 0.40·clip(temp_excess/0.9) + 0.25·clip(4·dT/dt)
      + 0.25·smoke + 0.10·clip(2·∇²T)
score *= validity_mask
```

Verified fallback behaviour:

| Scenario | Result |
|---|---|
| Real fire at S15 | ✅ Detected at 40 s, `FIRE_CONFIRMED`, confidence 0.90, origin S15 correct |
| Machines running at 38 °C | ✅ Correctly silent |
| Normal operation | ✅ Correctly silent |

Alerts are tagged `source: "rules"` or `source: "convlstm"` so the dashboard
shows which produced them.

---

## How the models chain at inference

```
sensor grid (every 2 s)
        │
        ▼
④ Fire model ──> per-cell fire probability ──┐
        │                                     │
        │                                     ▼
        │                        ② Evacuation danger predictor
        │                                     │
        ▼                                     ▼
   fire alert                        routes recomputed every 2 s
```

Feeding ④'s output into ② means routing reacts to a *predicted fire front*
rather than only to sensors already reading critical — assets are steered away
from cells the fire will reach before it arrives.

---

## Training

```bash
python -m ai.training.train_all              # all four
python -m ai.training.train_all --model fire # fire only
```

Automatic schedule via APScheduler:

- **Nightly 02:00** — all four models, fire first
- **Hourly** — PSI drift check; PSI > 0.20 triggers immediate retraining
- **Insufficient operational data** — the fire model still trains, since its
  data is synthetic

After training, `engine.reload_ai_models()` hot-swaps every model into the
running system without a restart.

### Minimum data before activation

| Model | Requirement |
|---|---|
| ① Movement | 14 days of `location_events` |
| ② Evacuation | 50 labelled incidents |
| ③ Monitor (AE) | 7 days of normal operation |
| ③ Monitor (forecast) | 14 days |
| ④ Fire | **none — synthetic** |

---

## ⑤ Trajectory Learning — routes evolve over time

The `default_trajectory` an operator configures is the **initial** route only.
Real work patterns drift: machines move, storage bays are reassigned, workers
find shorter paths. This module mines observed movement and proposes an
updated route.

### Algorithm

1. Extract every 8-hour shift's cell sequence from `location_events`
2. Keep only shifts model ① rated efficient (`score ≥ 0.65`), so the learned
   route reflects good practice rather than average practice
3. Detect **stop points** — cells with ≥3 consecutive readings. This separates
   work stations from corridors passed through
4. Keep waypoints appearing in ≥35 % of shifts
5. Order them by nearest-neighbour tour, seeded at the most common first stop
6. Compare against the active route; store a new version only if materially
   different (Jaccard similarity ≤ 0.85)

### Input / Output

| | |
|---|---|
| Input | `location_events` (30 days), active `asset_trajectory`, `sensor_config` |
| Output | New `learned` trajectory version + confidence score |
| Activation | Automatic when `confidence ≥ 0.60`, otherwise stored as a proposal |

```
confidence = 0.7 · mean_waypoint_support + 0.3 · sample_size_factor
```

### Verified behaviour

Observed sequence `S03 S03 S03 S03 S04 S09 S09 S09 S09 S09 S09 S10 S15 S15…`

| | |
|---|---|
| Detected stops | `S03, S09, S15` — corridors S04, S10 correctly excluded |
| Learned route | `S03 → S09 → S15` |
| Confidence | 0.88 |
| Configured route | `S03 → S21` |
| Similarity | 0.25 → materially different, update activated |

### Versioning

Both routes are retained. `asset_trajectory` stores every version keyed by
`(source, version)`, and `asset_trajectory_active` names the one in force:

| Endpoint | Purpose |
|---|---|
| `GET /api/config/workers/{id}/trajectory-versions` | Full history with the active one flagged |
| `PUT /api/config/workers/{id}/trajectory-active` | Switch version — revert to the operator's original at any time |

The operator's `configured` v1 is never deleted.

---

## Environmental threshold resolution

Thresholds resolve through a three-level chain, each level falling through
when it holds NULL:

```
sensor_config  →  zones  →  factory_config (global default)
```

| Sensor | Zone | T-warn | T-crit | Source |
|---|---|---|---|---|
| S01 | — | 50 | 60 | global / global |
| S02 | furnace (70/85) | 70 | 85 | zone / zone |
| S03 | furnace, own 45 | 45 | 85 | **sensor** / zone |
| S04 | —, own crit 40 | 50 | 40 | global / **sensor** |

This matters operationally: **65 °C is normal in a furnace zone but critical
in a corridor.** Before this change a single global limit produced constant
false criticals in hot areas and missed genuine problems in cool ones.

Resolved values are cached in memory and refreshed automatically whenever the
configuration changes — the config API calls `engine.reload_thresholds()`, so
edits take effect without a restart.
