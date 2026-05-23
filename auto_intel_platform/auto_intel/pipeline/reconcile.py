"""
pipeline/reconcile.py — cross-source agreement & granular check
================================================================
Two extra validation layers, callable from validate.py and the pipeline run:

  1. cross_source_agreement(rows_by_source)
       Given the same (oem, segment, month) parsed from NSE *and* BSE,
       agree only if deltas are small (≤2%). Otherwise raise CONFLICT.

  2. granular_reconcile(norm_row, granular_rows)
       Sum of granular sub-segments must approximate the normalized total
       (within 3%). Otherwise downgrade parser_status and emit a note.

Both functions are pure — they don't write files; the caller does.
"""

from __future__ import annotations
from typing import Iterable, Optional
from dataclasses import dataclass

from schema import NormalizedRow, GranularRow, ParserStatus


@dataclass
class ReconcileResult:
    ok:          bool
    note:        str = ""
    delta_pct:   Optional[float] = None
    agreed_total: Optional[int] = None
    sources_seen: tuple[str, ...] = ()


# ── 1. Cross-source agreement ───────────────────────────────────────────────

def cross_source_agreement(
    rows: Iterable[NormalizedRow],
    tolerance: float = 0.02,
) -> ReconcileResult:
    """
    Compare NormalizedRows for the same (oem, segment, month) from different
    sources. Returns whether they agree within tolerance.

    If only one source provided -> trivially agrees (note='single source').
    """
    rows = list(rows)
    if not rows:
        return ReconcileResult(ok=False, note="no rows to reconcile")

    sources = tuple(sorted({r.source for r in rows if r.source}))
    totals  = [r.total for r in rows if r.total is not None]

    if len(totals) <= 1:
        return ReconcileResult(
            ok=True, note=f"single source ({sources[0] if sources else '?'})",
            agreed_total=totals[0] if totals else None,
            sources_seen=sources,
        )

    mn, mx = min(totals), max(totals)
    delta = (mx - mn) / mx if mx > 0 else 0
    if delta <= tolerance:
        # Take the median (resistant to a single outlier source)
        sorted_t = sorted(totals)
        median = sorted_t[len(sorted_t) // 2]
        return ReconcileResult(
            ok=True,
            note=f"agreement within {delta*100:.1f}% across {sources}",
            delta_pct=round(delta, 4),
            agreed_total=median,
            sources_seen=sources,
        )

    return ReconcileResult(
        ok=False,
        note=f"CROSS-SOURCE CONFLICT {delta*100:.1f}% across {sources}: "
             f"min={mn:,} max={mx:,}",
        delta_pct=round(delta, 4),
        agreed_total=None,
        sources_seen=sources,
    )


# ── 2. Granular reconciliation ──────────────────────────────────────────────

def granular_reconcile(
    norm_row: NormalizedRow,
    granular_rows: list[GranularRow],
    tolerance: float = 0.03,
) -> ReconcileResult:
    """
    Sum of sub-segment units (granular) should ≈ norm_row.total.
    Tolerance default 3% (some filings have rounding / 'others' bucket).
    """
    if not granular_rows:
        return ReconcileResult(ok=True, note="no granular rows — skip")
    if norm_row.total is None or norm_row.total <= 0:
        return ReconcileResult(ok=False, note="norm total missing/zero")

    g_sum = sum(int(g.units or 0) for g in granular_rows)
    delta = abs(g_sum - norm_row.total) / norm_row.total
    if delta <= tolerance:
        return ReconcileResult(
            ok=True,
            note=f"granular sum={g_sum:,} matches total ({delta*100:.1f}%)",
            delta_pct=round(delta, 4),
            agreed_total=norm_row.total,
        )
    return ReconcileResult(
        ok=False,
        note=f"GRANULAR MISMATCH sum={g_sum:,} vs total={norm_row.total:,} "
             f"({delta*100:.1f}% gap)",
        delta_pct=round(delta, 4),
        agreed_total=None,
    )


# ── 3. Apply downgrade ──────────────────────────────────────────────────────

def downgrade_on_failure(
    row: NormalizedRow,
    result: ReconcileResult,
    new_status: str = ParserStatus.FLAGGED,
) -> NormalizedRow:
    """If result is not ok, append the note and downgrade parser_status."""
    if result.ok:
        return row
    if row.parser_status == ParserStatus.CLEAN:
        row.parser_status = new_status
    existing = row.review_note or ""
    row.review_note = (existing + " | " + result.note).strip(" |")
    return row
