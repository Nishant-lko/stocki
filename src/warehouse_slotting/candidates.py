"""Product-level candidate ranking and readable rule checks for the dashboard."""

from __future__ import annotations

from typing import Any

import pandas as pd

from warehouse_slotting.routing import depot_distance, travel_graph
from warehouse_slotting.synthesize import orientation_capacity


def product_rule_results(sku: pd.Series, location: pd.Series, rules: dict[str, Any]) -> dict[str, Any]:
    """Describe the existing static eligibility rules for one product/bin pair."""
    fit = orientation_capacity(sku, location, rules["usable_volume_fraction"])
    load = float(sku["unit_weight_kg"]) * int(sku["on_hand_qty"])
    hazard_ok = (sku["hazard_class"] != "none") == (location["zone"] == rules["hazardous_zone"])
    weight_ok = load <= float(location["bin_max_weight_kg"])
    heavy_ok = not (float(sku["unit_weight_kg"]) >= rules["heavy_unit_weight_kg"] and int(location["shelf_level"]) not in rules["heavy_allowed_levels"])
    fragile_ok = not (sku["handling_type"] == "fragile" and int(location["shelf_level"]) in rules["fragile_forbidden_levels"])
    failures = []
    if fit is None:
        failures.append("Stock does not fit the bin under the modeled grid packing rule.")
    if not weight_ok:
        failures.append("Stock load exceeds the bin weight limit.")
    if not hazard_ok:
        failures.append("Product and bin are in different hazard zones.")
    if not heavy_ok:
        failures.append("Heavy products are restricted to lower shelf levels.")
    if not fragile_ok:
        failures.append("Fragile products cannot use the top shelf.")
    return {
        "fit": fit is not None, "fit_capacity": fit[0] if fit else None,
        "load_kg": load, "bin_limit_kg": float(location["bin_max_weight_kg"]),
        "weight_ok": weight_ok, "hazard_ok": hazard_ok, "heavy_ok": heavy_ok,
        "fragile_ok": fragile_ok, "eligible": not failures, "reasons": failures,
    }


def ranked_product_candidates(
    sku: pd.Series,
    locations: pd.DataFrame,
    rules: dict[str, Any],
    warehouse: dict[str, Any],
    pick_frequency: float,
    limit: int = 5,
) -> pd.DataFrame:
    """Rank only bins allowed by the same hard checks as static_candidates.

    Ranking is a product-specific heuristic: desk distance weighted by observed pick
    frequency, modeled reach penalty, then a small preference for smaller bin volume.
    It is a short list for inspection, not an assignment or a second optimizer.
    """
    graph = travel_graph(locations, warehouse)
    distances = depot_distance(graph, int(warehouse["depot_aisle"]), float(warehouse["depot_y_m"]))
    reach = {int(level): float(seconds) for level, seconds in rules["reach_penalty_seconds"].items()}
    rows = []
    for index, location in locations.reset_index(drop=True).iterrows():
        check = product_rule_results(sku, location, rules)
        if not check["eligible"]:
            continue
        distance = float(distances[index])
        reach_s = reach[int(location["shelf_level"])]
        score = float(pick_frequency) * distance + reach_s + float(location["volumetric_capacity_cm3"]) / 1_000_000
        rows.append({**location.to_dict(), **check, "desk_distance_m": distance,
                     "reach_penalty_s": reach_s, "rank_score": score})
    return pd.DataFrame(rows).sort_values(
        ["rank_score", "desk_distance_m", "location_id"], ascending=True
    ).head(max(0, int(limit))).reset_index(drop=True) if rows else pd.DataFrame()
