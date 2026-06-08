"""
geocode_parcels.py — Geocode CRE parcels for the CRE Prospecting dashboard.

Reads:  dashboards/cre/cre-properties-tx.json (47 MB; regenerable from inline blob
        via dashboards/loan-maturity/data-collection/extract_cre_properties.py)
Writes: dashboards/cre/cre-coords-tx.json

162K parcels. Census batches at 10K each = ~17 batches. Allow ~45 min.
Resumable; safe to interrupt + resume.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from census_geocoder import geocode_batches, summary

HERE      = Path(__file__).parent
PROPS_FP  = HERE.parent / 'cre' / 'cre-properties-tx.json'
OUT_FP    = HERE.parent / 'cre' / 'cre-coords-tx.json'

def main():
    if not PROPS_FP.exists():
        print(f'ERROR: {PROPS_FP} not found. Run extract_cre_properties.py first.')
        sys.exit(1)
    props = json.load(open(PROPS_FP, encoding='utf-8'))
    print(f'Loaded {len(props):,} parcels')
    records = []
    for p in props:
        if not p.get('addr'): continue
        records.append({
            'id':     p.get('id'),
            'street': p.get('addr') or '',
            'city':   p.get('city') or '',
            'state':  'TX',
            'zip':    p.get('zip') or '',
            'county': p.get('county') or '',
        })
    print(f'Records with usable street address: {len(records):,}')
    cache = geocode_batches(records, OUT_FP, id_key='id', label='parcels', throttle_s=3.0)
    print()
    summary(cache, county_field='county', records=records, id_key='id')

if __name__ == '__main__':
    main()
