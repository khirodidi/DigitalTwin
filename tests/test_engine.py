# =============================================================================
# tests/test_engine.py
# Unit tests for the Digital Twin engine core:
#   - MQTT parser
#   - State store (asset + sensor updates, zone resolution)
#   - Rule engine (access control, scenarios, prediction)
#   - Watchdog (status transitions)
#   - System state aggregator
# Run with: pytest tests/test_engine.py -v
# =============================================================================

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from models.state import (
    ZoneRegistry, AssetState, SensorState, SensorHealthState,
    SensorStatus, EnvStatus, AccessStatus, SystemStatus,
)
from engine.state_store  import StateStore
from engine.rules        import check_access, evaluate_scenarios, predict_critical_states
from engine.watchdog     import SensorWatchdog, DEGRADED_THRESHOLD, OFFLINE_THRESHOLD
from engine.system_state import compute_system_state
from ingestion.mqtt_parser import parse_env_message, parse_location_message, route_message


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def registry():
    return ZoneRegistry({
        "S01": "zone_A", "S02": "zone_A",
        "S05": "zone_B", "S06": "zone_B",
        "S09": "zone_C",
    })

@pytest.fixture
def store(registry):
    return StateStore(registry)

@pytest.fixture
def now():
    return datetime.utcnow()


# ─── MQTT Parser ──────────────────────────────────────────────────────────────

class TestMqttParser:

    def test_parse_env_temperature(self):
        raw = ["S01", "temperature", 45.2, "2026-05-17T10:00:00"]
        p   = parse_env_message(raw)
        assert p["sensor_id"]    == "S01"
        assert p["reading_type"] == "temperature"
        assert p["value"]        == 45.2
        assert isinstance(p["timestamp"], datetime)

    def test_parse_env_smoke_bool(self):
        raw = ["S01", "smoke", True, "2026-05-17T10:00:00"]
        p   = parse_env_message(raw)
        assert p["value"] is True

    def test_parse_env_smoke_numeric(self):
        raw = ["S01", "smoke", 1, "2026-05-17T10:00:00"]
        p   = parse_env_message(raw)
        assert p["value"] is True

    def test_parse_env_invalid_type(self):
        with pytest.raises(ValueError, match="Unknown reading_type"):
            parse_env_message(["S01", "pressure", 1013, "2026-05-17T10:00:00"])

    def test_parse_env_wrong_length(self):
        with pytest.raises(ValueError, match="Invalid env message"):
            parse_env_message(["S01", "temperature", 45.2])

    def test_parse_location(self):
        raw = ["W01", "S05", "2026-05-17T10:00:00"]
        p   = parse_location_message(raw)
        assert p["asset_id"]  == "W01"
        assert p["sensor_id"] == "S05"
        assert isinstance(p["timestamp"], datetime)

    def test_route_env(self):
        msg_type, parsed = route_message(
            "wsn/env",
            ["S01", "humidity", 60.0, "2026-05-17T10:00:00"]
        )
        assert msg_type == "env"
        assert parsed["reading_type"] == "humidity"

    def test_route_location(self):
        msg_type, parsed = route_message(
            "wsn/location",
            ["F01", "S09", "2026-05-17T10:00:00"]
        )
        assert msg_type == "location"
        assert parsed["asset_id"] == "F01"

    def test_route_unknown_topic(self):
        with pytest.raises(ValueError, match="Unknown MQTT topic"):
            route_message("wsn/unknown", [])


# ─── Zone Registry ────────────────────────────────────────────────────────────

class TestZoneRegistry:

    def test_sensor_to_zone(self, registry):
        assert registry.get_zone("S01") == "zone_A"
        assert registry.get_zone("S09") == "zone_C"

    def test_unknown_sensor(self, registry):
        assert registry.get_zone("S99") is None

    def test_zone_to_sensors(self, registry):
        sensors = registry.get_sensors("zone_A")
        assert "S01" in sensors
        assert "S02" in sensors

    def test_all_zones(self, registry):
        zones = registry.all_zones()
        assert "zone_A" in zones
        assert "zone_C" in zones

    def test_all_sensors(self, registry):
        sensors = registry.all_sensors()
        assert len(sensors) == 5


# ─── State Store ──────────────────────────────────────────────────────────────

class TestStateStore:

    def test_sensor_update_resolves_zone(self, store, now):
        sensor = store.update_sensor_reading("S01", "temperature", 30.0, now)
        assert sensor.sensor_id == "S01"
        assert sensor.zone_id   == "zone_A"
        assert sensor.temperature == 30.0
        assert sensor.env_status  == EnvStatus.NORMAL

    def test_sensor_update_carries_forward(self, store, now):
        store.update_sensor_reading("S01", "temperature", 30.0, now)
        store.update_sensor_reading("S01", "humidity",    65.0, now)
        sensor = store.get_sensor("S01")
        assert sensor.temperature == 30.0   # carried forward
        assert sensor.humidity    == 65.0

    def test_sensor_smoke_critical(self, store, now):
        store.update_sensor_reading("S01", "temperature", 25.0, now)
        store.update_sensor_reading("S01", "smoke", True, now)
        sensor = store.get_sensor("S01")
        assert sensor.smoke      is True
        assert sensor.env_status == EnvStatus.CRITICAL

    def test_sensor_high_temp_critical(self, store, now):
        sensor = store.update_sensor_reading("S01", "temperature", 65.0, now)
        assert sensor.env_status == EnvStatus.CRITICAL

    def test_sensor_high_temp_warning(self, store, now):
        sensor = store.update_sensor_reading("S01", "temperature", 55.0, now)
        assert sensor.env_status == EnvStatus.WARNING

    def test_asset_location_update(self, store, now):
        asset = store.update_asset_location("W01", "S01", now)
        assert asset.id               == "W01"
        assert asset.current_sensor_id == "S01"
        assert asset.current_zone_id   == "zone_A"
        assert asset.previous_sensor_id is None

    def test_asset_zone_change_tracked(self, store, now):
        store.update_asset_location("W01", "S01", now)
        later = now + timedelta(minutes=5)
        asset = store.update_asset_location("W01", "S05", later)
        assert asset.current_zone_id  == "zone_B"
        assert asset.previous_zone_id == "zone_A"
        assert asset.has_changed_zone() is True

    def test_asset_same_zone_no_time_update(self, store, now):
        store.update_asset_location("W01", "S01", now)
        later = now + timedelta(minutes=5)
        asset = store.update_asset_location("W01", "S02", later)
        # Different sensor, same zone — time_change_location is from first entry
        assert asset.current_zone_id == "zone_A"
        assert asset.has_changed_zone() is False

    def test_assets_in_zone(self, store, now):
        store.update_asset_location("W01", "S01", now)
        store.update_asset_location("W02", "S02", now)
        store.update_asset_location("F01", "S05", now)
        assets = store.assets_in_zone("zone_A")
        ids = [a.id for a in assets]
        assert "W01" in ids
        assert "W02" in ids
        assert "F01" not in ids

    def test_assets_in_sensor(self, store, now):
        store.update_asset_location("W01", "S01", now)
        store.update_asset_location("W02", "S01", now)
        assets = store.assets_in_sensor("S01")
        assert len(assets) == 2

    def test_authorisation_carried_forward(self, store, now):
        store.set_asset_authorisations("W01", {"S01", "S02"}, {"zone_A"})
        store.update_asset_location("W01", "S01", now)
        asset = store.get_asset("W01")
        assert "S01" in asset.allowed_sensors
        assert "zone_A" in asset.allowed_zones

    def test_all_sensors_in_health(self, store):
        # All sensors from registry should have a health entry on init
        health = {h.sensor_id for h in store.all_health()}
        assert "S01" in health
        assert "S09" in health
        # All start OFFLINE (no heartbeat yet)
        for h in store.all_health():
            assert h.status == SensorStatus.OFFLINE


# ─── Access Control ───────────────────────────────────────────────────────────

class TestAccessControl:

    def _make_asset(self, sensor_id, zone_id, prev_sensor=None, prev_zone=None,
                    allowed_sensors=None, allowed_zones=None,
                    status=AccessStatus.AUTHORISED):
        return AssetState(
            id                   = "W01",
            asset_type           = "worker",
            current_sensor_id    = sensor_id,
            current_zone_id      = zone_id,
            previous_sensor_id   = prev_sensor,
            previous_zone_id     = prev_zone,
            time_change_location = datetime.utcnow(),
            allowed_sensors      = set(allowed_sensors or []),
            allowed_zones        = set(allowed_zones  or []),
            access_status        = status,
        )

    def test_no_violation_on_authorised(self):
        asset  = self._make_asset("S01", "zone_A",
                                  allowed_zones=["zone_A"],
                                  status=AccessStatus.AUTHORISED)
        result = check_access(asset)
        assert result is None

    def test_violation_fires_on_zone_change(self):
        asset = self._make_asset(
            "S05", "zone_B",
            prev_sensor="S01", prev_zone="zone_A",
            allowed_zones=["zone_A"],
            status=AccessStatus.VIOLATION,
        )
        result = check_access(asset)
        assert result is not None
        assert result["type"]  == "access_violation"
        assert result["level"] == "critical"

    def test_no_violation_when_sensor_authorised(self):
        asset = self._make_asset(
            "S05", "zone_B",
            prev_sensor="S01", prev_zone="zone_A",
            allowed_sensors=["S05"],
            status=AccessStatus.AUTHORISED,
        )
        assert check_access(asset) is None

    def test_unknown_status_no_alert(self):
        asset = self._make_asset("S05", "zone_B", status=AccessStatus.UNKNOWN)
        assert check_access(asset) is None


# ─── Scenario Rules ───────────────────────────────────────────────────────────

class TestScenarios:

    def _make_sensor(self, smoke=False, temp=25.0, humidity=50.0,
                     env_status=EnvStatus.NORMAL):
        return SensorState(
            sensor_id        = "S01",
            zone_id          = "zone_A",
            temperature      = temp,
            humidity         = humidity,
            smoke            = smoke,
            env_status       = env_status,
            last_time_change = datetime.utcnow(),
        )

    def test_smoke_triggers_critical(self):
        sensor = self._make_sensor(smoke=True, env_status=EnvStatus.CRITICAL)
        events = evaluate_scenarios(sensor, [])
        types  = [e["type"] for e in events]
        assert "smoke_detected" in types
        assert all(e["level"] == "critical" for e in events if e["type"] == "smoke_detected")

    def test_high_temperature_critical(self):
        sensor = self._make_sensor(temp=65.0, env_status=EnvStatus.CRITICAL)
        events = evaluate_scenarios(sensor, [])
        types  = [e["type"] for e in events]
        assert "high_temperature" in types

    def test_temperature_warning(self):
        sensor = self._make_sensor(temp=55.0, env_status=EnvStatus.WARNING)
        events = evaluate_scenarios(sensor, [])
        types  = [e["type"] for e in events]
        assert "temperature_warning" in types

    def test_workers_in_smoke_zone(self):
        sensor = self._make_sensor(smoke=True, env_status=EnvStatus.CRITICAL)
        asset  = MagicMock()
        events = evaluate_scenarios(sensor, [asset])
        types  = [e["type"] for e in events]
        assert "workers_in_danger" in types

    def test_normal_no_alerts(self):
        sensor = self._make_sensor(temp=22.0, env_status=EnvStatus.NORMAL)
        events = evaluate_scenarios(sensor, [])
        assert events == []


# ─── Prediction ───────────────────────────────────────────────────────────────

class TestPrediction:

    def _make_sensor_history(self, temps, smoke_vals=None):
        history = []
        for i, t in enumerate(temps):
            history.append(SensorState(
                sensor_id        = "S01",
                zone_id          = "zone_A",
                temperature      = t,
                humidity         = 50.0,
                smoke            = (smoke_vals[i] if smoke_vals else False),
                env_status       = EnvStatus.NORMAL,
                last_time_change = datetime.utcnow(),
            ))
        return history

    def test_rising_temperature_predicts_critical(self):
        temps   = [30, 33, 36, 40, 45, 51]
        history = self._make_sensor_history(temps)
        sensor  = history[-1]
        preds   = predict_critical_states(sensor, history)
        types   = [p["type"] for p in preds]
        assert "predicted_critical_temperature" in types

    def test_stable_temperature_no_prediction(self):
        temps   = [25, 25, 26, 25, 25, 25]
        history = self._make_sensor_history(temps)
        sensor  = history[-1]
        preds   = predict_critical_states(sensor, history)
        assert not any(p["type"] == "predicted_critical_temperature" for p in preds)

    def test_intermittent_smoke_detected(self):
        smoke   = [True, False, True, False, False]
        history = self._make_sensor_history([25]*5, smoke_vals=smoke)
        sensor  = SensorState(
            sensor_id="S01", zone_id="zone_A",
            temperature=25.0, humidity=50.0, smoke=False,
            env_status=EnvStatus.NORMAL, last_time_change=datetime.utcnow(),
        )
        preds = predict_critical_states(sensor, history)
        types = [p["type"] for p in preds]
        assert "intermittent_smoke" in types

    def test_too_short_history_no_prediction(self):
        history = self._make_sensor_history([30, 40])
        sensor  = history[-1]
        preds   = predict_critical_states(sensor, history)
        assert preds == []


# ─── Watchdog ─────────────────────────────────────────────────────────────────

class TestWatchdog:

    def _make_health(self, sensor_id="S01", zone_id="zone_A"):
        return {
            sensor_id: SensorHealthState(
                sensor_id            = sensor_id,
                zone_id              = zone_id,
                status               = SensorStatus.ONLINE,
                last_heartbeat       = datetime.utcnow(),
                last_reading         = datetime.utcnow(),
                consecutive_failures = 0,
            )
        }

    def test_heartbeat_resets_failures(self):
        health   = self._make_health()
        health["S01"].consecutive_failures = 3
        health["S01"].status = SensorStatus.DEGRADED
        alerts   = []
        watchdog = SensorWatchdog(health, lambda a: alerts.append(a))
        watchdog.on_message_received("S01")
        assert health["S01"].consecutive_failures == 0
        assert health["S01"].status == SensorStatus.ONLINE

    def test_recovery_fires_alert(self):
        health   = self._make_health()
        health["S01"].status = SensorStatus.OFFLINE
        alerts   = []
        watchdog = SensorWatchdog(health, lambda a: alerts.append(a))
        watchdog.on_message_received("S01")
        assert any(a["type"] == "sensor_recovered" for a in alerts)

    def test_unknown_sensor_ignored(self):
        health   = self._make_health()
        alerts   = []
        watchdog = SensorWatchdog(health, lambda a: alerts.append(a))
        watchdog.on_message_received("S99")   # not in health store
        assert alerts == []

    def test_status_transition_degraded(self):
        health = self._make_health()
        health["S01"].last_heartbeat       = datetime.utcnow() - timedelta(seconds=999)
        health["S01"].consecutive_failures = DEGRADED_THRESHOLD
        alerts   = []
        watchdog = SensorWatchdog(health, lambda a: alerts.append(a))
        watchdog._maybe_transition(health["S01"], datetime.utcnow())
        assert health["S01"].status == SensorStatus.DEGRADED
        assert any(a["type"] == "sensor_status_change" for a in alerts)

    def test_status_transition_offline(self):
        health = self._make_health()
        health["S01"].consecutive_failures = OFFLINE_THRESHOLD
        alerts   = []
        watchdog = SensorWatchdog(health, lambda a: alerts.append(a))
        watchdog._maybe_transition(health["S01"], datetime.utcnow())
        assert health["S01"].status == SensorStatus.OFFLINE
        critical = [a for a in alerts if a.get("level") == "critical"]
        assert len(critical) > 0


# ─── System State Aggregator ──────────────────────────────────────────────────

class TestSystemState:

    def _make_health(self, n_online=3, n_degraded=1, n_offline=1):
        health = []
        for i in range(n_online):
            health.append(SensorHealthState(
                sensor_id=f"S0{i}", zone_id="zone_A",
                status=SensorStatus.ONLINE,
                last_heartbeat=datetime.utcnow(), last_reading=datetime.utcnow(),
            ))
        for i in range(n_degraded):
            health.append(SensorHealthState(
                sensor_id=f"SD{i}", zone_id="zone_A",
                status=SensorStatus.DEGRADED,
                last_heartbeat=datetime.utcnow(), last_reading=datetime.utcnow(),
            ))
        for i in range(n_offline):
            health.append(SensorHealthState(
                sensor_id=f"SO{i}", zone_id="zone_A",
                status=SensorStatus.OFFLINE,
                last_heartbeat=None, last_reading=None,
            ))
        return health

    def _make_sensor(self, sensor_id, env_status):
        return SensorState(
            sensor_id=sensor_id, zone_id="zone_A",
            temperature=25.0, humidity=50.0, smoke=False,
            env_status=env_status,
            last_time_change=datetime.utcnow(),
        )

    def _make_asset(self, access_status):
        return AssetState(
            id="W01", asset_type="worker",
            current_sensor_id="S01", current_zone_id="zone_A",
            previous_sensor_id=None, previous_zone_id=None,
            time_change_location=datetime.utcnow(),
            access_status=access_status,
        )

    def test_nominal_state(self):
        state = compute_system_state(
            assets  = [self._make_asset(AccessStatus.AUTHORISED)],
            sensors = [self._make_sensor("S01", EnvStatus.NORMAL)],
            health  = self._make_health(n_online=3, n_degraded=0, n_offline=0),
        )
        assert state.overall_status == SystemStatus.NOMINAL

    def test_critical_on_offline_sensor(self):
        state = compute_system_state(
            assets  = [],
            sensors = [],
            health  = self._make_health(n_online=2, n_degraded=0, n_offline=1),
        )
        assert state.overall_status == SystemStatus.CRITICAL
        assert state.sensors_offline == 1

    def test_critical_on_env_critical(self):
        state = compute_system_state(
            assets  = [],
            sensors = [self._make_sensor("S01", EnvStatus.CRITICAL)],
            health  = self._make_health(n_online=3, n_degraded=0, n_offline=0),
        )
        assert state.overall_status == SystemStatus.CRITICAL

    def test_critical_on_violation(self):
        state = compute_system_state(
            assets  = [self._make_asset(AccessStatus.VIOLATION)],
            sensors = [self._make_sensor("S01", EnvStatus.NORMAL)],
            health  = self._make_health(n_online=3, n_degraded=0, n_offline=0),
        )
        assert state.overall_status == SystemStatus.CRITICAL
        assert state.access_violations == 1

    def test_degraded_on_warning(self):
        state = compute_system_state(
            assets  = [],
            sensors = [self._make_sensor("S01", EnvStatus.WARNING)],
            health  = self._make_health(n_online=3, n_degraded=0, n_offline=0),
        )
        assert state.overall_status == SystemStatus.DEGRADED

    def test_degraded_on_degraded_sensor(self):
        state = compute_system_state(
            assets  = [],
            sensors = [],
            health  = self._make_health(n_online=3, n_degraded=1, n_offline=0),
        )
        assert state.overall_status == SystemStatus.DEGRADED

    def test_counts_correct(self):
        state = compute_system_state(
            assets  = [
                self._make_asset(AccessStatus.AUTHORISED),
                self._make_asset(AccessStatus.VIOLATION),
                self._make_asset(AccessStatus.UNKNOWN),
            ],
            sensors = [
                self._make_sensor("S01", EnvStatus.NORMAL),
                self._make_sensor("S02", EnvStatus.WARNING),
                self._make_sensor("S03", EnvStatus.CRITICAL),
            ],
            health  = self._make_health(n_online=2, n_degraded=1, n_offline=2),
        )
        assert state.sensors_online   == 2
        assert state.sensors_degraded == 1
        assert state.sensors_offline  == 2
        assert state.access_violations == 1
        assert state.unknown_locations == 1

    def test_to_dict_serialisable(self):
        state = compute_system_state([], [], self._make_health())
        d = state.to_dict()
        assert "overall_status" in d
        assert "sensors"        in d
        assert "environment"    in d
        assert "access"         in d
        import json
        json.dumps(d)   # must not raise
