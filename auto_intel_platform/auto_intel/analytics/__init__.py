"""
analytics/ — analyst-grade derived metrics
==========================================
All computations here are deterministic and operate on a normalized DataFrame.
The dashboard never inlines maths; it always calls these functions.
"""

from .rolling import (
    add_rolling_mean,
    add_ttm,
    add_ytd,
    add_fytd,
    add_qoq,
    compute_cagr,
    fiscal_year,
    fiscal_quarter,
)
from .share import (
    add_market_share,
    share_delta_mom,
    share_delta_yoy,
    hhi,
    industry_concentration,
)
from .anomaly import (
    add_z_score,
    flag_anomalies,
    industry_vs_oem_divergence,
)
from .quality import (
    score_row_quality,
    oem_quality_card,
    filing_sla,
    filing_sla_summary,
)
from .benchmarks import (
    quartile_rank,
    ev_penetration,
    export_mix,
    segment_mix,
    growth_bridge,
    beat_miss_vs_trailing,
)

__all__ = [
    "add_rolling_mean", "add_ttm", "add_ytd", "add_fytd", "add_qoq",
    "compute_cagr", "fiscal_year", "fiscal_quarter",
    "add_market_share", "share_delta_mom", "share_delta_yoy",
    "hhi", "industry_concentration",
    "add_z_score", "flag_anomalies", "industry_vs_oem_divergence",
    "score_row_quality", "oem_quality_card", "filing_sla", "filing_sla_summary",
    "quartile_rank", "ev_penetration", "export_mix", "segment_mix",
    "growth_bridge", "beat_miss_vs_trailing",
]
