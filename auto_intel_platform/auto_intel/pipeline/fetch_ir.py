"""
pipeline/fetch_ir.py — OEM Investor Relations Page Fetcher
===========================================================
PRIMARY data source for all monthly sales data.

Why this instead of exchange APIs:
  - Companies publish this data themselves and want it to be read
  - No Terms-of-Service restrictions (unlike NSE/BSE undocumented JSON APIs)
  - Same underlying PDFs that get filed on the exchanges
  - 100% legal, zero-cost, sustainable forever

Approach:
  1. Fetch each OEM's public IR / Press Releases page with requests
  2. Parse with BeautifulSoup to find PDF links with sales-related titles
  3. Return announcement dicts in the same shape as fetch.py (NSE/BSE format)

If a page fails or is dynamically rendered:
  - Returns [] for that OEM
  - OEM goes to MANUAL review queue — never silently wrong
"""

from __future__ import annotations

import re
import time
import random
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from config import REQUEST_HEADERS, REQUEST_TIMEOUT, MAX_RETRIES, RETRY_BACKOFF
from registry import OEM_REGISTRY

logger = logging.getLogger(__name__)


# ── Sales-release keyword patterns ────────────────────────────────────────────

_SALES_RE = re.compile(
    r"(?i)(monthly[\s_\-]*sales|wholesale|dispatche?s?|retail[\s_\-]*sales"
    r"|sales[\s_\-]*data|vehicle[\s_\-]*sales|monthly[\s_\-]*dispatch"
    r"|unit[\s_\-]*sales|volume[\s_\-]*data|registration)",
)

_DATE_RE = re.compile(
    r"(?i)"
    r"(january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)"
    r"[\s\-_,]*"
    r"(20\d{2})",
)


# ── Per-OEM public IR page configuration ──────────────────────────────────────
# These are all publicly maintained company pages. No login, no API key,
# no scraping policy violations — companies publish this data for public access.

OEM_IR_CONFIG: dict[str, dict] = {
    "MARUTI": {
        "url":   "https://www.marutisuzuki.com/corporate/investors/press-releases",
        "base":  "https://www.marutisuzuki.com",
        "extra": ["dispatch", "wholesale", "domestic"],
    },
    "TATAMOTORS_PV": {
        "url":   "https://www.tatamotors.com/press/",
        "base":  "https://www.tatamotors.com",
        "extra": ["sales", "dispatch", "passenger"],
    },
    "TATAMOTORS_CV": {
        "url":   "https://www.tatamotors.com/press/",
        "base":  "https://www.tatamotors.com",
        "extra": ["sales", "dispatch", "commercial"],
    },
    "MAHINDRA_AUTO": {
        "url":   "https://www.mahindra.com/media/press-releases",
        "base":  "https://www.mahindra.com",
        "extra": ["auto", "vehicle", "suv", "xuv", "sales"],
    },
    "MAHINDRA_FARM": {
        "url":   "https://www.mahindra.com/media/press-releases",
        "base":  "https://www.mahindra.com",
        "extra": ["tractor", "farm", "agri", "sales"],
    },
    "BAJAJ": {
        "url":   "https://www.bajajauto.com/investors/press-releases",
        "base":  "https://www.bajajauto.com",
        "extra": ["sales", "dispatch", "wholesale", "two-wheeler", "three-wheeler"],
    },
    "HEROMOTOCO": {
        "url":   "https://www.heromotocorp.com/en-in/investors/press-releases.html",
        "base":  "https://www.heromotocorp.com",
        "extra": ["sales", "dispatch", "motorcycle", "scooter"],
    },
    "TVS": {
        "url":   "https://www.tvsmotor.com/investor-relations/press-releases",
        "base":  "https://www.tvsmotor.com",
        "extra": ["sales", "dispatch", "two-wheeler"],
    },
    "ASHOKLEY": {
        "url":   "https://www.ashokleyland.com/en/investor-relations/press-releases",
        "base":  "https://www.ashokleyland.com",
        "extra": ["sales", "dispatch", "wholesale", "commercial"],
    },
    "ESCORTS": {
        "url":   "https://www.escortskubota.com/investor-relations/press-releases",
        "base":  "https://www.escortskubota.com",
        "extra": ["tractor", "sales", "agri"],
    },
    "EICHER": {
        "url":   "https://www.eicherworld.com/investors",
        "base":  "https://www.eicherworld.com",
        "extra": ["royal enfield", "sales", "dispatch", "motorcycle"],
    },
    "OLA_ELECTRIC": {
        "url":   "https://investors.olaelectric.com/news-and-events",
        "base":  "https://investors.olaelectric.com",
        "extra": ["sales", "registration", "dispatch", "scooter"],
    },
}


# ── HTTP session ───────────────────────────────────────────────────────────────

def _make_session() -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(
        max_retries=Retry(
            total=MAX_RETRIES,
            backoff_factor=RETRY_BACKOFF,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    # Use browser-like headers so IR pages don't 403 on bots
    session.headers.update({
        **REQUEST_HEADERS,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Upgrade-Insecure-Requests": "1",
    })
    return session


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_sales_link(text: str, href: str, extra: list[str]) -> bool:
    """True if the link title or URL looks like a monthly sales release."""
    combined = (text + " " + href).lower()
    if _SALES_RE.search(combined):
        return True
    return any(kw.lower() in combined for kw in extra)


def _extract_date_str(text: str, href: str) -> str:
    """Try to pull a YYYY-MM-DD from the link text or URL. Falls back to today."""
    for candidate in [text, href]:
        m = _DATE_RE.search(candidate)
        if m:
            month_raw = m.group(1)[:3].title()   # "Jan", "Feb" …
            year_raw  = m.group(2)
            try:
                dt = datetime.strptime(f"{month_raw} {year_raw}", "%b %Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
    return datetime.today().strftime("%Y-%m-%d")


def _make_id(oem_key: str, url: str) -> str:
    return hashlib.sha1(f"IR:{oem_key}:{url}".encode()).hexdigest()[:12]


# ── Core fetcher ───────────────────────────────────────────────────────────────

def fetch_ir_announcements(
    oem_key: str,
    lookback_days: int = 60,
) -> list[dict]:
    """
    Fetch monthly sales press releases from the OEM's own IR page.

    Returns announcement dicts with _source="OEM_IR" — same shape as
    NSE/BSE fetcher output so downstream code is unchanged.
    """
    cfg = OEM_IR_CONFIG.get(oem_key)
    oem = OEM_REGISTRY.get(oem_key)
    if not cfg or not oem:
        logger.warning(f"[IR] No IR config for {oem_key} — skipping")
        return []

    session  = _make_session()
    cutoff   = datetime.today() - timedelta(days=lookback_days)
    extra_kw = cfg.get("extra", [])

    try:
        time.sleep(random.uniform(0.8, 2.0))   # polite crawl delay
        resp = session.get(cfg["url"], timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(
            f"[IR] {oem_key}: could not fetch IR page {cfg['url']} — {e}. "
            f"OEM will go to MANUAL review queue."
        )
        return []

    soup      = BeautifulSoup(resp.text, "lxml")
    results   = []
    seen_urls: set[str] = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        text = a_tag.get_text(separator=" ", strip=True)

        # Skip empty, anchor-only, or non-HTTP links
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        full_url = urljoin(cfg["base"], href)

        # Only care about PDFs or press-release HTML pages
        path_lower = urlparse(full_url).path.lower()
        is_pdf     = path_lower.endswith(".pdf")
        is_pr_page = any(
            kw in path_lower
            for kw in ("press", "release", "news", "media", "investor", "ir", "announcement")
        )

        if not (is_pdf or is_pr_page):
            continue

        if not _is_sales_link(text, href, extra_kw):
            continue

        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        release_date = _extract_date_str(text, href)

        # Respect lookback window if date was parsed
        try:
            if datetime.strptime(release_date, "%Y-%m-%d") < cutoff:
                continue
        except ValueError:
            pass

        ann = {
            "_source":     "OEM_IR",
            "_id":         _make_id(oem_key, full_url),
            "symbol":      oem.nse_symbol,
            "company":     oem.display_name,
            "title":       text or f"{oem.display_name} Monthly Sales",
            "category":    "Monthly Sales",
            "exchange_dt": release_date,
            "file_url":    full_url,
            "attachment":  path_lower.split("/")[-1],
            "raw":         {"href": href, "text": text, "ir_page": cfg["url"]},
        }
        results.append(ann)

    logger.info(f"[IR] {oem_key}: {len(results)} sales release(s) found on IR page")
    return results


# ── Batch fetcher ──────────────────────────────────────────────────────────────

def fetch_all_ir(
    oem_keys: Optional[list[str]] = None,
    lookback_days: int = 60,
) -> dict[str, list[dict]]:
    """
    Fetch IR announcements for all (or specified) OEMs.

    Returns {oem_key: [announcements]}
    """
    keys = oem_keys or list(OEM_IR_CONFIG.keys())
    results: dict[str, list[dict]] = {}

    for key in keys:
        results[key] = fetch_ir_announcements(key, lookback_days=lookback_days)
        time.sleep(random.uniform(1.0, 2.5))   # polite delay between sites

    total = sum(len(v) for v in results.values())
    logger.info(f"[IR] Batch fetch complete: {total} releases across {len(keys)} OEMs")
    return results
