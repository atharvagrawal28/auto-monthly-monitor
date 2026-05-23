# India Auto Monthly Monitor — Deployment Guide

Zero infrastructure cost. Runs forever on GitHub Actions + Streamlit Community Cloud.

---

## Stack

| Layer       | Tool                              | Cost     |
|-------------|-----------------------------------|----------|
| Scheduler   | GitHub Actions (free public repo) | Free     |
| Dashboard   | Streamlit Community Cloud         | Free     |
| Storage     | CSV files committed to the repo   | Free     |
| PDF parsing | pdfplumber (open-source)          | Free     |
| LLM         | Off by default (`use_llm: False`) | Free     |

---

## Step 1 — Fork the repo

Fork this repo to your GitHub account. The workflows run on any public repo with no billing required (2,000 GitHub Actions minutes/month free, the pipeline uses ~10 min/run).

---

## Step 2 — Set up GitHub Secrets (optional)

No secrets are required for the pipeline to run. The only optional secret is:

| Secret              | Purpose                                                       |
|---------------------|---------------------------------------------------------------|
| `ANTHROPIC_API_KEY` | Enables LLM narrative summaries (not used by default)         |

To add: **Repo → Settings → Secrets and variables → Actions → New repository secret.**

---

## Step 3 — Enable GitHub Actions

Navigate to **Actions** in your forked repo and enable workflows if prompted. The three workflows activate automatically:

| Workflow file                                  | Trigger                                     |
|------------------------------------------------|---------------------------------------------|
| `auto-data-pipeline.yml`                       | Daily at 09:30 IST (04:00 UTC)              |
| `auto-data-pipeline-filing-window.yml`         | 4×/day on 1st–8th of each month             |
| `auto_intel_platform/auto_intel/.github/workflows/pipeline.yml` | Same (inner mirror) |

---

## Step 4 — Generate initial sample data

Run once locally to seed the CSVs before your first real pipeline run:

```bash
cd auto_intel_platform/auto_intel
pip install -r requirements.txt
python data/generate_sample.py
```

This writes `data/normalized.csv` (408 rows) and `data/granular.csv` (1,296 rows) with 24 months of realistic wholesale data for all 12 OEMs.

---

## Step 5 — Deploy to Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. Click **New app**.
3. Set:
   - **Repository**: your fork
   - **Branch**: `main`
   - **Main file path**: `app.py`
4. Click **Deploy**.

The dashboard reads CSVs directly from the repo. Every time the pipeline commits new data, Streamlit auto-reloads within the cache TTL (5 minutes).

---

## Step 6 — Manual pipeline run

To force a refresh for specific OEMs, go to:

**GitHub → Actions → Auto Intel Daily Pipeline → Run workflow**

Inputs:
- `force_download`: `true` to re-download all PDFs
- `oems`: space-separated keys (e.g. `MARUTI BAJAJ TATAMOTORS`) — blank = all

---

## How data flows

```
NSE/BSE API
    │
    ▼
pipeline/fetch.py       ← pulls corporate announcements
    │
    ▼
pipeline/download.py    ← downloads PDFs (SHA256 idempotent)
    │
    ▼
parsers/{oem}.py        ← extracts domestic / exports / total per segment
    │
    ▼
pipeline/validate.py    ← 8-rule chain (arithmetic, sanity, YoY, z-score,
    │                      reconciliation, granular, cross-source, MANUAL guard)
    ▼
pipeline/store.py       ← upserts to data/normalized.csv + data/granular.csv
    │
    ▼
pipeline/monthly_close.py ← writes logs/close_report_YYYY-MM.md + .json
    │
    ▼
git commit + push       ← Action commits the updated CSVs
    │
    ▼
Streamlit Cloud         ← reads CSVs, shows dashboard
```

---

## Keeping it free forever

- **Do not turn on `use_llm: True`** unless you add an `ANTHROPIC_API_KEY` secret and accept per-token costs.
- **Keep the repo public** — private repos consume paid Action minutes beyond 2,000/month.
- **CSV storage** scales to millions of rows before GitHub LFS is needed (typical: ~50 KB/year).
- **No database** — all analytics run in-memory from pandas at dashboard load time.

---

## Adding a new OEM

1. Add an `OEMConfig` entry to `registry.py` with the NSE/BSE symbol and `typical_filing_day`.
2. Add a parser in `parsers/{oem}.py` (or map to `generic.py` if the PDF is table-based).
3. Register the parser in `pipeline/run.py` under the `PARSER_MAP`.
4. Re-run `data/generate_sample.py` to extend sample data with the new OEM stream.

---

## Troubleshooting

| Symptom                        | Fix                                                      |
|-------------------------------|----------------------------------------------------------|
| Dashboard shows no data       | Run `python data/generate_sample.py` to seed CSVs       |
| Pipeline fails in CI          | Check Actions log; NSE/BSE may rate-limit — retry later  |
| OEM shows MISSING in tracker  | Filing may be delayed; check NSE announcements manually  |
| Row stuck in CONFLICT status  | Open Review Queue page and approve/correct manually      |
| `ModuleNotFoundError: numpy`  | `pip install numpy>=1.26.0`                              |
