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
)


# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="India Auto Monthly Monitor",
    page_icon="🚙",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()


# ── Navigation map ───────────────────────────────────────────────────────────
NAV = [
    ("Overview",         "Industry headline, segment heat, top movers", overview.render),
    ("Monitoring",       "This-month change deep-dive & alerts",         monitoring.render),
    ("Deep Dive",        "Single-OEM analyst profile",                   deep_dive.render),
    ("Market Share",     "Ranked share, HHI, share migration",           market_share.render),
    ("Exports",          "Export volume, mix, decoupling check",         exports_view.render),
    ("EV Penetration",   "Industry EV share + per-OEM exposure",         ev_penetration.render),
    ("Filing Tracker",   "Filing SLA & data freshness",                  filing_tracker.render),
    ("Data Quality",     "Reliability scorecard & anomaly feed",         data_quality.render),
    ("Review Queue",     "Reviewer workflow",                            review_queue.render),
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
                    <span style='float:right;color:#F8FAFC;font-weight:600;'>{rows:,}</span></div>
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
            "NSE corporate announcements → BSE fallback → OEM IR pages.<br><br>"
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
    lm = latest_month(norm) if not norm.empty else None
    n_oems = norm["company_key"].nunique() if not norm.empty else 0
    rows = len(norm) if not norm.empty else 0

    C.hero(
        title=f"{page[0]}",
        subtitle=page[1],
        meta=[
            ("Latest filing month", lm or "—"),
            ("OEMs", str(n_oems)),
            ("Rows", f"{rows:,}"),
            ("Last refreshed", datetime.now().strftime("%d %b %Y %H:%M")),
        ],
    )

    page[2]()

    C.footer(
        "India Auto Monthly Monitor · NSE/BSE filings · pipeline-validated data",
    )


if __name__ == "__main__":
    main()
