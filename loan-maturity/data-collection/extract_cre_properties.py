"""
extract_cre_properties.py — Pull the inline `var ALL=[...]` blob out of
cre-dashboard-tx.html and write it to ../../cre/cre-properties-tx.json
so the join pipeline can read CRE data as a sibling file.

This is a build artifact regeneration step. Re-run any time the CRE
dashboard's inline data is refreshed.
"""
import re, json, os
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE.parent.parent / 'cre' / 'cre-dashboard-tx.html'
OUT = HERE.parent.parent / 'cre' / 'cre-properties-tx.json'

def main():
    html = open(SRC, encoding='utf-8').read()
    m = re.search(r'var ALL=(\[.*?\]);', html, re.DOTALL)
    if not m:
        raise SystemExit(f'ERROR: could not find var ALL=[...] in {SRC}')
    data = json.loads(m.group(1))
    print(f'Parsed {len(data):,} CRE properties from {SRC.name}')
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    print(f'Wrote {OUT}  ({os.path.getsize(OUT)/1024/1024:.1f} MB)')

if __name__ == '__main__':
    main()
