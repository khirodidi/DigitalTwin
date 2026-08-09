#!/usr/bin/env python3
# =============================================================================
# scripts/simulate_wsn.py  —  CONFIG-DRIVEN WITH TRAJECTORIES
#
# Everything is read from the Digital Twin configuration API:
#   • grid size            → /api/config/factory   (grid_cols, grid_rows)
#   • sensor coverage      → /api/config/sensors   (coverage_type, passable)
#   • zones                → /api/config/zones     (zone = its set of sensors)
#   • assets + auth        → /api/config/workers   (real IDs, names, auth)
#
# TRAJECTORY MODEL
# ────────────────
# Instead of a pure random walk, each asset is assigned a TRAJECTORY: an
# ordered list of waypoints inside its authorised area. The asset walks the
# shortest passable path from waypoint to waypoint, pausing at each one for a
# dwell time determined by that cell's coverage_type, then continues to the
# next. When the last waypoint is reached the route reverses (patrol) or
# loops (circuit), so movement is repeatable and realistic rather than random.
#
# Trajectory styles chosen per asset type:
#   worker    patrol   — walks between machines/stations in its zones, back and forth
#   forklift  circuit  — loops storage ↔ exit, avoiding machine cells
#   pallet    static   — parked, occasionally nudged one cell (moved by a forklift)
#
# Usage:
#   python scripts/simulate_wsn.py
#   python scripts/simulate_wsn.py --api http://backend:8000 --host mosquitto
#   python scripts/simulate_wsn.py --waypoints 5 --violation-rate 0.05
#   python scripts/simulate_wsn.py --no-config --cols 8 --rows 6 --workers 10
# =============================================================================

import argparse
import json
import math
import random
import sys
import time
from collections import deque
from datetime import datetime, timezone

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: pip install paho-mqtt"); sys.exit(1)

import urllib.request


# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION LOADER
# ═══════════════════════════════════════════════════════════════════════════════

class FactoryConfig:
    """Loads the live Digital Twin configuration from the backend API."""

    def __init__(self, api_url: str):
        self.api     = api_url.rstrip("/")
        self.cols    = 6
        self.rows    = 5
        self.name    = "Factory"
        self.sensors = {}   # sid → {zone_id, coverage_type, passable, row, col, description}
        self.zones   = {}   # zid → {name, sensor_ids}
        self.assets  = []   # [{asset_id, asset_type, name, allowed_zones, allowed_sensors}]

    def _get(self, path):
        try:
            with urllib.request.urlopen(f"{self.api}{path}", timeout=6) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            print(f"    ! {path}: {e}")
            return None

    def load(self) -> bool:
        print(f"  Reading configuration from {self.api}")

        fac = self._get("/api/config/factory")
        if fac:
            self.cols = int(fac.get("grid_cols", 6))
            self.rows = int(fac.get("grid_rows", 5))
            self.name = fac.get("factory_name", "Factory")
            bp = fac.get("blueprint_url") or "none"
            print(f"    factory   : {self.name}  {self.cols}x{self.rows}  blueprint={bp}")

        sen = self._get("/api/config/sensors")
        if sen:
            for s in sen:
                self.sensors[s["sensor_id"]] = {
                    "zone_id":       s.get("zone_id"),
                    "coverage_type": s.get("coverage_type", "passage"),
                    "passable":      bool(s.get("passable", True)),
                    "row":           s.get("grid_row", 0),
                    "col":           s.get("grid_col", 0),
                    "description":   s.get("description", ""),
                }
            types = {}
            for v in self.sensors.values():
                types[v["coverage_type"]] = types.get(v["coverage_type"], 0) + 1
            blocked = sum(1 for v in self.sensors.values() if not v["passable"])
            print(f"    sensors   : {len(self.sensors)}  types={types}  blocked={blocked}")

        zon = self._get("/api/config/zones")
        if zon:
            for z in zon:
                self.zones[z["zone_id"]] = {
                    "name":       z.get("name", z["zone_id"]),
                    "sensor_ids": list(z.get("sensor_ids") or []),
                }
            print(f"    zones     : {len(self.zones)}  " +
                  ", ".join(f"{k}({len(v['sensor_ids'])})" for k, v in self.zones.items()))

        wor = self._get("/api/config/workers")
        if wor:
            for w in wor:
                auth = w.get("authorisations") or []
                self.assets.append({
                    "asset_id":        w["asset_id"],
                    "asset_type":      w.get("asset_type", "worker"),
                    "name":            w.get("name", w["asset_id"]),
                    "allowed_zones":   [a["id"] for a in auth if a.get("type") == "zone"],
                    "allowed_sensors": [a["id"] for a in auth if a.get("type") == "sensor"],
                })
            counts = {}
            for a in self.assets:
                counts[a["asset_type"]] = counts.get(a["asset_type"], 0) + 1
            print(f"    assets    : {len(self.assets)}  {counts}")

        return bool(self.sensors and self.assets)

    # ── Grid helpers ─────────────────────────────────────────────────────────

    def sid(self, row, col):
        return f"S{row * self.cols + col + 1:02d}"

    def pos(self, sid):
        s = self.sensors.get(sid)
        if s:
            return s["row"], s["col"]
        n = int("".join(c for c in sid if c.isdigit()) or "1") - 1
        return divmod(n, self.cols)

    def all_sids(self):
        return sorted(self.sensors.keys()) if self.sensors else \
               [self.sid(r, c) for r in range(self.rows) for c in range(self.cols)]

    def passable(self, sid):
        return self.sensors.get(sid, {}).get("passable", True)

    def ctype(self, sid):
        return self.sensors.get(sid, {}).get("coverage_type", "passage")

    def zone_of(self, sid):
        return self.sensors.get(sid, {}).get("zone_id")

    def zone_sensors(self, zone_ids):
        out = []
        for z in zone_ids:
            out.extend(self.zones.get(z, {}).get("sensor_ids", []))
        return out

    def neighbours(self, sid, avoid=None):
        """Grid-adjacent, passable, not of an avoided coverage type."""
        r, c = self.pos(sid)
        cand = []
        if r > 0:             cand.append(self.sid(r - 1, c))
        if r < self.rows - 1: cand.append(self.sid(r + 1, c))
        if c > 0:             cand.append(self.sid(r, c - 1))
        if c < self.cols - 1: cand.append(self.sid(r, c + 1))
        out = []
        for n in cand:
            if self.sensors and n not in self.sensors:  continue
            if not self.passable(n):                    continue
            if avoid and self.ctype(n) in avoid:        continue
            out.append(n)
        return out

    def shortest_path(self, start, goal, avoid=None, prefer=None):
        """
        BFS over passable cells.
        If `prefer` is given, the search first tries to stay entirely inside
        that set (the asset's authorised area) and only falls back to the
        unrestricted grid when no such path exists. This stops an asset that
        strayed once from racking up violations on the walk home.
        """
        if start == goal:
            return [start]

        def bfs(allowed):
            seen = {start}
            q    = deque([[start]])
            while q:
                path = q.popleft()
                for n in self.neighbours(path[-1], avoid=avoid):
                    if n in seen:
                        continue
                    if allowed is not None and n not in allowed and n != goal:
                        continue
                    if n == goal:
                        return path + [n]
                    seen.add(n)
                    q.append(path + [n])
            return []

        if prefer:
            inside = bfs(set(prefer) | {start, goal})
            if inside:
                return inside
        return bfs(None)


# ═══════════════════════════════════════════════════════════════════════════════
#  ENVIRONMENTAL SENSOR
# ═══════════════════════════════════════════════════════════════════════════════

class SensorSim:
    """Base temperature depends on what the sensor covers."""
    TEMP = {"machine": (28.0, 34.0), "storage": (16.0, 20.0),
            "passage": (20.0, 25.0), "exit":    (15.0, 20.0)}

    def __init__(self, sid, ctype="passage"):
        lo, hi        = self.TEMP.get(ctype, (20.0, 26.0))
        self.sid      = sid
        self.ctype    = ctype
        self.base     = random.uniform(lo, hi)
        self.humidity = random.uniform(45, 65)
        self._drift   = random.uniform(-0.3, 0.3)

    def reading(self, elapsed, fire=False, fire_elapsed=0.0):
        noise = 0.4 if self.ctype == "machine" else 0.2
        temp  = self.base + 1.5 * math.sin(elapsed / 90.0) + random.gauss(0, noise)
        smoke = False
        if fire:
            p     = min(fire_elapsed / 60.0, 1.0)
            temp += p * 42.0
            smoke = p > 0.25
        self._drift   = max(-1.0, min(1.0, self._drift + random.gauss(0, 0.05)))
        self.humidity = max(20.0, min(95.0,
                            self.humidity + self._drift + random.gauss(0, 0.3)))
        return {"temperature": round(temp, 2),
                "humidity":    round(self.humidity, 2),
                "smoke":       smoke}


# ═══════════════════════════════════════════════════════════════════════════════
#  TRAJECTORY-DRIVEN ASSET
# ═══════════════════════════════════════════════════════════════════════════════

class Asset:
    """
    An asset that follows a generated trajectory through its authorised area.

    Life cycle each tick:
      1. If dwelling at a waypoint  → count down, publish same position
      2. Else if steps remain on the current leg → advance one cell
      3. Else → arrived at waypoint: set dwell, plan the leg to the next waypoint
    """

    # Dwell ticks per coverage type (how long the asset stays at a waypoint)
    DWELL = {"machine": (5, 12), "storage": (3, 6),
             "passage": (1, 2),  "exit":    (1, 2)}

    # Coverage types each asset type refuses to enter
    AVOID = {"worker": [], "forklift": ["machine"], "pallet": ["machine", "exit"]}

    # Preferred waypoint coverage types — the trajectory is built from these
    PREFER = {"worker":   ["machine", "storage", "passage"],
              "forklift": ["storage", "exit", "passage"],
              "pallet":   ["storage"]}

    # Trajectory style and how many ticks between advancing one cell
    STYLE = {"worker": "patrol", "forklift": "circuit", "pallet": "static"}
    SPEED = {"worker": 1, "forklift": 1, "pallet": 3}   # ticks per cell moved

    def __init__(self, cfg, spec, n_waypoints=4, violation_rate=0.02):
        self.cfg        = cfg
        self.id         = spec["asset_id"]
        self.type       = spec["asset_type"]
        self.name       = spec["name"]
        self.zones      = spec["allowed_zones"]
        self.sensors_ok = spec["allowed_sensors"]
        self.viol_rate  = violation_rate
        self.avoid      = self.AVOID.get(self.type, [])
        self.style      = self.STYLE.get(self.type, "patrol")
        self.speed      = self.SPEED.get(self.type, 1)

        self.home       = self._home_cells()
        self.waypoints  = self._build_trajectory(n_waypoints)
        self.wp_index   = 0
        self.leg        = []      # remaining cells on the current leg
        self.direction  = 1       # for patrol reversal
        self.dwell      = 0
        self.tick_mod   = 0
        self.violations = 0
        self.moves      = 0

        self.sensor = self.waypoints[0] if self.waypoints else self._any_passable()
        self._plan_next_leg()

    # ── Territory ────────────────────────────────────────────────────────────

    def _home_cells(self):
        allowed = set(self.cfg.zone_sensors(self.zones)) | set(self.sensors_ok)
        cells = [s for s in allowed
                 if self.cfg.passable(s) and self.cfg.ctype(s) not in self.avoid]
        if cells:
            return cells
        # No authorisation → roam anywhere passable (generates violations)
        return [s for s in self.cfg.all_sids()
                if self.cfg.passable(s) and self.cfg.ctype(s) not in self.avoid]

    def _any_passable(self):
        p = [s for s in self.cfg.all_sids() if self.cfg.passable(s)]
        return random.choice(p) if p else self.cfg.sid(0, 0)

    # ── Trajectory construction ──────────────────────────────────────────────

    def _reachable_home(self, origin):
        """
        Flood-fill from `origin` through home cells only.
        A zone can be split into disconnected islands by blocked cells or by
        coverage types this asset avoids; waypoints must all sit in the same
        island or the asset would be forced to cross unauthorised ground.
        """
        home = set(self.home)
        if origin not in home:
            return home
        seen, q = {origin}, deque([origin])
        while q:
            cur = q.popleft()
            for nb in self.cfg.neighbours(cur, avoid=self.avoid):
                if nb in home and nb not in seen:
                    seen.add(nb); q.append(nb)
        return seen

    def _build_trajectory(self, n):
        """
        Pick n waypoints inside the home area, preferring the coverage types
        this asset type works with, then order them into a sensible route by
        nearest-neighbour so the path doesn't zig-zag across the factory.
        Waypoints are restricted to one connected island so the asset never
        has to leave its authorised area to complete the route.
        """
        if not self.home:
            return []

        # Restrict to the largest connected island of the home area
        best = set()
        for seed in random.sample(self.home, min(len(self.home), 6)):
            comp = self._reachable_home(seed)
            if len(comp) > len(best):
                best = comp
        if best:
            self.home = sorted(best)

        if self.style == "static":
            # Pallets sit in one place with at most one nearby alternate
            base = random.choice(self.home)
            nbrs = [x for x in self.cfg.neighbours(base, avoid=self.avoid)
                    if x in self.home]
            return [base] + ([random.choice(nbrs)] if nbrs else [])

        # Rank candidates by preferred coverage type
        prefer = self.PREFER.get(self.type, ["passage"])
        buckets = {t: [s for s in self.home if self.cfg.ctype(s) == t] for t in prefer}

        picks = []
        for t in prefer:
            pool = [s for s in buckets.get(t, []) if s not in picks]
            random.shuffle(pool)
            picks.extend(pool[: max(1, n // max(len(prefer), 1))])
        # Top up from anywhere in the home area
        spare = [s for s in self.home if s not in picks]
        random.shuffle(spare)
        picks.extend(spare)
        picks = picks[: max(2, min(n, len(self.home)))]

        # Nearest-neighbour ordering from the first pick
        route, remaining = [picks[0]], picks[1:]
        while remaining:
            cur = route[-1]
            cr, cc = self.cfg.pos(cur)
            remaining.sort(key=lambda s: abs(self.cfg.pos(s)[0] - cr) +
                                         abs(self.cfg.pos(s)[1] - cc))
            route.append(remaining.pop(0))
        return route

    def _plan_next_leg(self):
        """Compute the walking path from current position to the next waypoint."""
        if len(self.waypoints) < 2:
            self.leg = []
            return

        if self.style == "circuit":
            self.wp_index = (self.wp_index + 1) % len(self.waypoints)
        else:  # patrol — bounce between the ends
            self.wp_index += self.direction
            if self.wp_index >= len(self.waypoints):
                self.wp_index = max(0, len(self.waypoints) - 2)
                self.direction = -1
            elif self.wp_index < 0:
                self.wp_index = min(1, len(self.waypoints) - 1)
                self.direction = 1

        target = self.waypoints[self.wp_index]
        path   = self.cfg.shortest_path(self.sensor, target,
                                        avoid=self.avoid, prefer=self.home)
        self.leg = path[1:] if len(path) > 1 else []

    # ── Authorisation ────────────────────────────────────────────────────────

    def _authorised(self, sid):
        if sid in self.sensors_ok:
            return True
        z = self.cfg.zone_of(sid)
        return bool(z and z in self.zones)

    # ── Per-tick update ──────────────────────────────────────────────────────

    def step(self) -> bool:
        # Speed throttling (pallets move rarely)
        self.tick_mod = (self.tick_mod + 1) % self.speed
        if self.tick_mod != 0:
            return False

        # Dwelling at a waypoint
        if self.dwell > 0:
            self.dwell -= 1
            return False

        # Occasional deliberate stray into an unauthorised neighbour
        if self.viol_rate > 0 and random.random() < self.viol_rate:
            outside = [n for n in self.cfg.neighbours(self.sensor, avoid=self.avoid)
                       if not self._authorised(n)]
            if outside:
                self.sensor = random.choice(outside)
                self.violations += 1
                self.moves     += 1
                self.dwell      = random.randint(1, 3)
                self.leg        = []          # re-plan from the new position
                self._plan_next_leg()
                return True

        # Walk the current leg
        if self.leg:
            was_ok      = self._authorised(self.sensor)
            self.sensor = self.leg.pop(0)
            self.moves += 1
            # Only count the transition INTO unauthorised ground
            if was_ok and not self._authorised(self.sensor):
                self.violations += 1
            if not self.leg:                  # arrived at the waypoint
                lo, hi = self.DWELL.get(self.cfg.ctype(self.sensor), (1, 2))
                self.dwell = random.randint(lo, hi)
                self._plan_next_leg()
            return True

        # No leg planned — plan one
        self._plan_next_leg()
        return False

    def describe(self) -> str:
        wp = " → ".join(self.waypoints[:6]) + ("…" if len(self.waypoints) > 6 else "")
        return (f"{self.id:5} {self.type:9} {self.name[:18]:18} "
                f"{self.style:7} home={len(self.home):3} "
                f"wp={len(self.waypoints)}  [{wp}]")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def build_fallback(cfg, args):
    """Grid + assets from CLI args when --no-config is used."""
    cfg.cols, cfg.rows = args.cols, args.rows
    for r in range(cfg.rows):
        for c in range(cfg.cols):
            cfg.sensors[cfg.sid(r, c)] = {
                "zone_id": None, "coverage_type": "passage", "passable": True,
                "row": r, "col": c, "description": ""}
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


def run(args):
    print(f"\n{'━' * 72}")
    cfg = FactoryConfig(args.api)

    if args.no_config:
        print("  Config loading disabled — using CLI arguments")
        build_fallback(cfg, args)
    elif not cfg.load():
        print("\n  Configuration incomplete. Start the backend and seed the DB,")
        print("  or run with --no-config to use CLI defaults.\n")
        return

    sids = cfg.all_sids()
    sims = {s: SensorSim(s, cfg.ctype(s)) for s in sids}

    # Fire on a machine cell when available — most realistic ignition point
    machines = [s for s in sids if cfg.ctype(s) == "machine" and cfg.passable(s)]
    passable = [s for s in sids if cfg.passable(s)]
    fire_sid = random.choice(machines or passable or sids)

    assets = [Asset(cfg, spec, n_waypoints=args.waypoints,
                    violation_rate=args.violation_rate)
              for spec in cfg.assets]
    if not assets:
        print("  No assets configured — add workers in the Configuration page.")
        return

    print(f"\n  {cfg.name}  {cfg.cols}x{cfg.rows}  ({len(sids)} sensors, "
          f"{sum(1 for s in sids if not cfg.passable(s))} blocked)")
    print(f"  Fire at {fire_sid} ({cfg.ctype(fire_sid)}) after {args.fire_delay}s"
          f"  ·  violation rate {args.violation_rate:.0%}")
    print(f"\n  Trajectories ({args.waypoints} waypoints target):")
    for a in assets:
        print("    " + a.describe())
    print(f"\n  Publishing every {args.interval}s → {args.host}:{args.port}")
    print(f"{'━' * 72}\n")

    client = mqtt.Client(client_id="dt_wsn_simulator")
    client.on_connect = lambda c, u, f, rc: print(
        "  MQTT connected\n" if rc == 0 else f"  MQTT failed rc={rc}")
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()

    ts  = lambda: datetime.now(timezone.utc).isoformat()
    pub = lambda t, p: client.publish(t, json.dumps(p), qos=1)

    start, tick = time.time(), 0
    try:
        while True:
            elapsed = time.time() - start
            tick   += 1
            burning = elapsed >= args.fire_delay
            f_el    = elapsed - args.fire_delay if burning else 0.0

            for s, sim in sims.items():
                env = sim.reading(elapsed, fire=(s == fire_sid and burning),
                                  fire_elapsed=f_el)
                for k, v in env.items():
                    pub("wsn/env", [s, k, v, ts()])

            for a in assets:
                a.step()
                pub("wsn/location", [a.id, a.sensor, ts()])

            moves = sum(a.moves for a in assets)
            viol  = sum(a.violations for a in assets)
            fire  = f"FIRE {fire_sid}" if burning else \
                    f"fire in {max(0, int(args.fire_delay - elapsed))}s"
            print(f"\r  tick={tick:>5} t={int(elapsed):>5}s  {fire:<16} "
                  f"moves={moves:<6} violations={viol:<5}", end="", flush=True)

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n\n  Stopped after {tick} ticks ({int(time.time() - start)}s)")
        print(f"  {'ASSET':6} {'TYPE':9} {'MOVES':>6} {'VIOL':>5}  POSITION")
        for a in assets:
            print(f"  {a.id:6} {a.type:9} {a.moves:>6} {a.violations:>5}  {a.sensor}")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Config-driven Digital Twin WSN simulator with trajectories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
The simulator reads grid size, sensor coverage, zones, assets and their
authorisations from the Digital Twin configuration API, then generates a
trajectory for each asset inside its authorised area.

  worker    patrol  — walks between machines/stations, reverses at the ends
  forklift  circuit — loops storage and exits, never enters machine cells
  pallet    static  — parked, nudged occasionally

Examples:
  python scripts/simulate_wsn.py
  python scripts/simulate_wsn.py --waypoints 6 --violation-rate 0.05
  python scripts/simulate_wsn.py --api http://backend:8000 --host mosquitto
  python scripts/simulate_wsn.py --no-config --cols 8 --rows 6 --workers 10
""")
    ap.add_argument("--api",  default="http://localhost:8000")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--interval",       type=float, default=2.0)
    ap.add_argument("--fire-delay",     type=int,   default=300)
    ap.add_argument("--waypoints",      type=int,   default=4,
                    help="Target number of waypoints per trajectory")
    ap.add_argument("--violation-rate", type=float, default=0.02,
                    help="Chance per move of straying outside authorised area")
    ap.add_argument("--no-config", action="store_true")
    ap.add_argument("--cols",      type=int, default=6)
    ap.add_argument("--rows",      type=int, default=5)
    ap.add_argument("--workers",   type=int, default=5)
    ap.add_argument("--forklifts", type=int, default=2)
    ap.add_argument("--pallets",   type=int, default=2)
    run(ap.parse_args())
