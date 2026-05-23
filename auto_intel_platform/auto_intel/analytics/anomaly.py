"""
analytics/anomaly.py — anomaly detection
==========================================
Two complementary checks:
  1. z-score vs OEM's own trailing 12 months (catches one-OEM outliers)
  2. divergence from industry growth (catches OEMs swimming against the tide)

Both run on the normalized DataFrame after rolling stats are attached.
"""

from __future__ import annotations
import pandas as pd
import numpy as np


def add_z_score(
    df: pd.DataFrame,
    value_col: str = "total",
    window: int = 12,
    out_col: str = "z_score_t12m",
) -> pd.DataFrame:
    """
    Z-score of the current value vs the OEM's prior 12 months (excluding self).
    NaN until the OEM has at least 6 prior months.
    """
    if df.empty:
        return df
    df = df.sort_values(
        ["company_key", "segment", "filing_month_year"]
    ).copy()

    def _zs(s: pd.Series) -> pd.Series:
        # rolling mean/std over the *previous* `window` values (exclude current)
        mean = s.shift(1).rolling(window, min_periods=6).mean()
        std  = s.shift(1).rolling(window, min_periods=6).std()
        with np.errstate(divide="ignore", invalid="ignore"):
            return ((s - mean) / std).round(2)

    df[out_col] = (
        df.groupby(["company_key", "segment"])[value_col].transform(_zs)
    )
    return df


def flag_anomalies(
    df: pd.DataFrame,
    z_col: str = "z_score_t12m",
    threshold: float = 2.5,
) -> pd.DataFrame:
    """Return rows whose |z-score| exceeds threshold."""
    if df.empty or z_col not in df.columns:
        return df.iloc[0:0]
    return df[df[z_col].abs() >= threshold].copy()


def industry_vs_oem_divergence(
    df: pd.DataFrame,
    yoy_col: str = "yoy_pct",
    spread_threshold_pp: float = 20.0,
) -> pd.DataFrame:
    """
    For each (segment, month), compute the industry mean YoY, then flag OEMs
    whose YoY diverges from it by more than spread_threshold_pp (percentage
    points). Returns the divergent rows with a 'divergence_pp' column.
    """
    if df.empty or yoy_col not in df.columns:
        return df.iloc[0:0]
    df = df.copy()
    df["_industry_yoy"] = df.groupby(
        ["segment", "filing_month_year"]
    )[yoy_col].transform("median")
    df["divergence_pp"] = ((df[yoy_col] - df["_industry_yoy"]) * 100).round(2)
    out = df[df["divergence_pp"].abs() >= spread_threshold_pp].copy()
    return out.drop(columns=["_industry_yoy"], errors="ignore")
