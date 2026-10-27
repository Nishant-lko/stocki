# Smart Warehouse Slotting: 48-Hour Implementation Plan

**Status:** Planning only. No implementation has been written or executed.
**Team:** 2–3 builders; flexible stack, confirmed by the team.
**Budget:** 48 elapsed hours, including rest, integration, and submission buffer.
**Authority:** This is the full delivery plan. The existing `STAGE_1_IMPLEMENTATION_PLAN.md` remains a reference for foundation work; its deferral of optimization does not apply here.

## 1. Outcome and interpretation of the problem statement

Deliver a working warehouse slotting tool that accepts order data, SKU metadata, and a supported warehouse layout; produces complete, physically feasible baseline and optimized assignments; and demonstrates their measured differences through an interactive layout and pick-path dashboard.

The supplied PDF's heading says “Smart Virtual Rehabilitation Companion,” but its detailed requirements and deliverables consistently describe warehouse slotting. This plan follows that body. The document supplies product requirements, not instructions authorizing implementation during this planning session.

The final product must demonstrate:

1. Physical fit, bin/shelf/rack load limits, and category/handling separation.
2. Demand-driven accessibility, basket affinity, and golden-zone consideration.
3. ABC/Pareto, affinity, and volumetric EDA before allocation.
4. The same route simulator evaluating baseline and optimized layouts.
5. Actual distance, simulated time, cube utilization, and safety results.
6. Interactive layout comparison and legal aisle pick paths.
7. Architecture, algorithms, complexity, assumptions, and trade-off documentation.

There is no defensible promise of a particular percentage improvement before running the experiment. A functioning optimizer and a measured improvement are separate acceptance questions; report both honestly.

## 2. Decisions to lock at the start

| Decision | Choice and reason |
|---|---|
| Application | Python package with Streamlit and Plotly; one process keeps integration manageable |
| Storage | Parquet for tables, JSON for reports, YAML for configuration; immutable run directories |
| Service layer | FastAPI deferred until all required deliverables work and actual integration needs justify it |
| Default size | 150 active SKUs and approximately 240 bins; configuration may reduce this for development |
| Storage policy | One SKU per bin, one bin per SKU, entire configured stock must fit |
| Physical fit | Conservative homogeneous grid packing under permitted orientations; no general 3D packing solver |
| Warehouse | Parallel walkable aisles joined by front and rear cross-aisles; one depot on the front cross-aisle |
| Baseline | Seeded demand-blind feasible allocation; never select a bad seed based on measured gains |
| Optimizer | Baseline-seeded feasible relocate/swap local search with demand, affinity, ergonomics, and occupied-capacity terms |
| Evaluation | Whole-order chronological 60/20/20 train/validation/test; train selects SKUs and features |
| Selection | One fixed objective configuration; validation chooses among baseline and search checkpoints |
| Delivery | Local runnable demo and saved result bundle; hosted deployment is optional |

Do not build authentication, a database, a job queue, a JavaScript frontend, an LLM feature, general CAD/topology import, multi-SKU bins, multi-bin SKU splitting, multi-picker scheduling, or a replenishment optimizer.

## 3. Requirement-to-evidence contract

| PDF requirement | Implementation scope | Evidence required at submission |
|---|---|---|
| Three data vectors | Canonical orders, SKU master, locations plus rules | Validated tables, provenance, reproducible generator settings |
| Spatial/volume constraints | Permitted grid packing, stock volume and mass checks | Boundary fixtures and zero-violation final reports |
| Structural loads | Final aggregate bin, shelf, and rack loads | Load visualization plus overload rejection tests |
| Category/hazard rules | Allowed zones, fragile-risk exclusions, heavy shelf limit, explicit pair separation | Rule matrix and deliberate invalid-layout demonstration |
| Demand/ABC | Train-only distinct-order frequencies, ABC tiers, depot access term | Pareto chart and demand-weighted accessibility metric |
| Affinity/clusters | Basket pair scores, supported pair components, proximity term | Matrix, frequent-pair table, component labels and before/after pair distances |
| Ergonomics | Configured golden-zone levels and shelf reach penalties | Frequency-weighted golden-zone share and handling-time contribution |
| Comparative impact | Identical test orders, stock, warehouse, rules, and routing | Baseline/optimized metric table with absolute and percentage changes |
| Interactive dashboard | Layout comparison, order selector, matched pick-path views | Working interactions using saved and newly computed runs |
| Documentation | Architecture, algorithm, complexity, EDA, limitations | README, algorithm note, actual findings, demo guide |

## 4. Data acquisition and experimental design

### 4.1 Source and fallback

Use one sheet/year of [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii). The official source describes transaction timestamps, invoice/product identifiers and quantities, and a CC BY 4.0 license. Preserve the source attribution, selected sheet, retrieval date, file hash, and cleaning decisions.

Timebox acquisition to 45 minutes during the first two hours. Convert the workbook to Parquet once. Do not let repeated Excel parsing sit on the interactive path. If acquisition fails, use a clearly labeled deterministic synthetic transaction generator: the PDF permits synthetic transactions. Record the fallback and its generation parameters in the dashboard and documentation. Never describe synthetic transactions or physical attributes as observed warehouse data.

### 4.2 Cleaning and cohort

- Preserve invoice/SKU identifiers as strings. Remove cancellation invoices, non-positive quantities, invalid timestamps, and missing required identifiers.
- Do not require CustomerID; missing customer identities do not invalidate baskets.
- Profile exact duplicate rows. Adopt and document a deduplication policy; identical rows are not automatically proof of source corruption.
- Aggregate repeated valid order/SKU lines after the chosen cleaning policy.
- Review special non-product stock codes with a configured exclusion list; retain legitimate alphanumeric SKUs.
- Give each complete order a canonical timestamp and flag conflicting source timestamps. Assign equal boundary timestamps together so an order never crosses splits.
- Split all cleaned orders chronologically into approximately 60% train, 20% validation, 20% test. Record actual counts and cutoffs. Do not shuffle or split individual lines.
- Choose the 150 highest train distinct-order-frequency SKUs, with SKU ID tie-breaking; then filter every split to that cohort. Drop empty filtered orders.
- Report retained line fraction, retained order fraction, units fraction, multi-item order fraction, and basket-size distribution for every split. Evaluation concerns this cohort, not the entire original retailer.
- Keep single-item orders for routing. Sparse affinity evidence must remain visible rather than replaced with invented associations.

### 4.3 Physical metadata and feasibility

Generate dimensions, mass, categories, hazards, handling flags, permitted orientations, stackability, and stock quantity from stable SKU-keyed seeds. Do not use ABC tier, order frequency, or held-out quantities to generate them. These are synthetic attributes of a warehouse scenario; they need not describe the retailer's actual products.

Construct a demand-independent warehouse scenario with a known feasible placement witness. Allow enough appropriate capacity for heavy, upright/fragile, and isolated inventory. Include multiple bin sizes and spare locations so relocation is meaningful. Preserve the witness, generation rules and capacity slack; run the independent validator on it. Never use demand to place the witness close to the depot or manufacture a poor baseline.

The scenario is one static stock snapshot. Route replay measures service paths for historical baskets and does not deplete stock, simulate stockouts, or model replenishment trips. Quantity contributes to modeled handling work; it does not establish that snapshot stock could fulfill the entire historical stream. Report orders whose individual quantity exceeds the configured pick-face stock and disclose that their service assumes external replenishment. No replenishment efficiency gain is claimed. Prefer demand-independent stock bounds large enough to make this uncommon, without changing them after inspecting test performance.

## 5. Canonical contracts

Use centimeters for item/bin dimensions, cubic centimeters for volume, kilograms for mass, meters for floor coordinates and walking, seconds for time. Keep conversions explicit. Shelf height is separate from floor-route distance.

| Table | Required fields and meaning |
|---|---|
| Orders | order_id, sku_id, positive integer quantity, timestamp; split is derived by the pipeline, never trusted from uploaded CSV |
| SKUs | sku_id, description, width, height, depth, unit_weight, category, hazard_class, handling_type, allowed_orientations, stackable, on_hand_qty |
| Locations | location_id, zone, aisle_number, rack_id, shelf_id, bay, shelf_level, actual bin-center x, y, z, bin dimensions and floor-footprint extents, volumetric_capacity, bin_max_weight, shelf_max_weight, rack_max_weight, distance_to_depot, is_golden_zone, risk_zone |
| Rules | heavy threshold, permitted heavy levels, category/zone matrix, forbidden risk zones, hazard pair minimum physical clearances, rotation/stacking policies, reach penalties, walking/picking constants |
| Assignment | sku_id, location_id, permitted packing orientation, method, seed |
| ABC | sku_id, distinct-order frequency, units, units/day, demand share, cumulative share, class |
| Affinity | unordered SKU pair, cooccurrence, support, both confidences, lift, Jaccard, component ID |
| Validation | feasibility, complete structured violations, coverage, aggregate load summaries |
| Metrics | evaluated order count/IDs or hash, distances, time components, fills, ergonomic access, violations, runtime, definitions |
| Manifest | source hashes, cohort/split cutoffs, config hash, seeds, version, selected checkpoint, sampling policy, status, artifact inventory |

Reject duplicate primary keys, unknown assignment IDs, non-finite numeric values, invalid units, unreachable pick faces, and inconsistent capacities on repeated shelf/rack IDs. Composite/global shelf IDs must prevent shelf levels on different racks from being combined accidentally.

Each run bundle contains the canonical inputs, EDA tables, baseline assignment, optimized assignment, both validation reports, comparison metrics, manifest, and findings. A failed attempt has its own failed status; it must never overwrite a successful run's files.

### Input and output experience

Provide a bundled scenario plus CSV upload for the three canonical vectors and a rules/configuration file. In uploaded locations, support only the documented parallel-aisle template. Validate that shelf coordinates project onto that layout; reject arbitrary geometry with a specific message. Uploaded physical fields are supplied facts; do not silently synthesize replacements for invalid user input.

The first integrated version may load files from a documented local input folder. By the final dashboard gate, uploads and downloadable assignments/results must work. Small data fixtures are development tools, not evidence of full default-scale completion.

## 6. Physical constraints and independent validation

All constraints below are hard feasibility rules. Objective improvements never compensate for a violation.

1. **Coverage:** Every active SKU exactly once; no bin used twice; no missing or unknown IDs.
2. **Packing:** For each permitted unit orientation, compute the integer counts fitting across bin width, height, and depth. The product must hold on_hand_qty. For non-stackable items, permit only one layer. Require at least one valid orientation. Also enforce configured usable volumetric capacity and total stock mass. This is a conservative packing model, not proof of arbitrary mixed-orientation packability.
3. **Load:** Unit mass multiplied by stock quantity gives bin load. Sum final assigned stock mass across each shelf and each rack. Enforce their respective capacities without double-counting nested levels.
4. **Vertical handling:** Define heavy using configured unit mass/handling class, separate from total shelf load; enforce allowed shelf levels. Restrict fragile/upright orientations and high-risk zones.
5. **Category/hazard:** Enforce allowed zones and pair separation rules from explicit scenario configuration. Use minimum planar Euclidean clearance between actual axis-aligned bin footprints, not walking distance or distance between projected pick faces. Treat vertically stacked footprints as zero planar clearance, conservatively. Dedicated isolation zones are additionally enforced by configuration. Label these scenario rules, not certified safety standards.
6. **Topology/data:** Validate capacity consistency, positive physical dimensions, finite coordinates and usable path connections before allocation.

Return all violations with rule code, SKU/location IDs, measured value, limit, and explanation. Distinguish invalid input, proven zero-candidate impossibility, and allocator search exhaustion. Heuristic failure is not proof that no feasible assignment exists.

Precompute static eligible bins using packing, bin load, zone, and shelf restrictions. Maintain dynamic shelf/rack loads and pair separation during allocation/search. The independent final validator must reconstruct final loads and pair relationships from the raw inputs; it cannot merely trust the optimizer's caches or success flag. Shared rule definitions are acceptable; independent traversal and targeted fixtures are required.

## 7. Routing and simulation semantics

Use a fixed supported floor model: parallel aisles, front and rear cross-aisles, and bin pick faces projected onto aisle centerlines. Same-aisle travel is direct along the aisle. Travel between different aisles takes the shorter legal path through the front or rear cross-aisle. The depot is a fixed point on the front cross-aisle. Store or reconstruct the actual path vertices used by each distance calculation.

For each order, visit each distinct assigned SKU pick face once, start and finish at the depot, and sequence stops by nearest neighbor with location-ID tie-breaking. Multiple shelf locations sharing a floor pick point require separate handling but no extra floor distance. Reuse the identical policy for every layout. This is a consistent heuristic route simulator, not an optimal picker tour.

Completion time is walking distance divided by configured speed, plus per-SKU-stop base handling, quantity-dependent handling, and shelf-specific reach penalties. All constants are explicit scenario assumptions. Height changes handling time, not walking distance. Exclude congestion, cart capacity, multiple pickers, and replenishment travel. Display the walking/handling/reach breakdown so modeled gains are attributable.

The route visualization must draw these same legal aisle paths. Straight segments cutting through racks are unacceptable even if the numerical metric is correct.

## 8. EDA before optimization

Produce these views and artifacts from training data before features feed allocation:

- **ABC/Pareto:** Count distinct orders per SKU, units and units/day. Sort by order frequency; A crosses 80%, B crosses 95%, C is the remainder. The item that crosses each threshold belongs to the preceding tier. Show actual class counts and shares; do not assume an exact 80/20 distribution.
- **Affinity:** Treat baskets as sets, count unordered pairs, and retain raw counts. Compute support, directional confidence, lift and Jaccard. Show a symmetric zero-diagonal cooccurrence matrix. Use configurable minimum cooccurrence, then retain up to ten strongest supported neighbors per SKU for optimization; take the union symmetrically. Connected components of the supported graph supply simple cluster labels. Report sparse/no-evidence cases; lift alone must not promote rare accidental pairs.
- **Space:** Before allocation, show item/stock volume and mass distributions, bin capacity classes, static eligible-bin counts and zero-candidate diagnostics. After the baseline exists, add occupied-bin fill diagnostics. Explain concrete bottlenecks from observed outputs; postbaseline diagnostics are not prerequisites for baseline construction.

Save a short findings report with computed facts and figures. EDA tab polish must not delay the first optimizer comparison.

## 9. Baseline and optimizer

### 9.1 Demand-blind feasible baseline

Predeclare the primary seed in configuration before viewing performance. Randomize SKU and eligible-bin order, place only where current hard constraints permit, and bound attempts to ten deterministic restarts. A demand-blind most-constrained-first attempt may follow. Neither path may read demand, affinity, golden-zone preferences, or depot-distance preferences.

For the generated default scenario only, the saved feasible witness is a final fallback. Record the resulting method honestly: a witness fallback is a feasible initial layout, not evidence that random allocation succeeded. For uploaded scenarios, report incomplete allocation with diagnostics instead of fabricating a witness. Validate the final baseline independently before any evaluation.

### 9.2 Fixed optimization objective

Use one documented heuristic objective, with smaller values preferred:

| Term | Definition | Default weight |
|---|---|---:|
| Depot accessibility D | Training-frequency-weighted mean depot distance, divided by maximum depot distance | 0.50 |
| Affinity A | Supported cooccurrence-weighted mean pair distance, divided by maximum location-to-location distance | 0.30 |
| Ergonomics E | Training-frequency-weighted shelf reach penalty, divided by maximum configured reach penalty | 0.15 |
| Occupied capacity C | Sum of capacities of assigned bins, divided by sum of the S largest bin capacities, for S active SKUs | 0.05 |

All distances are legal floor-route distances. Freeze scales for each input scenario. Disable terms with no evidence or zero normalization scale and renormalize active weights. The weights express prototype priorities; they are not learned physical constants. Hard constraints remain outside this score.

The depot/affinity score is a tractable surrogate for actual route performance. It does not guarantee a shorter multi-stop tour, so final selection uses simulated validation routes.

### 9.3 Search mechanics and limits

- Begin from the validated baseline, preserving feasibility throughout.
- Propose relocations into empty eligible bins and two-SKU swaps. Use deterministic seeded proposals with a mixture of broad candidates and demand/affinity-focused candidates.
- Reject illegal candidates; accept strict objective decreases only. Preserve the baseline and save at most five improving checkpoints plus the final incumbent.
- For swaps, remove both old loads before adding new loads; check net changes on deduplicated affected shelf/rack IDs. Recheck separation involving either SKU, including their mutual pair.
- Default cap: 10,000 proposals and a 60-second safety timeout, whichever occurs first. Tiny fixture profile: 2,000 proposals. Record tested/accepted moves, objective components, elapsed time and stopping reason.
- Use precomputed eligibility and distance tables and cached objective deltas. Recompute the complete objective at checkpoints to catch cache drift.
- Fixed completed proposal budgets should reproduce assignments. A wall-clock-interrupted run may stop at a different proposal; record this rather than promising identical results.
- Validate every checkpoint used for selection independently. A failed checkpoint is invalid, regardless of score.

### 9.4 Layout selection and final evaluation

Use all training data for frequency/affinity features. For checkpoint monitoring and validation selection, use fixed deterministic samples of up to 300 whole orders from each respective split, with sampling policy and hashes saved. Never alter samples between competing layouts.

Select among baseline and feasible checkpoints by minimum mean validation route distance; break exact ties with mean completion time, then objective, then checkpoint index. This prioritizes the PDF's travel objective. All other metric changes remain visible. A baseline winner means no supported optimization improvement was found; do not relabel it as a successful gain.

Freeze all algorithm choices and the selected layout before full test evaluation. Run final metrics on all filtered test orders. Do not tune weights, seeds, cohorts, geometry, stock, or test orders after seeing final scores. Correctness fixes require explicit versioning and rerun disclosure; they are not permission to hide an unfavorable result.

## 10. Metrics and claim rules

| Metric | Definition / interpretation |
|---|---|
| Travel | Total and mean legal round-trip distance per evaluated order; also distance per SKU stop |
| Time | Total and mean simulated completion time, with walking/base/quantity/reach components |
| Overall cube fill | Total stock volume divided by all available bin volume; invariant when stock and warehouse are fixed |
| Occupied-bin fill | Total stock volume divided by assigned-bin volume; may improve by choosing smaller suitable bins |
| Wasted occupied volume | Assigned-bin volume minus stock volume |
| Occupied bin count | Exactly S under one-SKU/one-bin policy; cannot improve through relocation |
| Ergonomics | Training- and test-frequency-weighted golden-zone accessibility, explicitly labeled |
| Safety | Hard violations, unassigned SKUs, overload maxima, and complete feasibility status |
| Runtime | Ingestion, EDA, baseline, optimization and final simulation separately |

For smaller-is-better metrics, reduction percentage is 100 × (baseline − optimized) / baseline. When the baseline is zero, show an absolute delta and “not applicable” for percentage. Display negative reductions when results worsen. Compare fills with percentage-point changes, using their stated denominators.

Never claim improved global cube fill, fewer occupied bins, optimality, certified warehouse safety, observed worker productivity, or real replenishment savings from this prototype. Improved occupied-bin fill is not warehouse consolidation.

One predeclared primary baseline is mandatory. If time remains, compare the frozen optimized layout with five additional predeclared feasible baseline seeds and report the whole distribution. Label this reference-baseline sensitivity, not five paired optimizer trials. Paired optimize-from-each-seed experiments are a separate optional study.

The required impact evidence is a genuine measured held-out efficiency gain with zero violations. If the final test does not show one, report that the submission has not established that part of the requirement. Never invent numbers or search for a worse baseline to satisfy it.

## 11. Dashboard and demo behavior

Keep five compact views, sharing run identity and consistent baseline/optimized colors:

1. **Run & comparison:** Scenario selection/upload, provenance, status, seeds, input hash, start action, KPI deltas, runtime, and result download.
2. **EDA:** Pareto/classes, affinity matrix/pairs/components, and volume/eligibility findings.
3. **Layout:** Matched baseline and optimized floor grids, shared scale, shelf filter, colors for ABC/fill/handling, and selected-SKU details.
4. **Pick paths:** The same evaluated order in both layouts, legal aisle polylines, step controls, distance and time breakdown. Default to the first test order by ID, not a cherry-picked winning order; allow browsing all orders and show gain/loss distribution.
5. **Rules & diagnostics:** Feasibility, shelf/rack loads, all violations and explanations, modeled safety rules, assumptions and input rejection messages.

Thin UI calls the same Python core used by the offline pipeline. Expensive generation/search happens only on explicit run actions; ordinary widget changes read saved artifacts. Cache with input/config hashes. State must distinguish ready, running, failed, and completed. A prior successful result may be opened as history, but cannot appear to be the output of a failed current request.

Support a lightweight demand-change demonstration by uploading or selecting a second predeclared training scenario and rerunning. Treat it as a separate scenario/run; do not use a final-test demand edit as a covert tuning step. This demonstrates recomputation, not streaming demand forecasting.

## 12. Architecture and ownership boundaries

Flow: source acquisition → cleaning/split/cohort → synthetic or supplied physical inputs → topology/input validation → train EDA → candidate generation → feasible baseline → local search/checkpoints → independent validation → validation selection → frozen test comparison → dashboard/export.

| Module responsibility | Owner with 3 people | Interface commitment |
|---|---|---|
| Ingestion, cohort, EDA, manifest | A | Canonical input tables and immutable split/features |
| Physical generator, candidates, validation, baseline | B | Feasibility reports and complete assignments |
| Route model, metrics, optimizer | B + C | Distance/path primitive first; optimizer uses same distance table |
| Dashboard, input/export, integration/demo | C | Reads core outputs; no duplicate business rules |
| Final checks, documentation | All; A coordinates | Shared gates and recorded evidence |

For two people: A owns data, EDA, dashboard and documentation; B owns physical model, validation, baseline, route engine and optimizer. A helps metric presentation and manual integration checks after hour 8. Do not leave routing blocked behind the baseline: build its tiny fixture interface immediately. Freeze contracts early and make one person responsible for each artifact, rather than multiple incompatible versions.

Expected package boundaries: ingestion, synthesis, schemas/config, EDA, constraints, baseline, routing, optimization, evaluation, pipeline/artifacts, and a thin Streamlit entry point. One test area holds hand-verifiable fixtures. One README explains setup and the demo; a separate algorithm note records formulas and complexity. Choose filenames during scaffolding; do not spend delivery time reproducing a decorative repository tree.

Keep dependencies small: pandas, NumPy, openpyxl, PyArrow, PyYAML, Plotly, Streamlit, pytest, and Ruff; add schema validation only where useful. No OR-Tools or NetworkX dependency is required for the initial algorithm and fixed aisle model.

## 13. Gated schedule: 48 elapsed hours

The hours below start when implementation is authorized, not when this plan was written. They are elapsed milestones, not a requirement for continuous work. Stagger rest; budget roughly 24–30 focused hours per builder and protect the closing buffer.

| Window | Parallel work | Exit gate / contingency |
|---|---|---|
| H0–H2 | Lock contracts, rules, weights, primary seed and splits; acquire data; sketch UI; tiny routing/constraint fixture | Source available or labeled synthetic fallback selected; no unresolved storage/routing semantics |
| H2–H6 | A: clean/cohort + ABC/affinity; B: physical generator/validator/candidates; C: route primitive, fixtures, comparison shell | Known-feasible witness and route distances verified; core modules exchange canonical tables |
| H6–H10 | Baseline allocation, full validation, route/time evaluator; EDA tables; first real assignment view | Complete baseline, zero violations, reproducible metrics, default cohort coverage recorded |
| H10–H16 | Feasible relocations/swaps, fixed objective, checkpoint selection, paired dashboard results; tiny 30-SKU comparison by H12, then scale | **Working baseline versus optimized comparison on validation, legal paths, zero violations.** This is the critical vertical slice |
| H16–H22 | Staggered rest; integration owner connects all EDA/layout/paths; input/export and errors | Required views use one run bundle. Cut optional work if H16 slipped |
| H22–H28 | Focused correctness tests, upload validation, quantity/rotation edge cases; improve only against train/validation | Default-scale run stable; no unsafe/partial success; slow stages measured |
| H28–H32 | Freeze model/cohort/algorithm; finalize validation selection; run full untouched test; export comparison | Test evidence recorded with limitations; no result-driven baseline/seed changes |
| H32–H38 | Staggered rest; finish actual EDA findings, algorithm docs, demo assets; optional sensitivity only if stable | Reproducible saved demo and documented assumptions |
| H38–H42 | Clean-environment rehearsal, representative upload and rejected input; prepare short recording | Another team member reproduces the required local demo from docs |
| H42–H46 | Fix only blocking correctness/demo issues; final screenshots and submission packaging | Every required deliverable present; any rerun/version change disclosed |
| H46–H48 | Submission, artifact checksum/link verification, contingency | Submitted bundle opens; preserved local working copy and recording |

With two people, keep the same H16 target and reduce visual styling. Target 150 SKUs; if the H12 tiny comparison or H16 integration gate slips, reduce to 60 using the same deterministic training-only selection rule. Regenerate all affected inputs, features, assignments and metrics; record the reduced cohort before final test evaluation. Never combine 150-SKU EDA labels with 60-SKU comparison results. Apply the same cut for measured runtime problems. With three people, use the third person to pull routing/UI integration forward, not add a second frontend or API.

### Failure-triggered cut ladder

| Trigger | Action |
|---|---|
| Data unavailable by H2 | Use labeled seeded synthetic orders; preserve acquisition notes |
| No complete baseline by H8 | Debug using 30-SKU fixture; use validated demand-blind witness for default scenario; disclose fallback method |
| No comparison by H16 | Stop styling; reduce active scale to 60 SKUs and document cohort coverage; cut sensitivity study, extra scenarios, optional hosting, animation and extra objective profiles; show static legal path polylines |
| Search too slow | Profile cache/delta errors first; reduce proposal budget and checkpoints; record actual runtime/termination |
| No validation gain | Inspect demand/affinity signal, topology slack and objective correctness using train/validation only; include simple depot-driven feasible moves as an interpretable candidate |
| Safety or ID joins fail | Block result publication; fix core integrity before any new feature |
| Sparse affinity | Show evidence limits, supported pairs and disabled term; do not synthesize associations into real baskets |
| Final test gain absent | Publish honest comparison and limitation; do not claim requirement satisfaction or retune on that test |
| UI unavailable near deadline | Preserve offline results and screenshots/video as fallback evidence; acknowledge that this does not fully meet the interactive-dashboard requirement |

Simple depot-only search may serve as a debugging/ablation candidate, but the intended final engine must still consider supported affinity and golden-zone ergonomics. Cutting either silently is not an acceptable scope reduction.

## 14. Verification and acceptance

Verification must target things that can invalidate the result, rather than mirror every implementation detail.

### Hand-checkable fixtures

- Order-level split with equal timestamps, cancellations, repeated lines, alphanumeric SKUs and missing customer IDs.
- ABC threshold crossings and pair counts/support/lift on small known baskets.
- A multi-unit item whose total volume fits but conservative grid packing does not; a rotation-only fit; an upright restriction; a non-stackable item.
- Two bins jointly overloading a shelf; two shelves jointly overloading a rack; exact-capacity cases and numeric tolerance policy.
- Heavy-at-height, forbidden zone, fragile risk-zone and hazard-separation violations, including physically close bins with a long walking route between them.
- Missing/duplicate/unknown SKU and bin assignments.
- Same-aisle, different-aisle front-versus-rear, depot return, same-floor-point different-shelf routes; plotted vertices sum to reported distance.
- Quantity and reach time contributions, fill denominators, percentage-point versus percentage calculations, and zero denominators.
- Swaps within the same shelf/rack and across different ones; no cache drift or double-counted load.
- Invalid request leaves a failed run status and cannot display old artifacts as current success.

### End-to-end release gates

- [ ] All three data vectors and actual provenance/synthetic labeling are present.
- [ ] EDA runs before optimization and produces all three required workstreams with actual findings.
- [ ] Both assignments cover every active SKU and pass independent validation with zero violations.
- [ ] Optimizer uses demand, supported affinity and ergonomic terms; term omissions are disclosed when data has no evidence.
- [ ] Same inventory, bins, rules, orders, route policy and time constants drive comparison.
- [ ] Frozen full-test comparison reports distance, time, overall and occupied fill, ergonomic access, safety and runtime; gains and regressions are visible.
- [ ] At least one efficiency gain is actually measured on held-out orders; otherwise mark this requirement unproven.
- [ ] Dashboard includes matched layouts and legal per-order path comparison, valid input acceptance, invalid-input diagnostics and export.
- [ ] Fixed-budget runs reproduce sorted assignment/table content and metrics; manifests legitimately differ in timestamps.
- [ ] Default scenario completes within measured demo limits; target under 60 seconds for search and under two minutes for a full cached-data rerun, verified on the team's hardware.
- [ ] Documentation explains algorithm, complexity, EDA, conservative packing, synthetic physical attributes and simulation limits.
- [ ] A second team member can reproduce the saved run and open the demo from written instructions.

### Complexity to document

Let R be order lines, S active SKUs, L bins, k the distinct SKU count in a basket, P retained affinity pairs, M search proposals, and p stops in a replayed order.

- Cleaning/aggregation is approximately linear with hashing, plus chronological sorting.
- Pair mining costs the sum of squared basket sizes; retain sparse pair evidence and limit dense visualization to the active cohort.
- Static eligibility is proportional to S × L × permitted orientations; the orientation set has at most six members.
- The location distance table is quadratic in L for the supported constant-cost aisle distance primitive.
- Final assignment validation includes linear load aggregation and up to quadratic SKU-pair separation checks.
- Local-search cost depends on M, affected affinity degrees and separation checks; give a measured runtime rather than an unjustified linear claim.
- Nearest-neighbor replay costs the sum of squared per-order stop counts. Cache common distances and do not recompute all test tours for every proposed move.

## 15. Five-minute judging sequence

1. **0:00–0:40:** State the warehouse problem, selected cohort, real-versus-synthetic provenance, and prototype assumptions.
2. **0:40–1:20:** Show Pareto, one supported affinity component/pair, and a volume/eligibility finding.
3. **1:20–2:10:** Show baseline and optimized layouts, high-frequency access and zero violations.
4. **2:10–3:10:** Replay the same test order along legal aisles in both layouts. Show how distance and handling produce time.
5. **3:10–4:10:** Present aggregate held-out comparison; explicitly explain unchanged overall fill and any tradeoffs.
6. **4:10–5:00:** Show one invalid input/rule rejection, a second scenario or rerun if time permits, and downloadable assignment/evidence bundle.

Have a saved completed run and short screen recording ready. A live rerun is useful, but the demo must not rely on network access or a lucky random seed.

## 16. Adversarial review and final decisions

Three review roles challenged requirements/evidence, architecture/optimization, and delivery/demo. Their contradictions changed the original plan as follows:

| Disagreement | Final decision and reason |
|---|---|
| Complete Stage 1 first, then optimize? | Build a full comparison by H16; an excellent foundation alone misses the central deliverable |
| Mandatory API plus UI? | Shared core and Streamlit first; required interactions do not need a service boundary |
| Unit fit plus total volume enough? | No; conservative multi-unit packing and orientation/stacking policies are mandatory |
| 3D Manhattan acceptable? | No; aisle-constrained floor paths are simple enough and must match the visualization |
| OR-Tools/global solver or second greedy constructor? | Baseline-seeded feasible moves/swaps minimize feasibility and integration risk; global optimality is out of scope |
| Tune several objective profiles? | One predeclared normalized score plus validation checkpoint selection; extra profiles are optional |
| Select by time or travel? | Travel first, time as tie-break; expose ergonomic and utilization tradeoffs |
| 80/20 or 60/20/20? | 60/20/20 because checkpoint selection needs validation separate from final evidence |
| Must acquire real transactions at any cost? | Prefer UCI; timeboxed synthetic fallback is permitted and must be labeled |
| Promise global fill or consolidation gains? | No; those quantities are invariant under the fixed-inventory single-SKU-bin model |
| Five additional seeds mandatory? | Optional sensitivity after core evidence is stable; primary baseline is fixed in advance |
| Spend all 48 hours building? | Protect rest, integration, reproducibility, recording and submission time |

This plan is ready to guide implementation once separately authorized. Remaining uncertainty is empirical: attainable held-out gains and measured runtime on the team's hardware. Those must be established through the planned gates, not asserted during planning.
