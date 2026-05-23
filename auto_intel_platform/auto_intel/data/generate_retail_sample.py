"""
data/generate_retail_sample.py — Retail Sample Data Generator
==============================================================
Generates data/retail.csv with 24 months of realistic FADA-style
retail registration data for India.

Kept COMPLETELY SEPARATE from generate_sample.py (wholesale).
Retail numbers are segment-level only (matching FADA reporting format),
slightly below wholesale to reflect natural dealer inventory dynamics.

Seasonal patterns:
  - Festive months (Oct, Nov): retail > wholesale (dealers draw down stock)
  - Slow months (Jun, Jul, Aug): wholesale > retail (stock builds up)
  - Q1 fiscal (Apr–Jun): summer slowdown
  - Jan–Mar: year-end push (retail spikes to clear stock before fiscal close)
"""

from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

OUTPUT_FILE = Path(__file__).parent / "retail.csv"

MONTHS_BACK = 24

# Base monthly retail volumes by segment (realistic India FY25-26 levels)
# These are segment totals across all dealers/OEMs — as FADA reports them.
# Retail base is set ~8-12% BELOW wholesale so channel inventory stays positive
# (dealers always hold some stock). Festive months pull it close to wholesale.
# Wholesale monthly approx: PV=280k, 2W=1135k, 3W=132k, CV=69k, Tractor=50k, EV=58k
SEGMENT_BASE = {
    "PV":      248_000,    # ~11% below wholesale PV
    "2W":    1_020_000,    # ~10% below wholesale 2W
    "3W":       112_000,   # ~15% below wholesale 3W
    "CV":        60_000,   # ~13% below wholesale CV
    "Tractor":   43_000,   # ~14% below wholesale Tractor
    "EV":        38_000,   # ~35% below — EV registration has longest lag
}

# Month-by-month seasonal multiplier for retail (1.0 = base)
# Retail is smoother than wholesale but has the same festive peak
SEASONAL_RETAIL = {
    1:  1.02,   # Jan — year-end push, fiscal close
    2:  0.94,   # Feb — quieter post-January
    3:  1.05,   # Mar — fiscal year-end registration rush
    4:  0.89,   # Apr — post-fiscal dip, summer starts
    5:  0.88,   # May — summer slowdown
    6:  0.84,   # Jun — monsoon onset, weakest month
    7:  0.87,   # Jul — monsoon, dealers cautious
    8:  0.93,   # Aug — pre-festive stocking
    9:  0.98,   # Sep — festive season begins
    10: 1.20,   # Oct — Navratri / Diwali, peak retail
    11: 1.15,   # Nov — post-Diwali carry through
    12: 1.05,   # Dec — year-end
}

# Tractor seasonality — agricultural, different from PV/2W
SEASONAL_TRACTOR = {
    1:  1.05,
    2:  1.10,
    3:  1.18,   # Rabi harvest, high liquidity
    4:  1.08,
    5:  0.95,
    6:  1.10,   # Kharif sowing
    7:  1.15,
    8:  0.90,
    9:  0.85,
    10: 0.92,
    11: 1.00,
    12: 0.92,
}

# EV growth trend — retail registration lags wholesale by ~2-3 weeks
# so EV retail grows a bit slower than EV wholesale
EV_TREND_PCT = 0.014     # +1.4%/month structural growth
ICE_TREND_PCT = 0.004    # +0.4%/month for non-EV segments


def _generate_months() -> list[str]:
    today = datetime.today().replace(day=1)
    months = []
    for i in range(MONTHS_BACK - 1, -1, -1):
        dt = today - timedelta(days=i * 30)
        months.append(dt.strftime("%Y-%m"))
    return months


def _retail_volume(segment: str, month_str: str, idx: int) -> int:
    """Generate a realistic retail registration count for a given segment/month."""
    base = SEGMENT_BASE[segment]
    month_num = int(month_str.split("-")[1])

    if segment == "Tractor":
        seasonal = SEASONAL_TRACTOR[month_num]
        trend    = (1 + ICE_TREND_PCT) ** idx
    elif segment == "EV":
        seasonal = SEASONAL_RETAIL[month_num]
        trend    = (1 + EV_TREND_PCT) ** idx
    else:
        seasonal = SEASONAL_RETAIL[month_num]
        trend    = (1 + ICE_TREND_PCT) ** idx

    # Random noise ±4% (retail is smoother than wholesale)
    noise = random.uniform(0.96, 1.04)
    return max(100, int(base * seasonal * trend * noise))


def _yoy(segment: str, values: dict[str, int], month_str: str) -> float | None:
    """Compute YoY % for retail if prior year data is available."""
    try:
        yr, mo = month_str.split("-")
        prior = f"{int(yr)-1}-{mo}"
        if prior in values:
            this  = values[month_str]
            prev  = values[prior]
            return round((this - prev) / prev, 4) if prev else None
    except Exception:
        pass
    return None


def main():
    months   = _generate_months()
    segments = list(SEGMENT_BASE.keys())

    # Pre-compute all values so we can compute YoY
    volume_grid: dict[str, dict[str, int]] = {seg: {} for seg in segments}
    for idx, month in enumerate(months):
        for seg in segments:
            volume_grid[seg][month] = _retail_volume(seg, month, idx)

    rows = []
    for month in months:
        # Simulate FADA filing date — usually 1st–5th of following month
        yr, mo = month.split("-")
        next_month = datetime(int(yr), int(mo), 1) + timedelta(days=32)
        filing_day = random.randint(1, 5)
        filing_date = next_month.replace(day=filing_day).strftime("%Y-%m-%d")

        for seg in segments:
            total  = volume_grid[seg][month]
            yoy    = _yoy(seg, volume_grid[seg], month)
            rows.append({
                "filing_month_year": month,
                "segment":           seg,
                "retail_total":      total,
                "yoy_pct":           yoy if yoy is not None else "",
                "source":            "FADA",
                "filing_date":       filing_date,
                "source_url":        "https://fada.in/media-press-releases/",
                "notes":             "",
            })

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "filing_month_year", "segment", "retail_total", "yoy_pct",
        "source", "filing_date", "source_url", "notes",
    ]
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    total_rows = len(rows)
    print(f"Retail sample data generated:")
    print(f"  -> {total_rows} rows -> data/retail.csv ({len(segments)} segments, {len(months)} months)")
    print(f"  Segments: {', '.join(segments)}")
    print(f"  Period:   {months[0]} to {months[-1]}")
    print(f"\nRun: streamlit run dashboard/app.py")


if __name__ == "__main__":
    main()
