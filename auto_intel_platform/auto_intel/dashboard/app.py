"""
dashboard/app.py — India Auto Monthly Monitor
================================================
Streamlit entry point. Sets up theme, sidebar navigation, and dispatches
to one of the analyst pages in dashboard/views/.

Every page reads the same enriched DataFrame via dashboard.data_layer.load_all.
This keeps numbers consistent across pages and stops UI code from doing maths.
"""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd
from datetime import datetime

from dashboard.theme import apply_theme
from dashboard import components as C
from dashboard.data_layer import load_all, latest_month
from dashboard.views import (
    overview,
    monitoring,
    deep_dive,
    market_share,
    exports as exports_view,
    ev_penetration,
    filing_tracker,
    data_quality,
    review_queue,
    retail_insights,
    forecast,
)
from dashboard.views import filing_tracker as _ft_mod   # for merged page


# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="India Auto Monthly Monitor",
    page_icon="🚙",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()


# ── Navigation map ───────────────────────────────────────────────────────────
def _filing_and_quality():
    """Filing Tracker + Data Quality merged into two tabs."""
    t1, t2 = st.tabs(["📅 Filing Tracker", "🔍 Data Quality"])
    with t1:
        filing_tracker.render()
    with t2:
        data_quality.render()


def _admin():
    """Review Queue + manual entry (already has its own tabs)."""
    review_queue.render()


NAV = [
    # ── Wholesale section ─────────────────────────────────────────────────────
    ("⚡ Overview",       "Industry headline, segment heat, top movers",  overview.render),
    ("🔍 Monitoring",    "This-month change deep-dive & alerts",          monitoring.render),
    ("🏢 Deep Dive",     "Single-OEM analyst profile",                    deep_dive.render),
    ("📊 Market Share",  "Ranked share, HHI, share migration",            market_share.render),
    ("📤 Exports",       "Export volume, mix, decoupling check",          exports_view.render),
    ("⚡ EV Penetration","Industry EV share + per-OEM exposure",          ev_penetration.render),
    # ── Retail section ────────────────────────────────────────────────────────
    ("📱 Retail Pulse",  "FADA retail registrations & dealer inventory",  retail_insights.render),
    ("📈 Forecast",      "3-month demand forecast · Holt-Winters / linear trend", forecast.render),
    # ── Data ops ──────────────────────────────────────────────────────────────
    ("📅 Filing Tracker","Filing SLA · Data Quality scorecard",           _filing_and_quality),
    ("🔄 Admin",         "Review queue · Manual data entry",              _admin),
]


# ── Sidebar ──────────────────────────────────────────────────────────────────
def render_sidebar() -> str:
    with st.sidebar:
        st.markdown(
            "<div style='padding:0.4rem 0 0.6rem;'>"
            "<div style='font-size:1.05rem;font-weight:700;color:#F8FAFC;'>"
            "India Auto Monitor</div>"
            "<div style='font-size:0.78rem;color:#94A3B8;margin-top:0.15rem;'>"
            "Institutional operating-data platform"
            "</div></div>",
            unsafe_allow_html=True,
        )
        st.divider()

        labels = [f"{name}" for name, _sub, _f in NAV]
        choice = st.radio(
            "Analyst workspace",
            labels,
            index=0,
            key="nav_choice",
            label_visibility="visible",
        )

        st.divider()
        norm, _, _, rq = load_all()
        if not norm.empty:
            lm = latest_month(norm)
            n_oems = norm["company_key"].nunique()
            rows = len(norm)
            review_n = len(rq) if rq is not None and not rq.empty else 0

            st.markdown(
                f"""
                <div style='font-size:0.78rem;color:#CBD5E1;line-height:1.65;'>
                <div><span style='color:#94A3B8;'>Latest data</span>
                    <span style='float:right;color:#F8FAFC;font-weight:600;'>{lm or '—'}</span></div>
                <div><span style='color:#94A3B8;'>OEMs tracked</span>
                    <span style='float:right;color:#F8FAFC;font-weight:600;'>{n_oems}</span></div>
                <div><span style='color:#94A3B8;'>Total rows</span>
                    <span style='float:right;color:#F8FAFC;font-weight:600;'>{C.fmt_indian(rows)}</span></div>
                <div><span style='color:#94A3B8;'>Review queue</span>
                    <span style='float:right;color:{"#F87171" if review_n else "#15803D"};font-weight:600;'>{review_n}</span></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.divider()
        st.markdown(
            "<div style='font-size:0.74rem;color:#94A3B8;line-height:1.55;'>"
            "<b style='color:#E2E8F0;'>Source priority</b><br>"
            "OEM Investor Relations pages (primary) · FADA retail (separate).<br><br>"
            "<b style='color:#E2E8F0;'>Automation</b><br>"
            "Filing-window workflow runs 4×/day during 1st-7th of each month "
            "(post-month-close). Daily baseline otherwise."
            "</div>",
            unsafe_allow_html=True,
        )
        st.divider()
        st.markdown(
            f"<div style='font-size:0.72rem;color:#64748B;'>"
            f"Refreshed {datetime.now().strftime('%d %b %Y · %H:%M')}"
            f"</div>",
            unsafe_allow_html=True,
        )
    return choice


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    choice = render_sidebar()

    page = next((entry for entry in NAV if entry[0] == choice), None)
    if page is None:
        st.error("Page not found.")
        return

    norm, _, _, _ = load_all()
    lm     = latest_month(norm) if not norm.empty else "—"
    n_oems = norm["company_key"].nunique() if not norm.empty else 0
    refreshed = datetime.now().strftime("%d %b %Y %H:%M")

    # Compact metadata bar — replaces the tall hero banner
    st.markdown(
        f"<div style='background:#1E293B;color:#94A3B8;padding:6px 16px;"
        f"font-size:0.72rem;border-radius:4px;margin-bottom:12px;"
        f"display:flex;justify-content:space-between;align-items:center;'>"
        f"<span><b style='color:#F1F5F9;font-size:0.82rem;'>{page[0]}</b>"
        f"&nbsp;&nbsp;·&nbsp;&nbsp;{page[1]}</span>"
        f"<span>Latest:&nbsp;<b style='color:#F1F5F9;'>{lm}</b>"
        f"&nbsp;&nbsp;·&nbsp;&nbsp;OEMs:&nbsp;<b style='color:#F1F5F9;'>{n_oems}</b>"
        f"&nbsp;&nbsp;·&nbsp;&nbsp;Refreshed:&nbsp;{refreshed}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    page[2]()

    C.footer(
        "India Auto Monthly Monitor · OEM IR pages · pipeline-validated data",
    )


if __name__ == "__main__":
    main()
