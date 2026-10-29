"""Reproducible synthetic event data for the judge-ready warehouse demo."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from warehouse_slotting.synthesize import generate_locations


EVENT_ID = "festival-gifting-week"
EVENT_NAME = "Festival gifting promotion (synthetic)"
EVENT_START = pd.Timestamp("2027-10-18")
EVENT_DAYS = 7
SEED = 20261029


def build_demo_tables(config: dict) -> dict[str, pd.DataFrame]:
    """Build orders, physical master, topology, and a forecast with visible provenance."""
    rng = np.random.default_rng(SEED)
    sku_count = 150
    families = [
        "Festival gift box", "Home decoration", "Gift wrap", "Tableware", "Storage",
        "Kitchen tools", "Personal care", "Stationery", "Medical supplies", "Flammable goods",
    ]
    family_for = np.arange(sku_count) % len(families)
    family_name = np.array(families)[family_for]
    sku_ids = [f"DEMO-{index + 1:03d}" for index in range(sku_count)]
    event_relevant_families = {"Festival gift box", "Home decoration", "Gift wrap", "Tableware"}
    event_tagged = np.isin(family_name, list(event_relevant_families))
    event_uplift = np.where(event_tagged, 3.0, 1.0)

    categories = np.array(
        ["normal"] * 92 + ["fragile"] * 25 + ["medical"] * 11 + ["fire"] * 11 + ["hazardous"] * 11
    )
    rng.shuffle(categories)
    descriptions = [f"{family_name[index]} {index + 1:02d}" for index in range(sku_count)]
    physical_rows = []
    for index, sku_id in enumerate(sku_ids):
        category = categories[index]
        width, height, depth = [int(value) for value in rng.integers(7, 16, size=3)]
        weight = round(float(rng.uniform(0.25, 3.5)), 2)
        if category == "fragile":
            width, height, depth = [int(value) for value in rng.integers(8, 14, size=3)]
            on_hand = 12
        else:
            on_hand = 24
        if index % 41 == 0:
            weight = 9.2
        event_tags = EVENT_ID if event_tagged[index] else ""
        physical_rows.append(
            {
                "sku_id": sku_id,
                "description": descriptions[index],
                "family": family_name[index],
                "event_tags": event_tags,
                "width_cm": width,
                "height_cm": height,
                "depth_cm": depth,
                "unit_weight_kg": weight,
                "category": category,
                "hazard_class": "isolated" if category == "hazardous" else "none",
                "handling_type": {
                    "normal": "normal", "fragile": "fragile", "medical": "medical",
                    "fire": "fire_risk", "hazardous": "hazmat",
                }[category],
                "on_hand_qty": on_hand,
                "reserve_qty": 180 if event_tagged[index] else 80,
                "supplier_lead_days": 4 if event_tagged[index] else 2,
                "allowed_orientations": "012" if category == "fragile" else "012;021;102;120;201;210",
                "stackable": 0 if category == "fragile" else 1,
            }
        )
    skus = pd.DataFrame(physical_rows)

    # A Zipf-like head, grouped baskets, and two historical repetitions of the event.
    # A calibrated Zipf-like head produces an approximately 80/20 order
    # concentration after basket deduplication and the seeded event weeks.
    raw_rank_weights = 1 / (np.arange(1, sku_count + 1, dtype=float) ** 1.30)
    raw_rank_weights /= raw_rank_weights.sum()
    family_weights = np.array([raw_rank_weights[family_for == family].sum() for family in range(len(families))])
    family_weights /= family_weights.sum()
    historical_events = [
        (pd.Timestamp("2024-10-21"), pd.Timestamp("2024-10-27")),
        (pd.Timestamp("2025-10-20"), pd.Timestamp("2025-10-26")),
    ]
    order_rows: list[dict[str, object]] = []
    next_order = 1
    dates = pd.date_range("2024-01-01", "2025-12-31", freq="D")
    for day in dates:
        is_event = any(start <= day <= end for start, end in historical_events)
        orders_today = int(rng.poisson(34 * (1.25 if is_event else 1.0)))
        for _ in range(orders_today):
            size = min(5, 1 + int(rng.poisson(1.25)))
            family_probabilities = family_weights.copy()
            if is_event:
                for family_index, family in enumerate(families):
                    if family in event_relevant_families:
                        family_probabilities[family_index] *= 2.6
                family_probabilities /= family_probabilities.sum()
            primary_family = int(rng.choice(len(families), p=family_probabilities))
            selected: list[int] = []
            for _item in range(size):
                family_index = primary_family
                if rng.random() < 0.18:
                    family_index = int(rng.choice(len(families), p=family_probabilities))
                members = np.flatnonzero(family_for == family_index)
                probabilities = raw_rank_weights[members].copy()
                if is_event and families[family_index] in event_relevant_families:
                    probabilities *= 3.0
                probabilities /= probabilities.sum()
                picked = int(rng.choice(members, p=probabilities))
                if picked not in selected:
                    selected.append(picked)
            order_id = f"FEST-{next_order:07d}"
            next_order += 1
            for picked in selected:
                order_rows.append(
                    {
                        "order_id": order_id,
                        "sku_id": sku_ids[picked],
                        "quantity": int(rng.choice([1, 1, 1, 2])),
                        "timestamp": day + pd.Timedelta(seconds=int(rng.integers(0, 86400))),
                    }
                )
    orders = pd.DataFrame(order_rows)

    # Monte Carlo forecast is explicitly synthetic and generated independently of historical orders.
    forecast_rng = np.random.default_rng(SEED + 1)
    simulated_orders = 120_000
    daily_order_rate = 34.0

    def expected_baskets(event: bool) -> np.ndarray:
        result = np.zeros(sku_count, dtype=float)
        probs = family_weights.copy()
        if event:
            for family_index, family in enumerate(families):
                if family in event_relevant_families:
                    probs[family_index] *= 2.6
            probs /= probs.sum()
        for _ in range(simulated_orders):
            size = min(5, 1 + int(forecast_rng.poisson(1.25)))
            primary = int(forecast_rng.choice(len(families), p=probs))
            selected = set()
            for _item in range(size):
                family_index = primary if forecast_rng.random() >= 0.18 else int(forecast_rng.choice(len(families), p=probs))
                members = np.flatnonzero(family_for == family_index)
                probabilities = raw_rank_weights[members]
                if event and families[family_index] in event_relevant_families:
                    probabilities = probabilities * 3.0
                probabilities = probabilities / probabilities.sum()
                selected.add(int(forecast_rng.choice(members, p=probabilities)))
            result[list(selected)] += 1.0
        return result / simulated_orders * daily_order_rate * EVENT_DAYS * (1.25 if event else 1.0)

    baseline_expected = expected_baskets(False)
    scenario_expected = expected_baskets(True)
    forecast = pd.DataFrame(
        {
            "sku_id": sku_ids,
            "description": descriptions,
            "family": family_name,
            "event_id": EVENT_ID,
            "event_name": EVENT_NAME,
            "event_start": EVENT_START.date().isoformat(),
            "scenario_days": EVENT_DAYS,
            "baseline_expected_orders": np.ceil(baseline_expected).astype(int),
            "expected_orders": np.ceil(scenario_expected).astype(int),
            "scenario_multiplier": np.divide(
                scenario_expected,
                np.maximum(baseline_expected, 1e-6),
            ).round(2),
            "forecast_source": "Synthetic event calendar and seeded basket simulator",
        }
    )
    events = pd.DataFrame(
        [
            {"event_id": EVENT_ID, "event_name": EVENT_NAME, "start_date": date.date().isoformat(),
             "end_date": (date + pd.Timedelta(days=EVENT_DAYS - 1)).date().isoformat(),
             "event_type": kind, "provenance": "synthetic seeded scenario"}
            for date, kind in [(historical_events[0][0], "historical"),
                               (historical_events[1][0], "historical"),
                               (EVENT_START, "forecast")]
        ]
    )
    return {
        "orders": orders,
        "skus": skus,
        "locations": generate_locations(config),
        "forecast": forecast,
        "events": events,
    }


def write_demo_dataset(config: dict, directory: str | Path) -> dict[str, Path]:
    """Write the reproducible demonstration inputs as simple CSV files."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    tables = build_demo_tables(config)
    files = {
        "orders": "festival_orders.csv",
        "skus": "festival_skus.csv",
        "locations": "festival_locations.csv",
        "forecast": "festival_forecast.csv",
        "events": "festival_events.csv",
    }
    result = {}
    for name, filename in files.items():
        path = target / filename
        tables[name].to_csv(path, index=False)
        result[name] = path
    return result


def build_affinity_showcase_tables(config: dict) -> dict[str, pd.DataFrame]:
    """Seeded basket clusters that expose a route benefit beyond frequency sorting.

    SKU IDs interleave four equally popular families. A nearest-bin frequency sort
    therefore mixes families, while a route-aware plan can group products commonly
    picked in the same order. Test orders are generated later in the same process,
    never read by the layout selector.
    """
    rng = np.random.default_rng(20261030)
    count = 150
    names = ("Gift kits", "Home decor", "Kitchen sets", "Party supplies")
    sku_rows = []
    for index in range(count):
        family = names[index % len(names)]
        sku_rows.append({
            "sku_id": f"SHOW-{index + 1:03d}",
            "description": f"{family} item {index // len(names) + 1:02d}",
            "family": family,
            "width_cm": 10, "height_cm": 10, "depth_cm": 10,
            "unit_weight_kg": 0.5, "category": "normal",
            "hazard_class": "none", "handling_type": "normal",
            "on_hand_qty": 12, "allowed_orientations": "012;021;102;120;201;210",
            "stackable": 1,
        })
    skus = pd.DataFrame(sku_rows)
    members = [np.arange(family, count, len(names)) for family in range(len(names))]
    rows = []
    order_number = 0
    for day in pd.date_range("2025-01-01", periods=120):
        for _ in range(60):
            order_number += 1
            family = int(rng.integers(0, len(names)))
            # Correlated baskets make aisle grouping matter; rank popularity is
            # intentionally similar across families, without encoding a layout.
            picks = rng.choice(members[family], size=5, replace=False)
            timestamp = day + pd.Timedelta(seconds=int(rng.integers(0, 86400)))
            for picked in picks:
                rows.append({"order_id": f"SHOW-{order_number:07d}",
                             "sku_id": f"SHOW-{int(picked) + 1:03d}",
                             "quantity": 1, "timestamp": timestamp})
    return {"orders": pd.DataFrame(rows), "skus": skus,
            "locations": generate_locations(config)}


def write_affinity_showcase_dataset(config: dict, directory: str | Path) -> dict[str, Path]:
    """Write the three synthetic input tables for the economic showcase."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, frame in build_affinity_showcase_tables(config).items():
        path = target / f"affinity_showcase_{name}.csv"
        frame.to_csv(path, index=False)
        files[name] = path
    return files
