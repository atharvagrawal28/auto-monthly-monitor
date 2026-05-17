"""
parsers/maruti.py — Maruti Suzuki Normalizer
=============================================
Detects format version, maps columns, returns NormalizedRow + GranularRows.

Maruti press release structure (consistent since FY20):
  Row labels: Alto, WagonR, Dzire, Swift, Baleno, Brezza, etc.
  Columns: Current Month Domestic | Current Month Export | Total | YTD columns
  Grand Total row at bottom.

Format versions:
  V1 (pre-FY22): 6-column layout, no EV mention
  V2 (FY22+):    7-column layout, includes Jimny/Fronx, YTD columns
"""

import re
import logging
from typing import Optional
import pandas as pd

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from schema import NormalizedRow, GranularRow, ParserStatus, ExtractionMethod, Segment

logger = logging.getLogger(__name__)

COMPANY_KEY = "MARUTI"
SEGMENT     = Segment.PV

# ── Sub-brand → normalized category map ──────────────────────────────────────
MARUTI_MODEL_MAP = {
    # Mini / Entry
    "alto":         "Mini",
    "s-presso":     "Mini",
    # Compact
    "wagonr":       "Compact",
    "wagon r":      "Compact",
    "celerio":      "Compact",
    "dzire":        "Compact",
    "swift":        "Compact",
    # Mid
    "baleno":       "Mid",
    "ignis":        "Mid",
    # SUV / Utility
    "brezza":       "UV",
    "vitara brezza":"UV",
    "grand vitara": "UV",
    "jimny":        "UV",
    "fronx":        "UV",
    "invicto":      "UV",
    # MPV
    "ertiga":       "MPV",
    "xl6":          "MPV",
    # Van
    "eeco":         "Van",
    "super carry":  "Van",
    # Total rows
    "total":        "Total",
    "grand total":  "Total",
}

DOMESTIC_ALIASES  = ["domestic", "dom.", "dom", "domestic sales"]
EXPORT_ALIASES    = ["export", "exports", "exp.", "overseas"]
TOTAL_ALIASES     = ["total", "grand total", "net total"]


def detect_format_version(tables: list, full_text: str) -> str:
    """
    Detect Maruti press release format version.
    Returns: "V1" | "V2" | "UNKNOWN"
    """
    text_lower = full_text.lower()

    if any(m in text_lower for m in ["jimny", "fronx", "invicto", "grand vitara"]):
        return "V2"
    if "baleno" in text_lower and "brezza" in text_lower:
        return "V1"

    # Column count heuristic
    for t in tables[:3]:
        df = t.get("df")
        if df is not None and len(df.columns) >= 7:
            return "V2"
        if df is not None and len(df.columns) in (5, 6):
            return "V1"

    return "V1"  # safe default


def normalize(
    tables: list,
    full_text: str,
    filing_month_year: str,
    filing_date: str,
    source: str,
    pdf_path: str,
) -> tuple[Optional[NormalizedRow], list[GranularRow], float]:
    """
    Main entry point called by the pipeline.

    Returns:
        (NormalizedRow | None, list of GranularRow, confidence_score)
    """
    version = detect_format_version(tables, full_text)
    logger.info(f"[MARUTI] Detected format version: {version}")

    # Try each candidate table from best to worst
    for candidate in tables:
        df = candidate.get("df")
        if df is None or df.empty:
            continue

        result = _try_parse_table(df, version, filing_month_year,
                                   filing_date, source, candidate)
        if result:
            norm_row, granular, confidence = result
            logger.info(f"[MARUTI] Parsed successfully: total={norm_row.total}, confidence={confidence:.2f}")
            return norm_row, granular, confidence

    # Fallback: regex from text
    logger.warning("[MARUTI] Table parse failed — trying text fallback")
    result = _text_fallback(full_text, filing_month_year, filing_date, source)
    if result:
        return result

    logger.error("[MARUTI] All extraction methods failed")
    return None, [], 0.0


def _try_parse_table(
    df: pd.DataFrame,
    version: str,
    filing_month_year: str,
    filing_date: str,
    source: str,
    candidate: dict,
) -> Optional[tuple]:
    """Attempt to parse a single DataFrame as a Maruti sales table."""
    try:
        col_map = _detect_columns(df)
        if not col_map:
            return None

        dom_col  = col_map.get("domestic")
        exp_col  = col_map.get("exports")
        tot_col  = col_map.get("total")
        cat_col  = col_map.get("category")

        if not tot_col and not dom_col:
            return None

        # Find Grand Total row
        totals = _find_total_row(df, cat_col)
        if not totals:
            return None

        domestic = _to_int(totals.get(dom_col)) if dom_col else None
        exports  = _to_int(totals.get(exp_col))  if exp_col else None
        total    = _to_int(totals.get(tot_col))  if tot_col else None

        # Derive missing values
        if total is None and domestic is not None and exports is not None:
            total = domestic + exports
        if domestic is None and total is not None and exports is not None:
            domestic = total - exports

        if total is None or total == 0:
            return None

        # Validation: arithmetic check
        confidence = _compute_confidence(domestic, exports, total, candidate["score"])

        # Build granular rows
        granular = _build_granular(df, cat_col, dom_col, exp_col, tot_col,
                                    filing_month_year)

        norm_row = NormalizedRow(
            company_key        = COMPANY_KEY,
            segment            = SEGMENT,
            filing_month_year  = filing_month_year,
            domestic           = domestic,
            exports            = exports,
            total              = total,
            source             = source,
            filing_date        = filing_date,
            parser_version     = f"MARUTI_{version}",
            extraction_method  = candidate.get("method", ExtractionMethod.PDFPLUMBER_TABLE),
            parser_status      = ParserStatus.CLEAN if confidence >= 0.7 else ParserStatus.FLAGGED,
            confidence_score   = confidence,
        )

        return norm_row, granular, confidence

    except Exception as e:
        logger.debug(f"[MARUTI] Table parse error: {e}")
        return None


def _detect_columns(df: pd.DataFrame) -> dict:
    """
    Detect which column maps to domestic, exports, total, and category.
    Works on column headers — case insensitive, alias-aware.
    """
    col_map = {}
    cols_lower = {c: str(c).lower().strip() for c in df.columns}

    # Find category column (leftmost text-dominant column)
    for col, col_str in cols_lower.items():
        if col_str in ("", "nan"):
            continue
        # Check if column is mostly non-numeric
        non_num = sum(1 for v in df[col] if not _is_numeric(str(v)))
        if non_num / max(len(df), 1) > 0.6:
            col_map["category"] = col
            break

    # Match metric columns
    for col, col_str in cols_lower.items():
        for alias in DOMESTIC_ALIASES:
            if alias in col_str:
                col_map["domestic"] = col
                break
        for alias in EXPORT_ALIASES:
            if alias in col_str:
                col_map["exports"] = col
                break
        for alias in TOTAL_ALIASES:
            if alias in col_str and "ytd" not in col_str:
                col_map["total"] = col
                break

    # Heuristic: if headers not labelled, use numeric column positions
    if not col_map.get("domestic") and not col_map.get("total"):
        numeric_cols = [
            c for c in df.columns
            if sum(_is_numeric(str(v)) for v in df[c]) / max(len(df), 1) > 0.5
        ]
        if len(numeric_cols) >= 2:
            col_map["domestic"] = numeric_cols[0]
            col_map["total"]    = numeric_cols[-1]
            if len(numeric_cols) >= 3:
                col_map["exports"] = numeric_cols[1]

    return col_map


def _find_total_row(df: pd.DataFrame, cat_col) -> Optional[dict]:
    """Find the grand total row in the table."""
    for _, row in df.iterrows():
        cat_val = str(row.get(cat_col, "")).lower() if cat_col else ""
        if any(t in cat_val for t in ["grand total", "total", "overall"]):
            return row.to_dict()

    # Last row fallback (Maruti often puts total last)
    if len(df) > 0:
        last = df.iloc[-1]
        if sum(_is_numeric(str(v)) for v in last.values) >= 2:
            return last.to_dict()

    return None


def _build_granular(df, cat_col, dom_col, exp_col, tot_col, filing_month_year) -> list:
    """Build GranularRow list from model-level rows."""
    rows = []
    if not cat_col:
        return rows

    for _, row in df.iterrows():
        cat_val = str(row.get(cat_col, "")).strip()
        if not cat_val or cat_val.lower() in ("nan", ""):
            continue

        cat_lower = cat_val.lower()
        if any(t in cat_lower for t in ["grand total", "total"]):
            continue

        # Find best matching normalized category
        norm_cat = "Other"
        for key, mapped in MARUTI_MODEL_MAP.items():
            if key in cat_lower:
                norm_cat = mapped
                break

        units = None
        if tot_col:
            units = _to_int(row.get(tot_col))
        elif dom_col:
            d = _to_int(row.get(dom_col))
            e = _to_int(row.get(exp_col)) if exp_col else 0
            units = (d or 0) + (e or 0)

        if units is not None:
            rows.append(GranularRow(
                company_key         = COMPANY_KEY,
                segment             = SEGMENT,
                filing_month_year   = filing_month_year,
                raw_category        = cat_val,
                normalized_category = norm_cat,
                units               = units,
            ))

    return rows


def _text_fallback(text, filing_month_year, filing_date, source):
    """Last resort: regex extraction from raw text."""
    patterns = [
        r"(?:total|grand\s+total)[^\d]*([\d,]+)\s+([\d,]+)\s+([\d,]+)",
        r"([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*(?:total|grand)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                d = _to_int(m.group(1))
                e = _to_int(m.group(2))
                t = _to_int(m.group(3))
                if t and t > 100:
                    norm_row = NormalizedRow(
                        company_key        = COMPANY_KEY,
                        segment            = SEGMENT,
                        filing_month_year  = filing_month_year,
                        domestic           = d, exports = e, total = t,
                        source             = source,
                        filing_date        = filing_date,
                        parser_version     = "MARUTI_TEXT_FALLBACK",
                        extraction_method  = ExtractionMethod.REGEX,
                        parser_status      = ParserStatus.FLAGGED,
                        confidence_score   = 0.45,
                    )
                    return norm_row, [], 0.45
            except Exception:
                pass
    return None


def _compute_confidence(domestic, exports, total, table_score) -> float:
    score = table_score * 0.4  # table detection quality

    if total and total > 0:
        score += 0.25
    if domestic is not None:
        score += 0.15
    if exports is not None:
        score += 0.10

    # Arithmetic validation
    if domestic is not None and exports is not None and total is not None:
        derived = domestic + exports
        tolerance = abs(derived - total) / max(total, 1)
        if tolerance < 0.02:
            score += 0.10   # arithmetic perfect
        elif tolerance < 0.05:
            score += 0.05
        # tolerance > 0.10 → no bonus

    return min(round(score, 4), 1.0)


def _to_int(val) -> Optional[int]:
    if val is None:
        return None
    s = str(val).strip().replace(",", "").replace(" ", "")
    if s in ("-", "–", "—", "nil", "n.a.", "na", ""):
        return 0
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _is_numeric(s: str) -> bool:
    s = s.strip().replace(",", "")
    if s in ("-", "–", "nil", ""):
        return True
    try:
        float(s)
        return True
    except ValueError:
        return False
