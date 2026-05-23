"""
analytics/benchmarks.py — cross-OEM and industry-level metrics
================================================================
Quartile rank within a segment-month, EV penetration, export mix,
beat/miss vs trailing N-month average, segment-mix shift,
industry growth bridge (decomposes industry growth into OEM contributions).
"""

from __future__ import annotations
import pandas as pd
import numpy as np


def quartile_rank(
    df: pd.DataFrame,
    metric: str = "total",
) -> pd.DataFrame:
    """
    Add `quartile_in_segment` (Q1=top 25%, Q4=bottom 25%) per (segment, month).
    """
    if df.empty:
        return df
    df = df.copy()

    def _q(s: pd.Series) -> pd.Series:
        if s.dropna().empty:
            return pd.Series([np.nan] * len(s), index=s.index)
        ranked = s.rank(method="min", ascending=False)
        n = ranked.notna().sum()
        if n < 4:
            return pd.Series([1] * len(s), index=s.index)
        return ((ranked - 1) // np.ceil(n / 4)).clip(0, 3).add(1)

    df["quartile_in_segment"] = (
        df.groupby(["segment", "filing_month_year"])[metric].transform(_q)
    )
    return df


def ev_penetration(df: pd.DataFrame) -> pd.DataFrame:
    """
    Industry-wide EV penetration: EV total / (EV + ICE comparable segments).
    Returns DataFrame indexed by month with columns:
        ev_total, comparable_total, ev_pct_of_comparable
    'Comparable' = PV + 2W + 3W + CV (the segments where EVs compete with ICE).
    """
    if df.empty:
        return pd.DataFrame()
    work = df.copy()
    work["total"] = pd.to_numeric(work["total"], errors="coerce")

    comp_segments = {"PV", "2W", "3W", "CV", "EV"}
    work = work[work["segment"].isin(comp_segments)]

    by_month_seg = (
        work.groupby(["filing_month_year", "segment"])["total"]
            .sum()
            .unstack(fill_value=0)
    )

    ev = by_month_seg.get("EV", pd.Series(0, index=by_month_seg.index))
    other = by_month_seg.drop(columns=[c for c in ["EV"]
                                       if c in by_month_seg.columns]).sum(axis=1)
    denom = ev + other

    out = pd.DataFrame({
        "ev_total":             ev.astype(int),
        "comparable_total":     denom.astype(int),
        "ev_pct_of_comparable": (ev / denom.replace(0, np.nan)).round(4),
    }).reset_index()
    return out


def export_mix(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-row export_mix_pct = exports / total. Also industry-wide export mix
    by month/segment.
    """
    if df.empty:
        return df
    df = df.copy()
    df["export_mix_pct"] = (
        pd.to_numeric(df["exports"], errors="coerce")
        / pd.to_numeric(df["total"], errors="coerce").replace(0, np.nan)
    ).round(4)
    return df


def segment_mix(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each (oem, month), share of total units coming from each segment.
    Useful for spotting an OEM rotating its mix (e.g. Tata growing PV vs CV).
    """
    if df.empty:
        return df
    df = df.copy()
    df["_oem_month_total"] = (
        df.groupby(["company_key", "filing_month_year"])["total"].transform("sum")
    )
    df["segment_mix_pct"] = (
        df["total"] / df["_oem_month_total"].replace(0, np.nan)
    ).round(4)
    return df.drop(columns=["_oem_month_total"])


def beat_miss_vs_trailing(
    df: pd.DataFrame,
    window: int = 6,
) -> pd.DataFrame:
    """
    Each row's `beat_miss_pct` = (this_month - trailing_avg) / trailing_avg.
    A simple "did this month beat or miss the recent run-rate?".
    """
    if df.empty:
        return df
    df = df.sort_values(["company_key", "segment", "filing_month_year"]).copy()
    trailing = (
        df.groupby(["company_key", "segment"])["total"]
          .transform(lambda s: s.shift(1).rolling(window, min_periods=3).mean())
    )
    df["beat_miss_pct"] = (
        (df["total"] - trailing) / trailing.replace(0, np.nan)
    ).round(4)
    return df


def growth_bridge(
    df: pd.DataFrame,
    segment: str,
    month: str,
    prior_month: str,
) -> pd.DataFrame:
    """
    Decompose industry growth (segment, prior_month → month) into per-OEM
    contributions (in absolute units AND as % of total industry change).
    Useful: "Industry grew 8% — Maruti contributed 4.1pp, Tata 1.8pp, ..."
    """
    cur  = df[(df["segment"] == segment) & (df["filing_month_year"] == month)]
    prev = df[(df["segment"] == segment) & (df["filing_month_year"] == prior_month)]
    if cur.empty or prev.empty:
        return pd.DataFrame()

    merged = cur[["company_key", "total"]].merge(
        prev[["company_key", "total"]],
        on="company_key", how="outer", suffixes=("_cur", "_prev"),
    ).fillna(0)
    merged["delta"] = merged["total_cur"] - merged["total_prev"]

    industry_prev = float(merged["total_prev"].sum())
    industry_delta = float(merged["delta"].sum())

    if industry_prev <= 0:
        return pd.DataFrame()

    merged["contribution_pp"] = (
        merged["delta"] / industry_prev * 100
    ).round(2)
    merged["share_of_change_pct"] = (
        merged["delta"] / industry_delta if industry_delta else 0
    )
    merged["share_of_change_pct"] = pd.to_numeric(
        merged["share_of_change_pct"], errors="coerce"
    ).round(4)
    return merged.sort_values("contribution_pp", ascending=False).reset_index(drop=True)
