"""
Auto Industry Intelligence Platform — Master Configuration
==========================================================
Single source of truth for all companies, segments, keywords, and system settings.
"""

import os
from pathlib import Path

# ─── PROJECT ROOT ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR  = BASE_DIR / "logs"
RAW_DIR  = DATA_DIR / "raw"
NORM_DIR = DATA_DIR / "normalized"
GRAN_DIR = DATA_DIR / "granular"
PDF_DIR  = DATA_DIR / "pdfs"

for d in [RAW_DIR, NORM_DIR, GRAN_DIR, PDF_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── PARSER VERSION ───────────────────────────────────────────────────────────
PARSER_VERSION = "2.1.0"

# ─── NSE / BSE ENDPOINTS ──────────────────────────────────────────────────────
NSE_BASE        = "https://www.nseindia.com"
NSE_ANNC_URL    = "https://www.nseindia.com/api/corporate-announcements"
BSE_ANNC_URL    = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
BSE_PDF_BASE    = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"

# ─── HTTP SETTINGS ────────────────────────────────────────────────────────────
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
}
REQUEST_TIMEOUT = 30          # seconds
MAX_RETRIES     = 3
RETRY_BACKOFF   = 2.0         # exponential base

# ─── COMPANY REGISTRY ─────────────────────────────────────────────────────────
# Each entry defines everything the system needs to locate, fetch, and parse filings.
COMPANIES = {
    "TATAMOTORS": {
        "name":        "Tata Motors",
        "nse_symbol":  "TATAMOTORS",
        "bse_code":    "500570",
        "segments":    ["PV", "CV"],
        "sub_brands":  ["Jaguar", "Land Rover", "Nexon EV", "Ace", "Ultra"],
        "parser":      "tata",
        "ev_segment":  True,
        "keywords":    [
            "monthly sales", "wholesale dispatches", "retail sales",
            "vehicle sales", "passenger vehicle", "commercial vehicle",
            "total dispatches", "total sales"
        ],
        "exclude_keywords": [
            "investor presentation", "earnings", "financial results",
            "annual report", "clarification", "AGM", "EGM"
        ],
        "title_regex": r"(?i)(sales|dispatches|wholesale).{0,40}(month|april|may|june|july|august|september|october|november|december|january|february|march)",
    },
    "MARUTI": {
        "name":        "Maruti Suzuki",
        "nse_symbol":  "MARUTI",
        "bse_code":    "532500",
        "segments":    ["PV"],
        "sub_brands":  ["Alto", "Swift", "Baleno", "Brezza", "Ertiga", "Grand Vitara"],
        "parser":      "maruti",
        "ev_segment":  False,
        "keywords":    [
            "monthly sales", "wholesale", "total sales", "vehicle sales",
            "passenger car", "utility vehicle", "van"
        ],
        "exclude_keywords": [
            "investor", "earnings", "results", "clarification", "agm"
        ],
        "title_regex": r"(?i)(sales|wholesale).{0,40}(month|april|may|june|july|august|september|october|november|december|january|february|march)",
    },
    "M&MLTD": {
        "name":        "Mahindra & Mahindra",
        "nse_symbol":  "M&MLTD",
        "bse_code":    "500520",
        "segments":    ["PV", "CV", "Tractor", "EV"],
        "sub_brands":  ["Scorpio", "XUV700", "Thar", "Bolero", "Jawa", "BE Series"],
        "parser":      "mm",
        "ev_segment":  True,
        "keywords":    [
            "monthly sales", "auto sales", "farm equipment", "tractor sales",
            "SUV", "pick-up", "utility vehicle", "total sales"
        ],
        "exclude_keywords": [
            "investor", "earnings", "results", "clarification", "agm", "quarterly"
        ],
        "title_regex": r"(?i)(sales|dispatches).{0,50}(month|quarter|april|may|june|july|august|september|october|november|december|january|february|march)",
    },
    "BAJAJ-AUTO": {
        "name":        "Bajaj Auto",
        "nse_symbol":  "BAJAJ-AUTO",
        "bse_code":    "532977",
        "segments":    ["2W", "3W"],
        "sub_brands":  ["Pulsar", "Dominar", "Platina", "Chetak EV", "CT"],
        "parser":      "generic",
        "ev_segment":  True,
        "keywords":    [
            "monthly sales", "motorcycle", "two-wheeler", "three-wheeler",
            "commercial vehicle", "total dispatches", "wholesale"
        ],
        "exclude_keywords": ["investor", "earnings", "results", "agm"],
        "title_regex": r"(?i)(sales|dispatches).{0,40}(month|april|may|june|july|august|september|october|november|december|january|february|march)",
    },
    "HEROMOTOCO": {
        "name":        "Hero MotoCorp",
        "nse_symbol":  "HEROMOTOCO",
        "bse_code":    "500182",
        "segments":    ["2W"],
        "sub_brands":  ["Splendor", "HF Deluxe", "Glamour", "Passion", "Xpulse", "Vida EV"],
        "parser":      "generic",
        "ev_segment":  True,
        "keywords":    [
            "monthly sales", "motorcycle", "scooter", "two-wheeler",
            "total dispatches", "retail", "wholesale"
        ],
        "exclude_keywords": ["investor", "earnings", "results", "agm"],
        "title_regex": r"(?i)(sales|dispatches).{0,40}(month|april|may|june|july|august|september|october|november|december|january|february|march)",
    },
    "TVSMOTOR": {
        "name":        "TVS Motor",
        "nse_symbol":  "TVSMOTOR",
        "bse_code":    "532343",
        "segments":    ["2W", "3W", "EV"],
        "sub_brands":  ["Apache", "Jupiter", "Ntorq", "iQube EV", "Radeon"],
        "parser":      "generic",
        "ev_segment":  True,
        "keywords":    [
            "monthly sales", "two-wheeler", "three-wheeler", "scooter",
            "motorcycle", "total sales", "wholesale dispatches"
        ],
        "exclude_keywords": ["investor", "earnings", "results", "agm"],
        "title_regex": r"(?i)(sales|dispatches).{0,40}(month|april|may|june|july|august|september|october|november|december|january|february|march)",
    },
    "ASHOKLEY": {
        "name":        "Ashok Leyland",
        "nse_symbol":  "ASHOKLEY",
        "bse_code":    "500477",
        "segments":    ["CV"],
        "sub_brands":  ["Dost", "Boss", "Captain", "Circuit EV"],
        "parser":      "generic",
        "ev_segment":  True,
        "keywords":    [
            "monthly sales", "commercial vehicle", "bus", "truck",
            "LCV", "MHCV", "HCV", "wholesale dispatches", "total sales"
        ],
        "exclude_keywords": ["investor", "earnings", "results", "agm"],
        "title_regex": r"(?i)(sales|dispatches).{0,40}(month|april|may|june|july|august|september|october|november|december|january|february|march)",
    },
    "ESCORTS": {
        "name":        "Escorts Kubota",
        "nse_symbol":  "ESCORTS",
        "bse_code":    "500495",
        "segments":    ["Tractor", "Construction"],
        "sub_brands":  ["Farmtrac", "Powertrac", "Digitrac"],
        "parser":      "generic",
        "ev_segment":  False,
        "keywords":    [
            "tractor sales", "monthly dispatches", "agri machinery",
            "construction equipment", "total sales"
        ],
        "exclude_keywords": ["investor", "earnings", "results", "agm"],
        "title_regex": r"(?i)(tractor|sales|dispatches).{0,40}(month|april|may|june|july|august|september|october|november|december|january|february|march)",
    },
}

# ─── SEGMENT TAXONOMY ─────────────────────────────────────────────────────────
SEGMENT_CONFIG = {
    "PV": {
        "label":    "Passenger Vehicles",
        "color":    "#2563EB",
        "icon":     "🚗",
        "keywords": ["passenger", "car", "SUV", "hatchback", "sedan", "MPV", "UV", "utility"],
    },
    "CV": {
        "label":    "Commercial Vehicles",
        "color":    "#DC2626",
        "icon":     "🚛",
        "keywords": ["commercial", "truck", "bus", "LCV", "HCV", "MHCV", "SCV", "ICV", "tipper"],
    },
    "2W": {
        "label":    "Two Wheelers",
        "color":    "#16A34A",
        "icon":     "🏍️",
        "keywords": ["motorcycle", "scooter", "moped", "two-wheeler", "2W"],
    },
    "3W": {
        "label":    "Three Wheelers",
        "color":    "#D97706",
        "icon":     "🛺",
        "keywords": ["three-wheeler", "auto-rickshaw", "3W", "e-rickshaw"],
    },
    "Tractor": {
        "label":    "Tractors / Farm Equipment",
        "color":    "#7C3AED",
        "icon":     "🚜",
        "keywords": ["tractor", "farm", "agri", "harvester", "implement"],
    },
    "EV": {
        "label":    "Electric Vehicles",
        "color":    "#0891B2",
        "icon":     "⚡",
        "keywords": ["electric", "EV", "BEV", "e-", "battery", "zero emission"],
    },
}

# ─── METRIC DEFINITIONS ───────────────────────────────────────────────────────
METRIC_ALIASES = {
    "domestic": ["domestic", "domestic sales", "dom", "domestic dispatches", "home market"],
    "exports":  ["exports", "export", "international", "overseas"],
    "total":    ["total", "grand total", "net total", "overall total", "combined"],
}

# ─── TABLE DETECTION THRESHOLDS ───────────────────────────────────────────────
TABLE_DETECTION = {
    "min_rows":             3,
    "min_cols":             3,
    "min_numeric_density":  0.35,     # 35% of cells must be numeric
    "min_header_score":     0.5,
    "time_col_patterns":    [
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
        r"\b20\d{2}\b",
        r"\bq[1-4]\b",
        r"ytd",
    ],
}

# ─── VALIDATION THRESHOLDS ────────────────────────────────────────────────────
VALIDATION = {
    "arithmetic_tolerance":   0.05,   # 5% tolerance for dom + exp ≈ total
    "max_yoy_change":         2.0,    # 200% YoY change triggers anomaly flag
    "min_absolute_sales":     100,    # below 100 units → likely parsing error
    "confidence_threshold":   0.6,    # minimum score to store data
}

# ─── INSIGHT ENGINE ───────────────────────────────────────────────────────────
INSIGHT_CONFIG = {
    "use_llm":            False,      # True requires ANTHROPIC_API_KEY in env; False = fully free
    "llm_model":          "claude-sonnet-4-20250514",
    "llm_max_tokens":     800,
    "top_insights_count": 5,
    "yoy_strong_growth":  0.15,       # 15%+ → "strong growth"
    "yoy_contraction":   -0.10,       # -10% → "contraction"
    "export_strength":    0.20,       # exports > 20% of total → "export-led"
}

# ─── ALERT THRESHOLDS ─────────────────────────────────────────────────────────
ALERT_CONFIG = {
    "yoy_crash":    -0.20,    # -20% alert
    "yoy_surge":     0.30,    # +30% alert
    "market_share_shift": 0.03,  # 3pp shift in market share
    "missing_filing_days": 5,    # alert if filing not seen within 5 days of month-end
}

# ─── ANTHROPIC API ────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
