# Slotwise

Slotwise is a Streamlit warehouse-slotting dashboard. It includes a reproducible festival warehouse demo, an event-aware temporary slotting plan, move-budget controls, a verified picker task queue, route evidence, and storage safety checks.

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run frontend/app.py
```

Select **Load festival demo** to build a named 150-SKU synthetic warehouse run, or use **Custom data feed** to bring your own orders, SKU master, and topology. The bundled run needs no external download.

The upload form accepts an orders CSV and optional SKU physical master and warehouse location CSVs. The SKU master must include `sku_id`, `width_cm`, `height_cm`, `depth_cm`, `unit_weight_kg`, `category`, `hazard_class`, `handling_type`, and `on_hand_qty`; accepted category names are normal, fragile, medical, fire, and hazardous (common aliases are normalized). `description`, `allowed_orientations`, and `stackable` are optional. Every SKU in the selected order cohort needs a row. Without this file, physical product attributes are synthetic.

Use **Download warehouse CSV template** in the upload panel to get an editable topology matching the supported parallel-aisle model. Warehouse location CSVs must include `location_id`, `zone`, `aisle_number`, `rack_id`, `shelf_id`, `bay`, `shelf_level`, `x_m`, `y_m`, `z_m`, `bin_width_cm`, `bin_height_cm`, `bin_depth_cm`, `volumetric_capacity_cm3`, `bin_max_weight_kg`, `shelf_max_weight_kg`, `rack_max_weight_kg`, `is_golden_zone`, and `risk_zone`. The configured aisle count, aisle spacing, front/rear cross-aisles, and depot geometry come from `configs/default.yaml`; arbitrary floor plans are rejected. Without a location file, locations are generated from that configuration. Each saved run records the input file hashes and provenance.

Default compatibility rules assign normal and fragile goods to `STANDARD`, medical goods to `MEDICAL`, fire-risk goods to `FIRE`, and hazardous goods to `HAZMAT`. Category shelf-level limits and symmetric edge-to-edge footprint clearances are configured in `configs/default.yaml` and shown in the dashboard's safety view. For the supported grid, bin depth spans across aisles (x) and bin width spans along bays (y). A non-empty `hazard_class` takes precedence and routes an SKU to `HAZMAT`. These are prototype scenario rules, not certified fire-code, medical-storage, or dangerous-goods guidance; adapt the matrix to the facility's approved policy before operational use.

For each new run, the published plan is selected using validation orders from the random legal baseline, the frequency-sort comparator, and feasible search candidates. A small exact-route refinement also uses validation orders only. The final held-out test split is scored after selection and never chooses the published layout. The dashboard reports monthly slices of that frozen test result; those slices do not replace independently retrained seasonal evaluations.

The festival dataset in `data/demo/` contains two years of seeded basket history, named SKU descriptions and event tags, physical attributes spanning all five storage categories, a seven-aisle warehouse, a future seven-day event forecast, and an event calendar. Its calibrated Zipf-like SKU demand is intended to put roughly 80% of training order appearances in the busiest 20% of products; the dashboard reports the measured share rather than assuming an exact 80/20 result. Regenerate the files with `PYTHONPATH=src .venv/bin/python scripts/generate_festival_demo.py`. The generator records assumptions and labels every value as synthetic; it does not present simulated demand as observed festival sales.

For the economics presentation, select **Load gains showcase**. Its separate seeded synthetic dataset has 150 products in four interleaved families and 120 days of correlated five-item baskets. It intentionally gives products similar popularity to isolate the value of basket affinity beyond frequency sorting; use the Festival Demo for the long-tail 80/20 example. It is not observed warehouse demand. Regenerate its three input CSVs with `PYTHONPATH=src .venv/bin/python scripts/generate_affinity_showcase.py`. The held-out comparison in the bundled run measured 33.55 m/order for frequency sort and 27.88 m/order for the published plan (5.67 m/order saved). Rebuilding after changing code or inputs may change those numbers. The test split did not select the published layout.

The **Database** tab requires an admin sign in and exposes three persistent SQLite tables: `orders`, `skus`, and `locations`. The username is `nishant`; set `SLOTWISE_ADMIN_PASSWORD` as an environment variable or in `.streamlit/secrets.toml` (copy `.streamlit/secrets.toml.example` and replace its placeholder). The real secrets file is ignored by Git. Without a configured password, database access stays disabled. Other dashboard tabs remain public. On first successful sign in, `data/processed/warehouse.sqlite` is initialized from the selected saved run. Browse pages of 100 rows, look up any row by its key, add or edit values, and delete rows. SKU deletion and ID changes are blocked while orders reference the SKU. **Build validated run from database** exports a snapshot of all three tables and runs the same cleaning, topology, safety, optimization, and held-out evaluation pipeline as the CSV feed. Saved runs are immutable, so database edits only affect a newly built run. The local SQLite file is ignored by Git and should be backed up separately if its edits matter.

In **Scenarios → Seasonal demand re-slotting**, preview or download the SKU forecast, set a limit on how many products may move, and generate a temporary layout. The plan starts from the published layout and validates every hard constraint. Its picker queue requires approval and checks the source bin again before applying each move. The payback estimate includes a modeled return move wave. Route projections reweight held-out basket shapes and remain scenario estimates.

The **Inventory** tab records product-level picks in a dedicated local SQLite demo ledger at `data/processed/demo_inventory.sqlite`. Select a product and quantity; the pick-face stock is reduced transactionally and remains updated across app reruns. Stock cells shade red through amber to green based on remaining stock. A depleted face offers a reserve refill or, when reserve is empty, a safety-checked reallocation. **Reset demo inventory database** restores the selected run's starting stock and assignment. This demo ledger is separate from persistent source tables and immutable saved runs.

Each saved run now carries a configuration snapshot and pipeline version. The dashboard recomputes feasibility against that snapshot and hides stale route metrics if the assignment fails its saved safety rules.

## Deploy on Streamlit Community Cloud

1. Select this GitHub repository and the `main` branch.
2. Set the app file path to `frontend/app.py`.
3. Deploy. Dependencies are installed from `requirements.txt`; the checked-in default run supplies the dashboard's initial data.

The default warehouse measurements and product physical attributes are modeled; uploaded location and SKU master files replace those defaults for that run. The area-map product and warehouse choices are deterministic synthetic demo data.
