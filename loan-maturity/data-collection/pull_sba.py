"""
pull_sba.py — Process SBA 7(a) and 504 FOIA bulk CSVs into per-loan records.

Source URLs (asof-260331 snapshot, fetched 2026-05-21 from data.sba.gov):
  - foia-7a-fy2010-fy2019-asof-260331.csv  (60 MB)
  - foia-7a-fy2020-present-asof-260331.csv (PPP-era; large)
  - foia-504-fy2010-present-asof-260331.csv

Filters:
  - projectstate = 'TX'
  - projectcounty in our 32-county footprint (mirror cre/cre-dashboard-tx.html)
  - loanstatus NOT in ('PIF','CHGOFF','CANCLD','EXEMPT')
  - maturity_date >= today (active maturity window)

Output: tx_sba_loans.json — list of loan records with full provenance.
"""
import csv, json, datetime as dt, os, re, sys
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

# Loan statuses that mean "this loan is still on the books"
ACTIVE_STATUSES = {'EXEMPT', 'NOT FUNDED', 'CMPL', 'COMMITMENT'}  # data-driven adjustment below
INACTIVE_STATUSES = {'P I F', 'PIF', 'CHGOFF', 'CANCLD', 'CANCELLED'}

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
            if status in INACTIVE_STATUSES: continue
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
    print(f'    Active (not PIF/CO):{active_total:,}')
    print(f'    Future maturity:    {future_maturity:,}')
    print(f'    Output rows:        {len(out):,}')
    return out

def main():
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
