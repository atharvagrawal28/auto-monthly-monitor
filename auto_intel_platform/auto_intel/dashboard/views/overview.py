"""
views/overview.py — Industry Overview
=======================================
The morning-coffee page. Tells the analyst:
  - What was the industry's wholesale volume this month, vs last month / last year?
  - Which segments are hot / cold?
  - Top movers (by absolute units and by share gain in pp)?
  - EV penetration & where it stands vs 6M ago.
  - Data freshness — how complete is this month's print?
"""

from __future__ import annotations
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from .. import components as C
from ..theme import BRAND, SEGMENT_COLORS, OEM_COLORS, plotly_layout
from ..data_layer import (
    load_all, latest_month, month_options,
    DISPLAY_NAMES, SEGMENT_LABELS,
)
from analytics.benchmarks import ev_penetration, growth_bridge
from analytics.share import industry_concentration


def render():
    norm, gran, fs, rq = load_all()

    if norm.empty:
        C.empty_state(
            "No data yet",
            "Run `python data/generate_sample.py` to load 24 months of "
            "realistic sample data, then refresh."
        )
        return

    months = month_options(norm)
    cur = months[0]
    prev = months[1] if len(months) > 1 else None
    yoy_month = (
        (pd.to_datetime(cur + "-01") - pd.DateOffset(years=1)).strftime("%Y-%m")
        if cur else None
    )

    # ── Filter bar ───────────────────────────────────────────────────────────
    sel_col1, sel_col2, _ = st.columns([1, 1, 3])
    selected_month = sel_col1.selectbox(
        "Reporting month", months, index=0, key="ov_month",
        format_func=lambda m: pd.to_datetime(m + "-01").strftime("%b %Y"),
    )
    comparison_mode = sel_col2.selectbox(
        "Compare against", ["Prior month (MoM)", "Same month last year (YoY)"],
        index=0, key="ov_cmp",
    )

    cmp_key = "mom" if comparison_mode.startswith("Prior") else "yoy"

    # ── Headline KPIs ───────────────────────────────────────────────────────
    C.section_header("Industry headline", "wholesale dispatches reported by listed OEMs")

    cur_df  = norm[norm["filing_month_year"] == selected_month]
    prev_period = prev if cmp_key == "mom" else yoy_month
    prev_df = norm[norm["filing_month_year"] == prev_period] if prev_period else pd.DataFrame()

    cur_total  = cur_df["total"].sum()
    prev_total = prev_df["total"].sum() if not prev_df.empty else None
    pct_change = (
        (cur_total - prev_total) / prev_total
        if prev_total and prev_total > 0 else None
    )
    cur_exports = cur_df["exports"].sum()
    cur_domestic = cur_df["domestic"].sum()
    export_pct = (cur_exports / cur_total) if cur_total > 0 else None

    ev_units = cur_df[cur_df["segment"] == "EV"]["total"].sum()
    ev_total_comparable = cur_df[cur_df["segment"].isin(
        ["PV", "2W", "3W", "CV", "EV"]
    )]["total"].sum()
    ev_pen = ev_units / ev_total_comparable if ev_total_comparable > 0 else None

    C.kpi_row([
        {
            "label": "Total wholesale volume",
            "value": C.fmt_units(cur_total),
            "unit":  "units",
            "delta": C.fmt_pct(pct_change),
            "delta_dir": C.delta_dir(pct_change),
            "foot":  f"vs {pd.to_datetime(prev_period + '-01').strftime('%b %Y')}"
                     if prev_period else "no prior period",
        },
        {
            "label": "Domestic",
            "value": C.fmt_units(cur_domestic),
            "unit":  "units",
            "foot":  f"{cur_domestic/cur_total:.1%} of total" if cur_total > 0 else "—",
        },
        {
            "label": "Exports",
            "value": C.fmt_units(cur_exports),
            "unit":  "units",
            "foot":  f"{export_pct:.1%} export mix" if export_pct else "—",
        },
        {
            "label": "EV penetration",
            "value": f"{ev_pen*100:.2f}%" if ev_pen else "—",
            "foot":  "EV ÷ (PV+CV+2W+3W+EV) wholesale",
        },
    ])

    # ── Segment grid ────────────────────────────────────────────────────────
    C.section_header(
        "Segment performance",
        f"All listed-OEM dispatches by segment, {cmp_key.upper()} change",
    )

    seg_now = cur_df.groupby("segment", as_index=False).agg(
        total=("total", "sum"),
        domestic=("domestic", "sum"),
        exports=("exports", "sum"),
        oems=("company_key", "nunique"),
    )
    seg_prev = (
        prev_df.groupby("segment", as_index=False)["total"].sum()
            .rename(columns={"total": "total_prev"})
        if not prev_df.empty else pd.DataFrame(columns=["segment", "total_prev"])
    )
    seg = seg_now.merge(seg_prev, on="segment", how="left")
    seg["pct_change"] = (seg["total"] - seg["total_prev"]) / seg["total_prev"]
    seg["export_mix"] = seg["exports"] / seg["total"].replace(0, pd.NA)
    seg["label"] = seg["segment"].map(SEGMENT_LABELS).fillna(seg["segment"])
    seg = seg.sort_values("total", ascending=False)

    seg_cols = st.columns(min(len(seg), 6) or 1)
    for col, (_, row) in zip(seg_cols, seg.iterrows()):
        with col:
            C.kpi(
                label=row["label"],
                value=C.fmt_units(row["total"]),
                unit="units",
                delta=C.fmt_pct(row["pct_change"]),
                delta_dir=C.delta_dir(row["pct_change"]),
                foot=f"{row['oems']} OEMs · {row['export_mix']*100:.1f}% exports"
                     if pd.notna(row["export_mix"]) else f"{row['oems']} OEMs",
            )

    # ── Top movers ──────────────────────────────────────────────────────────
    C.section_header(
        "Top movers — share of industry change",
        f"who drove the {cmp_key.upper()} delta, in industry percentage points",
    )

    movers_rows = []
    for seg_name in seg["segment"].tolist():
        if not prev_period:
            continue
        bridge = growth_bridge(norm, seg_name, selected_month, prev_period)
        if bridge.empty:
            continue
        bridge["segment"] = seg_name
        movers_rows.append(bridge)

    if movers_rows:
        bridge_df = pd.concat(movers_rows, ignore_index=True)
        bridge_df["display_name"] = bridge_df["company_key"].map(DISPLAY_NAMES).fillna(bridge_df["company_key"])
        bridge_df["segment_label"] = bridge_df["segment"].map(SEGMENT_LABELS).fillna(bridge_df["segment"])
        top_pos = bridge_df.nlargest(5, "contribution_pp")
        top_neg = bridge_df.nsmallest(5, "contribution_pp")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(
                f'**Adding to industry growth** '
                f'{C.chip("positive contribution", "green")}',
                unsafe_allow_html=True,
            )
            _render_mover_table(top_pos)
        with c2:
            st.markdown(
                f'**Dragging on industry growth** '
                f'{C.chip("negative contribution", "red")}',
                unsafe_allow_html=True,
            )
            _render_mover_table(top_neg)

    # ── Industry trend & EV trend ──────────────────────────────────────────
    C.section_header("Volume trend", "last 12 months, stacked by segment")
    trend_cutoff = (pd.to_datetime(selected_month + "-01") - pd.DateOffset(months=11)).strftime("%Y-%m")
    trend_df = norm[
        (norm["filing_month_year"] >= trend_cutoff) &
        (norm["filing_month_year"] <= selected_month)
    ].groupby(["filing_month_year", "segment"], as_index=False)["total"].sum()
    trend_df["month_label"] = pd.to_datetime(trend_df["filing_month_year"] + "-01").dt.strftime("%b %y")
    trend_df["segment_label"] = trend_df["segment"].map(SEGMENT_LABELS).fillna(trend_df["segment"])

    fig = px.bar(
        trend_df, x="month_label", y="total", color="segment",
        color_discrete_map=SEGMENT_COLORS,
        category_orders={"segment": ["PV", "CV", "2W", "3W", "Tractor", "EV"]},
        labels={"total": "Units", "month_label": "Month"},
    )
    fig.update_layout(**plotly_layout(height=340))
    fig.update_layout(barmode="stack", bargap=0.22, legend_title="")
    st.plotly_chart(fig, use_container_width=True)

    # ── Industry concentration (HHI) ─────────────────────────────────────────
    C.section_header(
        "Industry concentration",
        "HHI per segment — <1000 low · 1000-1800 moderate · >1800 concentrated",
    )
    hhi_df = industry_concentration(norm[norm["filing_month_year"] == selected_month])
    if not hhi_df.empty:
        hhi_df["segment_label"] = hhi_df["segment"].map(SEGMENT_LABELS).fillna(hhi_df["segment"])
        hhi_df["top3_share_pct"] = (hhi_df["top3_share"] * 100).round(1)
        show = hhi_df[["segment_label", "hhi", "top3_share_pct", "oem_count"]].copy()
        show.columns = ["Segment", "HHI", "Top-3 share (%)", "OEMs tracked"]
        st.dataframe(show, use_container_width=True, hide_index=True)

    # ── EV penetration trend ────────────────────────────────────────────────
    ev = ev_penetration(norm)
    if not ev.empty:
        C.section_header("EV penetration trend", "EV share of comparable wholesale")
        ev["month_label"] = pd.to_datetime(ev["filing_month_year"] + "-01").dt.strftime("%b %y")
        fig = px.line(
            ev.tail(18), x="month_label", y="ev_pct_of_comparable",
            markers=True,
        )
        fig.update_traces(line_color=SEGMENT_COLORS["EV"], line_width=2.4)
        fig.update_layout(**plotly_layout(height=280))
        fig.update_yaxes(tickformat=".2%")
        fig.update_xaxes(title_text="")
        st.plotly_chart(fig, use_container_width=True)


# ── helpers ──────────────────────────────────────────────────────────────────

def _render_mover_table(df: pd.DataFrame):
    show = df[["display_name", "segment_label", "delta", "contribution_pp"]].copy()
    show.columns = ["OEM", "Segment", "Δ units", "Industry contribution (pp)"]
    show["Δ units"] = show["Δ units"].apply(lambda v: f"{int(v):+,}")
    show["Industry contribution (pp)"] = show["Industry contribution (pp)"].apply(
        lambda v: f"{v:+.2f}"
    )
    st.dataframe(show, use_container_width=True, hide_index=True)
