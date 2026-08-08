# Digital Twin — Factory Monitoring System

Real-time factory digital twin built on a wireless sensor network (WSN).  
Tracks workers and mobile objects, monitors the environment, enforces access control, and runs AI models that improve over time.

---

## Quick start (Docker)

```bash
# 1. Clone and enter
git clone https://github.com/<you>/digitaltwin.git && cd digitaltwin

# 2. (Optional) drop your factory blueprint image into frontend/public/
cp my_factory.png frontend/public/factory_blueprint.png

# 3. Configure (edit docker-compose.yml → frontend.build.args if needed)
#    REACT_APP_GRID_COLS=6, REACT_APP_GRID_ROWS=5, REACT_APP_SENSOR_COUNT=30

# 4. Start all services
docker compose up --build

# 5. Seed the database
docker exec -i dt_postgres psql -U dt_user -d digital_twin < scripts/seed_db.sql

# 6. Open dashboard
open http://localhost:3000

# 7. (Optional) Run the WSN simulator
docker compose --profile sim up simulator
# or locally:
python scripts/simulate_wsn.py --cols 6 --rows 5 --interval 2
```

---

## Frontend configuration (env vars)

Set these in `docker-compose.yml → frontend.build.args` **or** in `frontend/.env`:

| Variable | Default | Description |
|---|---|---|
| `REACT_APP_FACTORY_IMAGE` | *(none)* | Filename of blueprint image in `frontend/public/` |
| `REACT_APP_GRID_COLS` | `6` | Sensors per row |
| `REACT_APP_GRID_ROWS` | `5` | Sensors per column |
| `REACT_APP_SENSOR_COUNT` | `30` | Total sensors (usually COLS × ROWS) |
| `REACT_APP_FACTORY_NAME` | `Factory` | Name shown in the dashboard header |
| `REACT_APP_API_URL` | `http://localhost:8000` | Backend REST URL |
| `REACT_APP_WS_URL` | `ws://localhost:8000/ws` | Backend WebSocket URL |

---

## Dashboard features

### Sensor grid
Each sensor cell shows:
- **Background colour** = sensor status  
  🟢 green = normal · 🟡 amber = warning/degraded · 🔴 red = critical/smoke · ⬛ gray = offline
- **Readings** — temperature (°C), humidity (%), smoke indicator
- **Asset counts** — e.g. 👷×2 🚜×1 (grouped by type)
- **Pulse animation** — critical sensors glow and pulse red

### Click any sensor
Opens a detail panel showing:
- Sensor ID, zone, health status, last heartbeat
- Temperature, humidity, smoke readings
- All assets currently in that sensor's range, **grouped by type**
- Each asset's access status (authorised / violation / unknown)

### Status bar
Live counts: sensors online/degraded/offline · zones critical · access violations · WS connection status

### Alert panel
Live feed of all rule-triggered alerts and AI insights, filterable by level or AI/rule source.

---

## WSN data formats

**Location message** (topic `wsn/location`):
```json
["worker_id|object_id", "sensor_id", "2026-05-17T10:23:00Z"]
```

**Environmental message** (topic `wsn/env`):
```json
["sensor_id", "temperature|humidity|smoke", 47.2, "2026-05-17T10:23:00Z"]
```

---

## Simulator

```bash
python scripts/simulate_wsn.py --cols 6 --rows 5 --interval 2 --fire-delay 120
```

| Flag | Default | Description |
|---|---|---|
| `--cols` | 6 | Grid columns (match REACT_APP_GRID_COLS) |
| `--rows` | 5 | Grid rows (match REACT_APP_GRID_ROWS) |
| `--interval` | 2.0 | Seconds per publish cycle |
| `--fire-delay` | 300 | Seconds until fire event starts |
| `--host` | localhost | MQTT broker host |
| `--port` | 1883 | MQTT broker port |

Assets move **only to adjacent sensors** (grid neighbours N/S/E/W) — no teleporting.  
A simulated fire starts in the centre sensor after `--fire-delay` seconds: temperature ramps up, smoke triggers, and the evacuation AI fires routes.

---

## AI models

| Model | Algorithm | Retrains | Cold start |
|---|---|---|---|
| Movement optimiser | LSTM sequence classifier | Weekly | Heuristic rules |
| Smart evacuation | XGBoost danger score + Dijkstra routing | On new incidents | Threshold rules |
| System monitor | LSTM Autoencoder + Forecaster + XGBoost failure | Nightly | Threshold rules |

```bash
# Run all training manually
python -m ai.training.train_all

# Single model
python -m ai.training.train_all --model movement --days 30
```

---

## Project structure

```
digitaltwin/
├── models/          state.py — all dataclasses + ZoneRegistry
├── ingestion/       mqtt_parser.py — parse WSN messages
├── engine/          engine.py · state_store.py · rules.py · watchdog.py · system_state.py
├── persistence/     postgres.py — full DB schema + read/write
├── api/             main.py (FastAPI) · ws_manager.py · routes/
├── ai/
│   ├── models/      movement_optimiser.py · smart_evacuation.py · system_monitor.py
│   ├── pipeline/    features.py — feature engineering
│   └── training/    movement.py · evacuation.py · monitor.py · drift.py · train_all.py
├── frontend/
│   ├── public/      index.html  ← drop blueprint image here
│   └── src/
│       ├── config/  factory.js  ← reads all env vars
│       ├── hooks/   useWebSocket.js · useApi.js
│       └── components/
│           ├── FactoryMap.jsx   ← blueprint + sensor grid + click handler
│           ├── SensorCell.jsx   ← one grid cell (status colour + readings + counts)
│           ├── SensorDetail.jsx ← click panel (assets grouped by type)
│           ├── StatusBar.jsx
│           ├── AlertPanel.jsx
│           └── AssetList.jsx
├── scripts/
│   ├── simulate_wsn.py   ← full WSN simulator (neighbor movement + env sensing)
│   ├── seed_db.sql       ← seed zones, sensors, assets, authorisations
│   └── push_to_github.sh
├── tests/           test_engine.py · test_ai.py · conftest.py
├── docs/            architecture diagrams (JSX)
├── docker-compose.yml
├── Dockerfile.backend · Dockerfile.frontend
└── requirements.txt
```

---

## Running tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

---

## License

MIT
