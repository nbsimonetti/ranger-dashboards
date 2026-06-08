"""
geocode_physicians.py — Geocode TX physician practice addresses.

Reads:  dashboards/physician/TX_Physician_Dashboard.html (RAW_DATA inline blob)
Writes: dashboards/physician/physicians-geocoded.json

~24,800 physicians. 3 Census batches; ~6 min total. Resumable.
"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from census_geocoder import geocode_batches, summary

HERE     = Path(__file__).parent
HTML_FP  = HERE.parent / 'physician' / 'TX_Physician_Dashboard.html'
OUT_FP   = HERE.parent / 'physician' / 'physicians-geocoded.json'

def extract_raw_data():
    """Pull the `RAW_DATA = [...]` inline array out of the physician dashboard HTML."""
    html = HTML_FP.read_text(encoding='utf-8')
    m = re.search(r'(?:var|const|let)\s+RAW_DATA\s*=\s*(\[.*?\])\s*;', html, re.DOTALL)
    if not m:
        raise SystemExit(f'ERROR: RAW_DATA array not found in {HTML_FP}')
    return json.loads(m.group(1))

def main():
    data = extract_raw_data()
    print(f'Loaded {len(data):,} physicians')
    records = []
    for r in data:
        addr = (r.get('address') or '').strip()
        if not addr: continue
        records.append({
            'npi':    r.get('npi'),
            'street': addr,
            'city':   r.get('city') or '',
            'state':  r.get('state') or 'TX',
            'zip':    str(r.get('zip') or '').strip(),
        })
    print(f'Records with usable street address: {len(records):,}')
    cache = geocode_batches(records, OUT_FP, id_key='npi', label='physicians', throttle_s=2.0)
    print()
    summary(cache)

if __name__ == '__main__':
    main()
