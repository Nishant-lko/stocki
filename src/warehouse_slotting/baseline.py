"""Demand-blind feasible baseline allocation."""

from __future__ import annotations

import random

import pandas as pd

from warehouse_slotting.constraints import static_candidates, validate_assignment


def allocate_baseline(
    skus: pd.DataFrame, locations: pd.DataFrame, rules: dict, seed: int, restarts: int
) -> pd.DataFrame:
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
    orders.append(
        sorted(
            sku_lookup.index,
            key=lambda sku: (len(candidates[sku]), -sku_lookup.loc[sku, "unit_volume_cm3"], sku),
        )
    )
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
                if (
                    shelf_loads.get(location["shelf_id"], 0.0) + load
                    > location["shelf_max_weight_kg"]
                ):
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
            rows.append(
                {
                    "sku_id": sku_id,
                    "location_id": chosen.name,
                    "method": "random" if attempt < restarts else "most_constrained",
                    "seed": seed + attempt,
                }
            )
        assignments = pd.DataFrame(rows)
        if (
            len(assignments) == len(skus)
            and validate_assignment(skus, locations, assignments, rules)["is_feasible"]
        ):
            return assignments.sort_values("sku_id").reset_index(drop=True)
    raise RuntimeError(
        "Baseline allocation exhausted all attempts without a feasible complete layout"
    )


def allocate_frequency_sort(
    skus: pd.DataFrame,
    locations: pd.DataFrame,
    abc: pd.DataFrame,
    rules: dict,
    graph: dict,
    distances: list[float],
) -> pd.DataFrame:
    """Build a transparent nearest-legal-bin comparator, fastest SKU first."""
    candidates = static_candidates(skus, locations, rules)
    location_rows = locations.set_index("location_id")
    sku_rows = skus.set_index("sku_id")
    frequencies = abc.set_index("sku_id")["pick_frequency"]
    ordered_skus = sorted(sku_rows.index, key=lambda sku: (-float(frequencies.loc[sku]), str(sku)))
    used: set[str] = set()
    shelf_load: dict[str, float] = {}
    rack_load: dict[str, float] = {}
    placements = []
    for sku_id in ordered_skus:
        sku = sku_rows.loc[sku_id]
        load = float(sku["unit_weight_kg"] * sku["on_hand_qty"])
        options = sorted(
            candidates.get(str(sku_id), []),
            key=lambda location_id: (
                float(distances[graph["index"][location_id]]),
                str(location_id),
            ),
        )
        chosen = None
        for location_id in options:
            if location_id in used:
                continue
            location = location_rows.loc[location_id]
            if (
                shelf_load.get(location["shelf_id"], 0.0) + load
                > float(location["shelf_max_weight_kg"]) + 1e-9
            ):
                continue
            if (
                rack_load.get(location["rack_id"], 0.0) + load
                > float(location["rack_max_weight_kg"]) + 1e-9
            ):
                continue
            chosen = location
            break
        if chosen is None:
            raise RuntimeError("The frequency-sort comparator could not fill every legal bin")
        location_id = str(chosen.name)
        used.add(location_id)
        shelf_load[chosen["shelf_id"]] = shelf_load.get(chosen["shelf_id"], 0.0) + load
        rack_load[chosen["rack_id"]] = rack_load.get(chosen["rack_id"], 0.0) + load
        placements.append({"sku_id": str(sku_id), "location_id": location_id})
    assignment = pd.DataFrame(placements)
    validation = validate_assignment(skus, locations, assignment, rules)
    if not validation["is_feasible"]:
        raise RuntimeError("The frequency-sort comparator failed the independent safety check")
    assignment["method"] = "frequency_sort"
    return assignment.sort_values("sku_id").reset_index(drop=True)
