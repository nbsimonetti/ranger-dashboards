"""
Statewide (all-Texas) SBA extract feeding three dashboards: Loan Maturity,
Professional Services BD, and Small Business & Ag Lending.

Same source and filters as pull_sba.py (TX, active status, still in its maturity
window) but with NO county restriction. Emits the SAME full record schema and the
SAME loan_id scheme as pull_sba.py, so the sparse geocode cache (loans-geocoded.json,
keyed by loan_id) still matches. Writes loan-maturity/loans_statewide.json.

The raw FOIA CSVs are large and untracked, so this runs offline (quarterly,
alongside the footprint pull) and the JSON is committed for the dashboards to fetch.

Status filter: loans whose status says paid in full, prepaid, cancelled, not
funded or charged off are dropped, in both the 7(a) codes and the 504 file's
wording (see INACTIVE below), as are loans with a blank status and troubled
loans (in liquidation, purchased by SBA, CLSLN).

Run:  python loan-maturity/data-collection/pull_sba_statewide.py
      ... --selftest        check the status filter offline and exit
      ... --asof YYYY-MM-DD --stamp ISO-TIMESTAMP
                            rebuild as of an earlier run: pins the maturity window,
                            months_to_maturity, generated_at and scraped_at
"""
import argparse
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

# Loan statuses that mean the loan is off the books. The 7(a) files use short
# codes (P I F, CHGOFF, CANCLD); the 504 file spells the same outcomes out
# (PREPAID IN FULL, PAID IN FULL, PAID IN FULL (LIQ), CANCELED, NOT FUNDED,
# CHARGED-OFF). Both vocabularies are listed, a pattern catches spelling
# variants, and a blank status is treated as inactive. Troubled loans are dropped
# as well: in liquidation (LIQUID), purchased by SBA and not yet charged off
# (PURCH(NOT C/O)) and CLSLN. Everything else stays in: current, committed, past
# due and deferred. pull_sba.py and pull_sba_statewide.py carry the same block;
# keep them in step.
INACTIVE = {
    "P I F", "PIF", "CHGOFF", "CANCLD", "CANCELLED",
    "PREPAID IN FULL", "PAID IN FULL", "PAID IN FULL (LIQ)",
    "CANCELED", "NOT FUNDED", "CHARGED-OFF",
    "LIQUID", "PURCH(NOT C/O)", "CLSLN",                  # troubled
}
INACTIVE_PATTERN = re.compile(
    r"PAID\s*IN\s*FULL|PRE[\s-]*PAID|CANCEL|CANCLD|NOT\s*FUNDED"
    r"|CHARGED?[\s-]*OFF|CHG[\s-]*OFF|^P\.?\s*I\.?\s*F\.?$")
# Kept statuses seen in the asof-260331 files. A status outside this list and
# outside INACTIVE is still kept, but the run reports it so a new SBA status
# word gets a decision.
KNOWN_ACTIVE = {
    "CURR", "CURRENT", "COMMIT", "DELINQ", "PSTDUE",
    "DEFERD", "IN CATCH-UP", "IN DEFERMENT", "EXEMPT",
}
PAST_DUE = re.compile(r"^>?\d+ MONTHS? PAST DUE$")


def _norm_status(status):
    return re.sub(r"\s+", " ", (status or "").strip().upper())


def is_inactive(status):
    """True when a loan status means paid off, prepaid, cancelled, never funded,
    in liquidation, purchased by SBA, CLSLN,
    charged off, or is blank."""
    s = _norm_status(status)
    return not s or s in INACTIVE or bool(INACTIVE_PATTERN.search(s))


def is_known_active(status):
    s = _norm_status(status)
    return s in KNOWN_ACTIVE or bool(PAST_DUE.match(s))


# Every status in the TX rows of the asof-260331 files, plus spelling variants.
SELFTEST_DROP = [
    "P I F", "PIF", "CHGOFF", "CANCLD", "CANCELLED",                  # 7(a)
    "PREPAID IN FULL", "PAID IN FULL", "PAID IN FULL (LIQ)",          # 504
    "CANCELED", "NOT FUNDED", "CHARGED-OFF", "", "   ", None,
    "paid in full", "Prepaid In Full", "PRE-PAID", "CHARGED OFF",     # variants
    "CHARGE-OFF", "CHG OFF", " cancelled ", "P.I.F.", "NOT  FUNDED",
    "LIQUID", "PURCH(NOT C/O)", "CLSLN", "liquid", " purch(not c/o) ",  # troubled
]
SELFTEST_KEEP = [
    "CURR", "COMMIT", "DELINQ", "PSTDUE", "DEFERD",                    # 7(a)
    "CURRENT", "IN CATCH-UP", "IN DEFERMENT", "1 MONTH PAST DUE",      # 504
] + ["%d MONTHS PAST DUE" % n for n in range(2, 10)] + [">9 MONTHS PAST DUE", "EXEMPT"]
RECORD_KEYS = [
    "loan_id", "source", "source_url", "source_doc_id", "borrower", "borrower_address",
    "borrower_city", "borrower_state", "borrower_zip", "lender", "lender_state",
    "lender_city", "lender_fdic_cert", "county", "project_state", "loan_amount",
    "sba_guaranteed_amount", "approval_date", "term_months", "maturity_date",
    "months_to_maturity", "interest_rate", "rate_type", "naics_code",
    "naics_description", "jobs_supported", "business_type", "loan_status",
    "has_collateral", "source_context", "scraped_at",
]
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
    dropped, unknown = Counter(), Counter()
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        for n, row in enumerate(csv.DictReader(f)):
            if n and n % 100000 == 0:
                print("    row %d..." % n)
            if (row.get("projectstate") or "").strip().upper() != "TX":
                continue
            status = (row.get("loanstatus") or "").strip().upper()
            if is_inactive(status):
                dropped[status or "(blank)"] += 1
                continue
            if not is_known_active(status):
                unknown[status] += 1
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
    print("    TX rows dropped by status: %s" % dict(dropped.most_common()))
    if unknown:
        print("    WARNING unrecognised status kept: %s" % dict(unknown.most_common()))
    return out


def selftest():
    """Offline check: every known status is classified as intended, and a small
    CSV run through the real row filter keeps exactly the active rows with the
    unchanged record schema and loan_id scheme."""
    import tempfile
    global HERE
    bad = [s for s in SELFTEST_DROP if not is_inactive(s)]
    bad += [s for s in SELFTEST_KEEP if is_inactive(s)]
    assert not bad, "misclassified statuses: %r" % bad
    stray = [s for s in SELFTEST_KEEP if not is_known_active(s)]
    assert not stray, "kept statuses missing from KNOWN_ACTIVE: %r" % stray
    cols = ["projectstate", "projectcounty", "loanstatus", "approvaldate",
            "terminmonths", "grossapproval", "locationid", "borrname"]
    with tempfile.TemporaryDirectory() as tmp:
        with open(Path(tmp) / "selftest.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for i, s in enumerate(SELFTEST_DROP + SELFTEST_KEEP):
                w.writerow(["TX", "DALLAS", s or "", "01/15/2020", "600", "1000",
                            str(1000 + i), "BORROWER %d" % i])
        saved, HERE = HERE, Path(tmp)
        try:
            kept = process("504", "selftest.csv")
        finally:
            HERE = saved
    got = sorted(r["loan_status"] for r in kept)
    want = sorted(s.strip().upper() for s in SELFTEST_KEEP)
    assert got == want, "row filter kept %r, expected %r" % (got, want)
    assert all(list(r.keys()) == RECORD_KEYS for r in kept), "record schema changed"
    assert all(r["loan_id"] == "sba-504-" + r["source_doc_id"] for r in kept), "loan_id scheme changed"
    print("selftest OK: %d inactive and %d active statuses classified as intended; "
          "row filter kept %d of %d test rows" % (len(SELFTEST_DROP), len(SELFTEST_KEEP),
                                                 len(kept), len(SELFTEST_DROP) + len(SELFTEST_KEEP)))


def main(argv=None):
    global TODAY, NOW_ISO
    ap = argparse.ArgumentParser(description="Statewide Texas SBA 7(a)/504 extract")
    ap.add_argument("--selftest", action="store_true",
                    help="check the status filter offline and exit")
    ap.add_argument("--asof", help="YYYY-MM-DD anchor for the maturity window and "
                                   "months_to_maturity (default: today)")
    ap.add_argument("--stamp", help="ISO timestamp for generated_at and scraped_at "
                                    "(default: now)")
    args = ap.parse_args(argv)
    if args.selftest:
        selftest()
        return
    if args.asof:
        TODAY = dt.date.fromisoformat(args.asof)
    if args.stamp:
        NOW_ISO = dt.datetime.fromisoformat(args.stamp).isoformat()
    print("maturity window from %s, stamp %s" % (TODAY.isoformat(), NOW_ISO))
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
