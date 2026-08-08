# =============================================================================
# engine/engine.py  —  DigitalTwinEngine: main class started by FastAPI lifespan
# =============================================================================
import asyncio, json, logging, os
from datetime import datetime
import paho.mqtt.client as mqtt

from models.state        import ZoneRegistry
from engine.state_store  import StateStore
from engine.rules        import check_access, evaluate_scenarios, predict_critical_states
from engine.watchdog     import SensorWatchdog
from engine.system_state import compute_system_state
from ingestion.mqtt_parser import route_message
from persistence.postgres  import (
    load_zone_registry, load_authorisations,
    save_location_event, save_env_reading,
    save_event, save_system_snapshot, create_schema,
)

logger = logging.getLogger(__name__)
MQTT_TOPICS   = [("wsn/env", 1), ("wsn/location", 1)]
HISTORY_LIMIT = 20


class DigitalTwinEngine:
    def __init__(self, ws_manager):
        self._ws             = ws_manager
        self._store          = None
        self._watchdog       = None
        self._client         = None
        self._loop           = None
        self._sensor_history : dict[str, list] = {}
        self._movement_model = None
        self._monitor_model  = None
        self._evac_model     = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    async def start(self):
        self._loop = asyncio.get_event_loop()
        dsn = os.getenv("POSTGRES_DSN", "postgresql://localhost/digital_twin")
        create_schema(dsn)
        registry       = load_zone_registry()
        authorisations = load_authorisations()
        self._store    = StateStore(registry)
        for aid, (sensors, zones) in authorisations.items():
            self._store.set_asset_authorisations(aid, sensors, zones)
        self._watchdog = SensorWatchdog(self._store.health, self._on_alert)
        host = os.getenv("MQTT_HOST", "localhost")
        port = int(os.getenv("MQTT_PORT", 1883))
        self._client = self._build_mqtt()
        self._client.connect(host, port, keepalive=60)
        self._client.loop_start()
        asyncio.create_task(self._watchdog.run())
        self.reload_ai_models()
        logger.info("Digital Twin Engine started.")

    def stop(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()

    # ── MQTT ───────────────────────────────────────────────────────────────────
    def _build_mqtt(self):
        def on_connect(c, u, f, rc):
            if rc == 0:
                for t, q in MQTT_TOPICS: c.subscribe(t, q)
                logger.info("MQTT connected.")
            else:
                logger.error(f"MQTT failed rc={rc}")

        def on_message(c, u, msg):
            try:
                payload        = json.loads(msg.payload.decode())
                msg_type, parsed = route_message(msg.topic, payload)
                coro = self._handle_env(parsed) if msg_type == "env" else self._handle_location(parsed)
                asyncio.run_coroutine_threadsafe(coro, self._loop)
            except Exception as e:
                logger.error(f"MQTT message error: {e}", exc_info=True)

        cl = mqtt.Client()
        cl.on_connect = on_connect
        cl.on_message = on_message
        cl.on_disconnect = lambda c, u, rc: logger.warning(f"MQTT disconnected rc={rc}")
        return cl

    # ── Handlers ───────────────────────────────────────────────────────────────
    async def _handle_env(self, p: dict):
        sid, rt, val, ts = p["sensor_id"], p["reading_type"], p["value"], p["timestamp"]
        self._watchdog.on_message_received(sid)
        sensor = self._store.update_sensor_reading(sid, rt, val, ts)
        save_env_reading(sensor, rt, val)
        hist = self._sensor_history.setdefault(sid, [])
        hist.append(sensor)
        if len(hist) > HISTORY_LIMIT: hist.pop(0)
        assets = self._store.assets_in_zone(sensor.zone_id or "")
        events = evaluate_scenarios(sensor, assets) + predict_critical_states(sensor, hist)
        for ev in events:
            save_event(ev)
            await self._ws.push_alert(ev)
        if self._monitor_model:
            try:
                import numpy as np, pandas as pd
                from ai.pipeline.features import build_env_sequence
                rows = [{"sensor_id":sid,"reading_type":rt2,"value":getattr(s, "temperature" if rt2=="temperature" else "humidity" if rt2=="humidity" else "smoke",None),"timestamp":s.last_time_change}
                        for s in hist for rt2 in ["temperature","humidity","smoke"]
                        if getattr(s,"temperature" if rt2=="temperature" else "humidity" if rt2=="humidity" else "smoke",None) is not None]
                if rows:
                    seq = build_env_sequence(pd.DataFrame(rows), sid)
                    hf  = np.array([self._store.get_health(sid).consecutive_failures if self._store.get_health(sid) else 0,
                                    sensor.temperature or 0, sensor.humidity or 0, float(sensor.smoke)], dtype=np.float32)
                    for a in self._monitor_model.analyse(sid, seq, hf):
                        await self._ws.push_ai_insight(a)
            except Exception as e:
                logger.debug(f"Monitor inference: {e}")
        await self._ws.push_sensor_update({
            "sensor_id":sid,"zone_id":sensor.zone_id,
            "temperature":sensor.temperature,"humidity":sensor.humidity,
            "smoke":sensor.smoke,"env_status":sensor.env_status,
            "last_time_change":sensor.last_time_change.isoformat(),
        })
        await self._push_system_state()

    async def _handle_location(self, p: dict):
        aid, sid, ts = p["asset_id"], p["sensor_id"], p["timestamp"]
        self._watchdog.on_message_received(sid)
        asset = self._store.update_asset_location(aid, sid, ts)
        if asset.has_changed_sensor(): save_location_event(asset)
        violation = check_access(asset)
        if violation:
            save_event(violation)
            await self._ws.push_alert(violation)
        await self._ws.push_asset_update({
            "id":aid,"asset_type":asset.asset_type,
            "current_sensor_id":asset.current_sensor_id,"current_zone_id":asset.current_zone_id,
            "previous_sensor_id":asset.previous_sensor_id,"previous_zone_id":asset.previous_zone_id,
            "time_change_location":asset.time_change_location.isoformat() if asset.time_change_location else None,
            "access_status":asset.access_status,
        })
        await self._push_system_state()

    def _on_alert(self, alert: dict):
        save_event(alert)
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._ws.push_alert(alert), self._loop)
            asyncio.run_coroutine_threadsafe(self._ws.push_health_update(alert), self._loop)

    async def _push_system_state(self):
        state = compute_system_state(self._store.all_assets(), self._store.all_sensors(), self._store.all_health())
        save_system_snapshot(state)
        await self._ws.push_system_state(state.to_dict())

    def get_snapshot(self) -> dict:
        if not self._store: return {}
        state = compute_system_state(self._store.all_assets(), self._store.all_sensors(), self._store.all_health())
        def _asset(a): return {"id":a.id,"asset_type":a.asset_type,"current_sensor_id":a.current_sensor_id,
            "current_zone_id":a.current_zone_id,"previous_sensor_id":a.previous_sensor_id,
            "previous_zone_id":a.previous_zone_id,
            "time_change_location":a.time_change_location.isoformat() if a.time_change_location else None,
            "access_status":a.access_status}
        def _sensor(s): return {"sensor_id":s.sensor_id,"zone_id":s.zone_id,"temperature":s.temperature,
            "humidity":s.humidity,"smoke":s.smoke,"env_status":s.env_status,
            "last_time_change":s.last_time_change.isoformat()}
        def _health(h): return {"sensor_id":h.sensor_id,"zone_id":h.zone_id,"status":h.status,
            "last_heartbeat":h.last_heartbeat.isoformat() if h.last_heartbeat else None,
            "consecutive_failures":h.consecutive_failures}
        return {"system_state":state.to_dict(),
                "sensors":[_sensor(s) for s in self._store.all_sensors()],
                "health": [_health(h) for h in self._store.all_health()],
                "assets": [_asset(a)  for a in self._store.all_assets()]}

    def reload_ai_models(self):
        from pathlib import Path
        MODEL_DIR = Path("models")
        for name, cls_path, attr in [
            ("movement_lstm.pt",    ("ai.models.movement_optimiser","MovementOptimiserInference"), "_movement_model"),
            ("autoencoder.pt",      ("ai.models.system_monitor",    "SystemMonitorInference"),     "_monitor_model"),
        ]:
            try:
                import importlib
                mod = importlib.import_module(cls_path[0])
                cls = getattr(mod, cls_path[1])
                setattr(self, attr, cls(model_path=str(MODEL_DIR/name)))
                logger.info(f"AI model loaded: {name}")
            except Exception as e:
                logger.info(f"AI model not available ({name}): {e}")
                setattr(self, attr, None)
