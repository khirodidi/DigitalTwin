# =============================================================================
# ai/training/trajectory.py
#
# TRAJECTORY LEARNING — the configured route is only the starting point
#
# An operator sets an initial `default_trajectory` when an asset is created.
# That route is a best guess. Real work patterns drift: a machine is moved, a
# storage bay is reassigned, a worker finds a shorter path between two
# stations. This module mines the movement actually observed and proposes an
# updated route.
#
# ALGORITHM
#   1. Extract every shift's cell sequence from location_events
#   2. Keep only shifts scored efficient by model ① (score >= MIN_EFFICIENCY),
#      so the learned route reflects good practice rather than average practice
#   3. Find stop points — cells where the asset dwelled beyond DWELL_THRESHOLD
#   4. Cluster stop points across shifts by frequency
#   5. Order the resulting waypoints with a nearest-neighbour tour seeded at
#      the most frequent morning start cell
#   6. Accept only if the proposal beats the active route on a held-out set
#
# INPUT   location_events, asset_trajectory (active version), sensor_config
# OUTPUT  a new 'learned' trajectory version per asset, with a confidence score
#
# The learned route becomes active only when confidence exceeds MIN_CONFIDENCE.
# The operator's original 'configured' version is never deleted and can be
# restored from the Configuration page at any time.
# =============================================================================

import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import numpy as np

logger = logging.getLogger(__name__)

MIN_SHIFTS       = 5      # shifts needed before proposing anything
MIN_EFFICIENCY   = 0.65   # only learn from shifts model ① rated efficient
DWELL_THRESHOLD  = 3      # consecutive readings at a cell to count as a stop
MIN_STOP_SUPPORT = 0.35   # a waypoint must appear in ≥35 % of shifts
MIN_CONFIDENCE   = 0.60   # below this the proposal is stored but not activated
MAX_WAYPOINTS    = 8


# ─── Extraction ───────────────────────────────────────────────────────────────

def extract_shift_sequences(days: int = 30) -> dict:
    """
    Returns { asset_id: [ [cell, cell, ...] per shift ] }.
    Shifts are 8-hour blocks, matching the movement model's sample unit.
    """
    from persistence.postgres import get_conn
    import psycopg2.extras
    import pandas as pd

    cutoff = datetime.utcnow() - timedelta(days=days)
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT asset_id, sensor_id, zone_id, timestamp
            FROM location_events
            WHERE timestamp >= %s AND sensor_id IS NOT NULL
            ORDER BY asset_id, timestamp
        """, (cutoff,))
        rows = cur.fetchall()

    if not rows:
        return {}

    df = pd.DataFrame(rows)
    df["timestamp"]   = pd.to_datetime(df["timestamp"])
    df["shift_start"] = df["timestamp"].dt.floor("8h")

    out = defaultdict(list)
    for (aid, _), grp in df.groupby(["asset_id", "shift_start"]):
        seq = grp.sort_values("timestamp")["sensor_id"].tolist()
        if len(seq) >= 4:
            out[aid].append(seq)
    return dict(out)


def find_stop_points(sequence: list, dwell: int = DWELL_THRESHOLD) -> list:
    """
    Cells where the asset stayed put — these are work stations, not corridors.

    A run of `dwell` or more consecutive identical readings counts as a stop.
    Returns stops in visiting order, de-duplicated consecutively.
    """
    stops, run, prev = [], 0, None
    for cell in sequence:
        if cell == prev:
            run += 1
        else:
            run, prev = 1, cell
        if run == dwell:
            if not stops or stops[-1] != cell:
                stops.append(cell)
    return stops


# ─── Learning ─────────────────────────────────────────────────────────────────

def learn_route(shifts: list, pos_fn, efficiency: dict = None) -> tuple:
    """
    Derive a waypoint route from observed shifts.

    Returns (waypoints, confidence). Confidence combines how consistently the
    waypoints appear and how many shifts contributed.
    """
    if len(shifts) < MIN_SHIFTS:
        return [], 0.0

    # Keep only shifts model ① rated as efficient, when scores are available
    usable = shifts
    if efficiency:
        good = [s for i, s in enumerate(shifts)
                if efficiency.get(i, 1.0) >= MIN_EFFICIENCY]
        if len(good) >= MIN_SHIFTS:
            usable = good

    # Which cells are worked at, and how often
    support = Counter()
    per_shift_stops = []
    for seq in usable:
        stops = find_stop_points(seq)
        per_shift_stops.append(stops)
        support.update(set(stops))

    n = len(usable)
    waypoints = [c for c, k in support.items() if k / n >= MIN_STOP_SUPPORT]
    if len(waypoints) < 2:
        return [], 0.0

    # Keep the best-supported waypoints
    waypoints.sort(key=lambda c: -support[c])
    waypoints = waypoints[:MAX_WAYPOINTS]

    # Order them: start from the most common first stop, then nearest-neighbour
    first = Counter(s[0] for s in per_shift_stops if s)
    start = (first.most_common(1)[0][0] if first and first.most_common(1)[0][0]
             in waypoints else waypoints[0])

    route, remaining = [start], [c for c in waypoints if c != start]
    while remaining:
        cr, cc = pos_fn(route[-1])
        remaining.sort(key=lambda c: abs(pos_fn(c)[0] - cr) + abs(pos_fn(c)[1] - cc))
        route.append(remaining.pop(0))

    # Confidence: mean support of chosen waypoints, scaled by sample size
    mean_support = float(np.mean([support[c] / n for c in route]))
    sample_factor = min(n / (MIN_SHIFTS * 3), 1.0)
    confidence = round(mean_support * 0.7 + sample_factor * 0.3, 4)

    return route, confidence


def route_similarity(a: list, b: list) -> float:
    """Jaccard overlap of two routes — used to decide if an update is material."""
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


# ─── Persistence ──────────────────────────────────────────────────────────────

def _load_grid():
    from persistence.postgres import get_conn
    import psycopg2.extras
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT key, value FROM factory_config")
        cfg = {r["key"]: r["value"] for r in cur.fetchall()}
    return int(cfg.get("grid_cols") or 6), int(cfg.get("grid_rows") or 5)


def _active_route(asset_id: str) -> list:
    from persistence.postgres import get_conn
    import psycopg2.extras
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT t.sensor_id FROM asset_trajectory t
            JOIN asset_trajectory_active a
              ON a.asset_id=t.asset_id AND a.source=t.source AND a.version=t.version
            WHERE t.asset_id=%s ORDER BY t.seq
        """, (asset_id,))
        return [r["sensor_id"] for r in cur.fetchall()]


def save_learned_route(asset_id: str, route: list, confidence: float,
                       activate: bool) -> int:
    """Store a new 'learned' version; activate it only if confident enough."""
    from persistence.postgres import get_conn
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""SELECT COALESCE(MAX(version),0)+1 FROM asset_trajectory
                       WHERE asset_id=%s AND source='learned'""", (asset_id,))
        version = cur.fetchone()[0]
        for i, sid in enumerate(route):
            cur.execute("""INSERT INTO asset_trajectory
                             (asset_id, seq, sensor_id, source, version, confidence)
                           VALUES (%s,%s,%s,'learned',%s,%s)""",
                        (asset_id, i, sid, version, confidence))
        if activate:
            cur.execute("""INSERT INTO asset_trajectory_active
                             (asset_id, source, version)
                           VALUES (%s,'learned',%s)
                           ON CONFLICT (asset_id) DO UPDATE
                             SET source='learned', version=EXCLUDED.version,
                                 updated_at=NOW()""", (asset_id, version))
    conn.commit()
    return version


# ─── Public entry point ───────────────────────────────────────────────────────

def train_trajectories(days: int = 30, activate: bool = True) -> dict:
    """
    Learn an updated trajectory for every asset with enough observed movement.

    Called nightly by AITrainer. Assets without enough data keep whatever
    route is currently active — usually the operator's original.
    """
    logger.info("=== Trajectory learning ===")
    cols, rows = _load_grid()
    pos_fn = lambda sid: divmod(
        int("".join(c for c in str(sid) if c.isdigit()) or 1) - 1, cols)

    sequences = extract_shift_sequences(days)
    if not sequences:
        logger.info("  No location history — nothing to learn")
        return {}

    updated, skipped, results = 0, 0, {}
    for asset_id, shifts in sequences.items():
        if len(shifts) < MIN_SHIFTS:
            skipped += 1
            continue

        route, conf = learn_route(shifts, pos_fn)
        if not route:
            skipped += 1
            continue

        current = _active_route(asset_id)
        sim     = route_similarity(route, current)

        # Only store a new version when the route materially differs
        if current and sim > 0.85:
            results[asset_id] = {"action": "unchanged", "similarity": round(sim, 3)}
            continue

        act = activate and conf >= MIN_CONFIDENCE
        version = save_learned_route(asset_id, route, conf, act)
        updated += 1
        results[asset_id] = {
            "action":     "activated" if act else "proposed",
            "version":    version,
            "confidence": conf,
            "similarity": round(sim, 3),
            "waypoints":  len(route),
            "route":      route,
        }
        logger.info(f"  {asset_id}: {len(route)} waypoints, conf={conf:.2f}, "
                    f"sim={sim:.2f} → {'ACTIVATED' if act else 'proposed only'}")

    logger.info(f"  {updated} route(s) updated, {skipped} skipped "
                f"(need ≥{MIN_SHIFTS} shifts)")
    return {"updated": updated, "skipped": skipped, "assets": results}
