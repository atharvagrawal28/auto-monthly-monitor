"""
registry.py — OEM Registry
===========================
Single source of truth for all OEM configurations.
Adding a new OEM = adding one entry here. No code changes elsewhere.
"""

from dataclasses import dataclass, field
from typing import Optional

@dataclass
class OEMConfig:
    key:               str          # canonical key e.g. "TATAMOTORS_CV"
    display_name:      str          # "Tata Motors – Commercial Vehicles"
    nse_symbol:        str
    bse_code:          str
    segments:          list
    parser_module:     str          # parsers/<module>.py
    format_versions:   list         # ["V1","V2","V3"]
    typical_filing_day: int         # day of following month by which they file
    ev_tracker:        bool = False
    active:            bool = True
    notes:             str  = ""
    include_keywords:  list = field(default_factory=list)
    exclude_keywords:  list = field(default_factory=list)
    title_regex:       str  = r"(?i)(sales|dispatches|wholesale).{0,50}(month|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"


OEM_REGISTRY: dict[str, OEMConfig] = {

    "TATAMOTORS_PV": OEMConfig(
        key="TATAMOTORS_PV",
        display_name="Tata Motors – Passenger Vehicles",
        nse_symbol="TATAMOTORS",
        bse_code="500570",
        segments=["PV", "EV"],
        parser_module="tata",
        format_versions=["V1", "V2", "V3"],
        typical_filing_day=3,
        ev_tracker=True,
        include_keywords=["passenger vehicle","utility","nexon","safari","harrier","punch","tigor","tiago","altroz","curvv"],
        exclude_keywords=["investor presentation","earnings","financial results","quarterly","agm","egm","annual report","buyback","dividend"],
        notes="Tata PV includes Nexon EV. Format changed significantly in FY23.",
    ),

    "TATAMOTORS_CV": OEMConfig(
        key="TATAMOTORS_CV",
        display_name="Tata Motors – Commercial Vehicles",
        nse_symbol="TATAMOTORS",
        bse_code="500570",
        segments=["CV"],
        parser_module="tata",
        format_versions=["V1", "V2", "V3"],
        typical_filing_day=3,
        ev_tracker=False,
        include_keywords=["commercial vehicle","truck","bus","scv","lcv","mhcv","hcv","ace","ultra","prima","signa"],
        exclude_keywords=["investor presentation","earnings","financial results","quarterly","agm","egm","annual report"],
        notes="Tata CV sub-segments: SCV, ICV, MHCV, Bus.",
    ),

    "MARUTI": OEMConfig(
        key="MARUTI",
        display_name="Maruti Suzuki",
        nse_symbol="MARUTI",
        bse_code="532500",
        segments=["PV"],
        parser_module="maruti",
        format_versions=["V1", "V2"],
        typical_filing_day=1,
        ev_tracker=False,
        include_keywords=["wholesale","domestic","export","total","passenger","utility","van","alto","swift","baleno","brezza","ertiga","vitara","jimny","fronx","invicto"],
        exclude_keywords=["investor","earnings","results","agm","egm","clarification","financial","annual"],
        notes="Maruti is most consistently formatted. Good first parser to build.",
    ),

    "MAHINDRA_AUTO": OEMConfig(
        key="MAHINDRA_AUTO",
        display_name="Mahindra & Mahindra – Automotive",
        nse_symbol="M&MLTD",
        bse_code="500520",
        segments=["PV", "CV", "EV"],
        parser_module="mm",
        format_versions=["V1", "V2"],
        typical_filing_day=4,
        ev_tracker=True,
        include_keywords=["utility vehicle","suv","pick-up","scorpio","xuv","thar","bolero","be series","ev","electric"],
        exclude_keywords=["farm","tractor","agri","investor","earnings","results","agm","annual","quarterly"],
        notes="M&M Auto and Farm are sometimes in same filing — parser must split.",
    ),

    "MAHINDRA_FARM": OEMConfig(
        key="MAHINDRA_FARM",
        display_name="Mahindra & Mahindra – Farm Equipment",
        nse_symbol="M&MLTD",
        bse_code="500520",
        segments=["Tractor"],
        parser_module="mm",
        format_versions=["V1", "V2"],
        typical_filing_day=4,
        ev_tracker=False,
        include_keywords=["tractor","farm equipment","agri","harvester"],
        exclude_keywords=["investor","earnings","results","agm","annual","quarterly"],
        notes="Farm division tracked separately from Auto.",
    ),

    "BAJAJ": OEMConfig(
        key="BAJAJ",
        display_name="Bajaj Auto",
        nse_symbol="BAJAJ-AUTO",
        bse_code="532977",
        segments=["2W", "3W", "EV"],
        parser_module="generic",
        format_versions=["V1"],
        typical_filing_day=2,
        ev_tracker=True,
        include_keywords=["motorcycle","two wheeler","three wheeler","commercial vehicle","domestic","export","chetak"],
        exclude_keywords=["investor","earnings","results","agm","annual","quarterly","financial"],
        notes="Bajaj reports 2W + 3W separately. Chetak EV tracked within 2W.",
    ),

    "HEROMOTOCO": OEMConfig(
        key="HEROMOTOCO",
        display_name="Hero MotoCorp",
        nse_symbol="HEROMOTOCO",
        bse_code="500182",
        segments=["2W", "EV"],
        parser_module="generic",
        format_versions=["V1"],
        typical_filing_day=3,
        ev_tracker=True,
        include_keywords=["motorcycle","scooter","two wheeler","domestic","export","vida","splendor","hf","glamour","passion","destini"],
        exclude_keywords=["investor","earnings","results","agm","annual","quarterly","financial"],
    ),

    "TVS": OEMConfig(
        key="TVS",
        display_name="TVS Motor Company",
        nse_symbol="TVSMOTOR",
        bse_code="532343",
        segments=["2W", "3W", "EV"],
        parser_module="generic",
        format_versions=["V1"],
        typical_filing_day=3,
        ev_tracker=True,
        include_keywords=["two wheeler","three wheeler","motorcycle","scooter","iqube","electric","domestic","export","apache","jupiter","ntorq","radeon"],
        exclude_keywords=["investor","earnings","results","agm","annual","quarterly","financial"],
    ),

    "ASHOKLEY": OEMConfig(
        key="ASHOKLEY",
        display_name="Ashok Leyland",
        nse_symbol="ASHOKLEY",
        bse_code="500477",
        segments=["CV"],
        parser_module="generic",
        format_versions=["V1"],
        typical_filing_day=5,
        ev_tracker=True,
        include_keywords=["commercial vehicle","truck","bus","lcv","mhcv","hcv","domestic","export","dost","boss","captain","circuit"],
        exclude_keywords=["investor","earnings","results","agm","annual","quarterly","financial"],
    ),

    "ESCORTS": OEMConfig(
        key="ESCORTS",
        display_name="Escorts Kubota",
        nse_symbol="ESCORTS",
        bse_code="500495",
        segments=["Tractor"],
        parser_module="generic",
        format_versions=["V1"],
        typical_filing_day=8,
        ev_tracker=False,
        include_keywords=["tractor","farm","agri","construction","domestic","export","farmtrac","powertrac","digitrac"],
        exclude_keywords=["investor","earnings","results","agm","annual","quarterly","financial"],
        notes="Escorts can file as late as day 8-10. Higher STALE tolerance needed.",
    ),

    "EICHER": OEMConfig(
        key="EICHER",
        display_name="Eicher Motors (Royal Enfield)",
        nse_symbol="EICHERMOT",
        bse_code="505200",
        segments=["2W"],
        parser_module="generic",
        format_versions=["V1"],
        typical_filing_day=4,
        ev_tracker=False,
        include_keywords=["motorcycle","two wheeler","domestic","export","royal enfield","hunter","meteor","classic","himalayan","bullet","thunderbird"],
        exclude_keywords=["investor","earnings","results","agm","annual","quarterly","financial","volvo","ve commercial"],
        notes="Royal Enfield is premium 2W. Eicher also has VE CV but track RE only.",
    ),

    "OLA_ELECTRIC": OEMConfig(
        key="OLA_ELECTRIC",
        display_name="Ola Electric",
        nse_symbol="OLAELEC",
        bse_code="544225",
        segments=["EV", "2W"],
        parser_module="generic",
        format_versions=["V1"],
        typical_filing_day=5,
        ev_tracker=True,
        active=True,
        include_keywords=["electric","ev","scooter","two wheeler","domestic","s1","s1 pro","s1 air"],
        exclude_keywords=["investor","earnings","results","agm","annual","quarterly","financial"],
        notes="Newer filer. Format may evolve. Added for EV penetration tracking.",
    ),
}


def get_oem(key: str) -> Optional[OEMConfig]:
    return OEM_REGISTRY.get(key)

def get_all_active() -> list[OEMConfig]:
    return [v for v in OEM_REGISTRY.values() if v.active]

def get_by_nse_symbol(symbol: str) -> list[OEMConfig]:
    """Multiple OEM keys can share a symbol (e.g. TATAMOTORS_CV + TATAMOTORS_PV)."""
    return [v for v in OEM_REGISTRY.values() if v.nse_symbol == symbol]

def get_by_segment(segment: str) -> list[OEMConfig]:
    return [v for v in OEM_REGISTRY.values() if segment in v.segments and v.active]
