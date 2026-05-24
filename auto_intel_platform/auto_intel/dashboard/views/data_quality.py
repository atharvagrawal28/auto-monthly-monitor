"""
views/data_quality.py — Data Quality scorecard
===============================================
Without trustworthy data, nothing else matters. This page exposes the
quality posture of every OEM:
  - Per-OEM scorecard (clean %, mean confidence, mean quality, # needs-review)
  - Anomaly feed (z-score / industry-divergence flagged rows)
  - Recent reconciliation issues (CONFLICT rows)
  - Source coverage (OEM IR pages / FADA / Manual)
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

        # ── Per-OEM scorecard table ───────────────────────────────────────────
        C.section_header(
            "Per-OEM data quality scorecard",
            "trailing 12 months · green = conf ≥ 85% · yellow = 70–85% · red < 70%",
        )
        score_show = score_df.copy()
        score_show["display_name"]    = score_show["oem"].map(DISPLAY_NAMES).fillna(score_show["oem"])
        score_show["Clean rows"]      = score_show.apply(
            lambda r: int(round(r["clean_pct"] * r["rows"])), axis=1
        )
        score_show["Flagged rows"]    = score_show["flagged"].fillna(0).astype(int)
        score_show["Needs Review"]    = score_show["needs_review"].fillna(0).astype(int)
        score_show["Avg Confidence"]  = (score_show["mean_confidence"] * 100).round(1).astype(str) + "%"
        score_show["Quality /100"]    = score_show["mean_quality"].astype(int)

        # Colour coding for Avg Confidence
        def _conf_color(conf_float: float) -> str:
            if conf_float >= 0.85:  return "🟢"
            if conf_float >= 0.70:  return "🟡"
            return "🔴"

        score_show["Status"] = score_show["mean_confidence"].apply(_conf_color)

        # Parser version: take mode across the OEM's rows
        pv_map = (
            norm.groupby("company_key")["parser_version"]
            .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else "—")
        )
        score_show["Parser"] = score_show["oem"].map(pv_map).fillna("—")

        show_cols = score_show[[
            "Status", "display_name", "rows", "months_covered",
            "Clean rows", "Flagged rows", "Needs Review",
            "Avg Confidence", "Quality /100", "latest_month", "Parser",
        ]].copy()
        show_cols.columns = [
            "●", "OEM", "Total rows", "Months",
            "Clean", "Flagged", "Needs Review",
            "Avg Confidence", "Quality /100", "Last filed", "Parser",
        ]
        st.dataframe(show_cols, use_container_width=True, hide_index=True)

        # ── Coverage gaps ─────────────────────────────────────────────────────
        C.section_header(
            "Coverage gaps",
            "OEM × month combinations missing from the dataset",
        )
        all_months = sorted(norm["filing_month_year"].dropna().unique())
        all_oems   = sorted(norm["company_key"].dropna().unique())
        present = set(zip(norm["company_key"], norm["filing_month_year"]))

        gap_rows = []
        for oem in all_oems:
            for mo in all_months:
                if (oem, mo) not in present:
                    gap_rows.append({
                        "OEM":   DISPLAY_NAMES.get(oem, oem),
                        "Month": mo,
                        "Gap":   "MISSING",
                    })

        if not gap_rows:
            st.success("No coverage gaps — all OEMs present in all months.")
        else:
            gap_df = pd.DataFrame(gap_rows)
            st.warning(
                f"{len(gap_df)} missing OEM × month combinations across "
                f"{gap_df['OEM'].nunique()} OEMs and {gap_df['Month'].nunique()} months."
            )
            # Pivot to matrix view
            gap_pivot = gap_df.pivot_table(
                index="OEM", columns="Month", values="Gap", aggfunc="first"
            ).fillna("✅")
            gap_pivot = gap_pivot.replace("MISSING", "❌")
            st.dataframe(gap_pivot, use_container_width=True)

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
    # Map internal source keys to readable labels
    _SOURCE_LABELS = {
        "OEM_IR":  "OEM IR Pages",
        "FADA":    "FADA Retail",
        "MANUAL":  "Manual Entry",
        "NSE":     "OEM IR Pages",   # legacy rows — treat as OEM_IR
        "BSE":     "OEM IR Pages",   # legacy rows — treat as OEM_IR
    }
    source_mix["source"] = source_mix["source"].map(
        lambda s: _SOURCE_LABELS.get(s, s)
    )
    source_mix = source_mix.groupby("source")["rows"].sum().reset_index()
    if not source_mix.empty:
        fig = px.pie(source_mix, values="rows", names="source", hole=0.55,
                     color_discrete_sequence=[BRAND["accent"], "#F59E0B", "#15803D"])
        fig.update_traces(textinfo="label+percent")
        fig.update_layout(**plotly_layout(height=260))
        st.plotly_chart(fig, use_container_width=True)
