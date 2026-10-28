"""Deterministic synthetic area/warehouse demo for the home finder."""

from __future__ import annotations

import pandas as pd


def synthetic_area_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return synthetic area points, products, and their ranked warehouse options."""
    names = ["North Hub", "East Hub", "Central Hub", "South Hub", "West Hub", "Airport Hub",
             "River Hub", "Garden Hub", "Market Hub", "Hill Hub", "Lake Hub", "Metro Hub",
             "Valley Hub", "Harbor Hub", "Park Hub", "Cedar Hub", "Maple Hub", "Sunrise Hub",
             "Meadow Hub", "Bridge Hub", "Summit Hub", "Oak Hub", "Pine Hub", "Coast Hub", "Field Hub"]
    capabilities = ["Fragile + General", "Cold + General", "Cold + General", "Fragile + General",
                    "General", "Cold + Fragile"]
    warehouse_rows = []
    for index, name in enumerate(names):
        warehouse_id = f"WH-{index + 1:02d}"
        capability = capabilities[index] if index < len(capabilities) else "Cold + Fragile + General"
        warehouse_rows.append((warehouse_id, name, index % 5, 4 - index // 5, capability))
    warehouses = pd.DataFrame(warehouse_rows, columns=["warehouse_id", "name", "x", "y", "type"])
    products = pd.DataFrame([
        ("P-101", "Everyday mugs", "General"),
        ("P-102", "Berry yogurt", "Cold"),
        ("P-103", "Glass vase", "Fragile"),
        ("P-104", "Cotton towels", "General"),
        ("P-105", "Fresh juice", "Cold"),
    ], columns=["product_id", "product", "handling"])
    ranks = {
        "P-101": ["WH-03", "WH-01", "WH-05"],
        "P-102": ["WH-02", "WH-06", "WH-03"],
        "P-103": ["WH-04", "WH-06", "WH-01"],
        "P-104": ["WH-05", "WH-03", "WH-01"],
        "P-105": ["WH-06", "WH-02", "WH-03"],
    }
    option_rows = []
    for product_id, ordered in ranks.items():
        for rank, warehouse_id in enumerate(ordered, start=1):
            option_rows.append((product_id, warehouse_id, rank, rank + 1, rank))
    options = pd.DataFrame(option_rows, columns=["product_id", "warehouse_id", "rank", "aisle", "bin"])
    return warehouses, products, options

