"""Regenerate the deterministic synthetic festival warehouse input files."""

from pathlib import Path

import numpy as np
import pandas as pd

from warehouse_slotting.config import load_config
from warehouse_slotting.demo_data import write_demo_dataset


ROOT = Path(__file__).resolve().parents[1]
config = load_config(ROOT / "configs/default.yaml")
files = write_demo_dataset(config, ROOT / "data/demo")

# Match the pipeline's timestamp-grouped chronological training split and fail
# loudly if a future generator edit stops demonstrating the intended long tail.
orders = pd.read_csv(files["orders"], parse_dates=["timestamp"])
order_times = orders.groupby("order_id", as_index=False)["timestamp"].min().sort_values("timestamp")
timestamp_counts = order_times.groupby("timestamp", as_index=False).size().rename(columns={"size": "orders"})
train_target = len(order_times) * float(config["split"]["train"])
train_times = timestamp_counts.loc[timestamp_counts["orders"].cumsum() <= train_target, "timestamp"]
train_ids = set(order_times.loc[order_times["timestamp"].isin(train_times), "order_id"])
frequency = orders.loc[orders["order_id"].isin(train_ids)].groupby("sku_id")["order_id"].nunique().sort_values(ascending=False)
top_count = max(1, int(np.ceil(len(frequency) * 0.20)))
top_share = float(frequency.head(top_count).sum() / frequency.sum())
print(f"Training top-20% SKU order share: {top_share:.1%}")
if not 0.75 <= top_share <= 0.85:
    raise RuntimeError(
        f"The synthetic festival demand profile missed its 80/20 target: observed {top_share:.1%}."
    )
for name, path in files.items():
    print(f"{name}: {path.relative_to(ROOT)}")
