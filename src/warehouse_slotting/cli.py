"""Command-line entry point for the reproducible baseline pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from warehouse_slotting.baseline import allocate_baseline
from warehouse_slotting.compare import attach_comparison
from warehouse_slotting.config import config_hash, load_config
from warehouse_slotting.constraints import static_candidates, validate_assignment
from warehouse_slotting.eda import abc_analysis, affinity_pairs
from warehouse_slotting.ingest import (
    chronological_split,
    clean_orders,
    read_online_retail_zip,
    select_active_cohort,
)
from warehouse_slotting.synthesize import generate_locations, generate_skus


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_line_items(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Clean a plain orders file: order_id, sku_id, quantity, optional timestamp."""
    cleaned = frame.copy()
    cleaned.columns = [str(column).strip().lower() for column in cleaned.columns]
    missing = {"order_id", "sku_id", "quantity"} - set(cleaned.columns)
    if missing:
        raise ValueError(f"The orders file is missing columns: {sorted(missing)}")
    source_rows = len(cleaned)
    if "timestamp" not in cleaned.columns:
        cleaned["timestamp"] = pd.date_range("2020-01-01", periods=len(cleaned), freq="60min").to_numpy()
    cleaned["order_id"] = cleaned["order_id"].astype("string").str.strip()
    cleaned["sku_id"] = cleaned["sku_id"].astype("string").str.strip()
    cleaned["quantity"] = pd.to_numeric(cleaned["quantity"], errors="coerce")
    cleaned["timestamp"] = pd.to_datetime(cleaned["timestamp"], errors="coerce")
    valid = cleaned["order_id"].notna() & cleaned["sku_id"].notna() & cleaned["timestamp"].notna() & (cleaned["quantity"] > 0)
    filtered = cleaned.loc[valid, ["order_id", "sku_id", "quantity", "timestamp"]].copy()
    filtered["quantity"] = filtered["quantity"].astype("int64")
    before_duplicates = len(filtered)
    filtered = filtered.drop_duplicates()
    grouped = (
        filtered.groupby(["order_id", "sku_id"], as_index=False)
        .agg(quantity=("quantity", "sum"), timestamp=("timestamp", "min"))
        .sort_values(["timestamp", "order_id", "sku_id"], kind="stable")
        .reset_index(drop=True)
    )
    report = {
        "source_rows": source_rows,
        "rows_after_validity_filter": before_duplicates,
        "exact_duplicates_removed": before_duplicates - len(filtered),
        "canonical_order_lines": len(grouped),
    }
    return grouped, report


def run(config_path: str | Path, orders_csv: Path | None = None, run_name: str | None = None) -> Path:
    """Build canonical inputs, train EDA and a validated demand-blind baseline."""
    config = load_config(config_path)
    run_config = config["run"]
    if run_name is not None:
        config["run"]["name"] = run_name
        run_config = config["run"]
    if orders_csv is not None:
        source_path = Path(orders_csv)
        if not source_path.is_file():
            raise FileNotFoundError(f"Orders file does not exist: {source_path}")
        cleaned, cleaning_report = clean_line_items(pd.read_csv(source_path))
        cleaning_report["source_label"] = source_path.name
    else:
        source_path = Path(run_config["source_file"])
        if not source_path.is_file():
            raise FileNotFoundError(f"Configured source archive does not exist: {source_path}")
        source = read_online_retail_zip(source_path, run_config["source_sheet"])
        cleaned, cleaning_report = clean_orders(source)
    orders = chronological_split(cleaned, config["split"])
    orders, cohort = select_active_cohort(orders, int(run_config["active_sku_count"]))
    if cohort.empty:
        raise ValueError("No active SKUs remained after cleaning and splitting")
    skus = generate_skus(cohort["sku_id"].tolist(), int(run_config["random_seed"]))
    locations = generate_locations(config)
    baseline = allocate_baseline(skus, locations, config["rules"], int(config["baseline"]["primary_seed"]), int(config["baseline"]["restarts"]))
    validation = validate_assignment(skus, locations, baseline, config["rules"])
    if not validation["is_feasible"]:
        raise RuntimeError(f"Allocator produced invalid baseline: {validation['violations']}")
    abc = abc_analysis(orders)
    affinity = affinity_pairs(orders)
    candidate_counts = pd.DataFrame(
        [{"sku_id": sku_id, "eligible_bin_count": len(bins)} for sku_id, bins in static_candidates(skus, locations, config["rules"]).items()]
    )
    run_id = f"{run_config['name']}-{config_hash(config)}"
    output = Path(run_config["output_root"]) / run_id
    output.mkdir(parents=True, exist_ok=True)
    for name, frame in {
        "orders": orders, "cohort": cohort, "skus": skus, "locations": locations,
        "abc": abc, "affinity_pairs": affinity, "candidate_counts": candidate_counts, "baseline_assignments": baseline,
    }.items():
        frame.to_parquet(output / f"{name}.parquet", index=False)
    (output / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    manifest = {
        "run_id": run_id, "status": "completed", "created_at": datetime.now(UTC).isoformat(),
        "config_hash": config_hash(config), "source_file": str(source_path), "source_sha256": _file_hash(source_path),
        "cleaning": cleaning_report, "rows": {"orders": len(orders), "skus": len(skus), "locations": len(locations)},
        "split_order_counts": orders.groupby("split")["order_id"].nunique().to_dict(),
        "baseline_seed": config["baseline"]["primary_seed"], "is_feasible": validation["is_feasible"],
    }
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    attach_comparison(output, config)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the warehouse-slotting baseline artifact bundle")
    parser.add_argument("--config", default="configs/default.yaml", help="Path to YAML configuration")
    arguments = parser.parse_args()
    print(run(arguments.config))


if __name__ == "__main__":
    main()

