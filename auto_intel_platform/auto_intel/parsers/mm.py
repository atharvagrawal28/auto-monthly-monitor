"""
parsers/mm.py — Mahindra & Mahindra Normalizer
===============================================
Handles MAHINDRA_AUTO and MAHINDRA_FARM separately.
M&M sometimes combines Auto + Farm in one press release.
The parser must detect which sections exist and split them.

Format versions:
  V1: Combined table, Auto first then Farm
  V2: Separate sections with clear headers
"""

import re
import logging
from typing import Optional
import pandas as pd

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from schema import NormalizedRow, GranularRow, ParserStatus, ExtractionMethod, Segment

logger = logging.getLogger(__name__)

AUTO_CATEGORY_MAP = {
    "utility vehicle": "UV",    "suv":         "UV",
    "xuv":             "UV",    "scorpio":      "UV",
    "thar":            "UV",    "bolero":       "UV",
    "be ":             "EV",    "xe ":          "EV",
    "electric":        "EV",
    "pick-up":         "CV",    "pickup":       "CV",
    "supro":           "CV",    "bolero pickup":"CV",
    "three wheeler":   "3W",    "e-alfa":       "3W",
}

FARM_CATEGORY_MAP = {
    "tractor":         "Tractor",
    "farm":            "Tractor",
    "below 30":        "Sub30HP",
    "30-40":           "30-40HP",
    "above 40":        "Above40HP",
    "arjun":           "Tractor",
    "yuvo":            "Tractor",
}

AUTO_SECTION_MARKERS  = ["automotive", "auto", "utility vehicle", "suv", "passenger", "xuv", "scorpio"]
FARM_SECTION_MARKERS  = ["farm", "tractor", "agri", "implement", "harvester"]
DOMESTIC_ALIASES = ["domestic", "dom", "dom."]
EXPORT_ALIASES   = ["export", "exports", "exp"]
TOTAL_ALIASES    = ["total", "grand total", "overall total"]


def detect_format_version(tables: list, full_text: str) -> str:
    text_lower = full_text.lower()
    if "automotive sector" in text_lower or "automotive division" in text_lower:
        return "V2"
    if "farm equipment" in text_lower and "utility vehicle" in text_lower:
        return "V1"
    return "V1"


def normalize(
    tables: list,
    full_text: str,
    filing_month_year: str,
    filing_date: str,
    source: str,
    pdf_path: str,
    target_key: str = "MAHINDRA_AUTO",
) -> tuple[Optional[NormalizedRow], list, float]:
    version = detect_format_version(tables, full_text)
    logger.info(f"[MM] Format: {version}, target: {target_key}")

    is_auto  = (target_key == "MAHINDRA_AUTO")
    segment  = Segment.PV if is_auto else Segment.TRACTOR
    section_markers = AUTO_SECTION_MARKERS if is_auto else FARM_SECTION_MARKERS
    cat_map  = AUTO_CATEGORY_MAP if is_auto else FARM_CATEGORY_MAP

    for candidate in tables:
        df = candidate.get("df")
        if df is None or df.empty:
            continue

        table_text = df.to_string().lower()
        if not any(m in table_text for m in section_markers):
            continue

        result = _try_parse_table(df, version, filing_month_year, filing_date,
                                   source, candidate, target_key, segment, cat_map, is_auto)
        if result:
            norm, granular, conf = result
            logger.info(f"[MM:{target_key}] total={norm.total}, conf={conf:.2f}")
            return norm, granular, conf

    logger.warning(f"[MM:{target_key}] Table parse failed — text fallback")
    return _text_fallback(full_text, filing_month_year, filing_date,
                          source, target_key, segment, is_auto)


def _try_parse_table(df, version, filing_month_year, filing_date, source,
                     candidate, target_key, segment, cat_map, is_auto):
    try:
        col_map = _detect_columns(df)
        if not col_map.get("total") and not col_map.get("domestic"):
            return None

        dom_col = col_map.get("domestic")
        exp_col = col_map.get("exports")
        tot_col = col_map.get("total")
        cat_col = col_map.get("category")

        total_row = _find_total_row(df, cat_col, is_auto)
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
        granular   = _build_granular(df, cat_col, dom_col, exp_col, tot_col,
                                      filing_month_year, target_key, segment, cat_map)

        norm = NormalizedRow(
            company_key       = target_key,
            segment           = segment,
            filing_month_year = filing_month_year,
            domestic=domestic, exports=exports, total=total,
            source=source, filing_date=filing_date,
            parser_version    = f"MM_{version}",
            extraction_method = candidate.get("method", ExtractionMethod.PDFPLUMBER_TABLE),
            parser_status     = ParserStatus.CLEAN if confidence >= 0.65 else ParserStatus.FLAGGED,
            confidence_score  = confidence,
        )
        return norm, granular, confidence

    except Exception as e:
        logger.debug(f"[MM] Parse error: {e}")
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

    if not col_map.get("domestic"):
        num_cols = [c for c in df.columns
                    if sum(_is_numeric(str(v)) for v in df[c]) / max(len(df),1) > 0.5]
        if len(num_cols) >= 2:
            col_map["domestic"] = num_cols[0]
            col_map["total"]    = num_cols[-1]
            if len(num_cols) >= 3:
                col_map["exports"] = num_cols[1]

    return col_map


def _find_total_row(df, cat_col, is_auto) -> Optional[dict]:
    labels_auto = ["total utility vehicles", "total automotive", "grand total auto",
                   "total vehicles", "grand total", "total"]
    labels_farm = ["total tractors", "total farm", "grand total farm",
                   "grand total", "total"]
    labels = labels_auto if is_auto else labels_farm

    for _, row in df.iterrows():
        cat = str(row.get(cat_col, "")).lower().strip() if cat_col else ""
        for label in labels:
            if label in cat:
                return row.to_dict()

    for _, row in df.iloc[::-1].iterrows():
        if sum(_is_numeric(str(v)) for v in row.values) >= 2:
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
        if any(t in cat_val.lower() for t in ["grand total", "total", "sub-total"]):
            continue

        norm_cat = "Other"
        for key, mapped in cat_map.items():
            if key in cat_val.lower():
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
                company_key=target_key, segment=segment,
                filing_month_year=filing_month_year,
                raw_category=cat_val, normalized_category=norm_cat, units=units,
            ))
    return rows


def _text_fallback(text, filing_month_year, filing_date, source, target_key, segment, is_auto):
    kw = r"automotive|utility|xuv|scorpio" if is_auto else r"tractor|farm"
    patterns = [
        rf"(?:{kw})[^\d]{{0,80}}([\d,]+)\s+([\d,]+)\s+([\d,]+)",
        r"grand\s+total[^\d]{0,30}([\d,]+)\s+([\d,]+)\s+([\d,]+)",
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
                        parser_version="MM_TEXT_FALLBACK",
                        extraction_method=ExtractionMethod.REGEX,
                        parser_status=ParserStatus.FLAGGED,
                        confidence_score=0.40,
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
    if s in ("-", "–", "nil", "n.a.", "na", ""): return 0
    try:    return int(float(s))
    except: return None


def _is_numeric(s: str) -> bool:
    s = s.strip().replace(",", "")
    if s in ("-", "–", "nil", ""): return True
    try:    float(s); return True
    except: return False
