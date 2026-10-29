"""Temporary, scenario-driven re-slotting using the existing constrained optimizer."""

from __future__ import annotations

import numpy as np
import pandas as pd

from warehouse_slotting.constraints import validate_assignment
from warehouse_slotting.evaluate import simulate_orders
from warehouse_slotting.optimize import optimize_assignment
from warehouse_slotting.relocation import safe_relocation_sequence
from warehouse_slotting.routing import travel_graph


def training_days(orders: pd.DataFrame) -> int:
    """Calendar span represented by training orders, with a one-day floor."""
    training = orders.loc[orders["split"] == "train", "timestamp"]
    if training.empty:
        raise ValueError("This run has no training orders for seasonal planning")
    return max(1, int((training.max().date() - training.min().date()).days + 1))


def stock_readiness(
    skus: pd.DataFrame,
    abc: pd.DataFrame,
    orders: pd.DataFrame,
    scenario_days: int,
    multipliers: dict[str, float],
) -> pd.DataFrame:
    """Estimate pick-face demand and reserve replenishment from SKU history and forecast."""
    baseline_days = training_days(orders)
    mean_units_per_order = (
        abc.set_index("sku_id")["units_sold"].astype(float)
        / abc.set_index("sku_id")["pick_frequency"].replace(0, np.nan)
    )
    frequency = abc.set_index("sku_id")["pick_frequency"].astype(float)
    rows = skus[["sku_id", "description", "on_hand_qty"]].copy()
    rows["baseline_orders_per_day"] = rows["sku_id"].map(frequency).fillna(0.0) / baseline_days
    rows["scenario_multiplier"] = rows["sku_id"].map(multipliers).fillna(1.0).astype(float)
    rows["expected_orders"] = (
        rows["baseline_orders_per_day"] * rows["scenario_multiplier"] * int(scenario_days)
    )
    rows["mean_units_per_order"] = rows["sku_id"].map(mean_units_per_order).fillna(1.0)
    rows["expected_units"] = np.ceil(rows["expected_orders"] * rows["mean_units_per_order"]).astype(int)
    if "reserve_qty" in skus:
        rows["reserve_qty"] = rows["sku_id"].map(skus.set_index("sku_id")["reserve_qty"]).fillna(0).astype(int)
    else:
        rows["reserve_qty"] = 0
    rows["pick_face_replenishment"] = np.maximum(
        rows["expected_units"] - rows["on_hand_qty"], 0
    )
    rows["reserve_replenishment"] = np.minimum(
        rows["pick_face_replenishment"], rows["reserve_qty"]
    )
    rows["uncovered_units"] = np.maximum(
        rows["pick_face_replenishment"] - rows["reserve_qty"], 0
    )
    rows["status"] = np.where(
        rows["uncovered_units"] > 0,
        "Shortfall",
        np.where(rows["pick_face_replenishment"] > 0, "Replenish pick face", "Covered"),
    )
    return rows.sort_values(
        ["uncovered_units", "pick_face_replenishment", "expected_units", "sku_id"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)


def synthetic_festival_forecast(
    skus: pd.DataFrame, abc: pd.DataFrame, scenario_days: int, baseline_days: int
) -> pd.DataFrame:
    """Create a deterministic, clearly synthetic festival forecast for a run's SKUs."""
    if scenario_days < 1 or baseline_days < 1:
        raise ValueError("Scenario and baseline durations must be positive")
    demand = abc[["sku_id", "pick_frequency"]].copy()
    demand["sku_id"] = demand["sku_id"].astype(str)
    demand["pick_frequency"] = pd.to_numeric(demand["pick_frequency"], errors="coerce").fillna(0.0)
    demand = demand.merge(
        skus[["sku_id", "description"]].assign(sku_id=lambda frame: frame["sku_id"].astype(str)),
        on="sku_id",
        how="left",
        validate="one_to_one",
    )
    if demand.empty:
        raise ValueError("This run has no SKUs for a synthetic forecast")
    demand = demand.sort_values(["pick_frequency", "sku_id"], ascending=[False, True]).reset_index(drop=True)
    promoted_count = min(len(demand), max(1, min(12, int(np.ceil(len(demand) * 0.10)))))
    promoted = set(demand.head(promoted_count)["sku_id"])
    demand["baseline_expected_orders"] = demand["pick_frequency"] / baseline_days * scenario_days
    demand["scenario_multiplier"] = demand["sku_id"].map(
        lambda sku_id: 3.0 if sku_id in promoted else 1.0
    )
    demand["expected_orders"] = np.ceil(
        demand["baseline_expected_orders"] * demand["scenario_multiplier"]
    ).astype(int)
    demand["scenario"] = "Synthetic festival promotion"
    demand["assumption"] = demand["sku_id"].map(
        lambda sku_id: "Illustrative 3× promotion uplift" if sku_id in promoted else "Baseline demand"
    )
    demand["baseline_expected_orders"] = np.ceil(demand["baseline_expected_orders"]).astype(int)
    return demand[
        [
            "sku_id",
            "description",
            "baseline_expected_orders",
            "scenario_multiplier",
            "expected_orders",
            "scenario",
            "assumption",
        ]
    ]


def monthly_demand_multipliers(
    orders: pd.DataFrame, abc: pd.DataFrame, month: str, prior_days: int = 7
) -> dict[str, float]:
    """Estimate scenario demand rates from a training-only calendar month.

    A seven-day prior at the training rate smooths sparse monthly SKU counts.
    """
    train = orders.loc[orders["split"] == "train"].copy()
    if train.empty:
        raise ValueError("This run has no training orders for seasonal planning")
    train["month"] = train["timestamp"].dt.to_period("M").astype(str)
    selected = train.loc[train["month"] == str(month)]
    if selected.empty:
        raise ValueError(f"No training orders are available for {month}")
    start = pd.Period(str(month), freq="M").start_time.date()
    end = pd.Period(str(month), freq="M").end_time.date()
    month_days = (end - start).days + 1
    baseline_days = training_days(orders)
    baseline = abc.set_index("sku_id")["pick_frequency"].astype(float) / baseline_days
    monthly = selected.groupby("sku_id")["order_id"].nunique().astype(float)
    rates = (monthly.add(baseline * prior_days, fill_value=0.0)) / (month_days + prior_days)
    rates = rates.reindex(baseline.index, fill_value=0.0)
    multipliers = rates.div(baseline.replace(0, np.nan)).fillna(1.0)
    return multipliers.clip(lower=0.0, upper=100.0).to_dict()


def forecast_demand_multipliers(
    forecast: pd.DataFrame,
    abc: pd.DataFrame,
    skus: pd.DataFrame,
    days: int,
    baseline_days: int,
) -> dict[str, float]:
    """Convert expected order counts during the scenario into demand-rate ratios."""
    frame = forecast.copy()
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    if not {"sku_id", "expected_orders"}.issubset(frame.columns):
        raise ValueError("Forecast CSV needs sku_id and expected_orders columns")
    frame["sku_id"] = frame["sku_id"].astype("string").str.strip()
    if frame["sku_id"].isna().any() or frame["sku_id"].eq("").any():
        raise ValueError("Forecast sku_id values must be present")
    if frame["sku_id"].duplicated().any():
        raise ValueError("Forecast CSV must contain at most one row per sku_id")
    frame["expected_orders"] = pd.to_numeric(frame["expected_orders"], errors="coerce")
    if (
        frame["expected_orders"].isna().any()
        or not np.isfinite(frame["expected_orders"]).all()
        or (frame["expected_orders"] < 0).any()
    ):
        raise ValueError("Forecast expected_orders values must be finite and non-negative")
    known = set(skus["sku_id"].astype(str))
    unknown = sorted(set(frame["sku_id"].astype(str)) - known)
    if unknown:
        raise ValueError(f"Forecast has unknown sku_id values: {unknown[:8]}")
    if frame["expected_orders"].sum() <= 0:
        raise ValueError("Forecast must contain positive expected demand for at least one SKU")
    baseline = abc.set_index("sku_id")["pick_frequency"].astype(float)
    rates = baseline / max(1, int(baseline_days))
    expected = frame.set_index("sku_id")["expected_orders"].astype(float)
    expected_rate = expected / max(1, int(days))
    ratios = expected_rate.div(rates.reindex(expected_rate.index).replace(0, np.nan))
    # A SKU with no observed history is assigned a conservative positive weight
    # proportional to its forecast, relative to the mean observed daily rate.
    fallback = expected_rate / max(float(rates.mean()), 1e-9)
    ratios = ratios.fillna(fallback)
    if (ratios > 100).any():
        raise ValueError("Forecast implies over 100× historical demand for an SKU; review the CSV units")
    return ratios.clip(lower=0.0, upper=100.0).to_dict()


def make_seasonal_layout(
    skus: pd.DataFrame,
    locations: pd.DataFrame,
    current: pd.DataFrame,
    abc: pd.DataFrame,
    affinity: pd.DataFrame,
    config: dict,
    multipliers: dict[str, float],
    max_changed_skus: int | None = None,
) -> tuple[pd.DataFrame, dict, dict]:
    """Optimize from the published layout using temporary demand weights only."""
    adjusted = abc.copy()
    adjusted["pick_frequency"] = adjusted["pick_frequency"].astype(float)
    adjusted["pick_frequency"] *= adjusted["sku_id"].map(multipliers).fillna(1.0)
    if adjusted["pick_frequency"].sum() <= 0:
        raise ValueError("Scenario demand is zero for every SKU")
    search_config = config
    if max_changed_skus is not None:
        search_config = {
            **config,
            "optimizer": {**config["optimizer"], "max_changed_skus": int(max_changed_skus)},
        }
    assignment, search = optimize_assignment(
        skus, locations, current, adjusted, affinity, search_config
    )
    validation = validate_assignment(skus, locations, assignment, config["rules"])
    if not validation["is_feasible"]:
        raise RuntimeError(f"Seasonal proposal failed safety validation: {validation['violations'][:3]}")
    return assignment, search, validation


def build_verified_move_tasks(
    skus: pd.DataFrame,
    locations: pd.DataFrame,
    current: pd.DataFrame,
    proposed: pd.DataFrame,
    abc: pd.DataFrame,
    rules: dict,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Sequence a temporary event plan through assignments verified at every step."""
    return safe_relocation_sequence(skus, locations, current, proposed, abc, rules)


def apply_verified_move_task(
    skus: pd.DataFrame,
    locations: pd.DataFrame,
    assignments: pd.DataFrame,
    task: pd.Series | dict,
    rules: dict,
) -> tuple[pd.DataFrame, dict]:
    """Apply one approved task only if its expected sources still match and verify."""
    task = dict(task)
    result = assignments[["sku_id", "location_id"]].copy()
    result["sku_id"] = result["sku_id"].astype(str)
    result["location_id"] = result["location_id"].astype(str)
    sku_id = str(task["sku_id"])
    current = result.set_index("sku_id")["location_id"]
    if sku_id not in current or str(current[sku_id]) != str(task["from_location"]):
        raise ValueError("The product is no longer at the task's expected source bin")
    operation = str(task["operation"]).casefold()
    if operation == "swap":
        other_sku_id = str(task["other_sku_id"])
        if other_sku_id not in current or str(current[other_sku_id]) != str(task["other_from"]):
            raise ValueError("The other product is no longer at the task's expected source bin")
        result.loc[result["sku_id"] == sku_id, "location_id"] = str(task["to_location"])
        result.loc[result["sku_id"] == other_sku_id, "location_id"] = str(task["other_to"])
    else:
        result.loc[result["sku_id"] == sku_id, "location_id"] = str(task["to_location"])
    validation = validate_assignment(skus, locations, result, rules)
    if not validation["is_feasible"]:
        raise ValueError(
            "The task would make the current layout unsafe: "
            + "; ".join(item["message"] for item in validation["violations"][:3])
        )
    return result, validation


def compare_scenario_routes(
    orders: pd.DataFrame,
    current: pd.DataFrame,
    proposed: pd.DataFrame,
    locations: pd.DataFrame,
    config: dict,
    multipliers: dict[str, float],
) -> dict[str, float | int]:
    """Compare routes on held-out orders reweighted to the requested SKU demand mix.

    For each order, use the largest changed-SKU multiplier in that basket. This
    conservative approximation avoids multiplying uplifts together in baskets
    containing several affected items.
    """
    warehouse = config["warehouse"]
    rules = config["rules"]
    graph = travel_graph(locations, warehouse)
    before = simulate_orders(
        orders, current, graph, rules, int(warehouse["depot_aisle"]),
        float(warehouse["depot_y_m"]), "test", None,
    )
    after = simulate_orders(
        orders, proposed, graph, rules, int(warehouse["depot_aisle"]),
        float(warehouse["depot_y_m"]), "test", None,
    )
    test = orders.loc[orders["split"] == "test", ["order_id", "sku_id"]].copy()
    test["scenario_multiplier"] = test["sku_id"].map(multipliers).fillna(1.0)
    order_weights = test.groupby("order_id")["scenario_multiplier"].max()
    pairs = before.merge(after, on="order_id", suffixes=("_current", "_proposed"), validate="one_to_one")
    pairs["scenario_weight"] = pairs["order_id"].map(order_weights).fillna(1.0)
    weights = pairs["scenario_weight"].to_numpy(dtype=float)
    if weights.sum() <= 0:
        raise ValueError("Scenario reweighting leaves no held-out orders to score")
    return {
        "orders": int(len(pairs)),
        "current_distance_m": float(np.average(pairs["distance_m_current"], weights=weights)),
        "proposed_distance_m": float(np.average(pairs["distance_m_proposed"], weights=weights)),
        "current_time_s": float(np.average(pairs["time_s_current"], weights=weights)),
        "proposed_time_s": float(np.average(pairs["time_s_proposed"], weights=weights)),
        "unweighted_current_distance_m": float(pairs["distance_m_current"].mean()),
        "unweighted_proposed_distance_m": float(pairs["distance_m_proposed"].mean()),
        "weighted_orders": float(weights.sum()),
    }
