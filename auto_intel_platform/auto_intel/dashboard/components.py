"""
dashboard/components.py — reusable visual primitives
======================================================
Lightweight helpers that wrap st.markdown so we keep page code free of
hand-rolled CSS strings. Every function emits its own HTML.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
from datetime import datetime
import html

from . import theme


# ── Section header ───────────────────────────────────────────────────────────

def section_header(title: str, sub: str | None = None) -> None:
    sub_html = f'<span class="section-sub">{html.escape(sub)}</span>' if sub else ""
    st.markdown(
        f"""
        <div class="section-header">
            <div class="section-bar"></div>
            <h2>{html.escape(title)}</h2>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Hero ─────────────────────────────────────────────────────────────────────

def hero(
    title: str,
    subtitle: str,
    meta: list[tuple[str, str]] | None = None,
) -> None:
    meta_html = ""
    if meta:
        items = "".join(
            f"<span>{html.escape(k)} <strong>{html.escape(str(v))}</strong></span>"
            for k, v in meta
        )
        meta_html = f'<div class="hero-meta">{items}</div>'
    st.markdown(
        f"""
        <div class="app-hero">
            <h1>{html.escape(title)}</h1>
            <p>{html.escape(subtitle)}</p>
            {meta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── KPI card ─────────────────────────────────────────────────────────────────

def kpi(
    label: str,
    value: str,
    *,
    unit: str | None = None,
    delta: str | None = None,
    delta_dir: str = "flat",     # "up" | "down" | "flat"
    foot: str | None = None,
) -> None:
    """A single, branded KPI card. Pass already-formatted strings."""
    unit_html  = f'<span class="kpi-unit">{html.escape(unit)}</span>' if unit else ""
    delta_html = (
        f'<div class="kpi-delta {delta_dir}">{html.escape(delta)}</div>'
        if delta else ""
    )
    foot_html  = f'<div class="kpi-foot">{html.escape(foot)}</div>' if foot else ""
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{html.escape(label)}</div>
            <div class="kpi-value">{html.escape(value)}{unit_html}</div>
            {delta_html}
            {foot_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_row(items: list[dict]) -> None:
    """Render a row of KPI cards. Each dict matches the kpi() kwargs."""
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        with col:
            kpi(**item)


# ── Status pill ──────────────────────────────────────────────────────────────

_STATUS_PILL_CLASS = {
    "CLEAN":        "pill-clean",
    "FLAGGED":      "pill-flagged",
    "NEEDS_REVIEW": "pill-review",
    "CONFLICT":     "pill-conflict",
    "MANUAL":       "pill-manual",
    "STALE":        "pill-stale",
    "PENDING":      "pill-pending",
    "ON_TIME":      "pill-ontime",
    "LATE":         "pill-late",
    "MISSING":      "pill-missing",
    "UPCOMING":     "pill-upcoming",
}


def status_pill(status: str) -> str:
    """Return HTML for a status pill (for use inside markdown blocks)."""
    cls = _STATUS_PILL_CLASS.get(status.upper(), "pill-pending")
    return f'<span class="pill {cls}">{html.escape(status)}</span>'


def chip(text: str, color: str = "neutral") -> str:
    """Return inline HTML chip; color in {blue, green, red, amber, neutral}."""
    color = color.lower()
    cls = "" if color == "neutral" else f" chip-{color}"
    return f'<span class="chip{cls}">{html.escape(str(text))}</span>'


# ── Number formatters ───────────────────────────────────────────────────────

def fmt_units(value, dash: str = "—") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return dash
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return dash


def fmt_pct(value, dash: str = "—", precision: int = 1) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return dash
    try:
        return f"{float(value) * 100:+.{precision}f}%"
    except (TypeError, ValueError):
        return dash


def fmt_pp(value, dash: str = "—", precision: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return dash
    try:
        return f"{float(value):+.{precision}f}pp"
    except (TypeError, ValueError):
        return dash


def fmt_lakh(value, dash: str = "—") -> str:
    """Indian-format big numbers as L (lakh) / Cr (crore) units."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return dash
    try:
        v = float(value)
    except (TypeError, ValueError):
        return dash
    if abs(v) >= 1e7:
        return f"{v/1e7:.2f} Cr"
    if abs(v) >= 1e5:
        return f"{v/1e5:.2f} L"
    return f"{v:,.0f}"


def delta_dir(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "flat"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "flat"
    if v > 0.001:  return "up"
    if v < -0.001: return "down"
    return "flat"


# ── Sparkline (mini SVG, no dependency on Plotly) ────────────────────────────

def sparkline(values: list[float], width: int = 110, height: int = 28,
              color: str | None = None) -> str:
    """Return inline SVG sparkline as an HTML string."""
    color = color or theme.BRAND["accent"]
    vals = [float(v) for v in values if v is not None and not pd.isna(v)]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = len(vals)
    dx = width / max(n - 1, 1)
    points = " ".join(
        f"{i*dx:.1f},{height - (v - lo)/span * (height - 4) - 2:.1f}"
        for i, v in enumerate(vals)
    )
    last_x = (n - 1) * dx
    last_y = height - (vals[-1] - lo) / span * (height - 4) - 2
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<polyline points="{points}" fill="none" stroke="{color}" '
        f'stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2.2" fill="{color}"/>'
        f'</svg>'
    )


# ── Footer ───────────────────────────────────────────────────────────────────

def footer(left: str, right: str | None = None) -> None:
    right = right or f"Generated {datetime.now().strftime('%d %b %Y %H:%M')}"
    st.markdown(
        f'<div class="app-footer"><span>{html.escape(left)}</span>'
        f'<span>{html.escape(right)}</span></div>',
        unsafe_allow_html=True,
    )


# ── Empty state ──────────────────────────────────────────────────────────────

def empty_state(title: str, body: str, action: str | None = None) -> None:
    action_html = (
        f'<div style="margin-top:0.6rem;color:#2563EB;font-weight:600;">{html.escape(action)}</div>'
        if action else ""
    )
    st.markdown(
        f"""
        <div style="background:white;border:1px dashed #E2E8F0;border-radius:10px;
                    padding:2rem 1.5rem;text-align:center;color:#64748B;">
            <div style="font-size:1rem;font-weight:600;color:#0F172A;
                        margin-bottom:0.4rem;">{html.escape(title)}</div>
            <div style="font-size:0.85rem;">{html.escape(body)}</div>
            {action_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
