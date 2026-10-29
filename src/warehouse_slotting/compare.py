"""Attach a validated before/after comparison to an existing run bundle."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pandas as pd

from warehouse_slotting.baseline import allocate_frequency_sort
from warehouse_slotting.constraints import static_candidates, validate_assignment
from warehouse_slotting.evaluate import compare_routes, placement_snapshot, simulate_orders
from warehouse_slotting.ml_policy import choose_ml_layout, train_policy, validate_layout
from warehouse_slotting.optimize import optimize_assignment, supported_pairs
from warehouse_slotting.relocation import safe_relocation_sequence
from warehouse_slotting.routing import travel_graph


def _ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_ready(item) for item in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


def _refine_by_validation_routes(
    orders: pd.DataFrame,
    skus: pd.DataFrame,
    abc: pd.DataFrame,
    locations: pd.DataFrame,
    rules: dict[str, Any],
    graph: dict[str, Any],
    warehouse: dict[str, Any],
    starting: pd.DataFrame,
    start_distance_m: float,
    proposals: int,
    seed: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Hill-climb the exact route metric on validation orders, preserving hard rules."""
    legal = static_candidates(skus, locations, rules)
    legal_sets = {sku_id: set(options) for sku_id, options in legal.items()}
    current = starting.copy().sort_values("sku_id").reset_index(drop=True)
    best = current.copy()
    best_distance = float(start_distance_m)
    rng = random.Random(seed)
    ids = current["sku_id"].astype(str).tolist()
    pick_frequency = abc.set_index("sku_id")["pick_frequency"]
    weights = [max(1.0, float(pick_frequency.get(sku_id, 1))) for sku_id in ids]
    occupancy = dict(zip(current["location_id"], current["sku_id"], strict=True))
    tested = accepted = 0
    warehouse_rules = warehouse
    depot_aisle = int(warehouse_rules["depot_aisle"])
    depot_y = float(warehouse_rules["depot_y_m"])

    def score(frame: pd.DataFrame) -> float:
        simulated = simulate_orders(
            orders,
            frame,
            graph,
            rules,
            depot_aisle,
            depot_y,
            "validation",
            None,
        )
        return float(simulated["distance_m"].mean())

    for _ in range(max(0, int(proposals))):
        sku_id = rng.choices(ids, weights=weights, k=1)[0]
        current_location = str(current.loc[current["sku_id"] == sku_id, "location_id"].iloc[0])
        options = [
            location_id for location_id in legal.get(sku_id, []) if location_id != current_location
        ]
        if not options:
            tested += 1
            continue
        options.sort(key=lambda location_id: (graph["index"].get(location_id, 0), str(location_id)))
        destination = rng.choice(options[: min(18, len(options))])
        other_sku = occupancy.get(destination)
        trial = current.copy()
        if other_sku is None:
            trial.loc[trial["sku_id"] == sku_id, "location_id"] = destination
        elif current_location in legal_sets.get(str(other_sku), set()):
            trial.loc[trial["sku_id"] == sku_id, "location_id"] = destination
            trial.loc[trial["sku_id"] == other_sku, "location_id"] = current_location
        else:
            tested += 1
            continue
        tested += 1
        if not validate_assignment(skus, locations, trial, rules)["is_feasible"]:
            continue
        distance_m = score(trial)
        if distance_m < best_distance - 1e-9:
            current = trial.sort_values("sku_id").reset_index(drop=True)
            best = current.copy()
            best_distance = distance_m
            occupancy = dict(zip(current["location_id"], current["sku_id"], strict=True))
            accepted += 1
    return best, {
        "proposals_tested": tested,
        "proposals_accepted": accepted,
        "validation_mean_before_m": float(start_distance_m),
        "validation_mean_after_m": float(best_distance),
        "selection_metric": "mean route distance per order on the validation split",
        "test_split_used_for_selection": False,
    }


def attach_comparison(output: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Run the search and judge it on later orders. Do not replace a failed search with a claim."""
    orders = pd.read_parquet(output / "orders.parquet")
    skus = pd.read_parquet(output / "skus.parquet")
    locations = pd.read_parquet(output / "locations.parquet")
    abc = pd.read_parquet(output / "abc.parquet")
    affinity = pd.read_parquet(output / "affinity_pairs.parquet")
    baseline = pd.read_parquet(output / "baseline_assignments.parquet")
    optimized, search = optimize_assignment(skus, locations, baseline, abc, affinity, config)
    warehouse = config["warehouse"]
    rules = config["rules"]
    graph = search["graph"]
    depot_aisle = int(warehouse["depot_aisle"])
    depot_y = float(warehouse["depot_y_m"])
    validation_before = simulate_orders(
        orders,
        baseline,
        graph,
        rules,
        depot_aisle,
        depot_y,
        "validation",
        int(config["split"]["route_sample_size"]),
    )
    try:
        frequency_sort = allocate_frequency_sort(
            skus, locations, abc, rules, graph, search["from_depot"]
        )
    except RuntimeError:
        frequency_sort = None
    candidates = [("baseline", baseline, float(search["objective_before"]))]
    if frequency_sort is not None:
        candidates.append(("frequency_sort", frequency_sort, float("inf")))
    for score, layout in search["checkpoints"]:
        frame = optimized.copy()
        frame["location_id"] = [graph["location_ids"][index] for index in layout]
        frame["method"] = "checkpoint"
        candidates.append(("checkpoint", frame, float(score)))
    candidates.append(("incumbent", optimized, float(search["objective_after"])))
    seen: set[tuple[str, ...]] = set()
    ranked = []
    for index, (name, frame, objective) in enumerate(candidates):
        key = tuple(frame.sort_values("sku_id")["location_id"].tolist())
        if key in seen:
            continue
        seen.add(key)
        simulated = (
            validation_before
            if name == "baseline"
            else simulate_orders(
                orders,
                frame,
                graph,
                rules,
                depot_aisle,
                depot_y,
                "validation",
                int(config["split"]["route_sample_size"]),
            )
        )
        ranked.append(
            (
                float(simulated["distance_m"].mean()),
                float(simulated["time_s"].mean()),
                objective,
                index,
                name,
                frame,
            )
        )
    ranked.sort()
    selected_validation_m, _, _, _, selected_name, selected = ranked[0]
    validation_ids = set(validation_before["order_id"])
    validation_sample = orders.loc[
        (orders["split"] == "validation") & orders["order_id"].isin(validation_ids)
    ].copy()
    route_refinement, route_refinement_report = _refine_by_validation_routes(
        validation_sample,
        skus,
        abc,
        locations,
        rules,
        graph,
        warehouse,
        selected,
        selected_validation_m,
        int(config["optimizer"].get("route_refinement_proposals", 120)),
        int(config["optimizer"]["seed"]) + 17,
    )
    if route_refinement_report["proposals_accepted"]:
        selected = route_refinement
        selected_name = "route_refined"
        selected_validation_m = route_refinement_report["validation_mean_after_m"]
    published = selected.sort_values("sku_id").reset_index(drop=True)
    published_validation = validate_assignment(skus, locations, published, rules)
    if not published_validation["is_feasible"]:
        raise RuntimeError(
            f"Selected layout failed validation: {published_validation['violations'][:3]}"
        )
    relocation_plan, relocation_report = safe_relocation_sequence(
        skus, locations, baseline, published, abc, rules
    )
    if relocation_plan.empty:
        relocation_plan = pd.DataFrame(
            columns=[
                "step", "operation", "sku_id", "from_location", "to_location",
                "other_sku_id", "other_from", "other_to", "product_moves", "pick_frequency",
            ]
        )
    relocation_plan.to_parquet(output / "relocation_plan.parquet", index=False)
    (output / "relocation_plan_status.json").write_text(
        json.dumps(_ready(relocation_report), indent=2), encoding="utf-8"
    )
    if selected_name == "baseline":
        published["method"] = "baseline_retained"
    elif selected_name == "frequency_sort":
        published["method"] = "frequency_sort"
    elif selected_name == "route_refined":
        published["method"] = "route_validated_search"
    else:
        published["method"] = "route_validated_search"
    published.to_parquet(output / "optimized_assignments.parquet", index=False)
    if frequency_sort is not None:
        frequency_sort.to_parquet(output / "frequency_sort_assignments.parquet", index=False)
    candidate_map = static_candidates(skus, locations, rules)
    eligible_rows = [
        {"sku_id": sku_id, "location_id": location_id}
        for sku_id, location_ids in candidate_map.items()
        for location_id in location_ids
    ]
    pd.DataFrame(eligible_rows).to_parquet(output / "eligible_bins.parquet", index=False)
    if selected_name == "baseline":
        optimized.to_parquet(output / "search_incumbent.parquet", index=False)
    test_before = simulate_orders(
        orders, baseline, graph, rules, depot_aisle, depot_y, "test", None
    )
    test_frequency = (
        simulate_orders(orders, frequency_sort, graph, rules, depot_aisle, depot_y, "test", None)
        if frequency_sort is not None
        else None
    )
    test_after = simulate_orders(
        orders, published, graph, rules, depot_aisle, depot_y, "test", None
    )
    test_summary, test_table = compare_routes(test_before, test_after)
    if test_frequency is not None:
        test_table = test_table.merge(
            test_frequency[["order_id", "distance_m"]].rename(
                columns={"distance_m": "frequency_sort_distance_m"}
            ),
            on="order_id",
            validate="one_to_one",
        )
    test_table.to_parquet(output / "order_comparison.parquet", index=False)
    monthly_rows = []
    test_lines = orders.loc[orders["split"] == "test"].copy()
    test_lines["test_month"] = pd.to_datetime(test_lines["timestamp"]).dt.to_period("M").astype(str)
    for month, month_lines in test_lines.groupby("test_month", sort=True):
        month_ids = set(month_lines["order_id"])
        month_orders = orders.loc[orders["order_id"].isin(month_ids)].copy()
        monthly_layouts = [("Random legal", baseline), ("Published", published)]
        if frequency_sort is not None:
            monthly_layouts.insert(1, ("Frequency sort", frequency_sort))
        for split_name, assignment in monthly_layouts:
            scored = simulate_orders(
                month_orders, assignment, graph, rules, depot_aisle, depot_y, "test", None
            )
            monthly_rows.append(
                {
                    "month": month,
                    "layout": split_name,
                    "orders": len(scored),
                    "mean_distance_m": float(scored["distance_m"].mean()),
                    "mean_time_s": float(scored["time_s"].mean()),
                }
            )
    pd.DataFrame(monthly_rows).to_parquet(output / "monthly_test_metrics.parquet", index=False)
    pairs = supported_pairs(
        affinity,
        int(config["optimizer"]["affinity"]["min_cooccurrence"]),
        int(config["optimizer"]["affinity"]["neighbors_per_sku"]),
    )
    full_graph = travel_graph(locations, warehouse)
    from_depot = search["from_depot"]
    test_weights = orders.loc[orders["split"] == "test"].groupby("sku_id")["order_id"].nunique()
    before_place = placement_snapshot(
        skus, locations, baseline, abc, full_graph, from_depot, pairs, test_weights
    )
    after_place = placement_snapshot(
        skus, locations, published, abc, full_graph, from_depot, pairs, test_weights
    )
    paired = baseline[["sku_id", "location_id"]].merge(
        published[["sku_id", "location_id"]], on="sku_id", suffixes=("_before", "_after")
    )
    before_joined = baseline.merge(locations, on="location_id")
    after_joined = published.merge(locations, on="location_id")
    moved = before_joined[["sku_id", "aisle_number"]].merge(
        after_joined[["sku_id", "aisle_number"]], on="sku_id", suffixes=("_before", "_after")
    )
    stock = float((skus["unit_volume_cm3"] * skus["on_hand_qty"]).sum())
    ml_policy = train_policy(
        skus, locations, abc, candidate_map, published, from_depot, int(config["optimizer"]["seed"])
    )
    ml_layout, ml_choice = choose_ml_layout(
        ml_policy["model"],
        ml_policy["pairs"],
        ml_policy["prediction"],
        skus,
        locations,
        abc,
        rules,
        int(config["optimizer"]["seed"]),
    )
    ml_block: dict[str, Any] = {}
    if ml_layout is None:
        ml_block = {
            "enabled": False,
            "reason": ml_choice.get("reason", "the classifier produced no layout"),
        }
    else:
        ml_report = validate_layout(skus, locations, ml_layout, rules)
        if not ml_report["is_feasible"]:
            ml_block = {
                "enabled": False,
                "reason": f"the classifier's layout broke a rule: {ml_report['violations'][0]['code']}",
            }
        else:
            ml_layout.to_parquet(output / "ml_layout.parquet", index=False)
            ml_simulated = simulate_orders(
                orders, ml_layout, graph, rules, depot_aisle, depot_y, "test", None
            )
            merged = test_table.merge(
                ml_simulated[["order_id", "distance_m"]].rename(
                    columns={"distance_m": "ml_distance_m"}
                ),
                on="order_id",
                validate="one_to_one",
            )
            delta_ml = merged["ml_distance_m"] - merged["optimized_distance_m"]
            ml_block = {
                "enabled": True,
                "model": "random forest classifier trained on the search's own placements",
                "top1_accuracy": ml_policy["top1_accuracy"],
                "top3_accuracy": ml_policy["top3_accuracy"],
                "holdout_skus": ml_policy["holdout_skus"],
                "training_pairs": ml_policy["training_pairs"],
                "feature_importance": ml_policy["feature_importance"],
                "mean_distance_m": float(ml_simulated["distance_m"].mean()),
                "published_mean_distance_m": test_summary["optimized_mean_distance_m"],
                "baseline_mean_distance_m": test_summary["baseline_mean_distance_m"],
                "orders_shorter_than_published": int((delta_ml < -1e-6).sum()),
                "orders_longer_than_published": int((delta_ml > 1e-6).sum()),
                "mean_handling_s": test_summary["mean_handling_s"],
                "mean_reach_s": float(ml_simulated["reach_s"].mean()),
                "features": [
                    "one row per product and legal bin",
                    "labels: the bin the search chose",
                    "features: product demand and physics, bin distance, height, size, zone",
                ],
            }
            merged[
                ["order_id", "baseline_distance_m", "optimized_distance_m", "ml_distance_m"]
            ].to_parquet(output / "ml_comparison.parquet", index=False)
            (output / "ml_views.json").write_text(
                json.dumps(ml_choice.get("views", {}), indent=2), encoding="utf-8"
            )
    metrics = {
        "selected": selected_name,
        "selection_note": {
            "baseline": "Validation walks preferred the random legal starting layout, so it remains published.",
            "frequency_sort": "Validation walks preferred the transparent frequency-sort plan. The search did not beat this comparator on the selection window.",
        }.get(
            selected_name,
            "A constrained route refinement improved the best validation candidate. Test orders were not used to make that choice.",
        ),
        "optimizer": {
            "proposals_tested": search["proposals_tested"],
            "proposals_accepted": search["proposals_accepted"],
            "stopping_reason": search["stopping_reason"],
            "elapsed_seconds": search["elapsed_seconds"],
            "objective_before": search["objective_before"],
            "objective_after": search["objective_after"],
            "components_before": search["components_before"],
            "components_after": search["components_after"],
            "weights": search["weights"],
            "incumbent_validation_mean_distance_m": float(
                next((item[0] for item in ranked if item[4] == "incumbent"), ranked[0][0])
            ),
            "baseline_validation_mean_distance_m": float(validation_before["distance_m"].mean()),
            "selected_validation_mean_distance_m": float(selected_validation_m),
            "validation_orders": len(validation_before),
            "validation_policy": "first configured validation order IDs in sorted order; published plan chosen from legal search checkpoints, random legal and frequency sort",
            "route_refinement": route_refinement_report,
        },
        "frequency_sort": {
            "available": frequency_sort is not None,
            "validation_mean_distance_m": float(
                next((item[0] for item in ranked if item[4] == "frequency_sort"), float("nan"))
            )
            if frequency_sort is not None
            else None,
            "test_mean_distance_m": float(test_frequency["distance_m"].mean())
            if test_frequency is not None
            else None,
            "feasible": frequency_sort is not None,
        },
        "relocation_plan": relocation_report,
        "test": test_summary,
        "placement": {
            "skus_moved": int((paired["location_id_before"] != paired["location_id_after"]).sum()),
            "skus_changed_aisle": int(
                (moved["aisle_number_before"] != moved["aisle_number_after"]).sum()
            ),
            "a_mean_depot_before_m": before_place["a_mean_depot_m"],
            "a_mean_depot_after_m": after_place["a_mean_depot_m"],
            "affinity_mean_before_m": before_place["affinity_mean_m"],
            "affinity_mean_after_m": after_place["affinity_mean_m"],
            "golden_share_train_before": before_place["golden_share_train"],
            "golden_share_train_after": after_place["golden_share_train"],
            "golden_share_test_before": before_place["golden_share_test"],
            "golden_share_test_after": after_place["golden_share_test"],
            "occupied_fill_before": before_place["occupied_fill"],
            "occupied_fill_after": after_place["occupied_fill"],
            "overall_cube_fill": stock / float(locations["volumetric_capacity_cm3"].sum()),
            "occupied_bin_count": len(skus),
        },
        "safety": {
            "baseline_feasible": True,
            "optimized_feasible": bool(published_validation["is_feasible"]),
            "optimized_violation_count": int(published_validation["violation_count"]),
        },
        "assumptions": {
            "walking_speed_mps": rules["walking_speed_mps"],
            "base_pick_seconds": rules["base_pick_seconds"],
            "seconds_per_unit": rules["seconds_per_unit"],
            "reach_penalty_seconds": rules["reach_penalty_seconds"],
            "heavy_unit_weight_kg": rules["heavy_unit_weight_kg"],
            "heavy_allowed_levels": rules["heavy_allowed_levels"],
            "golden_zone_levels": rules["golden_zone_levels"],
            "hazardous_zone": rules["hazardous_zone"],
            "aisle_spacing_m": warehouse["aisle_spacing_m"],
            "front_cross_aisle_y_m": warehouse["front_cross_aisle_y_m"],
            "rear_cross_aisle_y_m": warehouse["rear_cross_aisle_y_m"],
            "depot_aisle": warehouse["depot_aisle"],
            "depot_y_m": warehouse["depot_y_m"],
            "aisle_count": warehouse["aisle_count"],
        },
        "close_call_count": search["close_call_count"],
        "close_calls": search["close_calls"],
        "ml": ml_block,
    }
    payload = _ready(metrics)
    (output / "comparison_metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (output / "optimized_validation.json").write_text(
        json.dumps(published_validation, indent=2), encoding="utf-8"
    )
    manifest_path = output / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["comparison"] = {
        "selected": payload["selected"],
        "test_mean_distance_before_m": payload["test"]["baseline_mean_distance_m"],
        "test_mean_distance_after_m": payload["test"]["optimized_mean_distance_m"],
        "optimized_feasible": payload["safety"]["optimized_feasible"],
        "ml_enabled": payload["ml"].get("enabled", False),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return payload
