"""
pipeline/fetch_fada.py — FADA Retail Registration Data Fetcher
===============================================================
Source: fada.in/media-press-releases/  (Federation of Automobile Dealers
        Associations of India)

Legal status: 100% legal. FADA publishes monthly retail data as public
press releases. No login, no API key, no ToS restrictions.

FADA data covers:
  - Retail vehicle registrations (what consumers actually buy from dealers)
  - Segment-wise: PV / 2W / 3W / CV / Tractor / EV (where reported)
  - Published around 1st–5th of each month for the prior month

This is kept COMPLETELY SEPARATE from the wholesale OEM pipeline.
Retail data lives in data/retail.csv — never merged with data/normalized.csv.
The only connection is in the dashboard's Retail Pulse page where wholesale
and retail are compared side-by-side to compute channel inventory.

Automation: same GitHub Actions schedule as OEM IR pages (4x/day on 1st-8th).
Cost: Free forever. FADA website is publicly accessible plain HTML.
"""

from __future__ import annotations

import re
import csv
import time
import random
import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import sys
import pathlib as _pl
sys.path.insert(0, str(_pl.Path(__file__).parent.parent))

from config import REQUEST_HEADERS, REQUEST_TIMEOUT, MAX_RETRIES, RETRY_BACKOFF

logger = logging.getLogger(__name__)

FADA_BASE         = "https://fada.in"
FADA_PRESS_URL    = "https://fada.in/media-press-releases/"
RETAIL_CSV        = _pl.Path(__file__).parent.parent / "data" / "retail.csv"

RETAIL_CSV_COLS = [
    "filing_month_year",   # "2025-10"
    "segment",             # "PV" | "2W" | "3W" | "CV" | "Tractor" | "EV"
    "retail_total",        # int — retail registrations
    "yoy_pct",             # float — YoY % from FADA report
    "source",              # "FADA"
    "filing_date",         # "YYYY-MM-DD" — date FADA published this
    "source_url",          # URL of the press release
    "notes",               # e.g. "includes electric scooters"
]

# Pattern to detect monthly retail press releases in FADA's page
_PR_RE = re.compile(
    r"(?i)(retail|registration|vehicle\s+sales|monthly\s+data"
    r"|automobile\s+sales|auto\s+sales)",
)

_DATE_RE = re.compile(
    r"(?i)"
    r"(january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)"
    r"[\s,\-]*"
    r"(20\d{2})",
)

# Segment keywords to extract from press-release text
_SEGMENT_PATTERNS = {
    "PV":      re.compile(r"(?i)(passenger\s+vehicle|pv)[:\s]+([0-9,]+)"),
    "2W":      re.compile(r"(?i)(two[\s-]?wheeler|2w)[:\s]+([0-9,]+)"),
    "3W":      re.compile(r"(?i)(three[\s-]?wheeler|3w)[:\s]+([0-9,]+)"),
    "CV":      re.compile(r"(?i)(commercial\s+vehicle|cv)[:\s]+([0-9,]+)"),
    "Tractor": re.compile(r"(?i)(tractor)[:\s]+([0-9,]+)"),
    "EV":      re.compile(r"(?i)(electric\s+vehicle|ev)[:\s]+([0-9,]+)"),
}

_YOY_PATTERN = re.compile(
    r"(?i)([\+\-]?\d+\.?\d*)\s*%\s*(yoy|y-o-y|year[- ]on[- ]year|growth|decline)",
)


# ── HTTP session ───────────────────────────────────────────────────────────────

def _session() -> requests.Session:
    s = requests.Session()
    s.mount("https://", HTTPAdapter(
        max_retries=Retry(
            total=MAX_RETRIES,
            backoff_factor=RETRY_BACKOFF,
            status_forcelist=[429, 500, 502, 503, 504],
        )
    ))
    s.headers.update({
        **REQUEST_HEADERS,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    })
    return s


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_month(text: str, href: str) -> Optional[str]:
    """Extract YYYY-MM from text or URL. Returns None if not found."""
    for src in [text, href]:
        m = _DATE_RE.search(src)
        if m:
            month_str = m.group(1)[:3].title()
            year_str  = m.group(2)
            try:
                dt = datetime.strptime(f"{month_str} {year_str}", "%b %Y")
                return dt.strftime("%Y-%m")
            except ValueError:
                pass
    return None


def _extract_segment_volumes(text: str) -> dict[str, int]:
    """
    Try to extract per-segment retail totals from press-release body text.
    Returns {segment: units} for whatever segments are mentioned.
    """
    volumes: dict[str, int] = {}
    for seg, pattern in _SEGMENT_PATTERNS.items():
        m = pattern.search(text)
        if m:
            raw = m.group(2).replace(",", "")
            try:
                volumes[seg] = int(raw)
            except ValueError:
                pass
    return volumes


def _extract_yoy(text: str) -> Optional[float]:
    """Extract headline YoY % from text."""
    m = _YOY_PATTERN.search(text)
    if m:
        try:
            val = float(m.group(1))
            return round(val / 100, 4)
        except ValueError:
            pass
    return None


def _make_id(url: str) -> str:
    return hashlib.sha1(f"FADA:{url}".encode()).hexdigest()[:12]


# ── Listing page fetcher ───────────────────────────────────────────────────────

def _fetch_press_release_links(lookback_days: int = 90) -> list[dict]:
    """
    Scrape FADA press-release listing page and return links to retail reports.
    """
    sess   = _session()
    cutoff = datetime.today() - timedelta(days=lookback_days)
    links  = []

    try:
        time.sleep(random.uniform(1.0, 2.0))
        resp = sess.get(FADA_PRESS_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[FADA] Could not fetch press-release listing: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(separator=" ", strip=True)

        if not href or href.startswith(("#", "mailto:", "tel:")):
            continue

        full_url = urljoin(FADA_BASE, href)

        if not _PR_RE.search(text + " " + href):
            continue

        month_str = _parse_month(text, href)
        if month_str:
            try:
                month_dt = datetime.strptime(month_str + "-01", "%Y-%m-%d")
                if month_dt < cutoff:
                    continue
            except ValueError:
                pass

        links.append({
            "url":        full_url,
            "text":       text,
            "month_str":  month_str,
        })

    # Deduplicate by URL
    seen: set[str] = set()
    deduped = []
    for lnk in links:
        if lnk["url"] not in seen:
            seen.add(lnk["url"])
            deduped.append(lnk)

    logger.info(f"[FADA] Found {len(deduped)} potential retail press releases")
    return deduped


# ── Per-release fetcher ────────────────────────────────────────────────────────

def _fetch_release_data(link: dict) -> list[dict]:
    """
    Fetch a single press release and extract segment retail volumes.
    Returns a list of retail row dicts (one per segment found).
    """
    sess = _session()
    url  = link["url"]
    try:
        time.sleep(random.uniform(0.8, 1.8))
        resp = sess.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[FADA] Could not fetch {url}: {e}")
        return []

    soup      = BeautifulSoup(resp.text, "lxml")
    body_text = soup.get_text(separator=" ")

    month_str    = link.get("month_str") or _parse_month(body_text, url)
    volumes      = _extract_segment_volumes(body_text)
    yoy          = _extract_yoy(body_text)
    filing_date  = datetime.today().strftime("%Y-%m-%d")

    if not month_str:
        logger.warning(f"[FADA] Could not determine month for {url}")
        return []

    rows = []
    for seg, total in volumes.items():
        rows.append({
            "filing_month_year": month_str,
            "segment":           seg,
            "retail_total":      total,
            "yoy_pct":           yoy,
            "source":            "FADA",
            "filing_date":       filing_date,
            "source_url":        url,
            "notes":             "",
        })

    if rows:
        logger.info(f"[FADA] {month_str}: extracted {len(rows)} segment rows from {url}")
    else:
        logger.warning(f"[FADA] {month_str}: no segment volumes parsed from {url}")

    return rows


# ── Main public function ───────────────────────────────────────────────────────

def fetch_fada_retail(lookback_days: int = 90) -> list[dict]:
    """
    Fetch FADA retail registration data.

    Returns:
        List of row dicts (one per segment per month found).
        Each row: filing_month_year, segment, retail_total, yoy_pct,
                  source, filing_date, source_url, notes
    """
    links = _fetch_press_release_links(lookback_days=lookback_days)
    all_rows: list[dict] = []

    for link in links:
        rows = _fetch_release_data(link)
        all_rows.extend(rows)
        time.sleep(random.uniform(0.5, 1.2))

    logger.info(f"[FADA] Total retail rows fetched: {len(all_rows)}")
    return all_rows


# ── Storage helpers ────────────────────────────────────────────────────────────

def load_retail() -> list[dict]:
    """Load existing retail.csv into a list of dicts."""
    if not RETAIL_CSV.exists():
        return []
    rows = []
    with open(RETAIL_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def save_retail(new_rows: list[dict]) -> int:
    """
    Upsert new_rows into retail.csv.
    Primary key: (filing_month_year, segment, source).
    Returns number of rows written.
    """
    RETAIL_CSV.parent.mkdir(parents=True, exist_ok=True)

    existing = {
        (r["filing_month_year"], r["segment"], r["source"]): r
        for r in load_retail()
    }
    for row in new_rows:
        pk = (row["filing_month_year"], row["segment"], row["source"])
        existing[pk] = row

    rows = sorted(existing.values(), key=lambda r: (r["filing_month_year"], r["segment"]))
    with open(RETAIL_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RETAIL_CSV_COLS)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    rows = fetch_fada_retail(lookback_days=90)
    written = save_retail(rows)
    print(f"FADA fetch complete: {len(rows)} new rows, {written} total in retail.csv")
