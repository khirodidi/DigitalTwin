# Digital Twin — Factory Monitoring System

Real-time digital twin of a factory floor. A wireless sensor network tracks
workers and mobile assets and measures environmental conditions; a Python
engine maintains live state, enforces access control, runs five AI models, and
streams everything to a React dashboard over WebSocket.

Everything factory-specific — grid size, zones, blueprint, thresholds,
authorisations, worker stations and routes — is configured at **runtime** in
the dashboard and stored in PostgreSQL. Changing the floor layout never
requires a rebuild.

---

## Quick start

```bash
docker compose up --build              # postgres · mosquitto · backend · frontend
open http://localhost:3000             # first run shows the setup wizard
```

The first run opens a setup screen: grid size and a blueprint image are
mandatory before the monitoring view appears. To start from a worked example
instead, seed the database:

```bash
# macOS / Linux / WSL / Git Bash
docker exec -i dt_postgres psql -U dt_user -d digital_twin < scripts/seed_db.sql
```

```powershell
# Windows PowerShell — '<' is not an operator in PowerShell, and seed_db.sql
# contains UTF-8 text that Get-Content mangles on Windows PowerShell 5.1.
# Copying the file in avoids both problems.
docker cp scripts\seed_db.sql dt_postgres:/tmp/seed_db.sql
docker exec dt_postgres psql -U dt_user -d digital_twin -f /tmp/seed_db.sql
```

Then feed it data — no hardware needed:

```bash
docker compose --profile sim up simulator     # or: python scripts/simulate_wsn.py
```

| Service | Port | Container |
|---|---|---|
| Frontend (React + nginx) | 3000 | `dt_frontend` |
| Backend (FastAPI) | 8000 | `dt_backend` |
| PostgreSQL 16 | 5432 | `dt_postgres` |
| Mosquitto MQTT | 1883 | `dt_mosquitto` |

If Docker Hub times out during the build, pull the base images first:

```bash
docker pull python:3.12-slim node:20-alpine nginx:alpine \
            postgres:16-alpine eclipse-mosquitto:2
```

---

## How it fits together

```
WSN sensors ─→ Mother station ─→ MQTT (Mosquitto)
                                     │
                                     ▼
                        ┌────────────────────────┐
                        │  DigitalTwinEngine     │
                        │  · StateStore (memory) │
                        │  · rules + watchdog    │
                        │  · AI inference        │
                        └───────┬────────┬───────┘
                                │        │
                     PostgreSQL ◄┘        └─► WebSocket ─→ React dashboard
                     (best-effort)            (live push)
```

The in-memory `StateStore` is the source of truth for the live view;
PostgreSQL is written best-effort. A database failure must never stop the
WebSocket feed.

### MQTT payloads

Two topics, QoS 1, JSON **arrays**:

```jsonc
["S07", "temperature", 47.2, "2026-08-09T10:23:00Z"]   // wsn/env
["W01", "S07", "2026-08-09T10:23:00Z"]                 // wsn/location
```

Sensor IDs are `S01`…`SNN`, assigned row-major: `index = row * cols + col + 1`.
The engine, dashboard and simulator all assume this mapping.

---

## Configuration UI

Click **⚙️ Configuration** in the header. Four tabs:

| Tab | What you configure |
|---|---|
| 🏭 Factory Layout | Factory name · grid N×M · blueprint upload · zones and their sensors · global thresholds |
| 📡 Sensors | Per sensor: coverage type (passage / machine / storage / exit), `passable` flag, description, threshold overrides |
| 👷 Workers | Add/edit/delete assets · zone and sensor authorisations · **working station** · trajectory |
| 📍 Trajectory | Pick a worker → observed path on the grid, with the planned route and working station overlaid |

Saving broadcasts a `config_updated` event, and the dashboard reloads only the
affected section. No restart, no rebuild.

The blueprint is **uploaded through the UI**, not baked into the image. It is
stored in the `blueprint_store` volume and served from `/static/blueprints/`.

---

## Core concepts

**Zone.** A zone *is* its set of sensors. `sensors.zone_id` is the single
source of truth; the `zones` table only carries name, description and
threshold defaults.

**Access control.** Each asset has `allowed_zones` and `allowed_sensors`.
A zone authorisation **implicitly covers every sensor in that zone**, so
adding a sensor to a zone immediately extends every zone-level grant to it.

```
sensor OFFLINE          → UNKNOWN     (amber, no alert — not the worker's fault)
sensor_id ∈ allowed     → AUTHORISED
zone_id   ∈ allowed     → AUTHORISED
otherwise               → VIOLATION   (red + alert)
```

The OFFLINE check runs **first**: a dead sensor never produces a false
violation.

**Working station vs trajectory.** A worker's **station** is *where* it works:
an unordered set of cells, each with a dwell `weight`. Its **trajectory** is
*how* it moves between them: an ordered route. Both start as operator input
and are refined independently by model ⑤ — the cells someone dwells at can
drift while their tour stays the same.

Both are versioned. `asset_trajectory` / `asset_station` keep every version
keyed by `(source, version)`; `asset_trajectory_active` / `asset_station_active`
name the one in force. The operator's original is never deleted and can be
restored from the Workers tab.

**Thresholds resolve through three levels**, each `NULL` falling through:

```
sensor_config → zones → factory_config (global)
```

65 °C is normal in a furnace zone and critical in a corridor.

---

## The five AI models

| # | Model | Algorithm | Output | Retrains |
|---|---|---|---|---|
| ① | Movement optimiser | LSTM + DTW | efficiency score 0–1 | weekly |
| ② | Smart evacuation | XGBoost danger + Dijkstra | route per asset | on new incidents |
| ③ | System monitor | LSTM-AE + LSTM forecaster + XGBoost | anomaly · forecast · failure | nightly 02:00 |
| ④ | Fire detection | ConvLSTM, 3 heads | fire map · origin · spread | nightly + on incident |
| ⑤ | Trajectory & station learning | stop-point clustering | updated route + station | nightly |

```bash
python -m ai.training.train_all                  # all five
python -m ai.training.train_all --model fire     # one
# choices: all | movement | evacuation | monitor | fire | trajectory
```

Training order matters: **④ runs before ②**, because the evacuation planner
consumes per-cell fire probability as a feature. Model ④ is the only one
trainable on day one — its dataset is synthesised from the configured grid.

Every model falls back to a rule-based heuristic before it has enough data and
tags its output `source: "rules"` vs `source: "convlstm"`, so you can always
tell a learned decision from a heuristic one. Drift detection (PSI > 0.20)
triggers retraining outside the schedule, and models hot-reload without a
restart.

- [`docs/AI_MODELS_REFERENCE.md`](docs/AI_MODELS_REFERENCE.md) — per model:
  goal, inputs, outputs, training schedule, dataset, and which models are
  actually wired into the running engine.
- [`docs/AI_MODELS.md`](docs/AI_MODELS.md) — algorithm derivations and
  evaluation results.

---

## Simulator

Trajectory-driven, not a random walk. Each asset is assigned an ordered route
through its authorised area, walks the shortest **passable** path between
waypoints (BFS), and dwells at each according to that cell's coverage type.

```bash
python scripts/simulate_wsn.py                                # reads live config from the API
python scripts/simulate_wsn.py --violation-rate 0.08          # more deliberate strays
python scripts/simulate_wsn.py --waypoints 6 --interval 1
python scripts/simulate_wsn.py --no-config --cols 8 --rows 6 --workers 10
```

| Config setting | Simulator behaviour |
|---|---|
| `passable = false` | Never entered, and never routed through |
| `coverage_type = machine` | Dwell 5–12 ticks · base 28–34 °C · forklifts and pallets avoid |
| `coverage_type = storage` | Dwell 3–6 ticks · base 16–20 °C |
| `coverage_type = passage` | Dwell 1–2 ticks · base 20–25 °C |
| `coverage_type = exit` | Dwell 1–2 ticks · base 15–20 °C · passable by all types |
| Authorisations | The asset's home area is its authorised cells |
| Working station | Station cells are preferred as waypoints and dwelled on ~2.5× longer |
| Configured trajectory | Overrides the generated route when it has ≥2 usable cells |

Per asset type:

| Type | Style | Speed | Avoids | Starts at |
|---|---|---|---|---|
| worker | patrol (bounces between ends) | 1 tick/cell | — | an **exit** cell in its authorised zone |
| forklift | circuit (loops) | 1 tick/cell | machine cells | first cell of its trajectory |
| pallet | static (parked, nudged) | 3 ticks/cell | machine cells | first cell of its trajectory |

Workers enter through a door; forklifts and pallets are already parked when
the shift starts.

If a configured route names an impassable cell, or one stranded behind
impassable cells, the simulator drops that waypoint and reports it in the
startup table rather than freezing.

---

## Benchmarks

`bench/` measures the shipped code — engine service time, watchdog behaviour
under a real induced outage, access-control correctness, and the AI layer.
Nothing is hardcoded; the raw JSON it emits is what the paper figures are
built from.

```bash
python -m bench.bench_engine --msgs 5000 --runs 5 --spof   # add --db "<dsn>" for persistence cost
python -m bench.bench_ai                                    # ~4 min, CPU only
python -m bench.make_figures --out bench/figures
```

Representative output on a single CPU core:

| Measurement | Value |
|---|---|
| `wsn/env` service time (in-memory) | 0.033 ± 0.009 ms |
| `wsn/env` including PostgreSQL write | 0.042 ms |
| Scaling, 12 → 180 sensors | 0.019 → 0.130 ms (linear in sensor count) |
| First DEGRADED after gateway loss | 9.98 s (2 missed 5 s cycles) |
| All sensors OFFLINE | 24.99 s (5 cycles) |
| False violations during outage | 0 of 45 decisions |

---

## Repository layout

```
digitaltwin/
├── models/state.py              Dataclasses + enums + ZoneRegistry
├── ingestion/mqtt_parser.py     Parse wsn/env and wsn/location payloads
├── engine/
│   ├── engine.py                DigitalTwinEngine — started by FastAPI lifespan
│   ├── state_store.py           In-memory state, auto-registers unknown sensors
│   ├── rules.py                 Access control · safety scenarios · prediction
│   ├── watchdog.py              Heartbeat monitoring, ONLINE→DEGRADED→OFFLINE
│   ├── thresholds.py            sensor → zone → global threshold resolution
│   └── system_state.py          Global aggregation → SystemState
├── persistence/postgres.py      Schema (15 tables) + all read/write
├── api/
│   ├── main.py                  FastAPI app, WebSocket, static mount, lifespan
│   ├── ws_manager.py            Broadcast to all connected clients
│   └── routes/                  assets · sensors · zones · events · system · config
├── ai/
│   ├── models/                  movement_optimiser · smart_evacuation
│   │                            system_monitor · fire_detector
│   ├── pipeline/features.py     Shared feature engineering + DTW
│   └── training/                One module per model + trainer + drift
├── bench/                       Benchmark harness (engine · AI · figures)
├── frontend/src/
│   ├── App.jsx                  Root: setup gate → monitor → config routing
│   ├── hooks/                   useConfig · useWebSocket · useApi
│   ├── pages/                   SetupScreen (first run) · ConfigPage (4 tabs)
│   └── components/              FactoryMap · SensorCell · SensorDetail · SensorGridPicker
│                                StatusBar · AlertPanel · AssetList · FactoryLayout
│                                SensorEditor · WorkerManager · TrajectoryMap
│                                BlueprintUpload
├── scripts/
│   ├── simulate_wsn.py          Config-driven WSN simulator with trajectories
│   ├── seed_db.sql              Zones · sensors · assets · authorisations
│   ├── diagnose-build.sh        Shows the real React build error
│   └── rebuild.sh               Clean rebuild, clears stale bundle caches
├── docs/AI_MODELS.md            Full AI spec: algorithms, datasets, I/O
└── tests/                       test_engine.py · test_ai.py
```

---

## Database

15 tables. The ones worth knowing:

| Table | Purpose |
|---|---|
| `factory_config` | key-value: grid size, blueprint URL, global thresholds |
| `zones` · `sensors` · `sensor_config` | layout, zone membership, coverage type, per-sensor overrides |
| `assets` · `authorisations` | who exists, and what they may access |
| `asset_trajectory` (+`_active`) | versioned ordered routes |
| `asset_station` (+`_active`) | versioned working stations, with per-cell weight |
| `location_events` · `env_readings` · `sensor_health_events` · `events` | time series |
| `system_snapshots` | aggregated state history |

The schema is created idempotently at backend startup — there is no migration
tool, so changes go in `CREATE_TABLES` in `persistence/postgres.py` and must be
backward compatible.

```bash
docker compose down            # keeps data
docker compose down -v         # DESTROYS data — re-seed afterwards

docker exec dt_postgres pg_dump -U dt_user digital_twin > backup.sql
docker exec -i dt_postgres psql -U dt_user digital_twin < backup.sql
```

On Windows PowerShell, restore the same way as seeding — `docker cp` the dump
in, then `psql -f`:

```powershell
docker exec dt_postgres pg_dump -U dt_user digital_twin > backup.sql
docker cp backup.sql dt_postgres:/tmp/backup.sql
docker exec dt_postgres psql -U dt_user digital_twin -f /tmp/backup.sql
```

---

## API

**Monitoring**

| Method | Endpoint |
|---|---|
| GET | `/api/assets` · `/api/assets/{id}/history` |
| GET | `/api/sensors` · `/api/sensors/{id}/readings` |
| GET | `/api/zones` · `/api/events` |
| GET | `/api/system/state` · `/api/system/layout` |
| POST | `/api/system/reload-models` |
| WS | `/ws` — snapshot on connect, then incremental |

**Configuration**

| Method | Endpoint |
|---|---|
| GET/PUT | `/api/config/factory` |
| POST/GET/DELETE | `/api/config/factory/blueprint`(`/status`) |
| GET/POST/DELETE | `/api/config/zones`(`/{zone_id}`) |
| GET/PUT | `/api/config/sensors`(`/{sensor_id}`) |
| GET/POST/PUT/DELETE | `/api/config/workers`(`/{asset_id}`) |
| GET/PUT | `/api/config/workers/{id}/authorisations` |
| POST | `/api/config/workers/bulk-authorise` |
| GET | `/api/config/workers/{id}/trajectory?limit=N` |
| GET/PUT | `/api/config/workers/{id}/trajectory-versions` · `/trajectory-active` |
| GET/PUT | `/api/config/workers/{id}/station-versions` · `/station-active` |

**WebSocket events**

`snapshot` (on connect) · `system_state` · `sensor_update` · `health_update` ·
`asset_update` · `alert` · `ai_insight` · `config_updated`

---

## Frontend notes

Only two build-time variables exist: `REACT_APP_API_URL` and
`REACT_APP_WS_URL`. Everything else is runtime config from the API — do not
reintroduce build-time layout variables.

Styling is inline objects, no CSS framework. Dark palette: `#050c1a`
background · `#0d1829` panels · `#1e293b` borders · `#6366f1` accent.

Sensor cells are rendered **border-only** so the blueprint stays visible;
state is conveyed by border colour and weight. The factory map has 2D and 3D
modes and a full-screen view that fills 90 % of the viewport width.

---

## Tests

```bash
pip install -r requirements.txt
PYTHONPATH=. pytest tests/ -v
```

> **Known:** 5 tests currently fail — 4 in `tests/test_ai.py` (feature-key
> mismatches in `ai/pipeline/features.py`) and
> `test_engine.py::TestWatchdog::test_unknown_sensor_ignored`. These predate
> the current work and are unrelated to the engine, simulator or config paths.

Useful commands:

```bash
./scripts/diagnose-build.sh        # the real React build error (Docker only shows "exit code: 1")
./scripts/rebuild.sh               # clean rebuild, clears stale bundle caches
docker exec dt_mosquitto mosquitto_sub -t 'wsn/#' -C 20      # watch raw MQTT

# clear a violation storm (assets with no authorisations)
curl -X POST http://localhost:8000/api/config/workers/bulk-authorise \
  -H "Content-Type: application/json" \
  -d '{"asset_ids":"all","allowed_zones":["zone_A"],"mode":"replace"}'
```

[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) covers blank pages, offline sensors,
upload hangs and build failures. [`INSTALL.md`](INSTALL.md) covers manual
(non-Docker) setup.

---

## Status

Working end to end: ingestion, state, rules, watchdog, access control,
thresholds, configuration UI, 2D/3D visualisation, five AI models, simulator,
Docker deployment, benchmark harness.

Not done: physical hardware validation — everything is simulator-driven;
multi-gateway failover for the single mother station; and real-world accuracy
figures for the fire model, whose training data is synthetic.

---

## License

MIT
