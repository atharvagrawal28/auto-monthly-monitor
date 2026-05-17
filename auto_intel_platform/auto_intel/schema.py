"""
schema.py — Canonical Data Contract
=====================================
Single source of truth for all data structures.
PostgreSQL-ready from day one.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime
import hashlib, json

# ── Parser Status Enum ────────────────────────────────────────────────────────
class ParserStatus:
    CLEAN        = "CLEAN"         # passed all validations
    FLAGGED      = "FLAGGED"       # passed but anomaly detected
    NEEDS_REVIEW = "NEEDS_REVIEW"  # extraction/validation failed
    CONFLICT     = "CONFLICT"      # reconciliation mismatch >10%
    MANUAL       = "MANUAL"        # manually entered/corrected
    STALE        = "STALE"         # filing overdue, no data yet

# ── Extraction Method Enum ────────────────────────────────────────────────────
class ExtractionMethod:
    PDFPLUMBER_TABLE = "PDFPLUMBER_TABLE"
    PDFPLUMBER_TEXT  = "PDFPLUMBER_TEXT"
    CAMELOT          = "CAMELOT"
    REGEX            = "REGEX"
    MANUAL           = "MANUAL"

# ── Segment Enum ──────────────────────────────────────────────────────────────
class Segment:
    PV      = "PV"
    CV      = "CV"
    TW      = "2W"
    THREE_W = "3W"
    TRACTOR = "Tractor"
    EV      = "EV"

# ─────────────────────────────────────────────────────────────────────────────
# NORMALIZED ROW — one row per (company, segment, month)
# Primary key: (company_key, segment, filing_month_year)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class NormalizedRow:
    # Identity
    company_key:       str            # "MARUTI", "TATAMOTORS_CV"
    segment:           str            # Segment.*
    filing_month_year: str            # "2025-03"

    # Core metrics
    domestic:          Optional[int]  = None
    exports:           Optional[int]  = None
    total:             Optional[int]  = None

    # Growth (computed post-storage)
    yoy_pct:           Optional[float] = None
    mom_pct:           Optional[float] = None

    # Provenance
    source:            str  = "NSE"           # NSE | BSE
    filing_date:       str  = ""              # "2025-04-02"
    parser_version:    str  = ""              # "MARUTI_V2"
    extraction_method: str  = ExtractionMethod.PDFPLUMBER_TABLE
    parser_status:     str  = ParserStatus.NEEDS_REVIEW
    confidence_score:  float = 0.0

    # Integrity
    raw_row_hash:      str  = ""
    data_vintage:      str  = ""   # ISO timestamp when row was written
    last_updated:      str  = ""   # ISO timestamp of last modification

    # Review
    review_note:       str  = ""   # human note if NEEDS_REVIEW / MANUAL

    def __post_init__(self):
        if not self.data_vintage:
            self.data_vintage = datetime.utcnow().isoformat() + "Z"
        if not self.last_updated:
            self.last_updated = self.data_vintage
        if not self.raw_row_hash:
            self.raw_row_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = json.dumps({
            "company_key": self.company_key,
            "segment":     self.segment,
            "month":       self.filing_month_year,
            "domestic":    self.domestic,
            "exports":     self.exports,
            "total":       self.total,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def pk(self) -> tuple:
        return (self.company_key, self.segment, self.filing_month_year)


# ─────────────────────────────────────────────────────────────────────────────
# RAW ROW — immutable record of what was extracted from the PDF
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class RawRow:
    company_key:       str
    filing_month_year: str
    pdf_path:          str
    source_url:        str
    fetch_timestamp:   str
    parser_version:    str
    extraction_method: str
    raw_table:         list = field(default_factory=list)  # list of dicts
    raw_text_snippet:  str  = ""
    page_number:       int  = -1   # -1 = unknown/dynamic

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# GRANULAR ROW — sub-segment breakdown
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class GranularRow:
    company_key:        str
    segment:            str
    filing_month_year:  str
    raw_category:       str   # "SCV Cargo and Pickup"  ← preserve original
    normalized_category: str  # "SCV"                   ← our mapping
    units:              Optional[int] = None
    is_export:          bool = False
    notes:              str  = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# FILING STATUS — one row per (company, month) in filing calendar
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class FilingStatus:
    company_key:       str
    filing_month_year: str
    status:            str  = ParserStatus.STALE  # CLEAN|FLAGGED|NEEDS_REVIEW|CONFLICT|STALE
    filing_date:       str  = ""
    expected_by:       str  = ""    # "2025-04-05"
    pdf_url:           str  = ""
    notes:             str  = ""
    last_checked:      str  = field(default_factory=lambda: datetime.utcnow().isoformat()+"Z")

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# CSV COLUMN ORDER — enforced for all exports
# ─────────────────────────────────────────────────────────────────────────────
NORMALIZED_COLUMNS = [
    "company_key", "segment", "filing_month_year",
    "domestic", "exports", "total",
    "yoy_pct", "mom_pct",
    "source", "filing_date", "parser_version",
    "extraction_method", "parser_status", "confidence_score",
    "raw_row_hash", "data_vintage", "last_updated", "review_note",
]

GRANULAR_COLUMNS = [
    "company_key", "segment", "filing_month_year",
    "raw_category", "normalized_category",
    "units", "is_export", "notes",
]

FILING_STATUS_COLUMNS = [
    "company_key", "filing_month_year", "status",
    "filing_date", "expected_by", "pdf_url", "notes", "last_checked",
]
