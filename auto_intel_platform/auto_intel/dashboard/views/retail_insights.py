"""
dashboard/views/retail_insights.py — Retail Pulse Page
=======================================================
Shows FADA retail registration data SEPARATELY from wholesale.
The only connection to wholesale is the channel inventory section,
where wholesale and retail are compared to compute dealer stock levels.

Sections:
  1. What is this data  — clear explainer for first-time readers
  2. Latest retail KPIs — total retail, YoY, vs wholesale spread
  3. Segment snapshot   — wholesale vs retail side-by-side (current month)
  4. Channel inventory  — weeks of supply trend by segment
  5. Inventory health   — LEAN / HEALTHY / ELEVATED / BLOATED status table
  6. Retail trend       — 12-month retail volume trend per segment
"""

from __future__ import annotations

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from dashboard import components as C
from dashboard.theme import SEGMENT_COLORS, plotly_layout
from analytics.inventory import (
    channel_inventory, latest_inventory_snapshot,
    wholesale_by_segment, wholesale_retail_trend, health_label,
)


def _load_retail() -> pd.DataFrame:
    """Load retail.csv as a DataFrame."""
    retail_path = ROOT / "data" / "retail.csv"
    if not retail_path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(retail_path)
        df["retail_total"] = pd.to_numeric(df["retail_total"], errors="coerce").fillna(0).astype(int)
        df["yoy_pct"]      = pd.to_numeric(df["yoy_pct"],      errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()


def render():
    from dashboard.data_layer import load_all
    norm_df, _, _, _ = load_all()
    retail_df = _load_retail()

    if retail_df.empty:
        C.empty_state(
            "No Retail Data Yet",
            "Run `python data/generate_retail_sample.py` to seed sample data, "
            "or wait for the FADA pipeline to collect live data.",
            action="python data/generate_retail_sample.py",
        )
        return

    # ── What is this data ────────────────────────────────────────────────────
    C.section_header("About This Data")
    st.markdown(
        """
        <div style='background:#1E293B;border-left:3px solid #2563EB;
             padding:0.8rem 1rem;border-radius:0 6px 6px 0;
             font-size:0.84rem;color:#CBD5E1;line-height:1.7;'>
        <b style='color:#F8FAFC;'>Retail</b> = vehicles actually <b>registered</b> by consumers at RTO (FADA source).<br>
        <b style='color:#F8FAFC;'>Wholesale</b> = vehicles <b>shipped from factory to dealers</b> (OEM press releases).<br><br>
        The <b style='color:#F8FAFC;'>gap</b> between them is <b style='color:#F8FAFC;'>channel inventory</b> —
        how many units are sitting in the dealer network. A growing gap signals
        channel-stuffing risk; a shrinking gap signals strong retail demand.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Latest month KPIs ────────────────────────────────────────────────────
    latest_month = retail_df["filing_month_year"].max()
    latest_rt    = retail_df[retail_df["filing_month_year"] == latest_month]
    total_retail = int(latest_rt["retail_total"].sum())

    # Prior year same month
    yr, mo = latest_month.split("-")
    prior_yr_month = f"{int(yr)-1}-{mo}"
    prior_rt_df = retail_df[retail_df["filing_month_year"] == prior_yr_month]
    total_prior  = int(prior_rt_df["retail_total"].sum()) if not prior_rt_df.empty else 0
    retail_yoy   = (total_retail - total_prior) / total_prior if total_prior else None

    # Wholesale total same month
    ws_df = wholesale_by_segment(norm_df)
    ws_latest = ws_df[ws_df["filing_month_year"] == latest_month]
    total_ws  = int(ws_latest["wholesale_total"].sum()) if not ws_latest.empty else 0
    spread    = total_ws - total_retail

    C.section_header("Retail Snapshot", sub=f"FADA retail registrations — {latest_month}")
    C.kpi_row([
        {
            "label": "Retail Registrations",
            "value": C.fmt_units(total_retail),
            "unit":  "units",
            "delta": C.fmt_pct(retail_yoy) if retail_yoy is not None else None,
            "delta_dir": C.delta_dir(retail_yoy) if retail_yoy else "flat",
            "foot":  "FADA retail — consumer registrations at RTO",
        },
        {
            "label": "Wholesale (OEM dispatches)",
            "value": C.fmt_units(total_ws),
            "unit":  "units",
            "foot":  "Factory-to-dealer shipments (same month)",
        },
        {
            "label": "Monthly Spread",
            "value": f"{'+' if spread>=0 else ''}{spread:,}",
            "unit":  "units",
            "delta_dir": "down" if spread > 0 else "up",
            "foot":  "Wholesale − Retail (positive = stock building)",
        },
        {
            "label": "Source",
            "value": "FADA",
            "foot":  "Federation of Automobile Dealers Associations of India",
        },
    ])

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Segment comparison: wholesale vs retail (current month) ────────────
    C.section_header("Wholesale vs Retail by Segment", sub=f"Current month: {latest_month}")

    compare_rows = []
    for seg in ["PV", "2W", "3W", "CV", "Tractor", "EV"]:
        ws_val = int(ws_latest[ws_latest["segment"] == seg]["wholesale_total"].sum()) if not ws_latest.empty else 0
        rt_val = int(latest_rt[latest_rt["segment"] == seg]["retail_total"].sum())
        spread_seg = ws_val - rt_val
        compare_rows.append({
            "Segment":   seg,
            "Wholesale": ws_val,
            "Retail":    rt_val,
            "Spread":    spread_seg,
            "Spread %":  f"{spread_seg/rt_val*100:+.1f}%" if rt_val else "—",
        })

    compare_df = pd.DataFrame(compare_rows)

    # Grouped bar chart
    fig = go.Figure()
    for label, col, color in [
        ("Wholesale", "Wholesale", "#2563EB"),
        ("Retail",    "Retail",    "#15803D"),
    ]:
        fig.add_trace(go.Bar(
            name=label,
            x=compare_df["Segment"],
            y=compare_df[col],
            marker_color=color,
            text=[f"{v:,.0f}" for v in compare_df[col]],
            textposition="outside",
        ))

    fig.update_layout(
        **plotly_layout(height=360, title="Wholesale vs Retail — Current Month"),
        barmode="group",
        bargap=0.25,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Table
    st.dataframe(
        compare_df.style.format({
            "Wholesale": "{:,.0f}",
            "Retail":    "{:,.0f}",
            "Spread":    "{:+,.0f}",
        }),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Channel inventory ────────────────────────────────────────────────────
    C.section_header(
        "Channel Inventory (Dealer Stock)",
        sub="Cumulative wholesale − retail since data start. "
            "Shows units sitting in dealer network.",
    )

    inv_df = channel_inventory(norm_df, retail_df)

    if inv_df.empty:
        C.empty_state("Insufficient data", "Need both wholesale and retail data for the same months.")
    else:
        # Latest snapshot health table
        snap = latest_inventory_snapshot(inv_df)

        health_rows = []
        for _, row in snap.iterrows():
            lbl, clr = health_label(row.get("weeks_of_supply"))
            health_rows.append({
                "Segment":          row["segment"],
                "Inventory (units)": f"{int(row['cum_inventory']):+,}",
                "Weeks of Supply":   f"{row['weeks_of_supply']:.1f}w" if not pd.isna(row.get("weeks_of_supply")) else "—",
                "Status":            lbl,
                "Wholesale":         f"{int(row['wholesale_total']):,}",
                "Retail":            f"{int(row['retail_total']):,}",
                "Monthly Spread":    f"{int(row['monthly_spread']):+,}",
            })

        st.dataframe(
            pd.DataFrame(health_rows),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # Weeks of supply trend chart
        C.section_header("Weeks of Supply Trend", sub="By segment — healthy range is 3–6 weeks")

        segments_available = inv_df["segment"].unique()
        sel_seg = st.selectbox("Segment", sorted(segments_available), key="inv_seg")

        trend = wholesale_retail_trend(inv_df, sel_seg)
        if not trend.empty:
            fig2 = go.Figure()

            # Shaded healthy band (3–6 weeks)
            fig2.add_hrect(
                y0=3, y1=6,
                fillcolor="rgba(21,128,61,0.08)",
                line_width=0,
                annotation_text="Healthy (3-6w)",
                annotation_position="right",
                annotation_font_color="#15803D",
            )

            fig2.add_trace(go.Scatter(
                x=trend["filing_month_year"],
                y=trend["weeks_of_supply"],
                mode="lines+markers",
                name="Weeks of Supply",
                line=dict(color="#2563EB", width=2),
                marker=dict(size=6),
            ))

            # Reference lines
            for level, label, color in [(3, "LEAN threshold", "#15803D"), (8, "BLOATED threshold", "#DC2626")]:
                fig2.add_hline(
                    y=level, line_dash="dash", line_color=color,
                    annotation_text=label, annotation_position="right",
                    annotation_font_color=color,
                )

            fig2.update_layout(
                **plotly_layout(height=320, title=f"{sel_seg} — Weeks of Supply"),
                yaxis_title="Weeks",
            )
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Retail trend ─────────────────────────────────────────────────────────
    C.section_header("Retail Volume Trend", sub="12-month rolling retail registrations by segment")

    seg_filter = st.multiselect(
        "Segments",
        options=["PV", "2W", "3W", "CV", "Tractor", "EV"],
        default=["PV", "2W"],
        key="retail_seg_filter",
    )

    recent = retail_df[
        retail_df["filing_month_year"] >= (
            retail_df["filing_month_year"].max()[:4] + "-01"
        )
    ]
    chart_df = recent[recent["segment"].isin(seg_filter)] if seg_filter else recent

    if not chart_df.empty:
        fig3 = go.Figure()
        for seg in seg_filter:
            sub = chart_df[chart_df["segment"] == seg].sort_values("filing_month_year")
            if sub.empty:
                continue
            color = SEGMENT_COLORS.get(seg, "#94A3B8")
            fig3.add_trace(go.Scatter(
                x=sub["filing_month_year"],
                y=sub["retail_total"],
                name=seg,
                mode="lines+markers",
                line=dict(color=color, width=2),
                marker=dict(size=5),
            ))

        fig3.update_layout(
            **plotly_layout(height=340, title="Retail Registrations — Monthly Trend"),
            yaxis_title="Units (Retail)",
        )
        st.plotly_chart(fig3, use_container_width=True)

    # Data source note
    C.footer(
        "Retail data: FADA (Federation of Automobile Dealers Associations of India) — fada.in",
    )
