import sqlite3

import pandas as pd
import pytest

from warehouse_slotting.database import (
    connect, count, delete_row, export_tables, get_row, initialize, save_row,
)


def test_database_crud_preserves_referenced_skus_and_exports_edits(tmp_path):
    tables = {
        "orders": pd.DataFrame([{"order_id": "O1", "sku_id": "A", "quantity": 1,
                                 "timestamp": "2025-01-01"}]),
        "skus": pd.DataFrame([{"sku_id": "A", "width_cm": 10, "height_cm": 10,
                               "depth_cm": 10, "unit_weight_kg": 1.0, "on_hand_qty": 5}]),
        "locations": pd.DataFrame([{"location_id": "B1", "bin_width_cm": 20,
                                    "bin_height_cm": 20, "bin_depth_cm": 20,
                                    "bin_max_weight_kg": 10.0,
                                    "shelf_max_weight_kg": 20.0,
                                    "rack_max_weight_kg": 40.0}]),
    }
    path = tmp_path / "warehouse.sqlite"
    initialize(path, tables=tables)
    initialize(path, tables=tables)
    with connect(path) as connection:
        assert count(connection, "orders") == 1
        with pytest.raises(ValueError, match="used by orders"):
            delete_row(connection, "skus", ("A",))
        sku = get_row(connection, "skus", ("A",))
        sku["on_hand_qty"] = "8"
        save_row(connection, "skus", sku, ("A",))
        with pytest.raises(sqlite3.IntegrityError):
            save_row(connection, "orders", get_row(connection, "orders", ("O1", "A")))
        assert count(connection, "orders") == 1
        exported = export_tables(connection, tmp_path / "export")
        assert pd.read_csv(exported["skus"]).loc[0, "on_hand_qty"] == 8
        delete_row(connection, "orders", ("O1", "A"))
        delete_row(connection, "skus", ("A",))
        assert count(connection, "skus") == 0
