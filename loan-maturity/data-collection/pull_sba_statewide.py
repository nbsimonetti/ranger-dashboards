"""
Statewide (all-Texas) SBA extract for the Professional Services BD and Small
Business & Ag Lending dashboards.

Same source and filters as pull_sba.py (TX, active status, still in its maturity
window) but with NO county restriction, and a slim field set. Writes
loan-maturity/loans_statewide.json. The raw FOIA CSVs are large and untracked, so
this runs offline (quarterly, alongside the footprint pull) and the JSON is
committed for the dashboards + CI to consume.

Run:  python loan-maturity/data-collection/pull_sba_statewide.py
"""
import csv
import json
import re
import datetime as dt
from pathlib import Path

csv.field_size_limit(10 ** 7)
HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "loans_statewide.json"
TODAY = dt.date.today()

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
            maturity = add_months(approval, row.get("terminmonths"))
            if not maturity or maturity < TODAY:
                continue
            lender = (row.get("bankname") or "").strip()
            if program == "504" and not lender:
                lender = "(SBA 504 - partner bank not disclosed)"
            out.append({
                "borrower": (row.get("borrname") or "").strip(),
                "borrower_city": (row.get("borrcity") or "").strip().title(),
                "county": normalize_county(row.get("projectcounty")).title(),
                "lender": lender,
                "loan_amount": float(row.get("grossapproval") or 0) or 0,
                "sba_guaranteed_amount": float(row.get("sbaguaranteedapproval") or 0) or 0,
                "approval_date": approval.isoformat() if approval else None,
                "maturity_date": maturity.isoformat(),
                "interest_rate": float(row.get("initialinterestrate") or 0) or None,
                "rate_type": (row.get("fixedorvariableinterestind") or "").strip(),
                "naics_code": (row.get("naicscode") or "").strip(),
                "naics_description": (row.get("naicsdescription") or "").strip(),
                "loan_status": status,
                "source": "sba-" + program,
            })
    print("    kept %d TX active/in-window from %s" % (len(out), filename))
    return out


def main():
    loans = []
    for program, filename in INPUT_FILES:
        loans.extend(process(program, filename))
    counties = sorted({r["county"] for r in loans if r["county"]})
    meta = {
        "as_of": "2026-03-31", "scope": "all Texas (statewide)",
        "generated": TODAY.isoformat(), "loans": len(loans),
        "counties": len(counties),
        "total_amount": round(sum(r["loan_amount"] for r in loans)),
        "source": "SBA 7(a)/504 FOIA bulk (data.sba.gov)",
    }
    OUT.write_text(json.dumps({"meta": meta, "loans": loans}, separators=(",", ":")),
                   encoding="utf-8")
    print("wrote %s: %d loans, %d counties, $%.1fB, %.0f MB"
          % (OUT.name, len(loans), len(counties),
             meta["total_amount"] / 1e9, OUT.stat().st_size / 1e6))


if __name__ == "__main__":
    main()
