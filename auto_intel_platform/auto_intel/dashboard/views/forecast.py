"""
dashboard/views/forecast.py — Demand Forecast Page
====================================================
3-month ahead forecast for each OEM/segment using Holt-Winters
Exponential Smoothing (statsmodels).

Why Holt-Winters:
  - Handles India's multiplicative seasonality (festive peaks Oct/Nov,
    monsoon dip Jun-Aug, Rabi/Kharif cycle for tractors)
  - Produces confidence intervals — shows the range, not just a line
  - Zero paid API, zero cloud dependency, runs in GitHub Actions
  - Well-established method, trusted by analysts

What analysts can do here:
  - See the 3-month ahead forecast for any OEM/segment
  - See decomposed trend + seasonal pattern
  - Compare forecast vs trailing 6M average (beat/miss signal)
  - Download forecast table as CSV

Data source: wholesale normalized.csv (separate from retail).
"""

from __future__ import annotations

import warnings
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st

import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from dashboard import components as C
from dashboard.theme import OEM_COLORS, plotly_layout
from analytics.rolling import fiscal_year

FORECAST_MONTHS = 3
MIN_HISTORY     = 12    # minimum data points needed for seasonal model


def _run_forecast(series: pd.Series) -> dict | None:
    """
    Run Holt-Winters triple exponential smoothing on a monthly series.

    Returns dict with keys:
      historical, forecast, lower, upper, trend, seasonal, months_out
    Or None if statsmodels unavailable or insufficient data.
    """
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
    except ImportError:
        return None

    if len(series) < MIN_HISTORY:
        return None

    series = series.dropna()
    if len(series) < MIN_HISTORY:
        return None

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            model = ExponentialSmoothing(
                series,
                trend="add",
                seasonal="mul",
                seasonal_periods=12,
                initialization_method="estimated",
            ).fit(optimized=True)
        except Exception:
            # Fallback: additive seasonal (sometimes works better with low variance)
            try:
                model = ExponentialSmoothing(
                    series,
                    trend="add",
                    seasonal="add",
                    seasonal_periods=12,
                    initialization_method="estimated",
                ).fit(optimized=True)
            except Exception:
                return None

    fcast      = model.forecast(FORECAST_MONTHS)
    fitted     = model.fittedvalues

    # Approximate 80% confidence interval from residual std
    resid_std  = float(np.std(model.resid))
    z80        = 1.28
    lower      = fcast - z80 * resid_std * np.sqrt(np.arange(1, FORECAST_MONTHS + 1))
    upper      = fcast + z80 * resid_std * np.sqrt(np.arange(1, FORECAST_MONTHS + 1))
    lower      = lower.clip(0)

    # Decomposition: trend + seasonal
    try:
        trend_comp    = model.level
        seasonal_comp = model.season
    except AttributeError:
        trend_comp    = fitted
        seasonal_comp = pd.Series([1.0] * len(series), index=series.index)

    return {
        "historical": series,
        "fitted":     fitted,
        "forecast":   fcast,
        "lower":      lower,
        "upper":      upper,
        "trend":      trend_comp,
        "seasonal":   seasonal_comp,
        "aic":        model.aic,
    }


def _numpy_forecast(series: pd.Series) -> dict | None:
    """
    Fallback forecast using numpy linear regression + 12-month seasonal index.
    Used when statsmodels is not installed. No external deps beyond numpy/pandas.
    """
    if len(series) < 6:
        return None
    vals = series.values.astype(float)
    n    = len(vals)
    x    = np.arange(n)

    # Linear trend via least-squares
    A = np.vstack([x, np.ones(n)]).T
    slope, intercept = np.linalg.lstsq(A, vals, rcond=None)[0]

    # Seasonal index from residuals (group by month position mod 12)
    trend_vals = slope * x + intercept
    resid      = vals / np.where(trend_vals > 0, trend_vals, 1)
    months_in  = pd.to_datetime(series.index).month
    seas = np.ones(12)
    for m in range(1, 13):
        mask = months_in == m
        if mask.any():
            seas[m - 1] = float(np.mean(resid[mask]))

    # Forecast
    fc_x      = np.arange(n, n + FORECAST_MONTHS)
    fc_trend  = slope * fc_x + intercept
    fc_months_m = [(pd.to_datetime(series.index[-1]) + pd.DateOffset(months=i+1)).month
                   for i in range(FORECAST_MONTHS)]
    fc_seas   = np.array([seas[m - 1] for m in fc_months_m])
    fc_vals   = np.maximum(fc_trend * fc_seas, 0)

    resid_std = float(np.std(vals - trend_vals * np.array([seas[m-1] for m in months_in])))
    z80       = 1.28
    lower     = np.maximum(fc_vals - z80 * resid_std * np.sqrt(np.arange(1, FORECAST_MONTHS+1)), 0)
    upper     = fc_vals + z80 * resid_std * np.sqrt(np.arange(1, FORECAST_MONTHS+1))

    fcast_idx = pd.date_range(
        start=pd.to_datetime(series.index[-1]) + pd.DateOffset(months=1),
        periods=FORECAST_MONTHS, freq="MS"
    )

    return {
        "historical": series,
        "fitted":     pd.Series(trend_vals * np.array([seas[m-1] for m in months_in]),
                                index=series.index),
        "forecast":   pd.Series(fc_vals, index=fcast_idx),
        "lower":      pd.Series(lower,   index=fcast_idx),
        "upper":      pd.Series(upper,   index=fcast_idx),
        "trend":      pd.Series(trend_vals, index=series.index),
        "seasonal":   pd.Series([seas[m-1] for m in months_in], index=series.index),
        "aic":        float("nan"),
        "_method":    "Linear trend + seasonal index (numpy fallback)",
    }


def _forecast_months_index(last_hist_month: str, n: int) -> list[str]:
    """Generate n future month strings in YYYY-MM format."""
    from datetime import datetime
    dt = datetime.strptime(last_hist_month + "-01", "%Y-%m-%d")
    result = []
    for i in range(1, n + 1):
        month = dt.month + i
        year  = dt.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        result.append(f"{year}-{month:02d}")
    return result


def render():
    from dashboard.data_layer import load_all
    norm_df, _, _, _ = load_all()

    if norm_df.empty:
        C.empty_state("No Data", "Run the pipeline first to generate wholesale data.")
        return

    # ── Controls ─────────────────────────────────────────────────────────────
    col1, col2 = st.columns([2, 1])

    with col1:
        oem_options = sorted(norm_df["company_key"].unique())
        display_map = {}
        if "display_name" in norm_df.columns:
            for _, row in norm_df[["company_key", "display_name"]].drop_duplicates().iterrows():
                display_map[row["company_key"]] = row["display_name"]
        else:
            display_map = {k: k for k in oem_options}

        selected_oem = st.selectbox(
            "OEM",
            oem_options,
            format_func=lambda k: display_map.get(k, k),
            key="fc_oem",
        )

    oem_df = norm_df[norm_df["company_key"] == selected_oem]

    with col2:
        seg_options = sorted(oem_df["segment"].unique())
        selected_seg = st.selectbox("Segment", seg_options, key="fc_seg")

    sub = (
        oem_df[oem_df["segment"] == selected_seg]
        .sort_values("filing_month_year")
        .drop_duplicates("filing_month_year")
    )

    # ── Check data sufficiency ────────────────────────────────────────────────
    if len(sub) < MIN_HISTORY:
        st.warning(
            f"Need at least {MIN_HISTORY} months of data for a seasonal forecast. "
            f"Currently have {len(sub)} month(s) for {selected_oem} / {selected_seg}."
        )
        return

    # Convert to plain numpy float — statsmodels rejects pandas IntegerArray
    values = pd.to_numeric(sub["total"], errors="coerce").fillna(0).to_numpy(dtype=float)
    series = pd.Series(values, index=pd.to_datetime(sub["filing_month_year"].values + "-01"))

    # ── Run model ─────────────────────────────────────────────────────────────
    result = _run_forecast(series)

    if result is None:
        # statsmodels not available — fall back to numpy linear trend
        result = _numpy_forecast(series)

    if result is None:
        C.empty_state("Insufficient data", "Need at least 6 months to generate a forecast.")
        return

    hist        = result["historical"]
    fitted      = result["fitted"]
    fcast       = result["forecast"]
    lower       = result["lower"]
    upper       = result["upper"]

    last_hist   = sub["filing_month_year"].max()
    fcast_months = _forecast_months_index(last_hist, FORECAST_MONTHS)

    # ── KPIs ─────────────────────────────────────────────────────────────────
    oem_color   = OEM_COLORS.get(selected_oem, "#2563EB")
    trailing_6m = float(series.iloc[-6:].mean()) if len(series) >= 6 else float(series.mean())
    next_month_fc= float(fcast.iloc[0])
    beat_miss    = (next_month_fc - trailing_6m) / trailing_6m if trailing_6m else None

    C.section_header(
        "3-Month Forecast",
        sub=f"{display_map.get(selected_oem, selected_oem)} · {selected_seg} · "
            f"Holt-Winters seasonal model trained on {len(hist)} months",
    )

    fc_items = []
    for i, (fm, fv, lo, hi) in enumerate(
        zip(fcast_months, fcast.values, lower.values, upper.values)
    ):
        fc_items.append({
            "label": fm,
            "value": C.fmt_units(int(fv)),
            "unit":  "units",
            "foot":  f"80% CI: {C.fmt_indian(int(lo))} – {C.fmt_indian(int(hi))}",
            "delta_dir": "up" if fv > trailing_6m else "down",
        })

    C.kpi_row(fc_items)

    C.kpi_row([
        {
            "label": "Trailing 6M Average",
            "value": C.fmt_units(int(trailing_6m)),
            "unit":  "units/month",
            "foot":  "Baseline for beat/miss comparison",
        },
        {
            "label": "Next Month vs Trailing 6M",
            "value": C.fmt_pct(beat_miss) if beat_miss is not None else "—",
            "delta_dir": C.delta_dir(beat_miss) if beat_miss else "flat",
            "foot":  "Positive = forecast above recent run-rate",
        },
        {
            "label": "Model",
            "value": "Holt-Winters" if "_method" not in result else "Linear + Seasonal",
            "foot":  result.get("_method", f"AIC: {result['aic']:.0f} · Seasonal period: 12 months"),
        },
        {
            "label": "Training data",
            "value": f"{len(hist)} months",
            "foot":  f"{sub['filing_month_year'].min()} → {last_hist}",
        },
    ])

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Main forecast chart ───────────────────────────────────────────────────
    C.section_header("Historical + Forecast", sub="Shaded band = 80% confidence interval")

    hist_x  = sub["filing_month_year"].tolist()
    fitted_y = fitted.values.tolist()

    fig = go.Figure()

    # Confidence band
    fc_x_all = fcast_months
    fig.add_trace(go.Scatter(
        x=fc_x_all + fc_x_all[::-1],
        y=upper.tolist() + lower.tolist()[::-1],
        fill="toself",
        fillcolor=f"rgba({','.join(str(int(int(oem_color[1:3], 16))) for _ in range(3))},0.12)"
                  if oem_color.startswith("#") else "rgba(37,99,235,0.12)",
        line=dict(width=0),
        name="80% CI",
        showlegend=True,
    ))

    # Fitted line
    fig.add_trace(go.Scatter(
        x=hist_x,
        y=fitted_y,
        mode="lines",
        name="Model fit",
        line=dict(color="#94A3B8", width=1, dash="dot"),
    ))

    # Actual historical
    fig.add_trace(go.Scatter(
        x=hist_x,
        y=hist.values.tolist(),
        mode="lines+markers",
        name="Actual (wholesale)",
        line=dict(color=oem_color, width=2),
        marker=dict(size=5),
    ))

    # Forecast line
    fig.add_trace(go.Scatter(
        x=fcast_months,
        y=fcast.values.tolist(),
        mode="lines+markers",
        name="Forecast",
        line=dict(color=oem_color, width=2.5, dash="dash"),
        marker=dict(size=8, symbol="diamond"),
    ))

    # Vertical separator between history and forecast
    # Note: add_vline annotation kwargs are broken in Plotly 5.19 on Streamlit Cloud.
    # Use add_shape + add_annotation separately — fully compatible.
    fig.add_shape(
        type="line",
        x0=last_hist, x1=last_hist,
        y0=0, y1=1,
        xref="x", yref="paper",
        line=dict(color="#64748B", dash="dot", width=1.5),
    )
    fig.add_annotation(
        x=last_hist,
        y=1.0,
        xref="x", yref="paper",
        text="Forecast",
        showarrow=False,
        font=dict(color="#94A3B8", size=11),
        xanchor="left",
        yanchor="bottom",
        xshift=6,
    )

    fig.update_layout(
        **plotly_layout(
            height=400,
            title=f"{display_map.get(selected_oem, selected_oem)} · {selected_seg} — Wholesale Forecast",
        ),
        yaxis_title="Units (Wholesale)",
        legend=dict(orientation="h", y=-0.12),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Seasonal decomposition ────────────────────────────────────────────────
    C.section_header(
        "Seasonal Pattern",
        sub="Average monthly index — shows which months typically run above/below trend",
    )

    seasonal_vals = result["seasonal"]
    if hasattr(seasonal_vals, "values"):
        seasonal_vals = seasonal_vals.values

    # Average seasonal factor per calendar month
    months_in_data = pd.to_datetime(hist.index).month
    seasonal_by_month = {}
    for m_num, sv in zip(months_in_data, seasonal_vals[:len(months_in_data)]):
        seasonal_by_month.setdefault(m_num, []).append(sv)

    month_labels  = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    seasonal_avg  = [float(np.mean(seasonal_by_month.get(m+1, [1.0]))) for m in range(12)]

    fig2 = go.Figure(go.Bar(
        x=month_labels,
        y=seasonal_avg,
        marker_color=[
            oem_color if v >= (sum(seasonal_avg)/12) else "#475569"
            for v in seasonal_avg
        ],
        text=[f"{v:.2f}×" for v in seasonal_avg],
        textposition="outside",
    ))
    fig2.add_hline(
        y=sum(seasonal_avg)/12,
        line_dash="dot",
        line_color="#94A3B8",
        annotation_text="Average",
    )
    fig2.update_layout(
        **plotly_layout(height=300, title="Seasonal Index by Month (1.0 = average)"),
        yaxis_title="Seasonal Factor",
    )
    st.plotly_chart(fig2, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Forecast table ────────────────────────────────────────────────────────
    C.section_header("Forecast Table")

    fc_table = pd.DataFrame({
        "Month":         fcast_months,
        "Forecast":      [C.fmt_indian(int(v)) for v in fcast.values],
        "Lower (80% CI)": [C.fmt_indian(int(v)) for v in lower.values],
        "Upper (80% CI)": [C.fmt_indian(int(v)) for v in upper.values],
        "vs Trailing 6M": [
            f"{(v - trailing_6m)/trailing_6m*100:+.1f}%" if trailing_6m else "—"
            for v in fcast.values
        ],
    })
    st.dataframe(fc_table, use_container_width=True, hide_index=True)

    st.caption(
        "**Methodology:** Holt-Winters Exponential Smoothing (additive trend, multiplicative seasonality). "
        "Trained on all available historical wholesale data for this OEM/segment. "
        "80% CI = ±1.28σ of residual std scaled by forecast horizon. "
        "**This is a statistical forecast, not a guarantee.** "
        "Use alongside fundamentals (new model launches, price changes, macro)."
    )

    C.footer("Forecast: Holt-Winters model · Wholesale data source · FADA retail tracked separately")
