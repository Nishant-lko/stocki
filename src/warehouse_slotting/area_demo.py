"""Deterministic synthetic area/warehouse demo for the home finder."""

from __future__ import annotations

import math
import random

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
    # Rejection sampling makes a compact synthetic service area with no visible
    # row/column structure and enough separation for the map markers to read.
    rng = random.Random(25)
    coordinates: list[tuple[float, float]] = []
    while len(coordinates) < len(names):
        point = (rng.uniform(0.25, 3.75), rng.uniform(0.25, 3.75))
        if all(math.dist(point, existing) >= 0.62 for existing in coordinates):
            coordinates.append(point)
    for index, name in enumerate(names):
        warehouse_id = f"WH-{index + 1:02d}"
        capability = capabilities[index] if index < len(capabilities) else "Cold + Fragile + General"
        x, y = coordinates[index]
        warehouse_rows.append((warehouse_id, name, x, y, capability))
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


def synthetic_area_analytics(warehouses: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    """Create a clearly synthetic 30-day demand and stock snapshot for the demo."""
    rng = random.Random(2026)
    monthly_demand = {"P-101": 460, "P-102": 380, "P-103": 165, "P-104": 330, "P-105": 290}
    rows = []
    for warehouse in warehouses.itertuples(index=False):
        area_factor = rng.uniform(0.62, 1.42)
        for product in products.itertuples(index=False):
            if product.handling not in warehouse.type:
                continue
            units_sold = max(1, round(monthly_demand[product.product_id] * area_factor * rng.uniform(0.72, 1.28)))
            # A portion of locations have less than a week's modeled cover.
            cover_ratio = rng.uniform(0.05, 1.35)
            stock_on_hand = 0 if cover_ratio < 0.16 else round(units_sold * cover_ratio)
            rows.append({
                "warehouse_id": warehouse.warehouse_id,
                "warehouse": warehouse.name,
                "product_id": product.product_id,
                "product": product.product,
                "units_sold_30d": units_sold,
                "stock_on_hand": stock_on_hand,
                "days_cover": round(30 * stock_on_hand / units_sold, 1),
            })
    return pd.DataFrame(rows)

