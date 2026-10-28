from itertools import pairwise

import pandas as pd

from warehouse_slotting.routing import depot_distance, route_vertices, sequence_stops, travel_graph

WAREHOUSE = {
    "aisle_spacing_m": 4.0,
    "front_cross_aisle_y_m": 0.0,
    "rear_cross_aisle_y_m": 7.2,
    "depot_aisle": 0,
    "depot_y_m": 0.0,
}


def _locations() -> pd.DataFrame:
    return pd.DataFrame([
        {"location_id": "A", "aisle_number": 0, "y_m": 0.6, "shelf_level": 1, "x_m": -0.45},
        {"location_id": "B", "aisle_number": 0, "y_m": 5.4, "shelf_level": 1, "x_m": 0.45},
        {"location_id": "C", "aisle_number": 1, "y_m": 0.6, "shelf_level": 1, "x_m": 3.55},
    ])


def test_same_aisle_and_cross_aisle_distances() -> None:
    graph = travel_graph(_locations(), WAREHOUSE)
    index = graph["index"]
    assert abs(graph["distance"][index["A"], index["B"]] - 4.8) < 1e-6
    assert abs(graph["distance"][index["A"], index["C"]] - 5.2) < 1e-6
    from_depot = depot_distance(graph, 0, 0.0)
    assert abs(from_depot[index["A"]] - 0.6) < 1e-9
    assert abs(from_depot[index["C"]] - 4.6) < 1e-9


def test_polyline_matches_route_distance() -> None:
    graph = travel_graph(_locations(), WAREHOUSE)
    index = graph["index"]
    from_depot = depot_distance(graph, 0, 0.0)
    ordered, distance = sequence_stops([index["C"], index["A"]], graph["distance"], from_depot, graph["location_ids"])
    vertices = route_vertices(ordered, graph, 0, 0.0)
    length = sum(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 for (x1, y1), (x2, y2) in pairwise(vertices))
    assert abs(length - distance) < 1e-9
    assert ordered[0] == index["A"]
