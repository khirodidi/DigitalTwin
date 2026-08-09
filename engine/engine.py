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
from engine.thresholds    import resolver as threshold_resolver
from ingestion.mqtt_parser import route_message
from persistence.postgres  import (
    load_zone_registry, load_authorisations,
    save_location_event, save_env_reading,
    save_event, save_system_snapshot, create_schema, load_asset_meta,
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
        self._known_sensors  : set[str] = set()
        self._known_assets   : set[str] = set()
        self._movement_model = None
        self._monitor_model  = None
        self._evac_model     = None
        self._fire_model     = None      # ④ fire detection & localisation
        self._latest_env     = {}        # sensor_id → last reading, for the grid
        self._fire_active    = False

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
        # Display names and types so the dashboard shows names, not IDs
        try:
            for aid, meta in load_asset_meta().items():
                self._store.set_asset_meta(aid, meta["name"], meta["asset_type"])
        except Exception as e:
            logger.warning(f"Could not load asset names: {e}")
        # Resolve per-sensor thresholds (sensor → zone → global)
        threshold_resolver.reload()

        self._known_sensors = set(registry.all_sensors())
        try:
            self._known_assets = set(load_asset_meta().keys())
        except Exception:
            self._known_assets = set()
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
                coro = (self._handle_env(parsed) if msg_type == "env"
                        else self._handle_location(parsed))
                fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
                # Log handler exceptions — previously these vanished silently
                fut.add_done_callback(
                    lambda f: f.exception() and
                              logger.error(f"Handler error: {f.exception()}", exc_info=False))
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

        # 1) Health first — a sensor that speaks is ONLINE regardless of the DB
        self._watchdog.on_message_received(sid)

        # 2) In-memory state — this is what the dashboard renders
        sensor = self._store.update_sensor_reading(sid, rt, val, ts)

        # 3) Persistence is best-effort: never let a DB error stop the live feed
        self._safe_db(lambda: self._ensure_sensor_row(sid, sensor.zone_id))
        self._safe_db(lambda: save_env_reading(sensor, rt, val))

        hist = self._sensor_history.setdefault(sid, [])
        hist.append(sensor)
        if len(hist) > HISTORY_LIMIT: hist.pop(0)
        assets = self._store.assets_in_zone(sensor.zone_id or "")
        events = evaluate_scenarios(sensor, assets) + predict_critical_states(sensor, hist)
        for ev in events:
            self._safe_db(lambda e=ev: save_event(e))
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
        # ── ④ Fire detection & localisation — needs the WHOLE grid ──────────
        self._latest_env[sid] = {"temperature": sensor.temperature,
                                 "humidity":    sensor.humidity,
                                 "smoke":       sensor.smoke}
        if self._fire_model:
            try:
                health_map = {h.sensor_id: h.status for h in self._store.all_health()}
                fire = self._fire_model.update(self._latest_env, health_map)
                if fire:
                    if not self._fire_active:
                        self._fire_active = True
                        self._safe_db(lambda f=fire: save_event(f))
                        await self._ws.push_alert(fire)
                    await self._ws.push_ai_insight({**fire, "type": "fire_localisation"})
                    # Feed the fire map into evacuation routing
                    if self._evac_model and hasattr(self._evac_model, "set_fire_map"):
                        self._evac_model.set_fire_map(self._fire_model.fire_map())
                else:
                    self._fire_active = False
            except Exception as e:
                logger.debug(f"Fire inference: {e}")

        th = threshold_resolver.get(sid, sensor.zone_id)
        await self._ws.push_sensor_update({
            "sensor_id":sid,"zone_id":sensor.zone_id,
            "temperature":sensor.temperature,"humidity":sensor.humidity,
            "smoke":sensor.smoke,"env_status":sensor.env_status,
            "last_time_change":sensor.last_time_change.isoformat(),
            "thresholds": th.to_dict(),
        })

        # Push health too — otherwise a sensor that was never seeded stays
        # rendered as OFFLINE even though readings are arriving.
        h = self._store.get_health(sid)
        if h:
            await self._ws.push_health_update({
                "sensor_id": h.sensor_id, "zone_id": h.zone_id,
                "status": h.status,
                "last_heartbeat": h.last_heartbeat.isoformat() if h.last_heartbeat else None,
                "consecutive_failures": h.consecutive_failures,
            })

        await self._push_system_state()

    async def _handle_location(self, p: dict):
        aid, sid, ts = p["asset_id"], p["sensor_id"], p["timestamp"]
        self._watchdog.on_message_received(sid)
        asset = self._store.update_asset_location(aid, sid, ts)
        self._safe_db(lambda: self._ensure_sensor_row(sid, asset.current_zone_id))
        self._safe_db(lambda: self._ensure_asset_row(aid, asset.asset_type, asset.name))
        if asset.has_changed_sensor():
            self._safe_db(lambda: save_location_event(asset))
        violation = check_access(asset)
        if violation:
            self._safe_db(lambda: save_event(violation))
            await self._ws.push_alert(violation)
        await self._ws.push_asset_update({
            "id":aid,"asset_type":asset.asset_type,
            "name":getattr(asset, "name", None) or aid,
            "current_sensor_id":asset.current_sensor_id,"current_zone_id":asset.current_zone_id,
            "previous_sensor_id":asset.previous_sensor_id,"previous_zone_id":asset.previous_zone_id,
            "time_change_location":asset.time_change_location.isoformat() if asset.time_change_location else None,
            "access_status":asset.access_status,
        })
        await self._push_system_state()

    # ── Persistence helpers ──────────────────────────────────────────────────

    def _safe_db(self, fn):
        """
        Run a DB write, swallowing and logging any error.

        PostgreSQL aborts an entire transaction after one failed statement, so
        a single bad write would otherwise cascade and silently break the whole
        ingestion pipeline. On failure we roll back so the next write can
        succeed, and the live WebSocket feed continues either way.
        """
        try:
            fn()
        except Exception as e:
            try:
                from persistence.postgres import get_conn
                get_conn().rollback()
            except Exception:
                pass
            if not hasattr(self, "_db_err_count"):
                self._db_err_count = 0
            self._db_err_count += 1
            if self._db_err_count <= 5 or self._db_err_count % 100 == 0:
                logger.warning(f"DB write failed (#{self._db_err_count}): {e}")

    def _ensure_sensor_row(self, sensor_id: str, zone_id=None):
        """Insert a sensor discovered on MQTT but absent from the DB."""
        if sensor_id in self._known_sensors:
            return
        from persistence.postgres import get_conn
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO sensors (sensor_id, zone_id, grid_row, grid_col)
                VALUES (%s, %s, NULL, NULL)
                ON CONFLICT (sensor_id) DO NOTHING
            """, (sensor_id, zone_id))
        conn.commit()
        self._known_sensors.add(sensor_id)

    def _ensure_asset_row(self, asset_id: str, asset_type: str, name=None):
        """Insert an asset discovered on MQTT but absent from the DB."""
        if asset_id in self._known_assets:
            return
        from persistence.postgres import get_conn
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO assets (asset_id, asset_type, name) VALUES (%s,%s,%s)
                ON CONFLICT (asset_id) DO NOTHING
            """, (asset_id, asset_type or "worker", name or asset_id))
        conn.commit()
        self._known_assets.add(asset_id)

    def _on_alert(self, alert: dict):
        self._safe_db(lambda: save_event(alert))
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._ws.push_alert(alert), self._loop)
            asyncio.run_coroutine_threadsafe(self._ws.push_health_update(alert), self._loop)

    async def _push_system_state(self):
        state = compute_system_state(self._store.all_assets(),
                                     self._store.all_sensors(),
                                     self._store.all_health())
        self._safe_db(lambda: save_system_snapshot(state))
        await self._ws.push_system_state(state.to_dict())

    def get_snapshot(self) -> dict:
        if not self._store: return {}
        state = compute_system_state(self._store.all_assets(), self._store.all_sensors(), self._store.all_health())
        def _asset(a): return {"id":a.id,"asset_type":a.asset_type,
            "name":getattr(a, "name", None) or a.id,
            "current_sensor_id":a.current_sensor_id,
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

    def _load_fire_model(self):
        """Load the fire detector, sized to the configured grid."""
        try:
            from ai.models.fire_detector import FireDetectorInference
            from persistence.postgres import get_conn
            import psycopg2.extras
            conn = get_conn()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT key, value FROM factory_config")
                cfg = {r["key"]: r["value"] for r in cur.fetchall()}
                cur.execute("""SELECT s.sensor_id,
                                      COALESCE(sc.coverage_type,'passage') AS ct
                               FROM sensors s
                               LEFT JOIN sensor_config sc USING (sensor_id)""")
                coverage = {r["sensor_id"]: r["ct"] for r in cur.fetchall()}
            cols = int(cfg.get("grid_cols") or 6)
            rows = int(cfg.get("grid_rows") or 5)
            self._fire_model = FireDetectorInference(
                model_path="models/fire_convlstm.pt",
                cols=cols, rows=rows, coverage=coverage)
            logger.info(f"Fire detector ready ({cols}x{rows}, "
                        f"{'trained model' if self._fire_model.model else 'rule-based'})")
        except Exception as e:
            logger.info(f"Fire detector unavailable: {e}")
            self._fire_model = None

    def reload_thresholds(self):
        """Re-resolve every sensor's thresholds after a configuration change."""
        threshold_resolver.reload()
        logger.info("Thresholds reloaded.")

    def reload_authorisations(self):
        """
        Re-read asset authorisations from the database.

        A zone authorisation implicitly covers every sensor in that zone, so
        changing a zone's sensor membership also changes who may stand where.
        """
        try:
            from persistence.postgres import load_authorisations
            for aid, (sensors, zones) in load_authorisations().items():
                self._store.set_asset_authorisations(aid, sensors, zones)
            logger.info("Authorisations reloaded.")
        except Exception as e:
            logger.warning(f"Authorisation reload failed: {e}")

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

        # ④ Fire detector — always loaded; falls back to rules when untrained
        self._load_fire_model()
