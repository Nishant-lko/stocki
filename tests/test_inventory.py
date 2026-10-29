import pandas as pd

from warehouse_slotting.inventory import (
    find_safe_reallocation,
    initialize_demo_database,
    load_demo_assignments,
    load_demo_events,
    load_demo_inventory,
    process_order_cycle,
    record_demo_pick,
    record_demo_refill,
    reset_demo_database,
    refill_pick_face,
    save_demo_assignments,
)


def test_order_cycle_decrements_available_stock_and_reports_shortfall() -> None:
    inventory = {"A": {"pick_face": 2, "reserve": 5}}
    order = pd.DataFrame([{"sku_id": "A", "quantity": 3}])
    assignments = pd.DataFrame([{"sku_id": "A", "location_id": "L1"}])

    after, events = process_order_cycle(order, inventory, assignments)

    assert inventory["A"] == {"pick_face": 2, "reserve": 5}
    assert after["A"] == {"pick_face": 0, "reserve": 5}
    assert events[0]["picked_units"] == 2
    assert events[0]["unfulfilled_units"] == 1
    assert events[0]["status"] == "Partial / stockout"


def test_refill_moves_only_reserve_stock_up_to_pick_face_target() -> None:
    inventory = {"A": {"pick_face": 0, "reserve": 3}}
    after, transfer = refill_pick_face("A", inventory, {"A": 5})

    assert after["A"] == {"pick_face": 3, "reserve": 0}
    assert transfer["units_transferred"] == 3
    assert inventory["A"] == {"pick_face": 0, "reserve": 3}


def test_empty_face_can_be_reallocated_only_after_retiring_empty_sku() -> None:
    skus = pd.DataFrame(
        [
            {"sku_id": "EMPTY", "width_cm": 2, "height_cm": 2, "depth_cm": 2,
             "unit_volume_cm3": 8, "unit_weight_kg": 1, "category": "standard",
             "hazard_class": "none", "handling_type": "normal", "allowed_orientations": "012",
             "stackable": 1, "on_hand_qty": 1},
            {"sku_id": "FAST", "width_cm": 2, "height_cm": 2, "depth_cm": 2,
             "unit_volume_cm3": 8, "unit_weight_kg": 1, "category": "standard",
             "hazard_class": "none", "handling_type": "normal", "allowed_orientations": "012",
             "stackable": 1, "on_hand_qty": 10},
        ]
    )
    locations = pd.DataFrame(
        [
            {"location_id": "L1", "zone": "STANDARD", "shelf_level": 0,
             "bin_width_cm": 10, "bin_height_cm": 10, "bin_depth_cm": 10,
             "volumetric_capacity_cm3": 1000, "bin_max_weight_kg": 100,
             "shelf_id": "S1", "rack_id": "R1", "shelf_max_weight_kg": 100,
             "rack_max_weight_kg": 100, "x_m": 0, "y_m": 0, "bay": 0},
            {"location_id": "L2", "zone": "STANDARD", "shelf_level": 0,
             "bin_width_cm": 10, "bin_height_cm": 10, "bin_depth_cm": 10,
             "volumetric_capacity_cm3": 1000, "bin_max_weight_kg": 100,
             "shelf_id": "S2", "rack_id": "R2", "shelf_max_weight_kg": 100,
             "rack_max_weight_kg": 100, "x_m": 1, "y_m": 0, "bay": 0},
        ]
    )
    assignments = pd.DataFrame(
        [{"sku_id": "EMPTY", "location_id": "L1"}, {"sku_id": "FAST", "location_id": "L2"}]
    )
    inventory = {"EMPTY": {"pick_face": 0, "reserve": 0}, "FAST": {"pick_face": 10, "reserve": 0}}
    abc = pd.DataFrame([{"sku_id": "EMPTY", "pick_frequency": 1}, {"sku_id": "FAST", "pick_frequency": 50}])
    rules = {
        "usable_volume_fraction": 1.0,
        "hazardous_zone": "HAZMAT",
        "heavy_unit_weight_kg": 8,
        "heavy_allowed_levels": [0],
        "fragile_forbidden_levels": [3],
    }

    proposal = find_safe_reallocation(
        "EMPTY", skus, locations, assignments, inventory, abc, rules
    )

    assert proposal is not None
    assert proposal["replacement_sku_id"] == "FAST"
    assert proposal["empty_location_id"] == "L1"
    assert proposal["released_location_id"] == "L2"
    assert proposal["assignment"].set_index("sku_id").loc["FAST", "location_id"] == "L1"
    assert proposal["validation"]["is_feasible"]


def test_demo_sqlite_pick_refill_and_reset_are_persistent_and_logged(tmp_path) -> None:
    db = tmp_path / "demo-inventory.sqlite"
    skus = pd.DataFrame(
        [{"sku_id": "A", "on_hand_qty": 3, "reserve_qty": 5}]
    )
    assignments = pd.DataFrame([{"sku_id": "A", "location_id": "L1"}])
    initialize_demo_database(db, "run-1", skus, assignments)

    pick = record_demo_pick(db, "run-1", "A", 4, "L1")
    assert pick["changed_qty"] == 3
    assert pick["unfulfilled_qty"] == 1
    assert load_demo_inventory(db, "run-1")["A"] == {
        "pick_face": 0, "reserve": 5, "target": 3
    }

    refill = record_demo_refill(db, "run-1", "A", "L1")
    assert refill["changed_qty"] == 3
    assert load_demo_inventory(db, "run-1")["A"] == {
        "pick_face": 3, "reserve": 2, "target": 3
    }
    assert load_demo_events(db, "run-1")["action"].tolist() == ["Pick", "Refill"]

    moved = pd.DataFrame([{"sku_id": "A", "location_id": "L2"}])
    save_demo_assignments(db, "run-1", moved)
    assert load_demo_assignments(db, "run-1").loc[0, "location_id"] == "L2"

    reset_demo_database(db, "run-1", skus, assignments)
    assert load_demo_inventory(db, "run-1")["A"] == {
        "pick_face": 3, "reserve": 5, "target": 3
    }
    assert load_demo_assignments(db, "run-1").loc[0, "location_id"] == "L1"
    assert load_demo_events(db, "run-1").empty
