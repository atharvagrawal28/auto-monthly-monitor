"""
views/monitoring.py — What changed this month
===============================================
Detailed OEM-level grid for the selected month with YoY, MoM, market share,
share-delta in pp, quartile rank, z-score anomaly, beat/miss vs trailing 6M,
and an automated alert feed for surges / crashes / parser issues.
"""

from __future__ import annotations
import pandas as pd
import plotly.express as px
import streamlit as st

from .. import components as C
from ..theme import SEGMENT_COLORS, OEM_COLORS, plotly_layout
from ..data_layer import load_all, month_options, DISPLAY_NAMES, SEGMENT_LABELS

ANOMALY_Z = 2.5


def render():
    norm, _, _, _ = load_all()
    if norm.empty:
        C.empty_state("No data", "Generate sample data first.")
        return

    months = month_options(norm)
    f1, f2, f3 = st.columns([1, 1, 2])
    sel_month = f1.selectbox(
        "Month", months,
        format_func=lambda m: pd.to_datetime(m + "-01").strftime("%b %Y"),
        key="mon_month",
    )
    seg_choices = ["All"] + sorted(norm["segment"].dropna().unique().tolist())
    sel_seg = f2.selectbox(
        "Segment", seg_choices,
        format_func=lambda s: "All segments" if s == "All" else SEGMENT_LABELS.get(s, s),
        key="mon_seg",
    )

    cur = norm[norm["filing_month_year"] == sel_month].copy()
    if sel_seg != "All":
        cur = cur[cur["segment"] == sel_seg]

    if cur.empty:
        C.empty_state("No rows", "Selected month/segment has no data yet.")
        return

    # ── Quick KPI strip
    total      = cur["total"].sum()
    domestic   = cur["domestic"].sum()
    exports    = cur["exports"].sum()
    yoy_median = cur["yoy_pct"].median()
    mom_median = cur["mom_pct"].median()

    C.kpi_row([
        {"label": "Volume",   "value": C.fmt_units(total),     "unit": "units"},
        {"label": "Domestic", "value": C.fmt_units(domestic),  "unit": "units"},
        {"label": "Exports",  "value": C.fmt_units(exports),   "unit": "units"},
        {"label": "Median YoY",
         "value": C.fmt_pct(yoy_median),
         "delta": "across OEMs", "delta_dir": C.delta_dir(yoy_median)},
        {"label": "Median MoM",
         "value": C.fmt_pct(mom_median),
         "delta": "across OEMs", "delta_dir": C.delta_dir(mom_median)},
    ])

    # ── OEM detail grid ─────────────────────────────────────────────────────
    C.section_header(
        "OEM-level grid",
        "all metrics for the selected month, ranked by total volume",
    )

    grid = cur.copy().sort_values("total", ascending=False)
    grid_show = pd.DataFrame({
        "OEM":               grid["display_name"],
        "Segment":           grid["segment"].map(SEGMENT_LABELS).fillna(grid["segment"]),
        "Total":             grid["total"].apply(C.fmt_units),
        "Domestic":          grid["domestic"].apply(C.fmt_units),
        "Exports":           grid["exports"].apply(C.fmt_units),
        "Export mix":        grid["export_mix_pct"].apply(
                                  lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
        "YoY":               grid["yoy_pct"].apply(C.fmt_pct),
        "MoM":               grid["mom_pct"].apply(C.fmt_pct),
        "Market share":      grid["market_share_pct"].apply(
                                  lambda v: f"{v*100:.2f}%" if pd.notna(v) else "—"),
        "Share Δ MoM (pp)":  grid["market_share_delta_mom_pp"].apply(C.fmt_pp),
        "Share Δ YoY (pp)":  grid["market_share_delta_yoy_pp"].apply(C.fmt_pp),
        "Beat/Miss vs 6M":   grid["beat_miss_pct"].apply(C.fmt_pct),
        "Quartile":          grid["quartile_in_segment"].apply(
                                  lambda v: f"Q{int(v)}" if pd.notna(v) else "—"),
        "z-score (T12M)":    grid["z_score_t12m"].apply(
                                  lambda v: f"{v:+.2f}" if pd.notna(v) else "—"),
        "Parser":            grid["parser_status"],
        "Quality":           grid["quality_score"].apply(lambda v: f"{int(v)}/100"),
        "Source":            grid["source"],
        "Filed":             grid["filing_date"],
    })
    st.dataframe(grid_show, use_container_width=True, hide_index=True, height=420)

    # ── Alerts ──────────────────────────────────────────────────────────────
    C.section_header("Exception alerts", "automated flags for analyst attention")

    alerts = _build_alerts(cur)
    if alerts:
        for a in alerts:
            st.markdown(
                f'<div style="background:white;border:1px solid #E2E8F0;'
                f'border-left:3px solid {a["color"]};border-radius:6px;'
                f'padding:0.6rem 0.85rem;margin-bottom:0.45rem;">'
                f'<div style="font-weight:600;color:#0F172A;font-size:0.88rem;">'
                f'{a["title"]}</div>'
                f'<div style="font-size:0.8rem;color:#475569;">{a["body"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.success("No exception alerts this month.")

    # ── Top movers chart ────────────────────────────────────────────────────
    C.section_header("YoY ranking", "horizontal bar of OEM YoY growth")
    yoy = cur.dropna(subset=["yoy_pct"]).copy().sort_values("yoy_pct", ascending=True)
    if not yoy.empty:
        fig = px.bar(
            yoy, x="yoy_pct", y="display_name",
            color="yoy_pct", color_continuous_scale=["#B91C1C", "#F1F5F9", "#15803D"],
            color_continuous_midpoint=0, range_color=[-0.4, 0.4],
            text=yoy["yoy_pct"].apply(lambda v: f"{v*100:+.1f}%"),
        )
        fig.update_traces(textposition="outside", textfont_size=10)
        fig.update_layout(**plotly_layout(height=max(280, 26 * len(yoy))))
        fig.update_xaxes(tickformat=".0%", title_text="YoY %")
        fig.update_yaxes(title_text="")
        fig.update_layout(coloraxis_showscale=False, bargap=0.35)
        st.plotly_chart(fig, use_container_width=True)

    # ── Export
    csv = cur.to_csv(index=False).encode()
    st.download_button(
        "Download month snapshot (CSV)", csv,
        f"auto_intel_{sel_month}.csv", "text/csv",
    )


# ── Alert engine ────────────────────────────────────────────────────────────

def _build_alerts(cur: pd.DataFrame) -> list[dict]:
    """Generate a list of analyst-facing alert dicts {title, body, color}."""
    out = []
    for _, r in cur.iterrows():
        oem = r["display_name"]
        seg = SEGMENT_LABELS.get(r["segment"], r["segment"])

        # Crashes / surges (YoY)
        yoy = r.get("yoy_pct")
        if pd.notna(yoy):
            if yoy <= -0.20:
                out.append({
                    "title": f"{oem} ({seg}) — YoY crash {yoy*100:+.1f}%",
                    "body":  f"Volume {C.fmt_units(r['total'])} vs same month last "
                             f"year. Beat/miss vs 6M: {C.fmt_pct(r.get('beat_miss_pct'))}.",
                    "color": "#B91C1C",
                })
            elif yoy >= 0.30:
                out.append({
                    "title": f"{oem} ({seg}) — YoY surge {yoy*100:+.1f}%",
                    "body":  f"Volume {C.fmt_units(r['total'])}. Z-score "
                             f"vs trailing 12M: "
                             f"{r['z_score_t12m']:+.2f}σ"
                             if pd.notna(r.get("z_score_t12m")) else "",
                    "color": "#15803D",
                })

        # Z-score anomaly (independent of YoY)
        z = r.get("z_score_t12m")
        if pd.notna(z) and abs(z) >= ANOMALY_Z:
            out.append({
                "title": f"{oem} ({seg}) — anomalous print ({z:+.2f}σ vs T12M)",
                "body":  f"Value {C.fmt_units(r['total'])} sits "
                         f"{z:+.2f} standard deviations from the OEM's own "
                         f"trailing 12-month distribution.",
                "color": "#B45309",
            })

        # Market-share shift
        ms_d = r.get("market_share_delta_mom_pp")
        if pd.notna(ms_d) and abs(ms_d) >= 1.0:
            out.append({
                "title": f"{oem} ({seg}) — share shift {ms_d:+.2f}pp MoM",
                "body":  f"Now {r['market_share_pct']*100:.2f}% of {seg}. "
                         f"Quartile in segment: Q{int(r['quartile_in_segment'])}."
                         if pd.notna(r.get("quartile_in_segment")) else "",
                "color": "#2563EB",
            })

        # Parser status
        if r["parser_status"] in ("NEEDS_REVIEW", "CONFLICT"):
            out.append({
                "title": f"{oem} ({seg}) — parser status {r['parser_status']}",
                "body":  f"Row needs analyst attention: {r.get('review_note', '')[:140]}",
                "color": "#B91C1C",
            })

    # de-duplicate (same title)
    seen, dedup = set(), []
    for a in out:
        if a["title"] in seen:
            continue
        seen.add(a["title"])
        dedup.append(a)
    return dedup
