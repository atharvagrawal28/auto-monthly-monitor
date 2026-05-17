# India Auto Monthly Monitor — Setup Guide

## What You're Building
A self-updating operational intelligence platform for Indian auto OEM monthly sales data.
12 OEMs | 5 segments | 18 months of history | Live Streamlit dashboard

---

## STEP 1 — Set Up Your Local Environment

### 1.1 Install Prerequisites
- Python 3.11+ → https://python.org/downloads
- VS Code → https://code.visualstudio.com
- Git → https://git-scm.com

### 1.2 Create Project Folder
Open VS Code terminal (Ctrl + `) and run:

```bash
mkdir auto_intel
cd auto_intel
```

### 1.3 Copy All Project Files
Copy every file from this delivery into your `auto_intel/` folder.
The structure should look like:

```
auto_intel/
├── schema.py
├── registry.py
├── requirements.txt
├── pipeline/
│   ├── __init__.py
│   ├── fetch.py
│   ├── filter.py
│   ├── download.py
│   ├── extract.py
│   ├── validate.py
│   ├── store.py
│   └── run.py
├── parsers/
│   ├── __init__.py
│   ├── maruti.py
│   ├── tata.py
│   ├── mm.py
│   └── generic.py
├── dashboard/
│   ├── __init__.py
│   └── app.py
├── data/
│   └── generate_sample.py
├── .streamlit/
│   └── config.toml
└── .github/
    └── workflows/
        └── pipeline.yml
```

---

## STEP 2 — Create Virtual Environment

```bash
python -m venv venv

# Windows:
venv\Scripts\activate

# Mac/Linux:
source venv/bin/activate
```

---

## STEP 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

Takes about 2-3 minutes. You will see packages installing.

---

## STEP 4 — Generate Sample Data (Run Dashboard Immediately)

Before live exchange data is available, load 18 months of realistic sample data:

```bash
python data/generate_sample.py
```

You should see:
```
Generating sample normalized data...
  → 216 rows → data/normalized.csv
Generating granular breakdown...
  → 846 rows → data/granular.csv
Generating filing status...
  → 216 rows → data/filing_status.csv
Sample data generation complete.
```

---

## STEP 5 — Run the Dashboard Locally

```bash
streamlit run dashboard/app.py
```

Your browser will open automatically at:
```
http://localhost:8501
```

You will see:
- Filing Tracker (landing page)
- Monitoring Mode
- Deep Dive Mode
- Comparative Mode
- Review Queue

---

## STEP 6 — Set Up GitHub Repository

### 6.1 Create GitHub Account
Go to https://github.com and sign up if you don't have an account.

### 6.2 Create New Repository
- Click "New repository"
- Name: `auto-intel` (or any name)
- Set to **Private**
- Do NOT initialize with README (you have your own files)

### 6.3 Push Your Code

```bash
git init
git add .
git commit -m "initial: auto intel platform v1"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/auto-intel.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username.

---

## STEP 7 — Deploy to Streamlit Cloud

### 7.1 Go to Streamlit Cloud
Visit: https://share.streamlit.io
Sign in with your GitHub account.

### 7.2 Create New App
- Click "New app"
- Repository: select `auto-intel`
- Branch: `main`
- Main file path: `dashboard/app.py`
- Click "Deploy"

Deployment takes 2-3 minutes.
Your dashboard will be live at:
```
https://YOUR_USERNAME-auto-intel-dashboard-app-XXXXX.streamlit.app
```

---

## STEP 8 — Enable GitHub Actions (Daily Automation)

### 8.1 Add Secrets (Optional — for live exchange data)
In your GitHub repo:
- Go to Settings → Secrets and variables → Actions
- Add secret: `ANTHROPIC_API_KEY` (if using AI insights in Phase 3)

### 8.2 Enable Actions
- Go to your repo → Actions tab
- Click "Enable GitHub Actions"
- The pipeline will now run daily at 9:30 AM IST automatically

### 8.3 Run Manually (Test)
- Go to Actions → "Auto Intel Daily Pipeline"
- Click "Run workflow"
- Click "Run workflow" (green button)

Watch the logs — it will fetch from NSE/BSE and update your data files.

---

## STEP 9 — Run Live Pipeline (When Ready for Real Data)

```bash
# Run for all OEMs (last 45 days)
python pipeline/run.py

# Run for specific OEMs only
python pipeline/run.py --oems MARUTI TATAMOTORS_PV TATAMOTORS_CV

# Run with custom date range
python pipeline/run.py --from 01-03-2025 --to 30-04-2025

# Force re-download all PDFs
python pipeline/run.py --force
```

---

## STEP 10 — Onboarding Strategy (Recommended Order)

Do NOT try to run all 12 OEMs on day 1.

**Week 1:** Start with Maruti only
```bash
python pipeline/run.py --oems MARUTI
```
Maruti has the most consistent press release format. Get this working cleanly first.

**Week 2:** Add Tata
```bash
python pipeline/run.py --oems MARUTI TATAMOTORS_PV TATAMOTORS_CV
```

**Week 3:** Add M&M
```bash
python pipeline/run.py --oems MARUTI TATAMOTORS_PV TATAMOTORS_CV MAHINDRA_AUTO MAHINDRA_FARM
```

**Week 4+:** Add remaining OEMs one by one.

---

## Daily Workflow (Once Running)

1. GitHub Actions runs at 9:30 AM IST
2. Fetches announcements from NSE/BSE for all OEMs
3. Filters for monthly sales press releases
4. Downloads PDFs
5. Extracts and normalizes data
6. Validates and runs reconciliation
7. Saves to `data/normalized.csv`
8. Commits changes to GitHub
9. Streamlit Cloud auto-reloads from updated data

You open your Streamlit URL each morning and the data is already updated.

---

## Understanding the Review Queue

When you see rows in the Review Queue:
- `NEEDS_REVIEW` — parser couldn't extract data confidently
- `CONFLICT` — new data differs >10% from stored data

To handle:
1. Open Review Queue page in dashboard
2. View the flagged row and its note
3. Check the original PDF in `data/pdfs/COMPANY/`
4. Either approve (if data looks correct) or enter corrected numbers
5. Click "Approve & Move to Dataset"

Never ignore the review queue. It protects your dataset from silent corruption.

---

## File Locations

| File | Purpose |
|------|---------|
| `data/normalized.csv` | Main dataset — one row per OEM/segment/month |
| `data/granular.csv` | Sub-segment breakdown |
| `data/filing_status.csv` | Filing freshness tracker |
| `data/review_queue.csv` | Rows needing human review |
| `data/pdfs/` | Downloaded PDF filings |
| `logs/` | Daily pipeline logs |

---

## Common Issues

**"No data available" on dashboard**
→ Run `python data/generate_sample.py` first

**"pdfplumber not found"**
→ Run `pip install pdfplumber`

**NSE returns empty results**
→ Normal — NSE blocks direct API without session. The pipeline handles this.
→ BSE fallback will activate automatically.

**Parser returns NEEDS_REVIEW for all rows**
→ The OEM changed their PDF format. Check `logs/pipeline_YYYYMMDD.log`
→ Identify the new format and update the parser's format version detection.

**GitHub Actions fails with permission error**
→ Go to repo Settings → Actions → General → Workflow permissions → Read and write

---

## What to Build Next (Phase 2)

After Phase 1 is stable (2-3 months of clean data):

1. Add VAHAN integration:
   - Register at https://vahan.parivahan.gov.in
   - Daily retail registration data
   - Compute wholesale vs retail divergence

2. Add to `pipeline/vahan.py`:
   - Fetch state-wise registration by OEM
   - Normalize to same schema
   - Add "channel_inventory" derived metric

3. Dashboard: Add "Channel Check" tab showing wholesale-retail divergence

---

## Architecture Reference

```
NSE/BSE APIs
    ↓ pipeline/fetch.py
Raw Announcements
    ↓ pipeline/filter.py (keyword + regex scoring)
Relevant Filings
    ↓ pipeline/download.py
Local PDFs
    ↓ pipeline/extract.py (pdfplumber, all pages, scored tables)
Candidate Tables
    ↓ parsers/maruti.py | tata.py | mm.py | generic.py
    (format version detection → column mapping → row extraction)
NormalizedRow objects
    ↓ pipeline/validate.py (arithmetic + YoY + reconciliation)
Validated / Review Queue
    ↓ pipeline/store.py
data/normalized.csv
    ↓ dashboard/app.py
Streamlit Dashboard
```

---

## Quick Reference Commands

```bash
# Generate sample data
python data/generate_sample.py

# Run dashboard
streamlit run dashboard/app.py

# Run full pipeline
python pipeline/run.py

# Run specific OEM
python pipeline/run.py --oems MARUTI

# Check data
python -c "from pipeline.store import load_normalized; import pandas as pd; df = load_normalized(); print(df.tail(5))"
```
