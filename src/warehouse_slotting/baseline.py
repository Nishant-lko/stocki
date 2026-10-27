"""Demand-blind feasible baseline allocation."""

from __future__ import annotations

import random

import pandas as pd

from warehouse_slotting.constraints import static_candidates, validate_assignment


def allocate_baseline(skus: pd.DataFrame, locations: pd.DataFrame, rules: dict, seed: int, restarts: int) -> pd.DataFrame:
    """Assign each SKU once with seeded random restarts and an MCF fallback."""
    candidates = static_candidates(skus, locations, rules)
    missing = sorted(sku for sku, options in candidates.items() if not options)
    if missing:
        raise ValueError(f"No statically eligible bin for: {missing}")
    sku_lookup = skus.set_index("sku_id")
    location_lookup = locations.set_index("location_id")
    orders = []
    rng = random.Random(seed)
    for _ in range(restarts):
        order = list(sku_lookup.index)
        rng.shuffle(order)
        orders.append(order)
    orders.append(sorted(sku_lookup.index, key=lambda sku: (len(candidates[sku]), -sku_lookup.loc[sku, "unit_volume_cm3"], sku)))
    for attempt, order in enumerate(orders):
        rng = random.Random(seed + attempt)
        used: set[str] = set()
        shelf_loads: dict[str, float] = {}
        rack_loads: dict[str, float] = {}
        rows = []
        for sku_id in order:
            sku = sku_lookup.loc[sku_id]
            options = list(candidates[sku_id])
            rng.shuffle(options)
            load = float(sku["unit_weight_kg"] * sku["on_hand_qty"])
            chosen = None
            for location_id in options:
                if location_id in used:
                    continue
                location = location_lookup.loc[location_id]
                if shelf_loads.get(location["shelf_id"], 0.0) + load > location["shelf_max_weight_kg"]:
                    continue
                if rack_loads.get(location["rack_id"], 0.0) + load > location["rack_max_weight_kg"]:
                    continue
                chosen = location
                break
            if chosen is None:
                break
            used.add(chosen.name)
            shelf_loads[chosen["shelf_id"]] = shelf_loads.get(chosen["shelf_id"], 0.0) + load
            rack_loads[chosen["rack_id"]] = rack_loads.get(chosen["rack_id"], 0.0) + load
            rows.append({"sku_id": sku_id, "location_id": chosen.name, "method": "random" if attempt < restarts else "most_constrained", "seed": seed + attempt})
        assignments = pd.DataFrame(rows)
        if len(assignments) == len(skus) and validate_assignment(skus, locations, assignments, rules)["is_feasible"]:
            return assignments.sort_values("sku_id").reset_index(drop=True)
    raise RuntimeError("Baseline allocation exhausted all attempts without a feasible complete layout")

