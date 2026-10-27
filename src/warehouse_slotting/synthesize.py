"""Deterministic synthetic SKU physical master and parallel-aisle warehouse generator."""

from __future__ import annotations

from itertools import permutations

import numpy as np
import pandas as pd


def orientation_capacity(sku: pd.Series, location: pd.Series, usable_volume_fraction: float) -> tuple[int, str] | None:
    """Return best conservative homogeneous-grid capacity and orientation."""
    dimensions = (float(sku["width_cm"]), float(sku["height_cm"]), float(sku["depth_cm"]))
    bin_dimensions = (float(location["bin_width_cm"]), float(location["bin_height_cm"]), float(location["bin_depth_cm"]))
    allowed = sku["allowed_orientations"].split(";")
    best: tuple[int, str] | None = None
    for orientation in permutations(range(3)):
        name = "".join(str(axis) for axis in orientation)
        if name not in allowed:
            continue
        oriented = tuple(dimensions[index] for index in orientation)
        counts = [int(bin_dimension // dimension) for bin_dimension, dimension in zip(bin_dimensions, oriented)]
        if sku["stackable"] == 0:
            counts[1] = min(counts[1], 1)
        capacity = int(np.prod(counts))
        volume_ok = sku["unit_volume_cm3"] * sku["on_hand_qty"] <= location["volumetric_capacity_cm3"] * usable_volume_fraction
        if capacity >= int(sku["on_hand_qty"]) and volume_ok and (best is None or capacity > best[0]):
            best = (capacity, name)
    return best


def generate_skus(sku_ids: list[str], seed: int) -> pd.DataFrame:
    """Generate demand-independent physical attributes from a stable master seed."""
    rng = np.random.default_rng(seed)
    categories = rng.choice(["standard", "fragile", "hazardous"], len(sku_ids), p=[0.72, 0.18, 0.10])
    rows = []
    for sku_id, category in zip(sorted(sku_ids), categories):
        width, height, depth = rng.integers(8, 25, size=3)
        if category == "hazardous":
            width, height, depth = rng.integers(8, 18, size=3)
        volume = int(width * height * depth)
        unit_weight = round(max(0.15, volume / 1300 * rng.uniform(0.4, 1.5)), 2)
        if rng.random() < 0.08:
            unit_weight = round(unit_weight + rng.uniform(7, 13), 2)
        fragile = category == "fragile"
        rows.append({
            "sku_id": sku_id, "description": f"Synthetic item {sku_id}", "width_cm": int(width),
            "height_cm": int(height), "depth_cm": int(depth), "unit_volume_cm3": volume,
            "unit_weight_kg": unit_weight, "category": category,
            "hazard_class": "isolated" if category == "hazardous" else "none",
            "handling_type": "fragile" if fragile else ("hazmat" if category == "hazardous" else "normal"),
            "allowed_orientations": "012" if fragile else "012;021;102;120;201;210",
            "stackable": 0 if fragile else 1, "on_hand_qty": int(rng.integers(2, 13)),
        })
    return pd.DataFrame(rows)


def generate_locations(config: dict) -> pd.DataFrame:
    """Generate a fixed parallel-aisle topology with standard and hazmat bins."""
    warehouse = config["warehouse"]
    rules = config["rules"]
    rows = []
    for aisle in range(warehouse["aisle_count"]):
        for rack_side in range(warehouse["racks_per_aisle"]):
            for bay in range(warehouse["bays_per_rack"]):
                for level in range(warehouse["levels_per_bay"]):
                    is_hazmat = aisle == warehouse["aisle_count"] - 1
                    is_small = (bay + level) % 3 == 0
                    width, height, depth = (60, 50, 50) if is_small else (90, 75, 75)
                    x = aisle * warehouse["aisle_spacing_m"] + (0.45 if rack_side else -0.45)
                    y = (bay + 0.5) * warehouse["bay_pitch_m"]
                    volume = width * height * depth
                    shelf_id = f"A{aisle:02d}-R{rack_side}-B{bay:02d}-L{level}"
                    rack_id = f"A{aisle:02d}-R{rack_side}"
                    rows.append({
                        "location_id": f"{shelf_id}-BIN", "zone": rules["hazardous_zone"] if is_hazmat else "STANDARD",
                        "aisle_number": aisle, "rack_id": rack_id, "shelf_id": shelf_id, "bay": bay,
                        "shelf_level": level, "x_m": x, "y_m": y, "z_m": level * 0.55,
                        "bin_width_cm": width, "bin_height_cm": height, "bin_depth_cm": depth,
                        "volumetric_capacity_cm3": volume, "bin_max_weight_kg": 250.0,
                        "shelf_max_weight_kg": 250.0, "rack_max_weight_kg": 3000.0,
                        "is_golden_zone": level in rules["golden_zone_levels"], "risk_zone": level in rules["high_risk_levels"],
                    })
    return pd.DataFrame(rows)

