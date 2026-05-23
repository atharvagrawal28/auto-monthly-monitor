"""
views/deep_dive.py — Single-OEM analyst profile
=================================================
Picks one OEM × segment, shows everything:
  - Latest print KPIs (with YoY, MoM, vs T6M, market share, share delta)
  - Long-form volume trend (24M) split into domestic vs exports
  - YoY trend line with ±1σ band
  - FYTD vs prior FYTD performance
  - TTM trend
  - Quarterly aggregation (fiscal-quarter)
  - Sub-segment / model-level breakdown (from granular)
  - Filing freshness & lineage
"""

from __future__ import annotations
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from .. import components as C
from ..theme import BRAND, OEM_COLORS, SEGMENT_COLORS, plotly_layout
from ..data_layer import load_all, DISPLAY_NAMES, SEGMENT_LABELS
from analytics.rolling import add_qoq, compute_cagr, fiscal_year


def render():
    norm, gran, _, _ = load_all()
    if norm.empty:
        C.empty_state("No data", "Generate sample data first.")
        return

    available_oems = sorted(norm["company_key"].dropna().unique().tolist())
    oem_label_to_key = {DISPLAY_NAMES.get(k, k): k for k in available_oems}

    c1, c2 = st.columns([2, 2])
    sel_oem_label = c1.selectbox("OEM", list(oem_label_to_key.keys()), key="dd_oem")
    sel_oem = oem_label_to_key[sel_oem_label]

    oem_df = norm[norm["company_key"] == sel_oem].copy()
    available_segs = sorted(oem_df["segment"].dropna().unique().tolist())
    sel_seg = c2.selectbox(
        "Segment", available_segs,
        format_func=lambda s: SEGMENT_LABELS.get(s, s),
        key="dd_seg",
    )

    df = oem_df[oem_df["segment"] == sel_seg].sort_values("filing_month_year")
    if df.empty:
        C.empty_state("No data", f"No rows for {sel_oem_label} / {sel_seg}.")
        return

    latest = df.iloc[-1]

    # ── Latest print KPIs ───────────────────────────────────────────────────
    C.section_header(
        f"Latest print — {pd.to_datetime(latest['filing_month_year'] + '-01').strftime('%b %Y')}",
        f"{sel_oem_label} · {SEGMENT_LABELS.get(sel_seg, sel_seg)}",
    )

    export_mix = latest["exports"] / latest["total"] if latest["total"] > 0 else None

    C.kpi_row([
        {
            "label": "Wholesale",
            "value": C.fmt_units(latest["total"]),
            "unit":  "units",
            "delta": C.fmt_pct(latest.get("yoy_pct")),
            "delta_dir": C.delta_dir(latest.get("yoy_pct")),
            "foot":  "YoY",
        },
        {
            "label": "MoM",
            "value": C.fmt_pct(latest.get("mom_pct")),
            "delta_dir": C.delta_dir(latest.get("mom_pct")),
            "foot":  "vs prior month",
        },
        {
            "label": "Market share",
            "value": f"{latest['market_share_pct']*100:.2f}%"
                     if pd.notna(latest.get("market_share_pct")) else "—",
            "delta": C.fmt_pp(latest.get("market_share_delta_yoy_pp")),
            "delta_dir": C.delta_dir(latest.get("market_share_delta_yoy_pp")),
            "foot":  "share Δ YoY",
        },
        {
            "label": "Export mix",
            "value": f"{export_mix*100:.1f}%" if export_mix else "—",
            "foot":  f"{C.fmt_units(latest['exports'])} units exported",
        },
        {
            "label": "Beat/miss vs 6M",
            "value": C.fmt_pct(latest.get("beat_miss_pct")),
            "delta_dir": C.delta_dir(latest.get("beat_miss_pct")),
            "foot":  "vs trailing 6M average",
        },
    ])

    C.kpi_row([
        {
            "label": "TTM total",
            "value": C.fmt_lakh(latest.get("ttm_total")),
            "unit":  "units",
            "delta": C.fmt_pct(latest.get("ttm_yoy_pct")),
            "delta_dir": C.delta_dir(latest.get("ttm_yoy_pct")),
            "foot":  "trailing 12 months",
        },
        {
            "label": "FYTD",
            "value": C.fmt_lakh(latest.get("fytd_total")),
            "unit":  "units",
            "delta": C.fmt_pct(latest.get("fytd_yoy_pct")),
            "delta_dir": C.delta_dir(latest.get("fytd_yoy_pct")),
            "foot":  f"{latest.get('fiscal_year', '')} to date",
        },
        {
            "label": "3-month run-rate",
            "value": C.fmt_units(latest.get("total_r3m")),
            "unit":  "units / mo",
            "foot":  "trailing 3M average",
        },
        {
            "label": "Volatility (T12M)",
            "value": _coef_var(df.tail(12)["total"]),
            "foot":  "coefficient of variation",
        },
        {
            "label": "Data quality",
            "value": f"{int(latest.get('quality_score', 0))}/100",
            "foot":  f"Parser {latest['parser_status']} · conf "
                     f"{float(latest.get('confidence_score') or 0)*100:.0f}%",
        },
    ])

    # ── Long-form volume trend ──────────────────────────────────────────────
    C.section_header("Volume trend (24 months)", "domestic vs exports")
    last_24 = df.tail(24).copy()
    last_24["month_label"] = pd.to_datetime(last_24["filing_month_year"] + "-01").dt.strftime("%b %y")

    fig = go.Figure()
    fig.add_bar(
        x=last_24["month_label"], y=last_24["domestic"],
        name="Domestic", marker_color=BRAND["accent"],
    )
    fig.add_bar(
        x=last_24["month_label"], y=last_24["exports"],
        name="Exports", marker_color="#F59E0B",
    )
    fig.add_scatter(
        x=last_24["month_label"], y=last_24["total_r3m"],
        name="3M avg (total)", line=dict(color=BRAND["primary"], width=2.2, dash="dot"),
        mode="lines",
    )
    fig.update_layout(barmode="stack", **plotly_layout(height=360))
    st.plotly_chart(fig, use_container_width=True)

    # ── YoY trend with bands ────────────────────────────────────────────────
    C.section_header("YoY growth trend", "the OEM's growth tape")
    yoy_df = df.dropna(subset=["yoy_pct"]).tail(24).copy()
    yoy_df["month_label"] = pd.to_datetime(yoy_df["filing_month_year"] + "-01").dt.strftime("%b %y")

    if not yoy_df.empty:
        fig = go.Figure()
        fig.add_scatter(
            x=yoy_df["month_label"], y=yoy_df["yoy_pct"],
            mode="lines+markers", name="YoY",
            line=dict(color=OEM_COLORS.get(sel_oem, BRAND["accent"]), width=2.4),
        )
        fig.add_hline(y=0, line_color=BRAND["border"], line_dash="dot")
        fig.update_layout(**plotly_layout(height=300))
        fig.update_yaxes(tickformat=".0%", title_text="YoY")
        st.plotly_chart(fig, use_container_width=True)

    # ── Fiscal-quarter view ─────────────────────────────────────────────────
    C.section_header("Fiscal quarter aggregation", "QoQ & YoY at fiscal-quarter cadence")
    qoq_df = add_qoq(df)
    if not qoq_df.empty:
        show = qoq_df.tail(8).copy()
        show["total"]    = show["total"].apply(C.fmt_units)
        show["domestic"] = show["domestic"].apply(C.fmt_units)
        show["exports"]  = show["exports"].apply(C.fmt_units)
        show["qoq_pct"]  = show["qoq_pct"].apply(C.fmt_pct)
        show["yoy_pct"]  = show["yoy_pct"].apply(C.fmt_pct)
        show.columns = [c.upper().replace("_", " ") for c in show.columns]
        st.dataframe(show, use_container_width=True, hide_index=True)

    # ── CAGR card ──────────────────────────────────────────────────────────
    C.section_header("Long-horizon growth", "CAGR over selected lookback")
    cagr_cols = st.columns(3)
    for i, yrs in enumerate([1, 2, 3]):
        months_back = yrs * 12
        if len(df) > months_back:
            start = df.iloc[-1 - months_back]["total"]
            end   = df.iloc[-1]["total"]
            cagr  = compute_cagr(start, end, yrs)
            with cagr_cols[i]:
                C.kpi(
                    label=f"{yrs}-year CAGR",
                    value=f"{cagr*100:+.1f}%" if cagr is not None else "—",
                    foot=f"from {df.iloc[-1 - months_back]['filing_month_year']} "
                         f"to {df.iloc[-1]['filing_month_year']}",
                    delta_dir=C.delta_dir(cagr),
                )

    # ── Sub-segment breakdown ──────────────────────────────────────────────
    if not gran.empty:
        gsub = gran[
            (gran["company_key"] == sel_oem) &
            (gran["segment"] == sel_seg) &
            (gran["filing_month_year"] == latest["filing_month_year"])
        ].copy()
        if not gsub.empty:
            C.section_header(
                "Sub-segment breakdown",
                f"granular contributors, {pd.to_datetime(latest['filing_month_year'] + '-01').strftime('%b %Y')}",
            )
            gsub["units"] = pd.to_numeric(gsub["units"], errors="coerce")
            gsub = gsub.dropna(subset=["units"]).sort_values("units", ascending=False)
            total_g = gsub["units"].sum()
            gsub["share"] = gsub["units"] / total_g if total_g > 0 else 0

            c1, c2 = st.columns([2, 3])
            with c1:
                fig = px.pie(
                    gsub, values="units", names="normalized_category",
                    hole=0.55, color_discrete_sequence=px.colors.qualitative.Set2,
                )
                fig.update_traces(textinfo="label+percent", textfont_size=11)
                fig.update_layout(**plotly_layout(height=320))
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                show = gsub[["raw_category", "normalized_category", "units", "share"]].copy()
                show["units"] = show["units"].apply(C.fmt_units)
                show["share"] = show["share"].apply(lambda v: f"{v*100:.1f}%")
                show.columns = ["Reported line", "Normalized", "Units", "Share"]
                st.dataframe(show, use_container_width=True, hide_index=True)

    # ── Lineage ────────────────────────────────────────────────────────────
    C.section_header("Filing lineage", "audit trail for the latest print")
    st.markdown(
        f'<div style="background:white;border:1px solid #E2E8F0;border-radius:8px;'
        f'padding:0.85rem 1rem;font-size:0.85rem;color:#475569;">'
        f'<b>Source:</b> {latest["source"]} · '
        f'<b>Filed:</b> {latest["filing_date"]} · '
        f'<b>Parser:</b> {latest["parser_version"]} · '
        f'<b>Extraction:</b> {latest["extraction_method"]} · '
        f'<b>Confidence:</b> {float(latest.get("confidence_score") or 0)*100:.0f}% · '
        f'<b>Status:</b> {C.status_pill(latest["parser_status"])}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Export
    csv = df.to_csv(index=False).encode()
    st.download_button(
        f"Download {sel_oem_label} / {sel_seg} history (CSV)", csv,
        f"{sel_oem}_{sel_seg}.csv", "text/csv",
    )


def _coef_var(series: pd.Series) -> str:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty or s.mean() == 0:
        return "—"
    cv = float(s.std() / s.mean())
    return f"{cv*100:.1f}%"
