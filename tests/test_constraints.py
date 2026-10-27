import pandas as pd

from warehouse_slotting.constraints import static_candidates, validate_assignment

RULES = {
    "hazardous_zone": "HAZMAT", "heavy_unit_weight_kg": 8.0, "heavy_allowed_levels": [0],
    "fragile_forbidden_levels": [3], "usable_volume_fraction": 1.0, "hazard_min_clearance_m": 5.0,
}


def test_grid_packing_rejects_volume_only_fit() -> None:
    skus = pd.DataFrame([{"sku_id": "A", "width_cm": 6, "height_cm": 6, "depth_cm": 6, "unit_volume_cm3": 216, "unit_weight_kg": 1, "category": "standard", "hazard_class": "none", "handling_type": "normal", "allowed_orientations": "012", "stackable": 1, "on_hand_qty": 2}])
    locations = pd.DataFrame([{"location_id": "L", "zone": "STANDARD", "shelf_level": 0, "bin_width_cm": 10, "bin_height_cm": 10, "bin_depth_cm": 10, "volumetric_capacity_cm3": 1000, "bin_max_weight_kg": 10, "shelf_id": "S", "rack_id": "R", "shelf_max_weight_kg": 10, "rack_max_weight_kg": 10, "x_m": 0, "y_m": 0, "bay": 0}])
    assert static_candidates(skus, locations, RULES) == {"A": []}
    report = validate_assignment(skus, locations, pd.DataFrame([{"sku_id": "A", "location_id": "L"}]), RULES)
    assert not report["is_feasible"]
    assert any(item["code"] == "PACKING" for item in report["violations"])

