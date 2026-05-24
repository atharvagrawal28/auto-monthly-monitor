# India Auto Monthly Monitor

Institutional-grade Indian automotive sales intelligence platform.  
**12 OEMs · 6 segments · 24 months history · Live Streamlit dashboard**

Built by [Atharv Agrawal](https://www.linkedin.com/in/atharv-agrawal-295743233)

---

## What This Is

A self-updating operational intelligence platform for Indian OEM monthly wholesale sales data.  
Data source: **OEM Investor Relations pages** (companies' own public filings — 100% legal, zero paid APIs).

---

## OEMs Tracked

| OEM | Segments |
|-----|----------|
| Maruti Suzuki | PV |
| Tata Motors | PV, CV |
| Mahindra Auto | PV, EV |
| Mahindra Farm | Tractor |
| Bajaj Auto | 2W, 3W |
| Hero MotoCorp | 2W |
| TVS Motor | 2W, 3W |
| Ashok Leyland | CV |
| Escorts Kubota | Tractor |
| Eicher (Royal Enfield) | 2W |
| Ola Electric | EV |

---

## Dashboard Pages

| Page | What it shows |
|------|---------------|
| ⚡ Overview | Industry Quick Summary · Segment KPIs · Top movers |
| 🔍 Monitoring | OEM-level grid with YoY, MoM, FYTD, market share, z-score alerts |
| 🏢 Deep Dive | Single-OEM profile · 24M trend · sub-segment breakdown · filing lineage |
| 📊 Market Share | Ranked share · HHI concentration · share migration |
| 📤 Exports | Export volume · mix · wholesale-export decoupling |
| ⚡ EV Penetration | Industry EV share · per-OEM EV exposure |
| 📱 Retail Pulse | FADA retail registrations · dealer channel inventory |
| 📅 Filing Tracker | Filing SLA · Data Quality scorecard · coverage gaps |
| 🔄 Admin | Review queue · Manual data entry |

---

## Infrastructure (Zero Cost Forever)

| Component | Technology |
|-----------|-----------|
| Data fetch | GitHub Actions free tier — 4x/day on filing window (1st-8th of month) |
| Storage | CSV files in repo: data/normalized.csv, data/granular.csv |
| Dashboard | Streamlit Community Cloud (free) |
| Forecast | statsmodels Holt-Winters + numpy fallback |
| CI/CD | auto-data-pipeline.yml + auto-data-pipeline-filing-window.yml |

---

## Folder Structure

```
files (7)/                          <- git repo root
├── app.py                          <- Streamlit Cloud entrypoint
├── requirements.txt                <- Python dependencies
├── runtime.txt                     <- Python 3.11
├── .github/workflows/              <- GitHub Actions pipelines
├── auto_intel_platform/
│   └── auto_intel/
│       ├── dashboard/              <- Streamlit pages + components + theme
│       │   ├── app.py              <- Navigation + sidebar
│       │   ├── data_layer.py       <- Central cached data loader
│       │   ├── components.py       <- KPI cards, formatters
│       │   ├── theme.py            <- Brand colours + Plotly layout
│       │   └── views/              <- One file per page
│       ├── pipeline/               <- Fetch -> Extract -> Normalize -> Store
│       ├── analytics/              <- Market share, TTM, FYTD, z-score
│       ├── parsers/                <- OEM-specific PDF normalizers
│       ├── data/                   <- normalized.csv, granular.csv
│       └── logs/                   <- Pipeline run logs (gitignored)
├── SETUP.md
├── DEPLOYMENT.md
├── AUTOMATION.md
└── AUTOMATION_AUDIT.md
```

---

## Quick Start (Local)

```bash
git clone https://github.com/atharvagrawal28/auto-monthly-monitor.git
cd auto-monthly-monitor
pip install -r requirements.txt

cd auto_intel_platform/auto_intel
python data/generate_sample.py
python data/generate_retail_sample.py

cd ../..
streamlit run app.py
```

---

## Data Pipeline

Runs automatically via GitHub Actions:
- **Filing window** (1st-8th of month): every 6 hours
- **Daily baseline**: once per day for integrity checks

Trigger manually: GitHub -> Actions -> "Auto Data Pipeline" -> Run workflow

---

## Data Quality

Every normalized row has confidence_score, parser_status, quality_score, and raw_row_hash.

Run audit anytime:
```bash
cd auto_intel_platform/auto_intel
python run_audit.py
```

*Last audit: 2026-05-25 · Critical failures: 0 · Data fit for institutional use*
