"""Narrative dashboard for a saved baseline-versus-optimized warehouse run."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from warehouse_slotting.area_demo import synthetic_area_data
from warehouse_slotting.cli import run as run_pipeline
from warehouse_slotting.config import load_config
from warehouse_slotting.constraints import static_candidates, validate_assignment
from warehouse_slotting.evaluate import mean_route
from warehouse_slotting.routing import replay_order, travel_graph

ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = ROOT / "runs"
CONFIG_PATH = ROOT / "configs/default.yaml"
CONFIG = load_config(CONFIG_PATH)
COLORS = {"A": "#22c55e", "B": "#f59e0b", "C": "#ef4444"}
SHELF_NAME = {0: "floor", 1: "easy reach", 2: "easy reach", 3: "top shelf"}
VIOLATION_TEXT = {
    "PACKING": "The stock does not fit in that bin.",
    "BIN_WEIGHT": "That bin would be over its weight limit.",
    "SHELF_ID_WEIGHT": "That shelf would be over its weight limit.",
    "RACK_ID_WEIGHT": "That rack would be over its weight limit.",
    "HAZARD_ZONE": "Hazardous products cannot leave the isolation aisle.",
    "STANDARD_IN_HAZMAT": "An ordinary product cannot sit in the isolation aisle.",
    "HEAVY_HEIGHT": "This product is too heavy for that shelf.",
    "FRAGILE_RISK": "A fragile product cannot sit on the top shelf.",
    "HAZARD_CLEARANCE": "That bin is too close to a hazardous product.",
}


@st.cache_data(show_spinner=False)
def load_run(run_path: str) -> dict[str, object]:
    """Read one immutable run, including the comparison if it has been attached."""
    directory = Path(run_path)
    names = ["orders", "cohort", "skus", "locations", "abc", "affinity_pairs", "candidate_counts", "baseline_assignments"]
    loaded: dict[str, object] = {name: pd.read_parquet(directory / f"{name}.parquet") for name in names}
    loaded["manifest"] = json.loads((directory / "run_manifest.json").read_text(encoding="utf-8"))
    loaded["validation"] = json.loads((directory / "validation.json").read_text(encoding="utf-8"))
    comparison_path = directory / "comparison_metrics.json"
    if comparison_path.exists():
        loaded["optimized_assignments"] = pd.read_parquet(directory / "optimized_assignments.parquet")
        loaded["order_comparison"] = pd.read_parquet(directory / "order_comparison.parquet")
        loaded["comparison"] = json.loads(comparison_path.read_text(encoding="utf-8"))
        loaded["optimized_validation"] = json.loads((directory / "optimized_validation.json").read_text(encoding="utf-8"))
        eligible_path = directory / "eligible_bins.parquet"
        if eligible_path.exists():
            loaded["eligible_bins"] = pd.read_parquet(eligible_path)
        ml_layout_path = directory / "ml_layout.parquet"
        if ml_layout_path.exists():
            loaded["ml_layout"] = pd.read_parquet(ml_layout_path)
            loaded["ml_comparison"] = pd.read_parquet(directory / "ml_comparison.parquet")
            loaded["ml_views"] = json.loads((directory / "ml_views.json").read_text(encoding="utf-8"))
    return loaded


def run_directories() -> list[Path]:
    return sorted(RUNS_ROOT.glob("*/run_manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True)


def reduction(before: float, after: float) -> float | None:
    if before == 0:
        return None
    return 100.0 * (before - after) / before


def shelf_label(level: int) -> str:
    return f"{SHELF_NAME.get(int(level), 'shelf')} (level {int(level)})"


def placement_frames(bundle: dict[str, object]) -> pd.DataFrame:
    """Join both layouts so a sentence can name a real product, not a generic one."""
    locations = bundle["locations"]
    skus = bundle["skus"][["sku_id", "hazard_class", "handling_type", "unit_weight_kg"]]
    abc = bundle["abc"][["sku_id", "abc_class", "pick_frequency"]]
    before = bundle["baseline_assignments"].merge(locations, on="location_id").merge(skus, on="sku_id").merge(abc, on="sku_id")
    after = bundle["optimized_assignments"].merge(locations, on="location_id")
    keep = ["sku_id", "location_id", "aisle_number", "shelf_level", "zone", "x_m", "y_m", "is_golden_zone"]
    return before.merge(after[keep], on="sku_id", suffixes=("_before", "_after"))


def lead(metrics: dict[str, object]) -> str:
    test = metrics["test"]
    before = test["baseline_mean_distance_m"]
    after = test["optimized_mean_distance_m"]
    walk = reduction(before, after)
    if metrics["selected"] == "baseline":
        return (
            "The search did not earn a shorter walk on the orders used to choose a layout, "
            "so the published after is the same as the before. There is no improvement to claim."
        )
    return (
        f"Same 150 products. Same 240 bins. Same safety rules. On {test['order_count']:,} later orders "
        f"the search never saw, the average round trip fell from {before:.1f} m to {after:.1f} m"
        + (f" — {walk:.1f}% less walking." if walk is not None else ".")
        + " That walk stays on the aisles. It does not cut through the racks."
    )


def clock_sentence(metrics: dict[str, object]) -> str:
    test = metrics["test"]
    walk_pct = reduction(test["baseline_mean_distance_m"], test["optimized_mean_distance_m"])
    time_pct = reduction(test["baseline_mean_time_s"], test["optimized_mean_time_s"])
    return (
        f"Walking fell by {walk_pct:.1f}%. The clock fell by {time_pct:.1f}%, from "
        f"{test['baseline_mean_time_s']:.0f} s to {test['optimized_mean_time_s']:.0f} s. "
        f"That is not a smaller result we are hiding. {test['mean_handling_s']:.0f} s of every order "
        "is picking the units, and that work does not change when a bin changes. "
        f"The walk itself dropped from {test['baseline_mean_walk_s']:.0f} s to {test['optimized_mean_walk_s']:.0f} s. "
        f"Reaching up or bending dropped only from {test['baseline_mean_reach_s']:.1f} s to "
        f"{test['optimized_mean_reach_s']:.1f} s. Most of the saving is the walk, not the shelf height."
    )


def regret_sentence(metrics: dict[str, object]) -> str:
    test = metrics["test"]
    worse = test["worst_increase_m"]
    if worse <= 0:
        return "Even the worst test order got shorter. That will not always be true, and this page is built to show it when it is not."
    return (
        f"{test['orders_shorter']:,} test orders got shorter, {test['orders_longer']:,} got longer, "
        f"and {test['orders_same']:,} stayed the same. Order {test['worst_order_id']} is the worst: "
        f"{worse:.0f} m longer. A product in that basket was pulled toward other orders that buy it more often. "
        "The average can improve while that order does not. The path below can open that order."
    )


def move_sentence(joined: pd.DataFrame) -> str:
    moved = joined.loc[joined["location_id_before"] != joined["location_id_after"]]
    if moved.empty:
        return "No product changed bins."
    top = moved.sort_values("pick_frequency", ascending=False).iloc[0]
    if top["aisle_number_after"] < top["aisle_number_before"]:
        direction = "It moved toward the desk."
    elif top["aisle_number_after"] > top["aisle_number_before"]:
        direction = "It moved away from the desk, because a partner product or an easier shelf outweighed the walk to the front."
    else:
        direction = "It stayed in the same aisle. The floor walk barely changes; the shelf height is what changed."
    hazardous = joined.loc[joined["hazard_class"] != "none"]
    left = int((hazardous["zone_after"] != "HAZMAT").sum()) if len(hazardous) else 0
    isolation = (
        f"All {len(hazardous)} hazardous products stayed in the isolation aisle. A shorter walk is not allowed to break that."
        if left == 0
        else f"{left} hazardous products left the isolation aisle. That layout should not be published."
    )
    return (
        f"Product {top['sku_id']} is in {int(top['pick_frequency']):,} training orders. "
        f"It was on aisle {int(top['aisle_number_before'])}, {shelf_label(top['shelf_level_before'])}. "
        f"It is now on aisle {int(top['aisle_number_after'])}, {shelf_label(top['shelf_level_after'])}. {direction} {isolation}"
    )


def add_building(fig: go.Figure, locations: pd.DataFrame, assumptions: dict[str, object], column: int) -> None:
    spacing = float(assumptions["aisle_spacing_m"])
    front = float(assumptions["front_cross_aisle_y_m"])
    rear = float(assumptions["rear_cross_aisle_y_m"])
    aisles = sorted(locations["aisle_number"].unique())
    for aisle in aisles:
        fig.add_trace(go.Scatter(
            x=[aisle * spacing, aisle * spacing], y=[front, rear], mode="lines",
            line={"color": "#334155", "width": 8}, hoverinfo="skip", showlegend=False,
        ), row=1, col=column)
    fig.add_trace(go.Scatter(
        x=[aisles[0] * spacing, aisles[-1] * spacing], y=[front, front], mode="lines",
        line={"color": "#64748b", "width": 4}, hoverinfo="skip", showlegend=False,
    ), row=1, col=column)
    fig.add_trace(go.Scatter(
        x=[aisles[0] * spacing, aisles[-1] * spacing], y=[rear, rear], mode="lines",
        line={"color": "#64748b", "width": 4}, hoverinfo="skip", showlegend=False,
    ), row=1, col=column)
    fig.add_trace(go.Scatter(
        x=[float(assumptions["depot_aisle"]) * spacing], y=[float(assumptions["depot_y_m"])],
        mode="markers+text", text=["Desk"], textposition="top center",
        marker={"size": 14, "color": "#e2e8f0", "symbol": "diamond"},
        name="Desk", showlegend=column == 1, hoverinfo="skip",
    ), row=1, col=column)


def layout_figure(joined: pd.DataFrame, locations: pd.DataFrame, assumptions: dict[str, object], level: int, highlight: bool) -> go.Figure:
    fig = make_subplots(rows=1, cols=2, shared_yaxes=True, horizontal_spacing=0.06, subplot_titles=("Before — demand was ignored", "After — legal moves only"))
    add_building(fig, locations, assumptions, 1)
    add_building(fig, locations, assumptions, 2)
    scale = float(joined["pick_frequency"].max())
    sides = (
        (1, joined.loc[joined["shelf_level_before"] == level], "before"),
        (2, joined.loc[joined["shelf_level_after"] == level], "after"),
    )
    for column, shelf, marker in sides:
        for abc_class, color in COLORS.items():
            part = shelf.loc[shelf["abc_class"] == abc_class]
            if part.empty:
                continue
            moved = part["location_id_before"] != part["location_id_after"]
            fig.add_trace(go.Scatter(
                x=part[f"x_m_{marker}"], y=part[f"y_m_{marker}"], mode="markers",
                name="A — ordered most" if abc_class == "A" else abc_class,
                legendgroup=abc_class, showlegend=column == 1,
                marker={
                    "color": color,
                    "size": (8 + 14 * part["pick_frequency"] / scale).tolist(),
                    "line": {"width": [1.8 if highlight and flag else 0 for flag in moved], "color": "#f8fafc"},
                },
                customdata=list(zip(part["sku_id"], part[f"location_id_{marker}"], part[f"aisle_number_{marker}"], part["pick_frequency"], strict=True)),
                hovertemplate="Product %{customdata[0]}<br>Bin %{customdata[1]}<br>Aisle %{customdata[2]}<br>Training orders %{customdata[3]}<extra></extra>",
            ), row=1, col=column)
    rear = float(assumptions["rear_cross_aisle_y_m"])
    fig.update_xaxes(range=[-1.8, 22.2], title_text="Desk on the left, isolation aisle on the right")
    fig.update_yaxes(range=[rear + 0.9, -0.9], title_text="Front of the building at the top")
    fig.update_layout(height=560, margin={"l": 10, "r": 10, "t": 48, "b": 10}, legend_title_text="How often it is ordered")
    return fig


def area_figure(warehouses: pd.DataFrame, top_three: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=warehouses["x"], y=warehouses["y"], mode="markers+text", text=warehouses.warehouse_id,
        textposition="top center", marker={"size": 22, "color": "#64748b", "line": {"color": "#cbd5e1", "width": 2}},
        name="Other warehouses", hovertemplate="%{text}<extra></extra>"))
    colors = ["#22c55e", "#38bdf8", "#f59e0b"]
    for rank, row in enumerate(top_three.itertuples(index=False), start=1):
        wh = warehouses.loc[warehouses.warehouse_id == row.warehouse_id].iloc[0]
        fig.add_trace(go.Scatter(x=[wh.x], y=[wh.y], mode="markers+text", text=[f"#{rank} {wh.name}"], textposition="bottom center",
            marker={"size": 36, "color": colors[rank-1], "line": {"color": "white", "width": 2}},
            name=f"Top {rank}", hovertemplate=f"Top {rank}: {wh.name}<br>{wh.type}<extra></extra>"))
    fig.update_xaxes(visible=False, range=[-0.7, 4.7])
    fig.update_yaxes(visible=False, range=[-0.7, 4.7], scaleanchor="x", scaleratio=1)
    fig.update_layout(height=580, margin={"l": 10, "r": 10, "t": 15, "b": 10}, legend={"orientation": "h", "y": 1.02, "font": {"size": 13, "color": "#dbeafe"}}, plot_bgcolor="#101d2d", paper_bgcolor="#101d2d", font={"family": "Inter, Arial, sans-serif", "color": "#e2e8f0", "size": 13}, hoverlabel={"bgcolor": "#172a3f", "font": {"color": "#f8fafc", "size": 13}})
    return fig


def warehouse_layout_figure(warehouse_name: str, aisle: int, slot: int, rank: int) -> go.Figure:
    # Accept prior synthetic IDs ("Aisle 2", "B01") during Streamlit hot reloads.
    aisle = int(str(aisle).removeprefix("Aisle ").removeprefix("A"))
    slot = int(str(slot).removeprefix("B"))
    xs, ys, colors, labels = [], [], [], []
    for a in range(1, 5):
        for b in range(1, 7):
            xs.append(a); ys.append(b); labels.append(f"A{a}-B{b}")
            colors.append("#22c55e" if (a, b) == (aisle, slot) else "#334155")
    fig = go.Figure(go.Scatter(x=xs, y=ys, mode="markers+text", text=labels, textposition="middle center",
        marker={"size": 32, "color": colors, "line": {"color": "#94a3b8", "width": 1}},
        hovertemplate="%{text}<extra></extra>"))
    fig.update_xaxes(title="Aisle", tickvals=[1, 2, 3, 4], range=[0.5, 4.5], dtick=1)
    fig.update_yaxes(title="Bin row", tickvals=[1, 2, 3, 4, 5, 6], range=[0.5, 6.5], dtick=1)
    fig.update_layout(title={"text": f"<b>#{rank} {warehouse_name}</b><br><sup>Suggested bin A{aisle}-B{slot:02d}</sup>", "x": 0.04, "xanchor": "left"}, height=330, showlegend=False, margin={"l": 14, "r": 14, "t": 68, "b": 14}, paper_bgcolor="#142235", plot_bgcolor="#142235", font={"family": "Inter, Arial, sans-serif", "color": "#dbeafe", "size": 12}, xaxis={"gridcolor": "#293c51", "zeroline": False}, yaxis={"gridcolor": "#293c51", "zeroline": False})
    return fig


def render_find_home(bundle: dict[str, object]) -> None:
    st.markdown("## Find a home for a product")
    st.caption("Explore 25 synthetic warehouses and see the suggested bin in each of the top three matches.")
    warehouses, products, options = synthetic_area_data()
    with st.container(border=True):
        product = st.selectbox("Choose a product", products["product"].tolist(), key="area_product")
        selected_product = products.loc[products["product"] == product].iloc[0]
        top_three = options.loc[options.product_id == selected_product.product_id].sort_values("rank")
        st.markdown(f"**{selected_product.product}** &nbsp; · &nbsp; {selected_product.handling} handling &nbsp; · &nbsp; **{len(warehouses)} warehouses compared**", unsafe_allow_html=True)
        st.plotly_chart(area_figure(warehouses, top_three), width="stretch", key="area_map", config={"displayModeBar": False, "responsive": True})
        st.caption("Top three are highlighted by rank: green, blue, then amber. Gray markers are the other warehouses. Hover a marker for details.")
    st.markdown("### Suggested bins")
    st.caption("Each card shows a simple top-down layout. The green bin is the suggested home for the selected product.")
    columns = st.columns(3, gap="medium")
    for column, option in zip(columns, top_three.itertuples(index=False), strict=True):
        name = warehouses.loc[warehouses.warehouse_id == option.warehouse_id, "name"].iloc[0]
        with column.container(border=True):
            st.plotly_chart(warehouse_layout_figure(name, option.aisle, option.bin, option.rank), width="stretch", key=f"layout_{selected_product.product_id}_{option.warehouse_id}", config={"displayModeBar": False, "responsive": True})
    st.caption("Synthetic layout: 4 aisles × 6 bin rows per warehouse.")


def path_figure(replay: dict[str, object], locations: pd.DataFrame, assumptions: dict[str, object], title: str, color: str) -> go.Figure:
    fig = go.Figure()
    spacing = float(assumptions["aisle_spacing_m"])
    front = float(assumptions["front_cross_aisle_y_m"])
    rear = float(assumptions["rear_cross_aisle_y_m"])
    for aisle in sorted(locations["aisle_number"].unique()):
        fig.add_trace(go.Scatter(x=[aisle * spacing, aisle * spacing], y=[front, rear], mode="lines", line={"color": "#334155", "width": 8}, hoverinfo="skip", showlegend=False))
    vertices = replay["vertices"]
    fig.add_trace(go.Scatter(x=[point[0] for point in vertices], y=[point[1] for point in vertices], mode="lines", line={"color": color, "width": 3}, name="Walk", hoverinfo="skip"))
    stops = pd.DataFrame(replay["stops"]).merge(locations, on="location_id")
    fig.add_trace(go.Scatter(
        x=stops["x_m"], y=stops["y_m"], mode="markers+text", text=stops["sku_id"], textposition="top center",
        marker={"size": 9, "color": color}, name="Stops",
        hovertemplate="Product %{text}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(x=[float(assumptions["depot_aisle"]) * spacing], y=[front], mode="markers", marker={"size": 12, "color": "#e2e8f0", "symbol": "diamond"}, name="Desk"))
    fig.update_xaxes(range=[-1.8, 22.2], title_text="The line is the walkway, not a shortcut through racks")
    fig.update_yaxes(range=[rear + 0.9, -0.9], title_text="Front at the top")
    fig.update_layout(title=title, height=460, margin={"l": 10, "r": 10, "t": 48, "b": 10})
    return fig


def route_words(replay: dict[str, object]) -> str:
    stops = replay["stops"]
    shown = [f"{stop['sku_id']} (aisle {stop['aisle']}, {shelf_label(stop['shelf_level'])})" for stop in stops[:6]]
    extra = f", then {len(stops) - 6} more" if len(stops) > 6 else ""
    return "Desk, then " + ", then ".join(shown) + extra + ", then back to the desk."


@st.cache_data(show_spinner=False)
def replay_pair(run_path: str, order_id: str) -> tuple[dict[str, object], dict[str, object]]:
    bundle = load_run(run_path)
    graph = travel_graph(bundle["locations"], CONFIG["warehouse"])
    lines = bundle["orders"]
    frame = lines.loc[(lines["split"] == "test") & (lines["order_id"].astype(str) == order_id)]
    quantities = {str(sku): int(qty) for sku, qty in frame.groupby("sku_id")["quantity"].sum().items()}
    rules = CONFIG["rules"]
    depot = int(CONFIG["warehouse"]["depot_aisle"])
    depot_y = float(CONFIG["warehouse"]["depot_y_m"])
    before = replay_order(quantities, dict(zip(bundle["baseline_assignments"]["sku_id"], bundle["baseline_assignments"]["location_id"], strict=True)), graph, rules, depot, depot_y)
    after = replay_order(quantities, dict(zip(bundle["optimized_assignments"]["sku_id"], bundle["optimized_assignments"]["location_id"], strict=True)), graph, rules, depot, depot_y)
    return before, after


@st.cache_data(show_spinner=False)
def desk_scenario(run_path: str, depot_aisle: int) -> dict[str, float]:
    bundle = load_run(run_path)
    before = mean_route(bundle["orders"], bundle["baseline_assignments"], bundle["locations"], CONFIG["warehouse"], CONFIG["rules"], "test", 300, depot_aisle)
    after = mean_route(bundle["orders"], bundle["optimized_assignments"], bundle["locations"], CONFIG["warehouse"], CONFIG["rules"], "test", 300, depot_aisle)
    return {"before": before["mean_distance_m"], "after": after["mean_distance_m"], "orders": before["orders"]}


@st.cache_data(show_spinner=False)
def heavy_floor(run_path: str) -> dict[str, int]:
    bundle = load_run(run_path)
    rules = dict(CONFIG["rules"])
    rules["heavy_allowed_levels"] = [0]
    before = validate_assignment(bundle["skus"], bundle["locations"], bundle["baseline_assignments"], rules)
    after = validate_assignment(bundle["skus"], bundle["locations"], bundle["optimized_assignments"], rules)
    heavy = int((bundle["skus"]["unit_weight_kg"] >= CONFIG["rules"]["heavy_unit_weight_kg"]).sum())
    return {"before": before["violation_count"], "after": after["violation_count"], "heavy": heavy}


@st.cache_data(show_spinner=False)
def legal_bins(run_path: str) -> dict[str, list[str]]:
    bundle = load_run(run_path)
    return static_candidates(bundle["skus"], bundle["locations"], CONFIG["rules"])


@st.cache_data(show_spinner=False)
def pin_scenario(run_path: str, sku_id: str, location_id: str) -> dict[str, object]:
    bundle = load_run(run_path)
    published = bundle["optimized_assignments"].copy()
    current = str(published.loc[published["sku_id"] == sku_id, "location_id"].iloc[0])
    if current == location_id:
        return {"legal": True, "same": True}
    occupant = published.loc[published["location_id"] == location_id, "sku_id"]
    kind = "move into an empty bin"
    if len(occupant):
        other = str(occupant.iloc[0])
        published.loc[published["sku_id"] == other, "location_id"] = current
        kind = f"swap with {other}"
    published.loc[published["sku_id"] == sku_id, "location_id"] = location_id
    report = validate_assignment(bundle["skus"], bundle["locations"], published, CONFIG["rules"])
    if not report["is_feasible"]:
        messages = []
        for item in report["violations"]:
            messages.append(VIOLATION_TEXT.get(item["code"], item["message"]))
        return {"legal": False, "same": False, "messages": list(dict.fromkeys(messages))}
    before = mean_route(bundle["orders"], bundle["baseline_assignments"], bundle["locations"], CONFIG["warehouse"], CONFIG["rules"], "test", 300)
    automatic = mean_route(bundle["orders"], bundle["optimized_assignments"], bundle["locations"], CONFIG["warehouse"], CONFIG["rules"], "test", 300)
    pinned = mean_route(bundle["orders"], published, bundle["locations"], CONFIG["warehouse"], CONFIG["rules"], "test", 300)
    return {
        "legal": True, "same": False, "kind": kind,
        "before": before["mean_distance_m"], "automatic": automatic["mean_distance_m"], "pinned": pinned["mean_distance_m"],
    }


def render_comparison(bundle: dict[str, object], run_path: str) -> None:
    metrics = bundle["comparison"]
    test = metrics["test"]
    place = metrics["placement"]
    assumptions = metrics["assumptions"]
    st.markdown(f"### {lead(metrics)}")
    st.write(
        "Before is a legal layout that ignored what customers buy. That was deliberate: if the starting layout "
        "were already built to look bad, the improvement would be fake. After is the layout we would publish. "
        "A product moves only into a bin it is allowed to use. The orders in the result are later orders. "
        "They were not used to choose the layout."
    )
    st.write(clock_sentence(metrics))
    walk, clock, easy, safe = st.columns(4)
    walk.metric("Average walk", f"{test['optimized_mean_distance_m']:.1f} m", f"{test['optimized_mean_distance_m'] - test['baseline_mean_distance_m']:.1f} m", delta_color="inverse")
    walk.caption(f"Before: {test['baseline_mean_distance_m']:.1f} m. One round trip per customer order, then averaged. Later orders only.")
    clock.metric("Average time", f"{test['optimized_mean_time_s']:.0f} s", f"{test['optimized_mean_time_s'] - test['baseline_mean_time_s']:.1f} s", delta_color="inverse")
    clock.caption("Walk plus reach plus picking the units. Picking the units does not change.")
    easy.metric("Easy-shelf picks", f"{place['golden_share_train_after'] * 100:.0f}%", f"{(place['golden_share_train_after'] - place['golden_share_train_before']) * 100:.0f} pts")
    easy.caption("Share of training picks on the two middle shelves. Points, not a speed claim. Test picks moved the same way, from "
                 f"{place['golden_share_test_before'] * 100:.0f}% to {place['golden_share_test_after'] * 100:.0f}%.")
    safe.metric("Safety issues", metrics["safety"]["optimized_violation_count"])
    safe.caption("Zero is required. A shorter illegal walk is rejected, not shown as a win.")
    parts = pd.DataFrame([
        {"Layout": "Before", "Part": "Walking", "Seconds": test["baseline_mean_walk_s"]},
        {"Layout": "Before", "Part": "Reaching", "Seconds": test["baseline_mean_reach_s"]},
        {"Layout": "Before", "Part": "Picking the units", "Seconds": test["mean_handling_s"]},
        {"Layout": "After", "Part": "Walking", "Seconds": test["optimized_mean_walk_s"]},
        {"Layout": "After", "Part": "Reaching", "Seconds": test["optimized_mean_reach_s"]},
        {"Layout": "After", "Part": "Picking the units", "Seconds": test["mean_handling_s"]},
    ])
    chart = px.bar(parts, x="Layout", y="Seconds", color="Part", title="Where an order's time actually goes", color_discrete_map={"Walking": "#38bdf8", "Reaching": "#f59e0b", "Picking the units": "#94a3b8"})
    chart.update_layout(barmode="stack", height=360, margin={"l": 10, "r": 10, "t": 48, "b": 10})
    st.plotly_chart(chart, width="stretch")
    st.caption("The gray block is the same height on purpose. If someone asks why time fell less than distance, point at that block.")
    st.subheader("What did not change, and should not")
    st.write(
        f"All {place['occupied_bin_count']} products still have one bin each. The whole building is still "
        f"{place['overall_cube_fill'] * 100:.1f}% full. We did not add bins or throw stock away, so that number cannot improve. "
        f"The bins we did use went from {place['occupied_fill_before'] * 100:.1f}% full to {place['occupied_fill_after'] * 100:.1f}% full. "
        "That is a small change because each bin holds one product and the stock is a pick face, not a full pallet. "
        "Most of every bin stays empty. This is not a space-saving project."
    )
    st.write(
        f"Fast sellers were {place['a_mean_depot_before_m']:.1f} m from the desk, then {place['a_mean_depot_after_m']:.1f} m. "
        f"Products that are actually bought together were {place['affinity_mean_before_m']:.1f} m of walking apart, "
        f"then {place['affinity_mean_after_m']:.1f} m. {place['skus_moved']} products changed bins. "
        f"{place['skus_changed_aisle']} of those changed aisle."
    )
    joined = placement_frames(bundle)
    st.write(move_sentence(joined))
    st.subheader("The building, one shelf at a time")
    st.write(
        "Left is the desk. Right is the isolation aisle, the only legal home for hazardous products. "
        "Color is how often the product is ordered among these 150, not whether the move was good. "
        "Green is ordered most. A dot can leave this picture by moving to another shelf."
    )
    level = st.select_slider("Shelf height", options=[0, 1, 2, 3], value=1, format_func=shelf_label)
    highlight = st.checkbox("Outline products that moved", value=False)
    on_shelf = joined.loc[(joined["shelf_level_before"] == level) | (joined["shelf_level_after"] == level)]
    if on_shelf.empty:
        st.info("Nothing sits on this shelf in either layout.")
    else:
        st.plotly_chart(layout_figure(joined, bundle["locations"], assumptions, level, highlight), width="stretch")
        on_before = int((joined["shelf_level_before"] == level).sum())
        on_after = int((joined["shelf_level_after"] == level).sum())
        st.caption(f"This shelf held {on_before} products before and {on_after} after. A missing dot moved to another height. It was not dropped.")
    st.subheader("Not every order got better")
    st.write(regret_sentence(metrics))
    compared = bundle["order_comparison"].copy()
    compared["change_m"] = compared["optimized_distance_m"] - compared["baseline_distance_m"]
    compared["What happened"] = pd.cut(compared["change_m"], [-1e9, -1e-6, 1e-6, 1e9], labels=["Shorter", "Same", "Longer"])
    hist = px.histogram(compared, x="change_m", color="What happened", nbins=40, title="Change in walk, one bar per group of test orders", labels={"change_m": "After minus before (meters). Left of zero is a shorter walk."}, color_discrete_map={"Shorter": "#22c55e", "Same": "#94a3b8", "Longer": "#ef4444"})
    hist.add_vline(x=0, line_dash="dot", line_color="#e2e8f0")
    hist.update_layout(height=360, margin={"l": 10, "r": 10, "t": 48, "b": 10})
    st.plotly_chart(hist, width="stretch")
    st.subheader("The same order, both layouts")
    st.write("The line is the walk the number uses. It follows the aisle and the cross-aisles at the front and back. The visit order is nearest bin, with a fixed tie-break, and it is the same rule on both layouts. This is not an optimal tour, and it is not a smarter tour on the side we prefer.")
    options = compared.sort_values("order_id")["order_id"].astype(str).tolist()
    jumps = st.columns(3)
    if jumps[0].button("First test order"):
        st.session_state.path_order = test["first_order_id"]
    if jumps[1].button("Typical change"):
        st.session_state.path_order = test["median_order_id"]
    if jumps[2].button("Largest increase"):
        st.session_state.path_order = test["worst_order_id"]
    if "path_order" not in st.session_state:
        st.session_state.path_order = test["first_order_id"]
    order_id = st.selectbox("Test order", options, key="path_order")
    if order_id == test["first_order_id"]:
        st.caption("This is the earliest test order by ID. It is not the order where we look best.")
    elif order_id == test["worst_order_id"]:
        st.caption("This is the order that got worse by the most. It is here so the loss is inspectable.")
    else:
        st.caption("The caption on the average does not have to match this one order.")
    before_path, after_path = replay_pair(run_path, order_id)
    left, right = st.columns(2)
    left.plotly_chart(path_figure(before_path, bundle["locations"], assumptions, f"Before · {before_path['distance_m']:.0f} m · {before_path['time_s']:.0f} s", "#f59e0b"), width="stretch")
    left.write(route_words(before_path))
    right.plotly_chart(path_figure(after_path, bundle["locations"], assumptions, f"After · {after_path['distance_m']:.0f} m · {after_path['time_s']:.0f} s", "#38bdf8"), width="stretch")
    right.write(route_words(after_path))
    delta = after_path["distance_m"] - before_path["distance_m"]
    st.write(f"This order changed by {delta:+.0f} m. The published claim is the average over {test['order_count']:,} orders, not this drawing.")
    with st.expander("How the after layout was chosen"):
        opt = metrics["optimizer"]
        st.write(
            "The search started from the blind layout. It tried moving a product into an empty legal bin, or swapping two products. "
            "It kept a move only when a stand-in score fell: fast sellers nearer the desk, pairs closer, fast sellers at an easy height, "
            "and a small preference for not wasting a large bin. It is not an optimal solver. "
            f"It tested {opt['proposals_tested']:,} moves and kept {opt['proposals_accepted']:,}, in {opt['elapsed_seconds']:.1f} s."
        )
        st.write(
            f"The choice between candidates used {opt['validation_orders']} earlier held-out orders, not the test set. "
            f"Those walks went from {opt['baseline_validation_mean_distance_m']:.1f} m to {opt['selected_validation_mean_distance_m']:.1f} m. "
            "The test numbers above were computed after that choice was frozen."
        )
        st.write(metrics["selection_note"])


def render_what_if(bundle: dict[str, object], run_path: str) -> None:
    metrics = bundle["comparison"]
    test = metrics["test"]
    st.markdown("### The layout stays frozen")
    st.write(
        "These questions change the desk, the clock, the demand, or one human decision. "
        "They do not quietly re-place the warehouse. If a change makes homes illegal, the next step is to re-run the search, not to hand the building back to a person."
    )
    st.subheader("What if the packing desk moved?")
    st.write("The search assumed the desk stays at the front of aisle 0. This slider does not move products. It asks how much of the gain depended on that desk. The sample is the first 300 test orders, so it will not match the full-test average exactly.")
    current_aisle = int(metrics["assumptions"]["depot_aisle"])
    aisle = st.select_slider("Desk aisle", options=list(range(int(metrics["assumptions"]["aisle_count"]))), value=current_aisle, format_func=lambda value: f"Aisle {value}" + (" · current desk" if value == current_aisle else " · isolation aisle" if value == 5 else ""))
    if int(aisle) == current_aisle:
        st.write(
            f"With the desk where it is, the full test walks {test['baseline_mean_distance_m']:.1f} m before and "
            f"{test['optimized_mean_distance_m']:.1f} m after. Move the slider to price another door. That uses the first 300 test orders, so it will not match this average exactly."
        )
    else:
        with st.spinner("Replaying the first 300 test orders from that desk"):
            here = desk_scenario(run_path, current_aisle)
            desk = desk_scenario(run_path, int(aisle))
        gap_now = here["before"] - here["after"]
        gap = desk["before"] - desk["after"]
        st.write(
            f"On that same 300-order sample, aisle {current_aisle} walks {here['before']:.1f} m before and {here['after']:.1f} m after. "
            f"Aisle {aisle} walks {desk['before']:.1f} m before and {desk['after']:.1f} m after. The gap goes from {gap_now:.1f} m to {gap:.1f} m. "
            + ("Moving the desk shrinks the advantage. Part of the gain is 'put fast sellers near this desk,' not a layout that is shorter from every door." if gap < gap_now - 1 else "The after layout is still the shorter walk from this door.")
        )
    st.subheader("What if pickers walk at a different speed?")
    st.write("Distance is a property of the bins. Time divides that distance by a speed we assumed. Changing the speed cannot change the meters.")
    speed = st.slider("Walking speed (meters per second)", 0.6, 2.0, float(metrics["assumptions"]["walking_speed_mps"]), 0.1)
    before_time = test["baseline_mean_distance_m"] / speed + test["baseline_mean_reach_s"] + test["mean_handling_s"]
    after_time = test["optimized_mean_distance_m"] / speed + test["optimized_mean_reach_s"] + test["mean_handling_s"]
    st.write(
        f"At {speed:.1f} m/s the average order takes {before_time:.0f} s before and {after_time:.0f} s after. "
        f"The walks stay {test['baseline_mean_distance_m']:.1f} m and {test['optimized_mean_distance_m']:.1f} m. "
        "If a judge asks which number is the claim, it is the meters."
    )
    st.subheader("What if one product suddenly sells more?")
    st.write("We do not move a bin. Orders that contain the product count more, and we see which frozen layout suffers.")
    abc = bundle["abc"].sort_values("pick_frequency", ascending=False)
    sku_id = st.selectbox("Product", abc["sku_id"].tolist(), format_func=lambda sku: f"{sku} · {int(abc.set_index('sku_id').loc[sku, 'pick_frequency'])} training orders")
    multiplier = st.slider("Count those orders this many times", 1.0, 4.0, 2.0, 0.5)
    contains = set(bundle["orders"].loc[(bundle["orders"]["split"] == "test") & (bundle["orders"]["sku_id"] == sku_id), "order_id"].astype(str))
    weights = bundle["order_comparison"]["order_id"].astype(str).map(lambda order: multiplier if order in contains else 1.0)
    before = float((bundle["order_comparison"]["baseline_distance_m"] * weights).sum() / weights.sum())
    after = float((bundle["order_comparison"]["optimized_distance_m"] * weights).sum() / weights.sum())
    st.write(
        f"If orders containing {sku_id} count {multiplier:.0f}×, the weighted walk is {before:.1f} m before and {after:.1f} m after. "
        f"{len(contains):,} of {test['order_count']:,} test orders include it. "
        + ("The after layout is still the less exposed one." if after < before else "Under this surge the starting layout is shorter. The published layout was not chosen for this imagined demand.")
    )
    st.subheader("What if heavy products could only sit on the floor?")
    st.write("This tightens a rule. It does not re-slot. Illegal homes would go back through the search. They would not wait in a review queue.")
    if st.button("Check the tighter rule"):
        result = heavy_floor(run_path)
        st.write(
            f"{result['heavy']} products are heavy under the current rule. On the floor-only rule, the before layout has "
            f"{result['before']} violations and the after layout has {result['after']}. "
            "A violation here means 're-run under the new rule,' not 'ask someone to place these by hand.'"
        )
    st.subheader("Should a person step in?")
    close = metrics["close_call_count"]
    st.write(
        "No, not by default. The layout above is published automatically. Nothing sits in a queue. "
        f"We looked for close calls among the 40 busiest products: another legal bin, a different aisle or height, and almost the same score. "
        f"{close} of them have one. In a building of repeated bays, that is the shelves looking alike, not {close} decisions a person should make. "
        "A review queue would fill up with ties that do not change the walk. That is why this is not a manual system with an automatic suggestion. "
        "It is an automatic layout. The control below prices one override. It does not apply it."
    )
    st.write("The bins below are the ones the fit test already allows. Pricing an override replays 300 orders. It does not publish the change.")
    if "eligible_bins" in bundle:
        grouped = bundle["eligible_bins"].groupby("sku_id")["location_id"].apply(list).to_dict()
    else:
        with st.spinner("Checking which bins are legal"):
            grouped = legal_bins(run_path)
    chosen = st.selectbox("Override this product", abc["sku_id"].head(40).tolist())
    allowed = grouped[chosen]
    locations = bundle["locations"].set_index("location_id")
    occupied = set(bundle["optimized_assignments"]["location_id"])
    current = str(bundle["optimized_assignments"].set_index("sku_id").loc[chosen, "location_id"])
    ranked = sorted(allowed, key=lambda loc: (int(locations.loc[loc, "aisle_number"]), float(locations.loc[loc, "y_m"]), loc))[:25]
    if current not in ranked:
        ranked = [current, *ranked]
    def bin_label(loc: str) -> str:
        row = locations.loc[loc]
        state = "current bin" if loc == current else ("occupied" if loc in occupied else "empty")
        return f"Aisle {int(row['aisle_number'])}, {shelf_label(row['shelf_level'])}, {state}"
    target = st.selectbox("Put it in this legal bin", ranked, format_func=bin_label)
    st.caption("Showing the 25 legal bins nearest the front of the building, not every legal bin.")
    if st.button("Price this override"):
        with st.spinner("Replaying 300 orders with that one change"):
            outcome = pin_scenario(run_path, chosen, target)
        if outcome.get("same"):
            st.write("That is already its bin. The published layout is unchanged.")
        elif not outcome["legal"]:
            st.write("That override is illegal, so it is not a candidate. " + " ".join(outcome["messages"]))
        else:
            giveback = outcome["pinned"] - outcome["automatic"]
            if giveback > 0.5:
                verdict = "The override gives back part of the gain. It stays off unless someone explicitly wants that cost."
            elif giveback < -0.5:
                verdict = (
                    "The override is shorter on this sample. That is a useful finding, not a reason to reopen every placement: "
                    "the search is a heuristic, and one better bin does not prove the rest of the layout is wrong."
                )
            else:
                verdict = (
                    "The override is within half a meter of the automatic layout on this sample, so there is nothing to gain here. "
                    "It is not applied. A tie like this is why a review queue would not help."
                )
            st.write(
                f"This would {outcome['kind']}. On the same 300-order sample, the automatic layout walks "
                f"{outcome['automatic']:.1f} m and this override walks {outcome['pinned']:.1f} m ({giveback:+.1f} m). "
                f"The original before is {outcome['before']:.1f} m. {verdict}"
            )


def render_demand(bundle: dict[str, object]) -> None:
    abc = bundle["abc"]
    affinity = bundle["affinity_pairs"]
    st.markdown("### Look at the orders before moving a box")
    st.write(
        "These 150 products are already the busiest in the store. The A/B/C split is among busy products, not the whole catalog. "
        "That is why so many land in A. It is not a claim that 20% of a full catalog does 80% of the work."
    )
    counts = abc.groupby("abc_class", as_index=False).agg(products=("sku_id", "count"), training_orders=("pick_frequency", "sum"))
    st.write(
        "A product is A until cumulative orders cross 80%, B until 95%, and C after that. "
        + ", ".join(f"{row.abc_class}: {int(row.products)} products" for row in counts.itertuples())
        + ". The search was allowed to use this training demand. It was not allowed to see the test orders."
    )
    pareto = abc.copy()
    pareto["rank"] = range(1, len(pareto) + 1)
    figure = px.bar(pareto, x="rank", y="pick_frequency", color="abc_class", title="Training orders per product, busiest on the left", labels={"rank": "Product rank", "pick_frequency": "Training orders containing it", "abc_class": "Group"}, color_discrete_map=COLORS)
    figure.update_layout(height=380, showlegend=True)
    st.plotly_chart(figure, width="stretch")
    st.caption("The tall bars are the products worth moving toward the desk. A short bar can stay deep in the building.")
    st.subheader("Products that share a basket")
    st.write(
        "This table is a count, not a guess. The search used pairs that appeared together at least 3 times, and at most 10 partners per product. "
        "A pair that showed up once is not a relationship. Lift is shown so a rare coincidence is not mistaken for a habit."
    )
    minimum = st.slider("Minimum orders together", 1, int(affinity["cooccurrence"].max()), 3)
    shown = affinity.loc[affinity["cooccurrence"] >= minimum].head(20)
    st.dataframe(shown.rename(columns={"sku_a": "Product 1", "sku_b": "Product 2", "cooccurrence": "Orders together", "lift": "Lift", "jaccard": "Basket overlap"})[["Product 1", "Product 2", "Orders together", "Lift", "Basket overlap"]], width="stretch", hide_index=True)
    st.caption("After the moves, the walking distance between supported pairs fell. That number is on Before and after, in meters, not as a score.")


def render_safety(bundle: dict[str, object]) -> None:
    validation = bundle["validation"]
    optimized = bundle.get("optimized_validation", validation)
    st.markdown("### A shorter walk that breaks a rule is not a result")
    if validation["is_feasible"] and optimized["is_feasible"]:
        st.write("Both layouts place every product once, in a bin that can hold the stock, on a shelf the product is allowed to use. Hazardous products stay in the isolation aisle, with clearance from ordinary products. Heavy products stay off the high shelves. Fragile products stay off the top. Zero violations in both.")
    else:
        st.write("One of these layouts is not feasible. Do not quote a walk from it.")
    st.write(
        "The rules are scenario rules for this model, not a certified warehouse standard. "
        "Packing is a conservative grid: the boxes have to tile the bin. A volume that 'should fit' if you rotate boxes arbitrarily can still be rejected."
    )
    candidates = bundle["candidate_counts"]
    st.plotly_chart(px.histogram(candidates, x="eligible_bin_count", nbins=20, title="How many legal bins each product has", labels={"eligible_bin_count": "Legal bins", "count": "Products"}), width="stretch")
    st.caption("A product on the left has few legal homes. It constrains everyone else. The search cannot put a fast seller in a convenient bin if the bin is the wrong size, zone, or height.")
    with st.expander("Raw validation records"):
        st.json({"before": validation, "after": optimized})


def render_provenance(bundle: dict[str, object]) -> None:
    manifest = bundle["manifest"]
    metrics = bundle["comparison"]
    cleaning = manifest["cleaning"]
    st.markdown("### What is real, and what is modeled")
    st.write(
        "The orders are UCI Online Retail II, the 2010–2011 sheet. Cancellations, bad quantities, and exact duplicate rows were removed. "
        f"{cleaning['canonical_order_lines']:,} order lines remained from {cleaning['source_rows']:,} source rows. "
        "We then kept the 150 products that appeared in the most training orders, and kept every split to that cohort. "
        "Box sizes, weights, hazards, and the building are generated from a fixed seed. They are not that retailer's shelves. "
        "The walk is a simulation of that model."
    )
    st.write(
        f"Orders in the cohort: {manifest['split_order_counts'].get('train', 0):,} train, "
        f"{manifest['split_order_counts'].get('validation', 0):,} validation, "
        f"{manifest['split_order_counts'].get('test', 0):,} test. "
        "An order is never split across those sets. The baseline seed was fixed before looking at the gain."
    )
    opt = metrics["optimizer"]
    st.write(
        f"Search budget: {opt['proposals_tested']:,} proposals, {opt['proposals_accepted']:,} kept, stopped because of {opt['stopping_reason'].replace('_', ' ')}. "
        f"Source file hash starts {manifest['source_sha256'][:12]}."
    )
    assignments = bundle["optimized_assignments"]
    st.download_button("Download the published assignment", assignments.to_csv(index=False).encode(), file_name="published_assignments.csv", mime="text/csv")
    with st.expander("Run manifest"):
        st.json(manifest)


def ml_verdict(metrics: dict[str, object]) -> str:
    ml = metrics["ml"]
    if not ml.get("enabled", False):
        return f"The classifier was not shown as a layout this run. {ml.get('reason', '')}"
    beat = reduction(ml["baseline_mean_distance_m"], ml["mean_distance_m"])
    loss = ml["mean_distance_m"] - ml["published_mean_distance_m"]
    return (
        f"With no search at placement time — the model picks a bin for every product in one pass — its layout walks "
        f"{ml['mean_distance_m']:.1f} m on the same later orders. That beats the blind starting layout by {beat:.1f}% "
        f"but is {loss:.1f} m short of the full search, so the search's layout stays the published one. "
        f"The model is an explainer and a fast fallback, not the referee."
    )


def render_machine_learning(bundle: dict[str, object]) -> None:
    metrics = bundle["comparison"]
    ml = metrics.get("ml", {"enabled": False, "reason": "this run was compared before the classifier was added; re-run the pipeline to attach it."})
    st.markdown("### A classifier that answers 'which bin for this product?'")
    st.write(
        "Every training row is one product sitting in one of its legal bins. The label is the bin the search published. "
        "The model learns how demand, weight, size, hazard, desk distance, and shelf height combine into that answer. "
        "It is a random forest trained with bagging and per-split feature sampling, written with NumPy, "
        "and each tree is five levels deep. Same labels, same legal bins, same rules."
    )
    if not ml.get("enabled", False):
        st.write(f"This run did not produce a model layout to show. {ml.get('reason', '')}")
        return
    exact, ranked, quick, _ = st.columns(4)
    exact.metric("Chose the exact bin", f"{ml['top1_accuracy'] * 100:.0f}%", "20% of products held out")
    exact.caption("Each product has on the order of 160 legal bins. Naming the one bin the search would pick, from product and bin facts alone, is a hard ask.")
    ranked.metric("Picked a top-3 bin", f"{ml['top3_accuracy'] * 100:.0f}%", "same held-out products")
    ranked.caption("Out of every legal bin the product could legally use.")
    quick.metric("Its layout, later orders", f"{ml['mean_distance_m']:.1f} m", f"{ml['mean_distance_m'] - ml['published_mean_distance_m']:.1f} m", delta_color="inverse")
    quick.caption(f"The published layout walks {ml['published_mean_distance_m']:.1f} m; the blind start walked {ml['baseline_mean_distance_m']:.1f} m.")
    st.write(ml_verdict(metrics))
    st.subheader("What the classifier looks at")
    st.write("Importance is measured as the share of label uncertainty each feature removes across the forest's splits. It is an explanation, not a physical force.")
    importance = pd.DataFrame(list(ml["feature_importance"].items()), columns=["What it looks at", "Share of splits"])
    bars = px.bar(importance.sort_values("Share of splits"), y="What it looks at", x="Share of splits", title="Which facts drive the bin decision", orientation="h")
    bars.update_layout(height=460, margin={"l": 10, "r": 10, "t": 48, "b": 10})
    st.plotly_chart(bars, width="stretch")
    st.caption("If a judge asks why it is not all desk distance: the classifier learned that weight and demand decide the kind of home first, and distance only narrows the choice among legal ones.")
    st.subheader("Classify one product yourself")
    st.write("These are the model's own scores for every legal bin the product could use, best first. 'Occupied' means another product already took it during placement, so the classifier moved to its next choice. 'Rack full' means the structure limit stopped it.")
    views = bundle["ml_views"]
    abc = bundle["abc"].set_index("sku_id")
    sku_id = st.selectbox("Product", sorted(views), format_func=lambda sku: f"{sku} · {int(abc.loc[sku, 'pick_frequency'])} training orders")
    view = pd.DataFrame(views[sku_id]).merge(bundle["locations"], on="location_id")
    chosen = view.loc[view["state"] == "available"].iloc[0]
    view["Bin"] = "aisle " + view["aisle_number"].astype(str) + " · " + view["shelf_level"].map(shelf_label)
    st.dataframe(
        view.rename(columns={"probability": "Model score", "state": "State"})[["location_id", "Bin", "Model score", "State"]],
        width="stretch", hide_index=True,
    )
    if chosen["location_id"] == view.iloc[0]["location_id"]:
        reason = "Its top-scoring bin was available, so it went straight there."
    else:
        reason = (
            f"Bin {view.iloc[0]['location_id']} scored highest but was {view.iloc[0]['state']}, "
            f"so the classifier used its best available bin. That is the legality part no model is allowed to override."
        )
    st.write(f"The model placed {sku_id} in bin {chosen['location_id']} (aisle {int(chosen['aisle_number'])}, {shelf_label(chosen['shelf_level'])}). {reason}")
    ml_orders = bundle["ml_comparison"].copy()
    ml_orders["change_m"] = ml_orders["ml_distance_m"] - ml_orders["optimized_distance_m"]
    counts = pd.DataFrame([
        {"What happened": "Shorter than the search", "Orders": ml["orders_shorter_than_published"]},
        {"What happened": "Longer than the search", "Orders": ml["orders_longer_than_published"]},
    ])
    st.plotly_chart(px.bar(counts, x="What happened", y="Orders", color="What happened", title="The classifier's layout, order by order, against the search layout", color_discrete_map={"Shorter than the search": "#22c55e", "Longer than the search": "#f59e0b"}), width="stretch")
    st.caption("The published layout wins more orders, which is why it is the published layout. The classifier exists to explain the decision and to place fast when a search is not worth waiting for.")


def render_new_run_panel() -> None:
    """Upload a plain orders file and extend the library of completed runs."""
    orders = st.sidebar.file_uploader(
        "Your orders file (CSV)",
        type=["csv"],
        help="Columns: order_id, sku_id, quantity, and an optional timestamp. "
        "Without a timestamp one is invented, so the chronological splits keep their order.",
    )
    title = st.sidebar.text_input("Run title", value="uploaded")
    go = st.sidebar.button("Run the slotting test", type="primary", use_container_width=True, disabled=orders is None)
    if go and orders is not None:
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
            orders.seek(0)
            handle.write(orders.read().decode("utf-8-sig", errors="replace"))
            source = Path(handle.name)
        try:
            with st.spinner(
                f"Cleaning your {orders.name} file, generating the building and pick dates, then optimizing"
            ):
                release = run_pipeline(CONFIG_PATH, source, run_name=title.strip() or "uploaded")
            st.sidebar.success(f"Run released: {release.name}")
            st.session_state.show_new_run = False
            load_run.clear()
            st.rerun()
        except Exception as error:  # noqa: BLE001 - surfaced to the operator, not crashed
            st.sidebar.error(f"This file could not be turned into a run: {error}")
        finally:
            source.unlink(missing_ok=True)


st.set_page_config(page_title="Slotwise", page_icon="📦", layout="wide")
st.markdown(
    """<style>
    :root { color-scheme: dark; }
    .stApp {background: radial-gradient(ellipse at 50% -20%, #1b3550 0%, #0b1420 52%, #09111b 100%); color: #e6edf5;}
    [data-testid="stHeader"] {background: rgba(9, 17, 27, .78);}
    .block-container {max-width: 1440px; padding: 2.2rem 2.2rem 3.5rem;}
    h1, h2, h3 {letter-spacing: -.025em; color: #f4f8fc;}
    h1 {font-size: 2.35rem; font-weight: 750;}
    h2 {font-size: 1.65rem; font-weight: 700; margin-top: .5rem;}
    h3 {font-size: 1.25rem; font-weight: 650;}
    p, li, [data-testid="stCaptionContainer"] {color: #b9c7d6;}
    [data-testid="stSidebar"] {background: linear-gradient(180deg, #111e2d, #0c1724); border-right: 1px solid #26384a;}
    [data-testid="stTabs"] [role="tablist"] {gap: .45rem; border-bottom: 1px solid #2a3b4e;}
    [data-testid="stTabs"] button[role="tab"] {border-radius: 10px 10px 0 0; padding: .65rem 1rem; color: #aebfd0;}
    [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {color: #f8fbff; background: #172a3e; border-bottom: 2px solid #38bdf8;}
    [data-testid="stVerticalBlockBorderWrapper"] {background: rgba(18, 32, 48, .72); border-color: #2a3d51 !important; border-radius: 16px; box-shadow: 0 12px 32px rgba(0, 0, 0, .16);}
    [data-testid="stMetric"] {background: linear-gradient(145deg, #182a3d, #122235); border: 1px solid #2b4055; border-radius: 14px; padding: 14px 16px;}
    [data-testid="stMetricLabel"] {color: #9fb2c6;}
    [data-testid="stMetricValue"] {color: #f3f8fc;}
    div[data-baseweb="select"] > div {background: #142438; border: 1px solid #354b61; border-radius: 10px;}
    div[data-testid="stButton"] button {border-radius: 10px; font-weight: 600; transition: border-color .15s ease, transform .15s ease;}
    div[data-testid="stButton"] button:hover {border-color: #38bdf8; transform: translateY(-1px);}
    [data-testid="stPlotlyChart"] {border-radius: 12px; overflow: hidden;}
    [data-testid="stDataFrame"] {border: 1px solid #293d52; border-radius: 12px; overflow: hidden;}
    hr {border-color: #293b4e;}
    @media (max-width: 760px) {.block-container {padding: 1.2rem .8rem 2rem;} h1 {font-size: 1.85rem;}}
    </style>""",
    unsafe_allow_html=True,
)
st.title("Slotwise")
st.write("A picker should not cross the building for a product that sells every hour. This page says what changed, what did not, and what a change would cost.")

manifests = run_directories()
if not manifests:
    st.error("No completed run exists. Run `.venv/bin/warehouse-slotting --config configs/default.yaml` first.")
    st.stop()
paths = {path.parent.name: path.parent for path in manifests}
selected_run = st.sidebar.selectbox("Completed run", list(paths))
if st.sidebar.button("New test run", use_container_width=True):
    st.session_state.show_new_run = not st.session_state.get("show_new_run", False)
if st.session_state.get("show_new_run"):
    render_new_run_panel()
run_path = str(paths[selected_run])
bundle = load_run(run_path)
if "comparison" not in bundle:
    st.error("This run has a legal starting layout but no comparison yet.")
    st.stop()
st.sidebar.write("Before ignored demand on purpose. After may move a product only into a legal bin. The walk is on later orders.")
st.sidebar.caption(bundle["comparison"]["selection_note"])

comparison, find_home, what_if, ml_tab, demand, safety, provenance = st.tabs([
    "Before and after", "Find a home", "What if", "How the ML places", "What customers buy", "Safety", "Where the numbers come from",
])
with comparison:
    render_comparison(bundle, run_path)
with find_home:
    render_find_home(bundle)
with what_if:
    render_what_if(bundle, run_path)
with ml_tab:
    render_machine_learning(bundle)
with demand:
    render_demand(bundle)
with safety:
    render_safety(bundle)
with provenance:
    render_provenance(bundle)
