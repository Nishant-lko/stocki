"""Train-only demand, affinity, and coverage analyses."""

from __future__ import annotations

from itertools import combinations

import pandas as pd


def abc_analysis(orders: pd.DataFrame) -> pd.DataFrame:
    train = orders.loc[orders["split"] == "train"]
    span_days = max((train["timestamp"].max() - train["timestamp"].min()).days + 1, 1)
    result = train.groupby("sku_id", as_index=False).agg(
        pick_frequency=("order_id", "nunique"), units_sold=("quantity", "sum")
    )
    result = result.sort_values(["pick_frequency", "sku_id"], ascending=[False, True], kind="stable")
    result["velocity_per_day"] = result["units_sold"] / span_days
    total = result["pick_frequency"].sum()
    result["demand_share"] = result["pick_frequency"] / total
    result["cumulative_demand_share"] = result["demand_share"].cumsum()
    result["abc_class"] = pd.cut(
        result["cumulative_demand_share"], bins=[-0.001, 0.80, 0.95, 1.001], labels=["A", "B", "C"]
    ).astype("string")
    return result.reset_index(drop=True)


def affinity_pairs(orders: pd.DataFrame) -> pd.DataFrame:
    train = orders.loc[orders["split"] == "train"]
    baskets = train.groupby("order_id")["sku_id"].agg(lambda values: sorted(set(values)))
    counts: dict[tuple[str, str], int] = {}
    item_counts = train.groupby("sku_id")["order_id"].nunique().to_dict()
    for basket in baskets:
        for pair in combinations(basket, 2):
            counts[pair] = counts.get(pair, 0) + 1
    total = len(baskets)
    rows = []
    for (sku_a, sku_b), count in counts.items():
        support = count / total
        confidence_a_b = count / item_counts[sku_a]
        confidence_b_a = count / item_counts[sku_b]
        rows.append({
            "sku_a": sku_a, "sku_b": sku_b, "cooccurrence": count, "support": support,
            "confidence_a_b": confidence_a_b, "confidence_b_a": confidence_b_a,
            "lift": support / ((item_counts[sku_a] / total) * (item_counts[sku_b] / total)),
            "jaccard": count / (item_counts[sku_a] + item_counts[sku_b] - count),
        })
    return pd.DataFrame(rows).sort_values(["cooccurrence", "sku_a", "sku_b"], ascending=[False, True, True]) if rows else pd.DataFrame()
