"""
join_to_cre.py — Cross-reference SBA loan borrowers (Loan Maturity dashboard)
with CRE property owners (CRE Prospecting dashboard).

Inputs:
  - dashboards/loan-maturity/loans.json
  - dashboards/cre/cre-properties-tx.json (extracted from cre-dashboard-tx.html)

Output:
  - dashboards/loan-maturity/loan_property_join.json
      {
        "meta": { generated_at, totals, ... },
        "forward":  { loan_id: [{parcel_id, confidence, match_method}, ...] },
        "reverse":  { parcel_id: [{loan_id, confidence, match_method}, ...] },
        "entity_to_loans":    { entity_key: [loan_id, ...] },
        "entity_to_parcels":  { entity_key: [parcel_id, ...] }
      }

Join strategy:
  1. Normalize entity names (strip LLC/INC/LTD/etc, drop punctuation,
     uppercase, collapse whitespace).
  2. Bucket properties by (county, first_token_of_normalized_owner, length_bucket).
  3. For each loan, look up matching bucket in same county; fuzzy-compare with
     token-set ratio. If borrower address parses, also compare ZIP + street
     number for address-confidence boost.
  4. Score each candidate 0-100 across 5 components (see CONFIDENCE_SCORING below).
  5. Keep matches with confidence >= 50; mark default-visible at >= 75.

This is a one-shot offline pipeline. Re-run after SBA pulls or CRE refreshes.
"""
import json, re, datetime as dt
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
LOANS_FP    = HERE.parent / 'loans.json'
PROPS_FP    = HERE.parent.parent / 'cre' / 'cre-properties-tx.json'
OUT_FP      = HERE.parent / 'loan_property_join.json'

# Confidence thresholds
MIN_CONFIDENCE = 50      # below this, drop the match
DEFAULT_VISIBLE = 75     # at-or-above, show by default in the dashboard

# Entity-suffix tokens to strip during normalization
ENTITY_SUFFIXES = {
    'LLC', 'L.L.C', 'LLC.', 'L.L.C.',
    'INC', 'INC.', 'INCORPORATED',
    'CORP', 'CORP.', 'CORPORATION',
    'LP', 'L.P.', 'L.P', 'LP.',
    'LLP', 'L.L.P.',
    'CO', 'CO.', 'COMPANY',
    'LTD', 'LTD.', 'LIMITED',
    'PA', 'P.A.',  'PC', 'P.C.',  'PLLC', 'P.L.L.C.',
    'TRUST', 'TR',
    'PARTNERS', 'PARTNERSHIP',
    'HOLDINGS', 'HOLDING',
    'GROUP', 'GRP',
    'ENTERPRISES', 'ENT', 'ENTERPRISE',
    'PROPERTIES', 'PROPERTY', 'PROPS',
    'INVESTMENTS', 'INVESTMENT', 'INV',
    'REALTY', 'REAL', 'ESTATE',
    'MANAGEMENT', 'MGMT', 'MGT',
    'LLC.', 'INC',
}

# Words that don't help differentiate two entities
STOPWORDS = {'THE', 'OF', 'AND', '&', 'A', 'AN', 'TX', 'TEXAS', 'AT', 'BY', 'IN', 'ON'}

# Street-suffix normalization
STREET_SUFFIX_NORMALIZE = {
    'STREET':'ST','AVENUE':'AVE','AV':'AVE','BOULEVARD':'BLVD',
    'DRIVE':'DR','ROAD':'RD','LANE':'LN','HIGHWAY':'HWY','HWY':'HWY',
    'COURT':'CT','CIRCLE':'CIR','PLACE':'PL','PARKWAY':'PKWY',
    'TRAIL':'TRL','TERRACE':'TER','SQUARE':'SQ',
}

def normalize_entity(name):
    """Return (canonical_form, token_set)"""
    if not name: return '', set()
    s = name.upper().strip()
    s = re.sub(r'[",.]', ' ', s)        # punctuation → space
    s = re.sub(r'[^A-Z0-9& ]', ' ', s)  # keep alphanumeric, & and space
    s = re.sub(r'\s+', ' ', s).strip()
    toks = s.split(' ')
    # Strip entity suffix tokens
    toks = [t for t in toks if t not in ENTITY_SUFFIXES]
    # Drop stopwords if there are still meaningful tokens left
    nonstop = [t for t in toks if t not in STOPWORDS]
    if nonstop: toks = nonstop
    canonical = ' '.join(toks)
    token_set = set(toks)
    return canonical, token_set

def normalize_address(addr):
    if not addr: return '', None
    s = addr.upper().strip()
    s = re.sub(r'[,.]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    toks = s.split(' ')
    # Pull out leading street number
    num = None
    if toks and toks[0].isdigit():
        num = toks[0]
        toks = toks[1:]
    # Normalize the street suffix
    if toks and toks[-1] in STREET_SUFFIX_NORMALIZE:
        toks[-1] = STREET_SUFFIX_NORMALIZE[toks[-1]]
    return ' '.join(toks), num

def token_set_ratio(a, b):
    """Jaccard-style overlap between two token sets, 0-1."""
    if not a or not b: return 0.0
    inter = a & b
    union = a | b
    if not union: return 0.0
    return len(inter) / len(union)

def confidence(loan_canon, loan_toks, prop_canon, prop_toks,
               loan_zip, prop_zip, loan_street_num, prop_street_num,
               loan_state, prop_state, loan_suffix_set, prop_suffix_set):
    """Score 0-100 across 5 components."""
    score = 0
    # Name token-set ratio: 0-50 pts (this is the workhorse)
    name_ratio = token_set_ratio(loan_toks, prop_toks)
    score += int(name_ratio * 50)
    # Bonus: exact canonical match
    if loan_canon and loan_canon == prop_canon:
        score += 10
    # ZIP match: +20
    if loan_zip and prop_zip and loan_zip == prop_zip:
        score += 20
    # Street number match: +15
    if loan_street_num and prop_street_num and loan_street_num == prop_street_num:
        score += 15
    # own_state match (proxy for borrower_state == owner-state-of-record)
    if loan_state and prop_state and loan_state == prop_state:
        score += 10
    # Shared entity-suffix flavor (LLC vs LLC, TRUST vs TRUST)
    if loan_suffix_set and prop_suffix_set and (loan_suffix_set & prop_suffix_set):
        score += 5
    return min(100, score)

def length_bucket(s):
    n = len(s.split())
    if n <= 1: return 1
    if n == 2: return 2
    if n == 3: return 3
    if n == 4: return 4
    return 5

def first_token(s):
    return s.split(' ')[0] if s else ''

def main():
    print('=== Loan <-> CRE Property join pipeline ===')
    loans_blob = json.load(open(LOANS_FP, encoding='utf-8'))
    loans = loans_blob.get('loans', [])
    props = json.load(open(PROPS_FP, encoding='utf-8'))
    print(f'Loaded {len(loans):,} loans and {len(props):,} properties')

    # Normalize all properties + bucket
    print('Normalizing + bucketing properties…')
    prop_index = defaultdict(list)   # (county, first_tok, len_bucket) -> [(canonical, token_set, prop_record, zip, street_num, own_state, suffix_set)]
    prop_by_id = {}
    for p in props:
        canonical, toks = normalize_entity(p.get('owner',''))
        if not canonical: continue
        county = (p.get('county') or '').strip()
        # property address parts
        addr_canon, addr_num = normalize_address(p.get('addr',''))
        prop_zip = (p.get('zip') or '').strip() or None
        own_state = (p.get('own_state') or '').strip().upper() or None
        # Capture the entity suffix words present in the ORIGINAL name (LLC, TRUST, etc.)
        orig = (p.get('owner') or '').upper()
        suffix_set = {sfx for sfx in ENTITY_SUFFIXES if re.search(r'\b'+re.escape(sfx)+r'\b', orig)}
        key1 = (county, first_token(canonical), length_bucket(canonical))
        prop_index[key1].append({
            'parcel_id': p.get('id'),
            'canon': canonical,
            'toks': toks,
            'zip': prop_zip,
            'street_num': addr_num,
            'state': own_state,
            'suffix_set': suffix_set,
            'addr_canon': addr_canon,
            'val': p.get('val'),
            'owner_raw': p.get('owner'),
            'addr_raw': p.get('addr'),
        })
        prop_by_id[p.get('id')] = p

    print(f'Built {len(prop_index):,} property buckets')

    # Match loans
    forward = defaultdict(list)
    reverse = defaultdict(list)
    matched_loans = 0
    matched_pairs = 0
    bucket_misses = 0
    print('Matching loans against property buckets…')
    for i, loan in enumerate(loans):
        if i % 2000 == 0 and i: print(f'  loan {i:,}/{len(loans):,}  ({matched_loans:,} matched so far)')
        canonical, toks = normalize_entity(loan.get('borrower',''))
        if not canonical: continue
        county = (loan.get('county') or '').strip()
        # borrower address
        addr_canon, addr_num = normalize_address(loan.get('borrower_address','') or loan.get('borrower_city',''))
        loan_zip = (loan.get('borrower_zip') or '').strip() or None
        loan_state = (loan.get('borrower_state') or '').strip().upper() or None
        orig = (loan.get('borrower') or '').upper()
        suffix_set = {sfx for sfx in ENTITY_SUFFIXES if re.search(r'\b'+re.escape(sfx)+r'\b', orig)}

        # Try the exact bucket + adjacent length buckets (±1)
        lb = length_bucket(canonical)
        ft = first_token(canonical)
        candidates = []
        for delta in (0, 1, -1):
            for key in [(county, ft, lb+delta)]:
                candidates.extend(prop_index.get(key, []))
        # If a borrower has a very short first token (e.g., "THE"), the bucketing
        # collapses. We don't have a great fallback here without a quadratic
        # search; skip these — they were stripped by stop-word removal anyway.
        if not candidates:
            bucket_misses += 1
            continue

        # Score each candidate
        scored = []
        for c in candidates:
            sc = confidence(canonical, toks, c['canon'], c['toks'],
                            loan_zip, c['zip'], addr_num, c['street_num'],
                            loan_state, c['state'], suffix_set, c['suffix_set'])
            if sc < MIN_CONFIDENCE: continue
            # match_method
            method = 'fuzzy_name'
            if canonical == c['canon']: method = 'exact_name'
            if loan_zip and c['zip'] == loan_zip and addr_num and c['street_num'] == addr_num: method = 'address_match'
            scored.append((sc, c, method))
        if not scored: continue
        # Cap at top 5 matches per loan (avoid blowing up join file with weak duplicates)
        scored.sort(key=lambda t: -t[0])
        for sc, c, method in scored[:5]:
            # Embed minimal parcel info so the Loan Maturity dashboard doesn't have
            # to load the 47MB CRE properties JSON just to display a popover.
            forward[loan['loan_id']].append({
                'parcel_id': c['parcel_id'],
                'confidence': sc,
                'match_method': method,
                'visible_default': sc >= DEFAULT_VISIBLE,
                'owner': c['owner_raw'],
                'addr': c['addr_raw'],
                'val': c.get('val'),
            })
            reverse[c['parcel_id']].append({
                'loan_id': loan['loan_id'],
                'confidence': sc,
                'match_method': method,
                'visible_default': sc >= DEFAULT_VISIBLE,
                'borrower': loan.get('borrower'),
                'lender': loan.get('lender'),
                'loan_amount': loan.get('loan_amount'),
                'maturity_date': loan.get('maturity_date'),
                'months_to_maturity': loan.get('months_to_maturity'),
            })
            matched_pairs += 1
        matched_loans += 1

    # Entity-level aggregations: borrower → loans, owner → parcels (built once for cross-dashboard linking)
    entity_to_loans = defaultdict(list)
    entity_to_parcels = defaultdict(list)
    for loan in loans:
        canonical, _ = normalize_entity(loan.get('borrower',''))
        if canonical: entity_to_loans[canonical].append(loan['loan_id'])
    for p in props:
        canonical, _ = normalize_entity(p.get('owner',''))
        if canonical: entity_to_parcels[canonical].append(p.get('id'))

    blob = {
        'meta': {
            'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'min_confidence': MIN_CONFIDENCE,
            'default_visible_confidence': DEFAULT_VISIBLE,
            'total_loans': len(loans),
            'total_properties': len(props),
            'loans_with_match': matched_loans,
            'total_match_pairs': matched_pairs,
            'bucket_misses': bucket_misses,
            'unique_entities_in_loans': len(entity_to_loans),
            'unique_entities_in_props': len(entity_to_parcels),
        },
        'forward': dict(forward),
        'reverse': dict(reverse),
        'entity_to_loans':   dict(entity_to_loans),
        'entity_to_parcels': dict(entity_to_parcels),
    }
    with open(OUT_FP, 'w', encoding='utf-8') as f:
        json.dump(blob, f)
    print()
    print(f'=== Results ===')
    print(f'  Loans matched:           {matched_loans:,} / {len(loans):,}  ({100*matched_loans/max(1,len(loans)):.1f}%)')
    print(f'  Total match pairs:       {matched_pairs:,}')
    print(f'  Bucket misses (no cands):{bucket_misses:,}')
    print(f'  Unique loan entities:    {len(entity_to_loans):,}')
    print(f'  Unique prop owners:      {len(entity_to_parcels):,}')
    print(f'  Output:                  {OUT_FP}')
    print(f'  Size:                    {OUT_FP.stat().st_size/1024/1024:.1f} MB')

if __name__ == '__main__':
    main()
