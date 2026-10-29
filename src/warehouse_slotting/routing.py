"""Aisle-constrained walking distances, nearest-bin routes, and time components."""

from __future__ import annotations

from itertools import pairwise
from typing import Any

import numpy as np
import pandas as pd


def _point_distance(
    aisle_a: int,
    y_a: float,
    x_a: float,
    aisle_b: int,
    y_b: float,
    x_b: float,
    front: float,
    rear: float,
) -> tuple[float, str]:
    if aisle_a == aisle_b:
        return abs(y_a - y_b), "aisle"
    via_front = abs(y_a - front) + abs(x_a - x_b) + abs(y_b - front)
    via_rear = abs(y_a - rear) + abs(x_a - x_b) + abs(y_b - rear)
    if via_front <= via_rear:
        return via_front, "front"
    return via_rear, "rear"


def travel_graph(locations: pd.DataFrame, warehouse: dict[str, Any]) -> dict[str, Any]:
    """Project bins onto aisle centerlines and precompute legal walking distances."""
    spacing = float(warehouse["aisle_spacing_m"])
    front = float(warehouse["front_cross_aisle_y_m"])
    rear = float(warehouse["rear_cross_aisle_y_m"])
    frame = locations.sort_values("location_id").reset_index(drop=True)
    aisle = frame["aisle_number"].to_numpy(dtype=int)
    y = frame["y_m"].to_numpy(dtype=float)
    level = frame["shelf_level"].to_numpy(dtype=int)
    center_x = aisle.astype(float) * spacing
    same = aisle[:, None] == aisle[None, :]
    dy = np.abs(y[:, None] - y[None, :])
    dx = np.abs(center_x[:, None] - center_x[None, :])
    via_front = np.abs(y[:, None] - front) + dx + np.abs(y[None, :] - front)
    via_rear = np.abs(y[:, None] - rear) + dx + np.abs(y[None, :] - rear)
    distance = np.where(same, dy, np.minimum(via_front, via_rear)).astype(float)
    np.fill_diagonal(distance, 0.0)
    return {
        "location_ids": frame["location_id"].tolist(),
        "index": {location_id: position for position, location_id in enumerate(frame["location_id"])},
        "aisle": aisle,
        "y": y,
        "level": level,
        "center_x": center_x,
        "distance": distance,
        "front": front,
        "rear": rear,
        "spacing": spacing,
        "frame": frame,
    }


def depot_distance(graph: dict[str, Any], depot_aisle: int, depot_y: float) -> np.ndarray:
    """Legal distance from the packing desk to every bin centerline."""
    depot_x = float(depot_aisle) * graph["spacing"]
    aisle = graph["aisle"]
    y = graph["y"]
    center_x = graph["center_x"]
    front = graph["front"]
    rear = graph["rear"]
    same = aisle == int(depot_aisle)
    via_front = abs(depot_y - front) + np.abs(center_x - depot_x) + np.abs(y - front)
    via_rear = abs(depot_y - rear) + np.abs(center_x - depot_x) + np.abs(y - rear)
    along_aisle = np.abs(y - depot_y)
    return np.where(same, along_aisle, np.minimum(via_front, via_rear)).astype(float)


def _connect(
    aisle_a: int,
    y_a: float,
    x_a: float,
    aisle_b: int,
    y_b: float,
    x_b: float,
    front: float,
    rear: float,
) -> list[tuple[float, float]]:
    if aisle_a == aisle_b:
        return [(x_a, y_a), (x_b, y_b)]
    _, gate = _point_distance(aisle_a, y_a, x_a, aisle_b, y_b, x_b, front, rear)
    cross_y = front if gate == "front" else rear
    return [(x_a, y_a), (x_a, cross_y), (x_b, cross_y), (x_b, y_b)]


def sequence_stops(stop_indices: list[int], distance: np.ndarray, from_depot: np.ndarray, location_ids: list[str]) -> tuple[list[int], float]:
    """Nearest unused stop, tied by location ID, then return to the desk."""
    remaining = list(stop_indices)
    current = -1
    ordered: list[int] = []
    total = 0.0
    while remaining:
        best_at = 0
        best_key: tuple[float, str] | None = None
        for position, index in enumerate(remaining):
            leg = float(from_depot[index] if current < 0 else distance[current, index])
            key = (leg, location_ids[index])
            if best_key is None or key < best_key:
                best_key = key
                best_at = position
        chosen = remaining.pop(best_at)
        total += best_key[0]
        ordered.append(chosen)
        current = chosen
    if current >= 0:
        total += float(from_depot[current])
    return ordered, total


def route_vertices(ordered: list[int], graph: dict[str, Any], depot_aisle: int, depot_y: float) -> list[tuple[float, float]]:
    """Centerline polyline for a sequenced route, including the return to the desk."""
    depot_x = float(depot_aisle) * graph["spacing"]
    points = [(int(depot_aisle), float(depot_y), depot_x)]
    for index in ordered:
        points.append((int(graph["aisle"][index]), float(graph["y"][index]), float(graph["center_x"][index])))
    points.append((int(depot_aisle), float(depot_y), depot_x))
    vertices = [(points[0][2], points[0][1])]
    for start, end in pairwise(points):
        vertices.extend(_connect(start[0], start[1], start[2], end[0], end[1], end[2], graph["front"], graph["rear"])[1:])
    return vertices


def time_components(distance_m: float, levels: list[int], quantity: int, rules: dict[str, Any]) -> dict[str, float]:
    """Split a route into walking, reach, and handling. Handling does not depend on the bin."""
    reach_table = {int(level): float(seconds) for level, seconds in rules["reach_penalty_seconds"].items()}
    walk = distance_m / float(rules["walking_speed_mps"])
    reach = float(sum(reach_table[int(level)] for level in levels))
    base = float(rules["base_pick_seconds"]) * len(levels)
    quantity_time = float(rules["seconds_per_unit"]) * int(quantity)
    return {
        "walk_s": walk,
        "reach_s": reach,
        "base_s": base,
        "quantity_s": quantity_time,
        "time_s": walk + reach + base + quantity_time,
    }


def replay_order(
    sku_quantities: dict[str, int],
    assignment: dict[str, str],
    graph: dict[str, Any],
    rules: dict[str, Any],
    depot_aisle: int,
    depot_y: float,
) -> dict[str, Any]:
    """Route one order on a fixed assignment and return the path the chart draws."""
    from_depot = depot_distance(graph, depot_aisle, depot_y)
    indices = [graph["index"][assignment[sku_id]] for sku_id in sku_quantities]
    ordered, distance_m = sequence_stops(indices, graph["distance"], from_depot, graph["location_ids"])
    levels = [int(graph["level"][index]) for index in ordered]
    timing = time_components(distance_m, levels, sum(sku_quantities.values()), rules)
    id_by_index = {index: sku_id for sku_id, index in zip(sku_quantities, indices)}
    stops = []
    for index in ordered:
        sku_id = id_by_index[index]
        stops.append({
            "sku_id": sku_id,
            "location_id": graph["location_ids"][index],
            "aisle": int(graph["aisle"][index]),
            "shelf_level": int(graph["level"][index]),
            "quantity": int(sku_quantities[sku_id]),
        })
    return {
        "distance_m": distance_m,
        "vertices": route_vertices(ordered, graph, depot_aisle, depot_y),
        "stops": stops,
        **timing,
    }


def replay_order_policy(
    sku_quantities: dict[str, int],
    assignment: dict[str, str],
    graph: dict[str, Any],
    rules: dict[str, Any],
    depot_aisle: int,
    depot_y: float,
    policy: str,
) -> dict[str, Any]:
    """Replay one order using an aisle routing policy and return its legal path."""
    normalized = policy.lower().replace("-", " ").strip()
    if normalized in {"nearest", "nearest bin", "nearest stop"}:
        return replay_order(sku_quantities, assignment, graph, rules, depot_aisle, depot_y)
    if normalized not in {"s shape", "largest gap", "return"}:
        raise ValueError(f"Unknown routing policy: {policy}")
    from_depot = depot_distance(graph, depot_aisle, depot_y)
    stop_skus: dict[int, str] = {}
    groups: dict[int, list[int]] = {}
    for sku_id in sku_quantities:
        index = graph["index"][assignment[sku_id]]
        stop_skus[index] = sku_id
        groups.setdefault(int(graph["aisle"][index]), []).append(index)
    for aisle, indices in groups.items():
        groups[aisle] = sorted(indices, key=lambda index: (float(graph["y"][index]), graph["location_ids"][index]))

    depot_x = float(depot_aisle) * graph["spacing"]
    front, rear = float(graph["front"]), float(graph["rear"])
    waypoints: list[tuple[float, float]] = [(depot_x, float(depot_y))]
    ordered: list[int] = []

    def aisle_point(aisle: int, y: float) -> tuple[float, float]:
        return float(aisle) * graph["spacing"], float(y)

    def add_stops(indices: list[int]) -> None:
        ordered.extend(indices)
        waypoints.extend((float(graph["center_x"][index]), float(graph["y"][index])) for index in indices)

    active = sorted(groups)
    if normalized == "return":
        for aisle in active:
            waypoints.append(aisle_point(aisle, front))
            add_stops(groups[aisle])
            waypoints.append(aisle_point(aisle, front))
        waypoints.append((depot_x, float(depot_y)))
    elif normalized == "s shape":
        for position, aisle in enumerate(active):
            forward = position % 2 == 0
            start_y, end_y = (front, rear) if forward else (rear, front)
            waypoints.append(aisle_point(aisle, start_y))
            add_stops(groups[aisle] if forward else list(reversed(groups[aisle])))
            waypoints.append(aisle_point(aisle, end_y))
        end_y = rear if len(active) % 2 else front
        waypoints.extend([(depot_x, end_y), (depot_x, float(depot_y))])
    else:
        front_groups: dict[int, list[int]] = {}
        rear_groups: dict[int, list[int]] = {}
        for aisle in active:
            indices = groups[aisle]
            y_positions = [front, *(float(graph["y"][index]) for index in indices), rear]
            gaps = [right - left for left, right in pairwise(y_positions)]
            largest = int(np.argmax(gaps))
            if largest == 0:
                rear_groups[aisle] = indices
            elif largest == len(indices):
                front_groups[aisle] = indices
            else:
                front_groups[aisle] = indices[:largest]
                rear_groups[aisle] = list(reversed(indices[largest:]))
        for aisle in sorted(front_groups):
            waypoints.append(aisle_point(aisle, front))
            add_stops(front_groups[aisle])
            waypoints.append(aisle_point(aisle, front))
        if front_groups and rear_groups:
            last_front_aisle = max(front_groups)
            waypoints.append(aisle_point(last_front_aisle, rear))
        elif rear_groups:
            waypoints.append((depot_x, rear))
        for aisle in sorted(rear_groups, reverse=True):
            waypoints.append(aisle_point(aisle, rear))
            add_stops(rear_groups[aisle])
            waypoints.append(aisle_point(aisle, rear))
        if rear_groups:
            waypoints.extend([(depot_x, rear), (depot_x, float(depot_y))])
        else:
            waypoints.append((depot_x, float(depot_y)))

    compact: list[tuple[float, float]] = []
    for point in waypoints:
        if not compact or point != compact[-1]:
            compact.append(point)
    distance_m = float(sum(abs(x2 - x1) + abs(y2 - y1) for (x1, y1), (x2, y2) in pairwise(compact)))
    levels = [int(graph["level"][index]) for index in ordered]
    timing = time_components(distance_m, levels, sum(sku_quantities.values()), rules)
    stops = [{
        "sku_id": stop_skus[index], "location_id": graph["location_ids"][index],
        "aisle": int(graph["aisle"][index]), "shelf_level": int(graph["level"][index]),
        "quantity": int(sku_quantities[stop_skus[index]]),
    } for index in ordered]
    return {"distance_m": distance_m, "vertices": compact, "stops": stops, **timing}
