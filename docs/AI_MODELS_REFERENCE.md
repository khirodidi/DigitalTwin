# AI Models — Reference Card

One page per model: what it is for, what goes in, what comes out, when it
trains, and which data it learns from.

This document is descriptive of the code as it stands. Every constant below is
taken from the module named in its "Source" row — if you change a constant,
change it here too. For algorithm derivations and evaluation results see
[`AI_MODELS.md`](AI_MODELS.md).

---

## At a glance

| # | Model | Goal | Trains on | Cadence |
|---|---|---|---|---|
| ① | Movement optimiser | Score how efficiently a worker moved during a shift | `location_events` | Nightly |
| ② | Smart evacuation | Route every asset to a safe exit during an incident | `env_readings` + `events` + synthetic | Nightly |
| ③ | System monitor | Detect anomalies, forecast conditions, predict sensor failure | `env_readings` + `sensor_health_events` | Nightly |
| ④ | Fire detection | Locate a fire on the grid and predict its spread | Synthetic + real negatives | Nightly |
| ⑤ | Trajectory & station learning | Refine where each worker works and how they move | `location_events` | Nightly |

**All five retrain nightly at 02:00 UTC**, and additionally whenever hourly
drift detection fires. There is no per-model schedule — the trainer runs them
as one batch, in a fixed order (below).

> Training a model and using it are separate paths. Two of the five are
> currently trained but never loaded into the running engine, and one
> sub-model is never trained at all. Before relying on any output, read
> [Wiring status](#wiring-status--read-this-before-trusting-an-output).

---

## Scheduling: what actually happens

Source: `ai/training/trainer.py`

```
02:00 UTC daily  ──► _retrain_all()
every hour :00   ──► _check_drift() ──► PSI > 0.20 ──► _retrain_all()
```

`_retrain_all()` first asks whether there is enough operational history:

```
oldest row in env_readings is ≥ 7 days old ?
├── no  → train model ④ ONLY, reload, stop
└── yes → ④ fire → ① movement → ⑤ trajectory → ② evacuation → ③ monitor
```

Two things about this order are deliberate:

- **④ runs first** because ② consumes ④'s per-cell fire probability as an
  input feature. Training ② against a stale fire model degrades it.
- **④ runs even with no operational data at all.** Its dataset is synthesised
  from the configured grid, so it is the only model that is useful on day one.
  The others need accumulated history and are skipped until day 7.

After the batch, `engine.reload_ai_models()` swaps the new artefacts into the
running engine. No restart, no dropped messages.

### Drift detection

Source: `ai/training/drift.py`

Population Stability Index over `env_readings`, comparing the **last 7 days**
against the **30 days before that**, computed per reading type
(`temperature`, `humidity`) with 10 bins; the maximum across types is used.

```
PSI = Σᵢ (cᵢ − bᵢ) · ln(cᵢ / bᵢ)
```

`PSI > 0.20` triggers a full retrain outside the nightly schedule. A window is
skipped when the baseline has fewer than 20 samples or the current window
fewer than 10, so a quiet factory does not trigger spurious retraining.

### Manual training

```bash
python -m ai.training.train_all                     # all five, same order
python -m ai.training.train_all --model fire        # one
# choices: all | movement | evacuation | monitor | fire | trajectory
python -m ai.training.train_all --days 60           # widen the extraction window
```

---

## ① Movement optimiser

**Goal.** Score how efficiently an asset moved during an 8-hour shift, so
supervisors can spot wasted walking, repeated backtracking and time lost to
unauthorised detours.

**Source.** `ai/training/movement.py`, `ai/models/movement_optimiser.py`

### Input

One sample per **(asset, 8-hour shift)**, built from `location_events`.

| Part | Shape | Contents |
|---|---|---|
| Zone sequence | `(20,)` int tokens | The last 20 zones visited, left-padded with 0. Zones are mapped to integer tokens by a vocabulary built at training time. |
| Tabular features | `(6,)` float | `backtrack_ratio`, `idle_loop_count`, `auth_violations`, `mean_dwell_secs / 3600`, `hour / 23`, `day_of_week / 6` |

Shifts with fewer than 5 location hops are discarded.

### Output

A single efficiency score in `[0, 1]`, plus the DTW distance between the route
actually walked and the asset's active planned trajectory. An alert is raised
when the score falls below the configured threshold.

### Architecture

Zone tokens → `Embedding(vocab+1, 16)` → 2-layer `LSTM(hidden=64, dropout=0.2)`
→ last hidden state concatenated with the 6 tabular features → MLP → sigmoid.
Trained 40 epochs, Adam at `1e-3`, batch size 32.

### Dataset and labels

- **Source:** `location_events` over the last 30 days (configurable).
- **Labels are heuristic, not observed.** There is no ground-truth efficiency
  annotation, so labels come from a formula:

  ```
  score = 1 − min(1.5·backtrack_ratio, 0.50)
            − min(0.05·idle_loop_count,  0.30)
            − min(0.10·auth_violations,  0.20)
  ```

  This is the model's principal limitation: it learns to reproduce an
  expert-specified rule from sequence context, not to predict human judgement.
  Real supervisor annotation would be needed to make the score meaningful in
  an absolute sense. Treat it as a relative indicator across shifts.

---

## ② Smart evacuation

**Goal.** During an incident, route every asset to an exit along the path that
minimises exposure to danger, rather than the path that is merely shortest —
and re-plan continuously as conditions change.

**Source.** `ai/training/evacuation.py`, `ai/models/smart_evacuation.py`

### Input

Two stages.

**Stage 1 — danger scoring (learned).** Per sensor, from a rolling 10-reading
window of `env_readings`, 12 features:

| Feature | |
|---|---|
| `temp_last`, `hum_last`, `smoke_last` | latest values |
| `temp_mean_10`, `temp_std_10`, `temp_max_10` | temperature window statistics |
| `hum_mean_10`, `smoke_freq_10` | humidity mean, fraction of window with smoke |
| `temp_slope`, `hum_slope` | linear trend over the window |
| `hour`, `day_of_week` | temporal context |

The per-cell fire probability from model ④ is consumed as an additional
feature at inference time, which is why ④ trains first.

**Stage 2 — routing (not learned).** A 4-connected grid graph over the floor
with exit cells marked, plus the danger score per cell.

### Output

Per asset: an ordered route to an exit, the estimated traversal time, the peak
danger along the route, and an evacuation priority rank. Routes are recomputed
continuously while an incident is active.

### Algorithm

Danger score `d(v) ∈ [0,1]` from an XGBoost regressor
(`n_estimators=300`, `max_depth=4`, `learning_rate=0.05`), then Dijkstra over
edge costs

```
cost(u → v) = T_cross · (1 + W · d(v))     T_cross = 15 s,  W = 10
```

so a maximally dangerous cell costs 11× a safe one. Without a trained model
the planner falls back to rule-based danger scoring and still routes.

### Dataset and labels

- **Source:** `env_readings` over the last 90 days, joined against incident
  records in `events`. A reading is labelled dangerous when it falls within
  15 minutes of a recorded incident at that sensor.
- **Augmentation:** 200 synthetic fire samples and 500 synthetic normal
  samples, because real incidents are rare by design — a factory that
  generates enough fires to train on has a bigger problem than routing.

---

## ③ System monitor

**Goal.** Three related jobs on the environmental stream: notice that
something is wrong without having been told what "wrong" looks like, forecast
where conditions are heading, and predict sensor hardware failure before it
happens.

**Source.** `ai/training/monitor.py`, `ai/models/system_monitor.py`

This is one model entry with three independently trained sub-models.

### ③a LSTM Autoencoder — anomaly detection

| | |
|---|---|
| **Input** | `(30, 3)` window: temperature, humidity, smoke, normalised per sensor |
| **Output** | Reconstruction error → anomaly score; alert above threshold |
| **Trained on** | **Normal-operation windows only** — never on anomalies |
| **Threshold** | 95th percentile of validation reconstruction error, stored with the model |
| **Training** | 50 epochs |

Training only on normal data is what makes this useful: it needs no labelled
anomalies, and flags anything unlike normal operation rather than only the
failure modes someone thought to enumerate.

```
a(x) = (1/T) Σₜ ‖xₜ − x̂ₜ‖²
```

### ③b LSTM Forecaster — environmental prediction

| | |
|---|---|
| **Input** | `(30, 3)` window |
| **Output** | Next 5 readings of temperature and humidity |
| **Training** | 60 epochs, MSE loss |
| **Alert** | Predicted temperature > 58 °C raises a pre-alert before the real threshold is crossed |

### ③c XGBoost classifier — sensor failure prediction

> **Not currently trained.** `train_failure_predictor()` is implemented but no
> caller invokes it, so `failure_xgb.joblib` is never produced. The design is
> described here because the inference path expects it; see
> [Wiring status](#wiring-status--read-this-before-trusting-an-output).

| | |
|---|---|
| **Input** | `consecutive_failures` (from the watchdog), reading variance over the last 20 readings, time since last reading, temp/humidity/smoke mean and std, `hour`, `day_of_week` |
| **Output** | Failure probability; maintenance alert above 0.70 |
| **Label** | Retrospective — *did this sensor go OFFLINE within 24 h of this reading?* |
| **Imbalance** | Handled with `scale_pos_weight`, since failures are rare |

### Dataset

`env_readings` and `sensor_health_events` over the last 30 days. The
autoencoder additionally filters to periods with no recorded incident.

---

## ④ Fire detection and localisation

**Goal.** Decide *where* on the floor a fire is and *where it is going* — not
merely that some sensor is hot. A single hot sensor is ambiguous; a hotspot
expanding across neighbouring cells over time is not, and only a model that
sees the whole grid at once can tell them apart.

**Source.** `ai/training/fire.py`, `ai/models/fire_detector.py`

### Input

A grid tensor of shape `(20, H, W, 6)` — 20 timesteps (~40 s at a 2 s publish
rate) over the full `H × W` sensor grid, with six channels per cell:

| Ch | Contents |
|---|---|
| 0 | Temperature, normalised against that cell's coverage-type baseline |
| 1 | Humidity, z-scored — fire drives humidity down as it drives temperature up |
| 2 | Smoke, binary |
| 3 | `dT/dt` — rate of temperature change |
| 4 | `∇²T` — spatial Laplacian, separating an expanding hotspot from a static one |
| 5 | Validity mask — 0 where the sensor is offline, so the model can ignore it |

Channel 5 matters more than it looks: without it an offline sensor reads as a
cold cell, which suppresses detection exactly when a sensor has failed.

### Output

Three heads:

| Head | Output |
|---|---|
| Segmentation | `(H, W)` per-cell fire probability map |
| Origin | `(2,)` estimated ignition coordinates |
| Spread | `(3,)` predicted spread direction and rate |

### Architecture

Two stacked `ConvLSTM` cells (32 hidden channels, 3×3 kernel) — convolutional
gates rather than dense ones, so spatial structure survives the recurrence —
followed by the three heads. Trained 40 epochs, batch size 8, Adam at `1e-3`,
with Dice loss on the segmentation head.

### Dataset

**This is the only model trainable before the system has ever run**, because
its dataset is synthesised from the configured grid rather than accumulated
from operation.

| Portion | Count | Origin |
|---|---|---|
| Positive | 4,000 | Simulated fires — radial, corridor and corner propagation over the configured grid, respecting per-cell coverage type and `passable` |
| Negative | 12,000 | Synthetic normal operation, plus **real** windows drawn from `env_readings` when available (up to 3,000) |

Coverage-type baselines used for synthesis: machine 31.0 °C, storage 18.0 °C,
passage 22.5 °C, exit 17.5 °C.

Mixing real negatives in matters: a model trained only against synthetic
normality learns the simulator's noise profile and false-positives on real
sensor behaviour.

> **Accuracy is unproven.** The positive class has never been validated
> against a real fire. Treat the outputs as a prioritisation aid, not as a
> fire alarm, and keep the rule-based smoke and temperature scenarios enabled
> underneath it.

---

## ⑤ Trajectory and station learning

**Goal.** The route and working station an operator configures are an initial
guess. Real work patterns drift — machines move, storage bays are reassigned,
workers find shorter paths. This model mines what actually happened and
proposes updates to both.

**Source.** `ai/training/trajectory.py`

### Two artefacts, learned independently

| | **Working station** | **Trajectory** |
|---|---|---|
| Answers | *Where* does it work? | *How* does it move between? |
| Shape | Unordered set, weighted | Ordered route |
| Table | `asset_station` | `asset_trajectory` |

They are learned from the same observed shifts but by different statistics,
and deliberately not derived from one another: a worker can keep the same tour
while the cells they dwell at drift, and vice versa.

### Input

`location_events` over the last 30 days, grouped into 8-hour shifts. Shifts
with fewer than 4 events are dropped, and an asset needs at least 5 qualifying
shifts before anything is proposed.

### Algorithm

1. Extract each shift's cell sequence.
2. Where model ① scores are available, keep only shifts it rated efficient
   (≥ 0.65), so the result reflects good practice rather than average practice.
3. Detect **stop points** — runs of ≥ 3 consecutive readings at one cell. This
   is what separates work cells from corridors merely passed through.
4. Keep cells appearing in ≥ 35 % of shifts.
5. **Station:** weight the kept cells by share of dwell time, capped at the 6
   heaviest.

   ```
   wₛ = Dₛ / Σ D    (weights sum to 1)
   ```

6. **Trajectory:** order the same stop points by a nearest-neighbour tour,
   seeded at the most frequent first stop, capped at 8 waypoints.
7. Compare against what is active; store a new version only if materially
   different (Jaccard ≤ 0.85).

### Output

A new `learned` version of the station and/or the route, each with a
confidence score:

```
c = 0.7 · mean_support + 0.3 · min(n_shifts / 15, 1)
```

### Activation and versioning

| Confidence | Result |
|---|---|
| ≥ 0.60 | Activated automatically |
| < 0.60 | Stored as a proposal, not activated |

Both artefacts are versioned by `(source, version)`, with
`asset_trajectory_active` / `asset_station_active` naming the one in force.
**The operator's `configured` version 1 is never deleted** and can be restored
from the Workers tab at any time. A safety-relevant model that silently
overwrites operator intent is not auditable.

---

## Cold start: what works when

| Day | Available |
|---|---|
| 0 | ④ fire detection (synthetic dataset). Everything else falls back to rules. |
| 7 | Nightly batch begins training all five — `_has_enough_data()` requires `env_readings` spanning ≥ 7 days. |
| ~7+ | ③ anomaly detection becomes useful once enough normal operation has accumulated. |
| ~14+ | ① movement optimiser starts beating its rule-based fallback. |
| Varies | ⑤ needs ≥ 5 qualifying shifts per asset — an asset that rarely moves may never qualify, which is correct behaviour. |

Every model has a rule-based fallback and tags its output with the source that
produced it (`source: "rules"` vs `source: "convlstm"`, etc.), so a consumer
can always tell a learned decision from a heuristic one. The system is fully
functional before any model is trained; the models improve it, they are not
load-bearing for safety.

That fallback design is why the wiring defects above degrade the system
rather than break it — a model that never loads simply leaves its rule-based
path in service, which is also why the defects are easy to miss.

---

## Artefacts on disk

Written to `models/`, persisted in the `model_store` Docker volume across
container restarts.

| File | Model | Written by |
|---|---|---|
| `movement_lstm.pt` | ① | `ai/training/movement.py` |
| `danger_xgb.joblib` | ② | `ai/training/evacuation.py` |
| `autoencoder.pt` | ③a | `ai/training/monitor.py` |
| `forecaster.pt` | ③b | `ai/training/monitor.py` |
| `monitor_scalers.joblib` | ③ | `ai/training/monitor.py` |
| `fire_convlstm.pt` | ④ | `ai/training/fire.py` |
| — | ⑤ | versions go to PostgreSQL, not to disk |

Reload without restarting:

```bash
curl -X POST http://localhost:8000/api/system/reload-models
```

---

## Wiring status — read this before trusting an output

Training a model and *using* it are separate paths, and they do not currently
agree. As of this writing, `engine.reload_ai_models()` constructs only two
inference objects, and one of those calls fails. The table records what is
actually live at runtime, not what the modules are capable of.

| Model | Trains? | Loaded into the engine? | Effective runtime behaviour |
|---|---|---|---|
| ① Movement | Yes | **Yes** | Learned scoring |
| ② Evacuation | Yes | **No** | Rule-based danger fallback |
| ③a Anomaly | Yes | **No** | Not evaluated |
| ③b Forecast | Yes | **No** | Not evaluated |
| ③c Failure | **No** | **No** | Not evaluated |
| ④ Fire | Yes | **Yes** | Learned, with rule fallback |
| ⑤ Station/route | Yes | n/a — writes to the database | Live |

Three distinct defects produce that column:

1. **③ never loads.** `reload_ai_models()` calls
   `SystemMonitorInference(model_path=…)`, but the constructor takes
   `autoencoder_path` / `forecaster_path` / `failure_model_path`. The
   resulting `TypeError` is swallowed by the surrounding `except`, which logs
   it at info level as "AI model not available" and leaves the attribute
   `None`. Anomaly detection, forecasting and failure prediction therefore
   never run, however well they train.

2. **③c never trains.** `train_failure_predictor()` exists in
   `ai/models/system_monitor.py` but nothing calls it —
   `train_monitor_models()` trains only the autoencoder and the forecaster.
   `failure_xgb.joblib` is never produced.

3. **② never loads.** `_evac_model` is initialised to `None` and only ever
   read. `danger_xgb.joblib` is retrained nightly and never loaded, so the
   planner always uses its rule-based danger scoring at runtime.

None of this makes the system unsafe: the rule-based scenarios (smoke, high
temperature, workers-in-danger) run in the engine independently of the AI
layer and are unaffected. But an operator reading "five AI models" should know
that two and a half of them are currently inert at runtime.

---

## Honest limitations

- **Everything is simulator-validated.** No model has been evaluated against a
  physical deployment.
- **① labels are a formula, not observations.** The score reproduces an
  expert-specified heuristic; it is not calibrated against human judgement.
- **④ has never seen a real fire.** Its positive class is entirely synthetic.
- **② depends on incident records** that a well-run factory will barely have,
  which is why 700 synthetic samples carry much of the training signal.
- **⑤ recovers stations more reliably than routes.** Ordering must be inferred
  from a noisy visit sequence, and a patrol visits its endpoint waypoints half
  as often as its interior ones. Measured recovery against a known
  configuration: station Jaccard 0.893, route Jaccard 0.615 — see
  [`AI_MODELS.md`](AI_MODELS.md) for the measurement.
