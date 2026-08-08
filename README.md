# Digital Twin — Factory Monitoring System

Real-time factory digital twin: WSN sensor ingestion, zone-based asset tracking,
environmental monitoring, access control, three AI models, and a configurable
React dashboard with a full configuration UI.

---

## Quick start

```bash
# 1. Start everything
docker compose up --build

# 2. Seed the database (once)
docker exec -i dt_postgres psql -U dt_user -d digital_twin < scripts/seed_db.sql

# 3. Open the dashboard
open http://localhost:3000

# 4. Start the simulator (separate terminal or profile)
docker compose --profile sim up simulator
# or locally:
python scripts/simulate_wsn.py
```

If Docker Hub times out during build, pull the base images first:
```bash
docker pull python:3.12-slim && docker pull node:20-alpine
docker pull nginx:alpine && docker pull postgres:16-alpine
docker pull eclipse-mosquitto:2
docker compose up --build
```

---

## Configuration page

Click **⚙️ Configuration** in the dashboard header. Four tabs:

| Tab | What you configure |
|---|---|
| 🏭 Factory Layout | Factory name, blueprint image filename, grid N×M, zones + which sensors belong to each |
| 📡 Sensors | Per sensor: coverage type (passage / machine / storage / exit), passable flag, description |
| 👷 Workers | Add/edit/delete assets; set zone-level and sensor-level authorisations |
| 📍 Trajectory | Pick a worker → see their movement path drawn on the grid with access status colours |

All settings persist to PostgreSQL and are read by the simulator on startup.

---

## Blueprint image

1. Put your floor plan in `frontend/public/` (e.g. `factory.png`)
2. Either set it in the Configuration page, or in `docker-compose.yml`:
   ```yaml
   REACT_APP_FACTORY_IMAGE: "factory.png"
   ```
3. Rebuild the frontend: `docker compose up --build frontend`

---

## Config-aware simulator

The simulator reads live configuration from the API and simulates movement
that respects it.

```bash
python scripts/simulate_wsn.py                       # reads config from API
python scripts/simulate_wsn.py --violation-rate 0.08 # more violations
python scripts/simulate_wsn.py --no-config --cols 8 --rows 6 --workers 10
```

| Config setting | Simulator behaviour |
|---|---|
| `passable = false` | Asset never enters that cell |
| `coverage_type = machine` | Dwell 4–10 ticks · base temp 28–34 °C · forklifts avoid |
| `coverage_type = storage` | Dwell 2–5 ticks · base temp 16–20 °C |
| `coverage_type = passage` | Dwell 1–2 ticks · base temp 20–25 °C |
| `coverage_type = exit` | Dwell 1 tick · base temp 15–20 °C |
| Worker authorisations | Worker stays inside their allowed zones |
| Assets in DB | Real IDs and names used |

Movement profile per type:

| Type | Move prob | Avoids |
|---|---|---|
| worker | 0.35 | — |
| forklift | 0.45 | machine cells |
| pallet | 0.06 | machine, exit |

---

## Access control

```
Worker seen at sensor S07 (in zone_B):
  1. Is S07 OFFLINE?              → UNKNOWN  (amber, no alert)
  2. Is 'S07' in allowed_sensors? → AUTHORISED (green)
  3. Is 'zone_B' in allowed_zones?→ AUTHORISED (green)
  4. Otherwise                    → VIOLATION  (red + alert)
```

Set authorisations in the Configuration page → Workers tab → **Auth** button,
or via the API:
```bash
curl -X PUT http://localhost:8000/api/config/workers/W01/authorisations \
  -H "Content-Type: application/json" \
  -d '{"allowed_zones":["zone_A","zone_B"],"allowed_sensors":[]}'
```

---

## AI models

| Model | Algorithm | Retrains |
|---|---|---|
| Movement optimiser | LSTM sequence classifier | Weekly |
| Smart evacuation | XGBoost danger + Dijkstra routing | On new incidents |
| System monitor | LSTM-AE + LSTM forecaster + XGBoost failure | Nightly 02:00 |

```bash
python -m ai.training.train_all                 # all models
python -m ai.training.train_all --model monitor # one model
```

Drift detection (PSI > 0.20) triggers retraining outside the schedule.
Models hot-reload into the running engine without restart.

---

## Project structure

```
digitaltwin/
├── models/state.py              AssetState · SensorState · SensorHealthState · ZoneRegistry
├── ingestion/mqtt_parser.py     Parse wsn/env and wsn/location
├── engine/
│   ├── engine.py                DigitalTwinEngine (FastAPI lifespan)
│   ├── state_store.py           In-memory O(1) state
│   ├── rules.py                 Access control · scenarios · prediction
│   ├── watchdog.py              Sensor disconnection detection
│   └── system_state.py          Global state aggregator
├── persistence/postgres.py      11-table schema + read/write
├── api/
│   ├── main.py                  FastAPI + WebSocket + lifespan
│   ├── ws_manager.py            WebSocket broadcast
│   └── routes/                  assets · sensors · zones · events · system · config
├── ai/
│   ├── models/                  3 AI models
│   ├── pipeline/features.py     Feature engineering
│   └── training/                Training pipelines + APScheduler + drift
├── frontend/src/
│   ├── App.jsx                  Root + page routing
│   ├── pages/ConfigPage.jsx     4-tab configuration
│   ├── components/              FactoryMap · SensorCell · SensorDetail · StatusBar
│   │                            AlertPanel · AssetList · FactoryLayout
│   │                            SensorEditor · WorkerManager · TrajectoryMap
│   └── hooks/                   useWebSocket · useApi
├── scripts/
│   ├── simulate_wsn.py          Config-aware WSN simulator
│   └── seed_db.sql              Zones · sensors · assets · authorisations
├── tests/                       test_engine.py · test_ai.py
└── docker-compose.yml           postgres · mosquitto · backend · frontend · simulator
```

---

## API reference

**Monitoring**
| Method | Endpoint |
|---|---|
| GET | `/api/assets` · `/api/sensors` · `/api/zones` · `/api/events` |
| GET | `/api/system/state` · `/api/system/layout` |
| WS | `/ws` — real-time push |

**Configuration**
| Method | Endpoint |
|---|---|
| GET/PUT | `/api/config/factory` |
| GET/POST/DELETE | `/api/config/zones` |
| GET/PUT | `/api/config/sensors/{id}` |
| GET/POST/PUT/DELETE | `/api/config/workers` |
| GET/PUT | `/api/config/workers/{id}/authorisations` |
| GET | `/api/config/workers/{id}/trajectory?limit=N` |

---

## Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

---

## Database

Data lives in the Docker named volume `postgres_data`.

```bash
docker compose down          # keeps data
docker compose down -v       # DESTROYS data — re-seed after

# Manual backup
docker exec dt_postgres pg_dump -U dt_user digital_twin > backup.sql

# Restore
docker exec -i dt_postgres psql -U dt_user digital_twin < backup.sql
```

---

## License

MIT
