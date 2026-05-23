"""
views/market_share.py — Market share & concentration
======================================================
For a (segment, month) cell:
  - ranked share table with share Δ MoM (pp) and Δ YoY (pp)
  - donut + treemap visuals
  - 12-month share migration ribbon chart
  - HHI trend with concentration band shading
"""

from __future__ import annotations
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from .. import components as C
from ..theme import OEM_COLORS, SEGMENT_COLORS, BRAND, plotly_layout
from ..data_layer import load_all, month_options, DISPLAY_NAMES, SEGMENT_LABELS
from analytics.share import industry_concentration


def render():
    norm, _, _, _ = load_all()
    if norm.empty:
        C.empty_state("No data", "Generate sample data first.")
        return

    months = month_options(norm)
    segments = sorted(norm["segment"].dropna().unique().tolist())

    c1, c2 = st.columns(2)
    sel_seg = c1.selectbox(
        "Segment", segments,
        format_func=lambda s: SEGMENT_LABELS.get(s, s),
        key="ms_seg",
    )
    sel_month = c2.selectbox(
        "Month", months,
        format_func=lambda m: pd.to_datetime(m + "-01").strftime("%b %Y"),
        key="ms_month",
    )

    sub = norm[(norm["segment"] == sel_seg) & (norm["filing_month_year"] == sel_month)].copy()
    if sub.empty:
        C.empty_state("No data", f"No rows for {SEGMENT_LABELS.get(sel_seg, sel_seg)} in {sel_month}.")
        return

    industry_total = sub["total"].sum()
    n_oems = sub["company_key"].nunique()
    top3 = sub.nlargest(3, "total")["total"].sum()
    top3_share = top3 / industry_total if industry_total > 0 else None

    hhi_cur = industry_concentration(sub)
    cur_hhi = float(hhi_cur["hhi"].iloc[0]) if not hhi_cur.empty else None

    C.kpi_row([
        {"label": "Industry volume",
         "value": C.fmt_units(industry_total), "unit": "units"},
        {"label": "OEMs tracked", "value": str(n_oems)},
        {"label": "Top-3 share",
         "value": f"{top3_share*100:.1f}%" if top3_share else "—"},
        {"label": "HHI", "value": f"{cur_hhi:.0f}" if cur_hhi else "—",
         "foot": _hhi_band(cur_hhi)},
    ])

    # ── Ranked share table ─────────────────────────────────────────────────
    C.section_header("Share table", "ranked by current-month share")
    sub_sorted = sub.sort_values("market_share_pct", ascending=False)
    table = pd.DataFrame({
        "Rank":              range(1, len(sub_sorted) + 1),
        "OEM":               sub_sorted["display_name"],
        "Volume":            sub_sorted["total"].apply(C.fmt_units),
        "Share":             sub_sorted["market_share_pct"].apply(
                                  lambda v: f"{v*100:.2f}%" if pd.notna(v) else "—"),
        "Share Δ MoM (pp)":  sub_sorted["market_share_delta_mom_pp"].apply(C.fmt_pp),
        "Share Δ YoY (pp)":  sub_sorted["market_share_delta_yoy_pp"].apply(C.fmt_pp),
        "YoY":               sub_sorted["yoy_pct"].apply(C.fmt_pct),
        "Quartile":          sub_sorted["quartile_in_segment"].apply(
                                  lambda v: f"Q{int(v)}" if pd.notna(v) else "—"),
    })
    st.dataframe(table, use_container_width=True, hide_index=True)

    # ── Donut + bar ─────────────────────────────────────────────────────────
    C.section_header("Share visual", f"{sel_month} · {SEGMENT_LABELS.get(sel_seg, sel_seg)}")
    c1, c2 = st.columns([3, 4])
    with c1:
        fig = px.pie(
            sub_sorted, values="total", names="display_name", hole=0.55,
            color="company_key", color_discrete_map=OEM_COLORS,
        )
        fig.update_traces(
            textinfo="percent", textfont_size=11,
            hovertemplate="<b>%{label}</b><br>%{value:,} units (%{percent})<extra></extra>",
        )
        fig.update_layout(**plotly_layout(height=340))
        fig.update_layout(showlegend=True,
                          legend=dict(orientation="v", y=0.5, x=1.0))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        bar_df = sub_sorted.copy()
        bar_df["share_pct"] = bar_df["market_share_pct"] * 100
        fig = px.bar(
            bar_df, y="display_name", x="share_pct", orientation="h",
            color="company_key", color_discrete_map=OEM_COLORS,
            text=bar_df["share_pct"].apply(lambda v: f"{v:.1f}%"),
        )
        fig.update_traces(textposition="outside", textfont_size=10)
        fig.update_layout(**plotly_layout(height=340))
        fig.update_layout(showlegend=False, bargap=0.3)
        fig.update_xaxes(title_text="Share %", ticksuffix="%")
        fig.update_yaxes(title_text="", categoryorder="total ascending")
        st.plotly_chart(fig, use_container_width=True)

    # ── Share migration (last 12M) ─────────────────────────────────────────
    C.section_header("Share migration", "stacked-area share trend, last 12 months")
    cutoff = (pd.to_datetime(sel_month + "-01") - pd.DateOffset(months=11)).strftime("%Y-%m")
    trend = norm[(norm["segment"] == sel_seg) &
                 (norm["filing_month_year"] >= cutoff) &
                 (norm["filing_month_year"] <= sel_month)].copy()
    trend["month_label"] = pd.to_datetime(trend["filing_month_year"] + "-01").dt.strftime("%b %y")
    trend["share_pct"]   = trend["market_share_pct"] * 100

    fig = px.area(
        trend, x="month_label", y="share_pct", color="display_name",
        color_discrete_map={DISPLAY_NAMES.get(k, k): v for k, v in OEM_COLORS.items()},
        labels={"share_pct": "Share %", "month_label": "Month"},
    )
    fig.update_layout(**plotly_layout(height=340))
    fig.update_yaxes(ticksuffix="%")
    fig.update_layout(legend=dict(orientation="h", y=-0.22))
    st.plotly_chart(fig, use_container_width=True)

    # ── HHI trend ──────────────────────────────────────────────────────────
    C.section_header("Concentration trend (HHI)",
                    "<1000 low · 1000-1800 moderate · >1800 concentrated")
    hhi_trend = industry_concentration(
        norm[(norm["segment"] == sel_seg) & (norm["filing_month_year"] >= cutoff)]
    )
    if not hhi_trend.empty:
        hhi_trend["month_label"] = pd.to_datetime(
            hhi_trend["filing_month_year"] + "-01"
        ).dt.strftime("%b %y")

        fig = go.Figure()
        fig.add_hrect(y0=0, y1=1000, fillcolor="#DCFCE7",
                      opacity=0.35, layer="below", line_width=0)
        fig.add_hrect(y0=1000, y1=1800, fillcolor="#FEF3C7",
                      opacity=0.35, layer="below", line_width=0)
        fig.add_hrect(y0=1800, y1=10000, fillcolor="#FEE2E2",
                      opacity=0.35, layer="below", line_width=0)
        fig.add_scatter(
            x=hhi_trend["month_label"], y=hhi_trend["hhi"],
            mode="lines+markers",
            line=dict(color=BRAND["primary"], width=2.4),
            name="HHI",
        )
        fig.update_layout(**plotly_layout(height=300))
        fig.update_yaxes(title_text="HHI")
        st.plotly_chart(fig, use_container_width=True)


def _hhi_band(hhi: float | None) -> str:
    if hhi is None:
        return "—"
    if hhi < 1000:
        return "Low concentration"
    if hhi < 1800:
        return "Moderate concentration"
    return "High concentration"
