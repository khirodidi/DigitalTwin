# =============================================================================
# ai/models/smart_evacuation.py
# Digital Twin — AI Layer
# Model 2: Smart Evacuation Planner
#
# Two-stage approach:
#   Stage 1 — XGBoost: per-zone danger score from environmental features
#   Stage 2 — Dijkstra: safest route on danger-weighted zone adjacency graph
#
# Triggers on: smoke detected | temp > 60°C | operator command
# Recomputes:  every 2s during active emergency
# =============================================================================

import heapq
import numpy as np
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

try:
    from xgboost import XGBRegressor
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class ZoneNode:
    zone_id:       str
    sensor_ids:    list[str]
    is_exit:       bool = False
    danger_score:  float = 0.0      # 0 = safe, 1 = maximum danger


@dataclass
class EvacRoute:
    asset_id:        str
    start_zone:      str
    route:           list[str]      # ordered zone_ids to traverse
    exit_zone:       str
    estimated_secs:  float
    max_danger:      float
    priority_rank:   int            # 1 = evacuate first


# ─── Zone graph builder ───────────────────────────────────────────────────────

class ZoneGraph:
    """
    Adjacency graph of zones, built from the ZoneRegistry and floor plan.
    Edge weights incorporate the danger score of the destination zone.
    """

    SECONDS_PER_ZONE = 15.0        # average traversal time per zone

    def __init__(self):
        self._nodes: dict[str, ZoneNode] = {}
        self._adj:   dict[str, list[str]] = {}    # zone_id → [neighbour_zone_id]

    def add_zone(self, zone: ZoneNode):
        self._nodes[zone.zone_id] = zone
        self._adj.setdefault(zone.zone_id, [])

    def add_edge(self, zone_a: str, zone_b: str):
        """Bidirectional adjacency."""
        self._adj.setdefault(zone_a, []).append(zone_b)
        self._adj.setdefault(zone_b, []).append(zone_a)

    def update_danger(self, zone_id: str, danger_score: float):
        if zone_id in self._nodes:
            self._nodes[zone_id].danger_score = danger_score

    def edge_cost(self, from_zone: str, to_zone: str) -> float:
        """
        Cost to traverse from from_zone to to_zone.
        High danger in destination = high cost.
        """
        dest = self._nodes.get(to_zone)
        if dest is None:
            return float("inf")
        danger_weight = 1.0 + dest.danger_score * 10.0   # 1× (safe) to 11× (smoke)
        return self.SECONDS_PER_ZONE * danger_weight

    def dijkstra(self, start: str, exits: list[str]) -> tuple[list[str], float]:
        """
        Find the minimum-cost path from start to any exit zone.
        Returns (route, total_cost_seconds).
        """
        dist = {z: float("inf") for z in self._nodes}
        prev = {z: None for z in self._nodes}
        dist[start] = 0.0
        pq = [(0.0, start)]

        visited = set()
        while pq:
            cost, zone = heapq.heappop(pq)
            if zone in visited:
                continue
            visited.add(zone)

            if zone in exits:
                # Reconstruct path
                path = []
                cur = zone
                while cur is not None:
                    path.append(cur)
                    cur = prev[cur]
                return list(reversed(path)), cost

            for neighbour in self._adj.get(zone, []):
                if neighbour in visited:
                    continue
                new_cost = cost + self.edge_cost(zone, neighbour)
                if new_cost < dist[neighbour]:
                    dist[neighbour] = new_cost
                    prev[neighbour] = zone
                    heapq.heappush(pq, (new_cost, neighbour))

        return [], float("inf")   # no path found

    @property
    def exit_zones(self) -> list[str]:
        return [z for z, node in self._nodes.items() if node.is_exit]


# ─── Stage 1: Danger score predictor ─────────────────────────────────────────

class DangerScorePredictor:
    """
    XGBoost regressor: env features → danger_score ∈ [0, 1] per zone.
    Falls back to rule-based scoring when model not trained yet.
    """

    def __init__(self, model_path: str = None):
        self._model = None
        self._feature_keys: list[str] = []
        if XGB_AVAILABLE and model_path:
            self._load(model_path)

    def _load(self, path: str):
        import joblib
        try:
            artefact = joblib.load(path)
            self._model        = artefact["model"]
            self._feature_keys = artefact["feature_keys"]
            print(f"[DangerScorePredictor] Loaded from {path}")
        except Exception as e:
            print(f"[DangerScorePredictor] Could not load model: {e}")

    def train(
        self,
        X: np.ndarray,           # (N, F) feature matrix
        y: np.ndarray,           # (N,) danger scores ∈ [0, 1]
        feature_keys: list[str],
        model_path: str = "models/danger_xgb.joblib",
    ):
        if not XGB_AVAILABLE:
            raise RuntimeError("xgboost not installed. Run: pip install xgboost")

        import joblib
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import mean_squared_error

        X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)

        model = XGBRegressor(
            n_estimators     = 300,
            max_depth        = 4,
            learning_rate    = 0.05,
            subsample        = 0.8,
            colsample_bytree = 0.8,
            random_state     = 42,
        )
        model.fit(X_train, y_train,
                  eval_set=[(X_val, y_val)],
                  verbose=False)

        preds = model.predict(X_val)
        mse   = mean_squared_error(y_val, preds)
        print(f"  Danger predictor MSE: {mse:.4f} | RMSE: {mse**0.5:.4f}")

        import joblib
        joblib.dump({"model": model, "feature_keys": feature_keys}, model_path)
        self._model        = model
        self._feature_keys = feature_keys

    def predict(self, feature_vec: np.ndarray) -> float:
        """Predict danger score for one zone's current env features."""
        if self._model is not None:
            score = float(self._model.predict(feature_vec.reshape(1, -1))[0])
            return float(np.clip(score, 0.0, 1.0))
        # Rule-based fallback
        return self._rule_based(feature_vec)

    def _rule_based(self, vec: np.ndarray) -> float:
        """
        Simple rule-based danger score before model is trained.
        Assumes feature order: [temp_last, hum_last, smoke_last, ...]
        """
        temp  = vec[0] if len(vec) > 0 else 0
        smoke = vec[2] if len(vec) > 2 else 0
        score = 0.0
        if smoke > 0.5:
            score += 0.6
        if temp > 60:
            score += 0.4
        elif temp > 50:
            score += 0.2
        return float(np.clip(score, 0.0, 1.0))


# ─── Evacuation planner ───────────────────────────────────────────────────────

class SmartEvacuationPlanner:
    """
    Main evacuation planner. Combines danger scoring with graph routing.
    Maintains the zone graph and updates danger scores in real time.
    Produces per-asset evacuation routes when triggered.
    """

    TRIGGER_SMOKE_THRESHOLD = 0.5    # smoke sensor reading
    TRIGGER_TEMP_THRESHOLD  = 60.0   # °C
    RECOMPUTE_INTERVAL_SECS = 2.0    # during active emergency

    def __init__(self, graph: ZoneGraph, danger_predictor: DangerScorePredictor):
        self._graph       = graph
        self._danger      = danger_predictor
        self._active      = False
        self._last_routes: dict[str, EvacRoute] = {}

    def update_danger_scores(self, env_features: dict[str, np.ndarray]):
        """
        Called on every environmental reading update.
        Updates danger score for each zone in the graph.

        env_features: { zone_id: feature_vector }
        """
        for zone_id, feat_vec in env_features.items():
            score = self._danger.predict(feat_vec)
            self._graph.update_danger(zone_id, score)

    def should_trigger(self, sensor_states: list) -> bool:
        """
        Check if evacuation should be triggered based on current sensor states.
        sensor_states: list of SensorState objects.
        """
        for s in sensor_states:
            if s.smoke:
                return True
            if s.temperature and s.temperature > self.TRIGGER_TEMP_THRESHOLD:
                return True
        return False

    def compute_routes(
        self,
        asset_locations: list[tuple[str, str]],   # [(asset_id, zone_id)]
    ) -> list[EvacRoute]:
        """
        Compute optimal evacuation routes for all assets.
        Prioritises assets in highest-danger zones.

        Returns list of EvacRoute, sorted by priority (highest danger first).
        """
        exits = self._graph.exit_zones
        if not exits:
            return []

        routes = []
        for asset_id, zone_id in asset_locations:
            if zone_id not in self._graph._nodes:
                continue

            path, cost = self._graph.dijkstra(zone_id, exits)
            if not path:
                continue

            start_danger = self._graph._nodes[zone_id].danger_score
            max_danger   = max(
                self._graph._nodes[z].danger_score
                for z in path if z in self._graph._nodes
            )

            routes.append(EvacRoute(
                asset_id       = asset_id,
                start_zone     = zone_id,
                route          = path,
                exit_zone      = path[-1],
                estimated_secs = cost,
                max_danger     = max_danger,
                priority_rank  = 0,   # assigned below
            ))

        # Prioritise: highest start danger first
        routes.sort(key=lambda r: -self._graph._nodes[r.start_zone].danger_score)
        for rank, route in enumerate(routes, 1):
            route.priority_rank = rank

        self._last_routes = {r.asset_id: r for r in routes}
        self._active = True
        return routes

    def to_alert(self, route: EvacRoute) -> dict:
        return {
            "type":            "evacuation_route",
            "level":           "critical",
            "asset_id":        route.asset_id,
            "start_zone":      route.start_zone,
            "route":           route.route,
            "exit_zone":       route.exit_zone,
            "estimated_secs":  round(route.estimated_secs, 1),
            "max_danger":      round(route.max_danger, 3),
            "priority_rank":   route.priority_rank,
            "action":          "follow_evacuation_route",
            "timestamp":       datetime.utcnow().isoformat(),
        }

    def cancel(self):
        """Cancel active evacuation (all-clear)."""
        self._active = False
        self._last_routes = {}
