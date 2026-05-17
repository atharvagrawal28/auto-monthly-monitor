"""
pipeline/fetch.py
=================
Fetches corporate announcements from NSE (primary) and BSE (fallback).
Returns a list of raw announcement dicts for downstream filtering.

Design:
  - Session-level cookies for NSE (required for NSE API)
  - Exponential retry with jitter
  - Source tagging on every record
  - Respects rate limits via configurable sleep
"""

import time
import json
import random
import logging
import hashlib
import re
from datetime import datetime, timedelta
from typing import Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from config import (
    NSE_BASE, NSE_ANNC_URL, BSE_ANNC_URL, BSE_PDF_BASE,
    REQUEST_HEADERS, REQUEST_TIMEOUT, MAX_RETRIES, RETRY_BACKOFF,
    COMPANIES,
)
from registry import get_all_active, get_by_nse_symbol

logger = logging.getLogger(__name__)


# ─── HTTP SESSION ─────────────────────────────────────────────────────────────

def _make_session(retries: int = MAX_RETRIES, backoff: float = RETRY_BACKOFF) -> requests.Session:
    """Build a requests session with retry logic and browser-like headers."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(REQUEST_HEADERS)
    return session


def _warm_nse_session(session: requests.Session) -> bool:
    """
    NSE blocks direct API access without a valid session cookie.
    Hit the homepage first to obtain cookies.
    """
    try:
        resp = session.get(NSE_BASE, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            logger.debug("NSE session warmed successfully")
            return True
    except Exception as e:
        logger.warning(f"NSE session warm failed: {e}")
    return False


# ─── NSE FETCHER ──────────────────────────────────────────────────────────────

def fetch_nse_announcements(
    symbol: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    max_records: int = 100,
) -> list[dict]:
    """
    Fetch announcements for a given NSE symbol.

    Args:
        symbol:      NSE trading symbol (e.g., "TATAMOTORS")
        from_date:   "DD-MM-YYYY" or None (defaults to 30 days back)
        to_date:     "DD-MM-YYYY" or None (defaults to today)
        max_records: Cap on results

    Returns:
        List of announcement dicts with _source="NSE"
    """
    session = _make_session()
    if not _warm_nse_session(session):
        logger.error("NSE session warmup failed; aborting NSE fetch")
        return []

    today = datetime.today()
    if not to_date:
        to_date = today.strftime("%d-%m-%Y")
    if not from_date:
        from_date = (today - timedelta(days=45)).strftime("%d-%m-%Y")

    params = {
        "index":    "equities",
        "symbol":   symbol,
        "from_date": from_date,
        "to_date":   to_date,
    }

    try:
        time.sleep(random.uniform(0.5, 1.5))  # politeness
        resp = session.get(NSE_ANNC_URL, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.JSONDecodeError:
        logger.error(f"NSE returned non-JSON for {symbol}")
        return []
    except requests.exceptions.HTTPError as e:
        logger.error(f"NSE HTTP error for {symbol}: {e}")
        return []
    except Exception as e:
        logger.error(f"NSE fetch error for {symbol}: {e}")
        return []

    announcements = []
    raw_list = data if isinstance(data, list) else data.get("data", [])

    for item in raw_list[:max_records]:
        ann = {
            "_source":      "NSE",
            "_id":          _make_announcement_id("NSE", symbol, item),
            "symbol":       symbol,
            "company":      item.get("symbol", symbol),
            "title":        item.get("desc", item.get("subject", "")),
            "category":     item.get("purpose", item.get("category", "")),
            "exchange_dt":  item.get("an_dt", item.get("bm_desc", "")),
            "file_url":     _resolve_nse_pdf(item),
            "attachment":   item.get("attchmntFile", ""),
            "raw":          item,
        }
        announcements.append(ann)

    logger.info(f"[NSE] {symbol}: fetched {len(announcements)} announcements")
    return announcements


def _resolve_nse_pdf(item: dict) -> str:
    """Build full PDF URL from NSE attachment field."""
    attachment = item.get("attchmntFile", "")
    if attachment:
        if str(attachment).startswith("http"):
            return attachment
        return f"https://nsearchives.nseindia.com/corporate/xbrl/{attachment}"
    # fallback to alternate field
    alt = item.get("sm_pdf_file", "")
    if alt:
        return f"https://www.nseindia.com/corporate/{alt}"
    return ""


# ─── BSE FETCHER ──────────────────────────────────────────────────────────────

def fetch_bse_announcements(
    bse_code: str,
    category: str = "Corp.Action",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    max_records: int = 100,
) -> list[dict]:
    """
    Fetch announcements for a BSE scrip code.

    Args:
        bse_code:   BSE scrip code (e.g., "500570")
        category:   Announcement category
        from_date:  "YYYYMMDD" or None
        to_date:    "YYYYMMDD" or None

    Returns:
        List of announcement dicts with _source="BSE"
    """
    session = _make_session()

    today = datetime.today()
    if not to_date:
        to_date = today.strftime("%Y%m%d")
    else:
        to_date = _to_bse_date(to_date)
    if not from_date:
        from_date = (today - timedelta(days=45)).strftime("%Y%m%d")
    else:
        from_date = _to_bse_date(from_date)

    params = {
        "strCat":       "-1",
        "strPrevDate":  from_date,
        "strScrip":     bse_code,
        "strSearch":    "S",
        "strToDate":    to_date,
        "strType":      "C",
        "subcategory":  "-1",
    }

    try:
        time.sleep(random.uniform(0.5, 1.5))
        resp = session.get(BSE_ANNC_URL, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"BSE fetch error for {bse_code}: {e}")
        return []

    announcements = []
    raw_list = data.get("Table", [])

    for item in raw_list[:max_records]:
        pdf_file = item.get("ATTACHMENTNAME", "")
        ann = {
            "_source":      "BSE",
            "_id":          _make_announcement_id("BSE", bse_code, item),
            "symbol":       item.get("SCRIP_CD", bse_code),
            "company":      item.get("SLONGNAME", ""),
            "title":        item.get("HEADLINE", item.get("NEWSSUB", "")),
            "category":     item.get("CATEGORYNAME", ""),
            "exchange_dt":  item.get("NEWS_DT", ""),
            "file_url":     f"{BSE_PDF_BASE}{pdf_file}" if pdf_file else "",
            "attachment":   pdf_file,
            "raw":          item,
        }
        announcements.append(ann)

    logger.info(f"[BSE] {bse_code}: fetched {len(announcements)} announcements")
    return announcements


# ─── COMBINED FETCHER ─────────────────────────────────────────────────────────

def fetch_all_announcements(
    company_key: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> list[dict]:
    """
    Fetch from NSE first, fall back to BSE if NSE returns nothing.
    Deduplicates by file URL.

    Args:
        company_key: Key from COMPANIES dict (e.g., "TATAMOTORS")

    Returns:
        Merged, deduplicated list of announcements
    """
    config = COMPANIES.get(company_key) or _config_from_oem_registry(company_key)
    if not config:
        logger.error(f"Unknown company key: {company_key}")
        return []

    # --- NSE (primary) -------------------------------------------------------
    nse_results = fetch_nse_announcements(
        symbol=config["nse_symbol"],
        from_date=from_date,
        to_date=to_date,
    )

    if nse_results:
        return nse_results

    # --- BSE (fallback) -------------------------------------------------------
    logger.info(f"NSE returned 0 results for {company_key}, trying BSE...")
    bse_from_date = _to_bse_date(from_date) if from_date else None
    bse_to_date = _to_bse_date(to_date) if to_date else None
    bse_results = fetch_bse_announcements(
        bse_code=config["bse_code"],
        from_date=bse_from_date,
        to_date=bse_to_date,
    )
    return bse_results


def _config_from_oem_registry(symbol: str) -> Optional[dict]:
    """Build a minimal fetch config from the newer OEM registry."""
    matches = get_by_nse_symbol(symbol)
    if not matches:
        return None
    oem = matches[0]
    return {
        "name": oem.display_name,
        "nse_symbol": oem.nse_symbol,
        "bse_code": oem.bse_code,
    }


def _to_bse_date(date_value: str) -> str:
    """Convert common input dates to BSE's YYYYMMDD format."""
    if not date_value:
        return date_value
    if re.fullmatch(r"\d{8}", date_value):
        return date_value
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_value[:10], fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    return date_value


def _make_announcement_id(source: str, identifier: str, item: dict) -> str:
    """Deterministic ID for deduplication across runs."""
    key = f"{source}:{identifier}:{item.get('ATTACHMENTNAME', item.get('attchmntFile', str(item)[:100]))}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


# ─── BATCH FETCH ──────────────────────────────────────────────────────────────

def fetch_all_companies(
    company_keys: Optional[list] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> dict[str, list[dict]]:
    """
    Fetch announcements for all (or specified) companies.

    Returns:
        {company_key: [announcements]}
    """
    keys = company_keys or sorted({oem.nse_symbol for oem in get_all_active()})
    results = {}

    for key in keys:
        logger.info(f"Fetching announcements: {key}")
        try:
            announcements = fetch_all_announcements(key, from_date, to_date)
            results[key] = announcements
        except Exception as e:
            logger.exception(f"Unhandled error fetching {key}: {e}")
            results[key] = []

        # polite delay between companies
        time.sleep(random.uniform(1.0, 2.5))

    total = sum(len(v) for v in results.values())
    logger.info(f"Fetch complete: {total} announcements across {len(keys)} companies")
    return results
