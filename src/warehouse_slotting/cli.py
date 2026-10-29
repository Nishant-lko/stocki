"""Command-line entry point for the reproducible baseline pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from warehouse_slotting.baseline import allocate_baseline
from warehouse_slotting.compatibility import normalize_category
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

PIPELINE_VERSION = "slotwise-2026-10-29-3"


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
        cleaned["timestamp"] = pd.date_range(
            "2020-01-01", periods=len(cleaned), freq="60min"
        ).to_numpy()
    cleaned["order_id"] = cleaned["order_id"].astype("string").str.strip()
    cleaned["sku_id"] = cleaned["sku_id"].astype("string").str.strip()
    cleaned["quantity"] = pd.to_numeric(cleaned["quantity"], errors="coerce")
    cleaned["timestamp"] = pd.to_datetime(cleaned["timestamp"], errors="coerce")
    valid = (
        cleaned["order_id"].notna()
        & cleaned["sku_id"].notna()
        & cleaned["timestamp"].notna()
        & (cleaned["quantity"] > 0)
        & np.isfinite(cleaned["quantity"])
        & (cleaned["quantity"] == np.floor(cleaned["quantity"]))
    )
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


def read_sku_master(path: Path, sku_ids: list[str], seed: int) -> pd.DataFrame:
    """Merge a supplied physical SKU profile onto demand-selected products."""
    master = pd.read_csv(path)
    master.columns = [str(column).strip().lower() for column in master.columns]
    required = {
        "sku_id",
        "width_cm",
        "height_cm",
        "depth_cm",
        "unit_weight_kg",
        "category",
        "hazard_class",
        "handling_type",
        "on_hand_qty",
    }
    missing = required - set(master.columns)
    if missing:
        raise ValueError(f"SKU master is missing columns: {sorted(missing)}")
    master["sku_id"] = master["sku_id"].astype("string").str.strip()
    if master["sku_id"].isna().any() or master["sku_id"].duplicated().any():
        raise ValueError("SKU master sku_id values must be present and unique")
    absent = sorted(set(sku_ids) - set(master["sku_id"].astype(str)))
    if absent:
        raise ValueError(
            f"SKU master has no physical profile for {len(absent)} order SKUs; examples: {absent[:8]}"
        )
    master = master.loc[master["sku_id"].isin(sku_ids)].copy()
    for column in ("width_cm", "height_cm", "depth_cm", "unit_weight_kg", "on_hand_qty"):
        master[column] = pd.to_numeric(master[column], errors="coerce")
        if (
            master[column].isna().any()
            or not np.isfinite(master[column]).all()
            or (master[column] <= 0).any()
        ):
            raise ValueError(f"SKU master {column} values must be positive numbers")
    if not np.equal(master["on_hand_qty"], np.floor(master["on_hand_qty"])).all():
        raise ValueError("SKU master on_hand_qty values must be whole numbers")
    master["on_hand_qty"] = master["on_hand_qty"].astype(int)
    for column in ("reserve_qty", "supplier_lead_days"):
        if column not in master:
            continue
        master[column] = pd.to_numeric(master[column], errors="coerce")
        if (
            master[column].isna().any()
            or not np.isfinite(master[column]).all()
            or (master[column] < 0).any()
            or not np.equal(master[column], np.floor(master[column])).all()
        ):
            raise ValueError(f"SKU master {column} values must be non-negative whole numbers")
        master[column] = master[column].astype(int)
    try:
        master["category"] = master["category"].map(normalize_category)
    except ValueError as error:
        raise ValueError(f"SKU master {error}") from error
    for column in ("category", "hazard_class", "handling_type"):
        master[column] = master[column].astype("string").str.strip().str.lower()
        if master[column].isna().any() or master[column].eq("").any():
            raise ValueError(f"SKU master {column} values must be present")
    if "allowed_orientations" not in master:
        master["allowed_orientations"] = "012;021;102;120;201;210"
    master["allowed_orientations"] = master["allowed_orientations"].astype("string").str.strip()
    if master["allowed_orientations"].isna().any() or master["allowed_orientations"].eq("").any():
        raise ValueError("SKU master allowed_orientations must be non-empty when provided")
    if "stackable" not in master:
        master["stackable"] = 1
    master["stackable"] = pd.to_numeric(master["stackable"], errors="coerce")
    if master["stackable"].isna().any() or not master["stackable"].isin([0, 1]).all():
        raise ValueError("SKU master stackable values must be 0 or 1")
    master["stackable"] = master["stackable"].astype(int)
    generated = generate_skus(sku_ids, seed)
    keep = [
        "sku_id",
        "width_cm",
        "height_cm",
        "depth_cm",
        "unit_weight_kg",
        "category",
        "hazard_class",
        "handling_type",
        "on_hand_qty",
        "allowed_orientations",
        "stackable",
    ]
    keep.extend(
        column
        for column in (
            "description",
            "family",
            "event_tags",
            "event_uplift",
            "reserve_qty",
            "supplier_lead_days",
        )
        if column in master and column not in keep
    )
    merged = generated.drop(
        columns=[column for column in keep if column in generated and column != "sku_id"]
    ).merge(
        master[keep], on="sku_id", how="left", validate="one_to_one", suffixes=("_generated", "")
    )
    merged["unit_volume_cm3"] = (
        (merged["width_cm"] * merged["height_cm"] * merged["depth_cm"]).round().astype(int)
    )
    if "description" not in merged:
        merged["description"] = merged["sku_id"].map(lambda value: f"Product {value}")
    return merged.sort_values("sku_id").reset_index(drop=True)


def read_location_master(path: Path, config: dict) -> pd.DataFrame:
    """Read and validate a location CSV for the configured parallel-aisle model."""
    locations = pd.read_csv(path)
    locations.columns = [str(column).strip().lower() for column in locations.columns]
    required = {
        "location_id", "zone", "aisle_number", "rack_id", "shelf_id", "bay",
        "shelf_level", "x_m", "y_m", "z_m", "bin_width_cm", "bin_height_cm",
        "bin_depth_cm", "volumetric_capacity_cm3", "bin_max_weight_kg",
        "shelf_max_weight_kg", "rack_max_weight_kg", "is_golden_zone", "risk_zone",
    }
    missing = required - set(locations.columns)
    if missing:
        raise ValueError(f"Warehouse locations file is missing columns: {sorted(missing)}")
    for column in ("location_id", "zone", "rack_id", "shelf_id"):
        locations[column] = locations[column].astype("string").str.strip()
        if locations[column].isna().any() or locations[column].eq("").any():
            raise ValueError(f"Warehouse locations {column} values must be present")
    if locations["location_id"].duplicated().any():
        raise ValueError("Warehouse location_id values must be unique")
    for column in (
        "aisle_number", "bay", "shelf_level", "x_m", "y_m", "z_m", "bin_width_cm",
        "bin_height_cm", "bin_depth_cm", "volumetric_capacity_cm3", "bin_max_weight_kg",
        "shelf_max_weight_kg", "rack_max_weight_kg",
    ):
        locations[column] = pd.to_numeric(locations[column], errors="coerce")
        if locations[column].isna().any() or not np.isfinite(locations[column]).all():
            raise ValueError(f"Warehouse locations {column} values must be finite numbers")
    integer_columns = ("aisle_number", "bay", "shelf_level")
    for column in integer_columns:
        if (locations[column] < 0).any() or not np.equal(locations[column], np.floor(locations[column])).all():
            raise ValueError(f"Warehouse locations {column} values must be non-negative whole numbers")
        locations[column] = locations[column].astype(int)
    positive_columns = (
        "bin_width_cm", "bin_height_cm", "bin_depth_cm", "volumetric_capacity_cm3",
        "bin_max_weight_kg", "shelf_max_weight_kg", "rack_max_weight_kg",
    )
    if (locations[list(positive_columns)] <= 0).any().any():
        raise ValueError("Warehouse bin dimensions and capacities must be positive")
    expected_volume = locations["bin_width_cm"] * locations["bin_height_cm"] * locations["bin_depth_cm"]
    if (locations["volumetric_capacity_cm3"] > expected_volume + 1e-6).any():
        raise ValueError("volumetric_capacity_cm3 cannot exceed bin_width_cm × bin_height_cm × bin_depth_cm")
    if locations["is_golden_zone"].dtype != bool:
        normalized = locations["is_golden_zone"].astype("string").str.strip().str.lower()
        if not normalized.isin(["true", "false", "1", "0"]).all():
            raise ValueError("is_golden_zone values must be true/false or 1/0")
        locations["is_golden_zone"] = normalized.isin(["true", "1"])
    if locations["risk_zone"].dtype != bool:
        normalized = locations["risk_zone"].astype("string").str.strip().str.lower()
        if not normalized.isin(["true", "false", "1", "0"]).all():
            raise ValueError("risk_zone values must be true/false or 1/0")
        locations["risk_zone"] = normalized.isin(["true", "1"])
    warehouse = config["warehouse"]
    aisles = sorted(locations["aisle_number"].unique().tolist())
    if aisles != list(range(int(warehouse["aisle_count"]))):
        raise ValueError(
            "Warehouse locations must use every configured aisle number exactly as a zero-based range "
            f"0–{int(warehouse['aisle_count']) - 1}"
        )
    front = float(warehouse["front_cross_aisle_y_m"])
    rear = float(warehouse["rear_cross_aisle_y_m"])
    if rear <= front or (locations["y_m"] < front).any() or (locations["y_m"] > rear).any():
        raise ValueError("Warehouse y_m coordinates must fall between the configured front and rear cross-aisles")
    aisle_center_x = locations["aisle_number"] * float(warehouse["aisle_spacing_m"])
    if ((locations["x_m"] - aisle_center_x).abs() > float(warehouse["aisle_spacing_m"]) / 2).any():
        raise ValueError(
            "Warehouse x_m coordinates do not match the configured parallel-aisle spacing; "
            "each bin must lie within half an aisle spacing of its aisle centerline"
        )
    if int(warehouse["depot_aisle"]) not in aisles:
        raise ValueError("Configured depot_aisle is not present in the uploaded warehouse")
    if (locations.groupby("shelf_id")["rack_id"].nunique() > 1).any() or (
        locations.groupby("shelf_id")["shelf_level"].nunique() > 1
    ).any():
        raise ValueError("Each shelf_id must identify one rack and one shelf level")
    if (locations.groupby("rack_id")["aisle_number"].nunique() > 1).any():
        raise ValueError("Each rack_id must belong to one aisle")
    for id_column, capacity_column in (
        ("shelf_id", "shelf_max_weight_kg"),
        ("rack_id", "rack_max_weight_kg"),
    ):
        if (locations.groupby(id_column)[capacity_column].nunique() > 1).any():
            raise ValueError(f"Every {id_column} must have one consistent {capacity_column}")
    if (locations["bin_max_weight_kg"] > locations["shelf_max_weight_kg"]).any() or (
        locations["shelf_max_weight_kg"] > locations["rack_max_weight_kg"]
    ).any():
        raise ValueError("Capacity limits must satisfy bin ≤ shelf ≤ rack")
    locations["zone"] = locations["zone"].astype(str).str.strip()
    if locations["zone"].eq("").any():
        raise ValueError("Warehouse zone values must be present")
    return locations.sort_values("location_id").reset_index(drop=True)


def run(
    config_path: str | Path,
    orders_csv: Path | None = None,
    run_name: str | None = None,
    sku_master_csv: Path | None = None,
    locations_csv: Path | None = None,
    orders_label: str | None = None,
    sku_master_label: str | None = None,
    locations_label: str | None = None,
) -> Path:
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
        cleaning_report["source_label"] = orders_label or source_path.name
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
    skus = (
        read_sku_master(
            sku_master_csv, cohort["sku_id"].astype(str).tolist(), int(run_config["random_seed"])
        )
        if sku_master_csv is not None
        else generate_skus(cohort["sku_id"].tolist(), int(run_config["random_seed"]))
    )
    locations = (
        read_location_master(locations_csv, config)
        if locations_csv is not None
        else generate_locations(config)
    )
    baseline = allocate_baseline(
        skus,
        locations,
        config["rules"],
        int(config["baseline"]["primary_seed"]),
        int(config["baseline"]["restarts"]),
    )
    validation = validate_assignment(skus, locations, baseline, config["rules"])
    if not validation["is_feasible"]:
        raise RuntimeError(f"Allocator produced invalid baseline: {validation['violations']}")
    abc = abc_analysis(orders)
    affinity = affinity_pairs(orders)
    candidate_counts = pd.DataFrame(
        [
            {"sku_id": sku_id, "eligible_bin_count": len(bins)}
            for sku_id, bins in static_candidates(skus, locations, config["rules"]).items()
        ]
    )
    input_hashes = {
        "orders": _file_hash(source_path),
        "sku_master": _file_hash(sku_master_csv) if sku_master_csv is not None else None,
        "locations": _file_hash(locations_csv) if locations_csv is not None else None,
    }
    identity = hashlib.sha256(
        json.dumps(
            {"config": config_hash(config), "pipeline_version": PIPELINE_VERSION, **input_hashes},
            sort_keys=True,
        ).encode()
    ).hexdigest()[:16]
    run_id = f"{run_config['name']}-{identity}"
    output = Path(run_config["output_root"]) / run_id
    if output.exists():
        manifest_path = output / "run_manifest.json"
        comparison_path = output / "comparison_metrics.json"
        if manifest_path.exists() and comparison_path.exists():
            existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing_manifest.get("status") == "completed":
                return output
        raise FileExistsError(
            f"Run directory {output} already exists but is incomplete; it was left untouched"
        )
    output.mkdir(parents=True, exist_ok=False)
    for name, frame in {
        "orders": orders,
        "cohort": cohort,
        "skus": skus,
        "locations": locations,
        "abc": abc,
        "affinity_pairs": affinity,
        "candidate_counts": candidate_counts,
        "baseline_assignments": baseline,
    }.items():
        frame.to_parquet(output / f"{name}.parquet", index=False)
    (output / "config_snapshot.json").write_text(
        json.dumps(config, indent=2, sort_keys=True), encoding="utf-8"
    )
    (output / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    manifest = {
        "run_id": run_id,
        "pipeline_version": PIPELINE_VERSION,
        "status": "running",
        "created_at": datetime.now(UTC).isoformat(),
        "config_hash": config_hash(config),
        "source_file": orders_label or str(source_path),
        "source_sha256": input_hashes["orders"],
        "input_sha256": input_hashes,
        "cleaning": cleaning_report,
        "rows": {"orders": len(orders), "skus": len(skus), "locations": len(locations)},
        "split_order_counts": orders.groupby("split")["order_id"].nunique().to_dict(),
        "baseline_seed": config["baseline"]["primary_seed"],
        "is_feasible": validation["is_feasible"],
        "physical_attributes_source": "uploaded SKU master"
        if sku_master_csv is not None
        else "synthetic SKU master",
        "sku_master_source_file": sku_master_label if sku_master_csv is not None else None,
        "sku_master_source_sha256": _file_hash(sku_master_csv)
        if sku_master_csv is not None
        else None,
        "warehouse_layout_source": locations_label if locations_csv is not None else "synthetic configured aisle topology",
        "warehouse_layout_source_sha256": input_hashes["locations"],
    }
    manifest_path = output / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    try:
        attach_comparison(output, config)
    except Exception as error:
        manifest["status"] = "failed"
        manifest["error"] = str(error)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        raise
    manifest["status"] = "completed"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the warehouse-slotting baseline artifact bundle"
    )
    parser.add_argument(
        "--config", default="configs/default.yaml", help="Path to YAML configuration"
    )
    arguments = parser.parse_args()
    print(run(arguments.config))


if __name__ == "__main__":
    main()
