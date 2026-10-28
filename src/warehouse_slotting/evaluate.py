"""Held-out route comparison for two layouts that share orders, bins, and rules."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from warehouse_slotting.routing import depot_distance, sequence_stops, time_components, travel_graph


def _assignment_map(assignments: pd.DataFrame) -> dict[str, str]:
    return dict(zip(assignments["sku_id"], assignments["location_id"], strict=True))


def simulate_orders(
    orders: pd.DataFrame,
    assignments: pd.DataFrame,
    graph: dict[str, Any],
    rules: dict[str, Any],
    depot_aisle: int,
    depot_y: float,
    split: str,
    limit: int | None = None,
) -> pd.DataFrame:
    """Replay whole orders with the same nearest-bin rule used for every layout."""
    placed = _assignment_map(assignments)
    subset = orders.loc[orders["split"] == split, ["order_id", "sku_id", "quantity"]]
    order_ids = subset["order_id"].drop_duplicates().sort_values()
    if limit is not None:
        order_ids = order_ids.head(limit)
    subset = subset.loc[subset["order_id"].isin(set(order_ids))]
    from_depot = depot_distance(graph, depot_aisle, depot_y)
    rows = []
    for order_id, frame in subset.groupby("order_id", sort=True):
        quantities = frame.groupby("sku_id")["quantity"].sum()
        indices = [graph["index"][placed[sku_id]] for sku_id in quantities.index]
        ordered, distance_m = sequence_stops(indices, graph["distance"], from_depot, graph["location_ids"])
        levels = [int(graph["level"][index]) for index in ordered]
        timing = time_components(distance_m, levels, int(quantities.sum()), rules)
        rows.append({
            "order_id": order_id,
            "n_stops": len(ordered),
            "quantity": int(quantities.sum()),
            "distance_m": distance_m,
            "walk_s": timing["walk_s"],
            "reach_s": timing["reach_s"],
            "base_s": timing["base_s"],
            "quantity_s": timing["quantity_s"],
            "time_s": timing["time_s"],
        })
    return pd.DataFrame(rows)


def _weighted_share(assigned: pd.DataFrame, locations: pd.DataFrame, weights: pd.Series, column: str) -> float:
    joined = assigned.merge(locations[["location_id", column]], on="location_id")
    joined["weight"] = joined["sku_id"].map(weights).astype(float)
    total = float(joined["weight"].sum())
    if total == 0:
        return 0.0
    return float((joined["weight"] * joined[column].astype(float)).sum() / total)


def placement_snapshot(
    skus: pd.DataFrame,
    locations: pd.DataFrame,
    assignments: pd.DataFrame,
    abc: pd.DataFrame,
    graph: dict[str, Any],
    from_depot: np.ndarray,
    pairs: list[tuple[str, str, int]],
    order_weights: pd.Series,
) -> dict[str, float]:
    """Explain a layout in meters and shares, separate from the surrogate search score."""
    placed = _assignment_map(assignments)
    indices = np.array([graph["index"][placed[sku_id]] for sku_id in abc["sku_id"]])
    frequency = abc.set_index("sku_id")["pick_frequency"]
    a_mask = abc["abc_class"].eq("A").to_numpy()
    a_weights = frequency.loc[abc["sku_id"]].to_numpy(dtype=float)
    a_weights = np.where(a_mask, a_weights, 0.0)
    depot = float(np.dot(a_weights, from_depot[indices]) / a_weights.sum()) if a_weights.sum() else 0.0
    if pairs:
        left = np.array([graph["index"][placed[sku_a]] for sku_a, _, _ in pairs])
        right = np.array([graph["index"][placed[sku_b]] for _, sku_b, _ in pairs])
        pair_w = np.array([count for _, _, count in pairs], dtype=float)
        affinity = float(np.dot(pair_w, graph["distance"][left, right]) / pair_w.sum())
    else:
        affinity = 0.0
    joined = assignments.merge(skus, on="sku_id").merge(locations, on="location_id")
    stock = float((joined["unit_volume_cm3"] * joined["on_hand_qty"]).sum())
    occupied = float(joined["volumetric_capacity_cm3"].sum())
    train_weights = frequency
    return {
        "a_mean_depot_m": depot,
        "affinity_mean_m": affinity,
        "golden_share_train": _weighted_share(assignments, locations, train_weights, "is_golden_zone"),
        "golden_share_test": _weighted_share(assignments, locations, order_weights, "is_golden_zone"),
        "occupied_fill": stock / occupied if occupied else 0.0,
    }


def compare_routes(before: pd.DataFrame, after: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame]:
    """Pair the same orders and keep both gains and regressions."""
    merged = before.merge(after, on="order_id", suffixes=("_before", "_after"))
    delta = merged["distance_m_after"] - merged["distance_m_before"]
    shorter = int((delta < -1e-6).sum())
    longer = int((delta > 1e-6).sum())
    same = int(len(merged) - shorter - longer)
    worst_at = int(delta.idxmax())
    median = float(delta.median())
    typical_at = int((delta - median).abs().idxmin())
    first_at = int(merged["order_id"].astype(str).idxmin()) if False else int(merged.sort_values("order_id").index[0])
    stops = int(merged["n_stops_before"].sum())
    summary = {
        "order_count": len(merged),
        "baseline_mean_distance_m": float(merged["distance_m_before"].mean()),
        "optimized_mean_distance_m": float(merged["distance_m_after"].mean()),
        "baseline_mean_time_s": float(merged["time_s_before"].mean()),
        "optimized_mean_time_s": float(merged["time_s_after"].mean()),
        "baseline_mean_walk_s": float(merged["walk_s_before"].mean()),
        "optimized_mean_walk_s": float(merged["walk_s_after"].mean()),
        "baseline_mean_reach_s": float(merged["reach_s_before"].mean()),
        "optimized_mean_reach_s": float(merged["reach_s_after"].mean()),
        "mean_handling_s": float((merged["base_s_before"] + merged["quantity_s_before"]).mean()),
        "baseline_distance_per_stop_m": float(merged["distance_m_before"].sum() / stops),
        "optimized_distance_per_stop_m": float(merged["distance_m_after"].sum() / stops),
        "orders_shorter": shorter,
        "orders_longer": longer,
        "orders_same": same,
        "median_distance_delta_m": median,
        "worst_order_id": str(merged.loc[worst_at, "order_id"]),
        "worst_increase_m": float(delta.loc[worst_at]),
        "first_order_id": str(merged.loc[first_at, "order_id"]),
        "median_order_id": str(merged.loc[typical_at, "order_id"]),
    }
    table = pd.DataFrame({
        "order_id": merged["order_id"].astype(str),
        "n_stops": merged["n_stops_before"],
        "quantity": merged["quantity_before"],
        "baseline_distance_m": merged["distance_m_before"],
        "optimized_distance_m": merged["distance_m_after"],
        "baseline_walk_s": merged["walk_s_before"],
        "optimized_walk_s": merged["walk_s_after"],
        "baseline_reach_s": merged["reach_s_before"],
        "optimized_reach_s": merged["reach_s_after"],
        "baseline_time_s": merged["time_s_before"],
        "optimized_time_s": merged["time_s_after"],
        "handling_s": merged["base_s_before"] + merged["quantity_s_before"],
    })
    return summary, table.sort_values("order_id").reset_index(drop=True)


def mean_route(
    orders: pd.DataFrame,
    assignments: pd.DataFrame,
    locations: pd.DataFrame,
    warehouse: dict[str, Any],
    rules: dict[str, Any],
    split: str = "test",
    limit: int = 300,
    depot_aisle: int | None = None,
) -> dict[str, float]:
    """Score one layout under a stated desk position. Used by what-if, not by search."""
    graph = travel_graph(locations, warehouse)
    aisle = int(warehouse["depot_aisle"] if depot_aisle is None else depot_aisle)
    simulated = simulate_orders(orders, assignments, graph, rules, aisle, float(warehouse["depot_y_m"]), split, limit)
    return {
        "orders": len(simulated),
        "mean_distance_m": float(simulated["distance_m"].mean()),
        "mean_time_s": float(simulated["time_s"].mean()),
        "mean_walk_s": float(simulated["walk_s"].mean()),
        "mean_reach_s": float(simulated["reach_s"].mean()),
        "mean_handling_s": float((simulated["base_s"] + simulated["quantity_s"]).mean()),
    }
