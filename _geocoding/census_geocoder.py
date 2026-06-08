"""
census_geocoder.py — Shared US Census Geocoder bulk-batch utility.

Endpoint: https://geocoding.geo.census.gov/geocoder/locations/addressbatch
Input: CSV with header `id,street,city,state,zip` (max 10K rows per request).
Output: CSV with columns appended: matched, match_type, matched_address,
        lon_lat, tigerline_id, side. Lon/lat is comma-separated.

This module does NOT depend on the requests library — uses urllib for
zero-dependency portability across the Ranger dashboards repo.

Usage from another script:
    from census_geocoder import geocode_batches
    geocode_batches(records, out_path, id_key='loan_id')

Where `records` is a list of dicts each containing at minimum:
    {id_key: str, 'street': str, 'city': str, 'state': str, 'zip': str}
"""
import csv, io, json, time, urllib.request, urllib.parse, urllib.error
from pathlib import Path

ENDPOINT = 'https://geocoding.geo.census.gov/geocoder/locations/addressbatch'
BENCHMARK = 'Public_AR_Current'
BATCH_SIZE = 10000           # Census hard limit
TIMEOUT = 600                # 10 min per batch — they can be slow
UA = 'Mozilla/5.0 (Ranger Dashboards Geocoder; +https://github.com/nbsimonetti/ranger-dashboards)'


def _build_csv(records, id_key):
    """Build the CSV body Census expects: header-less, 5 columns (id, street, city, state, zip)."""
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    for r in records:
        rid = str(r.get(id_key, '') or '')
        st  = (r.get('street') or '').strip()
        ci  = (r.get('city') or '').strip()
        sta = (r.get('state') or '').strip()
        zp  = (r.get('zip') or '').strip()
        # Census requires non-empty street; skip records that would 400
        if not st: continue
        w.writerow([rid, st, ci, sta, zp])
    return buf.getvalue()


def _post_batch(csv_body, retries=3):
    """POST a batch CSV to Census; return the response CSV text."""
    # Census uses multipart/form-data with two fields: addressFile + benchmark.
    # Build the multipart body manually to avoid the `requests` dep.
    boundary = '----RangerGeocoderBoundary' + str(int(time.time()*1000))
    parts = []
    parts.append(f'--{boundary}'.encode('utf-8'))
    parts.append(b'Content-Disposition: form-data; name="addressFile"; filename="addresses.csv"')
    parts.append(b'Content-Type: text/csv\r\n')
    parts.append(csv_body.encode('utf-8'))
    parts.append(f'--{boundary}'.encode('utf-8'))
    parts.append(b'Content-Disposition: form-data; name="benchmark"\r\n')
    parts.append(BENCHMARK.encode('utf-8'))
    parts.append(f'--{boundary}--'.encode('utf-8'))
    body = b'\r\n'.join(parts)

    headers = {
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Content-Length': str(len(body)),
        'User-Agent': UA,
        'Accept': 'text/csv',
    }
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(ENDPOINT, data=body, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read().decode('utf-8', errors='replace')
        except urllib.error.HTTPError as e:
            last_err = f'HTTP {e.code}: {e.reason}'
        except Exception as e:
            last_err = str(e)
        backoff = 5 + 10*attempt
        print(f'    batch failed ({last_err}); retry in {backoff}s', flush=True)
        time.sleep(backoff)
    raise RuntimeError(f'Census batch failed after {retries} retries: {last_err}')


def _parse_response(csv_text):
    """Parse Census's response CSV into a dict keyed by original id."""
    out = {}
    rdr = csv.reader(io.StringIO(csv_text))
    for row in rdr:
        if len(row) < 5: continue
        rid = row[0]
        # Census layout: id, input_addr, match_status, match_type, matched_addr, lon_lat, tigerline, side
        match_status = row[2] if len(row) > 2 else ''
        matched_addr = row[4] if len(row) > 4 else ''
        lon_lat      = row[5] if len(row) > 5 else ''
        match_type   = row[3] if len(row) > 3 else ''
        if match_status != 'Match':
            out[rid] = {'matched': False, 'reason': match_status, 'match_type': match_type}
            continue
        lat = lon = None
        if lon_lat and ',' in lon_lat:
            try:
                lon_s, lat_s = lon_lat.split(',', 1)
                lon = float(lon_s); lat = float(lat_s)
            except Exception:
                pass
        out[rid] = {
            'matched': True,
            'lat': lat, 'lng': lon,
            'matched_address': matched_addr,
            'match_type': match_type,  # 'Exact', 'Non_Exact'
        }
    return out


def geocode_batches(records, out_path, id_key='id', resume=True, throttle_s=2.0, label='records'):
    """Geocode all records, writing results to `out_path` as JSON keyed by id.

    Resumable: if out_path exists, already-geocoded ids are skipped.
    Throttles `throttle_s` seconds between batches to be polite to Census.
    """
    out_path = Path(out_path)
    cache = {}
    if resume and out_path.exists():
        try:
            cache = json.load(open(out_path, encoding='utf-8'))
            print(f'  Resuming: {len(cache):,} {label} already cached in {out_path.name}')
        except Exception as e:
            print(f'  Could not load cache ({e}); starting fresh')
            cache = {}

    todo = [r for r in records if str(r.get(id_key, '')) not in cache]
    print(f'  Total: {len(records):,} {label}.  To geocode: {len(todo):,}.  ' \
          f'Cached: {len(cache):,}.  Batches: {(len(todo)+BATCH_SIZE-1)//BATCH_SIZE}')

    for i in range(0, len(todo), BATCH_SIZE):
        chunk = todo[i:i+BATCH_SIZE]
        bn = i // BATCH_SIZE + 1
        csv_body = _build_csv(chunk, id_key)
        if not csv_body.strip():
            print(f'  Batch {bn}: empty (no usable street values); skipping')
            continue
        t0 = time.time()
        print(f'  Batch {bn}: posting {len(chunk):,} {label}…', flush=True)
        resp = _post_batch(csv_body)
        elapsed = time.time() - t0
        parsed = _parse_response(resp)
        matched = sum(1 for v in parsed.values() if v.get('matched'))
        rate = 100 * matched / max(1, len(parsed))
        print(f'  Batch {bn}: returned {len(parsed):,} responses, {matched:,} matched ({rate:.1f}%) in {elapsed:.0f}s', flush=True)
        cache.update(parsed)
        # Persist after each batch — long jobs should be crash-safe
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f)
        if i + BATCH_SIZE < len(todo):
            time.sleep(throttle_s)

    print(f'  Done. {len(cache):,} total in cache.')
    return cache


def summary(cache, county_field=None, records=None, id_key='id'):
    """Print match-rate summary, optionally broken down by county if provided."""
    total = len(cache)
    matched = sum(1 for v in cache.values() if v.get('matched'))
    print(f'Match rate: {matched:,} / {total:,} = {100*matched/max(1,total):.1f}%')
    if county_field and records:
        from collections import defaultdict
        per_co = defaultdict(lambda: {'total':0, 'matched':0})
        for r in records:
            rid = str(r.get(id_key, ''))
            co = r.get(county_field, '?')
            per_co[co]['total'] += 1
            if cache.get(rid, {}).get('matched'): per_co[co]['matched'] += 1
        print('Per-county match rate:')
        for co in sorted(per_co.keys()):
            d = per_co[co]
            rate = 100*d['matched']/max(1,d['total'])
            print(f'  {co:24s}  {d["matched"]:>6,} / {d["total"]:>6,}  ({rate:5.1f}%)')
