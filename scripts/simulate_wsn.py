#!/usr/bin/env python3
# =============================================================================
# scripts/simulate_wsn.py  — FIXED
#
# Changes from previous version:
#   FIX: Added --workers, --forklifts, --pallets arguments so the number of
#        moving objects is configurable without editing the script.
#
# Usage examples:
#   python scripts/simulate_wsn.py                          # defaults
#   python scripts/simulate_wsn.py --workers 3 --forklifts 1 --pallets 2
#   python scripts/simulate_wsn.py --cols 8 --rows 6 --workers 10
#   python scripts/simulate_wsn.py --host mosquitto --fire-delay 60
# =============================================================================

import argparse, json, math, random, time
from datetime import datetime, timezone

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: pip install paho-mqtt"); raise


# ─── Grid helpers ─────────────────────────────────────────────────────────────

def sensor_id(row: int, col: int, cols: int) -> str:
    return f"S{row * cols + col + 1:02d}"

def neighbours(sid: str, cols: int, rows: int) -> list[str]:
    n   = int(sid[1:]) - 1
    row = n // cols
    col = n %  cols
    nb  = []
    if row > 0:        nb.append(sensor_id(row - 1, col, cols))
    if row < rows - 1: nb.append(sensor_id(row + 1, col, cols))
    if col > 0:        nb.append(sensor_id(row, col - 1, cols))
    if col < cols - 1: nb.append(sensor_id(row, col + 1, cols))
    return nb

def all_sensors(cols: int, rows: int) -> list[str]:
    return [sensor_id(r, c, cols) for r in range(rows) for c in range(cols)]


# ─── Environmental sensor simulator ───────────────────────────────────────────

class SensorSim:
    def __init__(self, sid: str, base_temp: float):
        self.sid       = sid
        self.base_temp = base_temp
        self.humidity  = random.uniform(45, 65)
        self._hd       = random.uniform(-0.3, 0.3)  # humidity drift

    def reading(self, elapsed: float, fire: bool = False, fire_elapsed: float = 0) -> dict:
        cycle = 1.5 * math.sin(elapsed / 90.0)
        temp  = self.base_temp + cycle + random.gauss(0, 0.2)
        smoke = False
        if fire:
            prog   = min(fire_elapsed / 60.0, 1.0)
            temp  += prog * 42.0
            smoke  = prog > 0.25
        self._hd      = max(-1.0, min(1.0, self._hd + random.gauss(0, 0.05)))
        self.humidity = max(20.0, min(95.0, self.humidity + self._hd + random.gauss(0, 0.3)))
        return {"temperature": round(temp, 2),
                "humidity":    round(self.humidity, 2),
                "smoke":       smoke}


# ─── Asset (random walk on grid) ──────────────────────────────────────────────

class Asset:
    def __init__(self, aid: str, atype: str, start: str,
                 cols: int, rows: int, move_prob: float = 0.25):
        self.id        = aid
        self.type      = atype
        self.sensor    = start
        self.cols      = cols
        self.rows      = rows
        self.move_prob = move_prob

    def step(self) -> bool:
        """Move to a random adjacent sensor. Returns True if moved."""
        if random.random() < self.move_prob:
            nb = neighbours(self.sensor, self.cols, self.rows)
            if nb:
                self.sensor = random.choice(nb)
                return True
        return False


# ─── Main ─────────────────────────────────────────────────────────────────────

def run(args):
    cols, rows    = args.cols, args.rows
    sensors       = all_sensors(cols, rows)
    fire_sensor   = sensor_id(rows // 2, cols // 2, cols)

    # Per-sensor environmental simulators
    sim_sensors = {s: SensorSim(s, random.uniform(18.0, 28.0)) for s in sensors}

    # ── FIX: asset counts from CLI args ───────────────────────────────────────
    all_assets: list[Asset] = []

    for i in range(1, args.workers + 1):
        all_assets.append(Asset(
            f"W{i:02d}", "worker",
            random.choice(sensors), cols, rows,
            move_prob = 0.20,
        ))
    for i in range(1, args.forklifts + 1):
        all_assets.append(Asset(
            f"F{i:02d}", "forklift",
            random.choice(sensors), cols, rows,
            move_prob = 0.35,
        ))
    for i in range(1, args.pallets + 1):
        all_assets.append(Asset(
            f"P{i:02d}", "pallet",
            random.choice(sensors), cols, rows,
            move_prob = 0.10,
        ))
    # ── End FIX ───────────────────────────────────────────────────────────────

    # MQTT connection
    client = mqtt.Client(client_id="dt_wsn_simulator")
    client.on_connect = lambda c, u, f, rc: (
        print(f"  Connected to {args.host}:{args.port}") if rc == 0
        else print(f"  MQTT connect failed rc={rc}")
    )
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()

    def ts() -> str:
        return datetime.now(timezone.utc).isoformat()

    def pub(topic: str, payload):
        client.publish(topic, json.dumps(payload), qos=1)

    print(f"\n{'━'*58}")
    print(f"  Digital Twin WSN Simulator")
    print(f"  Grid : {cols}×{rows}  ({cols*rows} sensors)")
    print(f"  Assets: {args.workers} workers  {args.forklifts} forklifts  {args.pallets} pallets")
    print(f"  Fire : sensor {fire_sensor} ignites after {args.fire_delay}s")
    print(f"  Pub  : every {args.interval}s → {args.host}:{args.port}")
    print(f"{'━'*58}\n")

    start = time.time()
    tick  = 0

    try:
        while True:
            elapsed     = time.time() - start
            tick       += 1
            fire_active = elapsed >= args.fire_delay

            # Publish environmental readings for every sensor
            for sid, sim in sim_sensors.items():
                is_fire = (sid == fire_sensor and fire_active)
                env     = sim.reading(
                    elapsed,
                    fire         = is_fire,
                    fire_elapsed = elapsed - args.fire_delay if fire_active else 0,
                )
                for rtype, val in env.items():
                    pub("wsn/env", [sid, rtype, val, ts()])

            # Move assets and publish locations (every tick)
            for asset in all_assets:
                asset.step()
                pub("wsn/location", [asset.id, asset.sensor, ts()])

            # Console status line
            fire_str = (f"🔥 FIRE at {fire_sensor}" if fire_active
                        else f"fire in {int(args.fire_delay - elapsed)}s")
            print(f"\r  tick={tick:>4}  t={int(elapsed):>4}s  {fire_str:<30}",
                  end="", flush=True)

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n\n  Stopped after {tick} ticks ({int(time.time()-start)}s).")
    finally:
        client.loop_stop()
        client.disconnect()


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Digital Twin WSN simulator")
    ap.add_argument("--host",       default="localhost")
    ap.add_argument("--port",       type=int,   default=1883)
    ap.add_argument("--cols",       type=int,   default=6,
                    help="Grid columns (must match REACT_APP_GRID_COLS)")
    ap.add_argument("--rows",       type=int,   default=5,
                    help="Grid rows (must match REACT_APP_GRID_ROWS)")
    ap.add_argument("--interval",   type=float, default=2.0,
                    help="Seconds between publish cycles")
    ap.add_argument("--fire-delay", type=int,   default=300,
                    help="Seconds before fire event starts")
    # ── FIX: new args ─────────────────────────────────────────────────────────
    ap.add_argument("--workers",    type=int,   default=5,
                    help="Number of worker tags (W01…WNN)")
    ap.add_argument("--forklifts",  type=int,   default=2,
                    help="Number of forklift tags (F01…FNN)")
    ap.add_argument("--pallets",    type=int,   default=2,
                    help="Number of pallet tags (P01…PNN)")
    # ── End FIX ───────────────────────────────────────────────────────────────

    run(ap.parse_args())
