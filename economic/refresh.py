"""
Footprint Economic & Market Vitality (TX) - data refresh.

Pulls county market fundamentals for the 33-county Ranger / RLSB footprint and
injects them into the self-contained dashboard (economic-tx.html):

  * BLS QCEW (annual averages) - employment, establishments, wages
        https://data.bls.gov/cew/data/api/{YEAR}/a/area/{FIPS}.csv
    The QCEW "Open Data Access" service returns CSV (the /a/area/{fips}.json
    path 404s), so we parse CSV. The county-total row is the one where
    industry_code == "10" (Total, all industries) AND own_code == "0"
    (Total covered, all ownerships) -> agglvl_code 70. Fields used:
        annual_avg_estabs, annual_avg_emplvl, annual_avg_wkly_wage,
        avg_annual_pay, total_annual_wages.

  * BLS LAUS (monthly) - county unemployment rate (latest month)
        POST https://api.bls.gov/publicAPI/v2/timeseries/data/
        series id LAUCN{FIPS}0000000003 (suffix ...03 = unemployment rate).
        BLS_API_KEY (registrationkey) is sent only if the env var is set;
        requests are chunked at 25 series so they also work keyless.

  * Census ACS 5-year (OPTIONAL) - median household income + population
        https://api.census.gov/data/{ACS_YEAR}/acs/acs5
        Only runs when CENSUS_API_KEY is set; skipped gracefully otherwise
        (keyless ACS returns a non-JSON error page). The scheduled GitHub
        Action supplies CENSUS_API_KEY as a repo secret.

"Market vitality" (0-100) percentile-ranks each of four metrics across the
footprint and blends them 30 / 25 / 25 / 20 (employment level / avg weekly wage
/ low unemployment / establishment density). Percentile ranks are
weight-independent, so the dashboard re-weights the blend live.

Run:  python economic/refresh.py      (auto-detects the latest QCEW year)
"""
import csv
import io
import json
import os
import sys
import statistics
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from footprint import (http_get, inject_data, stamp, FOOTPRINT, USER_AGENT)  # noqa: E402

HERE = Path(__file__).resolve().parent
HTML = HERE / "economic-tx.html"

QCEW_URL = "https://data.bls.gov/cew/data/api/%d/a/area/%s.csv"
LAUS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
ACS_YEAR = 2022
ACS_URL = ("https://api.census.gov/data/%d/acs/acs5"
           "?get=NAME,B19013_001E,B01003_001E&for=county:*&in=state:48&key=%s")
BEA_URL = ("https://apps.bea.gov/api/data?&UserID=%s&method=GetData&datasetname=Regional"
           "&TableName=CAINC1&LineCode=3&GeoFips=COUNTY&Year=LAST5&ResultFormat=json")

# Documented market-vitality weights (percentile blend, sum need not be 100).
VITALITY_WEIGHTS = {
    "employment": 30,             # employment level (higher = better)
    "wage": 25,                   # avg weekly wage (higher = better)
    "low_unemployment": 25,       # unemployment rate (lower = better)
    "establishment_density": 20,  # establishments per 1k workers (higher=better)
}

# Authoritative county name + centroid (Census 2023 Gazetteer, INTPTLAT/LONG)
# keyed by 5-digit FIPS. Used for display labels and the map so the label always
# matches the FIPS actually queried.
GEO = {
    "48005": ("Angelina", 31.2549, -94.6118), "48027": ("Bell", 31.0428, -97.4813),
    "48029": ("Bexar", 29.4487, -98.5201), "48039": ("Brazoria", 29.1678, -95.4346),
    "48041": ("Brazos", 30.6567, -96.3024), "48055": ("Caldwell", 29.8324, -97.6281),
    "48061": ("Cameron", 26.1029, -97.479), "48071": ("Chambers", 29.6964, -94.6694),
    "48099": ("Coryell", 31.3912, -97.798), "48113": ("Dallas", 32.767, -96.7784),
    "48135": ("Ector", 31.8653, -102.5425), "48157": ("Fort Bend", 29.5266, -95.771),
    "48167": ("Galveston", 29.2339, -94.8882), "48181": ("Grayson", 33.6245, -96.6758),
    "48183": ("Gregg", 32.4864, -94.8163), "48199": ("Hardin", 30.3296, -94.3932),
    "48201": ("Harris", 29.8573, -95.393), "48245": ("Jefferson", 29.854, -94.1493),
    "48251": ("Johnson", 32.3797, -97.3649), "48257": ("Kaufman", 32.5989, -96.2884),
    "48265": ("Kerr", 30.06, -99.3533), "48291": ("Liberty", 30.1585, -94.8441),
    "48355": ("Nueces", 27.74, -97.5162), "48365": ("Panola", 32.164, -94.3052),
    "48401": ("Rusk", 32.1094, -94.7564), "48439": ("Tarrant", 32.7721, -97.2912),
    "48441": ("Taylor", 32.2971, -99.8904), "48449": ("Titus", 33.2146, -94.9668),
    "48453": ("Travis", 30.2395, -97.6913), "48469": ("Victoria", 28.7964, -96.9712),
    "48485": ("Wichita", 33.9882, -98.708), "48491": ("Williamson", 30.6491, -97.6051),
    "48497": ("Wise", 33.2191, -97.654),
}

FIPS_LIST = sorted(set(FOOTPRINT.values()))
_MONTHS = {"M01": "Jan", "M02": "Feb", "M03": "Mar", "M04": "Apr", "M05": "May",
           "M06": "Jun", "M07": "Jul", "M08": "Aug", "M09": "Sep", "M10": "Oct",
           "M11": "Nov", "M12": "Dec"}


def _num(s):
    """Parse a QCEW numeric cell -> float or None (blank/non-numeric -> None)."""
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if s == "" or s == "N/A":
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ------------------------------------------------------------------ QCEW ----
def _qcew_total_row(csv_text):
    """Return the county-total row dict (industry 10, own 0) or None."""
    for row in csv.DictReader(io.StringIO(csv_text)):
        if row.get("industry_code") == "10" and row.get("own_code") == "0":
            return row
    return None


def latest_qcew_year(probe_fips="48113"):
    """Newest annual QCEW year that returns data (probe Dallas, step back)."""
    import datetime as _dt
    this_year = _dt.date.today().year
    for year in range(this_year, this_year - 8, -1):
        try:
            txt = http_get(QCEW_URL % (year, probe_fips)).decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            raise
        if _qcew_total_row(txt):
            return year
    raise SystemExit("no QCEW annual year returned data for %s" % probe_fips)


def fetch_qcew(year):
    """{fips: {employment, establishments, wkly_wage, annual_pay, total_wages}}."""
    out = {}
    for fips in FIPS_LIST:
        try:
            txt = http_get(QCEW_URL % (year, fips)).decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            print("  QCEW %s: HTTP %s (skipped)" % (fips, exc.code))
            continue
        row = _qcew_total_row(txt)
        if not row:
            print("  QCEW %s: no total row (skipped)" % fips)
            continue
        out[fips] = {
            "employment": _num(row.get("annual_avg_emplvl")),
            "establishments": _num(row.get("annual_avg_estabs")),
            "wkly_wage": _num(row.get("annual_avg_wkly_wage")),
            "annual_pay": _num(row.get("avg_annual_pay")),
            "total_wages": _num(row.get("total_annual_wages")),
        }
    return out


# ------------------------------------------------------------------ LAUS ----
def _post_json(url, body, headers=None, timeout=45, retries=3):
    import time
    hdrs = {"User-Agent": USER_AGENT, "Content-Type": "application/json",
            "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    data = json.dumps(body).encode("utf-8")
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(2.0 * (attempt + 1))
    raise last


def fetch_laus(cal_year):
    """{fips: (rate, 'Mon YYYY')} latest monthly unemployment rate per county."""
    key = os.environ.get("BLS_API_KEY")
    out = {}
    latest_period = ""  # 'YYYY-Mnn' for picking the overall newest month
    series_by_fips = {"LAUCN%s0000000003" % f: f for f in FIPS_LIST}
    ids = list(series_by_fips)
    for i in range(0, len(ids), 25):
        chunk = ids[i:i + 25]
        body = {"seriesid": chunk,
                "startyear": str(cal_year - 1), "endyear": str(cal_year)}
        if key:
            body["registrationkey"] = key
        try:
            resp = _post_json(LAUS_URL, body)
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            print("  LAUS chunk %d: %s (skipped)" % (i // 25, exc))
            continue
        if resp.get("status") != "REQUEST_SUCCEEDED":
            print("  LAUS chunk %d: %s %s" % (i // 25, resp.get("status"),
                                              resp.get("message")))
        for s in resp.get("Results", {}).get("series", []):
            fips = series_by_fips.get(s.get("seriesID"))
            pts = [d for d in s.get("data", [])
                   if d.get("period", "").startswith("M") and d.get("period") != "M13"
                   and _num(d.get("value")) is not None]
            if not fips or not pts:
                continue
            pts.sort(key=lambda d: (d["year"], d["period"]), reverse=True)
            top = pts[0]
            out[fips] = (float(top["value"]),
                         "%s %s" % (_MONTHS.get(top["period"], top["period"]),
                                    top["year"]))
            tag = "%s-%s" % (top["year"], top["period"])
            if tag > latest_period:
                latest_period = tag
    period_label = ""
    if latest_period:
        y, m = latest_period.split("-")
        period_label = "%s %s" % (_MONTHS.get(m, m), y)
    return out, period_label


# ------------------------------------------------------------------- ACS ----
def fetch_acs():
    """{fips: (median_income, population)} or {} when unavailable / no key."""
    key = os.environ.get("CENSUS_API_KEY")
    if not key:
        print("  ACS: CENSUS_API_KEY not set - skipping median income / population")
        return {}
    try:
        rows = json.loads(http_get(ACS_URL % (ACS_YEAR, key)).decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001 - never fail the whole refresh on ACS
        print("  ACS: request failed (%s) - skipping" % exc)
        return {}
    out = {}
    for r in rows[1:]:
        try:
            inc = int(r[1]) if r[1] not in (None, "", "-666666666") else None
            pop = int(r[2]) if r[2] not in (None, "") else None
            fips = "48" + r[-1]
        except (ValueError, IndexError):
            continue
        if fips in set(FIPS_LIST):
            out[fips] = (inc, pop)
    print("  ACS: %d footprint counties with income/population" % len(out))
    return out


# ------------------------------------------------------------------- BEA ----
def fetch_bea():
    """{fips: per_capita_personal_income} or {} when no key / unavailable.

    BEA Regional table CAINC1, LineCode 3 (per-capita personal income), latest of
    the last five years per county. Gated on BEA_API_KEY; never fails the refresh.
    """
    key = os.environ.get("BEA_API_KEY")
    if not key:
        print("  BEA: BEA_API_KEY not set - skipping per-capita income")
        return {}
    try:
        raw = json.loads(http_get(BEA_URL % key).decode("utf-8", "replace"))
        rows = raw["BEAAPI"]["Results"]["Data"]
    except Exception as exc:  # noqa: BLE001 - never fail the whole refresh on BEA
        print("  BEA: request failed (%s) - skipping" % exc)
        return {}
    best = {}
    fset = set(FIPS_LIST)
    for r in rows:
        fips = (r.get("GeoFips") or "").strip()
        if fips not in fset:
            continue
        try:
            yr = int(r.get("TimePeriod"))
            val = int(str(r.get("DataValue")).replace(",", "").strip())
        except (TypeError, ValueError):
            continue
        if fips not in best or yr > best[fips][0]:
            best[fips] = (yr, val)
    out = {f: v for f, (y, v) in best.items()}
    print("  BEA: %d footprint counties with per-capita income" % len(out))
    return out


# ------------------------------------------------------------- vitality ----
def pct_rank(values):
    """{fips: value|None} -> {fips: percentile 0-100|None}, higher value=higher.

    Ties share their average position; single value -> 100; None -> None.
    """
    items = [(f, v) for f, v in values.items() if v is not None]
    out = {f: None for f in values}
    n = len(items)
    if n == 0:
        return out
    if n == 1:
        out[items[0][0]] = 100.0
        return out
    items.sort(key=lambda kv: kv[1])
    i = 0
    while i < n:
        j = i
        while j + 1 < n and items[j + 1][1] == items[i][1]:
            j += 1
        pctl = round((i + j) / 2.0 / (n - 1) * 100.0, 1)
        for k in range(i, j + 1):
            out[items[k][0]] = pctl
        i = j + 1
    return out


def blend(pcts, weights):
    """Weighted mean of available percentile components -> 0-100 (or None)."""
    num = den = 0.0
    for comp, w in weights.items():
        p = pcts.get(comp)
        if p is not None:
            num += w * p
            den += w
    return round(num / den, 1) if den else None


# ------------------------------------------------------------------ build ---
def build(year, qcew, laus, acs, bea, laus_period):
    counties = {}
    for fips in FIPS_LIST:
        name, lat, lng = GEO.get(fips, (fips, None, None))
        q = qcew.get(fips, {})
        emp = q.get("employment")
        est = q.get("establishments")
        density = round(est / emp * 1000, 1) if (emp and est) else None
        rate, period = laus.get(fips, (None, None))
        inc, pop = acs.get(fips, (None, None))
        counties[fips] = {
            "fips": fips, "county": name, "lat": lat, "lng": lng,
            "employment": int(emp) if emp is not None else None,
            "establishments": int(est) if est is not None else None,
            "estab_density": density,
            "wkly_wage": int(q["wkly_wage"]) if q.get("wkly_wage") is not None else None,
            "annual_pay": int(q["annual_pay"]) if q.get("annual_pay") is not None else None,
            "unemp": rate, "unemp_period": period,
            "med_income": inc, "population": pop,
            "bea_pci": bea.get(fips),
        }

    # percentile ranks across the footprint (weight-independent)
    p_emp = pct_rank({f: c["employment"] for f, c in counties.items()})
    p_wage = pct_rank({f: c["wkly_wage"] for f, c in counties.items()})
    # lower unemployment is better -> rank the negated rate
    p_unemp = pct_rank({f: (-c["unemp"] if c["unemp"] is not None else None)
                        for f, c in counties.items()})
    p_dens = pct_rank({f: c["estab_density"] for f, c in counties.items()})
    for f, c in counties.items():
        c["p_emp"], c["p_wage"] = p_emp[f], p_wage[f]
        c["p_unemp"], c["p_density"] = p_unemp[f], p_dens[f]
        c["vitality"] = blend({"employment": c["p_emp"], "wage": c["p_wage"],
                               "low_unemployment": c["p_unemp"],
                               "establishment_density": c["p_density"]},
                              VITALITY_WEIGHTS)

    rows = sorted(counties.values(),
                  key=lambda c: (c["vitality"] is not None, c["vitality"] or 0),
                  reverse=True)

    emps = [c["employment"] for c in rows if c["employment"] is not None]
    ests = [c["establishments"] for c in rows if c["establishments"] is not None]
    rates = [c["unemp"] for c in rows if c["unemp"] is not None]
    ww = [(c["wkly_wage"], c["employment"]) for c in rows
          if c["wkly_wage"] is not None and c["employment"] is not None]
    wage_wtd = round(sum(w * e for w, e in ww) / sum(e for _, e in ww)) if ww else None
    top = rows[0] if rows and rows[0]["vitality"] is not None else None
    has_income = any(c["med_income"] is not None for c in rows)
    has_bea = any(c["bea_pci"] is not None for c in rows)

    src = "BLS QCEW (annual) + BLS LAUS (monthly)"
    if has_income:
        src += " + Census ACS 5-year"
    if has_bea:
        src += " + BEA per-capita income"
    meta = stamp(src, {
        "qcew_year": year,
        "laus_period": laus_period or None,
        "acs_year": ACS_YEAR if has_income else None,
        "has_income": has_income,
        "has_bea": has_bea,
        "footprint_counties": len(rows),
        "total_employment": sum(emps),
        "total_establishments": sum(ests),
        "median_unemployment": round(statistics.median(rates), 1) if rates else None,
        "avg_weekly_wage": wage_wtd,
        "top_county": top["county"] if top else None,
        "top_vitality": top["vitality"] if top else None,
        "weights": VITALITY_WEIGHTS,
    })
    return {"_meta": meta, "counties": rows}


def main():
    year = latest_qcew_year()
    print("latest QCEW annual year:", year)
    import datetime as _dt
    cal_year = _dt.date.today().year

    qcew = fetch_qcew(year)
    print("QCEW counties with data:", len(qcew))
    laus, laus_period = fetch_laus(cal_year)
    print("LAUS counties with data:", len(laus), "| latest period:", laus_period or "n/a")
    acs = fetch_acs()
    bea = fetch_bea()

    data = build(year, qcew, laus, acs, bea, laus_period)
    m = data["_meta"]
    print("footprint counties: %d | total employment: %s | median unemployment: %s%%"
          % (m["footprint_counties"], format(m["total_employment"], ","),
             m["median_unemployment"]))
    size = inject_data(HTML, data)
    print("injected %.0f KB into %s" % (size / 1024, HTML.name))


if __name__ == "__main__":
    main()
