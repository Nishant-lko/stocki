"""A random forest that classifies which bin each product belongs in.

It distills a validated optimized layout: product attributes plus bin attributes
predict whether a legal bin is the chosen one. Its own layout proposal is priced
on the same held-out orders as every other layout, and an independent feasibility
check decides whether it may be shown at all.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from warehouse_slotting.constraints import validate_assignment
from warehouse_slotting.forest import Forest, fit_forest

FEATURES = [
    "pick_frequency", "units_sold", "unit_weight_kg", "unit_volume_cm3", "on_hand_qty",
    "is_fragile", "is_hazmat", "is_heavy", "bin_depot_m", "shelf_level", "is_golden_zone",
    "bin_volume_cm3", "bin_is_hazmat_zone", "aisle_number",
]
FEATURE_READING = {
    "pick_frequency": "how often the product is ordered",
    "units_sold": "how many units it ships",
    "unit_weight_kg": "how heavy one unit is",
    "unit_volume_cm3": "how big one unit is",
    "on_hand_qty": "how many units we stock",
    "is_fragile": "whether it is fragile",
    "is_hazmat": "whether it is hazardous",
    "is_heavy": "whether it counts as heavy",
    "bin_depot_m": "how far the bin is from the packing desk",
    "shelf_level": "which shelf height the bin is on",
    "is_golden_zone": "whether the bin is at a back-friendly height",
    "bin_volume_cm3": "how big the bin is",
    "bin_is_hazmat_zone": "whether the bin is in the isolation aisle",
    "aisle_number": "which aisle the bin sits in",
}
FEATURE_NAMES = list(FEATURE_READING.values())


def pair_matrix(
    skus: pd.DataFrame,
    locations: pd.DataFrame,
    abc: pd.DataFrame,
    candidates: dict[str, list[str]],
    layout: pd.DataFrame,
    from_depot: np.ndarray,
) -> tuple[pd.DataFrame, np.ndarray]:
    """One row per (product, legal bin) pair; the label is the chosen bin."""
    location = locations.set_index("location_id")
    chosen_by = dict(zip(layout["sku_id"], layout["location_id"], strict=True))
    demand = abc.set_index("sku_id")
    index_of_location = {item: position for position, item in enumerate(locations["location_id"])}
    rows = []
    labels = []
    for sku_row in skus.itertuples(index=False):
        chosen_location = chosen_by.get(sku_row.sku_id)
        demand_row = demand.loc[sku_row.sku_id]
        is_fragile = float(sku_row.handling_type == "fragile")
        is_hazmat = float(sku_row.hazard_class != "none")
        is_heavy = float(sku_row.unit_weight_kg >= 8.0)
        for location_id in candidates[sku_row.sku_id]:
            bin_row = location.loc[location_id]
            rows.append({
                "sku_id": sku_row.sku_id, "location_id": location_id,
                "pick_frequency": float(demand_row["pick_frequency"]),
                "units_sold": float(demand_row["units_sold"]),
                "unit_weight_kg": float(sku_row.unit_weight_kg),
                "unit_volume_cm3": float(sku_row.unit_volume_cm3),
                "on_hand_qty": float(sku_row.on_hand_qty),
                "is_fragile": is_fragile, "is_hazmat": is_hazmat, "is_heavy": is_heavy,
                "bin_depot_m": float(from_depot[index_of_location[location_id]]),
                "shelf_level": int(bin_row["shelf_level"]),
                "is_golden_zone": float(bin_row["is_golden_zone"]),
                "bin_volume_cm3": float(bin_row["volumetric_capacity_cm3"]),
                "bin_is_hazmat_zone": float(bin_row["zone"] != "STANDARD"),
                "aisle_number": int(bin_row["aisle_number"]),
            })
            labels.append(float(location_id == chosen_location))
    return pd.DataFrame(rows), np.array(labels)


def train_policy(
    skus: pd.DataFrame,
    locations: pd.DataFrame,
    abc: pd.DataFrame,
    candidates: dict[str, list[str]],
    layout: pd.DataFrame,
    from_depot: np.ndarray,
    seed: int,
) -> dict[str, Any]:
    """Fit the classifier and report honest holdout accuracy at ranking the chosen bin."""
    pairs, labels = pair_matrix(skus, locations, abc, candidates, layout, from_depot)
    holdout_skus = set(pairs["sku_id"].drop_duplicates().sample(frac=0.2, random_state=seed))
    holdout_mask = pairs["sku_id"].isin(holdout_skus).to_numpy()
    chosen_mask = labels == 1.0
    training_mask = chosen_mask | (~holdout_mask)
    model = fit_forest(pairs.loc[training_mask, FEATURES].to_numpy(dtype=float), labels[training_mask], seed)
    prediction = model.predict(pairs[FEATURES].to_numpy(dtype=float))
    ranks = holdout_rank(pairs, prediction, chosen_mask, holdout_mask)
    top1 = float(np.mean([rank == 0 for rank in ranks])) if ranks else 0.0
    top3 = float(np.mean([rank < 3 for rank in ranks])) if ranks else 0.0
    return {
        "model": model,
        "pairs": pairs,
        "prediction": prediction,
        "top1_accuracy": top1,
        "top3_accuracy": top3,
        "holdout_skus": len(ranks),
        "feature_importance": {name: round(float(value), 4) for name, value in zip(FEATURE_NAMES, model.feature_importance, strict=True)},
        "training_pairs": int(training_mask.sum()),
    }


def holdout_rank(pairs: pd.DataFrame, prediction: np.ndarray, chosen_mask: np.ndarray, holdout_mask: np.ndarray) -> list[int]:
    """Rank of the chosen bin among that product's legal bins, for held-out products."""
    ranks = []
    flagged = pairs.index[pairs["sku_id"].isin(pairs.loc[holdout_mask, "sku_id"])]
    for sku_id in sorted(pairs.loc[flagged, "sku_id"].unique()):
        positions = pairs.index[(pairs["sku_id"] == sku_id)].to_numpy()
        probabilities = prediction[positions]
        order = np.argsort(-probabilities, kind="stable")
        chosen_within = np.flatnonzero(chosen_mask[positions])
        ranks.append(int(np.flatnonzero(order == chosen_within[0])[0]) if chosen_within.size else len(order))
    return ranks


def choose_ml_layout(
    model: Forest,
    pairs: pd.DataFrame,
    prediction: np.ndarray,
    skus: pd.DataFrame,
    locations: pd.DataFrame,
    abc: pd.DataFrame,
    rules: dict[str, Any],
    seed: int,
) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    """The classifier alone places every product. Rack limits and legality still hold."""
    ranked: dict[str, list[tuple[float, str]]] = {}
    for position, row in enumerate(pairs.itertuples(index=False)):
        ranked.setdefault(row.sku_id, []).append((float(prediction[position]), row.location_id))
    order = skus.merge(abc[["sku_id", "pick_frequency"]], on="sku_id").sort_values(
        ["pick_frequency", "sku_id"], ascending=[False, True], kind="stable"
    )
    rack_cap = locations.groupby("rack_id")["rack_max_weight_kg"].first().to_dict()
    rack_load: dict[str, float] = {}
    occupied: set[str] = set()
    chosen: dict[str, str] = {}
    views: dict[str, list[dict[str, object]]] = {}
    for sku_row in order.itertuples(index=False):
        sku_id = sku_row.sku_id
        load = float(sku_row.unit_weight_kg * sku_row.on_hand_qty)
        options = sorted(ranked[sku_id], key=lambda item: (-item[0], item[1]))
        picks = []
        for probability, location_id in options:
            if location_id in occupied:
                state = "occupied"
            else:
                rack_id = locations.loc[locations["location_id"] == location_id, "rack_id"].iloc[0]
                if rack_load.get(rack_id, 0.0) + load > rack_cap[rack_id] + 1e-9:
                    state = "rack full"
                else:
                    state = "available"
            picks.append({"location_id": location_id, "probability": round(probability, 4), "state": state})
            if state == "available" and sku_id not in chosen:
                occupied.add(location_id)
                rack_load[rack_id] = rack_load.get(rack_id, 0.0) + load
                chosen[sku_id] = location_id
        views[sku_id] = picks[:8]
    if len(chosen) != len(skus):
        return None, {"enabled": False, "reason": f"the classifier could only home {len(chosen)} of {len(skus)} products"}
    layout = pd.DataFrame({
        "sku_id": skus["sku_id"],
        "location_id": skus["sku_id"].map(chosen),
        "method": "random_forest_classifier",
        "seed": seed,
    })
    return layout.sort_values("sku_id").reset_index(drop=True), {
        "enabled": True,
        "views": {sku_id: picks for sku_id, picks in views.items()},
    }


def validate_layout(skus: pd.DataFrame, locations: pd.DataFrame, layout: pd.DataFrame, rules: dict[str, Any]) -> dict[str, Any]:
    return validate_assignment(skus, locations, layout, rules)
