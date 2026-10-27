# PS2 Stage 1 Implementation Plan

## Smart Warehouse Slotting & Optimization Engine

**Stage:** Data foundation, EDA, hard-constraint validation, and feasible unoptimized baseline  
**Timebox:** 1 day  
**Team assumption:** 2–3 people  
**Backend:** Python + FastAPI  
**Frontend:** Streamlit + Plotly  
**Storage:** Parquet/CSV + JSON artifacts; no database in Stage 1

---

## 1. Stage 1 objective

Build a reproducible vertical slice that converts real order transactions plus deterministic synthetic SKU/warehouse data into:

1. Clean, documented canonical datasets.
2. The three required EDA workstreams: ABC velocity, order affinity, and volumetric space profiling.
3. An explicit warehouse constraint model and reusable validator.
4. A demand-blind but fully feasible baseline SKU-to-bin assignment.
5. Baseline travel, utilization, completion-time, and safety metrics.
6. FastAPI endpoints and a small Streamlit interface for inspecting the results.
7. Tested artifacts and interfaces ready for the Stage 2 optimizer.

Stage 1 does **not** claim efficiency gains. An optimized layout does not exist yet, so improvement percentages and baseline-versus-optimized claims begin in Stage 2.

### Explicit non-goals

- No demand-aware optimizer, affinity-aware placement, or OR-Tools model yet.
- No production authentication, database, asynchronous job queue, or cloud deployment.
- No general 3D bin-packing solver; use documented prototype packing assumptions.
- No polished final dashboard or realistic aisle-routing engine.
- No fabricated experimental results or improvement numbers.

---

## 2. Prototype decisions to lock before coding

These decisions remove ambiguity and keep the one-day scope controllable:

- **Order source:** UCI Online Retail II, using one year/sheet initially. Source page: `https://archive.ics.uci.edu/dataset/502/online+retail+ii`.
- **SKU scale:** Start with 150 active SKUs selected by training-set pick frequency. Keep the limit configurable.
- **Physical and topology data:** Generate deterministically from a seed because the transaction source does not contain these attributes.
- **Units:** Dimensions in cm, volume in cm³, weight in kg, distance in m, and time in seconds. Convert coordinates to meters explicitly if necessary.
- **Inventory semantics:** `on_hand_qty` is the quantity stored. Assignment volume and weight use `unit_value × on_hand_qty`, not just one unit.
- **Assignment semantics:** Each active SKU is assigned to exactly one bin and each bin holds at most one SKU. Multi-bin and mixed-SKU storage are later extensions.
- **Orientation:** A SKU fits if any axis permutation of its unit dimensions fits the bin and its total inventory volume/weight fits the bin capacities.
- **Demand-blind baseline:** Random/restart placement and first-fit fallback must not use ABC, velocity, affinity, or distance-to-dispatch as placement preferences.
- **Reproducibility:** Fix the SKU-selection rule, generator seed, baseline seed, configuration, and chronological train/test split.
- **Evaluation split:** Use the earliest 80% of timestamps for feature discovery/EDA and the latest 20% for route evaluation. Select SKUs using training data only.
- **Feasibility gate:** No assignment with missing SKUs or hard-constraint violations is accepted or shown as successful.

---

## 3. End-to-end architecture

```text
Online Retail II (.xlsx)
          |
          v
 ingestion + cleaning + chronological split
          |
          v
 canonical orders --------------------> training EDA
          |                              |-- ABC/Pareto
          |                              |-- pair affinity
          |                              `-- data-quality report
          |
          +----> synthetic SKU master <--- ABC output
          |
          +----> synthetic warehouse topology
                         |
                         v
             candidate-bin precomputation
                         |
                         v
          feasible demand-blind baseline allocator
                         |
                         v
              independent constraint validator
                    |            |
                    |            `--> validation.json (must be clean)
                    v
          held-out order route simulation
                    |
                    v
             baseline_metrics.json
                    |
          +---------+----------+
          |                    |
       FastAPI             Streamlit
   artifact/run API       EDA + baseline UI
```

Keep ingestion, EDA, generation, allocation, validation, and metrics as ordinary Python modules. FastAPI and Streamlit should be thin adapters so Stage 2 can reuse the same core logic.

---

## 4. Proposed repository layout

```text
epoch_ps/
├── STAGE_1_IMPLEMENTATION_PLAN.md
├── README.md                         # setup, commands, assumptions, demo
├── pyproject.toml                    # dependencies and tool configuration
├── configs/
│   └── default.yaml                  # seeds, thresholds, warehouse and rule settings
├── data/
│   ├── raw/                          # manually acquired source; not committed
│   ├── processed/                    # canonical Parquet tables
│   └── eda/                          # EDA tables, plots, insights
├── artifacts/
│   ├── assignments.parquet
│   ├── baseline_metrics.json
│   ├── validation.json
│   └── run_manifest.json
├── scripts/
│   └── run_stage1.py                 # one-command offline pipeline
├── src/warehouse_slotting/
│   ├── api.py                        # FastAPI application
│   ├── baseline.py                   # feasible demand-blind allocator
│   ├── config.py
│   ├── constraints.py                # eligibility + full independent validation
│   ├── eda.py
│   ├── ingest.py
│   ├── metrics.py
│   ├── pipeline.py
│   ├── schemas.py                    # API DTOs and shared field definitions
│   ├── synthesize.py
│   └── visualization.py              # data preparation for plots/layout views
├── frontend/
│   └── app.py                        # Streamlit application
└── tests/
    ├── fixtures/                     # small hand-checkable datasets
    ├── test_ingest.py
    ├── test_eda.py
    ├── test_constraints.py
    ├── test_baseline.py
    ├── test_metrics.py
    └── test_api.py
```

Use `src/warehouse_slotting` as an installable package rather than relying on ad hoc import paths.

---

## 5. Canonical data contracts

All generated files must include stable IDs and documented units. Reject duplicate primary keys and missing required values early.

### 5.1 `orders.parquet`

| Field | Type | Meaning |
|---|---|---|
| `order_id` | string | Original invoice identifier after cleaning |
| `sku_id` | string | Selected product identifier |
| `quantity` | positive integer | Units in this order line |
| `timestamp` | timezone-naive UTC or documented source-local datetime | Order time |
| `split` | `train` or `test` | Chronological evaluation split |

Aggregate repeated `(order_id, sku_id)` lines into one line after cleaning. Preserve the source row counts in the data-quality report.

### 5.2 `skus.parquet`

Required PDF fields plus inventory fields:

`sku_id`, `description`, `width`, `height`, `depth`, `unit_volume`, `weight`, `category`, `hazard_class`, `handling_type`, `on_hand_qty`, `total_volume`, `total_weight`.

All dimensions and quantities must be positive. `unit_volume = width × height × depth`; `total_volume = unit_volume × on_hand_qty`; `total_weight = weight × on_hand_qty`.

### 5.3 `locations.parquet`

Required PDF fields plus capacity/ergonomic fields:

`location_id`, `zone`, `aisle_number`, `rack_id`, `bay`, `shelf_level`, `x`, `y`, `z`, `bin_width`, `bin_height`, `bin_depth`, `volumetric_capacity`, `bin_max_weight`, `shelf_max_weight`, `rack_max_weight`, `distance_to_dispatch_depot`, `is_golden_zone`.

Validate that shelf/rack capacities are consistent wherever their IDs repeat. Capacity and distance values must be non-negative; physical dimensions must be positive.

### 5.4 Derived and output tables

- `abc.parquet`: `sku_id`, `pick_frequency`, `units_sold`, `velocity_per_day`, `demand_share`, `cumulative_demand_share`, `abc_class`.
- `affinity_pairs.parquet`: `sku_a`, `sku_b`, `co_occurrence`, `support`, `confidence_a_b`, `confidence_b_a`, `lift`, `jaccard`.
- `affinity_matrix.parquet`: symmetric co-occurrence matrix for the active SKU set; zero diagonal.
- `space_profile.parquet`: per-SKU total volume/weight, eligible-bin count, best-fit capacity class, and volume-mismatch reason counts.
- `assignments.parquet`: `sku_id`, `location_id`, `method`, `seed`; one row per active SKU.
- `validation.json`: `is_feasible`, violation count, and structured violations with code/IDs/measured/limit values.
- `run_manifest.json`: config hash, seeds, source metadata, row counts, package version, timestamps, and artifact names.

---

## 6. Workstream A — acquisition, cleaning, and synthetic generation

### A1. Acquire and document the real orders

1. Download Online Retail II manually into `data/raw/`; do not make the build depend on an interactive download.
2. Record source URL, retrieval date, original filename, sheet/year, license/terms shown by the provider, and cleaning decisions in `README.md`.
3. Convert the selected sheet once to Parquet for faster repeatable runs.
4. If the file is unavailable, use a small synthetic fixture only for tests; clearly label any demo fallback rather than presenting it as real data.

### A2. Clean orders

1. Standardize column names and trim `Invoice`/`StockCode` strings.
2. Remove cancelled invoices, non-positive quantities, missing SKU/order/timestamp values, and exact duplicate rows.
3. Profile special non-product stock codes before excluding them through a documented configurable list; do not blindly remove valid alphanumeric SKUs.
4. Sort by timestamp and perform an 80/20 chronological split without shuffling.
5. Compute training pick frequency, select the top 150 SKUs deterministically with `sku_id` tie-breaking, and filter both splits to those SKUs.
6. Remove orders that become empty; retain single-item orders for travel and multi-item orders for affinity.
7. Save cleaning counts and reject reasons.

### A3. Generate SKU physical metadata

Use a fixed seed and category-specific bounded distributions:

- Categories such as standard, fragile, and hazardous; hazard classes are separate labels.
- Dimensions and weights must be physically plausible and positive; correlate weight loosely with volume and category density.
- Generate handling types such as normal, fragile, heavy, and hazmat.
- Generate bounded `on_hand_qty`; ABC class may inform the range but must not make generation infeasible.
- Construct capacities/quantities so the default dataset has at least one known feasible assignment.
- Save the generation config and seed; identical inputs must produce byte-equivalent tabular content after consistent sorting.

### A4. Generate warehouse topology

Start with a configurable small warehouse, for example approximately 240 bins across standard and isolation zones:

- Generate aisle/rack/bay/shelf coordinates and stable hierarchical IDs.
- Include several bin capacity classes and explicit shelf/rack weight limits.
- Mark chest-to-waist levels as golden-zone locations; this is metadata in Stage 1, not a baseline preference.
- Reserve enough isolation capacity for hazardous SKUs and lower levels for heavy/fragile inventory.
- Compute dispatch distances from a documented dispatch coordinate.
- Validate the generated topology independently before allocation.

---

## 7. Workstream B — required EDA

Run EDA on the training portion used to build future optimization features. Save both machine-readable tables and plots, plus a short `data/eda/insights.md` generated from actual results.

### B1. Demand velocity and ABC/Pareto

- `pick_frequency`: number of distinct orders containing the SKU.
- `units_sold`: sum of quantity.
- `velocity_per_day`: units sold divided by observed training days; document zero-day handling.
- Sort descending by `pick_frequency`, break ties by `sku_id`, and compute demand/cumulative shares.
- Default classes: A through the 80% boundary, B through 95%, and C thereafter. Include the item crossing a threshold in the earlier class and test this rule.
- Outputs: ABC table, Pareto chart, class counts, demand share by class, and top/fast/slow SKU tables.

### B2. Affinity and co-occurrence

- Count each SKU once per order regardless of quantity.
- Generate unique pairs with `itertools.combinations`; no self-pairs or duplicate reversed pairs.
- Compute pair support, both directional confidences, lift, and Jaccard.
- Keep the full sparse pair table and a symmetric matrix for the limited active SKU set.
- Use a configurable minimum support for displayed “strong” pairs; do not hide the raw counts.
- Outputs: top pair table, top-SKU heatmap, isolated-pair/insufficient-data warnings, and top affinity observations.
- NetworkX cluster visualization is optional only if time remains; optimization is not part of Stage 1.

### B3. Volumetric density and space profiling

- Plot unit/total volume and weight distributions by category and capacity class.
- For every SKU, count dimensionally eligible bins and report zero-eligibility cases before allocation.
- Compare inventory volumes with bin volumes; summarize underfill and mismatch bottlenecks using the baseline assignment.
- Report total capacity, occupied-bin capacity, used volume, and weight-utilization summaries.
- Outputs: distributions, capacity-class counts, eligibility summary, baseline fill histogram, and concrete data-derived findings.

---

## 8. Workstream C — hard constraints and feasible baseline

### C1. Encode rules in configuration

`default.yaml` should contain seeds, active SKU count, ABC thresholds, affinity support, warehouse dimensions, heavy/fragile shelf limits, isolation-zone mappings, incompatible hazard pairs, minimum aisle separation where required, and routing constants.

Do not bury rule values inside UI or API code.

### C2. Implement one reusable validator

`validate_assignment(skus, locations, assignments, rules)` returns all detected violations, not only the first. It must check:

1. **Coverage/uniqueness:** every active SKU occurs exactly once; every location has at most one SKU; all IDs exist.
2. **Spatial fit:** at least one dimension rotation fits each bin; total inventory volume is within volumetric capacity.
3. **Weight:** bin load, summed shelf load, and summed rack load remain within their respective limits.
4. **Vertical handling:** heavy and fragile items obey configured shelf-level restrictions.
5. **Hazard/category compatibility:** allowed-zone rules hold; incompatible pairs obey the separation matrix and configured aisle/zone separation.
6. **Data integrity:** no negative quantities/capacities, inconsistent shelf/rack limits, or duplicate IDs.

Violation example fields: `code`, `severity`, `sku_ids`, `location_ids`, `measured`, `limit`, `message`. Warnings must not be used to disguise hard failures.

### C3. Precompute static candidates

For each SKU, precompute bins passing dimensional fit, volume, individual bin weight, zone, and shelf-height rules. Sort candidate IDs for determinism. Fail early with useful diagnostics if any SKU has no candidate.

### C4. Build the demand-blind baseline

1. Randomize SKU order and eligible bins using the run seed.
2. Try candidates in that order, accepting only placements that keep incremental bin/shelf/rack loads and pairwise separation rules feasible.
3. On a dead end, restart with a fixed sequence of derived seeds; record every attempt.
4. If random restarts fail, use a deterministic demand-blind most-constrained-first fallback: fewest candidates first, then descending total volume/weight, then `sku_id`.
5. Never return a partial layout as feasible. Raise a clear error with unassigned SKUs and capacity diagnostics if all attempts fail.
6. Run the independent full validator after allocation and save only a zero-violation result as the baseline.

For the default demo data, constructively ensure feasibility during generation. Difficult random data may still legitimately fail; that is preferable to silently breaking rules.

---

## 9. Baseline evaluation metrics

Evaluate the baseline on the held-out test orders after validation passes. Save metric definitions and constants alongside values.

### 9.1 Route travel distance

For each order:

1. Map its SKUs to unique assigned locations; ignore no SKU silently.
2. Start at dispatch.
3. Use nearest-neighbor order sequencing with `location_id` tie-breaking.
4. Return to dispatch.
5. Use 3D Manhattan distance between coordinates for the initial transparent approximation.

Sum distance over all test orders and report mean distance per order and per picked SKU. The same simulator must later evaluate baseline and optimized layouts.

### 9.2 Route completion time

`completion_time = travel_distance / walking_speed + Σ(base_pick_seconds + quantity × seconds_per_unit)`.

Store walking speed and handling-time constants in config. Report total and mean completion time. This is a simulator estimate, not an observed warehouse measurement.

### 9.3 Utilization and compliance

- `overall_fill_rate = total_assigned_volume / total_volume_capacity_of_all_bins`.
- `occupied_fill_rate = total_assigned_volume / capacity_of_occupied_bins`.
- Mean/median occupied-bin fill, shelf/rack weight utilization, and occupied bin count.
- Hard violation count and `is_feasible`; expected values are zero and true.
- Unassigned SKU count; expected zero.

Do not report distance/time reduction percentages until Stage 2 supplies an optimized assignment evaluated on the identical test orders.

---

## 10. FastAPI and Streamlit scope

### FastAPI endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Service health |
| `GET /api/v1/run-summary` | Manifest, dataset counts, feasibility, and key KPIs |
| `GET /api/v1/eda/abc` | ABC rows and class summaries with a row limit |
| `GET /api/v1/eda/affinity` | Top pairs and optional selected-SKU matrix |
| `GET /api/v1/eda/space` | Space/eligibility summaries |
| `GET /api/v1/assignments` | Joined assignment/SKU/location table |
| `GET /api/v1/validation` | Full feasibility result and violations |
| `GET /api/v1/metrics/baseline` | Baseline metric payload and definitions |
| `POST /api/v1/baseline/run` | Re-run the small configured baseline with an optional seed |

Use Pydantic response models and proper 404/409/422 errors. The offline CLI remains the primary way to ingest the large raw file and regenerate all artifacts.

### Streamlit tabs

1. **Overview:** source/split counts, active SKUs/bins, run seed, feasibility badge, and baseline KPIs.
2. **ABC & Demand:** Pareto chart, class filter, and SKU table.
3. **Affinity:** minimum-support control, pair table, and heatmap.
4. **Space:** volume/weight distributions, eligibility warnings, and fill histogram.
5. **Baseline Layout & Validation:** aisle/rack/shelf filters, location heatmap colored by fill or ABC class, assignment table, and violation panel.

The UI consumes API responses; it does not reimplement allocation, constraints, or metric formulas. Display a prominent error instead of stale results if validation fails.

---

## 11. Dependencies

Use Python 3.11+ and only add what is needed:

- Data: `pandas`, `numpy`, `openpyxl`, `pyarrow`.
- Config/API: `pyyaml`, `pydantic`, `fastapi`, `uvicorn`.
- Analysis/visualization: `plotly`; add `networkx` only for the optional affinity graph.
- Frontend/API client: `streamlit`, `httpx`.
- Quality: `pytest`, `httpx` test support, and `ruff`.

OR-Tools is deliberately deferred until the Stage 2 optimization model. No database or frontend JavaScript toolchain is needed.

---

## 12. Implementation sequence and ownership

Agree on schemas and config keys during the first 30 minutes so work can proceed in parallel against small fixtures.

| Task | Owner | Depends on | Completion evidence |
|---|---|---|---|
| S1-01 Scaffold package, config, fixtures, CLI | A / lead | None | Package imports; fixture config loads |
| S1-02 Acquire, clean, split, and save orders | A | S1-01 | Canonical orders + rejection report |
| S1-03 Generate SKU master and warehouse | B | Schemas | Reproducible valid Parquet tables |
| S1-04 Implement ABC, affinity, and space EDA | A | S1-02; schemas | Required tables/plots + actual insights |
| S1-05 Implement hard-constraint validator | B | Schemas/config | Toy violations all detected |
| S1-06 Implement random/restart + fallback baseline | B | S1-03, S1-05 | Complete deterministic zero-violation layout |
| S1-07 Implement route and utilization metrics | C | Schemas | Hand-calculated fixture metrics pass |
| S1-08 Implement pipeline and manifest | A | A/B outputs | One command regenerates artifacts |
| S1-09 Implement FastAPI artifact endpoints | C | Schemas | OpenAPI and endpoint tests pass |
| S1-10 Implement five Streamlit tabs | C | API fixtures | All tabs render without stale-error hiding |
| S1-11 Integrate, test, profile, and fix | All | S1-04/06/07/08 | Full pipeline and tests pass |
| S1-12 Write run/demo docs and Stage 2 handoff | Lead | Integrated run | Reproduced from documented commands |

### Suggested one-day timeline

- **0:00–0:30:** lock contracts, config, fixture data, and ownership.
- **0:30–2:30:** parallel data/EDA, generator/validator, and API/UI/metrics scaffolding.
- **2:30–4:00:** finish baseline, integrate generated data, and enforce feasibility.
- **4:00–5:30:** run full EDA and metrics; connect API and Streamlit to real artifacts.
- **5:30–6:30:** unit/integration tests, edge cases, and deterministic rerun check.
- **6:30–7:15:** documentation, demo rehearsal, and Stage 2 interface review.
- **7:15–8:00:** buffer for data-download, feasibility, or integration issues.

For two people, combine C’s work with A and have B own constraints/baseline; integrate earlier rather than adding optional visualizations.

---

## 13. Test and verification plan

### Unit tests with small fixtures

- Cleaning removes cancellations, invalid quantities, missing IDs, and exact duplicates while retaining valid alphanumeric SKUs.
- Chronological split has no timestamp leakage and SKU selection is deterministic.
- ABC covers every selected SKU exactly once and cumulative shares/threshold boundaries are correct.
- Affinity counts match hand-built baskets; matrix is symmetric with zero diagonal.
- Every dimension rotation is tested, including a SKU that fits only after rotation.
- Validators independently reject missing/duplicate assignments, oversized volume, bin/shelf/rack overload, high-level heavy/fragile items, and incompatible hazards.
- Baseline produces identical output for the same seed and does not read demand/affinity inputs.
- Baseline output passes an independent validator and includes every active SKU.
- Route distance, return-to-dispatch, completion time, and both fill-rate denominators match hand calculations.

### Integration checks

1. Run the tiny fixture pipeline.
2. Run the default real-order/synthetic-master pipeline.
3. Verify all required artifacts exist and all referenced IDs join cleanly.
4. Verify `validation.json` has zero hard violations and no unassigned SKUs.
5. Re-run with identical inputs/seeds and compare sorted tabular outputs and metrics.
6. Test API success, missing-artifact, invalid-request, and infeasible-run responses.
7. Smoke-test every Streamlit tab against API responses.

Expected quality commands after implementation:

```bash
pytest
ruff check .
python scripts/run_stage1.py --config configs/default.yaml
uvicorn warehouse_slotting.api:app --reload
streamlit run frontend/app.py
```

### Complexity notes to include in the technical documentation

Let `R` be input rows, `O` orders, `k_o` distinct SKUs in an order, `S` active SKUs, `L` locations, `A` baseline attempts, and `p_o` picked locations in a test order.

- Cleaning and aggregation: approximately `O(R)` expected time with hash-based grouping.
- Affinity generation: `O(Σ k_o²)` time and `O(P)` pair storage, where `P` is observed pairs; the optional dense matrix costs `O(S²)` memory.
- Six-rotation static candidate generation: `O(6SL)`, simplified to `O(SL)`, before incremental dynamic checks.
- Baseline placement: bounded by `A` attempts of up to `S` placements and `L` candidate checks, plus incompatibility checks; report measured runtime rather than claiming optimality.
- Naive nearest-neighbor routing: `O(Σ p_o²)` time; acceptable for the small prototype and replaceable without changing metric contracts.

---

## 14. Stage 1 definition of done

Stage 1 is complete only when all items hold:

- [ ] Real order provenance and cleaning decisions are documented.
- [ ] Orders, SKU physical master, and warehouse topology are available in canonical schemas.
- [ ] SKU/layout generation is deterministic and default data is feasible by construction.
- [ ] ABC/Pareto, affinity matrix/scores, and volumetric profiling all produce tables, plots, and data-derived insights.
- [ ] Every hard rule has a validator and at least one targeted test.
- [ ] The demand-blind baseline assigns 100% of active SKUs exactly once.
- [ ] Independent validation reports **zero hard safety/physical violations**.
- [ ] Held-out travel distance, estimated completion time, utilization, and compliance metrics are saved with definitions.
- [ ] No unsupported optimization/improvement claim is made.
- [ ] FastAPI exposes the artifacts and Streamlit displays all five scoped views.
- [ ] The pipeline and tests pass from the documented commands; a same-seed rerun is reproducible.
- [ ] Architecture, assumptions, constraint logic, metric definitions, computational complexity, and trade-offs are documented.
- [ ] `run_manifest.json` and stable artifact contracts are ready for Stage 2.

### Five-minute demo sequence

1. Show source/provenance and the three canonical data vectors.
2. Show the Pareto/ABC result and one high-lift affinity pair.
3. Show a space mismatch or underutilization finding.
4. Run a seeded baseline and show complete assignment plus zero violations.
5. Show baseline distance/time/fill metrics and explain that Stage 2 will optimize against the same validator and simulator.

---

## 15. Main risks and mitigations

| Risk | Mitigation |
|---|---|
| Large Excel file slows iteration | Convert one sheet to Parquet once; use 150 active SKUs and a tiny development fixture |
| Real data lacks physical attributes | Clearly label seeded synthetic masters; do not imply dimensions/weights are observed |
| Synthetic layout is infeasible | Construct default capacities from a feasible design; precompute candidates and fail with diagnostics |
| Random baseline dead-ends | Fixed-seed restarts plus demand-blind most-constrained-first fallback |
| Pair generation grows quickly | Limit active SKUs, count unique order items, use sparse pairs, and only visualize top entries |
| Ambiguous hazard semantics | Put zone/separation rules in versioned config and test each rule explicitly |
| Route metric appears more realistic than it is | Document nearest-neighbor and 3D Manhattan assumptions; keep simulator identical across layouts |
| UI/integration consumes the day | Build core artifacts first; API/UI use fixtures in parallel; optional graph visualization is cut first |
| Accidental data leakage | Select SKUs and fit EDA features on training data; evaluate routes on the chronological holdout |

---

## 16. Handoff to Stage 2

Stage 2 should consume the existing `orders`, `skus`, `locations`, `abc`, `affinity_pairs`, feasible `assignments`, configuration, and test-order artifacts without changing their meanings.

The optimizer will add demand/dispatch accessibility, affinity adjacency, golden-zone ergonomics, and utilization objectives while reusing:

- the same hard-constraint validator as a non-negotiable gate;
- the same held-out orders and route simulator;
- the same baseline seed/artifact;
- the same metric definitions and API/UI result contracts.

Only after an optimized layout passes validation should the dashboard compute and display baseline-versus-optimized travel reduction, time reduction, utilization changes, and safety compliance.
