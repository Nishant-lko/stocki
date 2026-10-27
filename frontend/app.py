"""Interactive demo dashboard for saved warehouse-slotting run bundles."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = ROOT / "runs"


@st.cache_data(show_spinner=False)
def load_run(run_path: str) -> dict[str, object]:
    """Read a complete immutable run bundle."""
    directory = Path(run_path)
    tables = ["orders", "cohort", "skus", "locations", "abc", "affinity_pairs", "candidate_counts", "baseline_assignments"]
    loaded: dict[str, object] = {name: pd.read_parquet(directory / f"{name}.parquet") for name in tables}
    loaded["manifest"] = json.loads((directory / "run_manifest.json").read_text(encoding="utf-8"))
    loaded["validation"] = json.loads((directory / "validation.json").read_text(encoding="utf-8"))
    return loaded


def run_directories() -> list[Path]:
    return sorted(RUNS_ROOT.glob("*/run_manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True)


st.set_page_config(page_title="Slotwise | Warehouse Optimization", page_icon="📦", layout="wide")
st.title("Slotwise · Smart Warehouse Slotting")
st.caption("Feasible baseline placement, real order-demand analysis, and an auditable safety certificate.")

manifests = run_directories()
if not manifests:
    st.error("No completed run exists. Run `.venv/bin/warehouse-slotting --config configs/default.yaml` first.")
    st.stop()

paths = {path.parent.name: path.parent for path in manifests}
selected_run = st.sidebar.selectbox("Completed run", list(paths))
bundle = load_run(str(paths[selected_run]))
manifest = bundle["manifest"]
validation = bundle["validation"]

with st.sidebar:
    st.divider()
    st.caption("Run provenance")
    st.code(f"{manifest['run_id']}\nconfig {manifest['config_hash']}", language=None)
    st.success("Constraint certificate: feasible" if validation["is_feasible"] else "Constraint certificate: failed")

summary, eda, layout, rules = st.tabs(["Run summary", "Demand & affinity", "Warehouse layout", "Safety certificate"])

with summary:
    st.subheader("Baseline run")
    left, middle, right, fourth = st.columns(4)
    left.metric("Active SKUs", manifest["rows"]["skus"])
    middle.metric("Warehouse bins", manifest["rows"]["locations"])
    right.metric("Cohort order lines", f"{manifest['rows']['orders']:,}")
    fourth.metric("Hard-rule violations", validation["violation_count"])
    st.info("This run is the validated demand-blind baseline. The optimized-layout comparison appears here once the optimizer and route simulator are complete.")
    counts = pd.DataFrame(list(manifest["split_order_counts"].items()), columns=["split", "orders"])
    counts["split"] = pd.Categorical(counts["split"], ["train", "validation", "test"], ordered=True)
    st.plotly_chart(px.bar(counts.sort_values("split"), x="split", y="orders", text_auto=True, title="Chronological order split"), width="stretch")
    with st.expander("Source and cleaning report"):
        st.json({"source_sha256": manifest["source_sha256"], "cleaning": manifest["cleaning"], "baseline_seed": manifest["baseline_seed"]})

with eda:
    abc = bundle["abc"]
    affinity = bundle["affinity_pairs"]
    col1, col2 = st.columns((1.25, 1))
    with col1:
        pareto = abc.copy()
        pareto["sku_rank"] = range(1, len(pareto) + 1)
        figure = px.bar(pareto, x="sku_rank", y="pick_frequency", color="abc_class", title="ABC demand profile")
        figure.add_scatter(x=pareto["sku_rank"], y=pareto["cumulative_demand_share"] * pareto["pick_frequency"].max(), name="Cumulative demand share", yaxis="y")
        st.plotly_chart(figure, width="stretch")
    with col2:
        st.subheader("ABC cohort")
        st.dataframe(abc.groupby("abc_class", as_index=False).agg(skus=("sku_id", "count"), picks=("pick_frequency", "sum")), width="stretch", hide_index=True)
        st.subheader("Top movers")
        st.dataframe(abc[["sku_id", "pick_frequency", "velocity_per_day", "abc_class"]].head(12), width="stretch", hide_index=True)
    st.subheader("Supported order affinity")
    minimum = st.slider("Minimum co-occurrence", 1, int(affinity["cooccurrence"].max()), 3)
    filtered_pairs = affinity.loc[affinity["cooccurrence"] >= minimum].head(30)
    st.dataframe(filtered_pairs, width="stretch", hide_index=True)

with layout:
    locations = bundle["locations"]
    assignments = bundle["baseline_assignments"]
    skus = bundle["skus"]
    abc = bundle["abc"]
    joined = assignments.merge(locations, on="location_id").merge(skus, on="sku_id").merge(abc[["sku_id", "abc_class", "pick_frequency"]], on="sku_id")
    levels = sorted(joined["shelf_level"].unique())
    selected_level = st.select_slider("Shelf level", options=levels)
    view = joined.loc[joined["shelf_level"] == selected_level]
    chart = px.scatter(
        view, x="x_m", y="y_m", color="abc_class", size="pick_frequency", symbol="handling_type",
        hover_data=["sku_id", "location_id", "zone", "unit_weight_kg", "on_hand_qty"],
        title=f"Baseline pick faces · shelf level {selected_level}",
        color_discrete_map={"A": "#00CC96", "B": "#FECB52", "C": "#EF553B"},
    )
    chart.update_yaxes(autorange="reversed", title="Aisle depth (m)")
    chart.update_xaxes(title="Aisle position (m)")
    st.plotly_chart(chart, width="stretch")
    st.dataframe(view[["sku_id", "location_id", "abc_class", "zone", "handling_type", "pick_frequency"]].sort_values("pick_frequency", ascending=False), width="stretch", hide_index=True)

with rules:
    st.subheader("Independent feasibility result")
    if validation["is_feasible"]:
        st.success("All 150 active SKUs are assigned once and the baseline has zero detected hard-rule violations.")
    else:
        st.error("This run is not feasible. Do not use it for comparison claims.")
    st.json(validation)
    candidates = bundle["candidate_counts"]
    st.plotly_chart(px.histogram(candidates, x="eligible_bin_count", nbins=20, title="Static eligible bins per SKU"), width="stretch")
    st.caption("Rules checked: assignment uniqueness, conservative multi-unit packing, bin/shelf/rack mass, heavy/fragile level restrictions, hazmat zoning, and physical hazmat clearance.")

