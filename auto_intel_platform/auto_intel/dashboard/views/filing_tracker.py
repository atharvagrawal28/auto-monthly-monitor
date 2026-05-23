"""
views/filing_tracker.py — Filing Tracker (SLA + freshness)
============================================================
The "are we current?" page.

For each OEM × latest 6 months:
  - Was the filing posted within typical_filing_day + 2 grace days?
  - Days late vs the SLA?
  - Status pill (ON_TIME / LATE / MISSING / UPCOMING)
  - Per-OEM SLA scorecard (on-time pct, median days late, typical day)
"""

from __future__ import annotations
import pandas as pd
import plotly.express as px
import streamlit as st

from .. import components as C
from ..theme import BRAND, plotly_layout
from ..data_layer import load_all, DISPLAY_NAMES, SEGMENT_LABELS
from analytics.quality import filing_sla, filing_sla_summary
from registry import OEM_REGISTRY


def render():
    norm, _, fs, _ = load_all()
    if norm.empty:
        C.empty_state("No data", "Generate sample data first.")
        return

    months_back = 6
    months_axis = sorted(norm["filing_month_year"].unique())[-months_back:]

    # ── KPI strip
    sla_df = filing_sla_summary(norm, OEM_REGISTRY, months_window=12)
    industry_ontime = sla_df["on_time_pct"].mean() if not sla_df.empty else 0
    median_late = sla_df["median_days_late"].median() if not sla_df.empty else 0
    oems = sla_df["company_key"].nunique() if not sla_df.empty else 0

    C.kpi_row([
        {"label": "Industry on-time rate (T12M)",
         "value": f"{industry_ontime*100:.1f}%",
         "foot":  "filed within typical_filing_day + 2 days"},
        {"label": "Median days late (T12M)",
         "value": f"{median_late:+.1f}d",
         "foot":  "across OEMs"},
        {"label": "OEMs tracked", "value": str(oems)},
    ])

    # ── Filing matrix ───────────────────────────────────────────────────────
    C.section_header(
        "Filing status matrix",
        f"last {months_back} months · ✓ on-time · ! late · ✗ missing",
    )

    oem_keys = sorted(norm["company_key"].dropna().unique())
    matrix_rows = []
    for oem in oem_keys:
        cfg = OEM_REGISTRY.get(oem)
        typical = getattr(cfg, "typical_filing_day", 5) if cfg else 5

        row = {"OEM": DISPLAY_NAMES.get(oem, oem),
               "Typical day": f"D+{typical}"}
        for m in months_axis:
            oem_m = norm[(norm["company_key"] == oem) &
                         (norm["filing_month_year"] == m)]
            if oem_m.empty:
                sla = filing_sla({"filing_month_year": m, "filing_date": ""},
                                 typical_day=typical)
                cell = _cell_html(sla["status"], None, None)
            else:
                r = oem_m.iloc[0]
                sla = filing_sla(r, typical_day=typical)
                cell = _cell_html(sla["status"], sla["days_late"], r["total"])
            row[pd.to_datetime(m + "-01").strftime("%b %y")] = cell
        matrix_rows.append(row)

    matrix_df = pd.DataFrame(matrix_rows)
    st.markdown(_matrix_to_html(matrix_df), unsafe_allow_html=True)

    # ── SLA scorecard ──────────────────────────────────────────────────────
    if not sla_df.empty:
        C.section_header("SLA scorecard", "trailing 12 months by OEM")
        sla_show = sla_df.copy()
        sla_show["company_key"] = sla_show["company_key"].map(DISPLAY_NAMES).fillna(sla_show["company_key"])
        sla_show["on_time_pct"] = (sla_show["on_time_pct"] * 100).round(1).astype(str) + "%"
        sla_show["late_pct"] = (sla_show["late_pct"] * 100).round(1).astype(str) + "%"
        sla_show.columns = ["OEM", "Filings observed", "On-time %",
                            "Late %", "Median days late", "Typical day"]
        st.dataframe(sla_show, use_container_width=True, hide_index=True)

        # bar chart
        sla_chart = sla_df.copy()
        sla_chart["display_name"] = sla_chart["company_key"].map(DISPLAY_NAMES)
        sla_chart["on_time_pct_disp"] = sla_chart["on_time_pct"] * 100
        fig = px.bar(
            sla_chart.sort_values("on_time_pct_disp"),
            x="on_time_pct_disp", y="display_name", orientation="h",
            color="on_time_pct_disp",
            color_continuous_scale=["#B91C1C", "#FEF3C7", "#15803D"],
            range_color=[0, 100],
            text=sla_chart.sort_values("on_time_pct_disp")["on_time_pct_disp"].apply(
                lambda v: f"{v:.0f}%"),
        )
        fig.update_traces(textposition="outside", textfont_size=10)
        fig.update_layout(**plotly_layout(height=max(280, 26 * len(sla_chart))))
        fig.update_xaxes(ticksuffix="%", title_text="On-time %")
        fig.update_yaxes(title_text="")
        fig.update_layout(coloraxis_showscale=False, bargap=0.35)
        st.plotly_chart(fig, use_container_width=True)


def _cell_html(status: str, days_late, units) -> str:
    pill = C.status_pill(status)
    extra = ""
    if status in ("LATE",):
        extra = f"<br><span style='font-size:0.72rem;color:#92400E;'>+{days_late}d</span>"
    if status == "ON_TIME" and units:
        extra = (
            f"<br><span style='font-size:0.72rem;color:#475569;'>"
            f"{C.fmt_indian(int(units))}</span>"
        )
    return f"{pill}{extra}"


def _matrix_to_html(df: pd.DataFrame) -> str:
    """Render the filing matrix as a clean HTML table (status pills + counts)."""
    head = "".join(f"<th>{c}</th>" for c in df.columns)
    rows_html = []
    for _, r in df.iterrows():
        cells = []
        for c in df.columns:
            val = r[c]
            if c in ("OEM", "Typical day"):
                cells.append(f"<td style='font-weight:600;color:#0F172A;'>{val}</td>")
            else:
                cells.append(f"<td style='text-align:center;'>{val}</td>")
        rows_html.append(f"<tr>{''.join(cells)}</tr>")
    return f"""
    <div style="background:white;border:1px solid #E2E8F0;border-radius:8px;
                overflow:hidden;">
        <table style="width:100%;border-collapse:collapse;font-size:0.84rem;">
            <thead style="background:#F1F5F9;">
                <tr>{head}</tr>
            </thead>
            <tbody>{''.join(rows_html)}</tbody>
        </table>
    </div>
    <style>
        table th {{ padding:0.55rem 0.7rem;color:#475569;text-transform:uppercase;
                    font-size:0.7rem;letter-spacing:0.04em;text-align:left; }}
        table td {{ padding:0.6rem 0.7rem;border-top:1px solid #F1F5F9; }}
    </style>
    """
