import pandas as pd

from warehouse_slotting.candidates import product_rule_results, ranked_product_candidates
from warehouse_slotting.constraints import static_candidates

RULES = {
    "hazardous_zone": "HAZMAT", "heavy_unit_weight_kg": 8.0, "heavy_allowed_levels": [0, 1],
    "fragile_forbidden_levels": [3], "usable_volume_fraction": 1.0,
    "reach_penalty_seconds": {0: 1.5, 1: 0, 2: 0, 3: 2.5},
}
WAREHOUSE = {"aisle_spacing_m": 4, "front_cross_aisle_y_m": 0, "rear_cross_aisle_y_m": 8,
             "depot_aisle": 0, "depot_y_m": 0}


def test_ranked_candidates_use_existing_eligibility_and_order_by_modeled_cost() -> None:
    sku = pd.Series({"sku_id": "P", "width_cm": 10, "height_cm": 10, "depth_cm": 10,
                     "unit_volume_cm3": 1000, "unit_weight_kg": 1, "hazard_class": "none",
                     "handling_type": "normal", "allowed_orientations": "012;021;102;120;201;210",
                     "stackable": 1, "on_hand_qty": 2})
    bins = pd.DataFrame([
        {"location_id": "far", "zone": "STANDARD", "aisle_number": 2, "rack_id": "R2", "shelf_id": "S2", "bay": 0, "shelf_level": 1, "x_m": 8.45, "y_m": 1, "bin_width_cm": 20, "bin_height_cm": 20, "bin_depth_cm": 20, "volumetric_capacity_cm3": 8000, "bin_max_weight_kg": 10},
        {"location_id": "near", "zone": "STANDARD", "aisle_number": 0, "rack_id": "R0", "shelf_id": "S0", "bay": 0, "shelf_level": 1, "x_m": -0.45, "y_m": 1, "bin_width_cm": 20, "bin_height_cm": 20, "bin_depth_cm": 20, "volumetric_capacity_cm3": 8000, "bin_max_weight_kg": 10},
        {"location_id": "wrong-zone", "zone": "HAZMAT", "aisle_number": 3, "rack_id": "R3", "shelf_id": "S3", "bay": 0, "shelf_level": 1, "x_m": 12.45, "y_m": 1, "bin_width_cm": 20, "bin_height_cm": 20, "bin_depth_cm": 20, "volumetric_capacity_cm3": 8000, "bin_max_weight_kg": 10},
    ])
    ranked = ranked_product_candidates(sku, bins, RULES, WAREHOUSE, pick_frequency=5, limit=5)
    assert set(ranked.location_id) == set(static_candidates(pd.DataFrame([sku]), bins, RULES)["P"])
    assert ranked.location_id.tolist()[0] == "near"
    assert len(ranked) == 2


def test_rule_display_explains_each_known_ineligibility() -> None:
    sku = pd.Series({"width_cm": 10, "height_cm": 10, "depth_cm": 10, "unit_volume_cm3": 1000,
                     "unit_weight_kg": 9, "on_hand_qty": 2, "hazard_class": "isolated",
                     "handling_type": "fragile", "allowed_orientations": "012", "stackable": 0})
    location = pd.Series({"zone": "STANDARD", "shelf_level": 3, "bin_width_cm": 20,
                          "bin_height_cm": 20, "bin_depth_cm": 20, "volumetric_capacity_cm3": 8000,
                          "bin_max_weight_kg": 10})
    result = product_rule_results(sku, location, RULES)
    assert not result["eligible"]
    assert not result["weight_ok"]
    assert not result["hazard_ok"]
    assert not result["heavy_ok"]
    assert not result["fragile_ok"]
    assert result["fit"]
    assert len(result["reasons"]) == 4
