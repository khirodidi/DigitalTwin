# =============================================================================
# engine/engine.py
# Digital Twin Engine — refactored as a class so FastAPI can start/stop it
# as a background task and reload AI models on demand.
# =============================================================================

import asyncio
import json
import logging
from datetime import datetime

import paho.mqtt.client as mqtt

from models.state       import ZoneRegistry
from engine.state_store import StateStore
from engine.rules       import check_access, evaluate_scenarios, predict_critical_states
from engine.watchdog    import SensorWatchdog
from engine.system_state import compute_system_state
from ingestion.mqtt_parser import route_message
from persistence.postgres  import (
    load_zone_registry, load_authorisations,
    save_location_event, save_env_reading,
    save_sensor_health_event, save_event,
    save_system_snapshot, create_schema,
)

logger = logging.getLogger(__name__)

MQTT_HOST   = "localhost"
MQTT_PORT   = 1883
MQTT_TOPICS = [("wsn/env", 1), ("wsn/location", 1)]
HISTORY_LIMIT = 20


class DigitalTwinEngine:
    """
    Encapsulates the entire Digital Twin Engine lifecycle.
    Started once by FastAPI lifespan; pushes all events through ws_manager.
    Call reload_ai_models() after training to hot-swap inference models.
    """

    def __init__(self, ws_manager):
        self._ws       = ws_manager
        self._store:   StateStore  = None
        self._watchdog: SensorWatchdog = None
        self._client:  mqtt.Client = None
        self._loop:    asyncio.AbstractEventLoop = None
        self._sensor_history: dict[str, list] = {}

        # AI inference (lazy-loaded after training)
        self._movement_model   = None
        self._evacuation_model = None
        self._monitor_model    = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        import os
        self._loop = asyncio.get_event_loop()

        # Ensure DB schema exists
        dsn = os.getenv("POSTGRES_DSN", "postgresql://localhost/digital_twin")
        create_schema(dsn)

        # Load static configuration
        registry       = load_zone_registry()
        authorisations = load_authorisations()

        # Initialise state store
        self._store = StateStore(registry)
        for asset_id, (sensors, zones) in authorisations.items():
            self._store.set_asset_authorisations(asset_id, sensors, zones)

        # Initialise watchdog
        self._watchdog = SensorWatchdog(
            health_store   = self._store.health,
            alert_callback = self._on_alert,
        )

        # Connect MQTT
        host = os.getenv("MQTT_HOST", MQTT_HOST)
        port = int(os.getenv("MQTT_PORT", MQTT_PORT))
        self._client = self._build_mqtt_client()
        self._client.connect(host, port, keepalive=60)
        self._client.loop_start()

        # Start watchdog as background coroutine
        asyncio.create_task(self._watchdog.run())
        logger.info("Digital Twin Engine started.")

        # Try loading pre-trained AI models if they exist
        self.reload_ai_models()

    def stop(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
        logger.info("Digital Twin Engine stopped.")

    # ── MQTT wiring ───────────────────────────────────────────────────────────

    def _build_mqtt_client(self) -> mqtt.Client:
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                for topic, qos in MQTT_TOPICS:
                    client.subscribe(topic, qos)
                logger.info("MQTT connected and subscribed.")
            else:
                logger.error(f"MQTT connection failed rc={rc}")

        def on_message(client, userdata, msg):
            try:
                payload  = json.loads(msg.payload.decode())
                msg_type, parsed = route_message(msg.topic, payload)
                if msg_type == "env":
                    asyncio.run_coroutine_threadsafe(
                        self._handle_env(parsed), self._loop)
                elif msg_type == "location":
                    asyncio.run_coroutine_threadsafe(
                        self._handle_location(parsed), self._loop)
            except Exception as e:
                logger.error(f"MQTT message error: {e}", exc_info=True)

        def on_disconnect(client, userdata, rc):
            logger.warning(f"MQTT disconnected rc={rc}")

        client = mqtt.Client()
        client.on_connect    = on_connect
        client.on_message    = on_message
        client.on_disconnect = on_disconnect
        return client

    # ── Event handlers ────────────────────────────────────────────────────────

    async def _handle_env(self, parsed: dict):
        sensor_id    = parsed["sensor_id"]
        reading_type = parsed["reading_type"]
        value        = parsed["value"]
        timestamp    = parsed["timestamp"]

        self._watchdog.on_message_received(sensor_id)
        sensor = self._store.update_sensor_reading(
            sensor_id, reading_type, value, timestamp)
        save_env_reading(sensor, reading_type, value)

        # Rolling history for prediction
        hist = self._sensor_history.setdefault(sensor_id, [])
        hist.append(sensor)
        if len(hist) > HISTORY_LIMIT:
            hist.pop(0)

        assets_in_zone = self._store.assets_in_zone(sensor.zone_id or "")

        # Rule engine
        events = evaluate_scenarios(sensor, assets_in_zone)
        events += predict_critical_states(sensor, hist)
        for event in events:
            save_event(event)
            await self._ws.push_alert(event)

        # AI monitor inference
        if self._monitor_model:
            try:
                import numpy as np
                from ai.pipeline.features import build_env_sequence
                # Build a minimal DataFrame from history for the sequence builder
                import pandas as pd
                rows = [{"sensor_id": sensor_id,
                         "reading_type": rt,
                         "value": getattr(s, rt if rt != "smoke" else "smoke", None),
                         "timestamp": s.last_time_change}
                        for s in hist
                        for rt in ["temperature", "humidity", "smoke"]
                        if getattr(s, rt if rt != "smoke" else "smoke", None) is not None]
                if rows:
                    env_df = pd.DataFrame(rows)
                    seq    = build_env_sequence(env_df, sensor_id)
                    health_feats = np.array([
                        self._store.get_health(sensor_id).consecutive_failures,
                        sensor.temperature or 0,
                        sensor.humidity    or 0,
                        float(sensor.smoke),
                    ], dtype=np.float32)
                    ai_alerts = self._monitor_model.analyse(
                        sensor_id, seq, health_feats)
                    for a in ai_alerts:
                        await self._ws.push_ai_insight(a)
            except Exception as e:
                logger.debug(f"AI monitor inference error: {e}")

        await self._ws.push_sensor_update({
            "sensor_id":        sensor.sensor_id,
            "zone_id":          sensor.zone_id,
            "temperature":      sensor.temperature,
            "humidity":         sensor.humidity,
            "smoke":            sensor.smoke,
            "env_status":       sensor.env_status,
            "last_time_change": sensor.last_time_change.isoformat(),
        })
        await self._push_system_state()

    async def _handle_location(self, parsed: dict):
        asset_id  = parsed["asset_id"]
        sensor_id = parsed["sensor_id"]
        timestamp = parsed["timestamp"]

        self._watchdog.on_message_received(sensor_id)
        asset = self._store.update_asset_location(asset_id, sensor_id, timestamp)

        if asset.has_changed_sensor():
            save_location_event(asset)

        # Access control
        violation = check_access(asset)
        if violation:
            save_event(violation)
            await self._ws.push_alert(violation)

        # AI movement inference
        if self._movement_model and asset.has_changed_sensor():
            try:
                import pandas as pd
                from ai.pipeline.features import build_movement_features
                rows = [{
                    "asset_id":           asset_id,
                    "current_zone_id":    asset.current_zone_id,
                    "current_sensor_id":  asset.current_sensor_id,
                    "authorisation":      asset.access_status,
                    "timestamp":          timestamp,
                }]
                loc_df = pd.DataFrame(rows)
                feats  = build_movement_features(loc_df, asset_id)
                result = self._movement_model.score(feats)
                if result.get("is_inefficient"):
                    await self._ws.push_ai_insight({
                        **result,
                        "type":  "movement_inefficiency",
                        "level": "warning",
                    })
            except Exception as e:
                logger.debug(f"AI movement inference error: {e}")

        await self._ws.push_asset_update({
            "id":                   asset.id,
            "asset_type":           asset.asset_type,
            "current_sensor_id":    asset.current_sensor_id,
            "current_zone_id":      asset.current_zone_id,
            "previous_sensor_id":   asset.previous_sensor_id,
            "previous_zone_id":     asset.previous_zone_id,
            "time_change_location": asset.time_change_location.isoformat()
                                    if asset.time_change_location else None,
            "access_status":        asset.access_status,
        })
        await self._push_system_state()

    def _on_alert(self, alert: dict):
        """Sync callback from watchdog — schedule push on the event loop."""
        save_event(alert)
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._ws.push_alert(alert), self._loop)
            asyncio.run_coroutine_threadsafe(
                self._ws.push_health_update(alert), self._loop)

    async def _push_system_state(self):
        state = compute_system_state(
            self._store.all_assets(),
            self._store.all_sensors(),
            self._store.all_health(),
        )
        save_system_snapshot(state)
        await self._ws.push_system_state(state.to_dict())

    # ── Snapshot (sent to frontend on WS connect) ─────────────────────────────

    def get_snapshot(self) -> dict:
        """Returns the full live state for a newly connected client."""
        if not self._store:
            return {}
        state = compute_system_state(
            self._store.all_assets(),
            self._store.all_sensors(),
            self._store.all_health(),
        )
        return {
            "system_state": state.to_dict(),
            "sensors": [
                {
                    "sensor_id":        s.sensor_id,
                    "zone_id":          s.zone_id,
                    "temperature":      s.temperature,
                    "humidity":         s.humidity,
                    "smoke":            s.smoke,
                    "env_status":       s.env_status,
                    "last_time_change": s.last_time_change.isoformat(),
                }
                for s in self._store.all_sensors()
            ],
            "health": [
                {
                    "sensor_id":            h.sensor_id,
                    "zone_id":              h.zone_id,
                    "status":               h.status,
                    "last_heartbeat":       h.last_heartbeat.isoformat()
                                            if h.last_heartbeat else None,
                    "consecutive_failures": h.consecutive_failures,
                }
                for h in self._store.all_health()
            ],
            "assets": [
                {
                    "id":                   a.id,
                    "asset_type":           a.asset_type,
                    "current_sensor_id":    a.current_sensor_id,
                    "current_zone_id":      a.current_zone_id,
                    "previous_sensor_id":   a.previous_sensor_id,
                    "previous_zone_id":     a.previous_zone_id,
                    "time_change_location": a.time_change_location.isoformat()
                                            if a.time_change_location else None,
                    "access_status":        a.access_status,
                }
                for a in self._store.all_assets()
            ],
        }

    # ── AI model hot-reload ───────────────────────────────────────────────────

    def reload_ai_models(self):
        """
        Load (or reload) all three AI models from disk.
        Called at startup and by AITrainer after each retraining run.
        Safe to call at any time — falls back to None if models not found.
        """
        from pathlib import Path
        MODEL_DIR = Path("models")

        # Movement optimiser
        try:
            from ai.models.movement_optimiser import MovementOptimiserInference
            self._movement_model = MovementOptimiserInference(
                model_path = str(MODEL_DIR / "movement_lstm.pt"),
            )
            logger.info("Movement model loaded.")
        except Exception as e:
            logger.info(f"Movement model not available yet: {e}")
            self._movement_model = None

        # System monitor
        try:
            from ai.models.system_monitor import SystemMonitorInference
            self._monitor_model = SystemMonitorInference(
                autoencoder_path   = str(MODEL_DIR / "autoencoder.pt"),
                forecaster_path    = str(MODEL_DIR / "forecaster.pt"),
                failure_model_path = str(MODEL_DIR / "failure_xgb.joblib"),
            )
            logger.info("System monitor models loaded.")
        except Exception as e:
            logger.info(f"Monitor models not available yet: {e}")
            self._monitor_model = None

        # Evacuation planner (stateful — rebuilt on reload)
        try:
            from ai.models.smart_evacuation import (
                SmartEvacuationPlanner, DangerScorePredictor, ZoneGraph, ZoneNode
            )
            predictor = DangerScorePredictor(
                model_path = str(MODEL_DIR / "danger_xgb.joblib"),
            )
            # Build zone graph from registry
            graph = ZoneGraph()
            if self._store:
                reg = self._store._registry
                for zone_id in reg.all_zones():
                    graph.add_zone(ZoneNode(
                        zone_id    = zone_id,
                        sensor_ids = reg.get_sensors(zone_id),
                        is_exit    = zone_id.startswith("exit"),
                    ))
            self._evacuation_model = SmartEvacuationPlanner(graph, predictor)
            logger.info("Evacuation planner loaded.")
        except Exception as e:
            logger.info(f"Evacuation model not available yet: {e}")
            self._evacuation_model = None
