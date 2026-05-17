# Indian Auto Monthly Monitor Automation

## Goal

Build the dataset first. The dashboard should read only validated, normalized
data and should never parse PDFs at view time.

## Source Priority

1. NSE corporate announcements
2. BSE corporate announcements
3. OEM investor-relations / press-release pages as fallback
4. Manual review queue for parser failures, conflicts, and delayed filings

NSE/BSE remain the source of record for listed-company filings. OEM pages are
useful for redundancy, corrections, and cases where a release appears there
before exchange metadata is easy to classify.

## Daily Run

The GitHub Actions workflow runs daily at 09:30 IST and can also be triggered
manually. The pipeline fetches recent announcements, filters likely monthly
sales releases, downloads PDFs, extracts tables, normalizes rows, validates
against history, writes clean rows, and pushes review items into
`review_queue.csv`.

## Production Rules

- Preserve source metadata for every accepted row.
- Keep parser output deterministic and idempotent.
- Treat exact duplicates as no-ops.
- Treat changed accepted rows as upserts unless an existing row is MANUAL.
- Send validation failures and large reconciliation mismatches to review.
- Track filing status separately from normalized operational data.

## Next Source Layer

Add OEM-page collectors only after the exchange pipeline is stable. Each new
collector should return the same announcement dictionary shape as NSE/BSE:

```python
{
    "_source": "OEM_IR",
    "_id": "...",
    "symbol": "...",
    "company": "...",
    "title": "...",
    "category": "Monthly Sales",
    "exchange_dt": "YYYY-MM-DD",
    "file_url": "https://...",
    "attachment": "...",
    "raw": {...},
}
```

This keeps downstream filtering, downloading, extraction, validation, storage,
and dashboard code unchanged.
