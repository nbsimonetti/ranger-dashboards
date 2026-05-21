"""
merge_loans.py — Combine all source loan JSONs into one keyed blob with metadata.

Currently active sources:
  - tx_sba_loans.json  (from pull_sba.py)

Reserved keys for future sources (documented as blocked on the dashboard):
  - tx_cmbs_loans.json   (SEC EDGAR 10-D parsing — iteration 2)
  - tx_hmda_loans.json   (CFPB HMDA business-purpose subset)
  - tx_deeds.json        (county clerk deed-of-trust scrapes — blocked by paywalls)
  - tx_ucc.json          (state UCC bulk — blocked by paywalls)

Output: ../loans.json
"""
import json, datetime as dt
from pathlib import Path

HERE = Path(__file__).parent
OUT  = HERE.parent / 'loans.json'

SOURCES = [
    'tx_sba_loans.json',
    'tx_cmbs_loans.json',
    'tx_hmda_loans.json',
    'tx_deeds.json',
    'tx_ucc.json',
]

def main():
    all_loans = []
    sources_seen = {}
    for fn in SOURCES:
        fp = HERE / fn
        if not fp.exists():
            print(f'  SKIP (not present): {fn}')
            continue
        try:
            arr = json.load(open(fp, encoding='utf-8'))
        except Exception as e:
            print(f'  ERR reading {fn}: {e}')
            continue
        if not isinstance(arr, list):
            print(f'  ERR {fn}: expected list, got {type(arr).__name__}')
            continue
        print(f'  Loaded {len(arr):,} from {fn}')
        all_loans.extend(arr)
        # Source tally for the freshness ribbon + methodology
        for r in arr:
            src = r.get('source','unknown')
            sources_seen[src] = sources_seen.get(src, 0) + 1
    # Sort by maturity ascending
    all_loans.sort(key=lambda r: r.get('maturity_date',''))
    blob = {
        'meta': {
            'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'sba_asof': '2026-03-31',
            'sba_asof_tag': '260331',
            'total_loans': len(all_loans),
            'total_dollars': sum(r.get('loan_amount',0) or 0 for r in all_loans),
            'sources_seen': sources_seen,
            'footprint_counties': 32,
        },
        'loans': all_loans,
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(blob, f, default=str)
    print(f'\nWrote {OUT}')
    print(f'  Total loans:   {len(all_loans):,}')
    print(f'  Total dollars: ${blob["meta"]["total_dollars"]/1e6:.1f}M')
    print(f'  Sources:       {sources_seen}')
    print(f'  File size:     {OUT.stat().st_size/1024:.1f} KB')

if __name__ == '__main__':
    main()
