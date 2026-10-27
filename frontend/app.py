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
st.markdown(
    """<style>
    .block-container {max-width: 1350px; padding-top: 2.25rem;}
    [data-testid="stMetric"] {background: #172433; border-radius: 12px; padding: 16px;}
    </style>""",
    unsafe_allow_html=True,
)
st.title("Slotwise")
st.subheader("Where should each product live so picking stays fast, safe, and practical?")

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
    st.success("✓ Safe baseline" if validation["is_feasible"] else "Baseline needs attention")
    st.caption("This screen shows the current baseline. Optimization results will appear alongside it after the next pipeline stage.")

summary, eda, layout, rules = st.tabs(["Start here", "What customers buy", "Where products are stored", "Safety checks"])

with summary:
    st.subheader("What has happened in this run")
    st.write("We analyzed real historical orders, selected the 150 most active products, and placed every one into a legal warehouse bin. This is the safe starting layout that the optimizer will improve.")
    left, middle, right, fourth = st.columns(4)
    left.metric("Products placed", manifest["rows"]["skus"], "all assigned")
    middle.metric("Available bins", manifest["rows"]["locations"])
    right.metric("Order lines analyzed", f"{manifest['rows']['orders']:,}")
    fourth.metric("Safety issues", validation["violation_count"], "zero is the goal", delta_color="off")
    st.info("Current stage: safe baseline complete. Next stage: move high-demand and frequently paired products closer together, then compare travel time against this layout.")
    counts = pd.DataFrame(list(manifest["split_order_counts"].items()), columns=["split", "orders"])
    counts["split"] = pd.Categorical(counts["split"], ["train", "validation", "test"], ordered=True)
    chart = px.bar(counts.sort_values("split"), x="split", y="orders", text_auto=True, color="split", title="How we kept evaluation fair")
    chart.update_layout(showlegend=False, xaxis_title=None, yaxis_title="Customer orders")
    st.plotly_chart(chart, width="stretch")
    st.caption("Earlier orders train the model. Validation chooses a layout. Later test orders remain untouched until final evaluation.")
    with st.expander("Technical provenance"):
        st.json({"run": manifest["run_id"], "source_sha256": manifest["source_sha256"], "cleaning": manifest["cleaning"], "baseline_seed": manifest["baseline_seed"]})

with eda:
    abc = bundle["abc"]
    affinity = bundle["affinity_pairs"]
    st.subheader("What customers buy most often")
    st.write("Products on the left are picked more often. The optimizer will prioritize high-demand products for accessible and ergonomic positions.")
    col1, col2 = st.columns((1.25, 1))
    with col1:
        pareto = abc.copy()
        pareto["sku_rank"] = range(1, len(pareto) + 1)
        figure = px.bar(pareto, x="sku_rank", y="pick_frequency", color="abc_class", title="Pick frequency by product rank", labels={"sku_rank": "Product rank (most picked to least picked)", "pick_frequency": "Orders containing product", "abc_class": "Demand group"}, color_discrete_map={"A": "#22c55e", "B": "#f59e0b", "C": "#ef4444"})
        st.plotly_chart(figure, width="stretch")
    with col2:
        st.markdown("#### Demand groups")
        groups = abc.groupby("abc_class", as_index=False).agg(products=("sku_id", "count"), order_picks=("pick_frequency", "sum"))
        st.dataframe(groups, width="stretch", hide_index=True)
        st.caption("A = highest demand, B = medium demand, C = lowest demand in this active product cohort.")
    st.divider()
    st.subheader("Which products are usually ordered together?")
    st.write("Frequently paired products should be placed nearer each other so one picker walks less on multi-item orders.")
    minimum = st.slider("Show pairs ordered together at least this many times", 1, int(affinity["cooccurrence"].max()), 3)
    filtered_pairs = affinity.loc[affinity["cooccurrence"] >= minimum].head(30)
    st.dataframe(filtered_pairs.rename(columns={"sku_a": "Product 1", "sku_b": "Product 2", "cooccurrence": "Orders together", "lift": "Relationship strength", "jaccard": "Basket overlap"})[["Product 1", "Product 2", "Orders together", "Relationship strength", "Basket overlap"]], width="stretch", hide_index=True)

with layout:
    st.subheader("Current baseline product placement")
    st.write("Each point is one product stored in one bin. Size shows demand; color shows its demand group. Use the shelf selector to inspect one height at a time.")
    locations = bundle["locations"]
    assignments = bundle["baseline_assignments"]
    skus = bundle["skus"]
    abc = bundle["abc"]
    joined = assignments.merge(locations, on="location_id").merge(skus, on="sku_id").merge(abc[["sku_id", "abc_class", "pick_frequency"]], on="sku_id")
    levels = sorted(joined["shelf_level"].unique())
    selected_level = st.select_slider("Choose shelf height", options=levels, value=1)
    view = joined.loc[joined["shelf_level"] == selected_level]
    chart = px.scatter(
        view, x="x_m", y="y_m", color="abc_class", size="pick_frequency", symbol="handling_type",
        hover_data=["sku_id", "location_id", "zone", "unit_weight_kg", "on_hand_qty"],
        title=f"Products at shelf height {selected_level}",
        color_discrete_map={"A": "#00CC96", "B": "#FECB52", "C": "#EF553B"},
    )
    chart.update_yaxes(autorange="reversed", title="Aisle depth (m)")
    chart.update_xaxes(title="Aisle position (m)")
    st.plotly_chart(chart, width="stretch")
    with st.expander("Show products on this shelf"):
        st.dataframe(view[["sku_id", "location_id", "abc_class", "zone", "handling_type", "pick_frequency"]].sort_values("pick_frequency", ascending=False), width="stretch", hide_index=True)

with rules:
    st.subheader("Can this baseline operate safely?")
    if validation["is_feasible"]:
        st.success("Yes. Every active product has one bin, and the layout has zero detected safety or capacity issues.")
    else:
        st.error("This run is not feasible. Do not use it for comparison claims.")
    st.markdown("#### What was checked")
    st.write("Products fit inside their bins, bins/shelves/racks stay within weight limits, fragile and heavy products use permitted heights, and hazardous products stay isolated with physical clearance.")
    candidates = bundle["candidate_counts"]
    st.plotly_chart(px.histogram(candidates, x="eligible_bin_count", nbins=20, title="How much placement choice each product has", labels={"eligible_bin_count": "Legal bins available", "count": "Products"}), width="stretch")
    st.caption("Products with fewer legal bins are harder to place. The optimizer keeps every one of these rules intact while improving efficiency.")
    with st.expander("Raw validation record"):
        st.json(validation)

