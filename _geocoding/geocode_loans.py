"""
geocode_loans.py — Geocode SBA loan borrower addresses for the Loan Maturity dashboard.

Reads:  dashboards/loan-maturity/loans.json
Writes: dashboards/loan-maturity/loans-geocoded.json
        (dict keyed by loan_id → {matched, lat, lng, matched_address, match_type})

Resumable. Re-run after each SBA pipeline refresh.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from census_geocoder import geocode_batches, summary

HERE     = Path(__file__).parent
LOANS_FP = HERE.parent / 'loan-maturity' / 'loans.json'
OUT_FP   = HERE.parent / 'loan-maturity' / 'loans-geocoded.json'

def main():
    blob = json.load(open(LOANS_FP, encoding='utf-8'))
    loans = blob.get('loans', [])
    print(f'Loaded {len(loans):,} loans')
    # Build geocoder input — pull street out of `borrower_address` (already-concatenated)
    # or fall back to splitting components when present
    records = []
    for L in loans:
        # SBA bulk format: borrower_address = "<street>, <city>, <state> <zip>"
        # Use the raw field names captured by pull_sba.py instead of re-parsing
        addr = (L.get('borrower_address') or '').strip()
        # Robust split — first comma chunk is street; rest is city/state/zip
        parts = addr.split(',')
        if len(parts) >= 2:
            street = parts[0].strip()
        else:
            street = addr
        records.append({
            'loan_id': L.get('loan_id'),
            'street':  street,
            'city':    L.get('borrower_city') or '',
            'state':   L.get('borrower_state') or 'TX',
            'zip':     L.get('borrower_zip') or '',
            'county':  L.get('county') or '',
        })
    cache = geocode_batches(records, OUT_FP, id_key='loan_id', label='loans')
    print()
    summary(cache, county_field='county', records=records, id_key='loan_id')

if __name__ == '__main__':
    main()
