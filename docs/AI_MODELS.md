# AI Layer — Algorithms, Datasets, Inputs and Outputs

Five models run against the Digital Twin. All of them read the runtime
configuration (grid size, zones defined by their sensor lists, per-sensor
`coverage_type` and `passable` flags, worker authorisations, working stations
and trajectories), so nothing is hard-coded to a particular factory.

| # | Model | Algorithm | Trains on | Retrains |
|---|---|---|---|---|
| ① | Movement Optimiser | LSTM sequence classifier | `location_events` | nightly 02:00 |
| ② | Smart Evacuation | XGBoost + danger-weighted Dijkstra | `env_readings` + `events` + synthetic | nightly 02:00 |
| ③ | System Monitor | LSTM-Autoencoder + LSTM-Regressor (+ XGBoost, unwired) | `env_readings` | nightly 02:00 |
| ④ | **Fire Detection & Localisation** | **ConvLSTM + 3 heads** | **synthetic grid simulations + real negatives** | nightly 02:00 |
| ⑤ | Trajectory & Station Learning | stop-point clustering | `location_events` | nightly 02:00 |

There is no per-model cadence: `AITrainer` runs all five as one nightly batch,
plus whenever hourly drift detection fires. Execution order within the batch
matters — **④ trains first**, because ② is designed to consume its per-cell
fire probability.

> **Two documents, two purposes.** This file covers algorithms, feature
> derivations and evaluation. For a compact per-model card — goal, inputs,
> outputs, cadence, dataset — see
> [`AI_MODELS_REFERENCE.md`](AI_MODELS_REFERENCE.md).

> **Implementation status.** Several behaviours described below are implemented
> but not currently reachable at runtime: model ③ is never loaded into the
> engine, model ③c is never trained, model ②'s trained danger model is never
> loaded, and model ①'s DTW labelling exists but is not used by the trainer.
> Each is flagged in place, and summarised under
> [Implementation status](#implementation-status). The rule-based fallbacks
> keep the system functional regardless, which is why these are easy to miss.

---

## ① Movement Optimiser

**Problem.** Detect unnecessary worker movement and quantify wasted effort.

### Algorithm

Two-branch network (`ai/training/movement.py`):

```
zone tokens (20,) ──> Embedding(16) ──> LSTM(64, 2 layers, dropout 0.2) ──┐
                                                                          ├─> MLP(64) ─> sigmoid
tabular features (6,) ────────────────────────────────────────────────────┘
```

Trained 40 epochs, Adam at `1e-3`, batch size 32. Shifts with fewer than 5
location hops are discarded.

### Input

| Branch | Shape | Contents |
|---|---|---|
| Sequence | `(20,)` int | Zone token ids, left-padded with 0; vocabulary built at training time |
| Tabular | `(6,)` float | `backtrack_ratio`, `idle_loop_count`, `auth_violations`, `mean_dwell_secs/3600`, `hour/23`, `day_of_week/6` |

### Labels — heuristic, and this is the model's main weakness

There is no ground-truth efficiency annotation, so labels come from an
expert-specified formula (`_heuristic_label`):

```
e = 1 − min(1.5·backtrack_ratio, 0.50)
      − min(0.05·idle_loop_count,  0.30)
      − min(0.10·auth_violations,  0.20)
```

The model therefore learns to reproduce a rule from sequence context rather
than to predict human judgement. The score is meaningful *relative* to other
shifts, not in absolute terms. Real supervisor annotation would be required to
change that, and is the single most valuable thing that could be added to this
model.

> **Planned but not wired: DTW labelling against the configured route.**
> `ai/pipeline/features.py` implements `dtw_distance()`,
> `build_trajectory_features()` and `trajectory_efficiency_label()`, which
> would label a shift by how far it deviates from the asset's active
> `asset_trajectory` — real ground truth rather than an invented notion of
> efficiency. DTW is the right tool there because a worker who visits the
> right stops in the right order but lingers longer at one machine should not
> be penalised; DTW aligns sequences of unequal length and compares route
> *shape* only.
>
> Nothing calls these functions. `train_movement_model()` uses
> `build_movement_features()` + `_heuristic_label()` as above. Switching the
> trainer over is the intended next step for this model.

### Output

```json
{
  "efficiency": 0.42,
  "wasted_steps": 7,
  "level": "warning"
}
```

### Dataset

- Source: `location_events`, last 30 days (configurable via `--days`)
- Sample unit: one (asset, 8-hour shift)
- Split: chronological, never shuffled, to prevent leakage across time

---

## ② Smart Evacuation

**Problem.** Route every asset to an exit along the safest path, continuously
re-planned as conditions change.

The routing graph is built from live configuration: `coverage_type=exit` cells
become routing targets, and cell danger drives edge cost.

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

**Stage 1**, per cell, `(12,)`, from a rolling 10-reading window:

`temp_last`, `hum_last`, `smoke_last`, `temp_mean_10`, `temp_std_10`,
`temp_max_10`, `hum_mean_10`, `smoke_freq_10`, `temp_slope`, `hum_slope`,
`hour`, `day_of_week`

**Stage 2:** danger map + asset positions + graph derived from config.

> **Fire coupling is designed but not wired.** `smart_evacuation.py` provides
> `attach_fire_map()` and `fire_adjusted_danger()` so ④'s per-cell fire
> probability can raise danger at inference time, and `engine.py` calls
> `set_fire_map()` on the evacuation model. But `build_danger_dataset()` does
> not include any fire feature (12 features, listed above), and the engine's
> `_evac_model` is never constructed, so the call never executes. The
> ④-before-② training order is therefore correct in intent but currently
> carries no data dependency.

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

- Source: `env_readings` over the last 90 days, joined against incident records
  in `events`; a reading is labelled dangerous when it falls within 15 minutes
  of a recorded incident at that sensor.
- Augmented with 200 synthetic fire samples and 500 synthetic normal samples,
  because real incidents are rare by design — a factory generating enough
  fires to train on has a larger problem than routing.
- Threshold rules supply the label where no incident record applies:
  smoke → 0.90, T > 60 °C → 0.75, T > 50 °C → 0.40.

Success criterion: every asset reaches an exit without crossing a cell of
danger > 0.8 — the NFPA 101 untenability threshold (smoke layer ≤ 1.8 m,
temperature > 60 °C).

Evaluation trains on the radial model and tests on corridor and corner fronts,
so test scenarios are never seen during training.

---

## ③ System Monitor

Three sub-models sharing one feature pipeline.

Normalisation is per sensor, using scalers fitted once over all training data
and saved alongside the models, so training and inference agree.

> **Not conditioned on coverage type.** A machine cell idling at 31 °C is
> normal while a corridor at 31 °C is not, so conditioning the normal-operation
> baseline on `coverage_type` would remove a class of false positives.
> `ai/training/monitor.py` does not do this — it fits one scaler set across all
> sensors regardless of coverage. Model ④ *does* use per-coverage-type
> baselines (channel 0); model ③ does not.

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

> **Not currently trained.** `train_failure_predictor()` is implemented in
> `ai/models/system_monitor.py`, but `train_monitor_models()` trains only the
> autoencoder and the forecaster, and nothing else calls it. No
> `failure_xgb.joblib` is ever produced, so the inference path that would read
> it is unreachable. Described here because the design is complete and the
> wiring is a single missing call.

| | |
|---|---|
| Input | `consecutive_failures` (from the watchdog), reading variance over the last 20 readings, time since last reading, temp/humidity/smoke mean and std, `hour`, `day_of_week` |
| Output | P(sensor goes OFFLINE within 24 h) |
| Labels | Retrospective — did this sensor go OFFLINE within 24 h of this reading? |
| Imbalance | `scale_pos_weight` = negatives/positives |
| Alert | p > 0.70 |

### Dataset

- Source: `env_readings` (autoencoder and forecaster); the failure predictor
  would additionally use `sensor_health_events`
- Sample unit: (sensor, 30-step window)
- The autoencoder trains on **normal-operation windows only**; the forecaster
  trains on all windows
- Guards in `train_monitor_models()`: ≥ 50 sequences for the autoencoder,
  ≥ 100 pairs for the forecaster, otherwise that sub-model is skipped with a
  warning
- Scalers are fitted once over all data and saved as `monitor_scalers.joblib`,
  so training and inference normalise identically

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

Alerts are tagged `source: "rules"` or `source: "convlstm"` so the dashboard
shows which produced them.

> The rule detector's behaviour on simulated fires, hot machines and normal
> operation has not been measured by the benchmark harness; no figures are
> quoted here for that reason. Model ④ as a whole has never been evaluated
> against a real fire — its positive class is entirely synthetic.

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

Feeding ④'s output into ② would mean routing reacts to a *predicted fire front*
rather than only to sensors already reading critical — assets steered away from
cells the fire will reach before it arrives. This is the intent of the
`set_fire_map()` call in `engine.py`; see the note under ② for why it does not
currently execute.

---

## Training

```bash
python -m ai.training.train_all                  # all five
python -m ai.training.train_all --model fire     # one
# choices: all | movement | evacuation | monitor | fire | trajectory
python -m ai.training.train_all --days 60        # widen the extraction window
```

Automatic schedule via APScheduler (`ai/training/trainer.py`):

- **Nightly 02:00 UTC** — one batch, in order: ④ fire → ① movement →
  ⑤ trajectory → ② evacuation → ③ monitor
- **Hourly at :00** — PSI drift check; PSI > 0.20 triggers a full retrain
- **Under 7 days of `env_readings`** — only ④ trains, since its data is
  synthetic; the rest are skipped until enough history exists

Drift is computed over `env_readings`, comparing the last 7 days against the
30 before that, per reading type (`temperature`, `humidity`) with 10 bins,
taking the maximum:

```
PSI = Σᵢ (cᵢ − bᵢ) · ln(cᵢ / bᵢ)
```

After training, `engine.reload_ai_models()` swaps new artefacts into the
running system without a restart — but see
[Implementation status](#implementation-status): it currently reloads only ①
and ④.

### Minimum data before a model is useful

| Model | Requirement |
|---|---|
| ① Movement | 7 days before the batch runs at all; ~14 days before it beats its rule-based fallback |
| ② Evacuation | 7 days; quality depends on incident records, which are augmented with 700 synthetic samples |
| ③ Monitor (AE) | ≥ 50 normal-operation sequences |
| ③ Monitor (forecast) | ≥ 100 window/target pairs |
| ④ Fire | **none — synthetic** |
| ⑤ Trajectory & station | ≥ 5 qualifying 8-hour shifts per asset |

---

## ⑤ Trajectory & Station Learning — routes and stations evolve over time

The `default_trajectory` and the working `station` an operator configures are
the **initial** values only. Real work patterns drift: machines move, storage
bays are reassigned, workers find shorter paths. This module mines observed
movement and proposes both an updated route and an updated station.

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

### Worked example

Observed sequence `S03×4  S04  S09×6  S10  S15×5`, repeated over 6 shifts
(reproduce with `learn_route` in `ai/training/trajectory.py`):

| | |
|---|---|
| Detected stops | `S03, S09, S15` — corridors S04, S10 correctly excluded |
| Learned route | `S03 → S09 → S15` |
| Confidence | 0.82 |
| Configured route | `S03 → S21` |
| Similarity | 0.25 → materially different, update activated |

### Working station — *where* the asset works

The route answers "in what order does it move?". The **working station**
answers "where does it work?" — the unordered **set** of cells the asset
spends most of its time at, with a weight per cell.

A worker is assigned to a station (a machine and the cells around it); the
trajectory is how they move across stations. The two are learned from the same
observed dwell but **independently**: a worker can keep the same tour while the
cells they dwell at drift, and vice versa.

```
station weight(cell) = dwell(cell) / Σ dwell(kept cells)
```

Dwell is counted only inside runs of ≥ `DWELL_THRESHOLD` consecutive readings,
so corridors passed through score zero. A cell must appear in ≥35 % of shifts
(`MIN_STOP_SUPPORT`) to be kept, and at most `MAX_STATION_CELLS` (6) survive —
a station is an area, not half the factory.

| | |
|---|---|
| Input | `location_events` (30 days) |
| Output | New `learned` station version + per-cell weights + confidence |
| Activation | Automatic when `confidence ≥ 0.60`, otherwise stored as a proposal |

Confidence uses the same formula as the route.

#### Worked example

Observed sequence `S03×4  S04  S09×6  S10  S15×5`, repeated over 6 shifts:

| | |
|---|---|
| Learned station | `S09 40 %`, `S15 33 %`, `S03 27 %` |
| Corridors `S04`, `S10` | excluded — never dwelled at |
| Confidence | 0.82 |

Round-tripped against the simulator: configuring a station of
`S09 50 % · S15 30 % · S03 20 %`, generating 8 shifts of movement and feeding
them back recovers all three cells at confidence 0.75. Note the *ordering* of
learned weights need not match the configured ones — a patrol visits its two
endpoint waypoints half as often as its interior ones, so total occupancy
reflects route topology as well as per-visit dwell.

### Versioning

Both routes and both stations are retained. `asset_trajectory` and
`asset_station` store every version keyed by `(source, version)`, and
`asset_trajectory_active` / `asset_station_active` name the ones in force:

| Endpoint | Purpose |
|---|---|
| `GET /api/config/workers/{id}/trajectory-versions` | Full route history with the active one flagged |
| `PUT /api/config/workers/{id}/trajectory-active` | Switch route version — revert to the operator's original at any time |
| `GET /api/config/workers/{id}/station-versions` | Full station history with the active one flagged |
| `PUT /api/config/workers/{id}/station-active` | Switch station version — revert to the operator's original at any time |

The operator's `configured` v1 is never deleted, for either.

---

## Measured performance

The figures below come from `bench/bench_ai.py`, which trains and evaluates on
the machine running it and writes raw output to `bench/results_ai.json`.
Nothing here is estimated. Reproduce with:

```bash
python -m bench.bench_ai        # ~4 min, CPU only
```

Two methodological points, both of which are easy to get wrong:

- **Repetition count is chosen so the reported significance is attainable.** A
  two-sided Wilcoxon signed-rank test over *n* paired runs has a minimum
  attainable *p* of 2/2ⁿ, so at *n*=5 no result can legitimately be reported at
  *p* < 0.05. These runs use *n* = 20, floor 1.9 × 10⁻⁶.
- **Anomaly detection is evaluated before smoke becomes observable.** A fully
  developed fire is trivially separable and every method scores ≈ 1.0, which
  measures nothing. Windows are drawn from the simulator's own environmental
  model, and anomalous windows cover the first 14 s of a fire ramp — below the
  smoke-latch point, so temperature is rising and no smoke is present.

### ③a Anomaly detection — early (pre-smoke) fire onset, 20 runs

| Method | AUC-ROC | F1 | Precision | Recall |
|---|---|---|---|---|
| Threshold rule (deployed fallback) | 0.500 ± 0.000 | 0.000 | 0.000 | 0.000 |
| One-Class SVM | 0.627 ± 0.025 | 0.286 | 0.374 | 0.232 |
| Isolation Forest | 0.843 ± 0.018 | 0.313 | 0.398 | 0.258 |
| **LSTM-AE** | **0.998 ± 0.001** | **0.839** | 0.722 | 0.9996 |

Wilcoxon vs Isolation Forest and vs One-Class SVM: *p* = 1.9 × 10⁻⁶ — the floor
at *n* = 20, meaning the autoencoder won on every run. Training takes 1.5 s and
inference 0.95 ms per window on CPU, so nightly retraining and inline
evaluation need no GPU.

The threshold rule's AUC of exactly 0.500 is not a result to celebrate. It
fires above 50 °C or on latched smoke, and in the pre-smoke window neither
condition is reachable, so it sits at chance **by construction**. The honest
reading is not that the learned model outperforms the rule, but that it
operates where the rule is silent. They are complementary, and the deployed
system keeps the rule as the guard for the developed-fire case.

### ② Evacuation routing, 20 runs × 200 scenarios

Danger-weighted Dijkstra against danger-blind shortest-path. The danger
estimate is derived for radial propagation; corridor and corner patterns are
unseen and receive a noisier estimate, so those rows test generalisation.

| Fire model | Proposed | Shortest | Mean danger | Reduction | *p* |
|---|---|---|---|---|---|
| Radial (fitted) | 0.950 ± 0.015 | 0.888 | 0.205 vs 0.277 | 26 % | 8.8 × 10⁻⁵ |
| Corridor (unseen) | 0.945 ± 0.014 | 0.869 | 0.110 vs 0.178 | 38 % | 8.8 × 10⁻⁵ |
| Corner (unseen) | 0.874 ± 0.015 | 0.802 | 0.294 vs 0.370 | 21 % | 8.6 × 10⁻⁵ |

Success is defined as peak route danger staying below 0.8. Gains hold on unseen
propagation patterns, which indicates they come from the cost formulation
rather than from overfitting one fire geometry. The corner pattern is hardest
for both methods: it produces the broadest high-danger region, leaving fewer
safe routes.

This measures the **routing stage** using the shipped `ZoneGraph` and its
Dijkstra implementation. It does not measure the trained XGBoost danger
regressor, which is not loaded at runtime.

### ⑤ Station and route recovery, 20 runs

A known station is configured in the simulator, movement is generated, and
model ⑤ is asked to recover it. Ground truth is the configuration that produced
the data.

| Quantity | Mean ± std | 95 % CI |
|---|---|---|
| Station cell recall | 1.000 ± 0.000 | [1.000, 1.000] |
| Station Jaccard | 0.893 ± 0.135 | [0.833, 0.952] |
| Station confidence | 0.855 ± 0.057 | [0.830, 0.880] |
| Route Jaccard | 0.615 ± 0.120 | [0.563, 0.667] |

Every configured station cell is recovered in every run; the Jaccard shortfall
is occasional *extra* cells where the asset paused in transit, not missed ones.
Mean confidence sits above the 0.60 activation threshold, so these proposals
would activate in deployment.

**Route recovery is markedly weaker than station recovery, and that asymmetry
is the empirical case for separating the two.** A route imposes an ordering
that must be inferred from a noisy visit sequence, and a patrol visits its two
endpoint waypoints half as often as its interior ones, so the tour is
systematically harder to reconstruct than the occupancy set. Had the station
been derived from the learned route, it would have inherited that error.

### Not measured

No figures are reported for model ① or model ④. Credible evaluation of ①
requires human-annotated efficiency labels; of ④, real incident data. Neither
exists in a simulator, and simulator-derived scores would measure our own
assumptions rather than the models.

---

## Implementation status

Training a model and using it are separate paths, and they do not currently
agree. `engine.reload_ai_models()` constructs only two inference objects, and
one of those calls raises.

| Model | Trains | Loaded into engine | Effective runtime behaviour |
|---|---|---|---|
| ① Movement | Yes | **Yes** | Learned scoring |
| ② Evacuation | Yes | **No** | Rule-based danger fallback |
| ③a Anomaly | Yes | **No** | Not evaluated |
| ③b Forecast | Yes | **No** | Not evaluated |
| ③c Failure | **No** | **No** | Not evaluated |
| ④ Fire | Yes | **Yes** | Learned, with rule fallback |
| ⑤ Station/route | Yes | n/a — writes to PostgreSQL | Live |

Four distinct defects produce that column:

1. **③ never loads.** `reload_ai_models()` calls
   `SystemMonitorInference(model_path=…)`, but the constructor takes
   `autoencoder_path` / `forecaster_path` / `failure_model_path`. The resulting
   `TypeError` is caught by the surrounding `except`, logged at info level as
   "AI model not available", and the attribute is left `None`.
2. **③c never trains.** `train_failure_predictor()` has no caller.
3. **② never loads.** `_evac_model` is initialised to `None` and only ever
   read, so `danger_xgb.joblib` is retrained nightly and never used.
4. **① uses heuristic labels.** The DTW labelling in `features.py` is complete
   but unreferenced.

None of this makes the system unsafe. The rule-based scenarios — smoke, high
temperature, workers-in-danger — run in the engine independently of the AI
layer, and every model has a rule fallback tagged in its output. That is
precisely why these defects degrade rather than break the system, and why they
went unnoticed.

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
