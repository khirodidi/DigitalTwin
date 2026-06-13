# Digital Twin — Factory Monitoring System

A full-stack Digital Twin system for factory monitoring, built on a wireless sensor network (WSN). Provides real-time asset localisation, environmental monitoring, access control, and AI-driven optimisation.

---

## System Overview

```
WSN Sensors & Tags
      │  short-range wireless
      ▼
Mother Station  (single network gateway)
      │  MQTT / TCP-IP
      ▼
MQTT Broker  (Mosquitto)
      │  wsn/env · wsn/location
      ├─────────────────────┐
      ▼                     ▼
PostgreSQL            Digital Twin Engine
(persistence)         │  State · Rules · Watchdog · Predictor · Publisher
                      │
                      ├── AI Layer (Movement · Evacuation · Monitor)
                      │
                      ▼
              REST API + WebSocket
                      │
                      ▼
              Frontend Dashboard
```

---

## Features

### Core Digital Twin
| Feature | Description |
|---|---|
| **Zone-based localisation** | Grid sensor coverage — every factory cell has a sensor |
| **Asset tracking** | Workers and mobile objects located by sensor connection |
| **Environmental monitoring** | Temperature, humidity, smoke per sensor/zone in real time |
| **Access control** | Per-asset authorisation by sensor_id or zone_id |
| **Sensor health** | Online / Degraded / Offline detection with watchdog |
| **If-else scenarios** | Configurable reactive rules (smoke → evacuate, high temp → inspect) |
| **Predictive alerts** | Trend-based early warning before thresholds are breached |
| **SystemState** | Global factory status (NOMINAL / DEGRADED / CRITICAL) pushed via WebSocket |

### AI Layer
| Model | Purpose |
|---|---|
| **Movement Optimiser** | LSTM + PPO RL — detects unnecessary movements, scores efficiency |
| **Smart Evacuation** | XGBoost danger scoring + Dijkstra routing — per-asset evacuation routes |
| **System Monitor** | LSTM Autoencoder (anomaly) + Forecaster (temp/hum) + XGBoost (sensor failure) |

---

## Data Formats

### WSN → Mother Station → MQTT Broker

**Localisation message** (topic: `wsn/location`):
```json
["worker_id|object_id", "sensor_id", "2026-05-17T10:23:00Z"]
```

**Environmental message** (topic: `wsn/env`):
```json
["sensor_id", "temperature|humidity|smoke", 47.2, "2026-05-17T10:23:00Z"]
```

### State Classes

**AssetState** (in-memory, per worker or object):
```python
{
  "id":                   "W1",
  "asset_type":           "worker",
  "current_sensor_id":    "S6",
  "current_zone_id":      "zone_A",
  "previous_sensor_id":   "S5",
  "previous_zone_id":     "zone_A",
  "time_change_location": "2026-05-17T10:23:00Z",
  "allowed_sensors":      {"S1","S2","S5","S6"},
  "allowed_zones":        {"zone_A"},
  "access_status":        "authorised"
}
```

**SensorState** (in-memory, per sensor/grid cell):
```python
{
  "sensor_id":        "S3",
  "zone_id":          "zone_B",
  "temperature":      47.2,
  "humidity":         61.0,
  "smoke":            False,
  "env_status":       "normal",
  "last_time_change": "2026-05-17T10:23:00Z"
}
```

---

## Project Structure

```
digitaltwin/
│
├── models/
│   └── state.py                  # All dataclasses, enums, ZoneRegistry
│
├── ingestion/
│   └── mqtt_parser.py            # Parse WSN messages from mother station
│
├── engine/
│   ├── engine.py                 # Main MQTT loop — ties everything together
│   ├── state_store.py            # In-memory state (assets + sensors + health)
│   ├── rules.py                  # Access control · if-else scenarios · prediction
│   ├── watchdog.py               # Sensor disconnection detection
│   └── system_state.py           # Global system state aggregator
│
├── persistence/
│   └── postgres.py               # Full DB schema + all read/write operations
│
├── publisher.py                  # WebSocket broadcast to frontend
│
├── ai/
│   ├── pipeline/
│   │   └── features.py           # Feature engineering (shared by all AI models)
│   ├── models/
│   │   ├── movement_optimiser.py # LSTM + PPO — movement efficiency
│   │   ├── smart_evacuation.py   # XGBoost + Dijkstra — evacuation routing
│   │   └── system_monitor.py     # Autoencoder + Forecaster + Failure predictor
│   ├── training/                 # Training scripts (to be added)
│   └── inference/                # Inference engine integration (to be added)
│
├── docs/                         # Architecture diagrams (JSX)
├── tests/                        # Unit tests (to be added)
├── scripts/                      # Utility scripts
│
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Installation

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Mosquitto MQTT broker
- Node.js 18+ (for frontend diagrams)

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/digitaltwin.git
cd digitaltwin

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your PostgreSQL DSN and MQTT host

# 5. Initialise the database
python -c "from persistence.postgres import create_schema; create_schema()"

# 6. Start the engine
python -m engine.engine
```

### MQTT Broker (Mosquitto)

```bash
# Install
sudo apt install mosquitto mosquitto-clients   # Ubuntu/Debian

# Start
mosquitto -c /etc/mosquitto/mosquitto.conf

# Test
mosquitto_pub -t wsn/env      -m '["S1","temperature",24.5,"2026-05-17T10:23:00Z"]'
mosquitto_pub -t wsn/location -m '["W1","S6","2026-05-17T10:23:00Z"]'
```

---

## Configuration

Create a `.env` file in the project root:

```env
# Database
POSTGRES_DSN=postgresql://user:password@localhost/digital_twin

# MQTT
MQTT_HOST=localhost
MQTT_PORT=1883

# Engine
HEARTBEAT_INTERVAL=5
DEGRADED_THRESHOLD=2
OFFLINE_THRESHOLD=5

# AI thresholds
ANOMALY_THRESHOLD=0.75
FAILURE_THRESHOLD=0.70
TEMP_CRITICAL=60.0
TEMP_WARNING=50.0
HUMIDITY_CRITICAL=85.0
HUMIDITY_WARNING=70.0
```

---

## AI Models

### Cold Start Strategy
All three models fall back to rule-based heuristics until sufficient data is collected:
- **Movement Optimiser**: activates after 30 days of location_events
- **Smart Evacuation**: danger scoring rule-based until 50+ labelled incidents
- **System Monitor**: autoencoder needs 7+ days of normal operation data

### Training Schedule
```bash
# Run nightly training pipeline
python -m ai.training.train_all --date $(date +%Y-%m-%d)
```

### Model Storage
Trained models are stored in `models/` using MLflow:
```bash
mlflow ui --port 5000    # view experiments at http://localhost:5000
```

---

## Architecture Diagrams

Interactive diagrams are in `docs/`:
- `diagrams.jsx` — 5-tab engine + grid + flow diagrams
- `full_architecture.jsx` — 7-layer full system architecture
- `ai_architecture.jsx` — 5-tab AI layer diagrams

View locally:
```bash
npx create-react-app diagram-viewer
cp docs/*.jsx diagram-viewer/src/
cd diagram-viewer && npm start
```

---

## Roadmap

- [ ] Frontend dashboard (React + Three.js floor plan)
- [ ] REST API (FastAPI)
- [ ] WebSocket server (FastAPI + websockets)
- [ ] AI training scripts
- [ ] Docker Compose setup
- [ ] Unit tests
- [ ] CI/CD pipeline

---

## License

MIT
