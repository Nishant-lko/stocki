"""Regenerate synthetic correlated baskets for a reproducible gains demo."""

from pathlib import Path

from warehouse_slotting.config import load_config
from warehouse_slotting.demo_data import write_affinity_showcase_dataset


ROOT = Path(__file__).resolve().parents[1]
files = write_affinity_showcase_dataset(load_config(ROOT / "configs/default.yaml"), ROOT / "data/demo")
for name, path in files.items():
    print(f"{name}: {path.relative_to(ROOT)}")
