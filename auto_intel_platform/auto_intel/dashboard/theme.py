"""
dashboard/theme.py — design tokens & global CSS
=================================================
A single import that lifts a bare Streamlit page into something that doesn't
look like a default Streamlit page. Apply once at the top of app.py via
`apply_theme()`.
"""

from __future__ import annotations
import streamlit as st


# ── Brand palette ─────────────────────────────────────────────────────────────
BRAND = {
    "primary":     "#0F172A",   # slate-900 — headers
    "accent":      "#2563EB",   # blue-600 — primary actions, links
    "accent_soft": "#DBEAFE",   # blue-100 — subtle backgrounds
    "ink":         "#0F172A",
    "ink_muted":   "#475569",   # slate-600
    "ink_subtle":  "#94A3B8",   # slate-400
    "panel":       "#FFFFFF",
    "page":        "#F8FAFC",   # slate-50
    "border":      "#E2E8F0",   # slate-200
    "success":     "#15803D",   # green-700
    "warning":     "#B45309",   # amber-700
    "danger":      "#B91C1C",   # red-700
    "neutral":     "#64748B",   # slate-500
}

# Segment colors — high-contrast, print-safe
SEGMENT_COLORS = {
    "PV":      "#1D4ED8",   # blue-700
    "CV":      "#B91C1C",   # red-700
    "2W":      "#15803D",   # green-700
    "3W":      "#C2410C",   # orange-700
    "Tractor": "#7C3AED",   # violet-600
    "EV":      "#0E7490",   # cyan-700
}

# OEM colors — used in time-series + share charts
OEM_COLORS = {
    "MARUTI":         "#1D4ED8",
    "TATAMOTORS_PV":  "#DC2626",
    "TATAMOTORS_CV":  "#7F1D1D",
    "MAHINDRA_AUTO":  "#15803D",
    "MAHINDRA_FARM":  "#065F46",
    "BAJAJ":          "#B45309",
    "HEROMOTOCO":     "#6D28D9",
    "TVS":            "#BE185D",
    "ASHOKLEY":       "#0E7490",
    "ESCORTS":        "#65A30D",
    "EICHER":         "#EA580C",
    "OLA_ELECTRIC":   "#0F766E",
}


def apply_theme():
    """Inject global CSS + Plotly template defaults. Call once at app start."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


_GLOBAL_CSS = """
<style>
/* ───── Page base ───── */
.main > div.block-container {
    padding-top: 1.25rem;
    padding-bottom: 4rem;
    max-width: 1500px;
}

body, .stApp {
    background-color: #F8FAFC !important;
    color: #0F172A;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI",
        Roboto, Oxygen, Ubuntu, sans-serif;
}

/* ───── Sidebar ───── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0F172A 0%, #1E293B 100%);
    border-right: 1px solid #1E293B;
}
section[data-testid="stSidebar"] * {
    color: #E2E8F0 !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] h4 {
    color: #F8FAFC !important;
    letter-spacing: -0.01em;
}
section[data-testid="stSidebar"] .stRadio label,
section[data-testid="stSidebar"] .stSelectbox label {
    font-weight: 600 !important;
    color: #94A3B8 !important;
    text-transform: uppercase;
    font-size: 0.7rem;
    letter-spacing: 0.06em;
}
section[data-testid="stSidebar"] hr {
    border-color: #334155 !important;
}

/* ───── Header / top hero ───── */
.app-hero {
    background: linear-gradient(135deg, #0F172A 0%, #1E3A8A 100%);
    color: white;
    padding: 1.5rem 1.75rem;
    border-radius: 12px;
    margin-bottom: 1.25rem;
    box-shadow: 0 4px 14px rgba(15, 23, 42, 0.08);
}
.app-hero h1 {
    color: white;
    font-size: 1.55rem;
    margin: 0 0 0.25rem 0;
    font-weight: 700;
    letter-spacing: -0.01em;
}
.app-hero p {
    color: #CBD5E1;
    margin: 0;
    font-size: 0.92rem;
}
.app-hero .hero-meta {
    display: flex;
    gap: 1.5rem;
    margin-top: 0.85rem;
    font-size: 0.78rem;
    color: #94A3B8;
}
.app-hero .hero-meta span strong {
    color: #F8FAFC;
    font-weight: 600;
}

/* ───── Section header ───── */
.section-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin: 1.5rem 0 0.8rem 0;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #E2E8F0;
}
.section-header .section-bar {
    width: 4px;
    height: 1.1rem;
    background: #2563EB;
    border-radius: 2px;
}
.section-header h2 {
    margin: 0;
    font-size: 1.05rem;
    font-weight: 600;
    letter-spacing: -0.005em;
    color: #0F172A;
}
.section-header .section-sub {
    margin-left: auto;
    color: #64748B;
    font-size: 0.78rem;
}

/* ───── KPI card ───── */
.kpi-card {
    background: white;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 0.95rem 1.05rem 0.85rem;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
    height: 100%;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.kpi-card:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06);
}
.kpi-label {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #64748B;
    font-weight: 600;
    margin-bottom: 0.35rem;
}
.kpi-value {
    font-size: 1.55rem;
    font-weight: 700;
    color: #0F172A;
    line-height: 1.1;
    letter-spacing: -0.015em;
    font-variant-numeric: tabular-nums;
}
.kpi-unit {
    font-size: 0.75rem;
    font-weight: 500;
    color: #94A3B8;
    margin-left: 0.3rem;
}
.kpi-delta {
    margin-top: 0.45rem;
    font-size: 0.82rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}
.kpi-delta.up   { color: #15803D; }
.kpi-delta.down { color: #B91C1C; }
.kpi-delta.flat { color: #64748B; }
.kpi-foot {
    margin-top: 0.5rem;
    font-size: 0.72rem;
    color: #94A3B8;
}

/* ───── Status pill ───── */
.pill {
    display: inline-block;
    padding: 0.18rem 0.55rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.02em;
}
.pill-clean    { background: #DCFCE7; color: #166534; }
.pill-flagged  { background: #FEF3C7; color: #92400E; }
.pill-review   { background: #FEE2E2; color: #991B1B; }
.pill-conflict { background: #FCE7F3; color: #9D174D; }
.pill-manual   { background: #E0E7FF; color: #3730A3; }
.pill-stale    { background: #E2E8F0; color: #475569; }
.pill-pending  { background: #F1F5F9; color: #64748B; }
.pill-ontime   { background: #DCFCE7; color: #166534; }
.pill-late     { background: #FEE2E2; color: #991B1B; }
.pill-missing  { background: #FECACA; color: #7F1D1D; }
.pill-upcoming { background: #DBEAFE; color: #1E3A8A; }

/* ───── DataFrame polish ───── */
[data-testid="stDataFrame"] {
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    overflow: hidden;
}
[data-testid="stDataFrame"] thead tr th {
    background: #F1F5F9 !important;
    color: #475569 !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    font-size: 0.7rem;
    letter-spacing: 0.04em;
    border-bottom: 1px solid #E2E8F0 !important;
}
[data-testid="stDataFrame"] tbody tr td {
    font-variant-numeric: tabular-nums;
    font-size: 0.85rem;
    border-bottom: 1px solid #F1F5F9 !important;
}

/* ───── Tabs ───── */
[data-baseweb="tab-list"] {
    border-bottom: 1px solid #E2E8F0;
    gap: 0.25rem;
}
[data-baseweb="tab"] {
    background: transparent !important;
    color: #64748B !important;
    font-weight: 600 !important;
    padding: 0.55rem 1rem !important;
    border-radius: 6px 6px 0 0 !important;
}
[data-baseweb="tab"][aria-selected="true"] {
    color: #2563EB !important;
    background: #DBEAFE !important;
}

/* ───── Buttons ───── */
.stDownloadButton button, .stButton button {
    border-radius: 8px !important;
    border: 1px solid #E2E8F0 !important;
    background: white !important;
    color: #0F172A !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    padding: 0.45rem 0.9rem !important;
    transition: all 0.12s ease;
}
.stDownloadButton button:hover, .stButton button:hover {
    border-color: #2563EB !important;
    color: #2563EB !important;
}

/* ───── Metric (built-in) cleanup so it matches our cards ───── */
[data-testid="stMetric"] {
    background: white;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 0.7rem 0.9rem;
}
[data-testid="stMetricLabel"] {
    font-weight: 600 !important;
    color: #64748B !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: 0.7rem !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.45rem !important;
    color: #0F172A !important;
    font-weight: 700 !important;
    font-variant-numeric: tabular-nums;
}

/* ───── Expander ───── */
[data-testid="stExpander"] {
    background: white;
    border: 1px solid #E2E8F0 !important;
    border-radius: 10px !important;
    box-shadow: none !important;
}
[data-testid="stExpander"] summary p {
    font-weight: 600;
    color: #0F172A;
}

/* ───── Hide Streamlit chrome ───── */
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; }
.stApp > div:nth-child(1) > div:nth-child(1) {
    padding-top: 0 !important;
}

/* ───── Footer credit ───── */
.app-footer {
    margin-top: 2.5rem;
    padding-top: 1rem;
    border-top: 1px solid #E2E8F0;
    color: #94A3B8;
    font-size: 0.72rem;
    display: flex;
    justify-content: space-between;
}

/* ───── Inline mini chips ───── */
.chip {
    display: inline-block;
    padding: 0.12rem 0.45rem;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 600;
    background: #F1F5F9;
    color: #475569;
    margin-right: 0.3rem;
}
.chip-blue   { background: #DBEAFE; color: #1E40AF; }
.chip-green  { background: #DCFCE7; color: #166534; }
.chip-red    { background: #FEE2E2; color: #991B1B; }
.chip-amber  { background: #FEF3C7; color: #92400E; }
</style>
"""


# ── Plotly template ──────────────────────────────────────────────────────────

def plotly_layout(height: int = 360, title: str | None = None) -> dict:
    """Default Plotly layout — matches the brand."""
    return dict(
        title=dict(
            text=title or "",
            font=dict(size=14, color=BRAND["primary"], family="Inter"),
            x=0, y=0.97, xanchor="left",
        ),
        height=height,
        margin=dict(l=10, r=10, t=40 if title else 10, b=10),
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(family="Inter", size=12, color=BRAND["ink"]),
        xaxis=dict(
            showgrid=False, showline=True, linecolor=BRAND["border"],
            tickfont=dict(size=11, color=BRAND["ink_muted"]),
        ),
        yaxis=dict(
            showgrid=True, gridcolor=BRAND["border"], zeroline=False,
            tickfont=dict(size=11, color=BRAND["ink_muted"]),
        ),
        legend=dict(
            orientation="h", y=-0.18, font=dict(size=11),
            bgcolor="rgba(0,0,0,0)",
        ),
        hoverlabel=dict(
            bgcolor="white", bordercolor=BRAND["border"],
            font=dict(family="Inter", size=12, color=BRAND["ink"]),
        ),
    )
