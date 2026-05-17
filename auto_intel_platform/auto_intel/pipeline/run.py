"""
pipeline/run.py — Master Pipeline Orchestrator
===============================================
Runs the complete pipeline:
  Fetch → Filter → Download → Extract → Normalize → Validate → Store

Idempotent — safe to run daily via GitHub Actions.
Fails loudly — never silently produces wrong data.
"""

import logging
import sys
import json
import time
import random
from datetime import datetime, timedelta
from pathlib import Path

# ── Setup path ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from registry import OEM_REGISTRY, get_all_active
from schema import ParserStatus
from pipeline.fetch import fetch_all_companies
from pipeline.extract import extract_from_pdf
from pipeline.validate import validate_batch
from pipeline.store import (
    load_normalized, save_normalized, save_granular,
    save_review_queue, update_filing_status,
)

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            LOG_DIR / f"pipeline_{datetime.today().strftime('%Y%m%d')}.log"
        ),
    ],
)
logger = logging.getLogger("pipeline.run")


def _get_normalizer(parser_module: str):
    """Dynamically import the correct parser module."""
    import importlib
    try:
        mod = importlib.import_module(f"parsers.{parser_module}")
        return mod
    except ImportError as e:
        logger.error(f"Parser module not found: parsers.{parser_module} — {e}")
        return None


def run_pipeline(
    company_keys: list = None,
    from_date: str = None,
    to_date: str = None,
    force_download: bool = False,
) -> dict:
    """
    Full pipeline run.

    Args:
        company_keys:    Limit to specific OEMs (None = all active)
        from_date:       "DD-MM-YYYY" (NSE format)
        to_date:         "DD-MM-YYYY"
        force_download:  Re-download PDFs even if cached

    Returns:
        Summary dict with counts
    """
    start_time = datetime.utcnow()
    summary = {
        "run_at":         start_time.isoformat(),
        "fetched":        0,
        "filtered":       0,
        "downloaded":     0,
        "extracted":      0,
        "normalized":     0,
        "accepted":       0,
        "written":        0,
        "review_queue":   0,
        "errors":         [],
    }

    # Default: last 45 days
    if not to_date:
        to_date = datetime.today().strftime("%d-%m-%Y")
    if not from_date:
        from_date = (datetime.today() - timedelta(days=45)).strftime("%d-%m-%Y")

    active_oems = get_all_active()
    if company_keys:
        active_oems = [o for o in active_oems if o.key in company_keys]

    logger.info(f"Pipeline start: {len(active_oems)} OEMs | {from_date} → {to_date}")

    # ── STEP 1: Fetch announcements ────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 1: Fetching announcements from NSE/BSE")

    # Group by NSE symbol (multiple OEM keys may share a symbol e.g. TATAMOTORS)
    symbol_to_keys = {}
    for oem in active_oems:
        sym = oem.nse_symbol
        symbol_to_keys.setdefault(sym, []).append(oem.key)

    # Fetch once per symbol, then fan out to OEM keys
    raw_by_symbol = fetch_all_companies(
        company_keys=list(symbol_to_keys.keys()),
        from_date=from_date,
        to_date=to_date,
    )

    # Distribute to OEM keys
    raw_by_oem = {}
    for sym, oem_keys in symbol_to_keys.items():
        announcements = raw_by_symbol.get(sym, [])
        for key in oem_keys:
            raw_by_oem[key] = announcements
        summary["fetched"] += len(announcements)

    # ── STEP 2: Filter ────────────────────────────────────────────────────────
    logger.info("STEP 2: Filtering relevant filings")
    filtered_by_oem = {}
    for key, announcements in raw_by_oem.items():
        oem_config = OEM_REGISTRY[key]
        # Use the NSE symbol as filter key since filter.py uses COMPANIES dict
        filtered = filter_announcements_for_oem(announcements, oem_config)
        filtered_by_oem[key] = filtered
        summary["filtered"] += len(filtered)
        logger.info(f"  {key}: {len(announcements)} → {len(filtered)} relevant")

    # ── STEP 3: Download PDFs ─────────────────────────────────────────────────
    logger.info("STEP 3: Downloading PDFs")
    downloaded_by_oem = {}
    for key, announcements in filtered_by_oem.items():
        enriched = []
        for ann in announcements:
            url       = ann.get("file_url", "")
            tag       = _build_month_year(ann)

            from pipeline.download import download_pdf
            local_path = download_pdf(
                url=url,
                company_key=key,
                month_tag=tag,
                source=ann.get("_source", "NSE"),
                force=force_download,
            )
            ann["_local_pdf_path"] = str(local_path) if local_path else None
            if local_path:
                summary["downloaded"] += 1
            enriched.append(ann)
            time.sleep(random.uniform(0.3, 0.8))
        downloaded_by_oem[key] = enriched

    # ── STEP 4: Extract + Normalize + Validate + Store ────────────────────────
    logger.info("STEP 4-7: Extract → Normalize → Validate → Store")
    existing_df = load_normalized()

    norm_rows_collected = []
    row_metadata = {}
    all_granular = []

    for key, announcements in downloaded_by_oem.items():
        oem_config = OEM_REGISTRY[key]
        normalizer = _get_normalizer(oem_config.parser_module)
        if not normalizer:
            summary["errors"].append(f"{key}: parser module missing")
            continue

        for ann in announcements:
            pdf_path = ann.get("_local_pdf_path")
            if not pdf_path:
                filing_month = _build_month_year(ann)
                update_filing_status(
                    key,
                    filing_month,
                    ParserStatus.NEEDS_REVIEW,
                    notes="PDF download failed",
                )
                continue

            # Extract
            extraction = extract_from_pdf(pdf_path)
            if extraction["error"]:
                logger.error(f"[{key}] Extraction error: {extraction['error']}")
                summary["errors"].append(f"{key}: {extraction['error']}")
                continue

            summary["extracted"] += 1

            filing_month = _build_month_year(ann)
            filing_date  = ann.get("exchange_dt", "")[:10]

            # Normalize — pass target_key so Tata/M&M know which section to target
            try:
                result = normalizer.normalize(
                    tables            = extraction["tables"],
                    full_text         = extraction["full_text"],
                    filing_month_year = filing_month,
                    filing_date       = filing_date,
                    source            = ann.get("_source", "NSE"),
                    pdf_path          = pdf_path,
                    target_key        = key,
                )
            except TypeError:
                # Some normalizers don't take target_key
                result = normalizer.normalize(
                    tables            = extraction["tables"],
                    full_text         = extraction["full_text"],
                    filing_month_year = filing_month,
                    filing_date       = filing_date,
                    source            = ann.get("_source", "NSE"),
                    pdf_path          = pdf_path,
                )

            if isinstance(result, tuple) and len(result) == 3:
                norm_row, granular_rows, confidence = result
            else:
                norm_row, granular_rows, confidence = None, [], 0.0

            if norm_row is None:
                logger.warning(f"[{key}] Normalization returned None")
                update_filing_status(
                    key, filing_month, ParserStatus.NEEDS_REVIEW,
                    notes="Normalization failed — review PDF manually",
                )
                summary["errors"].append(f"{key} {filing_month}: normalization failed")
                continue

            summary["normalized"] += 1
            norm_rows_collected.append(norm_row)
            row_metadata[norm_row.pk] = {
                "filing_date": filing_date,
                "pdf_url": ann.get("file_url", ""),
            }
            all_granular.extend(granular_rows)

        logger.info(f"  {key}: extraction complete")

    # ── Batch validate ─────────────────────────────────────────────────────────
    logger.info("STEP 5: Validating batch")

    accepted, review = validate_batch(norm_rows_collected, existing_df, existing_df)
    summary["accepted"]     = len(accepted)
    summary["review_queue"] = len(review)

    for row in accepted + review:
        meta = row_metadata.get(row.pk, {})
        update_filing_status(
            row.company_key,
            row.filing_month_year,
            status=row.parser_status,
            filing_date=meta.get("filing_date", ""),
            pdf_url=meta.get("pdf_url", ""),
            notes=row.review_note,
        )

    # ── Store ─────────────────────────────────────────────────────────────────
    logger.info("STEP 6: Storing data")
    written = save_normalized(accepted)
    summary["written"] = written
    save_granular(all_granular)
    save_review_queue(review)

    elapsed = (datetime.utcnow() - start_time).total_seconds()
    summary["elapsed_seconds"] = round(elapsed, 1)

    _log_summary(summary)
    _save_run_log(summary)

    return summary


def filter_announcements_for_oem(announcements: list, oem_config) -> list:
    """Filter using OEM-level include/exclude keywords + title regex."""
    import re
    relevant = []
    for ann in announcements:
        title = ann.get("title", "").lower()
        text  = f"{title} {ann.get('category','').lower()}"

        # Exclude
        excluded = any(kw.lower() in text for kw in oem_config.exclude_keywords)
        if excluded:
            continue

        # Include signal
        include_hit = any(kw.lower() in text for kw in oem_config.include_keywords)
        regex_hit   = bool(re.search(oem_config.title_regex, title))

        if include_hit or regex_hit:
            tagged = ann.copy()
            month, year = _extract_reference_period(tagged)
            tagged["_is_relevant"] = True
            tagged["_oem_key"] = oem_config.key
            tagged["_reference_month"] = month
            tagged["_reference_year"] = year
            tagged["_filter_reason"] = (
                f"include_hit={include_hit}; title_regex={regex_hit}"
            )
            relevant.append(tagged)

    return relevant


def _extract_reference_period(ann: dict) -> tuple[str, int]:
    """Extract the sales month/year from title, falling back to filing date - 1 month."""
    import re

    month_tokens = {
        "january": 1, "jan": 1,
        "february": 2, "feb": 2,
        "march": 3, "mar": 3,
        "april": 4, "apr": 4,
        "may": 5,
        "june": 6, "jun": 6,
        "july": 7, "jul": 7,
        "august": 8, "aug": 8,
        "september": 9, "sep": 9,
        "october": 10, "oct": 10,
        "november": 11, "nov": 11,
        "december": 12, "dec": 12,
    }
    month_names = {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December",
    }

    title = ann.get("title", "").lower()
    filing_dt = _parse_exchange_date(ann.get("exchange_dt", ""))
    filing_year = filing_dt.year if filing_dt else datetime.today().year

    found_month = None
    for token, month_num in month_tokens.items():
        if re.search(rf"\b{re.escape(token)}\b", title):
            found_month = month_num
            break

    year_match = re.search(r"\b(20\d{2})\b", title)
    found_year = int(year_match.group(1)) if year_match else filing_year

    if found_month:
        if filing_dt and not year_match and found_month > filing_dt.month:
            found_year -= 1
        return month_names[found_month], found_year

    if filing_dt:
        first_of_month = filing_dt.replace(day=1)
        prior_month = first_of_month - timedelta(days=1)
        return month_names[prior_month.month], prior_month.year

    today = datetime.today()
    first_of_month = today.replace(day=1)
    prior_month = first_of_month - timedelta(days=1)
    return month_names[prior_month.month], prior_month.year


def _parse_exchange_date(raw_value: str):
    if not raw_value:
        return None
    value = str(raw_value).strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y%m%d", "%d %b %Y"):
        try:
            width = 11 if fmt == "%d %b %Y" else 10
            return datetime.strptime(value[:width].strip(), fmt)
        except ValueError:
            continue
    return None


def _build_month_year(ann: dict) -> str:
    month = ann.get("_reference_month", "")
    year = ann.get("_reference_year")
    if not month or not year:
        month, year = _extract_reference_period(ann)
    if month and year:
        for fmt in ("%B %Y", "%b %Y"):
            try:
                dt = datetime.strptime(f"{month} {year}", fmt)
                return dt.strftime("%Y-%m")
            except Exception:
                continue

    filing_dt = _parse_exchange_date(ann.get("exchange_dt", ""))
    if filing_dt:
        prior_month = filing_dt.replace(day=1) - timedelta(days=1)
        return prior_month.strftime("%Y-%m")

    today = datetime.today()
    prior_month = today.replace(day=1) - timedelta(days=1)
    return prior_month.strftime("%Y-%m")


def _log_summary(summary: dict) -> None:
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info(f"  Fetched:      {summary['fetched']}")
    logger.info(f"  Filtered:     {summary['filtered']}")
    logger.info(f"  Downloaded:   {summary['downloaded']}")
    logger.info(f"  Extracted:    {summary['extracted']}")
    logger.info(f"  Normalized:   {summary['normalized']}")
    logger.info(f"  Accepted:     {summary['accepted']}")
    logger.info(f"  Written:      {summary.get('written', 0)}")
    logger.info(f"  Review Queue: {summary['review_queue']}")
    logger.info(f"  Errors:       {len(summary['errors'])}")
    logger.info(f"  Elapsed:      {summary.get('elapsed_seconds', '?')}s")
    if summary["errors"]:
        for e in summary["errors"]:
            logger.warning(f"  ERROR: {e}")
    logger.info("=" * 60)


def _save_run_log(summary: dict) -> None:
    log_path = LOG_DIR / "run_history.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(summary) + "\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Auto Intel Pipeline")
    parser.add_argument("--oems",    nargs="+", help="Specific OEM keys")
    parser.add_argument("--from",    dest="from_date", help="From date DD-MM-YYYY")
    parser.add_argument("--to",      dest="to_date",   help="To date DD-MM-YYYY")
    parser.add_argument("--force",   action="store_true", help="Force re-download")
    args = parser.parse_args()

    run_pipeline(
        company_keys  = args.oems,
        from_date     = args.from_date,
        to_date       = args.to_date,
        force_download= args.force,
    )
