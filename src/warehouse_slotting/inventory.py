"""In-memory order picking and empty-pick-face recommendations for demos."""

from __future__ import annotations

import sqlite3
from typing import Any
from pathlib import Path

import pandas as pd

from warehouse_slotting.constraints import validate_assignment


def initialize_demo_database(
    path: str | Path,
    run_id: str,
    skus: pd.DataFrame,
    assignments: pd.DataFrame,
) -> None:
    """Create and seed the isolated, persistent demo inventory database."""
    database = Path(path)
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS demo_inventory (
                run_id TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                pick_face_qty INTEGER NOT NULL CHECK(pick_face_qty >= 0),
                reserve_qty INTEGER NOT NULL CHECK(reserve_qty >= 0),
                target_qty INTEGER NOT NULL CHECK(target_qty >= 0),
                PRIMARY KEY (run_id, sku_id)
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS demo_assignments (
                run_id TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                location_id TEXT NOT NULL,
                PRIMARY KEY (run_id, sku_id),
                UNIQUE (run_id, location_id)
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS demo_inventory_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                action TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                location_id TEXT NOT NULL DEFAULT '',
                requested_qty INTEGER NOT NULL DEFAULT 0,
                changed_qty INTEGER NOT NULL DEFAULT 0,
                pick_face_before INTEGER NOT NULL DEFAULT 0,
                pick_face_after INTEGER NOT NULL DEFAULT 0,
                reserve_after INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL
            )"""
        )
        for row in skus.itertuples(index=False):
            sku_id = str(row.sku_id)
            on_hand = max(0, int(row.on_hand_qty))
            reserve = max(0, int(getattr(row, "reserve_qty", 0)))
            connection.execute(
                """INSERT OR IGNORE INTO demo_inventory
                   (run_id, sku_id, pick_face_qty, reserve_qty, target_qty)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(run_id), sku_id, on_hand, reserve, on_hand),
            )
        connection.executemany(
            """INSERT OR IGNORE INTO demo_assignments (run_id, sku_id, location_id)
               VALUES (?, ?, ?)""",
            [
                (str(run_id), str(row.sku_id), str(row.location_id))
                for row in assignments.itertuples(index=False)
            ],
        )


def load_demo_inventory(path: str | Path, run_id: str) -> dict[str, dict[str, int]]:
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            """SELECT sku_id, pick_face_qty, reserve_qty, target_qty
               FROM demo_inventory WHERE run_id=? ORDER BY sku_id""",
            (str(run_id),),
        ).fetchall()
    return {
        str(sku): {"pick_face": int(face), "reserve": int(reserve), "target": int(target)}
        for sku, face, reserve, target in rows
    }


def load_demo_assignments(path: str | Path, run_id: str) -> pd.DataFrame:
    with sqlite3.connect(path) as connection:
        return pd.read_sql_query(
            "SELECT sku_id, location_id FROM demo_assignments WHERE run_id=? ORDER BY sku_id",
            connection,
            params=(str(run_id),),
        )


def save_demo_assignments(
    path: str | Path, run_id: str, assignments: pd.DataFrame
) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM demo_assignments WHERE run_id=?", (str(run_id),))
        connection.executemany(
            "INSERT INTO demo_assignments (run_id, sku_id, location_id) VALUES (?, ?, ?)",
            [
                (str(run_id), str(row.sku_id), str(row.location_id))
                for row in assignments.itertuples(index=False)
            ],
        )


def reset_demo_database(
    path: str | Path, run_id: str, skus: pd.DataFrame, assignments: pd.DataFrame
) -> None:
    with sqlite3.connect(path) as connection:
        for table in ("demo_inventory_events", "demo_inventory", "demo_assignments"):
            connection.execute(f"DELETE FROM {table} WHERE run_id=?", (str(run_id),))
    initialize_demo_database(path, run_id, skus, assignments)


def record_demo_pick(
    path: str | Path,
    run_id: str,
    sku_id: str,
    requested_qty: int,
    location_id: str,
) -> dict[str, Any]:
    """Atomically deduct a demo pick and append its transaction record."""
    requested = int(requested_qty)
    if requested < 1:
        raise ValueError("Pick quantity must be at least one")
    with sqlite3.connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT pick_face_qty, reserve_qty FROM demo_inventory WHERE run_id=? AND sku_id=?",
            (str(run_id), str(sku_id)),
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown demo SKU: {sku_id}")
        before, reserve = (int(row[0]), int(row[1]))
        changed = min(requested, before)
        after = before - changed
        status = "Picked" if changed == requested else (
            "Partial / stockout" if changed else "Depleted / stockout"
        )
        connection.execute(
            "UPDATE demo_inventory SET pick_face_qty=? WHERE run_id=? AND sku_id=?",
            (after, str(run_id), str(sku_id)),
        )
        connection.execute(
            """INSERT INTO demo_inventory_events
               (run_id, action, sku_id, location_id, requested_qty, changed_qty,
                pick_face_before, pick_face_after, reserve_after, status)
               VALUES (?, 'Pick', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(run_id), str(sku_id), str(location_id), requested, changed,
             before, after, reserve, status),
        )
    return {
        "sku_id": str(sku_id), "location_id": str(location_id),
        "requested_qty": requested, "changed_qty": changed,
        "unfulfilled_qty": requested - changed, "pick_face_before": before,
        "pick_face_after": after, "reserve_after": reserve, "status": status,
    }


def record_demo_refill(path: str | Path, run_id: str, sku_id: str, location_id: str) -> dict[str, Any]:
    """Atomically move reserve stock into the demo pick face and log the action."""
    with sqlite3.connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """SELECT pick_face_qty, reserve_qty, target_qty FROM demo_inventory
               WHERE run_id=? AND sku_id=?""",
            (str(run_id), str(sku_id)),
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown demo SKU: {sku_id}")
        before, reserve, target = map(int, row)
        changed = min(max(0, target - before), reserve)
        if changed <= 0:
            raise ValueError("There is no reserve stock available to refill this pick face")
        after = before + changed
        reserve_after = reserve - changed
        connection.execute(
            """UPDATE demo_inventory SET pick_face_qty=?, reserve_qty=?
               WHERE run_id=? AND sku_id=?""",
            (after, reserve_after, str(run_id), str(sku_id)),
        )
        connection.execute(
            """INSERT INTO demo_inventory_events
               (run_id, action, sku_id, location_id, changed_qty, pick_face_before,
                pick_face_after, reserve_after, status)
               VALUES (?, 'Refill', ?, ?, ?, ?, ?, ?, 'Refilled from reserve')""",
            (str(run_id), str(sku_id), str(location_id), changed,
             before, after, reserve_after),
        )
    return {
        "sku_id": str(sku_id), "location_id": str(location_id),
        "changed_qty": changed, "pick_face_before": before,
        "pick_face_after": after, "reserve_after": reserve_after,
        "status": "Refilled from reserve",
    }


def record_demo_reallocation(
    path: str | Path,
    run_id: str,
    retired_sku_id: str,
    replacement_sku_id: str,
    location_id: str,
    released_location_id: str,
) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """INSERT INTO demo_inventory_events
               (run_id, action, sku_id, location_id, status)
               VALUES (?, 'Reallocation', ?, ?, ?)""",
            (str(run_id), str(replacement_sku_id), str(location_id),
             f"{retired_sku_id} retired; replacement released {released_location_id}"),
        )


def load_demo_events(path: str | Path, run_id: str, limit: int = 50) -> pd.DataFrame:
    with sqlite3.connect(path) as connection:
        return pd.read_sql_query(
            """SELECT created_at, action, sku_id, location_id, requested_qty,
                      changed_qty, pick_face_before, pick_face_after, reserve_after, status
               FROM demo_inventory_events WHERE run_id=? ORDER BY event_id DESC LIMIT ?""",
            connection,
            params=(str(run_id), int(limit)),
        ).iloc[::-1].reset_index(drop=True)


def process_order_cycle(
    order_lines: pd.DataFrame,
    inventory: dict[str, dict[str, int]],
    assignments: pd.DataFrame,
) -> tuple[dict[str, dict[str, int]], list[dict[str, Any]]]:
    """Pick one basket from a simulated inventory snapshot without mutating inputs."""
    next_inventory = {key: dict(value) for key, value in inventory.items()}
    assigned = set(assignments["sku_id"].astype(str))
    grouped = order_lines.groupby("sku_id", as_index=False)["quantity"].sum()
    events: list[dict[str, Any]] = []
    for row in grouped.itertuples(index=False):
        sku_id = str(row.sku_id)
        requested = max(0, int(row.quantity))
        stock = next_inventory.get(sku_id, {"pick_face": 0, "reserve": 0})
        before = max(0, int(stock.get("pick_face", 0)))
        picked = min(requested, before) if sku_id in assigned else 0
        after = before - picked
        stock["pick_face"] = after
        next_inventory[sku_id] = stock
        status = (
            "No pick face" if sku_id not in assigned else
            "Picked" if picked == requested else
            "Partial / stockout" if picked > 0 else
            "Depleted / stockout"
        )
        events.append({
            "sku_id": sku_id,
            "requested_units": requested,
            "picked_units": picked,
            "unfulfilled_units": requested - picked,
            "stock_before": before,
            "stock_after": after,
            "status": status,
        })
    return next_inventory, events


def refill_pick_face(
    sku_id: str,
    inventory: dict[str, dict[str, int]],
    pick_face_targets: dict[str, int],
) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    """Transfer reserve units into a pick face up to its configured demo target."""
    key = str(sku_id)
    if key not in inventory:
        raise ValueError(f"Unknown SKU: {key}")
    result = {sku: dict(values) for sku, values in inventory.items()}
    stock = result[key]
    target = max(0, int(pick_face_targets.get(key, stock.get("pick_face", 0))))
    current = max(0, int(stock.get("pick_face", 0)))
    reserve = max(0, int(stock.get("reserve", 0)))
    transferred = min(max(0, target - current), reserve)
    if transferred <= 0:
        raise ValueError("There is no reserve stock to refill this pick face")
    stock["pick_face"] = current + transferred
    stock["reserve"] = reserve - transferred
    return result, {
        "sku_id": key,
        "units_transferred": transferred,
        "pick_face_after": stock["pick_face"],
        "reserve_after": stock["reserve"],
    }


def find_safe_reallocation(
    depleted_sku_id: str,
    skus: pd.DataFrame,
    locations: pd.DataFrame,
    assignments: pd.DataFrame,
    inventory: dict[str, dict[str, int]],
    abc: pd.DataFrame,
    rules: dict[str, Any],
) -> dict[str, Any] | None:
    """Find a fast-moving in-stock SKU that can safely take a retired empty face.

    This is advisory until the operator applies it. The depleted SKU is treated as
    retired in the simulated plan; production assignments and stock are untouched.
    """
    depleted = str(depleted_sku_id)
    assignments = assignments[["sku_id", "location_id"]].copy()
    assignments["sku_id"] = assignments["sku_id"].astype(str)
    assignments["location_id"] = assignments["location_id"].astype(str)
    current = assignments.set_index("sku_id")["location_id"]
    if depleted not in current or int(inventory.get(depleted, {}).get("pick_face", 0)) > 0:
        return None
    available_bin = str(current.loc[depleted])
    frequency = abc.set_index("sku_id")["pick_frequency"].astype(float)
    candidates = [
        sku for sku in current.index
        if sku != depleted and int(inventory.get(sku, {}).get("pick_face", 0)) > 0
    ]
    candidates.sort(key=lambda sku: (-float(frequency.get(sku, 0)), sku))
    for replacement in candidates:
        proposal = assignments.loc[assignments["sku_id"] != depleted].copy()
        proposal.loc[proposal["sku_id"] == replacement, "location_id"] = available_bin
        active_skus = skus.loc[skus["sku_id"].astype(str) != depleted].copy()
        active_skus["sku_id"] = active_skus["sku_id"].astype(str)
        active_skus["on_hand_qty"] = active_skus["sku_id"].map(
            lambda sku: int(inventory.get(sku, {}).get("pick_face", 0))
        )
        report = validate_assignment(active_skus, locations, proposal, rules)
        if report["is_feasible"]:
            return {
                "retired_sku_id": depleted,
                "replacement_sku_id": replacement,
                "empty_location_id": available_bin,
                "released_location_id": str(current.loc[replacement]),
                "replacement_frequency": int(frequency.get(replacement, 0)),
                "assignment": proposal.reset_index(drop=True),
                "validation": report,
            }
    return None
