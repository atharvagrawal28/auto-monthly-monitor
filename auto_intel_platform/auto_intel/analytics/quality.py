"""
analytics/quality.py — data quality scoring
=============================================
Every row gets a 0-100 quality score. Every OEM gets a scorecard summarising:
  - coverage    (% of expected months filed)
  - cleanliness (% of stored rows with status=CLEAN)
  - confidence  (mean parser confidence)
  - lineage     (% of rows with PDF URL + filing_date)
  - timeliness  (median days from month-end to filing)

Filing SLA = was the filing posted by OEM's typical_filing_day + 2 days?
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


# ── Per-row quality score ────────────────────────────────────────────────────

def score_row_quality(row: dict | pd.Series) -> int:
    """
    Composite 0-100 score:
        +40  parser_status=CLEAN  (FLAGGED=+25, MANUAL=+35, NEEDS_REVIEW=0)
        +30  confidence_score (×30)
        +10  filing_date present
        +10  source URL / pdf_url present
        +10  domestic + exports ≈ total (within 2%)
    """
    score = 0

    status = str(row.get("parser_status", ""))
    score += {
        "CLEAN":        40,
        "MANUAL":       35,
        "FLAGGED":      25,
        "NEEDS_REVIEW":  0,
        "CONFLICT":      0,
        "STALE":         0,
    }.get(status, 0)

    try:
        conf = float(row.get("confidence_score", 0) or 0)
    except (TypeError, ValueError):
        conf = 0
    score += int(round(conf * 30))

    if str(row.get("filing_date", "")).strip():
        score += 10

    if str(row.get("pdf_url", "") or row.get("source", "")).strip():
        score += 10

    try:
        dom = float(row.get("domestic") or 0)
        exp = float(row.get("exports") or 0)
        tot = float(row.get("total") or 0)
        if tot > 0 and abs((dom + exp) - tot) / tot <= 0.02:
            score += 10
    except (TypeError, ValueError):
        pass

    return min(score, 100)


def add_row_quality(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorised wrapper — adds 'quality_score' column."""
    if df.empty:
        return df
    df = df.copy()
    df["quality_score"] = df.apply(score_row_quality, axis=1)
    return df


# ── OEM-level scorecard ──────────────────────────────────────────────────────

def oem_quality_card(
    df: pd.DataFrame,
    oem_key: str,
    months_window: int = 12,
) -> dict:
    """Aggregate quality scorecard for one OEM over the trailing N months."""
    if df.empty:
        return {"oem": oem_key, "rows": 0}

    oem_df = df[df["company_key"] == oem_key].copy()
    if oem_df.empty:
        return {"oem": oem_key, "rows": 0}

    oem_df["_dt"] = pd.to_datetime(oem_df["filing_month_year"] + "-01")
    cutoff = oem_df["_dt"].max() - pd.DateOffset(months=months_window)
    window = oem_df[oem_df["_dt"] >= cutoff]

    if window.empty:
        return {"oem": oem_key, "rows": 0}

    if "quality_score" not in window.columns:
        window = add_row_quality(window)

    statuses = window["parser_status"].fillna("")
    clean_pct = float((statuses == "CLEAN").mean())
    conf_mean = float(pd.to_numeric(
        window.get("confidence_score", pd.Series(dtype=float)), errors="coerce"
    ).fillna(0).mean())

    return {
        "oem":              oem_key,
        "rows":             int(len(window)),
        "months_covered":   int(window["filing_month_year"].nunique()),
        "clean_pct":        round(clean_pct, 3),
        "mean_confidence":  round(conf_mean, 3),
        "mean_quality":     int(round(window["quality_score"].mean())),
        "needs_review":     int((statuses == "NEEDS_REVIEW").sum()),
        "manual":           int((statuses == "MANUAL").sum()),
        "flagged":          int((statuses == "FLAGGED").sum()),
        "latest_month":     window["filing_month_year"].max(),
    }


# ── Filing SLA ───────────────────────────────────────────────────────────────

def filing_sla(
    row: dict | pd.Series,
    typical_day: int,
    grace_days: int = 2,
) -> dict:
    """
    Was the filing posted on time?

    Args:
        row.filing_month_year (str YYYY-MM): the SALES month
        row.filing_date (str YYYY-MM-DD): when the filing was posted
        typical_day: OEM's typical_filing_day (e.g. 1, 3, 5)
        grace_days: how late before we call it 'LATE'

    Returns dict {status: ON_TIME|LATE|MISSING|UPCOMING, days_late, expected_by}
    """
    sales_month = str(row.get("filing_month_year", ""))
    filing_date = str(row.get("filing_date", "") or "")

    try:
        first_next_month = pd.to_datetime(sales_month + "-01") + pd.DateOffset(months=1)
        expected = first_next_month + pd.Timedelta(days=typical_day - 1)
        cutoff   = expected + pd.Timedelta(days=grace_days)
    except Exception:
        return {"status": "UNKNOWN", "days_late": None, "expected_by": ""}

    expected_str = expected.strftime("%Y-%m-%d")

    if not filing_date or filing_date in ("nan", "NaT"):
        if pd.Timestamp.today() > cutoff:
            return {"status": "MISSING", "days_late": None, "expected_by": expected_str}
        return {"status": "UPCOMING", "days_late": None, "expected_by": expected_str}

    try:
        posted = pd.to_datetime(filing_date)
    except Exception:
        return {"status": "UNKNOWN", "days_late": None, "expected_by": expected_str}

    days_late = (posted - expected).days
    status = "ON_TIME" if days_late <= grace_days else "LATE"
    return {"status": status, "days_late": int(days_late), "expected_by": expected_str}


def filing_sla_summary(
    df: pd.DataFrame,
    oem_registry: dict,
    months_window: int = 12,
) -> pd.DataFrame:
    """
    Compute SLA stats per OEM over the trailing N months.
    Returns one row per OEM with on_time_pct, late_pct, median_days_late.
    """
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["_dt"] = pd.to_datetime(df["filing_month_year"] + "-01")
    cutoff = df["_dt"].max() - pd.DateOffset(months=months_window)
    df = df[df["_dt"] >= cutoff]

    out = []
    for oem_key, oem_df in df.groupby("company_key"):
        oem_cfg = oem_registry.get(oem_key)
        typical_day = getattr(oem_cfg, "typical_filing_day", 5) if oem_cfg else 5
        slas = oem_df.apply(
            lambda r: filing_sla(r, typical_day=typical_day), axis=1
        ).tolist()
        on_time = sum(1 for s in slas if s["status"] == "ON_TIME")
        late    = sum(1 for s in slas if s["status"] == "LATE")
        days_late_vals = [s["days_late"] for s in slas if s["days_late"] is not None]
        out.append({
            "company_key":      oem_key,
            "filings_observed": len(slas),
            "on_time_pct":      round(on_time / max(len(slas), 1), 3),
            "late_pct":         round(late / max(len(slas), 1), 3),
            "median_days_late": float(np.median(days_late_vals)) if days_late_vals else 0.0,
            "typical_day":      typical_day,
        })
    return pd.DataFrame(out).sort_values("on_time_pct", ascending=False)
