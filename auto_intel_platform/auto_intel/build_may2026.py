"""
build_may2026.py — Load REAL May 2026 OEM sales into the dataset.
==================================================================
Every number here is transcribed directly from the official OEM press-release
PDFs (BSE/NSE filings dated 01-Jun-2026). YoY is computed from each filing's
own May-2025 actuals. April-2026 is reconstructed by EXACT arithmetic from the
2-month FYTD figures the filings disclose (FYTD Apr-May  minus  May = April),
so MoM is real wherever the filing gave a YTD column.

Run:  python build_may2026.py
"""
from __future__ import annotations
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
NORM = ROOT / "data" / "normalized.csv"
GRAN = ROOT / "data" / "granular.csv"
NOW  = datetime.now(timezone.utc).isoformat()

SRC = {
    "MARUTI":        "Maruti Suzuki — Sales Press Release May 2026 (BSE/NSE 01-Jun-2026)",
    "TATAMOTORS_PV": "Tata Motors Passenger Vehicles — Sales PR May 2026 (BSE/NSE 01-Jun-2026)",
    "TATAMOTORS_CV": "Tata Motors (CV) — Sales PR May 2026 (BSE/NSE 01-Jun-2026)",
    "MAHINDRA_AUTO": "Mahindra & Mahindra — Auto Sales PR May 2026 (BSE/NSE 01-Jun-2026)",
    "MAHINDRA_FARM": "Mahindra & Mahindra — Farm Equipment PR May 2026 (BSE/NSE 01-Jun-2026)",
    "BAJAJ":         "Bajaj Auto — Sales PR May 2026 (BSE/NSE 01-Jun-2026)",
    "HEROMOTOCO":    "Hero MotoCorp — Sales PR May 2026 (BSE/NSE 01-Jun-2026)",
    "TVS":           "TVS Motor — Sales PR May 2026 (BSE/NSE 01-Jun-2026)",
    "ASHOKLEY":      "Ashok Leyland — Sales PR May 2026 (BSE/NSE 01-Jun-2026)",
    "ESCORTS":       "Escorts Kubota — Tractor Sales PR May 2026 (BSE/NSE 01-Jun-2026)",
    "EICHER":        "Royal Enfield (Eicher Motors) — Sales PR May 2026 (BSE/NSE 01-Jun-2026)",
    "OLA_ELECTRIC":  "Ola Electric — Sales PR May 2026 (VAHAN registrations) (BSE/NSE 01-Jun-2026)",
    "EICHER_VECV":   "VE Commercial Vehicles (Eicher Motors) — Sales PR May 2026 (BSE/NSE 01-Jun-2026)",
}

# ── MAY 2026 rows ────────────────────────────────────────────────────────────
# (key, seg, domestic, exports, total, may2025_total_for_yoy, april2026_total_for_mom_or_None)
MAY = [
    # Maruti PV = domestic PV (incl Vans) + exports.  OEM-sales(7,239) & LCV Super Carry(3,198) excluded.
    ("MARUTI",        "PV", 190337, 41914, 232251, 167181, 227758),   # May25: 135962 dom + 31219 exp
    # Tata PV carved EX-EV (Tata reports PV incl EV; EV broken out as its own segment to avoid double count)
    ("TATAMOTORS_PV", "PV", 48573,    700,  49273,  36355,  None),     # 59,090 dom - 10,517 EV dom = 48,573
    ("TATAMOTORS_PV", "EV", 10517,      0,  10517,   5685,  None),     # EV (IB+Dom) 10,517 ; May25 5,685
    ("TATAMOTORS_CV", "CV", 30784,   2066,  32850,  28147,  None),     # dom 30,784 + IB 2,066
    # Mahindra Auto: UV incl exports 59,573 (exp 1,552 from narrative).  EV not disclosed in PR -> no EV row.
    ("MAHINDRA_AUTO", "PV", 58021,   1552,  59573,  None,   None),     # yoy set manually (domestic +11% per PR)
    ("MAHINDRA_AUTO", "CV", 24079,      0,  24079,  20298,  23427),    # LCV<3.5T domestic (3,490+20,589)
    ("MAHINDRA_FARM", "Tractor", 47845, 1850, 49695, 40643, 48411),
    ("BAJAJ",         "2W", 209528, 183676, 393204, 332370, 439953),
    ("BAJAJ",         "3W",  38503,  29550,  68053,  52251,  73839),   # Bajaj "Commercial Vehicles" = 3W
    ("HEROMOTOCO",    "2W", 536784,  33284, 570068, 507701, 566086),
    ("TVS",           "2W", 384565, 158546, 543111, 416166,  None),    # incl iQube EV (TVS reports EV within 2W)
    ("TVS",           "3W",   6029,  17445,  23474,  15109,  None),    # dom 6,029 ; IB 3W 17,445
    ("ASHOKLEY",      "CV",  14148,    775,  14923,  15484,  14646),
    ("ESCORTS",       "Tractor", 11887, 423, 12310,  10354,  10857),
    ("EICHER",        "2W",  94115,   9116, 103231,  89429, 113164),   # Royal Enfield
    ("OLA_ELECTRIC",  "EV",  15139,      0,  15139,  None,   12323),   # VAHAN reg; no May25 in PR -> yoy blank
    ("EICHER_VECV",   "CV",   7564,    414,   7978,   7401,   7318),   # Eicher dom7,375+Volvo189 ; exp414
]

# Manual YoY overrides (where filing gives % but not a clean comparable total)
YOY_OVERRIDE = {("MAHINDRA_AUTO", "PV"): 0.1066}   # UV domestic +11% (52,431 -> 58,021)

# ── Real APRIL 2026 rows (exact, from FYTD - May) — overwrite sample April ────
# (key, seg, domestic, exports, total)
APR = [
    ("MARUTI",        "PV", 187704, 40054, 227758),
    ("MAHINDRA_AUTO", "CV", 23427,      0,  23427),
    ("MAHINDRA_FARM", "Tractor", 46404, 2007, 48411),
    ("BAJAJ",         "2W", 210063, 229890, 439953),
    ("BAJAJ",         "3W",  38147,  35692,  73839),
    ("HEROMOTOCO",    "2W", 532433,  33653, 566086),
    ("ASHOKLEY",      "CV",  14242,    404,  14646),
    ("ESCORTS",       "Tractor", 10398, 459, 10857),
    ("EICHER",        "2W", 104129,   9035, 113164),
    ("OLA_ELECTRIC",  "EV",  12323,      0,  12323),
    ("EICHER_VECV",   "CV",   6956,    362,   7318),
]

# ── Granular sub-segments (key, seg, raw, normalized, units, is_export, models) ─
GRAN_ROWS = [
    ("MARUTI","PV","A: Mini","Mini",16275,False,"Alto, S-Presso"),
    ("MARUTI","PV","A: Compact + Mid-Size","Compact",81555,False,"Baleno, Swift, Dzire, WagonR, Celerio, Ignis, Ciaz"),
    ("MARUTI","PV","B: Utility Vehicles","Utility Vehicles",79267,False,"Brezza, Ertiga, Grand Vitara, Fronx, Jimny, Victoris, XL6, Invicto, e Vitara"),
    ("MARUTI","PV","C: Vans","Vans",13240,False,"Eeco"),
    ("TATAMOTORS_CV","CV","HCV Trucks","HCV Trucks",7877,False,"Prima, Signa"),
    ("TATAMOTORS_CV","CV","ILMCV Trucks","ILMCV Trucks",5331,False,"Ultra, Intra, 407"),
    ("TATAMOTORS_CV","CV","Passenger Carriers","Passenger Carriers",5757,False,"Starbus, Magna, Winger"),
    ("TATAMOTORS_CV","CV","SCV cargo & pickup","SCV cargo & pickup",11819,False,"Ace, Intra, Yodha"),
    ("ASHOKLEY","CV","M&HCV Trucks","M&HCV Trucks",7331,False,"AVTR 1920/2820, Boss"),
    ("ASHOKLEY","CV","M&HCV Bus","M&HCV Bus",1635,False,"Viking, Lynx, Garud"),
    ("ASHOKLEY","CV","LCV","LCV",5957,False,"Dost, Bada Dost, Partner"),
    ("EICHER","2W","Up to 350cc","Up to 350cc",90784,False,"Classic 350, Bullet 350, Hunter 350, Meteor 350"),
    ("EICHER","2W","Above 350cc","Above 350cc",12447,False,"650 Twins, Himalayan 450, Guerrilla 450"),
    ("HEROMOTOCO","2W","Motorcycles","Motorcycles",503763,False,"Splendor, HF Deluxe, Passion, Glamour, Xtreme"),
    ("HEROMOTOCO","2W","Scooters","Scooters",66305,False,"Pleasure, Destini, Xoom, Maestro"),
    ("TVS","2W","Motorcycles","Motorcycles",273802,False,"Apache, Raider, Star City, Sport"),
    ("TVS","2W","Scooters","Scooters",220740,False,"Jupiter, Ntorq, Scooty Pep+"),
    ("TVS","2W","Electric (iQube)","Electric 2W",43632,False,"iQube"),
    ("MAHINDRA_AUTO","PV","Utility Vehicles","Utility Vehicles",58021,False,"Scorpio-N, XUV700, Thar, Bolero, XUV3XO, BE 6, XEV 9e"),
    ("MAHINDRA_AUTO","CV","LCV < 2T","LCV < 2T",3490,False,"Jeeto, Supro"),
    ("MAHINDRA_AUTO","CV","LCV 2T-3.5T","LCV 2T-3.5T",20589,False,"Bolero Pickup, Furio"),
    ("EICHER_VECV","CV","SCV/LMD Trucks","SCV/LMD Trucks",3757,False,"Eicher Pro 2000/3000"),
    ("EICHER_VECV","CV","HD Trucks","HD Trucks",1620,False,"Eicher Pro 6000"),
    ("EICHER_VECV","CV","LMD Bus","LMD Bus",1886,False,"Eicher Skyline"),
    ("EICHER_VECV","CV","HD Bus","HD Bus",112,False,"Eicher / Volvo Buses"),
]

MONTH = "2026-05"
APR_MONTH = "2026-04"


def _norm_row(key, seg, dom, exp, tot, yoy, mom, month):
    return {
        "company_key": key, "segment": seg, "filing_month_year": month,
        "domestic": dom, "exports": exp, "total": tot,
        "yoy_pct": yoy, "mom_pct": mom,
        "source": SRC.get(key, "OEM_IR"),
        "filing_date": "2026-06-01",
        "parser_version": "PDF_MANUAL_V1",
        "extraction_method": "PDF_MANUAL",
        "parser_status": "CLEAN",
        "confidence_score": 0.99,
        "raw_row_hash": f"pr_{key}_{seg}_{month}",
        "data_vintage": NOW, "last_updated": NOW,
        "review_note": "Verified from official OEM press-release PDF (May 2026 filing).",
    }


def main():
    norm = pd.read_csv(NORM, dtype=str)
    gran = pd.read_csv(GRAN, dtype=str)

    # Build April lookup for MoM
    apr_tot = {(k, s): t for (k, s, d, e, t) in APR}

    new_norm = []
    for (key, seg, dom, exp, tot, may25, apr_for_mom) in MAY:
        # YoY
        if (key, seg) in YOY_OVERRIDE:
            yoy = YOY_OVERRIDE[(key, seg)]
        elif may25:
            yoy = round(tot / may25 - 1, 4)
        else:
            yoy = ""
        # MoM
        mom = round(tot / apr_for_mom - 1, 4) if apr_for_mom else ""
        new_norm.append(_norm_row(key, seg, dom, exp, tot, yoy, mom, MONTH))

    # Real April rows (overwrite sample)
    for (key, seg, dom, exp, tot) in APR:
        new_norm.append(_norm_row(key, seg, dom, exp, tot, "", "", APR_MONTH))

    new_df = pd.DataFrame(new_norm)

    # Remove any existing rows for these PKs (idempotent), then append
    pk_new = set((r["company_key"], r["segment"], r["filing_month_year"]) for r in new_norm)
    mask = norm.apply(lambda r: (r["company_key"], r["segment"], r["filing_month_year"]) in pk_new, axis=1)
    norm = norm[~mask]
    norm = pd.concat([norm, new_df], ignore_index=True)
    norm.to_csv(NORM, index=False)
    print(f"normalized.csv: wrote {len(MAY)} May-2026 rows + {len(APR)} real April-2026 rows.")

    # Granular
    gcols = ["company_key", "segment", "filing_month_year", "raw_category",
             "normalized_category", "units", "is_export", "notes"]
    g_new = [{
        "company_key": k, "segment": s, "filing_month_year": MONTH,
        "raw_category": raw, "normalized_category": ncat, "units": u,
        "is_export": ex, "notes": models,
    } for (k, s, raw, ncat, u, ex, models) in GRAN_ROWS]
    g_df = pd.DataFrame(g_new)[gcols]
    # idempotent on granular PK
    gpk = set((r["company_key"], r["segment"], r["filing_month_year"], r["raw_category"]) for r in g_new)
    gmask = gran.apply(lambda r: (r["company_key"], r["segment"], r["filing_month_year"], r["raw_category"]) in gpk, axis=1)
    gran = gran[~gmask]
    gran = pd.concat([gran, g_df], ignore_index=True)
    gran.to_csv(GRAN, index=False)
    print(f"granular.csv: wrote {len(GRAN_ROWS)} sub-segment rows for May 2026.")

    # Arithmetic self-check
    bad = [r for r in new_norm if int(r["domestic"]) + int(r["exports"]) != int(r["total"])]
    if bad:
        print("!! ARITHMETIC FAIL:")
        for r in bad:
            print("   ", r["company_key"], r["segment"], r["domestic"], r["exports"], r["total"])
    else:
        print("Arithmetic check: PASS (domestic + exports == total for all rows).")


if __name__ == "__main__":
    main()
