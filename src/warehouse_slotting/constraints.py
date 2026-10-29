"""Hard-rule eligibility and independent complete assignment validation."""

from __future__ import annotations

from itertools import combinations
from typing import Any

import pandas as pd

from warehouse_slotting.compatibility import (
    effective_category,
    required_pair_clearance,
    required_zone,
)
from warehouse_slotting.synthesize import orientation_capacity


def _physical_clearance(left: pd.Series, right: pd.Series) -> float:
    """Planar edge-to-edge distance between rectangular bin footprints."""
    if left["rack_id"] == right["rack_id"] and left["bay"] == right["bay"]:
        return 0.0
    gap_x = max(
        0.0,
        abs(float(left["x_m"]) - float(right["x_m"]))
        - (float(left["bin_depth_cm"]) + float(right["bin_depth_cm"])) / 200,
    )
    gap_y = max(
        0.0,
        abs(float(left["y_m"]) - float(right["y_m"]))
        - (float(left["bin_width_cm"]) + float(right["bin_width_cm"])) / 200,
    )
    return float((gap_x**2 + gap_y**2) ** 0.5)


def static_candidates(skus: pd.DataFrame, locations: pd.DataFrame, rules: dict[str, Any]) -> dict[str, list[str]]:
    candidates: dict[str, list[str]] = {}
    for _, sku in skus.iterrows():
        allowed = []
        category = effective_category(sku)
        zone = required_zone(sku, rules)
        category_levels = rules.get("category_allowed_levels", {}).get(category)
        for _, location in locations.iterrows():
            if str(location["zone"]).strip().casefold() != zone.casefold():
                continue
            if category_levels is not None and int(location["shelf_level"]) not in category_levels:
                continue
            if sku["unit_weight_kg"] >= rules["heavy_unit_weight_kg"] and location["shelf_level"] not in rules["heavy_allowed_levels"]:
                continue
            if (category == "fragile" or sku.get("handling_type") == "fragile") and location["shelf_level"] in rules["fragile_forbidden_levels"]:
                continue
            packed = orientation_capacity(sku, location, rules["usable_volume_fraction"])
            if packed and sku["unit_weight_kg"] * sku["on_hand_qty"] <= location["bin_max_weight_kg"]:
                allowed.append(location["location_id"])
        candidates[str(sku["sku_id"])] = sorted(allowed)
    return candidates


def validate_assignment(skus: pd.DataFrame, locations: pd.DataFrame, assignments: pd.DataFrame, rules: dict[str, Any]) -> dict[str, Any]:
    """Recompute every hard rule without trusting allocator state."""
    violations: list[dict[str, Any]] = []
    sku_ids = set(skus["sku_id"])
    assigned_skus = assignments["sku_id"].tolist() if "sku_id" in assignments else []
    assigned_locations = assignments["location_id"].tolist() if "location_id" in assignments else []
    for sku_id in sorted(sku_ids - set(assigned_skus)):
        violations.append({"code": "MISSING_SKU", "sku_ids": [sku_id], "message": "SKU is unassigned"})
    if len(assigned_skus) != len(set(assigned_skus)):
        violations.append({"code": "DUPLICATE_SKU", "message": "A SKU has multiple assignments"})
    if len(assigned_locations) != len(set(assigned_locations)):
        violations.append({"code": "DUPLICATE_LOCATION", "message": "A bin has multiple SKUs"})
    joined = assignments.merge(skus, on="sku_id", how="left").merge(locations, on="location_id", how="left", suffixes=("_sku", "_location"))
    for _, row in joined.iterrows():
        if pd.isna(row.get("width_cm")) or pd.isna(row.get("x_m")):
            violations.append({"code": "UNKNOWN_ID", "message": "Assignment contains unknown ID"})
            continue
        packed = orientation_capacity(row, row, rules["usable_volume_fraction"])
        load = row["unit_weight_kg"] * row["on_hand_qty"]
        category = effective_category(row)
        zone = required_zone(row, rules)
        if not packed:
            violations.append({"code": "PACKING", "sku_ids": [row["sku_id"]], "location_ids": [row["location_id"]], "message": "Stock does not fit bin"})
        if load > row["bin_max_weight_kg"]:
            violations.append({"code": "BIN_WEIGHT", "sku_ids": [row["sku_id"]], "message": "Bin load exceeded"})
        if str(row["zone"]).strip().casefold() != zone.casefold():
            if category == "hazardous":
                code, message = "HAZARD_ZONE", "Hazardous product is outside the isolation zone"
            elif row["zone"] == rules.get("hazardous_zone", "HAZMAT"):
                code, message = "STANDARD_IN_HAZMAT", "Non-hazardous product is in the isolation zone"
            else:
                code, message = "CATEGORY_ZONE", f"{category.title()} product requires the {zone} zone"
            violations.append({
                "code": code,
                "sku_ids": [row["sku_id"]],
                "location_ids": [row["location_id"]],
                "category": category,
                "required_zone": zone,
                "actual_zone": row["zone"],
                "message": message,
            })
        category_levels = rules.get("category_allowed_levels", {}).get(category)
        if category_levels is not None and int(row["shelf_level"]) not in category_levels:
            violations.append({
                "code": "CATEGORY_LEVEL",
                "sku_ids": [row["sku_id"]],
                "location_ids": [row["location_id"]],
                "category": category,
                "message": f"{category.title()} product is on a disallowed shelf level",
            })
        if row["unit_weight_kg"] >= rules["heavy_unit_weight_kg"] and row["shelf_level"] not in rules["heavy_allowed_levels"]:
            violations.append({"code": "HEAVY_HEIGHT", "sku_ids": [row["sku_id"]], "message": "Heavy SKU at forbidden level"})
        if (category == "fragile" or row["handling_type"] == "fragile") and row["shelf_level"] in rules["fragile_forbidden_levels"]:
            violations.append({"code": "FRAGILE_RISK", "sku_ids": [row["sku_id"]], "message": "Fragile SKU at risk level"})
    if not joined.empty:
        joined["stock_load_kg"] = joined["unit_weight_kg"] * joined["on_hand_qty"]
        for key, capacity in [("shelf_id", "shelf_max_weight_kg"), ("rack_id", "rack_max_weight_kg")]:
            loads = joined.groupby(key)["stock_load_kg"].sum()
            limits = joined.groupby(key)[capacity].first()
            for identifier, load in loads.items():
                if load > limits[identifier] + 1e-9:
                    violations.append({"code": f"{key.upper()}_WEIGHT", "location_ids": [identifier], "measured": float(load), "limit": float(limits[identifier]), "message": "Structural load exceeded"})
        for (_, left), (_, right) in combinations(joined.iterrows(), 2):
            left_category = effective_category(left)
            right_category = effective_category(right)
            minimum = required_pair_clearance(left_category, right_category, rules)
            if minimum <= 0:
                continue
            measured = _physical_clearance(left, right)
            if measured + 1e-9 < minimum:
                hazardous_pair = "hazardous" in {left_category, right_category}
                violations.append({
                    "code": "HAZARD_CLEARANCE" if hazardous_pair else "CATEGORY_SEPARATION",
                    "sku_ids": [left["sku_id"], right["sku_id"]],
                    "location_ids": [left["location_id"], right["location_id"]],
                    "categories": [left_category, right_category],
                    "measured": measured,
                    "limit": minimum,
                    "message": f"{left_category.title()} and {right_category.title()} products are too close",
                })
    return {"is_feasible": not violations, "violation_count": len(violations), "violations": violations}

