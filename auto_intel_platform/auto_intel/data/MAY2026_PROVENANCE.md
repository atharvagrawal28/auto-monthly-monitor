# May 2026 Data Provenance & Methodology

**Loaded:** 2026-06-02 · **Source:** Official OEM press-release PDFs (BSE/NSE filings dated 01-Jun-2026)
**Method:** Manually transcribed from PDFs, arithmetic-verified, YoY from each filing's own May-2025 actuals, April-2026 reconstructed by exact arithmetic (FYTD − May).

All figures are **wholesale dispatches (domestic + exports)** per SIAM convention, except Ola Electric (VAHAN registrations — the only figure Ola discloses).

---

## May 2026 — headline figures (as loaded)

| OEM (key) | Segment | Domestic | Exports | **Total** | YoY | MoM | Source line in PDF |
|-----------|---------|---------:|--------:|----------:|----:|----:|--------------------|
| MARUTI | PV | 190,337 | 41,914 | **232,251** | +38.9% | +2.0% | Domestic PV 190,337 + Exports 41,914 (excl. 7,239 OEM-sales & 3,198 Super Carry LCV) |
| TATAMOTORS_PV | PV | 48,573 | 700 | **49,273** | +35.5% | — | PV 59,790 − EV 10,517 (carved out to avoid double-count) |
| TATAMOTORS_PV | EV | 10,517 | 0 | **10,517** | +85.0% | — | "EV IB + Domestic 10,517" |
| TATAMOTORS_CV | CV | 30,784 | 2,066 | **32,850** | +16.7% | — | Domestic 30,784 + IB 2,066 |
| MAHINDRA_AUTO | PV | 58,021 | 1,552 | **59,573** | +10.7%* | — | UV incl. exports 59,573 |
| MAHINDRA_AUTO | CV | 24,079 | 0 | **24,079** | +18.6% | +2.8% | LCV<3.5T domestic (3,490 + 20,589) |
| MAHINDRA_FARM | Tractor | 47,845 | 1,850 | **49,695** | +22.3% | +2.6% | Farm Equipment total |
| BAJAJ | 2W | 209,528 | 183,676 | **393,204** | +18.3% | −10.6% | 2-Wheelers sub-total |
| BAJAJ | 3W | 38,503 | 29,550 | **68,053** | +30.2% | −7.8% | Bajaj "Commercial Vehicles" = 3-wheelers |
| HEROMOTOCO | 2W | 536,784 | 33,284 | **570,068** | +12.3% | +0.7% | Total dispatches |
| TVS | 2W | 384,565 | 158,546 | **543,111** | +30.5% | — | Total 2W (incl. iQube EV) |
| TVS | 3W | 6,029 | 17,445 | **23,474** | +55.4% | — | 3-wheeler total; IB 3W 17,445 |
| ASHOKLEY | CV | 14,148 | 775 | **14,923** | −3.6% | +1.9% | Total Vehicles (dom+exp) |
| ESCORTS | Tractor | 11,887 | 423 | **12,310** | +18.9% | +13.4% | Tractor total |
| EICHER | 2W | 94,115 | 9,116 | **103,231** | +15.4% | −8.8% | Royal Enfield motorcycles |
| OLA_ELECTRIC | EV | 15,139 | 0 | **15,139** | — | +22.9% | VAHAN registrations (15,139 vs Apr 12,323) |
| EICHER_VECV | CV | 7,564 | 414 | **7,978** | +7.8% | +9.0% | VECV total incl. EVs & Volvo (NEW line) |

**Industry total tracked (May 2026): 2,209,729 units across 13 OEMs.**

\* Mahindra Auto PV YoY uses the disclosed domestic UV growth (+11%, 52,431→58,021); a comparable May-2025 total-incl-exports was not published.

---

## Key methodology decisions (industry standard)

1. **Wholesale, not retail** — all OEMs reported on dispatch basis (SIAM standard). Ola is the exception: it only discloses VAHAN registrations, flagged accordingly.

2. **EV carve-out (Tata)** — Tata reports PV *including* EV. To avoid double-counting in industry/EV-penetration math, EV (10,517) is a separate segment row and PV is shown ex-EV (49,273). PV + EV = 59,790 = the reported total. ✓

3. **Bajaj "Commercial Vehicles" → 3W** — Bajaj's CV line is its three-wheeler/quadricycle business; mapped to the 3W segment.

4. **Maruti PV = 232,251** — domestic PV (incl. Vans) + exports. Excludes 7,239 units sold to other OEM (Toyota rebadges) and 3,198 Super Carry (LCV), which are reported separately and are not passenger vehicles in the strict sense.

5. **Mahindra exports** — M&M discloses exports as a single lump (5,000), only splitting domestic by segment. UV exports (1,552) are derivable from the narrative ("overall 59,573 incl. exports"); CV/3W exports are not, so CV is tracked on a domestic basis.

6. **Mahindra EV** — not disclosed in the May auto release; intentionally left as a coverage gap rather than estimated (no fabrication).

7. **April 2026 reconstruction** — where a filing published a 2-month FYTD column (Apr–May), real April = FYTD − May (exact arithmetic). This gives a **real MoM** for: Maruti, Mahindra Auto-CV, Mahindra Farm, Bajaj (2W/3W), Hero, Ashok Leyland, Escorts, Royal Enfield, Eicher-VECV, Ola. Tata (PV/EV/CV), TVS (2W/3W) and Mahindra Auto-PV did not publish a YTD column → MoM shown as "—" until their next consecutive real month loads.

---

## Coverage notes

- **Eicher VECV (CV)** added as a new tracked entity (`EICHER_VECV`).
- **Missing major OEM:** Hyundai Motor India (#2 PV, listed) — not yet tracked; add when its monthly PDF is available.
- **Granular / model detail** for Deep Dive captured for Maruti, Tata-CV, Ashok Leyland, Royal Enfield, Hero, TVS, Mahindra Auto, and Eicher-VECV (with real model names from the filings).
