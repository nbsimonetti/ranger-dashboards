"""
verify_pipeline.py — Post-pull sanity check for the loan-maturity dashboard.

Reads ../loans.json and reports:
  - Total loans + total $ tracked
  - Coverage by source (counts + dollars)
  - Coverage by county (top 10 + tail)
  - Maturity distribution (months bucket)
  - Provenance completeness rate (rows missing source_url, etc.)
"""
import json, collections, datetime as dt
from pathlib import Path

HERE = Path(__file__).parent
BLOB = HERE.parent / 'loans.json'

def main():
    data = json.load(open(BLOB, encoding='utf-8'))
    loans = data.get('loans', [])
    meta  = data.get('meta', {})
    today = dt.date.today()
    print(f'=== Loan Maturity Pipeline — Verification ===')
    print(f'Pipeline generated: {meta.get("generated_at","—")}')
    print(f'SBA snapshot tag:   asof-{meta.get("sba_asof_tag","—")}')
    print(f'Total loans:        {len(loans):,}')
    print(f'Total $ tracked:    ${meta.get("total_dollars",0)/1e6:,.1f}M')
    print()
    # Source
    by_src = collections.Counter(r.get('source','unknown') for r in loans)
    print('Loans by source:')
    for s,n in by_src.most_common(): print(f'  {s}: {n:,}')
    print()
    # County (top 10)
    by_co = collections.Counter(r.get('county','—') for r in loans)
    print('Top 10 counties by loan count:')
    for c,n in by_co.most_common(10): print(f'  {c}: {n:,}')
    print()
    # Maturity buckets
    buckets = collections.Counter()
    bucket_dollars = collections.defaultdict(float)
    for r in loans:
        m = r.get('months_to_maturity')
        if m is None: b = '—'
        elif m <= 6: b = '0-6'
        elif m <= 12: b = '7-12'
        elif m <= 24: b = '13-24'
        elif m <= 60: b = '25-60'
        else: b = '60+'
        buckets[b] += 1
        bucket_dollars[b] += r.get('loan_amount',0) or 0
    print('Months-to-maturity distribution:')
    for b in ['0-6','7-12','13-24','25-60','60+','—']:
        if b in buckets: print(f'  {b:>5} mo: {buckets[b]:>6,}   ${bucket_dollars[b]/1e6:>8,.1f}M')
    print()
    # Provenance completeness
    have_url   = sum(1 for r in loans if r.get('source_url'))
    have_ctx   = sum(1 for r in loans if r.get('source_context'))
    have_doc   = sum(1 for r in loans if r.get('source_doc_id'))
    have_naics = sum(1 for r in loans if r.get('naics_code'))
    have_rate  = sum(1 for r in loans if r.get('interest_rate') not in (None, 0))
    n = max(1, len(loans))
    print(f'Provenance completeness:')
    print(f'  source_url:      {have_url:,} ({100*have_url/n:.1f}%)')
    print(f'  source_context:  {have_ctx:,} ({100*have_ctx/n:.1f}%)')
    print(f'  source_doc_id:   {have_doc:,} ({100*have_doc/n:.1f}%)')
    print(f'  naics_code:      {have_naics:,} ({100*have_naics/n:.1f}%)')
    print(f'  interest_rate:   {have_rate:,} ({100*have_rate/n:.1f}%)')
    print()
    # Top lenders
    by_lender = collections.Counter()
    by_lender_dollars = collections.defaultdict(float)
    for r in loans:
        l = (r.get('lender') or '—').strip()
        by_lender[l] += 1
        by_lender_dollars[l] += r.get('loan_amount',0) or 0
    print('Top 10 lenders by $ exposure:')
    for l,_ in by_lender.most_common(50):
        pass
    # Re-sort by dollars
    sorted_l = sorted(by_lender.items(), key=lambda kv: -by_lender_dollars[kv[0]])[:10]
    for l,n in sorted_l: print(f'  {l[:50]:<50} ${by_lender_dollars[l]/1e6:>8,.1f}M ({n:,} loans)')

if __name__ == '__main__':
    main()
