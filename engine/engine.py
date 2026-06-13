# =============================================================================
# engine/engine.py
# Digital Twin — Factory Monitoring System
# Main entry point. Connects to MQTT broker, routes messages, drives
# the state store, rule engine, watchdog, and publisher.
# =============================================================================

import asyncio
import json
import logging
import signal

import paho.mqtt.client as mqtt

from models.state import ZoneRegistry
from engine.state_store   import StateStore
from engine.rules         import check_access, evaluate_scenarios, predict_critical_states
from engine.watchdog      import SensorWatchdog
from engine.system_state  import compute_system_state
from ingestion.mqtt_parser import route_message
from persistence.postgres  import (
    load_zone_registry, load_authorisations,
    save_location_event, save_env_reading,
    save_sensor_health_event, save_event,
    save_system_snapshot, load_sensor_history,
    create_schema,
)
from publisher import Publisher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────

MQTT_HOST   = "localhost"
MQTT_PORT   = 1883
MQTT_TOPICS = [
    ("wsn/env",      1),    # environmental readings
    ("wsn/location", 1),    # asset localisation
]

# Sensor reading history for prediction (sensor_id → list[SensorState])
_sensor_history: dict[str, list] = {}
HISTORY_LIMIT = 20


# ─── Core handlers ────────────────────────────────────────────────────────────

def handle_env(parsed: dict, store: StateStore,
               publisher: Publisher, watchdog: SensorWatchdog):
    sensor_id    = parsed["sensor_id"]
    reading_type = parsed["reading_type"]
    value        = parsed["value"]
    timestamp    = parsed["timestamp"]

    # Register heartbeat
    watchdog.on_message_received(sensor_id)

    # Update sensor state
    sensor = store.update_sensor_reading(sensor_id, reading_type, value, timestamp)

    # Persist raw reading
    save_env_reading(sensor, reading_type, value)

    # Maintain rolling history for prediction
    hist = _sensor_history.setdefault(sensor_id, [])
    hist.append(sensor)
    if len(hist) > HISTORY_LIMIT:
        hist.pop(0)

    # Assets currently in this sensor's zone
    assets_in_zone = store.assets_in_zone(sensor.zone_id or "")

    # 1. If-else scenarios
    scenario_events = evaluate_scenarios(sensor, assets_in_zone)

    # 2. Predictions
    prediction_events = predict_critical_states(sensor, hist)

    # Publish and persist all triggered events
    for event in scenario_events + prediction_events:
        save_event(event)
        publisher.push_alert(event)

    # Push sensor update to frontend
    publisher.push_sensor_update(sensor)

    # Recompute and push global system state
    _push_system_state(store, publisher)


def handle_location(parsed: dict, store: StateStore,
                    publisher: Publisher, watchdog: SensorWatchdog):
    asset_id  = parsed["asset_id"]
    sensor_id = parsed["sensor_id"]
    timestamp = parsed["timestamp"]

    # Register heartbeat for the sensor the asset connected to
    watchdog.on_message_received(sensor_id)

    # Update asset state
    asset = store.update_asset_location(asset_id, sensor_id, timestamp)

    # Persist location event (only on zone/sensor change)
    if asset.has_changed_sensor():
        save_location_event(asset)

    # 3. Access authorisation check
    violation = check_access(asset)
    if violation:
        save_event(violation)
        publisher.push_alert(violation)

    # Push asset update to frontend
    publisher.push_asset_update(asset)

    # Recompute and push global system state
    _push_system_state(store, publisher)


def _push_system_state(store: StateStore, publisher: Publisher):
    system_state = compute_system_state(
        store.all_assets(),
        store.all_sensors(),
        store.all_health(),
    )
    save_system_snapshot(system_state)
    publisher.push_system_state(system_state)


# ─── Alert callback (for watchdog) ────────────────────────────────────────────

def make_alert_callback(publisher: Publisher):
    def callback(alert: dict):
        save_event(alert)
        publisher.push_alert(alert)
        # Also push updated health to frontend
        publisher.push("health_update", alert)
    return callback


# ─── MQTT setup ───────────────────────────────────────────────────────────────

def build_mqtt_client(store: StateStore, publisher: Publisher,
                       watchdog: SensorWatchdog) -> mqtt.Client:

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            logger.info("Connected to MQTT broker")
            for topic, qos in MQTT_TOPICS:
                client.subscribe(topic, qos)
                logger.info(f"Subscribed to {topic}")
        else:
            logger.error(f"MQTT connection failed: rc={rc}")

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            msg_type, parsed = route_message(msg.topic, payload)

            if msg_type == "env":
                handle_env(parsed, store, publisher, watchdog)
            elif msg_type == "location":
                handle_location(parsed, store, publisher, watchdog)

        except Exception as e:
            logger.error(f"Error processing message on {msg.topic}: {e}", exc_info=True)

    def on_disconnect(client, userdata, rc):
        logger.warning(f"Disconnected from MQTT broker (rc={rc}). Reconnecting...")

    client = mqtt.Client()
    client.on_connect    = on_connect
    client.on_message    = on_message
    client.on_disconnect = on_disconnect
    return client


# ─── Entry point ──────────────────────────────────────────────────────────────

async def main():
    # 1. Ensure schema exists
    create_schema("postgresql://localhost/digital_twin")

    # 2. Load static configuration from DB
    registry       = load_zone_registry()
    authorisations = load_authorisations()

    # 3. Initialise state store
    store = StateStore(registry)
    for asset_id, (allowed_sensors, allowed_zones) in authorisations.items():
        store.set_asset_authorisations(asset_id, allowed_sensors, allowed_zones)

    # 4. Initialise publisher
    publisher = Publisher()

    # 5. Initialise watchdog
    watchdog = SensorWatchdog(
        health_store   = store.health,
        alert_callback = make_alert_callback(publisher),
    )

    # 6. Connect MQTT
    mqtt_client = build_mqtt_client(store, publisher, watchdog)
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    mqtt_client.loop_start()

    # 7. Run watchdog as background coroutine
    logger.info("Digital twin engine started.")
    try:
        await watchdog.run()
    except asyncio.CancelledError:
        logger.info("Engine shutting down.")
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
