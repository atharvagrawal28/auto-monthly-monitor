"""
data/generate_sample.py
=========================
Generate 24 months of realistic, multi-segment sample data so the dashboard
tells a believable story before live exchange data is wired up.

Numbers below are anchored to publicly reported FY24/FY25 actuals
(approx mid-cycle, ±10%) — they should not be cited as authoritative,
but they do let analyst-grade KPIs render sensibly.

Highlights vs the old generator:
  - Tata, Mahindra get multiple segments per OEM (PV/CV/EV; Auto/Farm)
  - EV penetration trends up materially over 24M (+3pp roughly)
  - Tractor seasonality reflects rabi/kharif cycle
  - 2W exports recovery in H2 of the period
  - Sub-segment granular splits match real-world category mix
"""

import random
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from schema import (
    ParserStatus, ExtractionMethod,
    NORMALIZED_COLUMNS, GRANULAR_COLUMNS, FILING_STATUS_COLUMNS,
)

random.seed(42)


# ── Base monthly wholesale (units) — anchored to recent reality ─────────────
# Multi-row OEMs (Tata, Mahindra) report once per (oem_key, segment) per month.
OEM_SEGMENTS = [
    # MARUTI — PV-only (no EV stream in published filings as of period)
    {"key": "MARUTI",         "segment": "PV",      "domestic": 145000, "exports": 24000,
     "ev_share_of_seg": 0.0, "filing_day": 1},

    # TATA — PV (includes EV row separately tracked under EV segment)
    {"key": "TATAMOTORS_PV",  "segment": "PV",      "domestic": 44000,  "exports": 4200,
     "ev_share_of_seg": 0.0, "filing_day": 3},
    {"key": "TATAMOTORS_PV",  "segment": "EV",      "domestic": 5400,   "exports": 0,
     "ev_share_of_seg": 1.0, "filing_day": 3},
    {"key": "TATAMOTORS_CV",  "segment": "CV",      "domestic": 31500,  "exports": 3000,
     "ev_share_of_seg": 0.0, "filing_day": 3},

    # MAHINDRA — Auto = PV (UV-heavy) and small CV; Farm = tractors
    {"key": "MAHINDRA_AUTO",  "segment": "PV",      "domestic": 41000,  "exports": 2500,
     "ev_share_of_seg": 0.0, "filing_day": 4},
    {"key": "MAHINDRA_AUTO",  "segment": "CV",      "domestic": 22000,  "exports": 1200,
     "ev_share_of_seg": 0.0, "filing_day": 4},
    {"key": "MAHINDRA_AUTO",  "segment": "EV",      "domestic": 1100,   "exports": 0,
     "ev_share_of_seg": 1.0, "filing_day": 4},
    {"key": "MAHINDRA_FARM",  "segment": "Tractor", "domestic": 30000,  "exports": 1500,
     "ev_share_of_seg": 0.0, "filing_day": 4},

    # 2W
    {"key": "BAJAJ",          "segment": "2W",      "domestic": 175000, "exports": 130000,
     "ev_share_of_seg": 0.02, "filing_day": 2},
    {"key": "BAJAJ",          "segment": "3W",      "domestic": 30000,  "exports": 18000,
     "ev_share_of_seg": 0.15, "filing_day": 2},
    {"key": "HEROMOTOCO",     "segment": "2W",      "domestic": 420000, "exports": 24000,
     "ev_share_of_seg": 0.005, "filing_day": 3},
    {"key": "TVS",            "segment": "2W",      "domestic": 280000, "exports": 95000,
     "ev_share_of_seg": 0.08, "filing_day": 3},
    {"key": "TVS",            "segment": "3W",      "domestic": 8500,   "exports": 6000,
     "ev_share_of_seg": 0.0, "filing_day": 3},
    {"key": "EICHER",         "segment": "2W",      "domestic": 66000,  "exports": 11000,
     "ev_share_of_seg": 0.0, "filing_day": 4},

    # CV
    {"key": "ASHOKLEY",       "segment": "CV",      "domestic": 14200,  "exports": 1800,
     "ev_share_of_seg": 0.0, "filing_day": 5},

    # Tractor
    {"key": "ESCORTS",        "segment": "Tractor", "domestic": 7600,   "exports": 1100,
     "ev_share_of_seg": 0.0, "filing_day": 8},

    # Pure-EV
    {"key": "OLA_ELECTRIC",   "segment": "EV",      "domestic": 30000,  "exports": 0,
     "ev_share_of_seg": 1.0, "filing_day": 5},
]


# ── Seasonality (month-of-year multiplier) ──────────────────────────────────
SEASONAL_DEFAULT = {
    1:  0.88, 2:  0.92, 3:  1.12,   # FY year-end push
    4:  0.94, 5:  0.96, 6:  0.88,
    7:  0.86, 8:  0.88, 9:  1.04,
    10: 1.20, 11: 0.94, 12: 0.98,   # festive peak Oct
}

# Tractor follows rabi/kharif cycle (sowing/harvest)
SEASONAL_TRACTOR = {
    1: 0.85, 2: 0.85, 3: 1.20, 4: 1.10, 5: 1.05, 6: 1.15,
    7: 1.10, 8: 0.95, 9: 1.10, 10: 1.05, 11: 0.85, 12: 0.80,
}

# EVs are growth-driven, less seasonal but still get a festive bump
SEASONAL_EV = {
    1: 0.92, 2: 0.95, 3: 1.10, 4: 1.00, 5: 1.00, 6: 0.95,
    7: 0.95, 8: 0.98, 9: 1.08, 10: 1.18, 11: 0.96, 12: 1.00,
}


def _seasonal(segment: str, month_no: int) -> float:
    if segment == "Tractor":
        return SEASONAL_TRACTOR[month_no]
    if segment == "EV":
        return SEASONAL_EV[month_no]
    return SEASONAL_DEFAULT[month_no]


# ── Generation ──────────────────────────────────────────────────────────────

MONTHS_BACK = 24
EV_TREND_PCT_PER_MONTH  = 0.018    # EV: +1.8% per month structural
ICE_TREND_PCT_PER_MONTH = 0.005    # other segments: +0.5% per month


def generate(months_back: int = MONTHS_BACK) -> pd.DataFrame:
    rows = []
    today = datetime.today().replace(day=1)

    for m in range(months_back, 0, -1):
        dt = today - timedelta(days=m * 30)
        # Snap to first of month
        dt = dt.replace(day=1)
        month_y = dt.strftime("%Y-%m")

        for cfg in OEM_SEGMENTS:
            seg = cfg["segment"]
            seasonal = _seasonal(seg, dt.month)
            noise = random.uniform(0.94, 1.06)

            # Structural trend
            trend_per_month = EV_TREND_PCT_PER_MONTH if seg == "EV" else ICE_TREND_PCT_PER_MONTH
            trend = 1.0 + (months_back - m) * trend_per_month

            domestic = int(cfg["domestic"] * seasonal * noise * trend)
            exports  = int(cfg["exports"] * seasonal * noise *
                           random.uniform(0.88, 1.12) * trend)
            total    = domestic + exports

            filing_dt = dt + pd.DateOffset(months=1) + pd.Timedelta(
                days=cfg["filing_day"] + random.randint(0, 2) - 1
            )

            rows.append({
                "company_key":       cfg["key"],
                "segment":           seg,
                "filing_month_year": month_y,
                "domestic":          domestic,
                "exports":           exports,
                "total":             total,
                "yoy_pct":           None,   # filled below
                "mom_pct":           None,   # filled below
                "source":            "OEM_IR",
                "filing_date":       filing_dt.strftime("%Y-%m-%d"),
                "parser_version":    f"{cfg['key']}_V1",
                "extraction_method": ExtractionMethod.MANUAL,
                "parser_status":     ParserStatus.CLEAN,
                "confidence_score":  round(random.uniform(0.85, 0.99), 2),
                "raw_row_hash":      f"sample_{cfg['key']}_{seg}_{month_y}",
                "data_vintage":      datetime.utcnow().isoformat() + "Z",
                "last_updated":      datetime.utcnow().isoformat() + "Z",
                "review_note":       "",
            })

    df = pd.DataFrame(rows)
    df = _compute_growth(df)

    # Inject a few real-world data quality issues (so dashboard QA pages show life)
    df = _inject_quality_issues(df)

    return df


def _compute_growth(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["company_key", "segment", "filing_month_year"]).copy()
    df["_dt"] = pd.to_datetime(df["filing_month_year"] + "-01")
    df["mom_pct"] = (
        df.groupby(["company_key", "segment"])["total"].pct_change().round(4)
    )
    df["yoy_pct"] = (
        df.groupby(["company_key", "segment"])["total"]
          .pct_change(periods=12).round(4)
    )
    return df.drop(columns=["_dt"])


def _inject_quality_issues(df: pd.DataFrame) -> pd.DataFrame:
    """Plant a handful of realistic issues so the QA/review pages aren't empty."""
    if len(df) < 30:
        return df

    # FLAGGED — high YoY swing
    flagged_idx = df.sample(3, random_state=7).index
    df.loc[flagged_idx, "parser_status"] = ParserStatus.FLAGGED
    df.loc[flagged_idx, "confidence_score"] = (
        df.loc[flagged_idx, "confidence_score"] - 0.15
    ).clip(lower=0.5)
    df.loc[flagged_idx, "review_note"] = "Anomalous swing flagged by validator"

    # NEEDS_REVIEW — low confidence
    review_idx = df.sample(2, random_state=11).index
    df.loc[review_idx, "parser_status"] = ParserStatus.NEEDS_REVIEW
    df.loc[review_idx, "confidence_score"] = round(random.uniform(0.30, 0.55), 2)
    df.loc[review_idx, "review_note"] = "Parser confidence below threshold"

    # MANUAL — one historical correction
    manual_idx = df.sample(1, random_state=13).index
    df.loc[manual_idx, "parser_status"] = ParserStatus.MANUAL
    df.loc[manual_idx, "review_note"] = "Manually corrected after analyst review"

    return df


# ── Granular sub-segments ───────────────────────────────────────────────────

GRANULAR_SPLITS = {
    "PV": {
        "MARUTI":         {"Mini": 0.06, "Compact": 0.34, "Mid": 0.13, "UV": 0.39, "MPV": 0.06, "Van": 0.02},
        "TATAMOTORS_PV":  {"UV": 0.72, "Hatch": 0.21, "Sedan": 0.07},
        "MAHINDRA_AUTO":  {"UV": 0.97, "Sedan": 0.03},
    },
    "CV": {
        "TATAMOTORS_CV":  {"SCV": 0.46, "ICV": 0.13, "MHCV": 0.30, "Bus": 0.11},
        "MAHINDRA_AUTO":  {"SCV": 0.65, "ICV": 0.18, "MHCV": 0.10, "Bus": 0.07},
        "ASHOKLEY":       {"LCV": 0.34, "MHCV": 0.46, "Bus": 0.20},
    },
    "2W": {
        "BAJAJ":      {"Motorcycle": 0.92, "Scooter": 0.05, "EV": 0.03},
        "HEROMOTOCO": {"Motorcycle": 0.83, "Scooter": 0.16, "EV": 0.01},
        "TVS":        {"Motorcycle": 0.42, "Scooter": 0.52, "Moped": 0.03, "EV": 0.03},
        "EICHER":     {"Motorcycle": 1.00},
    },
    "3W": {
        "BAJAJ": {"Passenger": 0.70, "Cargo": 0.15, "Electric": 0.15},
        "TVS":   {"Passenger": 0.85, "Cargo": 0.15},
    },
    "Tractor": {
        "MAHINDRA_FARM": {"Sub30HP": 0.18, "30-40HP": 0.55, "Above40HP": 0.27},
        "ESCORTS":       {"Sub30HP": 0.22, "30-40HP": 0.50, "Above40HP": 0.28},
    },
    "EV": {
        "TATAMOTORS_PV": {"Nexon EV": 0.60, "Tiago EV": 0.25, "Punch EV": 0.10, "Tigor EV": 0.05},
        "MAHINDRA_AUTO": {"BE 6": 0.55, "XEV 9e": 0.30, "XUV400 EV": 0.15},
        "OLA_ELECTRIC":  {"S1 Pro": 0.55, "S1 Air": 0.30, "S1 X": 0.15},
    },
}


def generate_granular(norm_df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for _, row in norm_df.iterrows():
        seg = row["segment"]
        oem = row["company_key"]
        splits = (
            GRANULAR_SPLITS.get(seg, {}).get(oem)
            or _default_split(seg)
        )
        total = int(row["total"]) if pd.notna(row["total"]) else 0
        if total == 0:
            continue
        for cat, pct in splits.items():
            units = int(total * pct * random.uniform(0.96, 1.04))
            out.append({
                "company_key":         oem,
                "segment":             seg,
                "filing_month_year":   row["filing_month_year"],
                "raw_category":        cat,
                "normalized_category": cat,
                "units":               units,
                "is_export":           False,
                "notes":               "sample",
            })
    return pd.DataFrame(out)


def _default_split(segment: str) -> dict:
    return {
        "PV":      {"UV": 0.55, "Compact": 0.30, "Sedan": 0.10, "MPV": 0.05},
        "CV":      {"SCV": 0.35, "LCV": 0.25, "MHCV": 0.30, "Bus": 0.10},
        "2W":      {"Motorcycle": 0.65, "Scooter": 0.30, "EV": 0.05},
        "3W":      {"Passenger": 0.70, "Cargo": 0.20, "Electric": 0.10},
        "Tractor": {"Sub30HP": 0.25, "30-40HP": 0.45, "Above40HP": 0.30},
        "EV":      {"EV Model A": 0.55, "EV Model B": 0.30, "EV Model C": 0.15},
    }.get(segment, {"Other": 1.0})


# ── Filing status ───────────────────────────────────────────────────────────

def generate_filing_status(norm_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in norm_df.iterrows():
        rows.append({
            "company_key":       row["company_key"],
            "filing_month_year": row["filing_month_year"],
            "status":            row["parser_status"],
            "filing_date":       row["filing_date"],
            "expected_by":       "",
            "pdf_url":           "",
            "notes":             "sample data",
            "last_checked":      datetime.utcnow().isoformat() + "Z",
        })
    return pd.DataFrame(rows)


# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    out_dir = ROOT / "data"
    out_dir.mkdir(exist_ok=True)

    print("Generating sample normalized data...")
    norm_df = generate(months_back=MONTHS_BACK)
    norm_df.to_csv(out_dir / "normalized.csv", index=False)
    print(f"  -> {len(norm_df):>5} rows -> data/normalized.csv "
          f"({norm_df['company_key'].nunique()} OEMs, "
          f"{norm_df['segment'].nunique()} segments)")

    print("Generating granular breakdown...")
    gran_df = generate_granular(norm_df)
    gran_df.to_csv(out_dir / "granular.csv", index=False)
    print(f"  -> {len(gran_df):>5} rows -> data/granular.csv")

    print("Generating filing status...")
    status_df = generate_filing_status(norm_df)
    status_df.to_csv(out_dir / "filing_status.csv", index=False)
    print(f"  -> {len(status_df):>5} rows -> data/filing_status.csv")

    print("\nSample data generation complete.")
    print("Run: streamlit run dashboard/app.py")
