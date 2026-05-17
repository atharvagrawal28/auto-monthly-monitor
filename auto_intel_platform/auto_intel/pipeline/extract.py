"""
pipeline/extract.py — Generic Extraction Engine
================================================
Scans ALL pages of a PDF. Never hardcodes page numbers.
Scores every table by numeric density + structure.
Returns ranked list of candidate tables for the normalizer.
"""

import re
import logging
from pathlib import Path
from typing import Optional
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    logger.warning("pdfplumber not installed. PDF extraction unavailable.")


# ─── Table scoring weights ────────────────────────────────────────────────────
MIN_ROWS             = 3
MIN_COLS             = 3
MIN_NUMERIC_DENSITY  = 0.25   # 25% of cells must be numeric
TIME_COL_PATTERNS    = [
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
    r"\b20\d{2}\b",
    r"\bq[1-4]\b",
    r"ytd",
    r"period",
    r"month",
]
SALES_HEADER_TOKENS = [
    "domestic", "export", "total", "wholesale", "dispatch",
    "sales", "unit", "vehicle", "motorcycle", "scooter",
    "passenger", "commercial", "tractor", "electric",
]


# ─── Main extraction entry point ─────────────────────────────────────────────

def extract_from_pdf(pdf_path: str) -> dict:
    """
    Extract all candidate tables + full text from a PDF.

    Returns:
        {
          "tables":      list of scored CandidateTable dicts (sorted best first),
          "full_text":   str,
          "page_count":  int,
          "method":      str,
          "error":       str or None,
        }
    """
    path = Path(pdf_path)
    if not path.exists():
        return _empty_result(f"File not found: {pdf_path}")

    if not HAS_PDFPLUMBER:
        return _empty_result("pdfplumber not installed")

    try:
        return _extract_pdfplumber(str(path))
    except Exception as e:
        logger.exception(f"Extraction failed for {pdf_path}: {e}")
        return _empty_result(str(e))


def _extract_pdfplumber(pdf_path: str) -> dict:
    """Full pdfplumber extraction — scans every page."""
    all_tables  = []
    full_text   = []
    page_count  = 0

    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        logger.info(f"Scanning {page_count} pages: {pdf_path}")

        for page_num, page in enumerate(pdf.pages, start=1):
            # ── Text ──────────────────────────────────────────────────────────
            text = page.extract_text() or ""
            full_text.append(text)

            # ── Tables ────────────────────────────────────────────────────────
            tables = page.extract_tables()
            if not tables:
                # Try with different table settings for borderless tables
                tables = page.extract_tables({
                    "vertical_strategy":   "text",
                    "horizontal_strategy": "text",
                }) or []

            for t_idx, raw_table in enumerate(tables):
                if not raw_table:
                    continue
                df = _raw_to_df(raw_table)
                if df is None:
                    continue

                score, reasons = _score_table(df)
                if score > 0.1:   # minimal bar — normalizer does final filtering
                    all_tables.append({
                        "df":          df,
                        "page":        page_num,
                        "table_index": t_idx,
                        "score":       round(score, 4),
                        "score_reasons": reasons,
                        "row_count":   len(df),
                        "col_count":   len(df.columns),
                        "method":      "PDFPLUMBER_TABLE",
                    })

    # Sort best candidates first
    all_tables.sort(key=lambda x: x["score"], reverse=True)

    combined_text = "\n".join(full_text)

    # If no tables found, try text-based extraction
    if not all_tables:
        text_tables = _extract_text_tables(combined_text)
        all_tables.extend(text_tables)

    logger.info(
        f"Extracted {len(all_tables)} candidate tables, "
        f"{page_count} pages, {len(combined_text)} chars"
    )

    return {
        "tables":     all_tables,
        "full_text":  combined_text,
        "page_count": page_count,
        "method":     "PDFPLUMBER_TABLE" if all_tables else "PDFPLUMBER_TEXT",
        "error":      None,
    }


def _raw_to_df(raw_table: list) -> Optional[pd.DataFrame]:
    """Convert raw pdfplumber table (list of lists) to cleaned DataFrame."""
    if not raw_table or len(raw_table) < 2:
        return None

    # Clean cells
    cleaned = []
    for row in raw_table:
        cleaned_row = [_clean_cell(c) for c in row]
        if any(c for c in cleaned_row):  # skip fully empty rows
            cleaned.append(cleaned_row)

    if len(cleaned) < 2:
        return None

    # Use first non-empty row as header
    header = cleaned[0]
    data   = cleaned[1:]

    # Handle duplicate/empty column names
    seen = {}
    safe_header = []
    for i, h in enumerate(header):
        h = h or f"col_{i}"
        if h in seen:
            seen[h] += 1
            h = f"{h}_{seen[h]}"
        else:
            seen[h] = 0
        safe_header.append(h)

    try:
        df = pd.DataFrame(data, columns=safe_header)
        df = df.dropna(how="all").reset_index(drop=True)
        return df if len(df) >= MIN_ROWS else None
    except Exception:
        return None


def _clean_cell(cell) -> str:
    """Clean a single table cell value."""
    if cell is None:
        return ""
    s = str(cell).strip()
    # Remove newlines within cells
    s = re.sub(r"\s+", " ", s)
    # Remove thousands separators to help numeric detection
    return s


def _score_table(df: pd.DataFrame) -> tuple[float, list]:
    """
    Score a table on likelihood of being a sales data table.
    Returns (score 0-1, list of reason strings).
    """
    score   = 0.0
    reasons = []

    rows, cols = len(df), len(df.columns)

    # ── Size checks ───────────────────────────────────────────────────────────
    if rows < MIN_ROWS or cols < MIN_COLS:
        return 0.0, ["too small"]

    score += 0.10
    reasons.append(f"+0.10 size OK ({rows}r×{cols}c)")

    # ── Numeric density ───────────────────────────────────────────────────────
    total_cells  = rows * cols
    numeric_cells = 0
    for col in df.columns:
        for val in df[col]:
            if _is_numeric(str(val)):
                numeric_cells += 1

    density = numeric_cells / total_cells if total_cells else 0
    if density >= MIN_NUMERIC_DENSITY:
        score += 0.25
        reasons.append(f"+0.25 numeric density {density:.0%}")
    elif density >= 0.15:
        score += 0.10
        reasons.append(f"+0.10 partial numeric density {density:.0%}")

    # ── Header / column analysis ──────────────────────────────────────────────
    header_text = " ".join(str(c).lower() for c in df.columns)

    for token in SALES_HEADER_TOKENS:
        if token in header_text:
            score += 0.08
            reasons.append(f"+0.08 header token '{token}'")
            break  # one bonus per table

    # Time-period column presence
    for pat in TIME_COL_PATTERNS:
        if re.search(pat, header_text, re.IGNORECASE):
            score += 0.12
            reasons.append(f"+0.12 time col pattern")
            break

    # ── Row content analysis ──────────────────────────────────────────────────
    all_text = " ".join(
        str(v).lower()
        for col in df.columns
        for v in df[col]
    )
    for token in SALES_HEADER_TOKENS:
        if token in all_text:
            score += 0.05
            reasons.append(f"+0.05 row content token '{token}'")
            break

    # ── Multi-period structure ────────────────────────────────────────────────
    # If 2+ columns look like months/years → strong signal
    time_cols = 0
    for col in df.columns:
        col_str = str(col).lower()
        for pat in TIME_COL_PATTERNS:
            if re.search(pat, col_str, re.IGNORECASE):
                time_cols += 1
                break
    if time_cols >= 2:
        score += 0.15
        reasons.append(f"+0.15 multi-period cols ({time_cols})")

    return min(score, 1.0), reasons


def _is_numeric(s: str) -> bool:
    """Check if string represents a number (handles commas, dashes for zero)."""
    s = s.strip().replace(",", "").replace(" ", "")
    if s in ("-", "–", "—", "nil", "n.a.", "na", ""):
        return True  # zero/missing numeric placeholder
    try:
        float(s)
        return True
    except ValueError:
        return False


def _extract_text_tables(text: str) -> list:
    """
    Fallback: attempt to extract tabular data from plain text using regex.
    Returns list of candidate table dicts (method=PDFPLUMBER_TEXT).
    """
    results = []
    lines = text.split("\n")

    # Look for blocks where multiple lines have similar numeric patterns
    numeric_line_re = re.compile(r"[\w\s/()&-]{3,40}\s+[\d,]+\s+[\d,]+")
    block = []

    for line in lines:
        line = line.strip()
        if numeric_line_re.search(line):
            block.append(line)
        else:
            if len(block) >= MIN_ROWS:
                df = _text_block_to_df(block)
                if df is not None:
                    results.append({
                        "df":          df,
                        "page":        -1,
                        "table_index": -1,
                        "score":       0.40,
                        "score_reasons": ["text fallback"],
                        "row_count":   len(df),
                        "col_count":   len(df.columns),
                        "method":      "PDFPLUMBER_TEXT",
                    })
            block = []

    return results


def _text_block_to_df(lines: list) -> Optional[pd.DataFrame]:
    """Convert a block of aligned text lines into a DataFrame."""
    rows = []
    for line in lines:
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) >= 2:
            rows.append(parts)

    if not rows:
        return None

    max_cols = max(len(r) for r in rows)
    padded   = [r + [""] * (max_cols - len(r)) for r in rows]
    cols     = [f"col_{i}" for i in range(max_cols)]

    try:
        df = pd.DataFrame(padded, columns=cols)
        return df if len(df) >= MIN_ROWS else None
    except Exception:
        return None


def _empty_result(error: str) -> dict:
    return {
        "tables":     [],
        "full_text":  "",
        "page_count": 0,
        "method":     None,
        "error":      error,
    }
