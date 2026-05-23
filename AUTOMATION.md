# Indian Auto Monthly Monitor — Automation & Data Integrity

## Principle

Build the dataset first. The dashboard reads only validated, normalized data
and never parses PDFs at view time. Data accuracy is the number-one priority;
the platform refuses to surface a number that hasn't passed the validation
chain.

## Source priority

1. **OEM Investor Relations pages** (primary — 100% legal, companies publish this themselves)
2. **Manual review queue** (IR page unreachable, parser failure, or data conflict)

NSE/BSE exchange APIs are **disabled by default** (`use_exchange_apis: False` in `config.py`).
They require a valid data license under NSE/BSE Terms of Service.
Only enable if you hold such a license.

The underlying data is identical — OEM IR press-release PDFs are the same documents
filed on the exchanges. Going directly to the source is legally cleaner and more
stable long-term (exchange API endpoints change; company IR pages rarely do).

When two IR page entries appear for the same `(oem, segment, month)`, the pipeline
runs `cross_source_agreement` and accepts only if totals match within 2%.
Otherwise routes to the review queue with status `CONFLICT`.

## Scheduling

| Window                 | When                                          | What it does                          |
|------------------------|-----------------------------------------------|----------------------------------------|
| **Filing window**      | 1st-8th of each month, 4×/day at 09:30 / 13:30 / 17:30 / 21:30 IST | Aggressive polling to catch each OEM's filing as soon as it lands. Looks back 60 days so late filings aren't missed. |
| **Daily baseline**     | Every day at 09:30 IST                        | Refresh + sanity-check any historical corrections.                |
| **Manual**             | `workflow_dispatch` (GitHub UI)               | Force re-download or run for specific OEMs.                       |

Workflows live in:
- `.github/workflows/auto-data-pipeline.yml` — daily baseline
- `.github/workflows/auto-data-pipeline-filing-window.yml` — 1st-8th heavy
- `auto_intel_platform/auto_intel/.github/workflows/pipeline.yml` — inner-mirror

## Validation chain (in order)

1. **Arithmetic check** — `domestic + exports ≈ total ±5%`
2. **Sanity check** — total in `[10, 2,000,000]`
3. **YoY anomaly** — `|YoY| > 50%` ⇒ `FLAGGED`
4. **Z-score anomaly** — `|z| ≥ 3σ` vs the OEM's trailing 12 months ⇒ `FLAGGED`
5. **Reconciliation vs stored** — `>10%` delta vs existing row ⇒ `CONFLICT`
6. **Granular reconciliation** — `Σ(sub-segments) ≈ total ±3%`, otherwise `FLAGGED` with note
7. **Cross-source agreement** — multi-source disagreement `>2%` ⇒ `CONFLICT`
8. **Manual override preservation** — never auto-overwrite a `MANUAL` row

Every flagged row carries a `review_note` explaining which rule fired.

## Data quality scorecard

Every stored row gets a 0-100 score (see `analytics/quality.py`):
- 40 — parser status (CLEAN=40 / MANUAL=35 / FLAGGED=25 / NEEDS_REVIEW=0)
- 30 — parser confidence × 30
- 10 — filing_date present
- 10 — source URL present
- 10 — arithmetic check passes

The OEM scorecard rolls these up over the trailing 12 months and is shown
on the **Data Quality** dashboard page.

## Filing SLA

For each OEM, `typical_filing_day` is recorded in `registry.py`. SLA = filed
by `typical_filing_day + 2 days` after the sales month-end. The Filing
Tracker page renders an `ON_TIME / LATE / MISSING / UPCOMING` pill per cell
and an OEM-level SLA scorecard (on-time %, median days late).

## Monthly close report

After every pipeline run, `pipeline/monthly_close.py` writes:
- `logs/close_report_<YYYY-MM>.md` — markdown summary (industry total, YoY,
  EV penetration, per-OEM SLA & quality)
- `logs/close_report_<YYYY-MM>.json` — same data, machine-readable

The markdown is also surfaced in the GitHub Actions run summary via
`$GITHUB_STEP_SUMMARY` so analysts can read it without opening the repo.

## Production rules

- Preserve source metadata for every accepted row.
- Keep parser output deterministic and idempotent.
- Treat exact duplicates as no-ops.
- Treat changed accepted rows as upserts unless the existing row is `MANUAL`.
- Send validation failures and large reconciliation mismatches to review.
- Track filing status separately from normalized operational data.
- Never silently produce wrong data — fail loudly via `parser_status`.

## Adding a new source

Each new collector (OEM IR pages, FADA, SIAM bulletins) should return the
same announcement dict shape as the NSE/BSE fetchers:

```python
{
    "_source":     "OEM_IR",
    "_id":         "...",
    "symbol":      "...",
    "company":     "...",
    "title":       "...",
    "category":    "Monthly Sales",
    "exchange_dt": "YYYY-MM-DD",
    "file_url":    "https://...",
    "attachment":  "...",
    "raw":         {...},
}
```

Downstream filtering, downloading, extraction, validation, storage, and
dashboard code remain unchanged.
