import pandas as pd
import pytest

from warehouse_slotting.seasonal import stock_readiness, training_days


def test_training_days_uses_training_split_and_inclusive_dates() -> None:
    orders = pd.DataFrame(
        {
            "split": ["train", "train", "test"],
            "timestamp": pd.to_datetime(["2025-01-01", "2025-01-03", "2025-12-31"]),
        }
    )
    assert training_days(orders) == 3


def test_stock_readiness_separates_pick_face_reserve_and_shortfall() -> None:
    skus = pd.DataFrame(
        [
            {"sku_id": "A", "description": "Fast mover", "on_hand_qty": 2, "reserve_qty": 3},
            {"sku_id": "B", "description": "No reserve", "on_hand_qty": 0, "reserve_qty": 0},
        ]
    )
    abc = pd.DataFrame(
        [
            {"sku_id": "A", "pick_frequency": 10, "units_sold": 20},
            {"sku_id": "B", "pick_frequency": 5, "units_sold": 5},
        ]
    )
    orders = pd.DataFrame(
        {
            "split": ["train", "train"],
            "timestamp": pd.to_datetime(["2025-01-01", "2025-01-10"]),
        }
    )

    result = stock_readiness(skus, abc, orders, 9, {"A": 1.0, "B": 1.0}).set_index("sku_id")

    assert result.loc["A", "expected_units"] == 18
    assert result.loc["A", "pick_face_replenishment"] == 16
    assert result.loc["A", "reserve_replenishment"] == 3
    assert result.loc["A", "uncovered_units"] == 13
    assert result.loc["A", "status"] == "Shortfall"
    assert result.loc["B", "reserve_replenishment"] == 0
    assert result.loc["B", "uncovered_units"] == 5


def test_stock_readiness_requires_training_orders() -> None:
    with pytest.raises(ValueError, match="training orders"):
        training_days(pd.DataFrame({"split": ["test"], "timestamp": pd.to_datetime(["2025-01-01"])}))
