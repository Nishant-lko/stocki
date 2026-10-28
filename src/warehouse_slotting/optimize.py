"""Baseline-seeded feasible relocation and swap search."""

from __future__ import annotations

import random
import time
from typing import Any

import numpy as np
import pandas as pd

from warehouse_slotting.constraints import static_candidates, validate_assignment
from warehouse_slotting.routing import depot_distance, travel_graph


def supported_pairs(affinity: pd.DataFrame, minimum: int, neighbors: int) -> list[tuple[str, str, int]]:
    """Keep frequent basket pairs, limited to the strongest neighbors of each product."""
    if affinity.empty:
        return []
    kept = affinity.loc[affinity["cooccurrence"] >= minimum]
    adjacent: dict[str, list[tuple[str, int]]] = {}
    for row in kept.itertuples(index=False):
        adjacent.setdefault(row.sku_a, []).append((row.sku_b, int(row.cooccurrence)))
        adjacent.setdefault(row.sku_b, []).append((row.sku_a, int(row.cooccurrence)))
    pairs: dict[tuple[str, str], int] = {}
    for sku_id, items in adjacent.items():
        ranked = sorted(items, key=lambda item: (-item[1], item[0]))
        for other, count in ranked[:neighbors]:
            key = tuple(sorted((sku_id, other)))
            pairs[key] = count
    return [(left, right, count) for (left, right), count in sorted(pairs.items())]


def _components(
    assigned: np.ndarray,
    frequency: np.ndarray,
    depot: np.ndarray,
    reach: np.ndarray,
    capacity: np.ndarray,
    distance: np.ndarray,
    pair_i: np.ndarray,
    pair_j: np.ndarray,
    pair_w: np.ndarray,
    scales: dict[str, float],
) -> dict[str, float]:
    frequency_total = float(frequency.sum())
    raw = {
        "depot": float(np.dot(frequency, depot[assigned]) / frequency_total / scales["depot"]),
        "ergonomics": float(np.dot(frequency, reach[assigned]) / frequency_total / scales["ergonomics"]),
        "occupied_capacity": float(capacity[assigned].sum() / scales["occupied_capacity"]),
        "affinity": 0.0,
    }
    if pair_w.size:
        raw["affinity"] = float(np.dot(pair_w, distance[assigned[pair_i], assigned[pair_j]]) / pair_w.sum() / scales["affinity"])
    return raw


def _weighted(components: dict[str, float], weights: dict[str, float]) -> float:
    return float(sum(weights[name] * components[name] for name in weights))


def optimize_assignment(
    skus: pd.DataFrame,
    locations: pd.DataFrame,
    baseline: pd.DataFrame,
    abc: pd.DataFrame,
    affinity: pd.DataFrame,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Search legal moves from the baseline. Reject any move that breaks a hard rule."""
    rules = config["rules"]
    warehouse = config["warehouse"]
    settings = config["optimizer"]
    weights = {name: float(value) for name, value in settings["weights"].items()}
    graph = travel_graph(locations, warehouse)
    from_depot = depot_distance(graph, int(warehouse["depot_aisle"]), float(warehouse["depot_y_m"]))
    frame = graph["frame"]
    location_ids = graph["location_ids"]
    sku_frame = skus.sort_values("sku_id").reset_index(drop=True)
    sku_ids = sku_frame["sku_id"].tolist()
    sku_index = {sku_id: position for position, sku_id in enumerate(sku_ids)}
    frequency_table = abc.set_index("sku_id")["pick_frequency"]
    frequency = np.array([float(frequency_table.loc[sku_id]) for sku_id in sku_ids])
    loads = (sku_frame["unit_weight_kg"] * sku_frame["on_hand_qty"]).to_numpy(dtype=float)
    reach_table = {int(level): float(seconds) for level, seconds in rules["reach_penalty_seconds"].items()}
    reach = np.array([reach_table[int(level)] for level in graph["level"]])
    capacity = frame["volumetric_capacity_cm3"].to_numpy(dtype=float)
    rack_ids = frame["rack_id"].tolist()
    rack_labels = sorted(set(rack_ids))
    rack_lookup = {rack_id: position for position, rack_id in enumerate(rack_labels)}
    rack_index = np.array([rack_lookup[rack_id] for rack_id in rack_ids])
    rack_cap = frame.groupby("rack_id")["rack_max_weight_kg"].first().reindex(rack_labels).to_numpy(dtype=float)
    candidates = static_candidates(sku_frame, frame, rules)
    missing = [sku_id for sku_id, options in candidates.items() if not options]
    if missing:
        raise ValueError(f"No statically eligible bin for: {missing[:8]}")
    eligible = [[graph["index"][location_id] for location_id in candidates[sku_id]] for sku_id in sku_ids]
    baseline_map = baseline.set_index("sku_id")["location_id"]
    assigned = np.array([graph["index"][baseline_map.loc[sku_id]] for sku_id in sku_ids])
    taken = np.zeros(len(location_ids), dtype=bool)
    taken[assigned] = True
    occupant = np.full(len(location_ids), -1)
    occupant[assigned] = np.arange(len(sku_ids))
    rack_load = np.zeros(len(rack_labels))
    for sku_position, location_position in enumerate(assigned):
        rack_load[rack_index[location_position]] += loads[sku_position]
    pairs = supported_pairs(affinity, int(settings["affinity"]["min_cooccurrence"]), int(settings["affinity"]["neighbors_per_sku"]))
    pair_i = np.array([sku_index[left] for left, _, _ in pairs], dtype=int)
    pair_j = np.array([sku_index[right] for _, right, _ in pairs], dtype=int)
    pair_w = np.array([count for _, _, count in pairs], dtype=float)
    active_weights = dict(weights)
    scales = {
        "depot": float(from_depot.max()),
        "ergonomics": float(max(reach_table.values())),
        "occupied_capacity": float(np.sort(capacity)[-len(sku_ids):].sum()),
        "affinity": float(graph["distance"].max()) if pair_w.size else 1.0,
    }
    if not pair_w.size:
        active_weights["affinity"] = 0.0
        total_weight = sum(active_weights.values())
        active_weights = {name: value / total_weight for name, value in active_weights.items()}
    distance = graph["distance"]

    def score(layout: np.ndarray) -> float:
        return _weighted(_components(layout, frequency, from_depot, reach, capacity, distance, pair_i, pair_j, pair_w, scales), active_weights)

    def rack_ok(layout: np.ndarray) -> bool:
        trial = np.zeros(len(rack_labels))
        for sku_position, location_position in enumerate(layout):
            trial[rack_index[location_position]] += loads[sku_position]
        return bool(np.all(trial <= rack_cap + 1e-6))

    start_components = _components(assigned, frequency, from_depot, reach, capacity, distance, pair_i, pair_j, pair_w, scales)
    best_score = _weighted(start_components, active_weights)
    started = time.perf_counter()
    tested = 0
    accepted = 0
    checkpoints: list[tuple[float, np.ndarray]] = []
    reason = "proposal_budget"

    def remember() -> None:
        checkpoints.append((best_score, assigned.copy()))
        checkpoints.sort(key=lambda item: item[0])
        del checkpoints[5:]

    def accept(trial: np.ndarray) -> None:
        nonlocal assigned, best_score, accepted
        assigned = trial
        taken[:] = False
        taken[assigned] = True
        occupant[:] = -1
        occupant[assigned] = np.arange(len(sku_ids))
        rack_load[:] = 0.0
        for sku_position, location_position in enumerate(assigned):
            rack_load[rack_index[location_position]] += loads[sku_position]
        best_score = score(assigned)
        accepted += 1
        remember()

    def consider(trial: np.ndarray) -> None:
        nonlocal tested
        tested += 1
        if score(trial) < best_score - 1e-12:
            accept(trial)

    frequency_order = sorted(range(len(sku_ids)), key=lambda position: (-frequency[position], sku_ids[position]))
    for _ in range(3):
        if tested >= int(settings["max_proposals"]):
            break
        for sku_position in frequency_order:
            if tested >= int(settings["max_proposals"]) or time.perf_counter() - started > float(settings["time_limit_seconds"]):
                reason = "time_limit" if time.perf_counter() - started > float(settings["time_limit_seconds"]) else reason
                break
            ranked = sorted(eligible[sku_position], key=lambda location: (from_depot[location], reach[location], location_ids[location]))[:12]
            best_trial = None
            best_trial_score = best_score
            for location in ranked:
                if location == assigned[sku_position]:
                    continue
                other = int(occupant[location])
                trial = assigned.copy()
                if other < 0:
                    trial[sku_position] = location
                elif assigned[sku_position] in eligible[other] and location in eligible[sku_position]:
                    trial[sku_position], trial[other] = location, assigned[sku_position]
                else:
                    tested += 1
                    continue
                tested += 1
                if not rack_ok(trial):
                    continue
                trial_score = score(trial)
                if trial_score < best_trial_score - 1e-12:
                    best_trial = trial
                    best_trial_score = trial_score
            if best_trial is not None:
                accept(best_trial)
        else:
            continue
        break

    rng = random.Random(int(settings["seed"]))
    while tested < int(settings["max_proposals"]):
        if time.perf_counter() - started > float(settings["time_limit_seconds"]):
            reason = "time_limit"
            break
        roll = rng.random()
        if roll < 0.34 and pair_i.size:
            pair_at = rng.randrange(int(pair_i.size))
            left = int(pair_i[pair_at])
            right = int(pair_j[pair_at])
            anchor = int(assigned[right])
            options = [location for location in eligible[left] if not taken[location]]
            options.sort(key=lambda location: (distance[anchor, location], location_ids[location]))
            if not options:
                tested += 1
                continue
            best_trial = None
            best_trial_score = best_score
            for location in options[:3]:
                tested += 1
                trial = assigned.copy()
                trial[left] = location
                if not rack_ok(trial):
                    continue
                trial_score = score(trial)
                if trial_score < best_trial_score - 1e-12:
                    best_trial = trial
                    best_trial_score = trial_score
            if best_trial is not None:
                accept(best_trial)
            continue
        if roll < 0.7:
            sku_position = rng.choices(range(len(sku_ids)), weights=frequency.tolist(), k=1)[0]
            options = [location for location in eligible[sku_position] if not taken[location]]
            if not options:
                tested += 1
                continue
            options.sort(key=lambda location: (from_depot[location], location_ids[location]))
            choice = options[rng.randrange(min(8, len(options)))] if rng.random() < 0.7 else options[rng.randrange(len(options))]
            trial = assigned.copy()
            trial[sku_position] = choice
            if rack_ok(trial):
                consider(trial)
            else:
                tested += 1
            continue
        left, right = rng.sample(range(len(sku_ids)), 2)
        if assigned[right] not in eligible[left] or assigned[left] not in eligible[right]:
            tested += 1
            continue
        trial = assigned.copy()
        trial[left], trial[right] = assigned[right], assigned[left]
        if rack_ok(trial):
            consider(trial)
        else:
            tested += 1

    rebuilt = np.zeros(len(rack_labels))
    for sku_position, location_position in enumerate(assigned):
        rebuilt[rack_index[location_position]] += loads[sku_position]
    if not np.allclose(rebuilt, rack_load):
        raise RuntimeError("Rack-load cache drifted from the assignment")
    result = pd.DataFrame({
        "sku_id": sku_ids,
        "location_id": [location_ids[index] for index in assigned],
        "method": "local_search",
        "seed": int(settings["seed"]),
    })
    validation = validate_assignment(sku_frame, frame, result, rules)
    if not validation["is_feasible"]:
        raise RuntimeError(f"Search returned an illegal layout: {validation['violations'][:3]}")
    end_components = _components(assigned, frequency, from_depot, reach, capacity, distance, pair_i, pair_j, pair_w, scales)
    close_calls = []
    for sku_position in frequency_order[:40]:
        current = int(assigned[sku_position])
        best_gap = None
        best_location = None
        for location in eligible[sku_position]:
            if taken[location]:
                continue
            if int(graph["aisle"][location]) == int(graph["aisle"][current]) and int(graph["level"][location]) == int(graph["level"][current]):
                continue
            trial = assigned.copy()
            trial[sku_position] = location
            if not rack_ok(trial):
                continue
            gap = score(trial) - best_score
            if best_gap is None or gap < best_gap:
                best_gap = gap
                best_location = location
        if best_gap is not None and best_gap < max(0.005, 0.01 * best_score):
            close_calls.append({
                "sku_id": sku_ids[sku_position],
                "current_location_id": location_ids[current],
                "alternative_location_id": location_ids[best_location],
                "score_increase": float(best_gap),
            })
    report = {
        "proposals_tested": tested,
        "proposals_accepted": accepted,
        "stopping_reason": reason,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "objective_before": best_score if accepted == 0 else _weighted(start_components, active_weights),
        "objective_after": _weighted(end_components, active_weights),
        "components_before": start_components,
        "components_after": end_components,
        "weights": active_weights,
        "checkpoints": checkpoints,
        "graph": graph,
        "from_depot": from_depot,
        "close_calls": close_calls[:8],
        "close_call_count": len(close_calls),
        "validation": validation,
    }
    report["objective_before"] = _weighted(start_components, active_weights)
    return result, report
