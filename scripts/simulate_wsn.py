#!/usr/bin/env python3
# =============================================================================
# scripts/simulate_wsn.py  —  CONFIG-AWARE VERSION
#
# The simulator now reads the live configuration from the backend API and
# simulates movement that respects it:
#
#   1. GRID SIZE          from /api/config/factory   (grid_cols, grid_rows)
#   2. SENSOR COVERAGE    from /api/config/sensors   (coverage_type, passable)
#   3. ZONES              from /api/config/zones     (sensor→zone mapping)
#   4. ASSETS + AUTH      from /api/config/workers   (real IDs, allowed zones)
#
# Movement rules derived from config:
#   • Workers never enter a cell with passable=false (machines, blocked areas)
#   • Workers prefer cells inside their authorised zones
#   • Occasionally (--violation-rate) a worker strays outside → VIOLATION alert
#   • Dwell time depends on coverage_type:
#       machine  → long dwell   (working at the machine)
#       storage  → medium dwell (picking items)
#       passage  → short dwell  (walking through)
#       exit     → very short   (passing the door)
#   • Forklifts avoid 'machine' cells entirely (too tight to manoeuvre)
#   • Pallets barely move (they are moved by forklifts)
#
# Environmental simulation is unchanged except the fire is placed on a
# passable cell so evacuation routing has a meaningful scenario.
#
# Usage:
#   python scripts/simulate_wsn.py                       # reads all config from API
#   python scripts/simulate_wsn.py --api http://localhost:8000
#   python scripts/simulate_wsn.py --no-config           # fall back to CLI args
#   python scripts/simulate_wsn.py --violation-rate 0.05 # 5% chance to stray
# =============================================================================

import argparse
import json
import math
import random
import sys
import time
from datetime import datetime, timezone

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: pip install paho-mqtt"); sys.exit(1)

try:
    import urllib.request
    import urllib.error
except ImportError:
    print("ERROR: urllib not available"); sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIG LOADER — pulls live configuration from the backend API
# ═══════════════════════════════════════════════════════════════════════════════

class FactoryConfig:
    """Loads and holds the factory configuration from the backend API."""

    def __init__(self, api_url: str):
        self.api_url    = api_url.rstrip("/")
        self.cols       = 6
        self.rows       = 5
        self.factory    = "Factory"
        self.sensors    = {}   # sensor_id → {zone_id, coverage_type, passable, row, col}
        self.zones      = {}   # zone_id   → {name, sensor_ids}
        self.assets     = []   # [{asset_id, asset_type, name, allowed_zones, allowed_sensors}]
        self.loaded     = False

    def _get(self, path: str):
        url = f"{self.api_url}{path}"
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            print(f"  ! Could not fetch {path}: {e}")
            return None

    def load(self) -> bool:
        """Fetch all config. Returns True if successful."""
        print(f"  Loading configuration from {self.api_url} ...")

        # ── 1. Factory-level settings ─────────────────────────────────────────
        fac = self._get("/api/config/factory")
        if fac:
            self.cols    = int(fac.get("grid_cols", 6))
            self.rows    = int(fac.get("grid_rows", 5))
            self.factory = fac.get("factory_name", "Factory")
            print(f"    Factory : {self.factory}  ({self.cols}x{self.rows} grid)")

        # ── 2. Sensor coverage metadata ───────────────────────────────────────
        sens = self._get("/api/config/sensors")
        if sens:
            for s in sens:
                self.sensors[s["sensor_id"]] = {
                    "zone_id":       s.get("zone_id"),
                    "coverage_type": s.get("coverage_type", "passage"),
                    "passable":      s.get("passable", True),
                    "row":           s.get("grid_row", 0),
                    "col":           s.get("grid_col", 0),
                    "description":   s.get("description", ""),
                }
            n_block = sum(1 for v in self.sensors.values() if not v["passable"])
            types   = {}
            for v in self.sensors.values():
                types[v["coverage_type"]] = types.get(v["coverage_type"], 0) + 1
            print(f"    Sensors : {len(self.sensors)}  "
                  f"({n_block} non-passable)  types={types}")

        # ── 3. Zones ──────────────────────────────────────────────────────────
        zns = self._get("/api/config/zones")
        if zns:
            for z in zns:
                self.zones[z["zone_id"]] = {
                    "name":       z.get("name", z["zone_id"]),
                    "sensor_ids": z.get("sensor_ids", []) or [],
                }
            print(f"    Zones   : {len(self.zones)}  "
                  f"({', '.join(self.zones.keys())})")

        # ── 4. Assets with authorisations ─────────────────────────────────────
        wks = self._get("/api/config/workers")
        if wks:
            for w in wks:
                auths  = w.get("authorisations") or []
                zones  = [a["id"] for a in auths if a.get("type") == "zone"]
                sensrs = [a["id"] for a in auths if a.get("type") == "sensor"]
                self.assets.append({
                    "asset_id":        w["asset_id"],
                    "asset_type":      w.get("asset_type", "worker"),
                    "name":            w.get("name", w["asset_id"]),
                    "allowed_zones":   zones,
                    "allowed_sensors": sensrs,
                })
            by_type = {}
            for a in self.assets:
                by_type[a["asset_type"]] = by_type.get(a["asset_type"], 0) + 1
            print(f"    Assets  : {len(self.assets)}  {by_type}")

        self.loaded = bool(self.sensors and self.assets)
        if not self.loaded:
            print("    ! Config incomplete — check the backend is running and DB is seeded")
        return self.loaded

    # ── Grid helpers driven by loaded config ─────────────────────────────────

    def sensor_id(self, row: int, col: int) -> str:
        return f"S{row * self.cols + col + 1:02d}"

    def pos(self, sid: str) -> tuple[int, int]:
        info = self.sensors.get(sid)
        if info:
            return info["row"], info["col"]
        n = int("".join(c for c in sid if c.isdigit()) or "1") - 1
        return divmod(n, self.cols)

    def all_sensor_ids(self) -> list[str]:
        if self.sensors:
            return sorted(self.sensors.keys())
        return [self.sensor_id(r, c) for r in range(self.rows) for c in range(self.cols)]

    def is_passable(self, sid: str) -> bool:
        return self.sensors.get(sid, {}).get("passable", True)

    def coverage_type(self, sid: str) -> str:
        return self.sensors.get(sid, {}).get("coverage_type", "passage")

    def zone_of(self, sid: str) -> str | None:
        return self.sensors.get(sid, {}).get("zone_id")

    def sensors_in_zones(self, zone_ids: list[str]) -> list[str]:
        """All sensor IDs belonging to any of the given zones."""
        out = []
        for zid in zone_ids:
            out.extend(self.zones.get(zid, {}).get("sensor_ids", []))
        return out

    def neighbours(self, sid: str, passable_only: bool = True,
                    avoid_types: list[str] = None) -> list[str]:
        """
        Grid-adjacent sensors (N/S/E/W).
        passable_only : skip cells configured as passable=false
        avoid_types   : skip cells whose coverage_type is in this list
        """
        row, col = self.pos(sid)
        cand = []
        if row > 0:              cand.append(self.sensor_id(row - 1, col))
        if row < self.rows - 1:  cand.append(self.sensor_id(row + 1, col))
        if col > 0:              cand.append(self.sensor_id(row, col - 1))
        if col < self.cols - 1:  cand.append(self.sensor_id(row, col + 1))

        result = []
        for c in cand:
            if c not in self.sensors and self.sensors:
                continue                                    # sensor not configured
            if passable_only and not self.is_passable(c):
                continue                                    # blocked cell
            if avoid_types and self.coverage_type(c) in avoid_types:
                continue                                    # type this asset avoids
            result.append(c)
        return result


# ═══════════════════════════════════════════════════════════════════════════════
#  ENVIRONMENTAL SENSOR SIMULATION
# ═══════════════════════════════════════════════════════════════════════════════

class SensorSim:
    """
    Simulates temperature / humidity / smoke for one sensor.
    Base temperature depends on coverage_type — machines run hotter.
    """
    BASE_TEMP = {
        "machine": (28.0, 34.0),   # machines radiate heat
        "storage": (16.0, 20.0),   # storage areas are cooler
        "passage": (20.0, 25.0),   # corridors are ambient
        "exit":    (15.0, 20.0),   # near doors = draughty
    }

    def __init__(self, sid: str, coverage_type: str = "passage"):
        self.sid      = sid
        self.ctype    = coverage_type
        lo, hi        = self.BASE_TEMP.get(coverage_type, (20.0, 26.0))
        self.base     = random.uniform(lo, hi)
        self.humidity = random.uniform(45, 65)
        self._hd      = random.uniform(-0.3, 0.3)

    def reading(self, elapsed: float, fire: bool = False,
                fire_elapsed: float = 0.0) -> dict:
        # Machines have more temperature variance than corridors
        noise_scale = 0.4 if self.ctype == "machine" else 0.2
        cycle = 1.5 * math.sin(elapsed / 90.0)
        temp  = self.base + cycle + random.gauss(0, noise_scale)

        smoke = False
        if fire:
            prog   = min(fire_elapsed / 60.0, 1.0)
            temp  += prog * 42.0
            smoke  = prog > 0.25

        self._hd      = max(-1.0, min(1.0, self._hd + random.gauss(0, 0.05)))
        self.humidity = max(20.0, min(95.0,
                            self.humidity + self._hd + random.gauss(0, 0.3)))

        return {"temperature": round(temp, 2),
                "humidity":    round(self.humidity, 2),
                "smoke":       smoke}


# ═══════════════════════════════════════════════════════════════════════════════
#  ASSET SIMULATION — movement driven by configuration
# ═══════════════════════════════════════════════════════════════════════════════

class Asset:
    """
    A tagged worker / forklift / pallet moving on the configured grid.

    Movement respects:
      - passable flag        : never enters a blocked cell
      - coverage_type        : dwells longer at machines than in corridors
      - allowed zones        : mostly stays inside authorised area
      - violation_rate       : occasional deliberate stray → VIOLATION alert
    """

    # How many ticks the asset lingers at each coverage type
    DWELL = {
        "machine": (4, 10),   # working at a machine
        "storage": (2, 5),    # picking stock
        "passage": (1, 2),    # walking through
        "exit":    (1, 1),    # passing the door
    }

    # Which coverage types each asset type avoids entirely
    AVOID = {
        "worker":   [],                     # workers go anywhere passable
        "forklift": ["machine"],            # too tight around machinery
        "pallet":   ["machine", "exit"],    # parked in storage/passage only
    }

    # Base probability of attempting a move on any given tick
    MOVE_PROB = {"worker": 0.35, "forklift": 0.45, "pallet": 0.06}

    def __init__(self, cfg: FactoryConfig, asset_id: str, asset_type: str,
                 name: str, allowed_zones: list[str], allowed_sensors: list[str],
                 violation_rate: float = 0.02):
        self.cfg             = cfg
        self.id              = asset_id
        self.type            = asset_type
        self.name            = name
        self.allowed_zones   = allowed_zones
        self.allowed_sensors = allowed_sensors
        self.violation_rate  = violation_rate
        self.dwell_left      = 0
        self.violations      = 0
        self.sensor          = self._pick_start()

    # ── Home territory = sensors this asset is authorised for ────────────────
    def home_sensors(self) -> list[str]:
        allowed = set(self.cfg.sensors_in_zones(self.allowed_zones))
        allowed.update(self.allowed_sensors)
        # Only passable ones this asset type doesn't avoid
        avoid = self.AVOID.get(self.type, [])
        return [s for s in allowed
                if self.cfg.is_passable(s) and self.cfg.coverage_type(s) not in avoid]

    def _pick_start(self) -> str:
        home = self.home_sensors()
        if home:
            return random.choice(home)
        # Unauthorised asset — start anywhere passable
        passable = [s for s in self.cfg.all_sensor_ids() if self.cfg.is_passable(s)]
        return random.choice(passable) if passable else self.cfg.sensor_id(0, 0)

    def _is_authorised(self, sid: str) -> bool:
        if sid in self.allowed_sensors:
            return True
        zone = self.cfg.zone_of(sid)
        return zone in self.allowed_zones if zone else False

    def step(self) -> bool:
        """Advance one tick. Returns True if the asset moved."""
        # Still dwelling at current cell?
        if self.dwell_left > 0:
            self.dwell_left -= 1
            return False

        if random.random() > self.MOVE_PROB.get(self.type, 0.3):
            return False

        avoid = self.AVOID.get(self.type, [])
        nbrs  = self.cfg.neighbours(self.sensor, passable_only=True, avoid_types=avoid)
        if not nbrs:
            return False

        # Split neighbours into authorised and unauthorised
        allowed_nbrs   = [n for n in nbrs if self._is_authorised(n)]
        forbidden_nbrs = [n for n in nbrs if not self._is_authorised(n)]

        # Decide destination
        if forbidden_nbrs and random.random() < self.violation_rate:
            dest = random.choice(forbidden_nbrs)   # deliberate stray → violation
            self.violations += 1
        elif allowed_nbrs:
            dest = random.choice(allowed_nbrs)     # normal authorised movement
        elif forbidden_nbrs:
            dest = random.choice(forbidden_nbrs)   # boxed in — must cross
            self.violations += 1
        else:
            return False

        self.sensor = dest
        # Set dwell time based on what the destination covers
        lo, hi = self.DWELL.get(self.cfg.coverage_type(dest), (1, 2))
        self.dwell_left = random.randint(lo, hi)
        return True


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN SIMULATION LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def run(args):
    cfg = FactoryConfig(args.api)

    # ── Load configuration from the API ───────────────────────────────────────
    print(f"\n{'━'*64}")
    if args.no_config:
        print("  Config loading DISABLED — using CLI arguments only")
        cfg.cols, cfg.rows = args.cols, args.rows
        for r in range(cfg.rows):
            for c in range(cfg.cols):
                sid = cfg.sensor_id(r, c)
                cfg.sensors[sid] = {"zone_id": None, "coverage_type": "passage",
                                     "passable": True, "row": r, "col": c,
                                     "description": ""}
        for i in range(1, args.workers + 1):
            cfg.assets.append({"asset_id": f"W{i:02d}", "asset_type": "worker",
                               "name": f"Worker {i}", "allowed_zones": [],
                               "allowed_sensors": []})
        for i in range(1, args.forklifts + 1):
            cfg.assets.append({"asset_id": f"F{i:02d}", "asset_type": "forklift",
                               "name": f"Forklift {i}", "allowed_zones": [],
                               "allowed_sensors": []})
        for i in range(1, args.pallets + 1):
            cfg.assets.append({"asset_id": f"P{i:02d}", "asset_type": "pallet",
                               "name": f"Pallet {i}", "allowed_zones": [],
                               "allowed_sensors": []})
    else:
        ok = cfg.load()
        if not ok:
            print("\n  Falling back to CLI defaults. Start the backend and seed the DB,")
            print("  then re-run to use the configured layout.\n")
            return run(argparse.Namespace(**{**vars(args), "no_config": True}))

    sensors_all = cfg.all_sensor_ids()

    # ── Build environmental simulators (type-aware base temperature) ─────────
    sim_sensors = {sid: SensorSim(sid, cfg.coverage_type(sid)) for sid in sensors_all}

    # ── Choose a fire location: a passable cell, preferably a machine ────────
    machine_cells  = [s for s in sensors_all
                      if cfg.coverage_type(s) == "machine" and cfg.is_passable(s)]
    passable_cells = [s for s in sensors_all if cfg.is_passable(s)]
    fire_sensor    = (random.choice(machine_cells) if machine_cells
                      else random.choice(passable_cells) if passable_cells
                      else sensors_all[0])

    # ── Instantiate assets from configuration ────────────────────────────────
    assets = [
        Asset(cfg, a["asset_id"], a["asset_type"], a["name"],
              a["allowed_zones"], a["allowed_sensors"],
              violation_rate=args.violation_rate)
        for a in cfg.assets
    ]

    if not assets:
        print("  ! No assets configured. Add workers in the Configuration page.")
        return

    # ── Summary ──────────────────────────────────────────────────────────────
    n_blocked = sum(1 for s in sensors_all if not cfg.is_passable(s))
    print(f"\n  {cfg.factory}  —  {cfg.cols}x{cfg.rows} grid, {len(sensors_all)} sensors")
    print(f"  Non-passable cells : {n_blocked}")
    print(f"  Fire location      : {fire_sensor} "
          f"({cfg.coverage_type(fire_sensor)}) after {args.fire_delay}s")
    print(f"  Violation rate     : {args.violation_rate:.0%}")
    print(f"\n  Assets:")
    for a in assets:
        home = len(a.home_sensors())
        zones = ", ".join(a.allowed_zones) if a.allowed_zones else "NONE (always violation)"
        print(f"    {a.id:5} {a.type:9} {a.name[:20]:20} start={a.sensor:4} "
              f"home={home:2} cells  zones=[{zones}]")
    print(f"\n  Publishing every {args.interval}s -> {args.host}:{args.port}")
    print(f"{'━'*64}\n")

    # ── MQTT ─────────────────────────────────────────────────────────────────
    client = mqtt.Client(client_id="dt_wsn_simulator")
    client.on_connect = lambda c, u, f, rc: (
        print(f"  MQTT connected\n") if rc == 0 else print(f"  MQTT failed rc={rc}")
    )
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()

    def ts() -> str:
        return datetime.now(timezone.utc).isoformat()

    def pub(topic, payload):
        client.publish(topic, json.dumps(payload), qos=1)

    start = time.time()
    tick  = 0
    total_moves = 0

    try:
        while True:
            elapsed     = time.time() - start
            tick       += 1
            fire_active = elapsed >= args.fire_delay
            fire_el     = elapsed - args.fire_delay if fire_active else 0.0

            # ── Environmental readings ────────────────────────────────────────
            for sid, sim in sim_sensors.items():
                env = sim.reading(
                    elapsed,
                    fire         = (sid == fire_sensor and fire_active),
                    fire_elapsed = fire_el,
                )
                for rtype, val in env.items():
                    pub("wsn/env", [sid, rtype, val, ts()])

            # ── Asset movement + location ─────────────────────────────────────
            moved_now = 0
            for a in assets:
                if a.step():
                    moved_now   += 1
                    total_moves += 1
                pub("wsn/location", [a.id, a.sensor, ts()])

            # ── Console status ────────────────────────────────────────────────
            total_viol = sum(a.violations for a in assets)
            fire_str = (f"FIRE at {fire_sensor}" if fire_active
                        else f"fire in {max(0, int(args.fire_delay - elapsed))}s")
            print(f"\r  tick={tick:>4} t={int(elapsed):>4}s  {fire_str:<22} "
                  f"moves={total_moves:<5} violations={total_viol:<4}",
                  end="", flush=True)

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n\n  Stopped after {tick} ticks ({int(time.time()-start)}s)")
        print(f"  Total moves      : {total_moves}")
        print(f"  Total violations : {sum(a.violations for a in assets)}")
        for a in assets:
            if a.violations:
                print(f"    {a.id} ({a.name}): {a.violations} violation(s)")
    finally:
        client.loop_stop()
        client.disconnect()


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Config-aware Digital Twin WSN simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/simulate_wsn.py
      Read all layout, sensors, zones and workers from the backend API.

  python scripts/simulate_wsn.py --api http://backend:8000 --host mosquitto
      Run inside Docker network.

  python scripts/simulate_wsn.py --violation-rate 0.08
      Higher chance of workers straying into unauthorised zones.

  python scripts/simulate_wsn.py --no-config --cols 8 --rows 6 --workers 10
      Ignore the API and use plain CLI arguments (old behaviour).
""")
    ap.add_argument("--api",  default="http://localhost:8000",
                    help="Backend API base URL for loading configuration")
    ap.add_argument("--host", default="localhost", help="MQTT broker host")
    ap.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    ap.add_argument("--interval",   type=float, default=2.0,
                    help="Seconds between publish cycles")
    ap.add_argument("--fire-delay", type=int, default=300,
                    help="Seconds before the fire event starts")
    ap.add_argument("--violation-rate", type=float, default=0.02,
                    help="Probability a worker strays into an unauthorised cell (0-1)")

    # Fallback arguments used only with --no-config
    ap.add_argument("--no-config", action="store_true",
                    help="Skip API config loading and use the CLI values below")
    ap.add_argument("--cols",      type=int, default=6)
    ap.add_argument("--rows",      type=int, default=5)
    ap.add_argument("--workers",   type=int, default=5)
    ap.add_argument("--forklifts", type=int, default=2)
    ap.add_argument("--pallets",   type=int, default=2)

    run(ap.parse_args())
