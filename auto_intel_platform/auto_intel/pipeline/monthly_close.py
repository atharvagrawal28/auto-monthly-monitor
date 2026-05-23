"""
pipeline/monthly_close.py — Monthly Close Reporter
====================================================
After each pipeline run, summarises how the monthly close is progressing:

  - For the most-recently-closed sales month:
      • Which OEMs have filed? (status, on-time vs late)
      • Which OEMs are missing? (and by how many days are they overdue)
      • Per-OEM data-quality score for the new prints
      • Industry total, EV penetration, segment growth headlines

Writes a Markdown report to logs/close_report_<YYYY-MM>.md so the GitHub
Actions run summary shows it. Returns a Python dict for in-app use.
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

import sys, pathlib as _pl
sys.path.insert(0, str(_pl.Path(__file__).parent.parent))

from schema import ParserStatus
from registry import OEM_REGISTRY, get_all_active
from analytics.quality import filing_sla, oem_quality_card
from analytics.benchmarks import ev_penetration

logger = logging.getLogger(__name__)

LOG_DIR = _pl.Path(__file__).parent.parent / "logs"


_STATUS_RANK = {
    ParserStatus.CONFLICT:    0,
    ParserStatus.NEEDS_REVIEW: 1,
    ParserStatus.FLAGGED:     2,
    ParserStatus.STALE:       3,
    ParserStatus.MANUAL:      4,
    ParserStatus.CLEAN:       5,
}


def _worst_status(statuses: list[str]) -> str:
    if not statuses:
        return ParserStatus.STALE
    return min(
        statuses,
        key=lambda s: _STATUS_RANK.get(s, 99),
    )


def _last_closed_month(today: datetime | None = None) -> str:
    """Return prior calendar month as 'YYYY-MM' — that's the sales month
    OEMs are filing about right now."""
    today = today or datetime.today()
    first = today.replace(day=1)
    prior = first - timedelta(days=1)
    return prior.strftime("%Y-%m")


def build_close_report(
    norm_df: pd.DataFrame,
    granular_df: pd.DataFrame | None = None,
    today: datetime | None = None,
) -> dict:
    today = today or datetime.today()
    target_month = _last_closed_month(today)

    active = get_all_active()
    expected = [o.key for o in active]

    cur = norm_df[norm_df["filing_month_year"] == target_month].copy() if not norm_df.empty else pd.DataFrame()
    filed_oems = set(cur["company_key"].unique()) if not cur.empty else set()
    missing_oems = sorted(set(expected) - filed_oems)

    # Per-OEM SLA
    sla_rows = []
    for oem in active:
        sub = cur[cur["company_key"] == oem.key] if not cur.empty else pd.DataFrame()
        if sub.empty:
            sla = filing_sla({"filing_month_year": target_month, "filing_date": ""},
                             typical_day=oem.typical_filing_day)
            sla_rows.append({
                "oem":         oem.key,
                "status":      sla["status"],
                "days_late":   sla["days_late"],
                "expected_by": sla["expected_by"],
            })
        else:
            # Pick the earliest filing_date row to represent the SLA;
            # sum total across all segments for the OEM.
            sub_sorted = sub.sort_values("filing_date", na_position="last")
            r = sub_sorted.iloc[0]
            sla = filing_sla(r, typical_day=oem.typical_filing_day)
            oem_total = int(pd.to_numeric(sub["total"], errors="coerce").sum())
            mean_conf = float(pd.to_numeric(
                sub["confidence_score"], errors="coerce"
            ).fillna(0).mean())
            worst_status = _worst_status(sub["parser_status"].tolist())
            sla_rows.append({
                "oem":         oem.key,
                "status":      sla["status"],
                "days_late":   sla["days_late"],
                "expected_by": sla["expected_by"],
                "parser_status": worst_status,
                "confidence":  mean_conf,
                "total":       oem_total,
                "segments":    int(sub["segment"].nunique()),
            })

    on_time   = sum(1 for r in sla_rows if r["status"] == "ON_TIME")
    late      = sum(1 for r in sla_rows if r["status"] == "LATE")
    missing   = sum(1 for r in sla_rows if r["status"] == "MISSING")
    upcoming  = sum(1 for r in sla_rows if r["status"] == "UPCOMING")

    industry_total = int(cur["total"].sum()) if not cur.empty else 0

    # YoY industry growth
    prior_y = (pd.to_datetime(target_month + "-01") -
               pd.DateOffset(years=1)).strftime("%Y-%m")
    prior_total = (
        int(norm_df[norm_df["filing_month_year"] == prior_y]["total"].sum())
        if not norm_df.empty else 0
    )
    yoy_pct = (
        (industry_total - prior_total) / prior_total
        if prior_total > 0 else None
    )

    # EV penetration
    ev = ev_penetration(norm_df) if not norm_df.empty else pd.DataFrame()
    ev_pen = None
    if not ev.empty:
        match = ev[ev["filing_month_year"] == target_month]
        if not match.empty:
            ev_pen = float(match["ev_pct_of_comparable"].iloc[0])

    report = {
        "target_month":     target_month,
        "generated_at":     today.isoformat(),
        "oems_expected":    len(expected),
        "oems_filed":       len(filed_oems),
        "oems_missing":     missing_oems,
        "filings_on_time":  on_time,
        "filings_late":     late,
        "filings_missing":  missing,
        "filings_upcoming": upcoming,
        "industry_total":   industry_total,
        "industry_yoy_pct": round(yoy_pct, 4) if yoy_pct is not None else None,
        "ev_penetration":   round(ev_pen, 4) if ev_pen is not None else None,
        "per_oem":          sla_rows,
    }
    return report


def write_markdown_report(report: dict, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or LOG_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"close_report_{report['target_month']}.md"

    lines = []
    lines.append(f"# Monthly close report - {report['target_month']}")
    lines.append("")
    lines.append(f"_Generated: {report['generated_at']}_")
    lines.append("")
    lines.append("## Coverage")
    lines.append("")
    lines.append(f"- OEMs expected: **{report['oems_expected']}**")
    lines.append(f"- OEMs filed:    **{report['oems_filed']}**")
    lines.append(f"- On-time:       **{report['filings_on_time']}**")
    lines.append(f"- Late:          **{report['filings_late']}**")
    lines.append(f"- Missing:       **{report['filings_missing']}**")
    lines.append(f"- Upcoming:      **{report['filings_upcoming']}**")
    lines.append("")
    lines.append("## Industry")
    lines.append("")
    if report["industry_total"]:
        def _ind(n):
            s = str(abs(int(n)))
            if len(s) <= 3: return s
            r, s = s[-3:], s[:-3]
            while s: r, s = s[-2:] + "," + r, s[:-2]
            return r
        lines.append(f"- Total wholesale: **{_ind(report['industry_total'])}** units")
    if report["industry_yoy_pct"] is not None:
        lines.append(f"- YoY:             **{report['industry_yoy_pct']*100:+.1f}%**")
    if report["ev_penetration"] is not None:
        lines.append(f"- EV penetration:  **{report['ev_penetration']*100:.2f}%**")
    lines.append("")

    if report["oems_missing"]:
        lines.append("## Still missing")
        lines.append("")
        for k in report["oems_missing"]:
            cfg = OEM_REGISTRY.get(k)
            display = cfg.display_name if cfg else k
            lines.append(f"- {display} (`{k}`)")
        lines.append("")

    lines.append("## Per-OEM detail")
    lines.append("")
    lines.append("| OEM | Status | Days late | Segments | Total | Confidence | Parser |")
    lines.append("|-----|--------|-----------|----------|-------|-----------|--------|")
    for r in report["per_oem"]:
        cfg = OEM_REGISTRY.get(r["oem"])
        display = cfg.display_name if cfg else r["oem"]
        days = "" if r.get("days_late") is None else f"{r['days_late']:+d}"
        segs = str(r.get("segments", "—"))
        total = f"{r.get('total', 0):,}" if r.get("total") else "—"
        conf = f"{r.get('confidence', 0)*100:.0f}%" if r.get("confidence") else "—"
        parser = r.get("parser_status", "—")
        lines.append(
            f"| {display} | {r['status']} | {days} | {segs} | {total} | {conf} | {parser} |"
        )

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_json_report(report: dict, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or LOG_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"close_report_{report['target_month']}.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return path


if __name__ == "__main__":
    from pipeline.store import load_normalized, load_granular
    norm = load_normalized()
    gran = load_granular()
    report = build_close_report(norm, gran)
    md = write_markdown_report(report)
    js = write_json_report(report)
    print(f"Wrote {md}")
    print(f"Wrote {js}")
    print(f"Coverage: {report['oems_filed']}/{report['oems_expected']}")
