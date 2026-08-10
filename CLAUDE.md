# Digital Twin — Factory Monitoring System

Real-time digital twin of a factory floor. A wireless sensor network tracks
workers and mobile objects and measures environmental conditions; a Python
engine maintains live state, enforces access control, runs five AI models, and
streams everything to a React dashboard over WebSocket.

---

## Quick start

```bash
docker compose up --build              # postgres · mosquitto · backend · frontend
docker exec -i dt_postgres psql -U dt_user -d digital_twin < scripts/seed_db.sql
open http://localhost:3000             # first run shows the setup screen

docker compose --profile sim up simulator   # WSN simulator (no hardware needed)
```

| Service | Port | Container |
|---|---|---|
| Frontend (React + nginx) | 3000 | `dt_frontend` |
| Backend (FastAPI) | 8000 | `dt_backend` |
| PostgreSQL 16 | 5432 | `dt_postgres` |
| Mosquitto MQTT | 1883 | `dt_mosquitto` |

---

## Architecture

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
                     (persistence)            (live push)
```

**Design rule that matters everywhere:** the in-memory `StateStore` is the
source of truth for the live view. PostgreSQL is written best-effort. A
database failure must never stop the WebSocket feed — see `_safe_db()` in
`engine/engine.py`. We hit this exact bug: an unguarded `save_env_reading()`
threw, killed the handler before the WebSocket push, and the error vanished
because the coroutine's future was never awaited. Every sensor then showed
OFFLINE with no data.

---

## Repository layout

```
digitaltwin/
├── models/state.py              Dataclasses + enums + ZoneRegistry
├── ingestion/mqtt_parser.py     Parse wsn/env and wsn/location payloads
├── engine/
│   ├── engine.py                DigitalTwinEngine — started by FastAPI lifespan
│   ├── state_store.py           In-memory O(1) state, auto-registers sensors
│   ├── rules.py                 Access control · safety scenarios · prediction
│   ├── watchdog.py              Heartbeat monitoring, ONLINE→DEGRADED→OFFLINE
│   ├── thresholds.py            sensor → zone → global threshold resolution
│   └── system_state.py          Global aggregation → SystemState
├── persistence/postgres.py      Schema (13 tables) + all read/write
├── api/
│   ├── main.py                  FastAPI app, WebSocket, static mount, lifespan
│   ├── ws_manager.py            Broadcast to all connected clients
│   └── routes/                  assets · sensors · zones · events · system · config
├── ai/
│   ├── models/                  movement_optimiser · smart_evacuation
│   │                            system_monitor · fire_detector
│   ├── pipeline/features.py     Shared feature engineering + DTW
│   └── training/                One module per model + trainer (APScheduler)
├── frontend/src/
│   ├── App.jsx                  Root: setup gate → monitor → config routing
│   ├── hooks/useConfig.js       Runtime config (NOT env vars) + live refresh
│   ├── hooks/useWebSocket.js    Auto-reconnecting WS with keep-alive
│   ├── pages/SetupScreen.jsx    First-run wizard (grid + blueprint mandatory)
│   ├── pages/ConfigPage.jsx     4 tabs: layout · sensors · workers · trajectory
│   └── components/              FactoryMap · SensorCell · SensorGridPicker …
├── scripts/
│   ├── simulate_wsn.py          Config-driven WSN simulator with trajectories
│   ├── seed_db.sql              Zones · sensors · assets · authorisations
│   ├── diagnose-build.sh        Shows the real React build error
│   └── rebuild.sh               Clean rebuild, clears stale bundle caches
├── docs/AI_MODELS.md            Full AI spec: algorithms, datasets, I/O
└── tests/                       test_engine.py · test_ai.py
```

---

## Data formats

Two MQTT topics, QoS 1, JSON arrays (not objects):

```jsonc
// topic: wsn/env
["S07", "temperature", 47.2, "2026-08-09T10:23:00Z"]
//  ^sensor  ^type: temperature|humidity|smoke   ^value  ^ISO timestamp

// topic: wsn/location
["W01", "S07", "2026-08-09T10:23:00Z"]
//  ^asset  ^sensor it is nearest to   ^ISO timestamp
```

Sensor IDs are `S01`…`SNN`, assigned row-major over the grid:
`sensor_index = row * cols + col + 1`. This mapping is assumed in the engine,
the frontend and the simulator — change it in one place and everything breaks.

---

## Core domain concepts

**Grid.** The floor is an `N × M` grid, one sensor per cell, full coverage.
`grid_cols` and `grid_rows` live in the `factory_config` table and are read at
**runtime** — they are deliberately *not* build-time env vars.

**Zone.** A zone *is* its set of sensors. `sensors.zone_id` is the single
source of truth; the `zones` table only carries the name, description and
threshold defaults.

**Localisation is zone-based, not trilateration.** A tag is simply associated
with whichever sensor detects it. Cell-level granularity, no calibration.

**Access control.** Each asset has `allowed_zones` and `allowed_sensors`.
A zone authorisation **implicitly covers every sensor in that zone**.

```
sensor OFFLINE          → UNKNOWN    (amber, no alert — not the worker's fault)
sensor_id ∈ allowed     → AUTHORISED
zone_id   ∈ allowed     → AUTHORISED
otherwise               → VIOLATION  (red + alert)
```

**Thresholds resolve through three levels**, each NULL falling through:

```
sensor_config → zones → factory_config (global)
```

This matters: 65 °C is normal in a furnace zone and critical in a corridor.
Resolution lives in `engine/thresholds.py` and is cached in memory; the config
API calls `engine.reload_thresholds()` so edits apply without a restart.

**Sensor coverage types.** `passage` (default) · `machine` · `storage` ·
`exit`, plus a `passable` boolean. These drive simulator movement, evacuation
routing, and per-coverage-type anomaly baselines.

---

## The five AI models

Full specification in `docs/AI_MODELS.md`. Summary:

| # | Model | Algorithm | Input | Output |
|---|---|---|---|---|
| ① | Movement optimiser | LSTM + DTW | zone sequence + 11 features | efficiency 0–1 |
| ② | Smart evacuation | XGBoost + Dijkstra | env features + fire map | route per asset |
| ③ | System monitor | LSTM-AE + LSTM-Reg + XGBoost | (30,3) window | anomaly · forecast · failure |
| ④ | Fire detection | ConvLSTM, 3 heads | (20,H,W,6) grid tensor | fire map · origin · spread |
| ⑤ | Trajectory learning | stop-point clustering | location history | updated route |

Training order matters — **④ runs first**, because ② consumes its per-cell fire
probability as a feature.

```bash
python -m ai.training.train_all                 # all five
python -m ai.training.train_all --model fire    # one
```

Every model falls back to rule-based heuristics before it has enough data, and
tags its output `source: "rules"` vs `source: "convlstm"` etc.

Model ④ is the only one trainable on day one — its dataset is synthesised from
the configured grid rather than accumulated from operation.

Model ⑤ means **trajectories are not fixed**: the operator sets an initial
route, and the AI proposes updates. Both are versioned in `asset_trajectory`
with `asset_trajectory_active` naming the one in force. The operator's
original is never deleted.

---

## Database

13 tables. The ones worth knowing:

| Table | Purpose |
|---|---|
| `factory_config` | key-value: grid size, blueprint URL, global thresholds |
| `zones` | name, description, zone-level thresholds |
| `sensors` | `zone_id`, `grid_row`, `grid_col` |
| `sensor_config` | coverage type, passable, per-sensor threshold overrides |
| `assets` | workers, forklifts, pallets |
| `authorisations` | `(asset_id, 'zone'\|'sensor', allowed_id)` |
| `asset_trajectory` | versioned routes: `(asset_id, source, version, seq)` |
| `asset_trajectory_active` | which version is in force |
| `location_events` · `env_readings` · `sensor_health_events` · `events` | time series |
| `system_snapshots` | aggregated state history |

Schema is created idempotently at backend startup via `create_schema()` —
there is no migration tool. Adding a column means editing `CREATE_TABLES` in
`persistence/postgres.py`.

---

## WebSocket protocol

```jsonc
{ "event": "sensor_update", "payload": { … }, "ts": "2026-08-09T…" }
```

| Event | When |
|---|---|
| `snapshot` | on connect — full state |
| `system_state` | after every update |
| `sensor_update` · `health_update` · `asset_update` | per reading |
| `alert` · `ai_insight` | rule or model output |
| `config_updated` | configuration changed — frontend refreshes that section |

`config_updated` carries `{section}` so `useConfig().refresh(section)` reloads
only what changed.

---

## Frontend conventions

**Only two env vars exist:** `REACT_APP_API_URL` and `REACT_APP_WS_URL`.
Everything else — factory name, grid size, blueprint — is runtime config from
the API. Do not reintroduce build-time layout vars; changing the grid must not
require a rebuild.

**Styling is inline objects**, no CSS framework. Dark palette:
`#050c1a` background · `#0d1829` panels · `#1e293b` borders · `#6366f1` accent.

**Scroll rule.** A flex child defaults to `min-height: auto` and refuses to
shrink, which silently disables `overflow: auto`. Every scroll container sets
`minHeight: 0`. Helpers in `src/styles/scroll.js`.

**Sensor rendering is border-only** — no background fill, so the blueprint
stays visible. State is conveyed by border colour and weight.

---

## Pitfalls we have already hit

These caused real outages; do not reintroduce them.

**Rules of hooks.** `SensorDetail.jsx` had `if (!sensorId) return null` *before*
a `useMemo`. Different renders ran different numbers of hooks → React unmounted
the tree → blank page. Early returns go **after** all hooks.

**Duplicate declarations.** Adding `cols` as a prop while a local
`const cols = …` still existed → `Identifier 'cols' has already been declared`
→ build failure. Props and locals share a scope.

**Docker `CI=true`.** CRA escalates ESLint warnings to errors under CI, so one
unused import broke the build. `Dockerfile.frontend` sets `CI=false` and
`DISABLE_ESLINT_PLUGIN=true`.

**Shell pipes swallow exit codes.** `npm run build | tee log` returns *tee's*
status, so a failed build reported success and the error was invisible. Never
pipe a command whose failure must propagate.

**nginx caches `index.html`.** After a rebuild the browser requested a bundle
hash that no longer existed → 404 → blank page. `nginx.conf` sends `no-store`
for `index.html` and `immutable` for hashed assets.

**nginx 1 MB upload limit.** Blueprint uploads appeared to hang. Now
`client_max_body_size 25m`, and uploads use XHR with a 60 s timeout so they
cannot spin forever.

---

## Common tasks

```bash
# See the real React build error (Docker only shows "exit code: 1")
./scripts/diagnose-build.sh

# Clean rebuild — clears stale bundle caches
./scripts/rebuild.sh

# Tests
pytest tests/ -v

# Simulator with configuration awareness
python scripts/simulate_wsn.py --api http://localhost:8000 --violation-rate 0.05

# Watch raw MQTT
docker exec dt_mosquitto mosquitto_sub -t 'wsn/#' -C 20

# Clear a violation storm (assets with no authorisations)
curl -X POST http://localhost:8000/api/config/workers/bulk-authorise \
  -H "Content-Type: application/json" \
  -d '{"asset_ids":"all","allowed_zones":["zone_A"],"mode":"replace"}'
```

`TROUBLESHOOTING.md` covers blank pages, offline sensors, upload hangs and
build failures in detail.

---

## Working style for this repo

- **Python 3.12**, type hints on public functions, dataclasses for state.
- **No migration framework** — schema changes go in `CREATE_TABLES` guarded by
  `IF NOT EXISTS`, and must be backward compatible.
- **The engine must never crash on bad data.** Wrap DB writes in `_safe_db()`;
  log and continue.
- **Config changes take effect without a restart.** If you add a setting the
  engine caches, add a `reload_*()` method and call it from `_refresh_engine()`
  in `api/routes/config.py`.
- **Verify before claiming.** The frontend cannot be compiled in every
  environment; when npm is unavailable, check syntax with `node --check` after
  stripping JSX, and scan for duplicate declarations and hook-order violations.

---

## Status

Working end to end: ingestion, state, rules, watchdog, access control,
thresholds, configuration UI, 2D/3D visualisation, five AI models, simulator,
Docker deployment.

Not done: physical hardware validation (everything is simulator-driven),
multi-gateway failover for the single mother station, and real-world accuracy
figures for the fire model — its training data is synthetic and its precision
is unproven against real incidents.
