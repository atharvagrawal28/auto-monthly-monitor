"""
analytics/rolling.py — time-window aggregations
================================================
TTM (trailing twelve months), YTD (calendar), FYTD (April–March India fiscal),
QoQ (quarterly aggregation), 3M rolling mean, multi-year CAGR.

Every function returns the input DataFrame plus new columns — never mutates.
Inputs must contain: company_key, segment, filing_month_year (YYYY-MM), total.
"""

from __future__ import annotations
import pandas as pd
import numpy as np


# ── Fiscal-year helpers (India: April → March) ───────────────────────────────

def fiscal_year(month_str: str) -> str:
    """'2025-04' → 'FY26'. April is month 1 of new fiscal year."""
    dt = pd.to_datetime(month_str + "-01")
    fy_end = dt.year + 1 if dt.month >= 4 else dt.year
    return f"FY{fy_end % 100:02d}"


def fiscal_quarter(month_str: str) -> str:
    """'2025-07' → 'FY26 Q2'. Apr-Jun=Q1, Jul-Sep=Q2, Oct-Dec=Q3, Jan-Mar=Q4."""
    dt = pd.to_datetime(month_str + "-01")
    fy_end = dt.year + 1 if dt.month >= 4 else dt.year
    m = dt.month
    q = ((m - 4) % 12) // 3 + 1
    return f"FY{fy_end % 100:02d} Q{q}"


# ── Rolling mean ─────────────────────────────────────────────────────────────

def add_rolling_mean(
    df: pd.DataFrame,
    window: int = 3,
    value_col: str = "total",
    group_cols=("company_key", "segment"),
    out_col: str | None = None,
) -> pd.DataFrame:
    """Add a trailing N-month rolling mean inside (oem, segment) groups."""
    if df.empty:
        return df
    out_col = out_col or f"{value_col}_r{window}m"
    df = df.sort_values(list(group_cols) + ["filing_month_year"]).copy()
    df[out_col] = (
        df.groupby(list(group_cols))[value_col]
          .transform(lambda s: s.rolling(window, min_periods=1).mean())
          .round(0)
    )
    return df


# ── TTM (trailing 12 months sum) ─────────────────────────────────────────────

def add_ttm(
    df: pd.DataFrame,
    value_col: str = "total",
    group_cols=("company_key", "segment"),
) -> pd.DataFrame:
    """
    Add ttm_total (trailing 12-month sum) and ttm_yoy_pct
    (TTM vs the previous-year TTM).
    """
    if df.empty:
        return df
    df = df.sort_values(list(group_cols) + ["filing_month_year"]).copy()
    df["ttm_total"] = (
        df.groupby(list(group_cols))[value_col]
          .transform(lambda s: s.rolling(12, min_periods=6).sum())
    )
    df["ttm_total_prev"] = df.groupby(list(group_cols))["ttm_total"].shift(12)
    df["ttm_yoy_pct"] = (
        (df["ttm_total"] - df["ttm_total_prev"]) / df["ttm_total_prev"]
    ).replace([np.inf, -np.inf], np.nan).round(4)
    df = df.drop(columns=["ttm_total_prev"])
    return df


# ── Calendar YTD ─────────────────────────────────────────────────────────────

def add_ytd(
    df: pd.DataFrame,
    value_col: str = "total",
    group_cols=("company_key", "segment"),
) -> pd.DataFrame:
    """Cumulative sum from Jan of the row's calendar year."""
    if df.empty:
        return df
    df = df.copy()
    df["_dt"] = pd.to_datetime(df["filing_month_year"] + "-01")
    df["_cy"] = df["_dt"].dt.year
    df = df.sort_values(list(group_cols) + ["_dt"])
    df["ytd_total"] = (
        df.groupby(list(group_cols) + ["_cy"])[value_col].cumsum()
    )
    df = df.drop(columns=["_dt", "_cy"])
    return df


# ── Fiscal YTD (Apr → Mar) ───────────────────────────────────────────────────

def add_fytd(
    df: pd.DataFrame,
    value_col: str = "total",
    group_cols=("company_key", "segment"),
) -> pd.DataFrame:
    """Cumulative sum from April of the row's fiscal year."""
    if df.empty:
        return df
    df = df.copy()
    df["_dt"] = pd.to_datetime(df["filing_month_year"] + "-01")
    df["_fy"] = df["filing_month_year"].apply(fiscal_year)
    df = df.sort_values(list(group_cols) + ["_dt"])
    df["fytd_total"] = (
        df.groupby(list(group_cols) + ["_fy"])[value_col].cumsum()
    )
    # FYTD YoY: same fiscal-month-position last year
    df["_fy_month_pos"] = ((df["_dt"].dt.month - 4) % 12) + 1
    df["_prior_fy"] = df["_fy"].apply(
        lambda x: f"FY{int(x[2:]) - 1:02d}"
    )
    prior_lookup = df.set_index(
        list(group_cols) + ["_fy", "_fy_month_pos"]
    )["fytd_total"].to_dict()

    def _lookup(row):
        key = (
            *(row[c] for c in group_cols),
            row["_prior_fy"],
            row["_fy_month_pos"],
        )
        return prior_lookup.get(key)

    df["fytd_total_prev"] = df.apply(_lookup, axis=1)
    df["fytd_yoy_pct"] = (
        (df["fytd_total"] - df["fytd_total_prev"]) / df["fytd_total_prev"]
    ).round(4)
    df["fiscal_year"] = df["_fy"]
    df = df.drop(columns=["_dt", "_fy", "_fy_month_pos", "_prior_fy",
                          "fytd_total_prev"])
    return df


# ── Quarterly aggregation ────────────────────────────────────────────────────

def add_qoq(
    df: pd.DataFrame,
    value_col: str = "total",
    group_cols=("company_key", "segment"),
) -> pd.DataFrame:
    """
    Aggregate monthly rows into fiscal quarters and compute QoQ + YoY growth.
    Returns a quarterly DataFrame (not the monthly one).
    """
    if df.empty:
        return df
    work = df.copy()
    work["fq"] = work["filing_month_year"].apply(fiscal_quarter)
    agg = (
        work.groupby(list(group_cols) + ["fq"], as_index=False)
            .agg(total=(value_col, "sum"),
                 domestic=("domestic", "sum"),
                 exports=("exports", "sum"),
                 months_in_q=(value_col, "count"))
    )
    # Sort by fiscal-quarter chronology
    agg["_sort"] = agg["fq"].apply(_fq_sort_key)
    agg = agg.sort_values(list(group_cols) + ["_sort"]).reset_index(drop=True)
    agg["qoq_pct"] = (
        agg.groupby(list(group_cols))["total"].pct_change().round(4)
    )
    agg["yoy_pct"] = (
        agg.groupby(list(group_cols))["total"].pct_change(periods=4).round(4)
    )
    agg = agg.drop(columns=["_sort"])
    return agg


def _fq_sort_key(fq: str) -> int:
    """'FY26 Q2' → 2602  (sortable integer)."""
    try:
        fy = int(fq[2:4])
        q  = int(fq[-1])
        return fy * 100 + q
    except Exception:
        return 0


# ── CAGR ─────────────────────────────────────────────────────────────────────

def compute_cagr(start_value: float, end_value: float, years: float) -> float | None:
    """Compound annual growth rate. Returns None on bad inputs."""
    if not start_value or start_value <= 0 or not end_value or end_value <= 0:
        return None
    if years <= 0:
        return None
    return round((end_value / start_value) ** (1 / years) - 1, 4)
