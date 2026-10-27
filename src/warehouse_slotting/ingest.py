"""Transaction ingestion, cleaning, chronological splitting, and cohort selection."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {"Invoice", "StockCode", "Quantity", "InvoiceDate"}


def read_online_retail_zip(path: str | Path, sheet_name: str) -> pd.DataFrame:
    """Read the configured UCI workbook sheet from its zip archive."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != 1 or not names[0].lower().endswith(".xlsx"):
            raise ValueError("Expected exactly one .xlsx workbook in source archive")
        with archive.open(names[0]) as workbook:
            frame = pd.read_excel(workbook, sheet_name=sheet_name)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Source is missing columns: {sorted(missing)}")
    return frame


def clean_orders(source: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Clean UCI line items without requiring a customer identifier."""
    original_count = len(source)
    frame = source.copy()
    frame.columns = [str(column).strip() for column in frame.columns]
    frame["Invoice"] = frame["Invoice"].astype("string").str.strip()
    frame["StockCode"] = frame["StockCode"].astype("string").str.strip()
    frame["InvoiceDate"] = pd.to_datetime(frame["InvoiceDate"], errors="coerce")
    valid = (
        frame["Invoice"].notna()
        & frame["StockCode"].notna()
        & frame["InvoiceDate"].notna()
        & (pd.to_numeric(frame["Quantity"], errors="coerce") > 0)
        & ~frame["Invoice"].str.upper().str.startswith("C", na=False)
    )
    filtered = frame.loc[valid, ["Invoice", "StockCode", "Quantity", "InvoiceDate"]].copy()
    filtered["Quantity"] = filtered["Quantity"].astype("int64")
    before_duplicates = len(filtered)
    filtered = filtered.drop_duplicates()
    grouped = (
        filtered.groupby(["Invoice", "StockCode"], as_index=False)
        .agg(quantity=("Quantity", "sum"), timestamp=("InvoiceDate", "min"))
        .rename(columns={"Invoice": "order_id", "StockCode": "sku_id"})
    )
    result = grouped.sort_values(["timestamp", "order_id", "sku_id"], kind="stable").reset_index(drop=True)
    report = {
        "source_rows": original_count,
        "rows_after_validity_filter": before_duplicates,
        "exact_duplicates_removed": before_duplicates - len(filtered),
        "canonical_order_lines": len(result),
    }
    return result, report


def chronological_split(orders: pd.DataFrame, fractions: dict[str, float]) -> pd.DataFrame:
    """Assign complete timestamp groups to chronological train/validation/test splits."""
    if not abs(sum(fractions.values()) - 1.0) < 1e-9:
        raise ValueError("Split fractions must sum to one")
    order_times = orders.groupby("order_id", as_index=False)["timestamp"].min().sort_values("timestamp")
    timestamp_counts = order_times.groupby("timestamp", as_index=False).size().rename(columns={"size": "orders"})
    total = len(order_times)
    train_target = total * fractions["train"]
    validation_target = total * (fractions["train"] + fractions["validation"])
    cumulative = timestamp_counts["orders"].cumsum()
    timestamp_counts["split"] = "test"
    timestamp_counts.loc[cumulative <= train_target, "split"] = "train"
    timestamp_counts.loc[(cumulative > train_target) & (cumulative <= validation_target), "split"] = "validation"
    if not (timestamp_counts["split"] == "train").any() or not (timestamp_counts["split"] == "test").any():
        raise ValueError("Not enough timestamp groups for chronological split")
    order_splits = order_times.merge(timestamp_counts[["timestamp", "split"]], on="timestamp", validate="many_to_one")
    return orders.merge(order_splits[["order_id", "split"]], on="order_id", validate="many_to_one")


def select_active_cohort(orders: pd.DataFrame, limit: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select active SKU IDs solely from train order frequency and filter all splits."""
    train = orders.loc[orders["split"] == "train"]
    frequency = train.groupby("sku_id")["order_id"].nunique().rename("pick_frequency")
    selected = frequency.rename_axis("sku_id").reset_index().sort_values(
        ["pick_frequency", "sku_id"], ascending=[False, True], kind="stable"
    ).head(limit)
    cohort = set(selected["sku_id"])
    filtered = orders.loc[orders["sku_id"].isin(cohort)].copy()
    surviving_orders = filtered["order_id"].unique()
    filtered = filtered.loc[filtered["order_id"].isin(surviving_orders)].reset_index(drop=True)
    return filtered, selected

