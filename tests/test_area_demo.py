from warehouse_slotting.area_demo import synthetic_area_data


def test_each_synthetic_product_has_three_warehouse_layout_options() -> None:
    warehouses, products, options = synthetic_area_data()
    assert len(warehouses) == 25
    assert not products.empty
    assert (options.groupby("product_id").size() == 3).all()
    assert options.groupby("product_id")["warehouse_id"].nunique().eq(3).all()
    assert set(options["warehouse_id"]) <= set(warehouses["warehouse_id"])
    assert options["aisle"].between(1, 4).all()
    assert options["bin"].between(1, 6).all()


def test_rank_order_is_stable_and_warehouse_capability_matches_product_handling() -> None:
    warehouses, products, options = synthetic_area_data()
    joined = options.merge(products, on="product_id").merge(warehouses, on="warehouse_id")
    assert joined.groupby("product_id")["rank"].apply(lambda ranks: ranks.tolist() == [1, 2, 3]).all()
    for row in joined.itertuples(index=False):
        assert row.handling in row.type
