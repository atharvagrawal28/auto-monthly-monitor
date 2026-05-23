"""
views/review_queue.py — Reviewer workflow
===========================================
Read the rows that failed validation / triggered conflicts, let the analyst
approve them (optionally with corrections), and move them to the normalized
dataset with MANUAL status.
"""

from __future__ import annotations
import pandas as pd
import streamlit as st

from .. import components as C
from ..data_layer import load_all, DISPLAY_NAMES, SEGMENT_LABELS
from pipeline.store import approve_review_item


def render():
    _, _, _, rq = load_all()

    C.section_header(
        "Review queue",
        "rows that failed validation, hit reconciliation conflict, or were "
        "downgraded by anomaly flags",
    )

    if rq is None or rq.empty:
        C.empty_state(
            "Queue is empty",
            "All rows are clean. No analyst action required.",
        )
        return

    st.warning(f"{len(rq)} rows need attention.")

    show = rq.copy()
    if "company_key" in show.columns:
        show["OEM"] = show["company_key"].map(DISPLAY_NAMES).fillna(show["company_key"])
    if "segment" in show.columns:
        show["Segment"] = show["segment"].map(SEGMENT_LABELS).fillna(show["segment"])

    cols = [
        "OEM", "Segment", "filing_month_year", "total", "domestic", "exports",
        "yoy_pct", "source", "filing_date", "parser_status", "confidence_score",
        "review_note",
    ]
    show = show[[c for c in cols if c in show.columns]]
    rename = {
        "filing_month_year": "Month",
        "total": "Total",
        "domestic": "Domestic",
        "exports": "Exports",
        "yoy_pct": "YoY",
        "source": "Source",
        "filing_date": "Filed",
        "parser_status": "Status",
        "confidence_score": "Confidence",
        "review_note": "Review note",
    }
    show = show.rename(columns=rename)
    st.dataframe(show, use_container_width=True, hide_index=True, height=380)

    C.section_header("Approve / correct an item")

    with st.form("rq_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        oems   = rq["company_key"].unique() if "company_key" in rq.columns else []
        segs   = rq["segment"].unique()      if "segment" in rq.columns else []
        months = rq["filing_month_year"].unique() if "filing_month_year" in rq.columns else []
        a_company = c1.selectbox("Company", oems, format_func=lambda k: DISPLAY_NAMES.get(k, k))
        a_segment = c2.selectbox("Segment", segs, format_func=lambda s: SEGMENT_LABELS.get(s, s))
        a_month   = c3.selectbox("Month",   months)

        c4, c5, c6 = st.columns(3)
        a_total    = c4.number_input("Corrected total (0 = keep original)", min_value=0)
        a_dom      = c5.number_input("Corrected domestic (0 = keep)",       min_value=0)
        a_exp      = c6.number_input("Corrected exports (0 = keep)",        min_value=0)

        a_note = st.text_input("Reviewer note", placeholder="What did you verify?")
        submitted = st.form_submit_button("Approve & move to dataset")
        if submitted:
            ok = approve_review_item(
                a_company, a_segment, a_month,
                corrected_total    = int(a_total) if a_total > 0 else None,
                corrected_domestic = int(a_dom)   if a_dom   > 0 else None,
                corrected_exports  = int(a_exp)   if a_exp   > 0 else None,
                reviewer_note      = a_note,
            )
            if ok:
                st.success("Approved and moved to normalized dataset.")
                st.cache_data.clear()
            else:
                st.error("Approval failed — item not found in queue.")

    csv = rq.to_csv(index=False).encode()
    st.download_button("Download review queue (CSV)", csv,
                       "review_queue.csv", "text/csv")
