"""
analytics/share.py — market share and concentration
=====================================================
Share = OEM_total / industry_total, computed inside each (segment, month).
Share delta is reported in percentage points (pp), not relative %.
HHI = Σ share² (Herfindahl-Hirschman) — measures industry concentration.
"""

from __future__ import annotations
import pandas as pd
import numpy as np


def add_market_share(
    df: pd.DataFrame,
    value_col: str = "total",
) -> pd.DataFrame:
    """
    Add market_share_pct (0..1) per row inside its (segment, month) cohort.
    """
    if df.empty:
        return df
    df = df.copy()
    industry = (
        df.groupby(["segment", "filing_month_year"])[value_col]
          .transform("sum")
    )
    df["industry_total"] = industry
    df["market_share_pct"] = np.where(
        industry > 0, df[value_col] / industry, np.nan
    )
    df["market_share_pct"] = df["market_share_pct"].round(4)
    return df


def share_delta_mom(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add market_share_delta_mom_pp — MoM change in market share, in percentage
    points (i.e. 18.4% → 19.1% is +0.7 pp, NOT +3.8%).
    """
    if df.empty or "market_share_pct" not in df.columns:
        return df
    df = df.sort_values(
        ["company_key", "segment", "filing_month_year"]
    ).copy()
    df["market_share_delta_mom_pp"] = (
        df.groupby(["company_key", "segment"])["market_share_pct"]
          .diff()
          .mul(100)
          .round(2)
    )
    return df


def share_delta_yoy(df: pd.DataFrame) -> pd.DataFrame:
    """Same as MoM but vs same month a year ago."""
    if df.empty or "market_share_pct" not in df.columns:
        return df
    df = df.sort_values(
        ["company_key", "segment", "filing_month_year"]
    ).copy()
    df["market_share_delta_yoy_pp"] = (
        df.groupby(["company_key", "segment"])["market_share_pct"]
          .diff(periods=12)
          .mul(100)
          .round(2)
    )
    return df


# ── HHI (concentration) ──────────────────────────────────────────────────────

def hhi(shares: pd.Series) -> float:
    """
    Herfindahl-Hirschman Index. Pass shares as fractions (0..1).
    Returns value scaled 0..10,000 (industry standard).
        <1,000  : low concentration
        1,000-1,800 : moderate
        >1,800 : high
    """
    shares = shares.dropna()
    if shares.empty:
        return float("nan")
    return float(((shares * 100) ** 2).sum().round(1))


def industry_concentration(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute HHI by (segment, month). Requires market_share_pct present.
    Returns long-form DataFrame: segment, filing_month_year, hhi, top3_share.
    """
    if df.empty or "market_share_pct" not in df.columns:
        return pd.DataFrame(columns=["segment", "filing_month_year",
                                     "hhi", "top3_share"])
    rows = []
    for (seg, month), g in df.groupby(["segment", "filing_month_year"]):
        shares = g["market_share_pct"].dropna()
        if shares.empty:
            continue
        top3 = shares.nlargest(3).sum()
        rows.append({
            "segment": seg,
            "filing_month_year": month,
            "hhi": hhi(shares),
            "top3_share": round(float(top3), 4),
            "oem_count": int(len(shares)),
        })
    return pd.DataFrame(rows).sort_values(
        ["segment", "filing_month_year"]
    ).reset_index(drop=True)
