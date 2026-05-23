"""
pipeline/integrity_check.py — Post-pipeline data integrity validator
=====================================================================
Runs after every pipeline execution. Catches problems before they
reach the dashboard and mislead analysts.

Checks (in order of severity):
  1. CRITICAL — Arithmetic: domestic + exports ≠ total (tolerance ±1 unit)
  2. CRITICAL — Duplicate primary keys (same OEM/segment/month entered twice)
  3. HIGH     — Missing OEMs past their expected filing day + 5 grace days
  4. HIGH     — Confidence score below threshold (< 0.65)
  5. MEDIUM   — YoY growth outside plausible range (< -80% or > +300%)
  6. INFO     — Total volume = 0 for a CLEAN row

Exit codes:
  0 — all checks passed (or only MEDIUM/INFO issues found)
  1 — CRITICAL or HIGH issues found → GitHub Action step will fail

Usage:
  python pipeline/integrity_check.py [--strict]

  --strict: exit 1 on ANY issue including MEDIUM/INFO
"""

from __future__ import annotations

import sys
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.store import load_normalized
from registry import OEM_REGISTRY, get_all_active
from analytics.quality import filing_sla

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# ── thresholds ────────────────────────────────────────────────────────────────
ARITH_TOLERANCE   = 1        # units (rounding differences)
LOW_CONFIDENCE    = 0.65
YOY_LOW_BOUND     = -0.80    # -80% is the floor for plausible YoY
YOY_HIGH_BOUND    = 3.00     # +300% is the ceiling
MISSING_GRACE_DAYS = 5       # days past typical_filing_day before we alert


def _fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)


def run_checks(strict: bool = False) -> int:
    """
    Run all integrity checks. Returns exit code (0 = OK, 1 = issues found).
    """
    df = load_normalized()
    if df.empty:
        logger.warning("normalized.csv is empty — nothing to check.")
        return 0

    # Cast numeric columns
    for col in ["domestic", "exports", "total"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["confidence_score"] = pd.to_numeric(df["confidence_score"], errors="coerce").fillna(0)
    df["yoy_pct"]          = pd.to_numeric(df["yoy_pct"],          errors="coerce")

    issues: list[dict] = []   # {level, oem, segment, month, message}

    # ── Check 1: Arithmetic ──────────────────────────────────────────────────
    bad_arith = df[
        (df["domestic"] + df["exports"] - df["total"]).abs() > ARITH_TOLERANCE
    ].copy()
    for _, r in bad_arith.iterrows():
        issues.append({
            "level":   "CRITICAL",
            "oem":     r.get("company_key", "?"),
            "segment": r.get("segment", "?"),
            "month":   r.get("filing_month_year", "?"),
            "message": (
                f"Arithmetic fail: domestic({_fmt(r['domestic'])}) + "
                f"exports({_fmt(r['exports'])}) = {_fmt(r['domestic']+r['exports'])} "
                f"≠ total({_fmt(r['total'])})"
            ),
        })

    # ── Check 2: Duplicate primary keys ─────────────────────────────────────
    pk = ["company_key", "segment", "filing_month_year"]
    dupes = df[df.duplicated(subset=pk, keep=False)]
    for _, r in dupes.drop_duplicates(subset=pk).iterrows():
        count = len(df[
            (df["company_key"] == r["company_key"]) &
            (df["segment"]     == r["segment"]) &
            (df["filing_month_year"] == r["filing_month_year"])
        ])
        issues.append({
            "level":   "CRITICAL",
            "oem":     r.get("company_key", "?"),
            "segment": r.get("segment", "?"),
            "month":   r.get("filing_month_year", "?"),
            "message": f"Duplicate key — {count} rows for same OEM/segment/month",
        })

    # ── Check 3: Missing OEMs past grace period ──────────────────────────────
    today = datetime.today()
    # Only check if we're past the 5th of the current month
    if today.day > 5:
        # Target month = last closed month
        first_of_month = today.replace(day=1)
        target_month   = (first_of_month - timedelta(days=1)).strftime("%Y-%m")
        filed_oems     = set(
            df[df["filing_month_year"] == target_month]["company_key"].unique()
        )
        for oem in get_all_active():
            if oem.key in filed_oems:
                continue
            # Check if past expected day + grace
            typical = getattr(oem, "typical_filing_day", 5)
            cutoff  = first_of_month.replace(day=1) + timedelta(days=typical + MISSING_GRACE_DAYS)
            if today > cutoff:
                issues.append({
                    "level":   "HIGH",
                    "oem":     oem.key,
                    "segment": "—",
                    "month":   target_month,
                    "message": (
                        f"No data filed for {target_month}. "
                        f"Expected by D+{typical}, grace period (+{MISSING_GRACE_DAYS}d) expired. "
                        f"Use Review Queue → Manual Entry."
                    ),
                })

    # ── Check 4: Low confidence scores ──────────────────────────────────────
    low_conf = df[
        (df["confidence_score"] < LOW_CONFIDENCE) &
        (df["parser_status"] != "MANUAL")   # manual rows are always confidence=1.0
    ]
    for _, r in low_conf.iterrows():
        issues.append({
            "level":   "HIGH",
            "oem":     r.get("company_key", "?"),
            "segment": r.get("segment", "?"),
            "month":   r.get("filing_month_year", "?"),
            "message": (
                f"Low confidence: {r['confidence_score']:.0%} "
                f"(threshold {LOW_CONFIDENCE:.0%}) — parser may have extracted wrong numbers"
            ),
        })

    # ── Check 5: YoY out of range ────────────────────────────────────────────
    has_yoy = df[df["yoy_pct"].notna()]
    bad_yoy = has_yoy[
        (has_yoy["yoy_pct"] < YOY_LOW_BOUND) | (has_yoy["yoy_pct"] > YOY_HIGH_BOUND)
    ]
    for _, r in bad_yoy.iterrows():
        issues.append({
            "level":   "MEDIUM",
            "oem":     r.get("company_key", "?"),
            "segment": r.get("segment", "?"),
            "month":   r.get("filing_month_year", "?"),
            "message": (
                f"Extreme YoY: {r['yoy_pct']*100:+.1f}% "
                f"(plausible range: {YOY_LOW_BOUND*100:.0f}% to {YOY_HIGH_BOUND*100:.0f}%)"
            ),
        })

    # ── Check 6: Zero volume rows ────────────────────────────────────────────
    zero_vol = df[
        (df["total"] == 0) &
        (df["parser_status"] == "CLEAN")
    ]
    for _, r in zero_vol.iterrows():
        issues.append({
            "level":   "INFO",
            "oem":     r.get("company_key", "?"),
            "segment": r.get("segment", "?"),
            "month":   r.get("filing_month_year", "?"),
            "message": "Total volume = 0 with CLEAN status — verify this is not a parse failure",
        })

    # ── Report ───────────────────────────────────────────────────────────────
    if not issues:
        logger.info("✅ All integrity checks passed.")
        _write_summary([], df)
        return 0

    # Count by level
    by_level: dict[str, int] = {}
    for i in issues:
        by_level[i["level"]] = by_level.get(i["level"], 0) + 1

    logger.info(f"\n{'='*60}")
    logger.info(f"INTEGRITY CHECK REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info(f"{'='*60}")
    logger.info(f"Total issues: {len(issues)}")
    for level, count in sorted(by_level.items()):
        logger.info(f"  {level}: {count}")
    logger.info("")

    for level in ["CRITICAL", "HIGH", "MEDIUM", "INFO"]:
        level_issues = [i for i in issues if i["level"] == level]
        if not level_issues:
            continue
        logger.info(f"── {level} ({len(level_issues)}) ──")
        for i in level_issues:
            logger.info(f"  [{i['oem']}] {i['segment']} {i['month']}: {i['message']}")
        logger.info("")

    _write_summary(issues, df)

    # Decide exit code
    has_critical = any(i["level"] == "CRITICAL" for i in issues)
    has_high     = any(i["level"] == "HIGH"     for i in issues)

    if has_critical or has_high:
        logger.error(
            "❌ CRITICAL or HIGH issues found. "
            "Fix them in Review Queue → Manual Entry before trusting this data."
        )
        return 1

    if strict:
        logger.warning("⚠ Issues found (strict mode). Returning exit code 1.")
        return 1

    logger.warning("⚠ Only MEDIUM/INFO issues found. Data is usable but review recommended.")
    return 0


def _write_summary(issues: list[dict], df: pd.DataFrame) -> None:
    """Write a markdown summary to logs/ for GitHub Actions step summary."""
    try:
        log_dir = Path(__file__).parent.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"integrity_{datetime.now().strftime('%Y-%m-%d')}.md"

        lines = [
            f"# Integrity check — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            f"- Rows checked: **{len(df)}**",
            f"- Issues found: **{len(issues)}**",
            "",
        ]

        if not issues:
            lines.append("✅ **All checks passed.**")
        else:
            by_level: dict[str, list] = {}
            for i in issues:
                by_level.setdefault(i["level"], []).append(i)

            for level in ["CRITICAL", "HIGH", "MEDIUM", "INFO"]:
                if level not in by_level:
                    continue
                lines.append(f"## {level} ({len(by_level[level])})")
                lines.append("")
                lines.append("| OEM | Segment | Month | Issue |")
                lines.append("|-----|---------|-------|-------|")
                for i in by_level[level]:
                    lines.append(f"| {i['oem']} | {i['segment']} | {i['month']} | {i['message']} |")
                lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Integrity report written → {path}")
    except Exception as e:
        logger.warning(f"Could not write integrity report: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Post-pipeline integrity check")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 on ANY issue, not just CRITICAL/HIGH")
    args = parser.parse_args()

    exit_code = run_checks(strict=args.strict)
    sys.exit(exit_code)
