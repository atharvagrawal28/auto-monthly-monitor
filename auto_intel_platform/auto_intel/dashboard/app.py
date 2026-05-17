"""
dashboard/app.py — India Auto Monthly Monitor
==============================================
Three analyst workflow modes:
  A. Monitoring   — "What changed this month?"
  B. Deep Dive    — "Tell me everything about Tata CV"
  C. Comparative  — "Compare OEMs/segments"
  D. Filing Tracker (landing page)
  E. Review Queue (admin)
"""

import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from pipeline.store import (
    load_normalized, load_granular, load_filing_status,
    load_review_queue, get_market_share,
)
from schema import ParserStatus

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="India Auto Monitor",
    page_icon="A",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Brand colors ──────────────────────────────────────────────────────────────
COLORS = {
    "MARUTI":        "#2563EB",
    "TATAMOTORS_PV": "#DC2626",
    "TATAMOTORS_CV": "#B91C1C",
    "MAHINDRA_AUTO": "#059669",
    "MAHINDRA_FARM": "#047857",
    "BAJAJ":         "#D97706",
    "HEROMOTOCO":    "#7C3AED",
    "TVS":           "#DB2777",
    "ASHOKLEY":      "#0891B2",
    "ESCORTS":       "#65A30D",
    "EICHER":        "#EA580C",
    "OLA_ELECTRIC":  "#0D9488",
}

DISPLAY_NAMES = {
    "MARUTI":        "Maruti Suzuki",
    "TATAMOTORS_PV": "Tata Motors PV",
    "TATAMOTORS_CV": "Tata Motors CV",
    "MAHINDRA_AUTO": "Mahindra Auto",
    "MAHINDRA_FARM": "Mahindra Farm",
    "BAJAJ":         "Bajaj Auto",
    "HEROMOTOCO":    "Hero MotoCorp",
    "TVS":           "TVS Motor",
    "ASHOKLEY":      "Ashok Leyland",
    "ESCORTS":       "Escorts Kubota",
    "EICHER":        "Eicher (RE)",
    "OLA_ELECTRIC":  "Ola Electric",
}

SEGMENT_LABELS = {
    "PV": "Passenger Vehicles (PV)",
    "CV": "Commercial Vehicles (CV)",
    "2W": "Two-Wheelers (2W)",
    "3W": "Three-Wheelers (3W)",
    "Tractor": "Tractors / Farm Equipment",
    "EV": "Electric Vehicles (EV)",
}

SEGMENT_UNITS = {
    "PV": "vehicle units",
    "CV": "vehicle units",
    "2W": "two-wheeler units",
    "3W": "three-wheeler units",
    "Tractor": "tractor units",
    "EV": "EV units",
}

STATUS_LABELS = {
    ParserStatus.CLEAN: "Clean",
    ParserStatus.FLAGGED: "Flagged",
    ParserStatus.NEEDS_REVIEW: "Needs Review",
    ParserStatus.CONFLICT: "Conflict",
    ParserStatus.MANUAL: "Manual",
    ParserStatus.STALE: "Stale",
}

STATUS_EMOJI = {
    ParserStatus.CLEAN:        "✅",
    ParserStatus.FLAGGED:      "⚠️",
    ParserStatus.NEEDS_REVIEW: "🔄",
    ParserStatus.CONFLICT:     "❌",
    ParserStatus.MANUAL:       "✏️",
    ParserStatus.STALE:        "⏳",
}


def segment_label(segment: str) -> str:
    return SEGMENT_LABELS.get(segment, segment)


def unit_label(segment: str) -> str:
    return SEGMENT_UNITS.get(segment, "units")


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def format_units(value) -> str:
    return f"{int(value):,}" if pd.notna(value) else "-"


def format_pct(value) -> str:
    return f"{value:.1%}" if pd.notna(value) else "-"


@st.cache_data(ttl=300)
def get_data():
    norm    = load_normalized()
    gran    = load_granular()
    status  = load_filing_status()
    review  = load_review_queue()

    if not norm.empty:
        norm["total"]    = pd.to_numeric(norm["total"],    errors="coerce")
        norm["domestic"] = pd.to_numeric(norm["domestic"], errors="coerce")
        norm["exports"]  = pd.to_numeric(norm["exports"],  errors="coerce")
        norm["yoy_pct"]  = pd.to_numeric(norm["yoy_pct"],  errors="coerce")
        norm["mom_pct"]  = pd.to_numeric(norm["mom_pct"],  errors="coerce")
        norm["display_name"] = norm["company_key"].map(DISPLAY_NAMES).fillna(norm["company_key"])
        norm["segment_label"] = norm["segment"].map(SEGMENT_LABELS).fillna(norm["segment"])
        norm["unit_label"] = norm["segment"].map(SEGMENT_UNITS).fillna("units")
        norm["status_label"] = norm["parser_status"].map(STATUS_LABELS).fillna(norm["parser_status"])
        norm["export_mix_pct"] = (norm["exports"] / norm["total"]).where(norm["total"] > 0)
        norm["_dt"] = pd.to_datetime(norm["filing_month_year"] + "-01", errors="coerce")

    return norm, gran, status, review


# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown("## India Auto Monthly Monitor")
        st.markdown("*Institutional operating data platform*")
        st.divider()

        mode = st.radio(
            "**Analyst Mode**",
            ["Filing Tracker", "Monitoring", "Deep Dive", "Comparative", "Review Queue"],
            index=0,
        )
        st.divider()

        norm, _, _, _ = get_data()
        if not norm.empty:
            all_months = sorted(norm["filing_month_year"].unique(), reverse=True)
            latest_month = all_months[0] if all_months else None
            st.markdown(f"**Latest data:** `{latest_month}`")
            st.markdown(f"**OEMs tracked:** `{norm['company_key'].nunique()}`")
            st.markdown(f"**Total rows:** `{len(norm):,}`")
        st.markdown("**Scheduled fetch:** Daily 09:30 IST")
        st.caption("Sources: NSE announcements first, BSE fallback. OEM IR pages can be added as fallback adapters.")
        st.divider()
        st.caption(f"Last refreshed: {datetime.now().strftime('%d %b %Y %H:%M')}")

    return mode


# ─── PAGE: FILING TRACKER ─────────────────────────────────────────────────────
def page_filing_tracker():
    st.header("Filing Tracker")
    st.caption("Data freshness, filing status, segment coverage, and source lineage.")

    norm, _, filing_df, _ = get_data()

    if norm.empty:
        st.warning("No data yet. Run `python data/generate_sample.py` to load sample data.")
        return

    with st.expander("How the data is fetched and refreshed", expanded=True):
        st.markdown(
            """
            **Schedule:** GitHub Actions runs the pipeline daily at **09:30 IST** and it can also be run manually.

            **Source order:** NSE corporate announcements are checked first. If no filing is found for a symbol, BSE announcements are used as fallback. OEM investor-relations pages should be added next as fallback/cross-check source adapters.

            **Dataset rule:** the dashboard does not scrape live pages. It reads validated CSV data created by the pipeline: fetch filings, download PDFs, extract tables, normalize rows, validate, then store clean rows or route exceptions to review.
            """
        )

    all_months = sorted(norm["filing_month_year"].unique(), reverse=True)
    oems       = list(DISPLAY_NAMES.keys())
    latest_4   = all_months[:4]

    # Build status matrix
    matrix_rows = []
    for oem_key in oems:
        oem_rows = norm[norm["company_key"] == oem_key]
        coverage = ", ".join(sorted(oem_rows["segment_label"].dropna().unique())) if not oem_rows.empty else "-"
        row_data = {"OEM": DISPLAY_NAMES.get(oem_key, oem_key), "Coverage": coverage}
        for month in latest_4:
            month_data = norm[
                (norm["company_key"] == oem_key) &
                (norm["filing_month_year"] == month)
            ]
            if month_data.empty:
                row_data[month] = "Pending"
            else:
                status = month_data.iloc[0]["parser_status"]
                total  = int(month_data.iloc[0]["total"]) if pd.notna(month_data.iloc[0]["total"]) else 0
                row_data[month] = f"{status_label(status)} | {total:,} units"
        matrix_rows.append(row_data)

    matrix_df = pd.DataFrame(matrix_rows)

    st.subheader("Filing Status Matrix")
    st.table(matrix_df)

    # Summary metrics
    latest = norm[norm["filing_month_year"] == all_months[0]] if all_months else pd.DataFrame()
    col1, col2, col3, col4 = st.columns(4)

    clean_count    = len(latest[latest["parser_status"] == ParserStatus.CLEAN])
    flagged_count  = len(latest[latest["parser_status"] == ParserStatus.FLAGGED])
    review_count   = len(latest[latest["parser_status"] == ParserStatus.NEEDS_REVIEW])
    pending_count  = max(0, len(oems) - len(latest))

    col1.metric("Clean rows", clean_count)
    col2.metric("Flagged rows", flagged_count)
    col3.metric("Needs review", review_count)
    col4.metric("Pending OEMs", pending_count)


# ─── PAGE: MONITORING ─────────────────────────────────────────────────────────
def page_monitoring():
    st.header("Monthly Monitoring")
    st.caption("All volumes are monthly units reported in OEM filings. Domestic and export values are separated where the filing provides them.")

    norm, _, _, _ = get_data()
    if norm.empty:
        st.warning("No data available.")
        return

    all_months = sorted(norm["filing_month_year"].unique(), reverse=True)
    selected_month = st.selectbox("Select Month", all_months, index=0)

    current  = norm[norm["filing_month_year"] == selected_month].copy()
    prev_idx = 1 if len(all_months) > 1 else None
    previous = norm[norm["filing_month_year"] == all_months[prev_idx]].copy() if prev_idx else pd.DataFrame()

    if current.empty:
        st.info("No data for selected month.")
        return

    # ── KPI row ───────────────────────────────────────────────────────────────
    st.subheader(f"Industry Snapshot - {selected_month}")
    cols = st.columns(4)

    pv_total = current[current["segment"] == "PV"]["total"].sum()
    cv_total = current[current["segment"] == "CV"]["total"].sum()
    tw_total = current[current["segment"] == "2W"]["total"].sum()
    ev_total = current[current["segment"] == "EV"]["total"].sum()

    cols[0].metric("Passenger Vehicles", f"{int(pv_total):,}", "vehicle units")
    cols[1].metric("Commercial Vehicles", f"{int(cv_total):,}", "vehicle units")
    cols[2].metric("Two-Wheelers", f"{int(tw_total):,}", "two-wheeler units")
    cols[3].metric("Electric Vehicles", f"{int(ev_total):,}", "EV units")

    # ── YoY table ────────────────────────────────────────────────────────────
    st.subheader("OEM Performance This Month")
    display = current[[
        "display_name", "segment_label", "unit_label", "total", "domestic",
        "exports", "export_mix_pct", "yoy_pct", "mom_pct", "source",
        "filing_date", "status_label", "confidence_score",
    ]].copy()
    display["total"] = display["total"].apply(format_units)
    display["domestic"] = display["domestic"].apply(format_units)
    display["exports"] = display["exports"].apply(format_units)
    display["export_mix_pct"] = display["export_mix_pct"].apply(format_pct)
    display["yoy_pct"] = display["yoy_pct"].apply(format_pct)
    display["mom_pct"] = display["mom_pct"].apply(format_pct)
    display["confidence_score"] = display["confidence_score"].apply(lambda x: f"{x:.0%}" if pd.notna(x) else "-")
    display.columns = [
        "OEM", "Segment", "Unit Type", "Total Units", "Domestic Units",
        "Export Units", "Export Mix", "YoY", "MoM", "Source",
        "Filing Date", "Parser Status", "Confidence",
    ]

    st.dataframe(display, use_container_width=True, hide_index=True)

    # ── Segment bar chart ─────────────────────────────────────────────────────
    st.subheader("OEM Sales by Segment")
    fig = px.bar(
        current.sort_values("total", ascending=False),
        x="display_name", y="total", color="segment_label",
        labels={"display_name": "OEM", "total": "Monthly Units", "segment_label": "Segment"},
        height=400, title=f"Monthly Units by OEM and Segment - {selected_month}",
    )
    fig.update_layout(xaxis_tickangle=-30, yaxis_title="Monthly units")
    st.plotly_chart(fig, use_container_width=True)

    # ── Alerts ───────────────────────────────────────────────────────────────
    st.subheader("Exception Alerts")
    alerts = []
    for _, row in current.iterrows():
        yoy = row.get("yoy_pct")
        if pd.notna(yoy):
            if yoy <= -0.20:
                alerts.append(f"**{DISPLAY_NAMES.get(row['company_key'], row['company_key'])}** - {segment_label(row['segment'])} volume down {yoy:.1%} YoY")
            elif yoy >= 0.30:
                alerts.append(f"**{DISPLAY_NAMES.get(row['company_key'], row['company_key'])}** - {segment_label(row['segment'])} volume up {yoy:.1%} YoY")
        if row.get("parser_status") == ParserStatus.NEEDS_REVIEW:
            alerts.append(f"**{DISPLAY_NAMES.get(row['company_key'], row['company_key'])}** - parser output is in the review queue")

    if alerts:
        for a in alerts:
            st.markdown(a)
    else:
        st.success("No significant alerts this month.")

    # ── Download ──────────────────────────────────────────────────────────────
    csv = current.to_csv(index=False).encode()
    st.download_button(f"Download {selected_month} Data", csv,
                       f"auto_intel_{selected_month}.csv", "text/csv")


# ─── PAGE: DEEP DIVE ──────────────────────────────────────────────────────────
def page_deep_dive():
    st.header("OEM Deep Dive")

    norm, gran, _, _ = get_data()
    if norm.empty:
        st.warning("No data available.")
        return

    col1, col2 = st.columns(2)
    oem_options = {v: k for k, v in DISPLAY_NAMES.items() if k in norm["company_key"].values}
    selected_display = col1.selectbox("Select OEM", list(oem_options.keys()))
    selected_key = oem_options[selected_display]

    oem_df = norm[norm["company_key"] == selected_key].sort_values("filing_month_year")

    if oem_df.empty:
        st.info("No data for this OEM.")
        return

    # ── KPI row ───────────────────────────────────────────────────────────────
    latest   = oem_df.iloc[-1]
    prev     = oem_df.iloc[-2] if len(oem_df) > 1 else None
    latest_segment = segment_label(latest["segment"])
    latest_units = unit_label(latest["segment"])

    st.caption(
        f"Latest filing month: {latest['filing_month_year']} | "
        f"Segment: {latest_segment} | Unit type: {latest_units} | "
        f"Source: {latest.get('source', '-')}"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Latest Total Units", format_units(latest["total"]),
              f"{latest['yoy_pct']:.1%} YoY" if pd.notna(latest.get('yoy_pct')) else None)
    c2.metric("Domestic Units", format_units(latest["domestic"]))
    c3.metric("Export Units", format_units(latest["exports"]))

    export_mix = (latest['exports'] / latest['total'] * 100) if pd.notna(latest['exports']) and latest['total'] > 0 else 0
    c4.metric("Export Mix",      f"{export_mix:.1f}%")

    # ── Volume trend ──────────────────────────────────────────────────────────
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=oem_df["filing_month_year"], y=oem_df["domestic"],
        name="Domestic", marker_color="#2563EB"
    ))
    fig.add_trace(go.Bar(
        x=oem_df["filing_month_year"], y=oem_df["exports"],
        name="Exports", marker_color="#F59E0B"
    ))
    fig.update_layout(
        barmode="stack", title=f"{selected_display} - Monthly Unit Trend",
        xaxis_title="Month", yaxis_title=f"Monthly units ({latest_units})", height=380,
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── YoY trend ────────────────────────────────────────────────────────────
    yoy_df = oem_df.dropna(subset=["yoy_pct"])
    if not yoy_df.empty:
        fig2 = px.line(
            yoy_df, x="filing_month_year", y="yoy_pct",
            title=f"{selected_display} - YoY Growth (%)",
            labels={"yoy_pct": "YoY %", "filing_month_year": "Month"},
            height=300,
        )
        fig2.add_hline(y=0, line_dash="dash", line_color="red")
        fig2.update_traces(line_color=COLORS.get(selected_key, "#2563EB"))
        fig2.update_yaxes(tickformat=".0%")
        st.plotly_chart(fig2, use_container_width=True)

    # ── Data table ────────────────────────────────────────────────────────────
    with st.expander("Full Data Table"):
        display = oem_df[["filing_month_year", "segment_label", "unit_label", "domestic", "exports",
                           "total", "yoy_pct", "mom_pct", "source", "filing_date", "status_label"]].copy()
        for col in ["domestic", "exports", "total"]:
            display[col] = display[col].apply(format_units)
        display["yoy_pct"] = display["yoy_pct"].apply(format_pct)
        display["mom_pct"] = display["mom_pct"].apply(format_pct)
        display.columns = [
            "Month", "Segment", "Unit Type", "Domestic Units", "Export Units",
            "Total Units", "YoY", "MoM", "Source", "Filing Date", "Status",
        ]
        st.dataframe(display, use_container_width=True, hide_index=True)

    csv = oem_df.to_csv(index=False).encode()
    st.download_button(f"Download {selected_display} Data", csv,
                       f"{selected_key}_history.csv", "text/csv")


# ─── PAGE: COMPARATIVE ────────────────────────────────────────────────────────
def page_comparative():
    st.header("Comparative Analysis")

    norm, _, _, _ = get_data()
    if norm.empty:
        st.warning("No data available.")
        return

    all_months = sorted(norm["filing_month_year"].unique(), reverse=True)
    segments = sorted(norm["segment"].unique())
    segment_options = {segment_label(seg): seg for seg in segments}

    tab1, tab2, tab3 = st.tabs(["Market Share", "Segment Trends", "Export Analysis"])

    # ── Market Share ─────────────────────────────────────────────────────────
    with tab1:
        st.subheader("Market Share by Segment")
        col1, col2 = st.columns(2)
        selected_month = col1.selectbox("Month", all_months, key="ms_month")
        selected_seg_label = col2.selectbox("Segment", list(segment_options.keys()), key="ms_seg")
        selected_seg = segment_options[selected_seg_label]

        ms_df = norm[
            (norm["filing_month_year"] == selected_month) &
            (norm["segment"] == selected_seg)
        ].copy()

        if not ms_df.empty:
            total = ms_df["total"].sum()
            ms_df["share"] = ms_df["total"] / total * 100

            fig = px.pie(
                ms_df, values="share", names="display_name",
                title=f"{selected_seg_label} Market Share - {selected_month}",
                hole=0.4, height=400,
            )
            st.plotly_chart(fig, use_container_width=True)

            # Share over time (last 6 months)
            last_6 = all_months[:6]
            share_rows = []
            for m in last_6:
                seg_df = norm[(norm["filing_month_year"] == m) & (norm["segment"] == selected_seg)]
                if seg_df.empty: continue
                total_m = seg_df["total"].sum()
                for _, r in seg_df.iterrows():
                    share_rows.append({
                        "month": m,
                        "OEM":   DISPLAY_NAMES.get(r["company_key"], r["company_key"]),
                        "share": r["total"] / total_m * 100 if total_m > 0 else 0,
                    })

            if share_rows:
                share_trend = pd.DataFrame(share_rows)
                fig2 = px.area(
                    share_trend, x="month", y="share", color="OEM",
                    title=f"{selected_seg_label} Market Share Trend (Last 6M)",
                    labels={"share": "Share %", "month": "Month"}, height=350,
                )
                st.plotly_chart(fig2, use_container_width=True)

    # ── Segment Trends ────────────────────────────────────────────────────────
    with tab2:
        st.subheader("Industry Segment Volume Trends")
        seg_agg = norm.groupby(["filing_month_year", "segment_label"])["total"].sum().reset_index()
        fig = px.line(
            seg_agg, x="filing_month_year", y="total", color="segment_label",
            title="Segment-wise Monthly Volume (All OEMs)",
            labels={"total": "Monthly Units", "filing_month_year": "Month", "segment_label": "Segment"}, height=420,
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Export Analysis ───────────────────────────────────────────────────────
    with tab3:
        st.subheader("Export Trends")
        selected_seg_exp_label = st.selectbox("Segment", list(segment_options.keys()), key="exp_seg")
        selected_seg_exp = segment_options[selected_seg_exp_label]

        exp_df = norm[norm["segment"] == selected_seg_exp].copy()
        exp_df["export_mix"] = exp_df["exports"] / exp_df["total"] * 100

        fig = px.line(
            exp_df.sort_values("filing_month_year"),
            x="filing_month_year", y="export_mix", color="display_name",
            title=f"Export Mix % - {selected_seg_exp_label}",
            labels={"export_mix": "Export %", "filing_month_year": "Month"}, height=380,
        )
        st.plotly_chart(fig, use_container_width=True)

    # Download full dataset
    st.divider()
    csv = norm.to_csv(index=False).encode()
    st.download_button("Download Full Normalized Dataset",
                       csv, "auto_intel_full.csv", "text/csv")


# ─── PAGE: REVIEW QUEUE ───────────────────────────────────────────────────────
def page_review_queue():
    st.header("Review Queue")
    st.caption("Rows that failed validation or triggered reconciliation conflicts.")

    _, _, _, review_df = get_data()

    if review_df.empty:
        st.success("Review queue is empty. All data is clean.")
        return

    st.warning(f"{len(review_df)} rows need attention.")

    if "segment" in review_df.columns:
        review_df["segment_label"] = review_df["segment"].map(SEGMENT_LABELS).fillna(review_df["segment"])
    display_cols = ["company_key", "segment_label", "filing_month_year",
                    "total", "domestic", "exports", "source", "filing_date", "parser_status", "review_note"]
    show_df = review_df[[c for c in display_cols if c in review_df.columns]].copy()
    st.dataframe(show_df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Approve / Correct an Item")

    with st.form("approve_form"):
        col1, col2, col3 = st.columns(3)
        a_company  = col1.selectbox("Company", review_df["company_key"].unique() if "company_key" in review_df.columns else [])
        a_segment  = col2.selectbox("Segment", review_df["segment"].unique() if "segment" in review_df.columns else [])
        a_month    = col3.selectbox("Month",   review_df["filing_month_year"].unique() if "filing_month_year" in review_df.columns else [])
        a_total    = st.number_input("Corrected Total (0 = keep original)", min_value=0)
        a_note     = st.text_input("Reviewer Note")
        submitted  = st.form_submit_button("Approve & Move to Dataset")

        if submitted:
            from pipeline.store import approve_review_item
            ok = approve_review_item(
                a_company, a_segment, a_month,
                corrected_total=int(a_total) if a_total > 0 else None,
                reviewer_note=a_note,
            )
            if ok:
                st.success("Approved and moved to normalized dataset.")
                st.cache_data.clear()
            else:
                st.error("Approval failed — item not found in queue.")

    csv = review_df.to_csv(index=False).encode()
    st.download_button("Download Review Queue", csv, "review_queue.csv", "text/csv")


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    mode = render_sidebar()

    if mode == "Filing Tracker":
        page_filing_tracker()
    elif mode == "Monitoring":
        page_monitoring()
    elif mode == "Deep Dive":
        page_deep_dive()
    elif mode == "Comparative":
        page_comparative()
    elif mode == "Review Queue":
        page_review_queue()


if __name__ == "__main__":
    main()
