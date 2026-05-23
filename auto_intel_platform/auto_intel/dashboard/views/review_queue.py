"""
views/review_queue.py — Reviewer workflow
===========================================
Two sections:
  1. Review queue  — approve/correct rows that failed validation
  2. Manual entry  — enter data directly when scraping fails for an OEM
                     (the essential safety net for JS-rendered IR pages)
"""

from __future__ import annotations
import hashlib
from datetime import datetime, date

import pandas as pd
import streamlit as st

from .. import components as C
from ..data_layer import load_all, DISPLAY_NAMES, SEGMENT_LABELS
from pipeline.store import approve_review_item, load_normalized
from registry import OEM_REGISTRY, get_all_active


# ── helpers ───────────────────────────────────────────────────────────────────

def _all_oem_keys() -> list[str]:
    return sorted(OEM_REGISTRY.keys())


def _month_options() -> list[str]:
    """Last 6 months as YYYY-MM strings, most recent first."""
    from datetime import date
    import pandas as pd
    today = date.today()
    months = []
    for i in range(6):
        d = pd.Timestamp(today) - pd.DateOffset(months=i)
        months.append(d.strftime("%Y-%m"))
    return months


def _save_manual_row(
    company_key: str,
    segment: str,
    filing_month_year: str,
    domestic: int,
    exports: int,
    source_url: str,
    filing_date_str: str,
    reviewer_note: str,
) -> bool:
    """Write a manually entered row straight to normalized.csv."""
    try:
        from pipeline.store import NORM_PATH, load_normalized
        from schema import ParserStatus, ExtractionMethod

        total = domestic + exports
        now   = datetime.utcnow().isoformat() + "Z"
        cfg   = OEM_REGISTRY.get(company_key)
        raw_hash = hashlib.sha1(
            f"MANUAL:{company_key}:{segment}:{filing_month_year}:{total}".encode()
        ).hexdigest()[:16]

        new_row = {
            "company_key":       company_key,
            "display_name":      cfg.display_name if cfg else company_key,
            "segment":           segment,
            "filing_month_year": filing_month_year,
            "domestic":          domestic,
            "exports":           exports,
            "total":             total,
            "yoy_pct":           None,
            "mom_pct":           None,
            "source":            "MANUAL",
            "source_url":        source_url,
            "filing_date":       filing_date_str,
            "parser_version":    "MANUAL_ENTRY_V1",
            "extraction_method": ExtractionMethod.MANUAL,
            "parser_status":     ParserStatus.MANUAL,
            "confidence_score":  1.0,
            "raw_row_hash":      raw_hash,
            "data_vintage":      now,
            "last_updated":      now,
            "review_note":       reviewer_note,
        }

        existing = load_normalized()

        # Remove stale entry if it exists for this PK
        if not existing.empty:
            mask = (
                (existing["company_key"]       == company_key) &
                (existing["segment"]           == segment) &
                (existing["filing_month_year"] == filing_month_year)
            )
            existing = existing[~mask]

        updated = pd.concat([existing, pd.DataFrame([new_row])], ignore_index=True)
        NORM_PATH.parent.mkdir(parents=True, exist_ok=True)
        updated.to_csv(NORM_PATH, index=False)
        return True
    except Exception as e:
        st.error(f"Save failed: {e}")
        return False


# ── main render ───────────────────────────────────────────────────────────────

def render():
    _, _, _, rq = load_all()

    tab_review, tab_manual = st.tabs(["📋 Review Queue", "➕ Enter Data Manually"])

    # ── TAB 1: REVIEW QUEUE ─────────────────────────────────────────────────
    with tab_review:
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
        else:
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
                "filing_month_year": "Month", "total": "Total",
                "domestic": "Domestic", "exports": "Exports", "yoy_pct": "YoY",
                "source": "Source", "filing_date": "Filed",
                "parser_status": "Status", "confidence_score": "Confidence",
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
                a_total = c4.number_input("Corrected total (0 = keep original)", min_value=0)
                a_dom   = c5.number_input("Corrected domestic (0 = keep)",       min_value=0)
                a_exp   = c6.number_input("Corrected exports (0 = keep)",        min_value=0)

                a_note = st.text_input("Reviewer note", placeholder="What did you verify?")
                submitted = st.form_submit_button("✅ Approve & move to dataset")
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

    # ── TAB 2: MANUAL ENTRY ─────────────────────────────────────────────────
    with tab_manual:
        C.section_header(
            "Manual data entry",
            "Use this when the pipeline could not scrape an OEM's IR page. "
            "Look up the OEM's press release, verify the numbers, enter here.",
        )

        # Show which OEMs are missing for latest month
        norm = load_normalized()
        if not norm.empty:
            latest_m = norm["filing_month_year"].max()
            filed = set(norm[norm["filing_month_year"] == latest_m]["company_key"].unique())
            active = {o.key for o in get_all_active()}
            missing = sorted(active - filed)
            if missing:
                names = ", ".join(DISPLAY_NAMES.get(k, k) for k in missing)
                st.warning(
                    f"**{len(missing)} OEM(s) have no data for {latest_m}:** {names}\n\n"
                    "Enter their data below after checking their press release."
                )
            else:
                st.success(f"All active OEMs have data for {latest_m}.")

        st.markdown(
            "<div style='background:#1E293B;border-left:3px solid #F59E0B;"
            "padding:0.75rem 1rem;border-radius:0 6px 6px 0;"
            "font-size:0.83rem;color:#CBD5E1;line-height:1.7;margin-bottom:1rem;'>"
            "<b style='color:#FCD34D;'>How to enter data correctly</b><br>"
            "1. Go to the OEM's official press release (link from their IR page)<br>"
            "2. Find the table with Domestic / Exports / Total wholesales<br>"
            "3. Enter the <b>exact numbers from the press release</b> — do not estimate<br>"
            "4. Paste the press release URL in the Source URL field<br>"
            "5. The system will set status = MANUAL so it is clearly marked as human-verified"
            "</div>",
            unsafe_allow_html=True,
        )

        all_oems = _all_oem_keys()
        all_segs = ["PV", "2W", "3W", "CV", "Tractor", "EV"]
        month_opts = _month_options()

        with st.form("manual_entry_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            oem_key  = col1.selectbox(
                "OEM *", all_oems,
                format_func=lambda k: DISPLAY_NAMES.get(k, k),
            )
            segment  = col2.selectbox("Segment *", all_segs)
            month    = col3.selectbox("Month (sales month) *", month_opts)

            col4, col5 = st.columns(2)
            domestic = col4.number_input("Domestic wholesales *", min_value=0, step=100)
            exports  = col5.number_input("Exports", min_value=0, step=100, value=0)

            total_preview = domestic + exports
            st.info(f"Total = Domestic + Exports = **{C.fmt_indian(total_preview)} units**")

            col6, col7 = st.columns(2)
            filing_date = col6.date_input(
                "Press release date *",
                value=date.today(),
            )
            source_url = col7.text_input(
                "Source URL *",
                placeholder="https://www.maruti.co.in/press-release/april-2025.pdf",
            )

            reviewer_note = st.text_area(
                "Verification note *",
                placeholder="e.g. 'Verified against Maruti press release dated 01-May-2025, "
                            "Table 1 – Wholesale dispatches'",
                height=80,
            )

            save_btn = st.form_submit_button("💾 Save to dataset", type="primary")

            if save_btn:
                errors = []
                if domestic == 0 and exports == 0:
                    errors.append("Domestic and Exports cannot both be zero.")
                if not source_url.strip():
                    errors.append("Source URL is required — paste the press release link.")
                if not reviewer_note.strip():
                    errors.append("Verification note is required.")

                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    ok = _save_manual_row(
                        company_key       = oem_key,
                        segment           = segment,
                        filing_month_year = month,
                        domestic          = int(domestic),
                        exports           = int(exports),
                        source_url        = source_url.strip(),
                        filing_date_str   = filing_date.strftime("%Y-%m-%d"),
                        reviewer_note     = reviewer_note.strip(),
                    )
                    if ok:
                        st.success(
                            f"✅ Saved: {DISPLAY_NAMES.get(oem_key, oem_key)} · "
                            f"{segment} · {month} · "
                            f"{C.fmt_indian(domestic + exports)} units (MANUAL)"
                        )
                        st.cache_data.clear()
