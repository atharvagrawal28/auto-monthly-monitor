"""
pipeline/validate.py — Validation + Reconciliation Engine
==========================================================
Rules:
  1. Arithmetic: domestic + exports ≈ total (±5%)
  2. Sanity: total > 0, values not absurdly large
  3. Anomaly: YoY change > ±50% → FLAGGED
  4. Duplicate: (company, segment, month) already in dataset
  5. Reconciliation: new vs existing — conflict if >10% delta
"""

import logging
from typing import Optional
import pandas as pd

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from schema import NormalizedRow, ParserStatus, NORMALIZED_COLUMNS

logger = logging.getLogger(__name__)

ARITHMETIC_TOLERANCE = 0.05
ANOMALY_YOY_THRESHOLD = 0.50
MIN_UNITS = 10
MAX_UNITS = 2_000_000
CONFLICT_THRESHOLD = 0.10   # 10% delta → CONFLICT


def validate(row: NormalizedRow, existing_df: pd.DataFrame) -> NormalizedRow:
    """
    Run all validation checks on a NormalizedRow.
    Modifies parser_status in place. Never raises — fails loudly via status.
    """
    issues = []

    # ── 1. Arithmetic check ───────────────────────────────────────────────────
    if row.domestic is not None and row.exports is not None and row.total is not None:
        derived = row.domestic + row.exports
        if row.total > 0:
            tol = abs(derived - row.total) / row.total
            if tol > ARITHMETIC_TOLERANCE:
                issues.append(f"Arithmetic fail: {row.domestic}+{row.exports}={derived} ≠ {row.total} ({tol:.1%})")

    # ── 2. Sanity check ───────────────────────────────────────────────────────
    if row.total is not None:
        if row.total < MIN_UNITS:
            issues.append(f"Total too low: {row.total} < {MIN_UNITS}")
        if row.total > MAX_UNITS:
            issues.append(f"Total unrealistically high: {row.total}")

    # ── 3. YoY anomaly ────────────────────────────────────────────────────────
    if row.yoy_pct is not None:
        if abs(row.yoy_pct) > ANOMALY_YOY_THRESHOLD:
            issues.append(f"YoY anomaly: {row.yoy_pct:.1%}")

    # ── 4. Reconciliation against existing data ───────────────────────────────
    recon_issue = _reconcile(row, existing_df)
    if recon_issue:
        issues.append(recon_issue)
        if "CONFLICT" in recon_issue:
            row.parser_status = ParserStatus.CONFLICT
            row.review_note   = recon_issue
            return row

    # ── Determine final status ────────────────────────────────────────────────
    if issues:
        status_issues = [i for i in issues if "Arithmetic fail" in i
                         or "too low" in i or "unrealistically" in i]
        if status_issues:
            row.parser_status = ParserStatus.NEEDS_REVIEW
            row.review_note   = " | ".join(issues)
        else:
            # YoY anomaly alone = FLAGGED (data may be correct, just unusual)
            if row.parser_status == ParserStatus.CLEAN:
                row.parser_status = ParserStatus.FLAGGED
            row.review_note = " | ".join(issues)
    else:
        if row.parser_status not in (ParserStatus.MANUAL, ParserStatus.CONFLICT):
            row.parser_status = ParserStatus.CLEAN

    if issues:
        logger.warning(f"[Validate] {row.company_key} {row.filing_month_year}: {' | '.join(issues)}")
    else:
        logger.info(f"[Validate] {row.company_key} {row.filing_month_year}: CLEAN")

    return row


def _reconcile(row: NormalizedRow, existing_df: pd.DataFrame) -> Optional[str]:
    """
    Compare against existing stored value.
    Returns issue string or None.
    """
    if existing_df is None or existing_df.empty:
        return None

    mask = (
        (existing_df["company_key"]       == row.company_key) &
        (existing_df["segment"]            == row.segment) &
        (existing_df["filing_month_year"]  == row.filing_month_year)
    )
    existing = existing_df[mask]

    if existing.empty:
        return None  # new row, no conflict possible

    existing_row = existing.iloc[0]
    if _same_core_metrics(row, existing_row):
        return "DUPLICATE: identical data already stored"

    stored_total = _to_float(existing_row.get("total"))
    if stored_total is None or stored_total == 0:
        return None

    if row.total is None or row.total == 0:
        return "CONFLICT: new total is 0/None vs stored"

    delta = abs(row.total - stored_total) / stored_total

    if delta < CONFLICT_THRESHOLD:
        return f"MINOR_DELTA: new={row.total} vs stored={stored_total} ({delta:.1%}) — will overwrite"
    else:
        return f"CONFLICT: new={row.total} vs stored={stored_total} ({delta:.1%}) — review required"


def _to_float(value) -> Optional[float]:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _same_core_metrics(row: NormalizedRow, existing_row) -> bool:
    for col in ("domestic", "exports", "total"):
        existing_value = _to_float(existing_row.get(col))
        new_value = getattr(row, col)
        if existing_value is None and new_value is None:
            continue
        if existing_value != new_value:
            return False
    return True


def compute_growth(row: NormalizedRow, history_df: pd.DataFrame) -> NormalizedRow:
    """
    Compute YoY and MoM growth rates from historical data.
    Attaches to row.yoy_pct and row.mom_pct.
    """
    if history_df is None or history_df.empty or row.total is None:
        return row

    mask_base = (
        (history_df["company_key"] == row.company_key) &
        (history_df["segment"]      == row.segment)
    )
    company_hist = history_df[mask_base].copy()

    if company_hist.empty:
        return row

    # Parse month strings to dates for comparison
    try:
        company_hist["_dt"] = pd.to_datetime(company_hist["filing_month_year"] + "-01")
        current_dt = pd.to_datetime(row.filing_month_year + "-01")
    except Exception:
        return row

    # YoY: same month last year
    yoy_dt  = current_dt - pd.DateOffset(years=1)
    yoy_row = company_hist[company_hist["_dt"] == yoy_dt]
    if not yoy_row.empty:
        yoy_total = yoy_row.iloc[0]["total"]
        if yoy_total and yoy_total > 0:
            row.yoy_pct = round((row.total - yoy_total) / yoy_total, 4)

    # MoM: previous month
    mom_dt  = current_dt - pd.DateOffset(months=1)
    mom_row = company_hist[company_hist["_dt"] == mom_dt]
    if not mom_row.empty:
        mom_total = mom_row.iloc[0]["total"]
        if mom_total and mom_total > 0:
            row.mom_pct = round((row.total - mom_total) / mom_total, 4)

    return row


def validate_batch(
    rows: list[NormalizedRow],
    existing_df: pd.DataFrame,
    history_df: pd.DataFrame,
) -> tuple[list[NormalizedRow], list[NormalizedRow]]:
    """
    Validate a batch of rows.

    Returns:
        (accepted_rows, review_queue_rows)
    """
    accepted = []
    review   = []

    for row in rows:
        duplicate_note = _reconcile(row, existing_df)
        if duplicate_note and duplicate_note.startswith("DUPLICATE"):
            logger.info(
                f"[Validate] Skipping duplicate: {row.company_key} "
                f"{row.segment} {row.filing_month_year}"
            )
            continue

        row = compute_growth(row, history_df)
        row = validate(row, existing_df)

        if row.parser_status in (ParserStatus.NEEDS_REVIEW, ParserStatus.CONFLICT):
            review.append(row)
            logger.warning(f"→ REVIEW QUEUE: {row.company_key} {row.filing_month_year} [{row.parser_status}]")
        else:
            accepted.append(row)

    logger.info(f"Validation: {len(accepted)} accepted, {len(review)} in review queue")
    return accepted, review
