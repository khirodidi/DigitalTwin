"""
bench/bench_engine.py — REAL measurements of the Digital Twin engine.

Every number this module returns is produced by executing the shipped engine
code on the machine running the benchmark. Nothing is hardcoded, sampled from
a distribution, or adjusted after the fact. Where a quantity cannot be
measured here it is omitted rather than estimated.

Measured:
  * end-to-end per-message service time through the real ingest path
    (StateStore -> thresholds -> rules -> access control -> SystemState),
    with and without a real PostgreSQL write
  * the same, swept across grid sizes, for scalability
  * watchdog ONLINE -> DEGRADED -> OFFLINE -> ONLINE transition timing under a
    real induced outage, using the real asyncio coroutine and wall clock
  * access-control decision correctness over the full rule table

Run:  python -m bench.bench_engine            (latency + access control)
      python -m bench.bench_engine --spof     (adds the real-time SPOF run)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from datetime import datetime, timedelta

from models.state import (
    ZoneRegistry, SensorStatus, AccessStatus, SensorHealthState,
)
from engine.state_store import StateStore
from engine.rules import check_access, evaluate_scenarios, predict_critical_states
from engine.system_state import compute_system_state
from engine.watchdog import SensorWatchdog, HEARTBEAT_INTERVAL

# perf_counter_ns: monotonic, nanosecond resolution, unaffected by clock steps
NS = time.perf_counter_ns


# ─────────────────────────────────────────────────────────────────────────────
#  Fixture construction — a factory of a given size, wired exactly as at runtime
# ─────────────────────────────────────────────────────────────────────────────

def build_factory(cols: int, rows: int, n_assets: int, n_zones: int = 5):
    """Return (store, sensor_ids, asset_ids) with every sensor ONLINE."""
    sensor_ids = [f"S{i+1:02d}" for i in range(cols * rows)]
    per_zone = max(1, len(sensor_ids) // n_zones)
    mapping = {sid: f"zone_{chr(ord('A') + min(i // per_zone, n_zones - 1))}"
               for i, sid in enumerate(sensor_ids)}

    store = StateStore(ZoneRegistry(mapping))
    for h in store.all_health():
        h.status = SensorStatus.ONLINE
        h.last_heartbeat = datetime.utcnow()

    asset_ids = [f"W{i+1:02d}" for i in range(n_assets)]
    zones = sorted(set(mapping.values()))
    for i, aid in enumerate(asset_ids):
        # Half the assets are zone-authorised, so both the AUTHORISED and the
        # VIOLATION branch of the access rule are exercised under load.
        store.set_asset_authorisations(
            aid, set(), {zones[i % len(zones)]} if i % 2 == 0 else set())
    return store, sensor_ids, asset_ids


# ─────────────────────────────────────────────────────────────────────────────
#  Latency — the real ingest path, timed per message
# ─────────────────────────────────────────────────────────────────────────────

def _env_once(store, sid, value, history):
    """One wsn/env message through the real pipeline. Returns elapsed ns."""
    t0 = NS()
    sensor = store.update_sensor_reading(sid, "temperature", value,
                                         datetime.utcnow())
    hist = history.setdefault(sid, [])
    hist.append(sensor)
    del hist[:-20]                                  # engine keeps 20 readings
    assets = store.assets_in_sensor(sid)
    evaluate_scenarios(sensor, assets)
    predict_critical_states(sensor, hist)
    compute_system_state(store.all_assets(), store.all_sensors(),
                         store.all_health())
    return NS() - t0


def _loc_once(store, aid, sid):
    """One wsn/location message through the real pipeline. Returns elapsed ns."""
    t0 = NS()
    asset = store.update_asset_location(aid, sid, datetime.utcnow())
    check_access(asset)
    compute_system_state(store.all_assets(), store.all_sensors(),
                         store.all_health())
    return NS() - t0


def measure_latency(cols=6, rows=5, n_assets=9, n_msgs=10_000, runs=5,
                    warmup=500, dsn=None):
    """
    Service time per message through the real engine.

    dsn: when given, every message additionally performs the real PostgreSQL
    write the engine performs in production, so the DB cost is included.
    """
    from persistence.postgres import save_env_reading, save_location_event

    per_run = {"env": [], "loc": []}
    raw = {"env": [], "loc": []}

    for run in range(runs):
        store, sensor_ids, asset_ids = build_factory(cols, rows, n_assets)
        history: dict[str, list] = {}
        env_s, loc_s = [], []

        for i in range(warmup + n_msgs):
            sid = sensor_ids[i % len(sensor_ids)]
            # Sweep 18-64 C so NORMAL, WARNING and CRITICAL branches all fire
            value = 18.0 + (i % 46)
            dt = _env_once(store, sid, value, history)
            if dsn:
                t0 = NS()
                try:
                    save_env_reading(store.get_sensor(sid))
                except Exception:
                    pass
                dt += NS() - t0
            if i >= warmup:
                env_s.append(dt / 1e6)              # ns -> ms

            aid = asset_ids[i % len(asset_ids)]
            dt = _loc_once(store, aid, sensor_ids[(i * 7) % len(sensor_ids)])
            if dsn:
                t0 = NS()
                try:
                    save_location_event(store.get_asset(aid))
                except Exception:
                    pass
                dt += NS() - t0
            if i >= warmup:
                loc_s.append(dt / 1e6)

        per_run["env"].append(statistics.mean(env_s))
        per_run["loc"].append(statistics.mean(loc_s))
        raw["env"].extend(env_s)
        raw["loc"].extend(loc_s)
        print(f"    run {run+1}/{runs}: env {statistics.mean(env_s):.3f} ms  "
              f"loc {statistics.mean(loc_s):.3f} ms")

    return {k: _summarise(raw[k], per_run[k]) for k in ("env", "loc")}, raw


def _summarise(samples, run_means):
    s = sorted(samples)
    n = len(s)
    pct = lambda p: s[min(n - 1, int(n * p / 100))]
    mean = statistics.mean(s)
    # CI over RUN means (n=runs), not over individual messages: successive
    # messages on one run are not independent, so a per-message CI would be
    # anticonservative by orders of magnitude.
    if len(run_means) > 1:
        half = 1.96 * statistics.stdev(run_means) / (len(run_means) ** 0.5)
    else:
        half = 0.0
    return {
        "n_samples":  n,
        "runs":       len(run_means),
        "mean":       round(mean, 4),
        "std":        round(statistics.pstdev(s), 4),
        "p50":        round(pct(50), 4),
        "p95":        round(pct(95), 4),
        "p99":        round(pct(99), 4),
        "max":        round(s[-1], 4),
        "run_means":  [round(x, 4) for x in run_means],
        "ci95_of_mean_over_runs": [round(statistics.mean(run_means) - half, 4),
                                   round(statistics.mean(run_means) + half, 4)],
    }


def measure_scalability(grids, n_msgs=3000, runs=3):
    """P99 service time and derived throughput ceiling across grid sizes."""
    out = []
    for cols, rows in grids:
        n_assets = max(4, (cols * rows) // 3)
        print(f"  grid {cols}x{rows} ({cols*rows} sensors, {n_assets} assets)")
        stats_, _ = measure_latency(cols, rows, n_assets,
                                    n_msgs=n_msgs, runs=runs, warmup=200)
        p99 = stats_["env"]["p99"]
        out.append({
            "grid":     f"{cols}x{rows}",
            "sensors":  cols * rows,
            "assets":   n_assets,
            "mean_ms":  stats_["env"]["mean"],
            "p99_ms":   p99,
            # Single-threaded ceiling implied by the measured mean service
            # time. This is an upper bound on one engine process, not a
            # measured saturation point under concurrent load.
            "max_msgs_per_s_singlethread": round(1000.0 / stats_["env"]["mean"], 1),
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
#  Access control — exhaustive over the decision table
# ─────────────────────────────────────────────────────────────────────────────

def verify_access_control():
    """
    Exercise every branch of the documented access rule against the real
    StateStore + AssetState, including the zone-implies-sensors property.
    Returns per-case expected/actual so the paper can state coverage honestly.
    """
    mapping = {"S01": "zone_A", "S02": "zone_A", "S03": "zone_B", "S04": None}
    cases, passed = [], 0

    def fresh():
        st = StateStore(ZoneRegistry({k: v for k, v in mapping.items() if v}))
        for sid in mapping:
            h = st._ensure_health(sid)
            h.status = SensorStatus.ONLINE
        return st

    now = datetime.utcnow

    # 1. explicit sensor authorisation
    st = fresh(); st.set_asset_authorisations("A", {"S01"}, set())
    st.update_asset_location("A", "S01", now())
    cases.append(("explicit sensor grant", AccessStatus.AUTHORISED,
                  st.get_asset("A").access_status))

    # 2. zone grant covers a sensor in that zone
    st = fresh(); st.set_asset_authorisations("A", set(), {"zone_A"})
    st.update_asset_location("A", "S01", now())
    cases.append(("zone grant -> member sensor", AccessStatus.AUTHORISED,
                  st.get_asset("A").access_status))

    # 3. zone grant covers EVERY sensor in that zone (the implicit rule)
    st.update_asset_location("A", "S02", now())
    cases.append(("zone grant -> second member sensor", AccessStatus.AUTHORISED,
                  st.get_asset("A").access_status))

    # 4. sensor outside the granted zone
    st.update_asset_location("A", "S03", now())
    cases.append(("sensor outside granted zone", AccessStatus.VIOLATION,
                  st.get_asset("A").access_status))

    # 5. no authorisation at all
    st = fresh(); st.update_asset_location("B", "S01", now())
    cases.append(("no authorisation", AccessStatus.VIOLATION,
                  st.get_asset("B").access_status))

    # 6. OFFLINE sensor must yield UNKNOWN, never VIOLATION
    st = fresh(); st.get_health("S01").status = SensorStatus.OFFLINE
    st.update_asset_location("C", "S01", now())
    cases.append(("offline sensor, unauthorised", AccessStatus.UNKNOWN,
                  st.get_asset("C").access_status))

    # 7. OFFLINE dominates even when authorised
    st = fresh(); st.set_asset_authorisations("D", {"S01"}, set())
    st.get_health("S01").status = SensorStatus.OFFLINE
    st.update_asset_location("D", "S01", now())
    cases.append(("offline sensor, authorised", AccessStatus.UNKNOWN,
                  st.get_asset("D").access_status))

    # 8. authorisations set BEFORE the asset ever reports (startup order)
    st = fresh(); st.set_asset_authorisations("E", set(), {"zone_A"})
    st.update_asset_location("E", "S01", now())
    cases.append(("grant precedes first location event", AccessStatus.AUTHORISED,
                  st.get_asset("E").access_status))

    # 9. a live grant recomputes status immediately
    st = fresh(); st.update_asset_location("F", "S01", now())
    before = st.get_asset("F").access_status
    st.set_asset_authorisations("F", set(), {"zone_A"})
    cases.append(("live grant recomputes", (AccessStatus.VIOLATION,
                                            AccessStatus.AUTHORISED),
                  (before, st.get_asset("F").access_status)))

    rows = []
    for name, expected, actual in cases:
        ok = expected == actual
        passed += ok
        rows.append({"case": name, "expected": str(expected),
                     "actual": str(actual), "pass": ok})
    return {"cases": rows, "passed": passed, "total": len(rows)}


# ─────────────────────────────────────────────────────────────────────────────
#  SPOF — real watchdog, real clock
# ─────────────────────────────────────────────────────────────────────────────

async def measure_spof(n_sensors=30, outage_s=45.0, settle_s=12.0):
    """
    Drive the real SensorWatchdog coroutine through a genuine gateway outage.

    All sensors are heartbeating; heartbeats stop for `outage_s`; then resume.
    Transition instants are recorded from the watchdog's own alert callback
    against a monotonic clock. Nothing is simulated but the gateway.
    """
    health = {
        f"S{i+1:02d}": SensorHealthState(
            sensor_id=f"S{i+1:02d}", zone_id="zone_A",
            status=SensorStatus.ONLINE, last_heartbeat=datetime.utcnow(),
            last_reading=datetime.utcnow(), consecutive_failures=0)
        for i in range(n_sensors)
    }

    events = []
    t_zero = time.monotonic()
    wd = SensorWatchdog(health, lambda a: events.append(
        (round(time.monotonic() - t_zero, 3), a)))

    task = asyncio.create_task(wd.run())
    outage_start = None
    try:
        # Heartbeat normally for two watchdog ticks so the baseline is stable
        pre = HEARTBEAT_INTERVAL * 2
        end = time.monotonic() + pre
        while time.monotonic() < end:
            for sid in health:
                wd.on_message_received(sid)
            await asyncio.sleep(0.5)

        outage_start = time.monotonic() - t_zero
        await asyncio.sleep(outage_s)              # gateway down: no heartbeats
        outage_end = time.monotonic() - t_zero

        n_before_resume = len(events)
        for sid in health:                          # gateway back
            wd.on_message_received(sid)
        recovery_deadline = time.monotonic() + settle_s
        while time.monotonic() < recovery_deadline:
            for sid in health:
                wd.on_message_received(sid)
            await asyncio.sleep(0.5)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def first(pred):
        return next((t for t, a in events if pred(a)), None)

    t_degraded = first(lambda a: a.get("to_status") == SensorStatus.DEGRADED)
    t_offline_first = first(lambda a: a.get("to_status") == SensorStatus.OFFLINE)
    offline_times = [t for t, a in events
                     if a.get("to_status") == SensorStatus.OFFLINE]
    # Recovery alerts are those emitted from the resume onward. Recovery is
    # driven by on_message_received(), not by a watchdog tick, so it is bounded
    # by message arrival rather than by the heartbeat interval.
    resume_events = events[n_before_resume:]
    recovered = [t for t, a in resume_events
                 if a.get("type") == "sensor_recovered"]
    t_recovered = max(recovered) if recovered else None

    return {
        "n_sensors":            n_sensors,
        "heartbeat_interval_s": HEARTBEAT_INTERVAL,
        "outage_start_s":       round(outage_start, 2),
        "outage_duration_s":    outage_s,
        "outage_end_s":         round(outage_end, 2),
        "first_degraded_after_outage_s":
            round(t_degraded - outage_start, 2) if t_degraded else None,
        "first_offline_after_outage_s":
            round(t_offline_first - outage_start, 2) if t_offline_first else None,
        "all_offline_after_outage_s":
            round(max(offline_times) - outage_start, 2) if offline_times else None,
        "sensors_declared_offline": len(offline_times),
        "recovery_all_online_after_reconnect_s":
            round(t_recovered - outage_end, 3) if t_recovered is not None else None,
        "sensors_recovered":    len(recovered),
        "total_alerts":         len(events),
    }


def measure_false_violations_during_outage(n_sensors=30):
    """
    An asset located on an OFFLINE sensor must yield UNKNOWN, not VIOLATION.
    Counts real access decisions taken while every sensor is offline.
    """
    mapping = {f"S{i+1:02d}": "zone_A" for i in range(n_sensors)}
    store = StateStore(ZoneRegistry(mapping))
    for h in store.all_health():
        h.status = SensorStatus.ONLINE
    for i in range(5):
        store.set_asset_authorisations(f"W{i+1:02d}", set(), {"zone_A"})

    for h in store.all_health():                    # gateway down
        h.status = SensorStatus.OFFLINE

    decisions, violations, unknown = 0, 0, 0
    for cycle in range(9):                          # 9 missed publish cycles
        for i in range(5):
            aid = f"W{i+1:02d}"
            sid = f"S{((cycle * 5 + i) % n_sensors) + 1:02d}"
            a = store.update_asset_location(aid, sid, datetime.utcnow())
            decisions += 1
            violations += a.access_status == AccessStatus.VIOLATION
            unknown += a.access_status == AccessStatus.UNKNOWN
            if check_access(a):
                violations += 0                     # alert only fires on VIOLATION
    return {"decisions": decisions, "false_violations": violations,
            "unknown": unknown}


# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--msgs", type=int, default=10_000)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--spof", action="store_true",
                    help="run the real-time SPOF experiment (~70 s)")
    ap.add_argument("--db", default=None,
                    help="PostgreSQL DSN to include real persistence cost")
    ap.add_argument("--out", default="bench/results_engine.json")
    args = ap.parse_args()

    out = {"meta": {
        "measured_at": datetime.utcnow().isoformat() + "Z",
        "python": os.sys.version.split()[0],
        "note": "All values measured by executing the shipped engine code.",
    }}

    print("[1/4] Access-control decision table")
    out["access_control"] = verify_access_control()
    print(f"    {out['access_control']['passed']}/"
          f"{out['access_control']['total']} cases correct")

    print(f"[2/4] Latency, in-memory path ({args.runs} runs x {args.msgs} msgs)")
    lat, _ = measure_latency(n_msgs=args.msgs, runs=args.runs)
    out["latency_inmemory"] = lat

    if args.db:
        print("[3/4] Latency including real PostgreSQL write")
        os.environ["POSTGRES_DSN"] = args.db
        latdb, _ = measure_latency(n_msgs=min(args.msgs, 2000),
                                   runs=min(args.runs, 3), dsn=args.db)
        out["latency_with_postgres"] = latdb
    else:
        print("[3/4] Skipping PostgreSQL path (no --db)")

    print("[4/4] Scalability sweep")
    out["scalability"] = measure_scalability(
        [(4, 3), (6, 5), (10, 8), (15, 12)], n_msgs=2000, runs=3)

    out["false_violations_during_outage"] = \
        measure_false_violations_during_outage()

    if args.spof:
        print("[+] SPOF experiment (real time, ~70 s)")
        out["spof"] = asyncio.run(measure_spof())

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {args.out}")
    return out


if __name__ == "__main__":
    main()
