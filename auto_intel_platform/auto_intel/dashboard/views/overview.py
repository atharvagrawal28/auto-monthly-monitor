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

    # ── ABSOLUTE FIRST: Industry Quick Summary ────────────────────────────────
    _render_industry_quick_summary(norm, cur, prev, yoy_month)

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
        # Split by sign first — nlargest/nsmallest on all-negative data
        # would put negatives in the "positive" column, which is wrong.
        pos_df = bridge_df[bridge_df["contribution_pp"] > 0]
        neg_df = bridge_df[bridge_df["contribution_pp"] < 0]
        top_pos = pos_df.nlargest(5,  "contribution_pp") if not pos_df.empty else pd.DataFrame()
        top_neg = neg_df.nsmallest(5, "contribution_pp") if not neg_df.empty else pd.DataFrame()

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(
                f'**Adding to industry growth** '
                f'{C.chip("positive contribution", "green")}',
                unsafe_allow_html=True,
            )
            if top_pos.empty:
                C.empty_state("No positive contributors", "All OEMs declined vs prior period.")
            else:
                _render_mover_table(top_pos)
        with c2:
            st.markdown(
                f'**Dragging on industry growth** '
                f'{C.chip("negative contribution", "red")}',
                unsafe_allow_html=True,
            )
            if top_neg.empty:
                C.empty_state("No negative contributors", "All OEMs grew vs prior period.")
            else:
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

def _render_industry_quick_summary(
    norm: pd.DataFrame,
    cur_month: str,
    prev_month: str | None,
    yoy_month: str | None,
) -> None:
    """Industry Quick Summary — the at-a-glance table shown first on every load."""
    cur_df  = norm[norm["filing_month_year"] == cur_month]
    prev_df = norm[norm["filing_month_year"] == prev_month] if prev_month else pd.DataFrame()
    yoy_df  = norm[norm["filing_month_year"] == yoy_month]  if yoy_month  else pd.DataFrame()

    SEG_ORDER = ["PV", "2W", "CV", "3W", "Tractor", "EV"]

    rows = []
    for seg in SEG_ORDER:
        cur_seg  = cur_df[cur_df["segment"] == seg]
        prev_seg = prev_df[prev_df["segment"] == seg] if not prev_df.empty else pd.DataFrame()
        yoy_seg  = yoy_df[yoy_df["segment"] == seg]  if not yoy_df.empty  else pd.DataFrame()

        total    = cur_seg["total"].sum()
        if total == 0:
            continue

        prev_tot = prev_seg["total"].sum() if not prev_seg.empty else None
        yoy_tot  = yoy_seg["total"].sum()  if not yoy_seg.empty  else None
        mom_pct  = (total - prev_tot) / prev_tot if prev_tot else None
        yoy_pct  = (total - yoy_tot)  / yoy_tot  if yoy_tot  else None

        # Coverage: OEMs with non-null total in this segment
        oems_filed = int(cur_seg["company_key"].nunique())
        # Expected OEMs per segment (static reference from registry)
        _SEG_EXPECTED = {"PV": 3, "2W": 4, "CV": 3, "3W": 2, "Tractor": 2, "EV": 2}
        oems_exp = _SEG_EXPECTED.get(seg, oems_filed)

        rows.append({
            "Segment":   SEGMENT_LABELS.get(seg, seg),
            "Units":     C.fmt_units(total),
            "YoY":       C.fmt_pct(yoy_pct)  if yoy_pct  is not None else "—",
            "MoM":       C.fmt_pct(mom_pct)  if mom_pct  is not None else "—",
            "Coverage":  f"{oems_filed}/{oems_exp} OEMs",
            "_yoy":      yoy_pct,
            "_mom":      mom_pct,
        })

    if not rows:
        return

    month_label = pd.to_datetime(cur_month + "-01").strftime("%B %Y") if cur_month else "—"

    # Build table rows HTML first — all in one string so the dark wrapper actually wraps it.
    # Split st.markdown() calls means each renders independently; outer div won't contain inner table.
    table_rows_html = ""
    for r in rows:
        yoy_color = "#15803D" if (r["_yoy"] or 0) >= 0 else "#B91C1C"
        mom_color = "#15803D" if (r["_mom"] or 0) >= 0 else "#B91C1C"
        table_rows_html += (
            f"<tr>"
            f"<td style='padding:6px 12px;color:#1E293B;font-size:0.83rem;'>{r['Segment']}</td>"
            f"<td style='padding:6px 12px;color:#0F172A;font-weight:700;font-size:0.83rem;"
            f"font-family:monospace;'>{r['Units']}</td>"
            f"<td style='padding:6px 12px;color:{yoy_color};font-weight:700;font-size:0.83rem;"
            f"font-family:monospace;'>{r['YoY']}</td>"
            f"<td style='padding:6px 12px;color:{mom_color};font-weight:700;font-size:0.83rem;"
            f"font-family:monospace;'>{r['MoM']}</td>"
            f"<td style='padding:6px 12px;color:#475569;font-size:0.79rem;'>{r['Coverage']}</td>"
            f"</tr>"
        )

    th = ("padding:5px 12px;color:#64748B;font-size:0.72rem;font-weight:700;"
          "text-align:left;text-transform:uppercase;letter-spacing:0.07em;border-bottom:2px solid #E2E8F0;")

    html = (
        f"<div style='border:1px solid #E2E8F0;border-radius:8px;overflow:hidden;margin-bottom:1rem;'>"
        f"<div style='background:#F8FAFC;padding:8px 12px 6px;border-bottom:1px solid #E2E8F0;'>"
        f"<span style='font-size:0.72rem;color:#64748B;font-weight:700;letter-spacing:0.08em;"
        f"text-transform:uppercase;'>India Auto Sales — {month_label}</span>"
        f"</div>"
        f"<table style='width:100%;border-collapse:collapse;background:white;'>"
        f"<thead><tr>"
        f"<th style='{th}'>Segment</th>"
        f"<th style='{th}'>Units</th>"
        f"<th style='{th}'>YoY</th>"
        f"<th style='{th}'>MoM</th>"
        f"<th style='{th}'>Coverage</th>"
        f"</tr></thead>"
        f"<tbody>{table_rows_html}</tbody>"
        f"</table></div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _render_mover_table(df: pd.DataFrame):
    show = df[["display_name", "segment_label", "delta", "contribution_pp"]].copy()
    show.columns = ["OEM", "Segment", "Δ units", "Industry contribution (pp)"]
    show["Δ units"] = show["Δ units"].apply(lambda v: C.fmt_indian(int(v), sign=True))
    show["Industry contribution (pp)"] = show["Industry contribution (pp)"].apply(
        lambda v: f"{v:+.2f}"
    )
    st.dataframe(show, use_container_width=True, hide_index=True)
