"""
pipeline/filter.py
==================
Smart relevance filter for auto sales press release detection.

Philosophy:
  - Positive + negative signal scoring (not just keyword match)
  - Recency-aware (monthly filings cluster around month-end)
  - Segment hint extraction for downstream use
  - Explains its decisions via a reason string
"""

import re
import logging
from datetime import datetime
from typing import Optional

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from config import COMPANIES, SEGMENT_CONFIG

logger = logging.getLogger(__name__)

# ─── MONTH TOKENS ─────────────────────────────────────────────────────────────
MONTH_TOKENS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# ─── POSITIVE SIGNALS ─────────────────────────────────────────────────────────
# Each tuple: (regex_pattern, score_contribution)
POSITIVE_SIGNALS = [
    (r"\bmonthly\s+sales?\b",                   0.30),
    (r"\bsales?\s+(data|update|figures?|no\.?s?)\b", 0.25),
    (r"\b(wholesale|retail)\s+(dispatche?s?|sales?)\b", 0.25),
    (r"\btotal\s+(dispatche?s?|sales?|vehicles?)\b", 0.20),
    (r"\b(domestic|export)\s+(sales?|dispatche?s?)\b", 0.15),
    (r"\bvehicle\s+(sales?|dispatche?s?|production)\b", 0.15),
    (r"\b(passenger|commercial)\s+vehicle\b",   0.10),
    (r"\b2w\b|\btwo.?wheeler\b",                0.10),
    (r"\btractor\s+sales?\b",                   0.10),
    (r"\b(motorcycle|scooter)\s+(sales?|dispatche?s?)\b", 0.10),
    (r"\bev\s+sales?\b|\belectric\s+vehicle\b", 0.08),
]

# ─── NEGATIVE SIGNALS ─────────────────────────────────────────────────────────
NEGATIVE_SIGNALS = [
    (r"\binvestor\s+presentation\b",             -0.80),
    (r"\bearnings\b",                            -0.70),
    (r"\bfinancial\s+results?\b",                -0.70),
    (r"\bquarterly\s+results?\b",                -0.70),
    (r"\bannual\s+report\b",                     -0.60),
    (r"\bq[1-4]\s+(results?|earnings?)\b",       -0.60),
    (r"\bclarification\b",                       -0.50),
    (r"\bagm\b|\begm\b",                         -0.50),
    (r"\bprospectus\b|\bipo\b",                  -0.90),
    (r"\bboard\s+meeting\b",                     -0.40),
    (r"\bdividend\b",                            -0.40),
    (r"\brights?\s+issue\b",                     -0.80),
    (r"\bbuyback\b",                             -0.50),
    (r"\bpress\s+release\s+on\s+(eps|pat|revenue)\b", -0.60),
    (r"\bQ\d\s*FY\d{2}\s+results?\b",            -0.70),
]

# ─── MUST-HAVE PATTERN ────────────────────────────────────────────────────────
# At least one of these must be present for the announcement to be considered
MONTH_REFERENCE = re.compile(
    r"\b(" + "|".join(MONTH_TOKENS.keys()) + r")\b"
    r"|\b20\d{2}\b",
    re.IGNORECASE
)


# ─── MAIN FILTER ──────────────────────────────────────────────────────────────

def score_announcement(announcement: dict, company_key: str) -> dict:
    """
    Score a single announcement for relevance to monthly auto sales.

    Returns the announcement dict enriched with:
        _relevance_score  : float [0, 1]
        _is_relevant      : bool
        _segment_hints    : list of segment keys detected
        _reference_month  : detected month name or None
        _reference_year   : detected year or None
        _filter_reason    : human-readable explanation
    """
    title    = announcement.get("title", "").lower().strip()
    category = announcement.get("category", "").lower().strip()
    text     = f"{title} {category}"

    config = COMPANIES.get(company_key, {})

    # ── Company-level exclude override ────────────────────────────────────────
    for kw in config.get("exclude_keywords", []):
        if kw.lower() in text:
            return _tag(announcement, 0.0, False, [], None, None,
                        f"Hard exclude match: '{kw}'")

    # ── Score computation ─────────────────────────────────────────────────────
    score = 0.0
    reasons = []

    # Positive
    for pattern, weight in POSITIVE_SIGNALS:
        if re.search(pattern, text, re.IGNORECASE):
            score += weight
            reasons.append(f"+{weight:.2f} [{pattern[:30]}]")

    # Company-specific keyword bonus
    for kw in config.get("keywords", []):
        if kw.lower() in text:
            score += 0.10
            reasons.append(f"+0.10 [company kw: {kw}]")
            break  # single bonus

    # Negative
    for pattern, weight in NEGATIVE_SIGNALS:
        if re.search(pattern, text, re.IGNORECASE):
            score += weight   # weight is negative
            reasons.append(f"{weight:.2f} [{pattern[:30]}]")

    # Company-specific title regex
    title_regex = config.get("title_regex")
    if title_regex and re.search(title_regex, title):
        score += 0.20
        reasons.append("+0.20 [title regex match]")

    score = max(0.0, min(1.0, score))

    # ── Month / year extraction ───────────────────────────────────────────────
    ref_month, ref_year = _extract_period(title)

    # Penalize if no month reference at all
    if not MONTH_REFERENCE.search(title):
        score *= 0.6
        reasons.append("×0.6 [no month/year in title]")

    # ── Segment detection ─────────────────────────────────────────────────────
    segment_hints = _detect_segments(text, config.get("segments", []))

    is_relevant = score >= 0.35

    reason_str = " | ".join(reasons) or "no signals matched"
    return _tag(announcement, round(score, 4), is_relevant,
                segment_hints, ref_month, ref_year, reason_str)


def _tag(ann, score, is_rel, segs, month, year, reason):
    ann = ann.copy()
    ann["_relevance_score"] = score
    ann["_is_relevant"]     = is_rel
    ann["_segment_hints"]   = segs
    ann["_reference_month"] = month
    ann["_reference_year"]  = year
    ann["_filter_reason"]   = reason
    return ann


def _extract_period(text: str) -> tuple[Optional[str], Optional[int]]:
    """Extract month name and year from title string."""
    text_lower = text.lower()
    month_name = None
    year = None

    for tok, _ in MONTH_TOKENS.items():
        if re.search(r"\b" + tok + r"\b", text_lower):
            month_name = tok.capitalize()
            break

    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        year = int(year_match.group(1))

    return month_name, year


def _detect_segments(text: str, allowed_segments: list) -> list[str]:
    """Detect which segments are mentioned in the announcement text."""
    detected = []
    for seg_key, seg_config in SEGMENT_CONFIG.items():
        if seg_key not in allowed_segments:
            continue
        for kw in seg_config["keywords"]:
            if kw.lower() in text:
                if seg_key not in detected:
                    detected.append(seg_key)
                break
    return detected


# ─── BATCH FILTER ─────────────────────────────────────────────────────────────

def filter_announcements(
    company_key: str,
    announcements: list[dict],
    threshold: float = 0.35,
) -> list[dict]:
    """
    Filter and score a list of announcements for a company.

    Returns only relevant ones, sorted by score descending.
    """
    scored = []
    for ann in announcements:
        scored_ann = score_announcement(ann, company_key)
        if scored_ann["_is_relevant"]:
            scored.append(scored_ann)
            logger.debug(
                f"RELEVANT ({scored_ann['_relevance_score']:.2f}): "
                f"{scored_ann.get('title', '')[:60]}"
            )
        else:
            logger.debug(
                f"FILTERED ({scored_ann['_relevance_score']:.2f}): "
                f"{scored_ann.get('title', '')[:60]}"
            )

    # Sort by relevance score
    scored.sort(key=lambda x: x["_relevance_score"], reverse=True)

    # Deduplicate by file URL (same PDF linked multiple times)
    seen_urls = set()
    unique = []
    for ann in scored:
        url = ann.get("file_url", "")
        if url and url in seen_urls:
            continue
        seen_urls.add(url)
        unique.append(ann)

    logger.info(
        f"[Filter] {company_key}: {len(announcements)} → {len(unique)} relevant"
    )
    return unique


def filter_all_companies(
    raw_announcements: dict[str, list[dict]]
) -> dict[str, list[dict]]:
    """
    Filter all companies' announcements.

    Args:
        raw_announcements: {company_key: [announcements]}

    Returns:
        {company_key: [relevant_announcements]}
    """
    filtered = {}
    for key, announcements in raw_announcements.items():
        filtered[key] = filter_announcements(key, announcements)
    return filtered
