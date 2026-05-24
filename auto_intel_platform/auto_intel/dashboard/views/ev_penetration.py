"""
views/ev_penetration.py — EV penetration tracker
=================================================
Headline: EV share of comparable wholesale (PV+CV+2W+3W+EV).
Drill-down: per-OEM EV exposure (units + share).
Trend:    monthly penetration line over 24 months.
"""

from __future__ import annotations
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from .. import components as C
from ..theme import SEGMENT_COLORS, OEM_COLORS, BRAND, plotly_layout
from ..data_layer import load_all, month_options, DISPLAY_NAMES
from analytics.benchmarks import ev_penetration


def render():
    # ── Data separation notice (no retail/VAHAN data on this page) ───────────
    # This page uses ONLY OEM wholesale data (segment == "EV" from normalized.csv).
    # FADA retail / VAHAN registration data is on the Retail Pulse page exclusively.
    norm, _, _, _ = load_all()
    if norm.empty:
        C.empty_state("No data", "Generate sample data first.")
        return

    months = month_options(norm)
    sel_month = st.selectbox(
        "Reporting month", months,
        format_func=lambda m: pd.to_datetime(m + "-01").strftime("%b %Y"),
        key="ev_month",
    )

    ev_trend = ev_penetration(norm)
    if ev_trend.empty:
        C.empty_state("No EV data", "No EV-segment rows in dataset.")
        return

    cur = ev_trend[ev_trend["filing_month_year"] == sel_month]
    cur_row = cur.iloc[0] if not cur.empty else ev_trend.iloc[-1]

    yoy_month = (pd.to_datetime(sel_month + "-01") - pd.DateOffset(years=1)).strftime("%Y-%m")
    yoy_row = ev_trend[ev_trend["filing_month_year"] == yoy_month]
    yoy_pct = float(yoy_row["ev_pct_of_comparable"].iloc[0]) if not yoy_row.empty else None
    delta_pp = (
        (cur_row["ev_pct_of_comparable"] - yoy_pct) * 100
        if yoy_pct is not None else None
    )

    C.kpi_row([
        {"label": "EV penetration",
         "value": f"{cur_row['ev_pct_of_comparable']*100:.2f}%",
         "delta": C.fmt_pp(delta_pp),
         "delta_dir": C.delta_dir(delta_pp),
         "foot":  "vs same month last year"},
        {"label": "EV wholesale",
         "value": C.fmt_units(cur_row["ev_total"]),
         "unit":  "units"},
        {"label": "Comparable wholesale",
         "value": C.fmt_units(cur_row["comparable_total"]),
         "unit":  "units",
         "foot":  "PV + CV + 2W + 3W + EV"},
    ])

    # ── EV penetration trend ───────────────────────────────────────────────
    C.section_header("Penetration trend", "EV share of comparable wholesale")
    last = ev_trend.tail(24).copy()
    last["month_label"] = pd.to_datetime(last["filing_month_year"] + "-01").dt.strftime("%b %y")

    fig = go.Figure()
    fig.add_scatter(
        x=last["month_label"], y=last["ev_pct_of_comparable"],
        mode="lines+markers", name="EV %",
        line=dict(color=SEGMENT_COLORS["EV"], width=2.6),
        fill="tozeroy", fillcolor="rgba(14,116,144,0.10)",
    )
    fig.update_layout(**plotly_layout(height=320))
    fig.update_yaxes(tickformat=".2%", title_text="")
    st.plotly_chart(fig, use_container_width=True)

    # ── Per-OEM EV exposure ────────────────────────────────────────────────
    C.section_header(
        "Per-OEM EV exposure",
        f"selected month: {pd.to_datetime(sel_month + '-01').strftime('%b %Y')}",
    )
    ev_rows = norm[(norm["segment"] == "EV") & (norm["filing_month_year"] == sel_month)].copy()
    if ev_rows.empty:
        C.empty_state("No per-OEM EV print", "No EV-segment rows for the selected month.")
        return

    ev_rows = ev_rows.sort_values("total", ascending=False)
    ev_total = ev_rows["total"].sum()
    ev_rows["share_of_ev"] = ev_rows["total"] / ev_total if ev_total > 0 else None

    c1, c2 = st.columns([3, 4])
    with c1:
        fig = px.pie(
            ev_rows, values="total", names="display_name", hole=0.55,
            color="company_key", color_discrete_map=OEM_COLORS,
        )
        fig.update_traces(textinfo="percent",
                          hovertemplate="<b>%{label}</b><br>%{value:,} units (%{percent})<extra></extra>")
        fig.update_layout(**plotly_layout(height=320))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        table = pd.DataFrame({
            "OEM":           ev_rows["display_name"],
            "EV units":      ev_rows["total"].apply(C.fmt_units),
            "Share of EV":   ev_rows["share_of_ev"].apply(
                                  lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
            "YoY":           ev_rows["yoy_pct"].apply(C.fmt_pct),
            "MoM":           ev_rows["mom_pct"].apply(C.fmt_pct),
        })
        st.dataframe(table, use_container_width=True, hide_index=True)
