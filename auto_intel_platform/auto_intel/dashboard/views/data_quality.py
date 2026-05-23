"""
views/data_quality.py — Data Quality scorecard
===============================================
Without trustworthy data, nothing else matters. This page exposes the
quality posture of every OEM:
  - Per-OEM scorecard (clean %, mean confidence, mean quality, # needs-review)
  - Anomaly feed (z-score / industry-divergence flagged rows)
  - Recent reconciliation issues (CONFLICT rows)
  - Cross-source coverage (NSE vs BSE)
"""

from __future__ import annotations
import pandas as pd
import plotly.express as px
import streamlit as st

from .. import components as C
from ..theme import BRAND, plotly_layout
from ..data_layer import load_all, DISPLAY_NAMES, SEGMENT_LABELS
from analytics.quality import oem_quality_card
from analytics.anomaly import flag_anomalies, industry_vs_oem_divergence


def render():
    norm, _, _, rq = load_all()
    if norm.empty:
        C.empty_state("No data", "Generate sample data first.")
        return

    # ── Headline
    cards = [
        oem_quality_card(norm, oem) for oem in sorted(norm["company_key"].unique())
    ]
    cards = [c for c in cards if c.get("rows")]
    if cards:
        score_df = pd.DataFrame(cards)
        avg_quality = score_df["mean_quality"].mean()
        avg_clean   = score_df["clean_pct"].mean()
        avg_conf    = score_df["mean_confidence"].mean()
        review_cnt  = int(score_df["needs_review"].sum())

        C.kpi_row([
            {"label": "Mean quality score",
             "value": f"{avg_quality:.0f}/100",
             "foot":  "trailing 12M, across OEMs"},
            {"label": "Mean clean %",
             "value": f"{avg_clean*100:.1f}%",
             "foot":  "rows passing all validations"},
            {"label": "Mean parser confidence",
             "value": f"{avg_conf*100:.1f}%",
             "foot":  "extraction quality"},
            {"label": "Open review queue",
             "value": str(len(rq) if rq is not None and not rq.empty else 0),
             "foot":  f"{review_cnt} review events in T12M"},
        ])

        # ── Per-OEM scorecard ─────────────────────────────────────────────────
        C.section_header("Per-OEM scorecard", "trailing 12 months")
        score_show = score_df.copy()
        score_show["display_name"] = score_show["oem"].map(DISPLAY_NAMES).fillna(score_show["oem"])
        score_show["clean_pct"] = (score_show["clean_pct"] * 100).round(1).astype(str) + "%"
        score_show["mean_confidence"] = (score_show["mean_confidence"] * 100).round(1).astype(str) + "%"
        show = score_show[[
            "display_name", "rows", "months_covered", "clean_pct",
            "mean_confidence", "mean_quality", "needs_review",
            "flagged", "manual", "latest_month",
        ]]
        show.columns = ["OEM", "Rows", "Months", "Clean %",
                        "Confidence", "Quality /100", "Needs Review",
                        "Flagged", "Manual", "Latest month"]
        st.dataframe(show, use_container_width=True, hide_index=True)

        # Quality chart
        chart = score_df.copy()
        chart["display_name"] = chart["oem"].map(DISPLAY_NAMES).fillna(chart["oem"])
        fig = px.bar(
            chart.sort_values("mean_quality"),
            x="mean_quality", y="display_name", orientation="h",
            color="mean_quality",
            color_continuous_scale=["#B91C1C", "#FEF3C7", "#15803D"],
            range_color=[40, 100],
            text=chart.sort_values("mean_quality")["mean_quality"].apply(lambda v: f"{int(v)}"),
        )
        fig.update_traces(textposition="outside", textfont_size=10)
        fig.update_layout(**plotly_layout(height=max(280, 26 * len(chart))))
        fig.update_layout(coloraxis_showscale=False, bargap=0.35)
        fig.update_xaxes(title_text="Quality score (0-100)")
        fig.update_yaxes(title_text="")
        st.plotly_chart(fig, use_container_width=True)

    # ── Anomaly feed ────────────────────────────────────────────────────────
    C.section_header(
        "Anomaly feed",
        "rows with |z-score| ≥ 2.5σ vs OEM's trailing 12M",
    )
    anoms = flag_anomalies(norm, threshold=2.5)
    if anoms.empty:
        st.success("No anomalies in current dataset.")
    else:
        anoms = anoms.sort_values("z_score_t12m", key=lambda s: s.abs(), ascending=False)
        show = anoms[["display_name", "segment_label", "filing_month_year",
                      "total", "yoy_pct", "z_score_t12m", "parser_status"]].head(20).copy()
        show["total"] = show["total"].apply(C.fmt_units)
        show["yoy_pct"] = show["yoy_pct"].apply(C.fmt_pct)
        show["z_score_t12m"] = show["z_score_t12m"].apply(lambda v: f"{v:+.2f}σ")
        show.columns = ["OEM", "Segment", "Month", "Volume", "YoY", "Z-score", "Parser"]
        st.dataframe(show, use_container_width=True, hide_index=True)

    # ── Industry divergence ────────────────────────────────────────────────
    C.section_header(
        "OEMs swimming against the industry",
        "YoY deviates from segment median by >20pp",
    )
    diverg = industry_vs_oem_divergence(norm, spread_threshold_pp=20.0)
    if diverg.empty:
        st.success("No significant divergence in current dataset.")
    else:
        diverg = diverg.sort_values("divergence_pp", key=lambda s: s.abs(), ascending=False)
        show = diverg[["display_name", "segment_label", "filing_month_year",
                       "total", "yoy_pct", "divergence_pp"]].head(20).copy()
        show["total"] = show["total"].apply(C.fmt_units)
        show["yoy_pct"] = show["yoy_pct"].apply(C.fmt_pct)
        show["divergence_pp"] = show["divergence_pp"].apply(lambda v: f"{v:+.1f}pp")
        show.columns = ["OEM", "Segment", "Month", "Volume", "YoY", "vs Industry"]
        st.dataframe(show, use_container_width=True, hide_index=True)

    # ── Source coverage ────────────────────────────────────────────────────
    C.section_header("Source coverage", "where the data came from")
    source_mix = norm.groupby("source")["company_key"].count().reset_index(name="rows")
    if not source_mix.empty:
        fig = px.pie(source_mix, values="rows", names="source", hole=0.55,
                     color_discrete_sequence=[BRAND["accent"], "#F59E0B", "#15803D"])
        fig.update_traces(textinfo="label+percent")
        fig.update_layout(**plotly_layout(height=260))
        st.plotly_chart(fig, use_container_width=True)
