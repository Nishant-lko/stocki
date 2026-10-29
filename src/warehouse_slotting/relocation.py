"""Build executable, safety-checked steps between two single-SKU layouts."""

from __future__ import annotations

import pandas as pd

from warehouse_slotting.constraints import static_candidates, validate_assignment


def safe_relocation_sequence(
    skus: pd.DataFrame,
    locations: pd.DataFrame,
    current: pd.DataFrame,
    target: pd.DataFrame,
    abc: pd.DataFrame,
    rules: dict,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Find a sequence whose every intermediate assignment passes the full verifier."""
    candidate_bins = static_candidates(skus, locations, rules)
    eligible = {sku_id: set(bins) for sku_id, bins in candidate_bins.items()}
    frequency = abc.set_index("sku_id")["pick_frequency"].to_dict()
    target_map = dict(zip(target["sku_id"].astype(str), target["location_id"].astype(str), strict=True))
    work = current[["sku_id", "location_id"]].copy()
    work["sku_id"] = work["sku_id"].astype(str)
    work["location_id"] = work["location_id"].astype(str)
    if set(work["sku_id"]) != set(target_map):
        return pd.DataFrame(), {"executable": False, "reason": "The two layouts do not contain the same SKUs."}
    if not validate_assignment(skus, locations, work, rules)["is_feasible"]:
        return pd.DataFrame(), {"executable": False, "reason": "The starting layout fails the safety verifier."}
    if not validate_assignment(skus, locations, target, rules)["is_feasible"]:
        return pd.DataFrame(), {"executable": False, "reason": "The target layout fails the safety verifier."}

    steps: list[dict[str, object]] = []
    all_target_bins = set(target_map.values())
    max_actions = max(1, len(work) * 4)

    def occupancy() -> dict[str, str]:
        return dict(zip(work["location_id"], work["sku_id"], strict=True))

    def apply_move(sku_id: str, destination: str, operation: str) -> bool:
        nonlocal work
        source = str(work.loc[work["sku_id"] == sku_id, "location_id"].iloc[0])
        trial = work.copy()
        trial.loc[trial["sku_id"] == sku_id, "location_id"] = destination
        if not validate_assignment(skus, locations, trial, rules)["is_feasible"]:
            return False
        steps.append({
            "step": len(steps) + 1, "operation": operation, "sku_id": sku_id,
            "from_location": source, "to_location": destination,
            "other_sku_id": "", "other_from": "", "other_to": "",
            "product_moves": 1, "pick_frequency": int(frequency.get(sku_id, 0)),
        })
        work = trial
        return True

    while any(
        str(row.location_id) != target_map[str(row.sku_id)]
        for row in work.itertuples()
    ):
        if len(steps) >= max_actions:
            return pd.DataFrame(steps), {
                "executable": False,
                "reason": "A safe move cycle exceeded the planning limit.",
                "completed_actions": len(steps),
            }
        occupied = occupancy()
        mismatch = [
            sku_id for sku_id, location_id in zip(work["sku_id"], work["location_id"], strict=True)
            if location_id != target_map[sku_id]
        ]
        mismatch.sort(key=lambda sku_id: (-int(frequency.get(sku_id, 0)), sku_id))

        advanced = False
        # First use destinations that are currently empty; each candidate is independently verified.
        for sku_id in mismatch:
            destination = target_map[sku_id]
            if destination not in occupied and apply_move(sku_id, destination, "Move"):
                advanced = True
                break
        if advanced:
            continue

        # Break cycles with an empty, legal staging bin. Every physical relocation
        # is a separate verified task; a swap is never treated as one atomic action.
        staging_done = False
        for sku_id in mismatch:
            for buffer in candidate_bins.get(sku_id, []):
                if buffer in occupied or buffer in all_target_bins:
                    continue
                if apply_move(sku_id, buffer, "Stage"):
                    staging_done = True
                    break
            if staging_done:
                break
        if not staging_done:
            return pd.DataFrame(steps), {
                "executable": False,
                "reason": "No rule-compliant move, swap, or empty staging bin was available.",
                "completed_actions": len(steps),
            }

    completed = all(
        str(row.location_id) == target_map[str(row.sku_id)] for row in work.itertuples()
    )
    return pd.DataFrame(steps), {
        "executable": completed,
        "reason": "Every action was independently checked; the final assignment matches the published plan."
        if completed else "The generated sequence did not reach the target assignment.",
        "actions": len(steps),
        "product_moves": int(sum(int(step["product_moves"]) for step in steps)),
        "staging_actions": int(sum(step["operation"] == "Stage" for step in steps)),
        "all_intermediate_layouts_feasible": True,
    }
