"""
parsers/tata.py — Tata Motors Normalizer
=========================================
Handles TATAMOTORS_CV and TATAMOTORS_PV separately.
Tata has the most complex press release structure of any Indian OEM:
  - CV section: SCV, ICV, MHCV Trucks, MHCV Buses, Sub-Total CV
  - PV section: Passenger Vehicles, EV sub-line
  - Format changed in FY21, FY23 (EV added prominently)

Format versions:
  V1 (pre-FY21): CV + PV in one table, 4 columns
  V2 (FY21-FY22): Separate CV/PV blocks, 5 columns
  V3 (FY23+):    EV row added to PV block, 6 columns
"""

import re
import logging
from typing import Optional
import pandas as pd

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from schema import NormalizedRow, GranularRow, ParserStatus, ExtractionMethod, Segment

logger = logging.getLogger(__name__)

# ── CV sub-segment map ────────────────────────────────────────────────────────
CV_CATEGORY_MAP = {
    "scv cargo":     "SCV",  "scv":        "SCV",
    "ace":           "SCV",  "super ace":  "SCV",
    "icv":           "ICV",  "ultra":      "ICV",
    "intermediate":  "ICV",
    "mhcv truck":    "MHCV", "heavy":      "MHCV",
    "prima":         "MHCV", "signa":      "MHCV",
    "mhcv bus":      "Bus",  "bus":        "Bus",
    "pick up":       "SCV",  "pickup":     "SCV",
    "passenger":     "PV",   "ev":         "EV",
    "nexon":         "EV",   "tigor ev":   "EV",
}

# ── PV sub-segment map ────────────────────────────────────────────────────────
PV_CATEGORY_MAP = {
    "nexon":    "UV",   "safari":   "UV",
    "harrier":  "UV",   "punch":    "UV",
    "curvv":    "UV",
    "tiago":    "Hatch","altroz":   "Hatch",
    "tigor":    "Sedan",
    "nexon ev": "EV",   "tigor ev": "EV",
    "ev":       "EV",
}

DOMESTIC_ALIASES = ["domestic", "dom", "dom.", "domestic units"]
EXPORT_ALIASES   = ["export", "exports", "exp", "exp.", "international"]
TOTAL_ALIASES    = ["total", "grand total", "net", "overall"]
CV_SECTION_TOKENS = ["commercial vehicle", "cv", "scv", "mhcv", "lcv", "truck", "bus"]
PV_SECTION_TOKENS = ["passenger vehicle", "pv", "utility vehicle", "hatchback", "sedan"]


def detect_format_version(tables: list, full_text: str) -> str:
    text_lower = full_text.lower()
    if "nexon ev" in text_lower or "tigor ev" in text_lower or "ev sales" in text_lower:
        return "V3"
    if "sub-total" in text_lower or "sub total" in text_lower:
        return "V2"
    return "V1"


def normalize(
    tables: list,
    full_text: str,
    filing_month_year: str,
    filing_date: str,
    source: str,
    pdf_path: str,
    target_key: str = "TATAMOTORS_CV",
) -> tuple[Optional[NormalizedRow], list, float]:
    """
    Main entry point. target_key determines CV or PV extraction.
    """
    version = detect_format_version(tables, full_text)
    logger.info(f"[TATA] Format version: {version}, target: {target_key}")

    is_cv = (target_key == "TATAMOTORS_CV")
    section_tokens = CV_SECTION_TOKENS if is_cv else PV_SECTION_TOKENS
    segment = Segment.CV if is_cv else Segment.PV
    cat_map = CV_CATEGORY_MAP if is_cv else PV_CATEGORY_MAP

    # Try each table
    for candidate in tables:
        df = candidate.get("df")
        if df is None or df.empty:
            continue

        # Check if this table is relevant to the target segment
        table_text = df.to_string().lower()
        if not any(tok in table_text for tok in section_tokens):
            continue

        result = _try_parse_table(
            df, version, filing_month_year, filing_date, source,
            candidate, target_key, segment, cat_map
        )
        if result:
            norm, granular, conf = result
            logger.info(f"[TATA:{target_key}] total={norm.total}, conf={conf:.2f}")
            return norm, granular, conf

    # Fallback: find CV/PV totals in text
    logger.warning(f"[TATA:{target_key}] Table parse failed — text fallback")
    return _text_fallback(full_text, filing_month_year, filing_date,
                          source, target_key, segment, is_cv)


def _try_parse_table(df, version, filing_month_year, filing_date,
                     source, candidate, target_key, segment, cat_map):
    try:
        col_map = _detect_columns(df)
        if not col_map.get("total") and not col_map.get("domestic"):
            return None

        dom_col = col_map.get("domestic")
        exp_col = col_map.get("exports")
        tot_col = col_map.get("total")
        cat_col = col_map.get("category")

        total_row = _find_subtotal_row(df, cat_col, segment)
        if not total_row:
            return None

        domestic = _to_int(total_row.get(dom_col)) if dom_col else None
        exports  = _to_int(total_row.get(exp_col))  if exp_col else None
        total    = _to_int(total_row.get(tot_col))  if tot_col else None

        if total is None and domestic is not None and exports is not None:
            total = domestic + exports
        if total is None or total == 0:
            return None

        confidence = _compute_confidence(domestic, exports, total, candidate["score"])

        granular = _build_granular(df, cat_col, dom_col, exp_col, tot_col,
                                   filing_month_year, target_key, segment, cat_map)

        norm = NormalizedRow(
            company_key       = target_key,
            segment           = segment,
            filing_month_year = filing_month_year,
            domestic          = domestic,
            exports           = exports,
            total             = total,
            source            = source,
            filing_date       = filing_date,
            parser_version    = f"TATA_{version}",
            extraction_method = candidate.get("method", ExtractionMethod.PDFPLUMBER_TABLE),
            parser_status     = ParserStatus.CLEAN if confidence >= 0.65 else ParserStatus.FLAGGED,
            confidence_score  = confidence,
        )
        return norm, granular, confidence

    except Exception as e:
        logger.debug(f"[TATA] Table parse error: {e}")
        return None


def _detect_columns(df: pd.DataFrame) -> dict:
    col_map = {}
    cols_lower = {c: str(c).lower().strip() for c in df.columns}

    for col, col_str in cols_lower.items():
        non_num = sum(1 for v in df[col] if not _is_numeric(str(v)))
        if non_num / max(len(df), 1) > 0.6 and "category" not in col_map:
            col_map["category"] = col

    for col, col_str in cols_lower.items():
        for a in DOMESTIC_ALIASES:
            if a in col_str and "domestic" not in col_map:
                col_map["domestic"] = col
        for a in EXPORT_ALIASES:
            if a in col_str and "exports" not in col_map:
                col_map["exports"] = col
        for a in TOTAL_ALIASES:
            if a in col_str and "ytd" not in col_str and "total" not in col_map:
                col_map["total"] = col

    # Position-based fallback
    if not col_map.get("domestic"):
        num_cols = [c for c in df.columns
                    if sum(_is_numeric(str(v)) for v in df[c]) / max(len(df),1) > 0.5]
        if len(num_cols) >= 2:
            col_map["domestic"] = num_cols[0]
            col_map["total"]    = num_cols[-1]
            if len(num_cols) >= 3:
                col_map["exports"] = num_cols[1]

    return col_map


def _find_subtotal_row(df: pd.DataFrame, cat_col, segment: str) -> Optional[dict]:
    """Find the subtotal row for the relevant segment."""
    is_cv = (segment == Segment.CV)

    subtotal_labels = (
        ["sub-total cv", "total cv", "total commercial", "commercial vehicle total", "total"]
        if is_cv else
        ["sub-total pv", "total pv", "total passenger", "passenger vehicle total",
         "total utility", "grand total", "total"]
    )

    for _, row in df.iterrows():
        cat = str(row.get(cat_col, "")).lower().strip() if cat_col else ""
        for label in subtotal_labels:
            if label in cat:
                return row.to_dict()

    # Last numeric row fallback
    for _, row in df.iloc[::-1].iterrows():
        numeric_count = sum(_is_numeric(str(v)) for v in row.values)
        if numeric_count >= 2:
            return row.to_dict()

    return None


def _build_granular(df, cat_col, dom_col, exp_col, tot_col,
                    filing_month_year, target_key, segment, cat_map) -> list:
    rows = []
    if not cat_col:
        return rows

    for _, row in df.iterrows():
        cat_val = str(row.get(cat_col, "")).strip()
        if not cat_val or cat_val.lower() in ("nan", ""):
            continue
        cat_lower = cat_val.lower()
        if any(t in cat_lower for t in ["sub-total", "grand total", "total"]):
            continue

        norm_cat = "Other"
        for key, mapped in cat_map.items():
            if key in cat_lower:
                norm_cat = mapped
                break

        units = None
        if tot_col:
            units = _to_int(row.get(tot_col))
        elif dom_col:
            d = _to_int(row.get(dom_col)) or 0
            e = _to_int(row.get(exp_col)) or 0 if exp_col else 0
            units = d + e

        if units is not None:
            rows.append(GranularRow(
                company_key         = target_key,
                segment             = segment,
                filing_month_year   = filing_month_year,
                raw_category        = cat_val,
                normalized_category = norm_cat,
                units               = units,
            ))
    return rows


def _text_fallback(text, filing_month_year, filing_date, source, target_key, segment, is_cv):
    section_kw = "commercial" if is_cv else "passenger"
    patterns = [
        rf"{section_kw}[^\d]{{0,60}}([\d,]+)\s+([\d,]+)\s+([\d,]+)",
        r"total[^\d]{0,30}([\d,]+)\s+([\d,]+)\s+([\d,]+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                d, e, t = _to_int(m.group(1)), _to_int(m.group(2)), _to_int(m.group(3))
                if t and t > 100:
                    norm = NormalizedRow(
                        company_key       = target_key,
                        segment           = segment,
                        filing_month_year = filing_month_year,
                        domestic=d, exports=e, total=t,
                        source=source, filing_date=filing_date,
                        parser_version    = "TATA_TEXT_FALLBACK",
                        extraction_method = ExtractionMethod.REGEX,
                        parser_status     = ParserStatus.FLAGGED,
                        confidence_score  = 0.40,
                    )
                    return norm, [], 0.40
            except Exception:
                pass
    return None, [], 0.0


def _compute_confidence(domestic, exports, total, table_score) -> float:
    score = table_score * 0.4
    if total and total > 0:     score += 0.25
    if domestic is not None:    score += 0.15
    if exports is not None:     score += 0.10
    if domestic and exports and total:
        tol = abs((domestic + exports) - total) / max(total, 1)
        if tol < 0.02:   score += 0.10
        elif tol < 0.05: score += 0.05
    return min(round(score, 4), 1.0)


def _to_int(val) -> Optional[int]:
    if val is None: return None
    s = str(val).strip().replace(",", "").replace(" ", "")
    if s in ("-", "–", "—", "nil", "n.a.", "na", ""): return 0
    try:    return int(float(s))
    except: return None


def _is_numeric(s: str) -> bool:
    s = s.strip().replace(",", "")
    if s in ("-", "–", "nil", ""): return True
    try:    float(s); return True
    except: return False
