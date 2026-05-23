"""
dashboard/data_layer.py — central data loader for the UI
==========================================================
Loads CSVs once via @st.cache_data, applies all derived analytics, and
returns a single enriched DataFrame that every page can rely on.

Keeping this in one place means a page never recomputes share or YoY itself.
"""

from __future__ import annotations
import pandas as pd
import streamlit as st

from pipeline.store import (
    load_normalized, load_granular, load_filing_status, load_review_queue,
)
from analytics import (
    add_market_share, share_delta_mom, share_delta_yoy,
    add_ttm, add_rolling_mean, add_fytd, add_ytd,
    add_z_score, quartile_rank,
)
from analytics.benchmarks import (
    export_mix, segment_mix, beat_miss_vs_trailing,
)
from analytics.quality import add_row_quality


# ── Canonical display names ──────────────────────────────────────────────────
DISPLAY_NAMES = {
    "MARUTI":        "Maruti Suzuki",
    "TATAMOTORS_PV": "Tata Motors — PV",
    "TATAMOTORS_CV": "Tata Motors — CV",
    "MAHINDRA_AUTO": "Mahindra Auto",
    "MAHINDRA_FARM": "Mahindra Farm",
    "BAJAJ":         "Bajaj Auto",
    "HEROMOTOCO":    "Hero MotoCorp",
    "TVS":           "TVS Motor",
    "ASHOKLEY":      "Ashok Leyland",
    "ESCORTS":       "Escorts Kubota",
    "EICHER":        "Eicher (Royal Enfield)",
    "OLA_ELECTRIC":  "Ola Electric",
}

SEGMENT_LABELS = {
    "PV":      "Passenger Vehicles",
    "CV":      "Commercial Vehicles",
    "2W":      "Two-Wheelers",
    "3W":      "Three-Wheelers",
    "Tractor": "Tractors / Farm",
    "EV":      "Electric Vehicles",
}

SEGMENT_UNITS = {
    "PV":      "units",
    "CV":      "units",
    "2W":      "units",
    "3W":      "units",
    "Tractor": "units",
    "EV":      "units",
}


@st.cache_data(ttl=300, show_spinner=False)
def load_all():
    """
    Return (normalized_enriched, granular, filing_status, review_queue).
    The normalized DataFrame already has display_name, market_share_pct,
    TTM totals, rolling means, z-scores, segment mix, FYTD, YTD, etc.
    """
    norm = load_normalized()
    gran = load_granular()
    fs   = load_filing_status()
    rq   = load_review_queue()

    if norm.empty:
        return norm, gran, fs, rq

    # ── Coerce numerics
    for col in ["domestic", "exports", "total"]:
        if col in norm.columns:
            norm[col] = pd.to_numeric(norm[col], errors="coerce")
    for col in ["yoy_pct", "mom_pct", "confidence_score"]:
        if col in norm.columns:
            norm[col] = pd.to_numeric(norm[col], errors="coerce")

    # ── Labels for display
    norm["display_name"]  = norm["company_key"].map(DISPLAY_NAMES).fillna(norm["company_key"])
    norm["segment_label"] = norm["segment"].map(SEGMENT_LABELS).fillna(norm["segment"])
    norm["unit_label"]    = norm["segment"].map(SEGMENT_UNITS).fillna("units")
    norm["_dt"]           = pd.to_datetime(norm["filing_month_year"] + "-01", errors="coerce")

    # ── Layered analytics (order matters)
    norm = export_mix(norm)
    norm = add_market_share(norm)
    norm = share_delta_mom(norm)
    norm = share_delta_yoy(norm)
    norm = add_ttm(norm)
    norm = add_rolling_mean(norm, window=3)
    norm = add_rolling_mean(norm, window=6, out_col="total_r6m")
    norm = add_fytd(norm)
    norm = add_ytd(norm)
    norm = add_z_score(norm)
    norm = quartile_rank(norm)
    norm = segment_mix(norm)
    norm = beat_miss_vs_trailing(norm, window=6)
    norm = add_row_quality(norm)

    # Recompute MoM if missing (some sample rows may not have it)
    if "mom_pct" not in norm.columns or norm["mom_pct"].isna().all():
        norm = norm.sort_values(["company_key", "segment", "filing_month_year"])
        norm["mom_pct"] = (
            norm.groupby(["company_key", "segment"])["total"]
                .pct_change().round(4)
        )

    return norm, gran, fs, rq


def latest_month(norm: pd.DataFrame) -> str | None:
    if norm.empty:
        return None
    return sorted(norm["filing_month_year"].dropna().unique())[-1]


def month_options(norm: pd.DataFrame, n: int | None = None) -> list[str]:
    if norm.empty:
        return []
    months = sorted(norm["filing_month_year"].dropna().unique(), reverse=True)
    return months[:n] if n else months
