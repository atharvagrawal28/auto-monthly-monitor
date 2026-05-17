"""
pipeline/store.py — Storage Layer
==================================
Writes NormalizedRows to CSV/Parquet.
Schema is PostgreSQL-ready — migration is just pg COPY.
Handles idempotency, append, and review queue separately.
"""

import logging
from pathlib import Path
from datetime import datetime
import pandas as pd

import sys, pathlib as _pl
sys.path.insert(0, str(_pl.Path(__file__).parent.parent))
from schema import (
    NormalizedRow, GranularRow, FilingStatus,
    NORMALIZED_COLUMNS, GRANULAR_COLUMNS, FILING_STATUS_COLUMNS,
    ParserStatus,
)

logger = logging.getLogger(__name__)

# ── File paths ────────────────────────────────────────────────────────────────
BASE      = _pl.Path(__file__).parent.parent / "data"
NORM_PATH = BASE / "normalized.csv"
GRAN_PATH = BASE / "granular.csv"
RAW_PATH  = BASE / "raw_log.csv"
REVIEW_PATH = BASE / "review_queue.csv"
FILING_PATH = BASE / "filing_status.csv"


def load_normalized() -> pd.DataFrame:
    """Load the full normalized dataset."""
    if not NORM_PATH.exists():
        return pd.DataFrame(columns=NORMALIZED_COLUMNS)
    try:
        df = pd.read_csv(NORM_PATH, dtype=str)
        # Cast numeric columns
        for col in ["domestic", "exports", "total"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        for col in ["yoy_pct", "mom_pct", "confidence_score"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception as e:
        logger.error(f"Failed to load normalized data: {e}")
        return pd.DataFrame(columns=NORMALIZED_COLUMNS)


def load_granular() -> pd.DataFrame:
    if not GRAN_PATH.exists():
        return pd.DataFrame(columns=GRANULAR_COLUMNS)
    try:
        return pd.read_csv(GRAN_PATH, dtype=str)
    except Exception:
        return pd.DataFrame(columns=GRANULAR_COLUMNS)


def load_review_queue() -> pd.DataFrame:
    if not REVIEW_PATH.exists():
        return pd.DataFrame(columns=NORMALIZED_COLUMNS)
    return pd.read_csv(REVIEW_PATH, dtype=str)


def load_filing_status() -> pd.DataFrame:
    if not FILING_PATH.exists():
        return pd.DataFrame(columns=FILING_STATUS_COLUMNS)
    return pd.read_csv(FILING_PATH, dtype=str)


def save_normalized(rows: list[NormalizedRow]) -> int:
    """
    Append new rows to normalized.csv.
    Idempotent — skips exact duplicates by primary key.
    Returns count of rows actually written.
    """
    if not rows:
        return 0

    existing = load_normalized()
    new_dicts = [r.to_dict() for r in rows]
    new_df    = pd.DataFrame(new_dicts)

    # Ensure all columns present
    for col in NORMALIZED_COLUMNS:
        if col not in new_df.columns:
            new_df[col] = None
    new_df = new_df[NORMALIZED_COLUMNS]

    pk = ["company_key", "segment", "filing_month_year"]
    rows_to_write = []
    keys_to_replace = set()

    for _, row in new_df.iterrows():
        row_key = tuple(row[c] for c in pk)
        existing_match = _find_existing_pk(existing, row_key)

        if existing_match is None:
            rows_to_write.append(row.to_dict())
            continue

        if _same_metrics(existing_match, row):
            logger.info(f"Skipping exact duplicate row: {row_key}")
            continue

        if (
            str(existing_match.get("parser_status", "")) == ParserStatus.MANUAL
            and str(row.get("parser_status", "")) != ParserStatus.MANUAL
        ):
            logger.warning(f"Preserving MANUAL row, skipped automatic overwrite: {row_key}")
            continue

        rows_to_write.append(row.to_dict())
        keys_to_replace.add(row_key)

    new_df = pd.DataFrame(rows_to_write, columns=NORMALIZED_COLUMNS)

    if new_df.empty:
        logger.info("No new rows to write (all already stored)")
        return 0

    if not existing.empty and keys_to_replace:
        replace_mask = existing.apply(
            lambda r: (r["company_key"], r["segment"], r["filing_month_year"]) in keys_to_replace,
            axis=1,
        )
        existing = existing[~replace_mask]

    combined = pd.concat([existing, new_df], ignore_index=True)
    NORM_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(NORM_PATH, index=False)
    logger.info(f"Saved {len(new_df)} new rows → {NORM_PATH}")
    return len(new_df)


def _find_existing_pk(existing: pd.DataFrame, row_key: tuple):
    if existing is None or existing.empty:
        return None
    mask = (
        (existing["company_key"] == row_key[0]) &
        (existing["segment"] == row_key[1]) &
        (existing["filing_month_year"] == row_key[2])
    )
    match = existing[mask]
    if match.empty:
        return None
    return match.iloc[0]


def _same_metrics(existing_row, new_row) -> bool:
    compare_cols = ["domestic", "exports", "total", "raw_row_hash"]
    for col in compare_cols:
        existing_val = existing_row.get(col)
        new_val = new_row.get(col)
        if pd.isna(existing_val) and pd.isna(new_val):
            continue
        if str(existing_val) != str(new_val):
            return False
    return True


def save_granular(rows: list[GranularRow]) -> int:
    if not rows:
        return 0

    existing = load_granular()
    new_df   = pd.DataFrame([r.to_dict() for r in rows])

    for col in GRANULAR_COLUMNS:
        if col not in new_df.columns:
            new_df[col] = None
    new_df = new_df[GRANULAR_COLUMNS]

    combined = pd.concat([existing, new_df], ignore_index=True)
    combined = combined.drop_duplicates(
        subset=["company_key", "segment", "filing_month_year", "raw_category"]
    )
    GRAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(GRAN_PATH, index=False)
    logger.info(f"Saved {len(new_df)} granular rows → {GRAN_PATH}")
    return len(new_df)


def save_review_queue(rows: list[NormalizedRow]) -> int:
    """Write NEEDS_REVIEW / CONFLICT rows to review queue."""
    if not rows:
        return 0

    existing = load_review_queue()
    new_df   = pd.DataFrame([r.to_dict() for r in rows])

    for col in NORMALIZED_COLUMNS:
        if col not in new_df.columns:
            new_df[col] = None
    new_df = new_df[NORMALIZED_COLUMNS]

    combined = pd.concat([existing, new_df], ignore_index=True)
    # Keep all review entries (don't deduplicate — each attempt is a record)
    REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(REVIEW_PATH, index=False)
    logger.warning(f"→ Review queue: {len(new_df)} rows added → {REVIEW_PATH}")
    return len(new_df)


def update_filing_status(
    company_key: str,
    filing_month_year: str,
    status: str,
    filing_date: str = "",
    expected_by: str = "",
    pdf_url: str = "",
    notes: str = "",
) -> None:
    """Upsert a filing status entry."""
    existing = load_filing_status()
    now = datetime.utcnow().isoformat() + "Z"

    new_entry = {
        "company_key":       company_key,
        "filing_month_year": filing_month_year,
        "status":            status,
        "filing_date":       filing_date,
        "expected_by":       expected_by,
        "pdf_url":           pdf_url,
        "notes":             notes,
        "last_checked":      now,
    }

    if not existing.empty:
        mask = (
            (existing["company_key"]       == company_key) &
            (existing["filing_month_year"] == filing_month_year)
        )
        existing = existing[~mask]

    updated = pd.concat([existing, pd.DataFrame([new_entry])], ignore_index=True)
    FILING_PATH.parent.mkdir(parents=True, exist_ok=True)
    updated.to_csv(FILING_PATH, index=False)


def approve_review_item(
    company_key: str,
    segment: str,
    filing_month_year: str,
    corrected_total: int = None,
    corrected_domestic: int = None,
    corrected_exports: int = None,
    reviewer_note: str = "",
) -> bool:
    """
    Approve a review queue item — optionally with corrections.
    Moves it to the normalized dataset with MANUAL status.
    """
    queue = load_review_queue()
    mask  = (
        (queue["company_key"]       == company_key) &
        (queue["segment"]            == segment) &
        (queue["filing_month_year"]  == filing_month_year)
    )
    items = queue[mask]
    if items.empty:
        logger.warning(f"Review item not found: {company_key} {segment} {filing_month_year}")
        return False

    item = items.iloc[0].to_dict()
    if corrected_total:    item["total"]    = corrected_total
    if corrected_domestic: item["domestic"] = corrected_domestic
    if corrected_exports:  item["exports"]  = corrected_exports
    item["parser_status"] = ParserStatus.MANUAL
    item["review_note"]   = reviewer_note
    item["last_updated"]  = datetime.utcnow().isoformat() + "Z"

    # Save to normalized
    existing = load_normalized()
    # Remove old entry if exists
    pk_mask = (
        (existing["company_key"]       == company_key) &
        (existing["segment"]            == segment) &
        (existing["filing_month_year"]  == filing_month_year)
    )
    existing = existing[~pk_mask]
    updated = pd.concat([existing, pd.DataFrame([item])], ignore_index=True)
    updated.to_csv(NORM_PATH, index=False)

    # Remove from review queue
    queue = queue[~mask]
    queue.to_csv(REVIEW_PATH, index=False)

    logger.info(f"Approved review item: {company_key} {segment} {filing_month_year}")
    return True


def get_market_share(month_year: str, segment: str = None) -> pd.DataFrame:
    """
    Compute market share for a given month across OEMs.
    Optionally filter by segment.
    """
    df = load_normalized()
    if df.empty:
        return pd.DataFrame()

    df = df[df["filing_month_year"] == month_year].copy()
    if segment:
        df = df[df["segment"] == segment]

    df = df[df["parser_status"].isin([ParserStatus.CLEAN, ParserStatus.FLAGGED, ParserStatus.MANUAL])]

    if df.empty:
        return pd.DataFrame()

    df["total"] = pd.to_numeric(df["total"], errors="coerce")
    industry_total = df["total"].sum()

    if industry_total > 0:
        df["market_share_pct"] = (df["total"] / industry_total * 100).round(2)
    else:
        df["market_share_pct"] = 0.0

    return df[["company_key", "segment", "total", "market_share_pct"]].sort_values(
        "total", ascending=False
    )
