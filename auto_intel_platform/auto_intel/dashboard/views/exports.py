"""
views/exports.py — Exports & geographic exposure
==================================================
Indian auto exports are a real driver of OEM margin (esp 2W, PV, CV).
This view focuses on:
  - Industry-wide export volume and export-mix trend
  - Per-OEM export concentration
  - Export YoY vs domestic YoY (decoupling check)
"""

from __future__ import annotations
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from .. import components as C
from ..theme import OEM_COLORS, SEGMENT_COLORS, BRAND, plotly_layout
from ..data_layer import load_all, month_options, DISPLAY_NAMES, SEGMENT_LABELS


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
        format_func=lambda s: SEGMENT_LABELS.get(s, s), key="exp_seg",
    )
    sel_month = c2.selectbox(
        "Month", months,
        format_func=lambda m: pd.to_datetime(m + "-01").strftime("%b %Y"),
        key="exp_month",
    )

    sub = norm[(norm["segment"] == sel_seg) &
               (norm["filing_month_year"] == sel_month)].copy()
    if sub.empty:
        C.empty_state("No data", "Selected segment/month is empty.")
        return

    # ── Headline KPIs
    total_exp = sub["exports"].sum()
    total_vol = sub["total"].sum()
    mix       = total_exp / total_vol if total_vol > 0 else None

    # YoY for exports
    yoy_month = (pd.to_datetime(sel_month + "-01") - pd.DateOffset(years=1)).strftime("%Y-%m")
    yoy_df = norm[(norm["segment"] == sel_seg) & (norm["filing_month_year"] == yoy_month)]
    yoy_exp = yoy_df["exports"].sum() if not yoy_df.empty else None
    exp_yoy_pct = (total_exp - yoy_exp) / yoy_exp if yoy_exp and yoy_exp > 0 else None

    C.kpi_row([
        {"label": "Industry exports",
         "value": C.fmt_units(total_exp), "unit": "units",
         "delta": C.fmt_pct(exp_yoy_pct),
         "delta_dir": C.delta_dir(exp_yoy_pct),
         "foot":  "YoY"},
        {"label": "Export mix",
         "value": f"{mix*100:.1f}%" if mix else "—",
         "foot":  f"of {C.fmt_units(total_vol)} units shipped"},
        {"label": "OEMs exporting",
         "value": str(int((sub["exports"] > 0).sum())),
         "foot":  f"of {sub['company_key'].nunique()} OEMs in segment"},
    ])

    # ── Per-OEM table ───────────────────────────────────────────────────────
    C.section_header("Export by OEM", "current-month export volume & mix")
    show = sub.copy().sort_values("exports", ascending=False)
    show["export_mix"] = show["exports"] / show["total"]
    table = pd.DataFrame({
        "OEM":       show["display_name"],
        "Exports":   show["exports"].apply(C.fmt_units),
        "Total":     show["total"].apply(C.fmt_units),
        "Mix":       show["export_mix"].apply(
                          lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
        "Share of segment exports": (
            (show["exports"] / total_exp * 100).round(1).astype(str) + "%"
            if total_exp > 0 else "—"
        ),
    })
    st.dataframe(table, use_container_width=True, hide_index=True)

    # ── Industry export-mix trend ───────────────────────────────────────────
    C.section_header("Industry export-mix trend",
                    f"{SEGMENT_LABELS.get(sel_seg, sel_seg)}, last 18 months")
    cutoff = (pd.to_datetime(sel_month + "-01") - pd.DateOffset(months=17)).strftime("%Y-%m")
    trend = norm[(norm["segment"] == sel_seg) &
                 (norm["filing_month_year"] >= cutoff) &
                 (norm["filing_month_year"] <= sel_month)]
    agg = trend.groupby("filing_month_year", as_index=False).agg(
        domestic=("domestic", "sum"),
        exports=("exports", "sum"),
        total=("total", "sum"),
    )
    agg["mix"] = agg["exports"] / agg["total"].replace(0, pd.NA)
    agg["month_label"] = pd.to_datetime(agg["filing_month_year"] + "-01").dt.strftime("%b %y")

    fig = go.Figure()
    fig.add_bar(x=agg["month_label"], y=agg["domestic"],
                name="Domestic", marker_color=BRAND["accent"])
    fig.add_bar(x=agg["month_label"], y=agg["exports"],
                name="Exports", marker_color="#F59E0B")
    fig.add_scatter(x=agg["month_label"], y=agg["mix"],
                    name="Export mix %", yaxis="y2",
                    line=dict(color=BRAND["primary"], width=2.4),
                    mode="lines+markers")
    fig.update_layout(
        barmode="stack",
        yaxis2=dict(overlaying="y", side="right", tickformat=".0%",
                    title_text="Export mix"),
        **plotly_layout(height=380),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Domestic vs export YoY scatter ─────────────────────────────────────
    C.section_header("Domestic vs export YoY",
                    "decoupling check — quadrants flag mismatched dynamics")
    scatter = sub.copy()
    # Compute per-OEM export YoY for the chart
    yoy_per_oem = (
        norm[(norm["segment"] == sel_seg) & (norm["filing_month_year"] == yoy_month)]
            [["company_key", "domestic", "exports"]]
            .rename(columns={"domestic": "dom_yoy_base", "exports": "exp_yoy_base"})
    )
    scatter = scatter.merge(yoy_per_oem, on="company_key", how="left")
    scatter["dom_yoy_pct"] = (
        (scatter["domestic"] - scatter["dom_yoy_base"]) /
        scatter["dom_yoy_base"].replace(0, pd.NA)
    )
    scatter["exp_yoy_pct"] = (
        (scatter["exports"] - scatter["exp_yoy_base"]) /
        scatter["exp_yoy_base"].replace(0, pd.NA)
    )
    scatter = scatter.dropna(subset=["dom_yoy_pct", "exp_yoy_pct"])
    if not scatter.empty:
        fig = px.scatter(
            scatter, x="dom_yoy_pct", y="exp_yoy_pct",
            size="total", color="display_name", text="display_name",
            color_discrete_map={DISPLAY_NAMES.get(k, k): v for k, v in OEM_COLORS.items()},
        )
        fig.update_traces(textposition="top center", textfont_size=10)
        fig.add_hline(y=0, line_color=BRAND["border"], line_dash="dot")
        fig.add_vline(x=0, line_color=BRAND["border"], line_dash="dot")
        fig.update_layout(**plotly_layout(height=380))
        fig.update_layout(showlegend=False)
        fig.update_xaxes(tickformat=".0%", title_text="Domestic YoY")
        fig.update_yaxes(tickformat=".0%", title_text="Export YoY")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Insufficient YoY history for scatter.")
