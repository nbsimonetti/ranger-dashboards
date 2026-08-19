"""
Statewide (all-Texas) SBA extract feeding three dashboards: Loan Maturity,
Professional Services BD, and Small Business & Ag Lending.

Same source and filters as pull_sba.py (TX, active status, still in its maturity
window) but with NO county restriction. Emits the SAME full record schema and the
SAME loan_id scheme as pull_sba.py, so the sparse geocode cache (loans-geocoded.json,
keyed by loan_id) still matches. Writes loan-maturity/loans_statewide.json.

The raw FOIA CSVs are large and untracked, so this runs offline (quarterly,
alongside the footprint pull) and the JSON is committed for the dashboards to fetch.

Run:  python loan-maturity/data-collection/pull_sba_statewide.py
"""
import csv
import json
import re
import datetime as dt
from collections import Counter
from pathlib import Path

csv.field_size_limit(10 ** 7)
HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "loans_statewide.json"
TODAY = dt.date.today()
NOW_ISO = dt.datetime.now(dt.timezone.utc).isoformat()

INACTIVE = {"P I F", "PIF", "CHGOFF", "CANCLD", "CANCELLED"}
INPUT_FILES = [
    ("7a", "foia-7a-fy2010-fy2019-asof-260331.csv"),
    ("7a", "foia-7a-fy2020-present-asof-260331.csv"),
    ("504", "foia-504-fy2010-present-asof-260331.csv"),
]


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def add_months(d, months):
    if not d or not months:
        return None
    try:
        months = int(months)
    except (TypeError, ValueError):
        return None
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    day = min(d.day, [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return dt.date(year, month, day)


def normalize_county(c):
    if not c:
        return ""
    return re.sub(r"\s+", " ", c.upper().replace("COUNTY", "").replace("CO.", "").strip())


def loan_id(program, locationid, borrname, approval):
    base = "sba-%s-%s" % (program, locationid)
    if not locationid:
        base = "sba-%s-%s-%s" % (program, borrname.strip()[:30], approval)
    return base.lower().replace(" ", "_").replace("/", "_")


def process(program, filename):
    path = HERE / filename
    if not path.exists():
        print("  SKIP (not downloaded):", filename)
        return []
    print("  processing", filename)
    out = []
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        for n, row in enumerate(csv.DictReader(f)):
            if n and n % 100000 == 0:
                print("    row %d..." % n)
            if (row.get("projectstate") or "").strip().upper() != "TX":
                continue
            status = (row.get("loanstatus") or "").strip().upper()
            if status in INACTIVE:
                continue
            approval = parse_date(row.get("approvaldate"))
            term = row.get("terminmonths")
            maturity = add_months(approval, term)
            if not maturity or maturity < TODAY:
                continue
            gross = float(row.get("grossapproval") or 0) or 0
            lender = (row.get("bankname") or "").strip()
            lstate = (row.get("bankstate") or "").strip().upper()
            if program == "504" and not lender:
                lender = "(SBA 504 - partner bank not disclosed)"
                lstate = ""
            county = normalize_county(row.get("projectcounty"))
            out.append({
                "loan_id": loan_id(program, row.get("locationid", ""),
                                   row.get("borrname", ""), row.get("approvaldate", "")),
                "source": "sba-" + program,
                "source_url": "https://data.sba.gov/dataset/7-a-504-foia",
                "source_doc_id": row.get("locationid") or None,
                "borrower": (row.get("borrname") or "").strip(),
                "borrower_address": ((row.get("borrstreet") or "") + ", " + (row.get("borrcity") or "")
                                     + ", " + (row.get("borrstate") or "") + " "
                                     + (row.get("borrzip") or "")).strip(", "),
                "borrower_city": (row.get("borrcity") or "").strip().title(),
                "borrower_state": (row.get("borrstate") or "").strip().upper(),
                "borrower_zip": (row.get("borrzip") or "").strip(),
                "lender": lender,
                "lender_state": lstate,
                "lender_city": (row.get("bankcity") or "").strip().title(),
                "lender_fdic_cert": (row.get("bankfdicnumber") or "").strip(),
                "county": county.title(),
                "project_state": "TX",
                "loan_amount": gross,
                "sba_guaranteed_amount": float(row.get("sbaguaranteedapproval") or 0) or 0,
                "approval_date": approval.isoformat() if approval else None,
                "term_months": int(term) if term and term.isdigit() else None,
                "maturity_date": maturity.isoformat(),
                "months_to_maturity": (maturity.year - TODAY.year) * 12 + (maturity.month - TODAY.month),
                "interest_rate": float(row.get("initialinterestrate") or 0) or None,
                "rate_type": (row.get("fixedorvariableinterestind") or "").strip(),
                "naics_code": (row.get("naicscode") or "").strip(),
                "naics_description": (row.get("naicsdescription") or "").strip(),
                "jobs_supported": int(row.get("jobssupported") or 0) or None,
                "business_type": (row.get("businesstype") or "").strip(),
                "loan_status": status,
                "has_collateral": (row.get("collateralind") or "").strip().upper() == "Y",
                "source_context": "SBA %s approval %s - term %smo - status %s"
                                  % (program, row.get("approvaldate", ""), term, status),
                "scraped_at": NOW_ISO,
            })
    print("    kept %d TX active/in-window" % len(out))
    return out


def main():
    loans = []
    for program, filename in INPUT_FILES:
        loans.extend(process(program, filename))
    loans.sort(key=lambda r: r["maturity_date"])
    counties = sorted({r["county"] for r in loans if r["county"]})
    # Match loans.json's meta schema exactly (the dashboard JS reads these keys;
    # sources_seen is a {source: count} dict, not a list). footprint_counties keeps
    # its name for JS compatibility but now counts all statewide counties.
    meta = {
        "generated_at": NOW_ISO,
        "sba_asof": "2026-03-31",
        "sba_asof_tag": "260331",
        "total_loans": len(loans),
        "total_dollars": float(sum(r["loan_amount"] for r in loans)),
        "sources_seen": dict(Counter(r["source"] for r in loans)),
        "footprint_counties": len(counties),
        "scope": "all Texas (statewide)",
    }
    OUT.write_text(json.dumps({"meta": meta, "loans": loans}, separators=(",", ":")),
                   encoding="utf-8")
    print("wrote %s: %d loans, %d counties, $%.1fB, %.0f MB"
          % (OUT.name, len(loans), len(counties),
             meta["total_dollars"] / 1e9, OUT.stat().st_size / 1e6))


if __name__ == "__main__":
    main()
