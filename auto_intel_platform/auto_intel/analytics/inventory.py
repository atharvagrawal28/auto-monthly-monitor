"""
analytics/inventory.py — Channel Inventory Analytics
=====================================================
Channel inventory = cumulative (wholesale − retail) since a base period.
Shows whether dealers are overstocked (channel-stuffing risk) or running lean.

This module is RETAIL-ONLY. It joins wholesale and retail only for the
channel inventory computation — never modifies either source dataset.

Key metrics:
  - Monthly spread   : wholesale − retail for that month (flow)
  - Channel inventory: running cumulative spread (stock)
  - Weeks of supply  : channel inventory ÷ (trailing 3M retail ÷ 13)
  - Health label     : LEAN / HEALTHY / ELEVATED / BLOATED

Segment mapping (which OEM keys roll up to each FADA segment):
  PV      → MARUTI + TATAMOTORS_PV + MAHINDRA_AUTO
  2W      → BAJAJ + HEROMOTOCO + TVS + EICHER
  3W      → BAJAJ + TVS
  CV      → TATAMOTORS_CV + ASHOKLEY + MAHINDRA_AUTO (CV portion)
  Tractor → MAHINDRA_FARM + ESCORTS
  EV      → OLA_ELECTRIC + TATAMOTORS_PV (EV) + MAHINDRA_AUTO (EV)
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Optional


# ── Segment roll-up map ────────────────────────────────────────────────────────
# Maps each retail segment (as FADA reports it) to the OEM keys + segments
# that contribute to it in the wholesale dataset.

SEGMENT_ROLLUP: dict[str, list[tuple[str, str]]] = {
    "PV":      [
        ("MARUTI",        "PV"),
        ("TATAMOTORS_PV", "PV"),
        ("MAHINDRA_AUTO", "PV"),
    ],
    "2W":      [
        ("BAJAJ",     "2W"),
        ("HEROMOTOCO","2W"),
        ("TVS",       "2W"),
        ("EICHER",    "2W"),
    ],
    "3W":      [
        ("BAJAJ", "3W"),
        ("TVS",   "3W"),
    ],
    "CV":      [
        ("TATAMOTORS_CV", "CV"),
        ("ASHOKLEY",      "CV"),
        ("MAHINDRA_AUTO", "CV"),
    ],
    "Tractor": [
        ("MAHINDRA_FARM", "Tractor"),
        ("ESCORTS",       "Tractor"),
    ],
    "EV":      [
        ("OLA_ELECTRIC",  "EV"),
        ("TATAMOTORS_PV", "EV"),
        ("MAHINDRA_AUTO", "EV"),
        ("HEROMOTOCO",    "EV"),
        ("TVS",           "EV"),
        ("BAJAJ",         "EV"),
    ],
}

# Weeks-of-supply thresholds
_HEALTH_THRESHOLDS = [
    (3,  "LEAN",     "#15803D"),   # < 3 weeks — supply-constrained, strong demand
    (6,  "HEALTHY",  "#2563EB"),   # 3–6 weeks — normal operating range
    (8,  "ELEVATED", "#D97706"),   # 6–8 weeks — watch closely
    (999,"BLOATED",  "#DC2626"),   # > 8 weeks — channel-stuffing risk
]


def health_label(weeks: Optional[float]) -> tuple[str, str]:
    """
    Returns (label, hex_color) based on weeks of supply.
    """
    if weeks is None or np.isnan(weeks):
        return ("UNKNOWN", "#64748B")
    for threshold, label, color in _HEALTH_THRESHOLDS:
        if weeks < threshold:
            return (label, color)
    return ("BLOATED", "#DC2626")


# ── Wholesale aggregation ──────────────────────────────────────────────────────

def wholesale_by_segment(norm_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate the normalized wholesale DataFrame to segment level.

    Returns:
        DataFrame with columns [filing_month_year, segment, wholesale_total]
    """
    if norm_df.empty:
        return pd.DataFrame(columns=["filing_month_year", "segment", "wholesale_total"])

    rows = []
    months = norm_df["filing_month_year"].dropna().unique()

    for month in sorted(months):
        month_df = norm_df[norm_df["filing_month_year"] == month]
        for seg, oem_seg_pairs in SEGMENT_ROLLUP.items():
            total = 0
            for oem_key, oem_seg in oem_seg_pairs:
                sub = month_df[
                    (month_df["company_key"] == oem_key) &
                    (month_df["segment"]     == oem_seg)
                ]
                if not sub.empty:
                    val = pd.to_numeric(sub["total"], errors="coerce").sum()
                    if not np.isnan(val):
                        total += int(val)
            rows.append({
                "filing_month_year": month,
                "segment":           seg,
                "wholesale_total":   total,
            })

    return pd.DataFrame(rows)


# ── Channel inventory computation ─────────────────────────────────────────────

def channel_inventory(
    norm_df:   pd.DataFrame,
    retail_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute monthly wholesale vs retail gap and running channel inventory.

    Args:
        norm_df:   Wholesale normalized data (from data/normalized.csv)
        retail_df: Retail FADA data (from data/retail.csv)

    Returns:
        DataFrame with columns:
          filing_month_year, segment,
          wholesale_total, retail_total,
          monthly_spread,      # wholesale − retail (this month)
          cum_inventory,       # running cumulative spread (units)
          trailing_3m_retail,  # trailing 3-month retail average
          weeks_of_supply,     # cum_inventory / (trailing_3m_retail / 13)
          health_label,
          health_color
    """
    if norm_df.empty or retail_df.empty:
        return pd.DataFrame()

    ws = wholesale_by_segment(norm_df)

    rt = retail_df.copy()
    rt["retail_total"] = pd.to_numeric(rt["retail_total"], errors="coerce").fillna(0).astype(int)
    rt_agg = (
        rt.groupby(["filing_month_year", "segment"])["retail_total"]
        .sum()
        .reset_index()
        .rename(columns={"retail_total": "retail_total"})
    )

    merged = pd.merge(ws, rt_agg, on=["filing_month_year", "segment"], how="outer")
    merged["wholesale_total"] = merged["wholesale_total"].fillna(0).astype(int)
    merged["retail_total"]    = merged["retail_total"].fillna(0).astype(int)
    merged["monthly_spread"]  = merged["wholesale_total"] - merged["retail_total"]

    merged = merged.sort_values(["segment", "filing_month_year"]).reset_index(drop=True)

    # Running cumulative inventory per segment
    merged["cum_inventory"] = merged.groupby("segment")["monthly_spread"].cumsum()

    # Trailing 3-month retail average per segment
    merged["trailing_3m_retail"] = (
        merged.groupby("segment")["retail_total"]
        .transform(lambda x: x.rolling(3, min_periods=1).mean())
    )

    # Weeks of supply = inventory ÷ weekly retail run rate
    # weekly_retail = trailing_3m_retail / 13  (13 weeks in 3 months)
    with np.errstate(divide="ignore", invalid="ignore"):
        merged["weeks_of_supply"] = np.where(
            merged["trailing_3m_retail"] > 0,
            merged["cum_inventory"] / (merged["trailing_3m_retail"] / 13.0),
            np.nan,
        )
    merged["weeks_of_supply"] = merged["weeks_of_supply"].round(1)

    # Health labels
    merged[["health_label", "health_color"]] = merged["weeks_of_supply"].apply(
        lambda w: pd.Series(health_label(w))
    )

    return merged.sort_values(["filing_month_year", "segment"]).reset_index(drop=True)


def latest_inventory_snapshot(inv_df: pd.DataFrame) -> pd.DataFrame:
    """
    Return only the most recent month's channel inventory per segment.
    """
    if inv_df.empty:
        return inv_df
    latest = inv_df["filing_month_year"].max()
    return inv_df[inv_df["filing_month_year"] == latest].copy()


def wholesale_retail_trend(
    inv_df: pd.DataFrame,
    segment: str,
) -> pd.DataFrame:
    """
    Return monthly wholesale vs retail trend for a specific segment.
    Used by the Retail Pulse page charts.
    """
    sub = inv_df[inv_df["segment"] == segment].copy()
    return sub.sort_values("filing_month_year").reset_index(drop=True)
