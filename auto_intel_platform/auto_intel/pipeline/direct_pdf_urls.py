"""
pipeline/direct_pdf_urls.py — Known direct PDF URL patterns per OEM
====================================================================
Problem: Most OEM websites are JavaScript-rendered. requests + BeautifulSoup
cannot see PDF links because the page renders them client-side in React/JS.

Solution: Each OEM uses predictable PDF naming conventions. Instead of
scraping the IR page, we generate the expected PDF URL directly and try
to download it. If the PDF loads (HTTP 200), we skip the IR page scrape.

Why this works:
  - PDFs are static files served from CDN / object storage
  - They are not JS-rendered — direct HTTP GET always works
  - The URL pattern is consistent month-to-month for each OEM

Usage:
  from pipeline.direct_pdf_urls import build_candidate_urls
  urls = build_candidate_urls("MARUTI", 2025, 4)
  # returns list of (url, oem_key, year, month) sorted most-likely-first
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import NamedTuple

MONTH_NAMES = [
    "", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
MONTH_SHORT = [
    "", "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
]


class PdfCandidate(NamedTuple):
    url:      str
    oem_key:  str
    year:     int
    month:    int
    priority: int   # lower = try first


def _m(n: int) -> str:
    """Full month name, title-cased."""
    return MONTH_NAMES[n].capitalize()


def _ms(n: int) -> str:
    """Short month name, title-cased."""
    return MONTH_SHORT[n].capitalize()


def _mu(n: int) -> str:
    """Full month name, upper-cased."""
    return MONTH_NAMES[n].upper()


# ── Per-OEM PDF URL builders ──────────────────────────────────────────────────
# Each function returns a list of candidate URLs for that OEM/year/month.
# We try them in order and use the first that returns HTTP 200.
#
# URL patterns are derived from publicly available past press releases.
# No authentication, no login, no API key required.

def _maruti_urls(y: int, m: int) -> list[str]:
    """
    Maruti Suzuki: PDFs uploaded to Azure Blob Storage.
    Pattern observed: Sales_Highlights_{Month}_{Year}.pdf
    Also sometimes on marutistorage.blob.core.windows.net
    """
    mn = _m(m)
    ms = _ms(m)
    return [
        f"https://marutistorage.blob.core.windows.net/saleshighlights/Sales_Highlights_{mn}_{y}.pdf",
        f"https://www.marutisuzuki.com/api/Uploads/SalesData/Sales_Highlights_{mn}_{y}.pdf",
        f"https://www.marutisuzuki.com/api/Uploads/PressRelease/Sales_{mn}_{y}.pdf",
        f"https://marutistorage.blob.core.windows.net/saleshighlights/Sales-Highlights-{mn}-{y}.pdf",
    ]


def _tatamotors_urls(y: int, m: int) -> list[str]:
    """Tata Motors: press releases on tatamotors.com."""
    mn = _m(m)
    ms = _ms(m).lower()
    return [
        f"https://www.tatamotors.com/wp-content/uploads/{y}/{m:02d}/tata-motors-sales-{ms}-{y}.pdf",
        f"https://www.tatamotors.com/wp-content/uploads/{y}/{m:02d}/tata-motors-{ms}-{y}-sales.pdf",
        f"https://www.tatamotors.com/wp-content/uploads/{y}/{m:02d}/{ms}-{y}-sales.pdf",
    ]


def _mahindra_urls(y: int, m: int) -> list[str]:
    """Mahindra: press releases on mahindra.com."""
    mn = _m(m)
    ms = _ms(m)
    return [
        f"https://www.mahindra.com/resources/pdf/{y}/{ms.lower()}/mahindra-auto-sales-{ms.lower()}-{y}.pdf",
        f"https://www.mahindra.com/resources/pdf/Mahindra-Auto-Sales-{mn}-{y}.pdf",
    ]


def _bajaj_urls(y: int, m: int) -> list[str]:
    """Bajaj Auto: very consistent naming on bajajauto.com."""
    mn = _m(m)
    ms = _ms(m)
    y2 = str(y)[2:]
    return [
        f"https://www.bajajauto.com/media/pdf/Bajaj_Auto_Sales_{mn}_{y}.pdf",
        f"https://www.bajajauto.com/media/pdf/Bajaj-Auto-Sales-{mn}-{y}.pdf",
        f"https://bajajauto.com/investors/press-releases/Bajaj_Auto_Sales_{mn}_{y}.pdf",
    ]


def _hero_urls(y: int, m: int) -> list[str]:
    """Hero MotoCorp: IR section on heromotocorp.com."""
    mn = _m(m)
    ms = _ms(m)
    return [
        f"https://www.heromotocorp.com/content/dam/hero-motocorp/investor-relations/press-release/Sales-{mn}-{y}.pdf",
        f"https://www.heromotocorp.com/content/dam/hero-motocorp/press-release/Hero-MotoCorp-Sales-{mn}-{y}.pdf",
        f"https://www.heromotocorp.com/en-in/uploads/press_release/Hero_MotoCorp_{mn}_{y}_Sales.pdf",
    ]


def _tvs_urls(y: int, m: int) -> list[str]:
    """TVS Motor: IR releases on tvsmotor.com."""
    mn = _m(m)
    ms = _ms(m)
    return [
        f"https://www.tvsmotor.com/media/pdf/Sales-Report-{mn}-{y}.pdf",
        f"https://www.tvsmotor.com/investor-relations/press-releases/TVS-Sales-{mn}-{y}.pdf",
    ]


def _ashokley_urls(y: int, m: int) -> list[str]:
    """Ashok Leyland: IR on ashokleyland.com."""
    mn = _m(m)
    ms = _ms(m)
    return [
        f"https://www.ashokleyland.com/media/pdf/Sales_Data_{mn}_{y}.pdf",
        f"https://www.ashokleyland.com/content/dam/al/investor-relations/press-releases/Sales-{mn}-{y}.pdf",
    ]


def _escorts_urls(y: int, m: int) -> list[str]:
    """Escorts Kubota: tractor sales on escortskubota.com."""
    mn = _m(m)
    return [
        f"https://www.escortskubota.com/media/pdf/Escorts-Kubota-Tractor-Sales-{mn}-{y}.pdf",
        f"https://www.escortskubota.com/investor-relations/press-releases/tractor-sales-{mn.lower()}-{y}.pdf",
    ]


def _eicher_urls(y: int, m: int) -> list[str]:
    """Eicher / Royal Enfield: eicherworld.com."""
    mn = _m(m)
    ms = _ms(m)
    return [
        f"https://www.eicherworld.com/media/royal-enfield/sales/{y}/RE-Sales-{mn}-{y}.pdf",
        f"https://www.eicherworld.com/investors/press-release/Royal_Enfield_Sales_{mn}_{y}.pdf",
    ]


def _ola_electric_urls(y: int, m: int) -> list[str]:
    """Ola Electric: investors.olaelectric.com."""
    mn = _m(m)
    ms = _ms(m)
    return [
        f"https://investors.olaelectric.com/media/pdf/Ola-Electric-Sales-{mn}-{y}.pdf",
        f"https://investors.olaelectric.com/news-and-events/Ola_Electric_{mn}_{y}_Sales.pdf",
    ]


# ── Registry ──────────────────────────────────────────────────────────────────

_BUILDERS: dict[str, callable] = {
    "MARUTI":         _maruti_urls,
    "TATAMOTORS_PV":  _tatamotors_urls,
    "TATAMOTORS_CV":  _tatamotors_urls,
    "MAHINDRA_AUTO":  _mahindra_urls,
    "MAHINDRA_FARM":  _mahindra_urls,
    "BAJAJ":          _bajaj_urls,
    "HEROMOTOCO":     _hero_urls,
    "TVS":            _tvs_urls,
    "ASHOKLEY":       _ashokley_urls,
    "ESCORTS":        _escorts_urls,
    "EICHER":         _eicher_urls,
    "OLA_ELECTRIC":   _ola_electric_urls,
}


def build_candidate_urls(oem_key: str, year: int, month: int) -> list[PdfCandidate]:
    """
    Return a list of candidate PDF URLs for the given OEM/year/month,
    sorted by priority (try index 0 first).

    Example:
        urls = build_candidate_urls("MARUTI", 2025, 4)
        for c in urls:
            resp = requests.head(c.url, timeout=10)
            if resp.status_code == 200:
                # download and parse this PDF
    """
    builder = _BUILDERS.get(oem_key)
    if not builder:
        return []
    raw = builder(year, month)
    return [
        PdfCandidate(url=u, oem_key=oem_key, year=year, month=month, priority=i)
        for i, u in enumerate(raw)
    ]


def try_find_pdf(oem_key: str, year: int, month: int,
                 timeout: int = 10) -> str | None:
    """
    Try each candidate URL with a HEAD request.
    Returns the first URL that responds with HTTP 200, or None.
    Logs each attempt.
    """
    import logging
    import requests

    logger = logging.getLogger(__name__)
    candidates = build_candidate_urls(oem_key, year, month)

    if not candidates:
        logger.warning(f"[DirectPDF] No URL templates for {oem_key}")
        return None

    for c in candidates:
        try:
            resp = requests.head(c.url, timeout=timeout, allow_redirects=True,
                                 headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                logger.info(f"[DirectPDF] {oem_key} {year}-{month:02d}: found → {c.url}")
                return c.url
            logger.debug(f"[DirectPDF] {oem_key}: {resp.status_code} {c.url}")
        except Exception as e:
            logger.debug(f"[DirectPDF] {oem_key}: error {e} on {c.url}")

    logger.info(f"[DirectPDF] {oem_key} {year}-{month:02d}: no direct PDF found, fallback to IR page scrape")
    return None


if __name__ == "__main__":
    # Quick test: print candidate URLs for current month
    today = datetime.today()
    from datetime import timedelta
    prior = (today.replace(day=1) - timedelta(days=1))
    y, m = prior.year, prior.month

    print(f"\nCandidate PDF URLs for {y}-{m:02d}:\n")
    for oem_key in _BUILDERS:
        candidates = build_candidate_urls(oem_key, y, m)
        print(f"  {oem_key}:")
        for c in candidates:
            print(f"    [{c.priority}] {c.url}")
        print()
