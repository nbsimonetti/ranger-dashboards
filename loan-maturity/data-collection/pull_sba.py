"""
pull_sba.py — Process SBA 7(a) and 504 FOIA bulk CSVs into per-loan records.

Source URLs (asof-260331 snapshot, fetched 2026-05-21 from data.sba.gov):
  - foia-7a-fy2010-fy2019-asof-260331.csv  (60 MB)
  - foia-7a-fy2020-present-asof-260331.csv (PPP-era; large)
  - foia-504-fy2010-present-asof-260331.csv

Filters:
  - projectstate = 'TX'
  - projectcounty in our 32-county footprint (mirror cre/cre-dashboard-tx.html)
  - loan status active: drops the 7(a) codes P I F, PIF, CHGOFF, CANCLD and
    CANCELLED, the 504 file's PREPAID IN FULL, PAID IN FULL, PAID IN FULL (LIQ),
    CANCELED, NOT FUNDED and CHARGED-OFF, spelling variants of those, and a blank
    status. Everything else stays in, including EXEMPT, past due, deferred,
    LIQUID, PURCH(NOT C/O) and CLSLN (see INACTIVE below).
  - maturity_date >= today, or the --asof date (active maturity window)

Output: tx_sba_loans.json — list of loan records with full provenance.
Then run merge_loans.py to rebuild ../loans.json.

Run:  python pull_sba.py
      python pull_sba.py --selftest           check the status filter offline
      python pull_sba.py --asof YYYY-MM-DD    pin the maturity window and
                                              months_to_maturity to an earlier run
"""
import argparse, csv, json, datetime as dt, os, re, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
TODAY = dt.date.today()

# 32-county TX footprint, matching the CRE dashboard sidebar
COUNTIES = {
    'ANGELINA','BELL','BEXAR','BRAZORIA','BRAZOS','CALDWELL','CAMERON','CHAMBERS',
    'CORYELL','DALLAS','ECTOR','FORT BEND','GALVESTON','GRAYSON','GREGG','HARDIN',
    'JEFFERSON','JOHNSON','KAUFMAN','KERR','LIBERTY','NUECES','PANOLA','RUSK',
    'TARRANT','TAYLOR','TITUS','TRAVIS','VICTORIA','WICHITA','WILLIAMSON','WISE',
    # Also include HARRIS (Houston core) — not in CRE 32-county list but central to footprint
    'HARRIS',
}

# Loan statuses that mean the loan is off the books. The 7(a) files use short
# codes (P I F, CHGOFF, CANCLD); the 504 file spells the same outcomes out
# (PREPAID IN FULL, PAID IN FULL, PAID IN FULL (LIQ), CANCELED, NOT FUNDED,
# CHARGED-OFF). Both vocabularies are listed, a pattern catches spelling
# variants, and a blank status is treated as inactive. Everything else stays in:
# current, committed, past due, deferred, in liquidation (LIQUID), purchased by
# SBA (PURCH(NOT C/O)) and CLSLN. pull_sba.py and pull_sba_statewide.py carry
# the same block; keep them in step.
INACTIVE = {
    "P I F", "PIF", "CHGOFF", "CANCLD", "CANCELLED",
    "PREPAID IN FULL", "PAID IN FULL", "PAID IN FULL (LIQ)",
    "CANCELED", "NOT FUNDED", "CHARGED-OFF",
}
INACTIVE_PATTERN = re.compile(
    r"PAID\s*IN\s*FULL|PRE[\s-]*PAID|CANCEL|CANCLD|NOT\s*FUNDED"
    r"|CHARGED?[\s-]*OFF|CHG[\s-]*OFF|^P\.?\s*I\.?\s*F\.?$")
# Kept statuses seen in the asof-260331 files. A status outside this list and
# outside INACTIVE is still kept, but the run reports it so a new SBA status
# word gets a decision.
KNOWN_ACTIVE = {
    "CURR", "CURRENT", "COMMIT", "PURCH(NOT C/O)", "LIQUID", "DELINQ", "PSTDUE",
    "DEFERD", "CLSLN", "IN CATCH-UP", "IN DEFERMENT", "EXEMPT",
}
PAST_DUE = re.compile(r"^>?\d+ MONTHS? PAST DUE$")


def _norm_status(status):
    return re.sub(r"\s+", " ", (status or "").strip().upper())


def is_inactive(status):
    """True when a loan status means paid off, prepaid, cancelled, never funded,
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
]
SELFTEST_KEEP = [
    "CURR", "COMMIT", "PURCH(NOT C/O)", "LIQUID", "DELINQ", "PSTDUE",  # 7(a)
    "DEFERD", "CLSLN",
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

# Files to process (relative to this script). Add the 504 file when downloaded.
INPUT_FILES = [
    ('7a', 'foia-7a-fy2010-fy2019-asof-260331.csv'),
    ('7a', 'foia-7a-fy2020-present-asof-260331.csv'),
    ('504', 'foia-504-fy2010-present-asof-260331.csv'),
]

def parse_date(s):
    if not s: return None
    s = s.strip()
    for fmt in ('%m/%d/%Y','%Y-%m-%d','%m/%d/%y'):
        try: return dt.datetime.strptime(s, fmt).date()
        except: continue
    return None

def add_months(d, months):
    if not d or not months: return None
    try:
        months = int(months)
    except: return None
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    day = min(d.day, [31,29 if year%4==0 and (year%100!=0 or year%400==0) else 28,
                       31,30,31,30,31,31,30,31,30,31][month-1])
    return dt.date(year, month, day)

def normalize_county(c):
    if not c: return ''
    return re.sub(r'\s+',' ', c.upper().replace('COUNTY','').replace('CO.','').strip())

def loan_id(program, locationid, borrname, approval):
    """Stable ID for a loan record across re-pulls."""
    base = f'sba-{program}-{locationid}'
    if not locationid:
        base = f'sba-{program}-{borrname.strip()[:30]}-{approval}'
    return base.lower().replace(' ','_').replace('/','_')

def process_file(program, filename):
    path = HERE / filename
    if not path.exists():
        print(f'  SKIP (not yet downloaded): {filename}', flush=True)
        return []
    print(f'  Processing: {filename}', flush=True)
    out = []
    tx_total = 0
    footprint_total = 0
    active_total = 0
    future_maturity = 0
    dropped, unknown = Counter(), Counter()
    with open(path, 'r', encoding='utf-8', errors='replace', newline='') as f:
        reader = csv.DictReader(f)
        for n, row in enumerate(reader):
            if n % 50000 == 0 and n: print(f'    row {n:,}…', flush=True)
            state = (row.get('projectstate') or '').strip().upper()
            if state != 'TX': continue
            tx_total += 1
            county = normalize_county(row.get('projectcounty'))
            if county not in COUNTIES: continue
            footprint_total += 1
            status = (row.get('loanstatus') or '').strip().upper()
            if is_inactive(status):
                dropped[status or '(blank)'] += 1
                continue
            if not is_known_active(status):
                unknown[status] += 1
            active_total += 1
            approval = parse_date(row.get('approvaldate'))
            term = row.get('terminmonths')
            maturity = add_months(approval, term)
            if not maturity: continue
            if maturity < TODAY: continue
            future_maturity += 1
            gross = float(row.get('grossapproval') or 0) or 0
            lender_raw = (row.get('bankname') or '').strip()
            lender_state = (row.get('bankstate') or '').strip().upper()
            # SBA 504 loans are originated by Certified Development Companies (CDCs)
            # with a partner bank funding 50%. The bulk CSV redacts the partner bank
            # name. Label these clearly so users know it's not a Ranger competitor we
            # can identify by name.
            if program == '504' and not lender_raw:
                lender_raw = '(SBA 504 — partner bank not disclosed)'
                lender_state = ''
            rec = {
                'loan_id': loan_id(program, row.get('locationid',''), row.get('borrname',''), row.get('approvaldate','')),
                'source': f'sba-{program}',
                'source_url': 'https://data.sba.gov/dataset/7-a-504-foia',
                'source_doc_id': row.get('locationid') or None,
                'borrower': (row.get('borrname') or '').strip(),
                'borrower_address': ((row.get('borrstreet') or '') + ', ' + (row.get('borrcity') or '') + ', ' + (row.get('borrstate') or '') + ' ' + (row.get('borrzip') or '')).strip(', '),
                'borrower_city': (row.get('borrcity') or '').strip().title(),
                'borrower_state': (row.get('borrstate') or '').strip().upper(),
                'borrower_zip': (row.get('borrzip') or '').strip(),
                'lender': lender_raw,
                'lender_state': lender_state,
                'lender_city': (row.get('bankcity') or '').strip().title(),
                'lender_fdic_cert': (row.get('bankfdicnumber') or '').strip(),
                'county': county.title(),
                'project_state': 'TX',
                'loan_amount': gross,
                'sba_guaranteed_amount': float(row.get('sbaguaranteedapproval') or 0) or 0,
                'approval_date': approval.isoformat() if approval else None,
                'term_months': int(term) if term and term.isdigit() else None,
                'maturity_date': maturity.isoformat(),
                'months_to_maturity': (maturity.year - TODAY.year) * 12 + (maturity.month - TODAY.month),
                'interest_rate': float(row.get('initialinterestrate') or 0) or None,
                'rate_type': (row.get('fixedorvariableinterestind') or '').strip(),
                'naics_code': (row.get('naicscode') or '').strip(),
                'naics_description': (row.get('naicsdescription') or '').strip(),
                'jobs_supported': int(row.get('jobssupported') or 0) or None,
                'business_type': (row.get('businesstype') or '').strip(),
                'loan_status': status,
                'has_collateral': (row.get('collateralind') or '').strip().upper() == 'Y',
                'source_context': f"SBA {program} approval {row.get('approvaldate','')} · term {term}mo · status {status}",
                'scraped_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            }
            out.append(rec)
    print(f'    TX total:           {tx_total:,}')
    print(f'    In 32-county fp:    {footprint_total:,}')
    print(f'    Active status:      {active_total:,}')
    print(f'    Future maturity:    {future_maturity:,}')
    print(f'    Output rows:        {len(out):,}')
    print(f'    Dropped by status:  {dict(dropped.most_common())}')
    if unknown:
        print(f'    WARNING unrecognised status kept: {dict(unknown.most_common())}')
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
            kept = process_file("504", "selftest.csv")
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
    global TODAY
    ap = argparse.ArgumentParser(description='Footprint SBA 7(a)/504 extract')
    ap.add_argument('--selftest', action='store_true',
                    help='check the status filter offline and exit')
    ap.add_argument('--asof', help='YYYY-MM-DD anchor for the maturity window and '
                                   'months_to_maturity (default: today)')
    args = ap.parse_args(argv)
    if args.selftest:
        selftest()
        return
    if args.asof:
        TODAY = dt.date.fromisoformat(args.asof)
    print(f'maturity window from {TODAY.isoformat()}')
    all_loans = []
    for program, fn in INPUT_FILES:
        all_loans.extend(process_file(program, fn))
    print(f'\nTotal output loans across all SBA files: {len(all_loans):,}')
    if not all_loans:
        print('No loans produced — input files may not be downloaded yet.')
        return
    # Sort by maturity ascending (soonest first)
    all_loans.sort(key=lambda r: r['maturity_date'])
    out_path = HERE / 'tx_sba_loans.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(all_loans, f, default=str)
    print(f'Wrote {out_path}  ({out_path.stat().st_size/1024:.1f} KB)')

if __name__ == '__main__':
    main()
