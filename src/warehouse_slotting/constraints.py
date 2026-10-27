"""Hard-rule eligibility and independent complete assignment validation."""

from __future__ import annotations

from itertools import combinations
from typing import Any

import pandas as pd

from warehouse_slotting.synthesize import orientation_capacity


def _physical_clearance(left: pd.Series, right: pd.Series) -> float:
    """Planar clearance between bin footprints; vertically stacked bins are adjacent."""
    if left["rack_id"] == right["rack_id"] and left["bay"] == right["bay"]:
        return 0.0
    return float(((left["x_m"] - right["x_m"]) ** 2 + (left["y_m"] - right["y_m"]) ** 2) ** 0.5)


def static_candidates(skus: pd.DataFrame, locations: pd.DataFrame, rules: dict[str, Any]) -> dict[str, list[str]]:
    candidates: dict[str, list[str]] = {}
    for _, sku in skus.iterrows():
        allowed = []
        for _, location in locations.iterrows():
            is_hazmat = sku["hazard_class"] != "none"
            if is_hazmat != (location["zone"] == rules["hazardous_zone"]):
                continue
            if sku["unit_weight_kg"] >= rules["heavy_unit_weight_kg"] and location["shelf_level"] not in rules["heavy_allowed_levels"]:
                continue
            if sku["handling_type"] == "fragile" and location["shelf_level"] in rules["fragile_forbidden_levels"]:
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
        if not packed:
            violations.append({"code": "PACKING", "sku_ids": [row["sku_id"]], "location_ids": [row["location_id"]], "message": "Stock does not fit bin"})
        if load > row["bin_max_weight_kg"]:
            violations.append({"code": "BIN_WEIGHT", "sku_ids": [row["sku_id"]], "message": "Bin load exceeded"})
        if row["hazard_class"] != "none" and row["zone"] != rules["hazardous_zone"]:
            violations.append({"code": "HAZARD_ZONE", "sku_ids": [row["sku_id"]], "message": "Hazmat outside isolation"})
        if row["hazard_class"] == "none" and row["zone"] == rules["hazardous_zone"]:
            violations.append({"code": "STANDARD_IN_HAZMAT", "sku_ids": [row["sku_id"]], "message": "Standard item in isolation"})
        if row["unit_weight_kg"] >= rules["heavy_unit_weight_kg"] and row["shelf_level"] not in rules["heavy_allowed_levels"]:
            violations.append({"code": "HEAVY_HEIGHT", "sku_ids": [row["sku_id"]], "message": "Heavy SKU at forbidden level"})
        if row["handling_type"] == "fragile" and row["shelf_level"] in rules["fragile_forbidden_levels"]:
            violations.append({"code": "FRAGILE_RISK", "sku_ids": [row["sku_id"]], "message": "Fragile SKU at risk level"})
    if not joined.empty:
        joined["stock_load_kg"] = joined["unit_weight_kg"] * joined["on_hand_qty"]
        for key, capacity in [("shelf_id", "shelf_max_weight_kg"), ("rack_id", "rack_max_weight_kg")]:
            loads = joined.groupby(key)["stock_load_kg"].sum()
            limits = joined.groupby(key)[capacity].first()
            for identifier, load in loads.items():
                if load > limits[identifier] + 1e-9:
                    violations.append({"code": f"{key.upper()}_WEIGHT", "location_ids": [identifier], "measured": float(load), "limit": float(limits[identifier]), "message": "Structural load exceeded"})
        hazardous = joined.loc[joined["hazard_class"] != "none"]
        standard = joined.loc[joined["hazard_class"] == "none"]
        for (_, hz), (_, item) in combinations(list(hazardous.iterrows()) + list(standard.iterrows()), 2):
            if (hz["hazard_class"] != "none") == (item["hazard_class"] != "none"):
                continue
            if _physical_clearance(hz, item) < rules["hazard_min_clearance_m"]:
                violations.append({"code": "HAZARD_CLEARANCE", "sku_ids": [hz["sku_id"], item["sku_id"]], "message": "Hazmat clearance is below configured minimum"})
    return {"is_feasible": not violations, "violation_count": len(violations), "violations": violations}

