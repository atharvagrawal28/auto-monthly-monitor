"""
data/generate_sample.py
=======================
Generates 18 months of realistic sample data for all OEMs.
Run this to populate the dashboard before live data is available.
Numbers are based on publicly reported actuals (approximate).
"""

import random
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from schema import ParserStatus, ExtractionMethod, NORMALIZED_COLUMNS, GRANULAR_COLUMNS

random.seed(42)

# ── Base monthly totals (approximate real-world actuals, units) ───────────────
OEM_BASES = {
    "MARUTI":          {"segment": "PV",      "domestic": 150000, "exports": 22000},
    "TATAMOTORS_PV":   {"segment": "PV",      "domestic": 46000,  "exports": 4000},
    "TATAMOTORS_CV":   {"segment": "CV",      "domestic": 35000,  "exports": 3500},
    "MAHINDRA_AUTO":   {"segment": "PV",      "domestic": 38000,  "exports": 6000},
    "MAHINDRA_FARM":   {"segment": "Tractor", "domestic": 28000,  "exports": 4500},
    "BAJAJ":           {"segment": "2W",      "domestic": 180000, "exports": 120000},
    "HEROMOTOCO":      {"segment": "2W",      "domestic": 420000, "exports": 35000},
    "TVS":             {"segment": "2W",      "domestic": 270000, "exports": 110000},
    "ASHOKLEY":        {"segment": "CV",      "domestic": 14000,  "exports": 2000},
    "ESCORTS":         {"segment": "Tractor", "domestic": 7000,   "exports": 1200},
    "EICHER":          {"segment": "2W",      "domestic": 65000,  "exports": 12000},
    "OLA_ELECTRIC":    {"segment": "EV",      "domestic": 28000,  "exports": 0},
}

# ── Seasonal multipliers (month-on-month relative to flat baseline) ───────────
SEASONAL = {
    1:  0.88,   # Jan   — post-festive lull
    2:  0.90,   # Feb
    3:  1.10,   # Mar   — financial year-end push
    4:  0.92,   # Apr
    5:  0.94,   # May
    6:  0.88,   # Jun   — monsoon onset
    7:  0.86,   # Jul   — monsoon peak
    8:  0.87,   # Aug
    9:  1.05,   # Sep   — pre-festive
    10: 1.18,   # Oct   — Navratri/Diwali
    11: 0.95,   # Nov   — post-festive hangover
    12: 0.98,   # Dec
}

DISPLAY_NAMES = {
    "MARUTI":        "Maruti Suzuki",
    "TATAMOTORS_PV": "Tata Motors – PV",
    "TATAMOTORS_CV": "Tata Motors – CV",
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


def generate(months_back: int = 18) -> pd.DataFrame:
    rows = []
    today = datetime.today()

    for m in range(months_back, 0, -1):
        dt      = today - timedelta(days=m * 30)
        month_y = dt.strftime("%Y-%m")
        month_n = dt.month
        year    = dt.year

        # YoY growth trends — industry growing ~12% over period with EV acceleration
        trend_factor = 1.0 + (months_back - m) * 0.008   # 0.8% monthly structural growth
        ev_trend     = 1.0 + (months_back - m) * 0.025   # 2.5% monthly for EV

        for key, base in OEM_BASES.items():
            seasonal   = SEASONAL[month_n]
            noise      = random.uniform(0.95, 1.05)
            is_ev      = base["segment"] == "EV"
            multiplier = (ev_trend if is_ev else trend_factor) * seasonal * noise

            domestic = int(base["domestic"] * multiplier)
            exports  = int(base["exports"]  * multiplier * random.uniform(0.9, 1.1))
            total    = domestic + exports

            # Compute growth vs 12 months prior (simple estimate)
            yoy_base = base["domestic"] + base["exports"]
            yoy_pct  = round((total - yoy_base) / yoy_base, 4) if yoy_base > 0 else None

            filing_date = (dt + timedelta(days=random.randint(1, 5))).strftime("%Y-%m-%d")

            rows.append({
                "company_key":       key,
                "segment":           base["segment"],
                "filing_month_year": month_y,
                "domestic":          domestic,
                "exports":           exports,
                "total":             total,
                "yoy_pct":           yoy_pct,
                "mom_pct":           None,
                "source":            "NSE",
                "filing_date":       filing_date,
                "parser_version":    f"{key}_V1",
                "extraction_method": ExtractionMethod.MANUAL,
                "parser_status":     ParserStatus.CLEAN,
                "confidence_score":  0.95,
                "raw_row_hash":      f"sample_{key}_{month_y}",
                "data_vintage":      datetime.utcnow().isoformat() + "Z",
                "last_updated":      datetime.utcnow().isoformat() + "Z",
                "review_note":       "sample data",
            })

    df = pd.DataFrame(rows)
    # Compute MoM
    df = _compute_mom(df)
    return df


def _compute_mom(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["company_key", "segment", "filing_month_year"])
    df["_dt"] = pd.to_datetime(df["filing_month_year"] + "-01")
    df["mom_pct"] = df.groupby(["company_key", "segment"])["total"].pct_change().round(4)
    df = df.drop(columns=["_dt"])
    return df


def generate_granular(normalized_df: pd.DataFrame) -> pd.DataFrame:
    """Generate sub-segment granular breakdown from normalized data."""
    gran_rows = []

    sub_splits = {
        "PV":      {"UV": 0.52, "Compact": 0.30, "Mini": 0.08, "Sedan": 0.06, "MPV": 0.04},
        "CV":      {"SCV": 0.35, "ICV": 0.20, "MHCV": 0.28, "Bus": 0.17},
        "2W":      {"Motorcycle": 0.65, "Scooter": 0.28, "Moped": 0.04, "EV": 0.03},
        "Tractor": {"Sub30HP": 0.25, "30-40HP": 0.45, "Above40HP": 0.30},
        "EV":      {"Scooter_EV": 0.80, "Motorcycle_EV": 0.20},
    }

    for _, row in normalized_df.iterrows():
        seg   = row["segment"]
        split = sub_splits.get(seg, {"Other": 1.0})
        total = int(row["total"]) if pd.notna(row["total"]) else 0

        for cat, pct in split.items():
            units = int(total * pct * random.uniform(0.97, 1.03))
            gran_rows.append({
                "company_key":          row["company_key"],
                "segment":              seg,
                "filing_month_year":    row["filing_month_year"],
                "raw_category":         cat,
                "normalized_category":  cat,
                "units":                units,
                "is_export":            False,
                "notes":                "sample",
            })

    return pd.DataFrame(gran_rows)


def generate_filing_status(normalized_df: pd.DataFrame) -> pd.DataFrame:
    """Generate filing status table from normalized data."""
    from schema import FILING_STATUS_COLUMNS
    rows = []
    for _, row in normalized_df.iterrows():
        rows.append({
            "company_key":       row["company_key"],
            "filing_month_year": row["filing_month_year"],
            "status":            ParserStatus.CLEAN,
            "filing_date":       row["filing_date"],
            "expected_by":       "",
            "pdf_url":           "",
            "notes":             "sample data",
            "last_checked":      datetime.utcnow().isoformat() + "Z",
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    out_dir = ROOT / "data"
    out_dir.mkdir(exist_ok=True)

    print("Generating sample normalized data...")
    norm_df = generate(months_back=18)
    norm_df.to_csv(out_dir / "normalized.csv", index=False)
    print(f"  → {len(norm_df)} rows → data/normalized.csv")

    print("Generating granular breakdown...")
    gran_df = generate_granular(norm_df)
    gran_df.to_csv(out_dir / "granular.csv", index=False)
    print(f"  → {len(gran_df)} rows → data/granular.csv")

    print("Generating filing status...")
    status_df = generate_filing_status(norm_df)
    status_df.to_csv(out_dir / "filing_status.csv", index=False)
    print(f"  → {len(status_df)} rows → data/filing_status.csv")

    print("\nSample data generation complete.")
    print("Run: streamlit run dashboard/app.py")
