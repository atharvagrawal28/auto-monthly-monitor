"""
parsers/generic.py — Generic OEM Normalizer
============================================
Used for: Bajaj, Hero, TVS, Ashok Leyland, Escorts, Eicher, Ola Electric.
These OEMs have simpler, more consistent press releases than Tata/M&M.
Still fully dynamic — no page number assumptions.
"""

import re
import logging
from typing import Optional
import pandas as pd

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from schema import NormalizedRow, GranularRow, ParserStatus, ExtractionMethod, Segment
from registry import OEM_REGISTRY

logger = logging.getLogger(__name__)

DOMESTIC_ALIASES = ["domestic", "dom", "dom.", "home market", "domestic sales"]
EXPORT_ALIASES   = ["export", "exports", "exp", "exp.", "overseas", "international"]
TOTAL_ALIASES    = ["total", "grand total", "overall", "net total", "combined"]


def normalize(
    tables: list,
    full_text: str,
    filing_month_year: str,
    filing_date: str,
    source: str,
    pdf_path: str,
    target_key: str = "BAJAJ",
) -> tuple[Optional[NormalizedRow], list, float]:

    oem_config = OEM_REGISTRY.get(target_key)
    if not oem_config:
        logger.error(f"[GENERIC] Unknown OEM key: {target_key}")
        return None, [], 0.0

    primary_segment = oem_config.segments[0] if oem_config.segments else "2W"
    logger.info(f"[GENERIC:{target_key}] segment={primary_segment}, tables={len(tables)}")

    for candidate in tables:
        df = candidate.get("df")
        if df is None or df.empty:
            continue

        result = _try_parse_table(df, filing_month_year, filing_date, source,
                                   candidate, target_key, primary_segment, oem_config)
        if result:
            norm, granular, conf = result
            logger.info(f"[GENERIC:{target_key}] total={norm.total}, conf={conf:.2f}")
            return norm, granular, conf

    logger.warning(f"[GENERIC:{target_key}] All tables failed — text fallback")
    return _text_fallback(full_text, filing_month_year, filing_date,
                          source, target_key, primary_segment)


def _try_parse_table(df, filing_month_year, filing_date, source,
                     candidate, target_key, segment, oem_config):
    try:
        col_map = _detect_columns(df)
        if not col_map.get("total") and not col_map.get("domestic"):
            return None

        dom_col = col_map.get("domestic")
        exp_col = col_map.get("exports")
        tot_col = col_map.get("total")
        cat_col = col_map.get("category")

        total_row = _find_total_row(df, cat_col)
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
        granular   = _build_granular(df, cat_col, tot_col, filing_month_year,
                                      target_key, segment, oem_config)

        norm = NormalizedRow(
            company_key       = target_key,
            segment           = segment,
            filing_month_year = filing_month_year,
            domestic=domestic, exports=exports, total=total,
            source=source, filing_date=filing_date,
            parser_version    = f"{target_key}_V1",
            extraction_method = candidate.get("method", ExtractionMethod.PDFPLUMBER_TABLE),
            parser_status     = ParserStatus.CLEAN if confidence >= 0.6 else ParserStatus.FLAGGED,
            confidence_score  = confidence,
        )
        return norm, granular, confidence

    except Exception as e:
        logger.debug(f"[GENERIC:{target_key}] Parse error: {e}")
        return None


def _detect_columns(df: pd.DataFrame) -> dict:
    col_map = {}
    cols_lower = {c: str(c).lower().strip() for c in df.columns}

    # Category = leftmost mostly-text column
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

    if not col_map.get("domestic") and not col_map.get("total"):
        num_cols = [c for c in df.columns
                    if sum(_is_numeric(str(v)) for v in df[c]) / max(len(df), 1) > 0.5]
        if len(num_cols) >= 2:
            col_map["domestic"] = num_cols[0]
            col_map["total"]    = num_cols[-1]
            if len(num_cols) >= 3:
                col_map["exports"] = num_cols[1]

    return col_map


def _find_total_row(df: pd.DataFrame, cat_col) -> Optional[dict]:
    total_labels = ["grand total", "total", "overall", "net total", "combined total"]

    for _, row in df.iterrows():
        cat = str(row.get(cat_col, "")).lower().strip() if cat_col else ""
        for label in total_labels:
            if label in cat:
                return row.to_dict()

    # Last numeric row
    for _, row in df.iloc[::-1].iterrows():
        if sum(_is_numeric(str(v)) for v in row.values) >= 2:
            return row.to_dict()

    return None


def _build_granular(df, cat_col, tot_col, filing_month_year,
                    target_key, segment, oem_config) -> list:
    rows = []
    if not cat_col or not tot_col:
        return rows

    for _, row in df.iterrows():
        cat_val = str(row.get(cat_col, "")).strip()
        if not cat_val or cat_val.lower() in ("nan", ""):
            continue
        if any(t in cat_val.lower() for t in ["grand total", "total", "sub-total"]):
            continue

        units = _to_int(row.get(tot_col))
        if units is None:
            continue

        # Best-effort normalization using segment keywords
        norm_cat = _infer_category(cat_val.lower(), segment)

        rows.append(GranularRow(
            company_key=target_key, segment=segment,
            filing_month_year=filing_month_year,
            raw_category=cat_val, normalized_category=norm_cat,
            units=units,
        ))
    return rows


def _infer_category(cat_lower: str, segment: str) -> str:
    """Best-effort category inference from raw string."""
    if segment == Segment.TW or segment == "2W":
        if any(k in cat_lower for k in ["motorcycle", "bike"]): return "Motorcycle"
        if any(k in cat_lower for k in ["scooter", "scooterette"]): return "Scooter"
        if "moped" in cat_lower: return "Moped"
        if "electric" in cat_lower or "ev" in cat_lower: return "EV"
    if segment == Segment.CV:
        if any(k in cat_lower for k in ["hcv", "heavy", "truck"]): return "HCV"
        if any(k in cat_lower for k in ["lcv", "light"]): return "LCV"
        if "bus" in cat_lower: return "Bus"
    if segment == Segment.TRACTOR:
        return "Tractor"
    return "Other"


def _text_fallback(text, filing_month_year, filing_date, source, target_key, segment):
    patterns = [
        r"total[^\d]{0,30}([\d,]+)\s+([\d,]+)\s+([\d,]+)",
        r"grand\s+total[^\d]{0,20}([\d,]+)\s+([\d,]+)\s+([\d,]+)",
        r"([\d,]{4,})\s+([\d,]+)\s+([\d,]{4,})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                d, e, t = _to_int(m.group(1)), _to_int(m.group(2)), _to_int(m.group(3))
                if t and t > 100:
                    norm = NormalizedRow(
                        company_key=target_key, segment=segment,
                        filing_month_year=filing_month_year,
                        domestic=d, exports=e, total=t,
                        source=source, filing_date=filing_date,
                        parser_version=f"{target_key}_TEXT_FALLBACK",
                        extraction_method=ExtractionMethod.REGEX,
                        parser_status=ParserStatus.FLAGGED,
                        confidence_score=0.35,
                    )
                    return norm, [], 0.35
            except Exception:
                pass
    return None, [], 0.0


def _compute_confidence(domestic, exports, total, table_score) -> float:
    score = table_score * 0.4
    if total and total > 0:  score += 0.25
    if domestic is not None: score += 0.15
    if exports is not None:  score += 0.10
    if domestic and exports and total:
        tol = abs((domestic + exports) - total) / max(total, 1)
        if tol < 0.02:   score += 0.10
        elif tol < 0.05: score += 0.05
    return min(round(score, 4), 1.0)


def _to_int(val) -> Optional[int]:
    if val is None: return None
    s = str(val).strip().replace(",", "").replace(" ", "")
    if s in ("-", "–", "nil", "n.a.", "na", ""): return 0
    try:    return int(float(s))
    except: return None


def _is_numeric(s: str) -> bool:
    s = s.strip().replace(",", "")
    if s in ("-", "–", "nil", ""): return True
    try:    float(s); return True
    except: return False
