"""
Mortgage Lending Landscape (TX) - data refresh.

Pulls HMDA mortgage aggregations for every footprint county from the CFPB /
FFIEC data-browser API and injects origination volume, denial rates, loan-purpose
mix, and an average-purchase-size ("high-income / jumbo") proxy into the
self-contained dashboard HTML.

Public source: CFPB / FFIEC HMDA data browser (ffiec.cfpb.gov) - free, no key.
Every request MUST send a browser User-Agent or the API returns 403.

Key API quirk (verified): geography must be passed as counties={5-digit FIPS}
with NO states= parameter. If both are sent, the API silently ignores the
county and returns the whole state. See METHODOLOGY in mortgage-tx.html.

Run:  python refresh.py         (auto-detects the latest available HMDA year)
"""
import sys
import re
import time
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from footprint import (http_get_json, inject_data, stamp, FOOTPRINT, COUNTY_GEO)  # noqa: E402

HERE = Path(__file__).resolve().parent
HTML = HERE / "mortgage-tx.html"
BASE = "https://ffiec.cfpb.gov/v2/data-browser-api/view/aggregations"
# The FFIEC data browser rejects a stdlib/default UA with 403; a browser UA works.
HDRS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
# HMDA (ffiec.cfpb.gov) blocks GitHub Actions runner IPs (403), so this can't run
# in CI - it is refreshed from a non-blocked network and committed (like the SBA
# data). Skip when the dashboard already holds fresh data so the weekly CI job
# doesn't repeatedly fail against HMDA. HMDA is annual, so the window is generous.
SKIP_DAYS = 40


def _fresh():
    if not HTML.exists():
        return False
    txt = HTML.read_text(encoding="utf-8")
    mo = re.search(r'"generated_at":"([0-9T:\-]+Z)".{0,300}?"footprint_originations":(\d+)',
                   txt, re.S)
    if not mo:
        return False
    try:
        gen = dt.datetime.strptime(mo.group(1), "%Y-%m-%dT%H:%M:%SZ").date()
    except ValueError:
        return False
    return int(mo.group(2)) > 0 and (dt.date.today() - gen).days < SKIP_DAYS

# FHFA baseline conforming-loan limit (1-unit) by year. Used only as the jumbo
# reference line / "jumbo-lean" flag on the physician-proxy view.
CONFORMING = {2020: 510400, 2021: 548250, 2022: 647200, 2023: 726200,
              2024: 766550, 2025: 806500, 2026: 838150}



def _agg(url, tries=2):
    """Fetch aggregations; return {} on a hard failure so one bad county
    cannot abort the whole run."""
    for t in range(tries):
        try:
            j = http_get_json(url, headers=HDRS, timeout=60)
            out = {}
            for a in j.get("aggregations", []):
                key = a.get("actions_taken", "") + "|" + a.get("loan_purposes", "")
                out[key] = (a.get("count", 0) or 0, a.get("sum", 0) or 0.0)
            return out
        except Exception as exc:  # noqa: BLE001
            if t + 1 >= tries:
                print("    ! request failed:", type(exc).__name__, exc)
                return {}
            time.sleep(1.5)


def latest_year():
    """Highest year the data browser actually serves. Unpublished years return
    HTTP 400 (verified for 2026 while 2025 was live), so the first year that
    returns originations is the latest complete year."""
    start = dt.date.today().year
    for y in range(start, start - 9, -1):
        d = _agg(BASE + "?years=%d&counties=48113&actions_taken=1" % y)
        cnt = d.get("1|", (0, 0))[0]
        if cnt > 0:
            return y
        time.sleep(0.4)
    raise SystemExit("no HMDA year returned data from the data browser")


def pull_county(year, fips):
    # Call A: action breakdown -> originations, denials, applications.
    a = _agg(BASE + "?years=%d&counties=%s&actions_taken=1,2,3,4,5" % (year, fips))
    time.sleep(0.45)
    # Call B: originated loans by purpose -> purpose mix + avg purchase size.
    b = _agg(BASE + "?years=%d&counties=%s&actions_taken=1&loan_purposes=1,2,31,32,4"
             % (year, fips))
    time.sleep(0.45)

    orig, orig_usd = a.get("1|", (0, 0.0))
    denials = a.get("3|", (0, 0.0))[0]
    apps = sum(a.get(k, (0, 0.0))[0] for k in ("1|", "2|", "3|", "4|", "5|"))

    purchase, purchase_usd = b.get("1|1", (0, 0.0))
    refi_c = b.get("1|31", (0, 0.0))[0] + b.get("1|32", (0, 0.0))[0]
    refi_usd = b.get("1|31", (0, 0.0))[1] + b.get("1|32", (0, 0.0))[1]

    return {
        "orig": orig, "orig_usd": round(orig_usd),
        "apps": apps, "denials": denials,
        "denial_rate": round(100.0 * denials / apps, 1) if apps else None,
        "purchase": purchase, "purchase_usd": round(purchase_usd),
        "refi": refi_c, "refi_usd": round(refi_usd),
        "avg_orig": round(orig_usd / orig) if orig else None,
        "avg_purchase": round(purchase_usd / purchase) if purchase else None,
        "pct_purchase": round(100.0 * purchase / orig, 1) if orig else None,
        "pct_refi": round(100.0 * refi_c / orig, 1) if orig else None,
    }


def build(year):
    rows = []
    for i, (name, fips) in enumerate(sorted(FOOTPRINT.items()), 1):
        print("  [%2d/%d] %-12s %s" % (i, len(FOOTPRINT), name, fips), end=" ")
        d = pull_county(year, fips)
        _, lat, lng = COUNTY_GEO.get(fips, (None, None, None))
        d.update({"county": name, "fips": fips, "lat": lat, "lng": lng})
        print("orig=%-7s denials=%-6s dr=%s%%"
              % (d["orig"], d["denials"], d["denial_rate"]))
        rows.append(d)

    rows.sort(key=lambda r: -(r["orig"] or 0))
    fp_orig = sum(r["orig"] for r in rows)
    fp_usd = sum(r["orig_usd"] for r in rows)
    fp_apps = sum(r["apps"] for r in rows)
    fp_denials = sum(r["denials"] for r in rows)
    fp_purch = sum(r["purchase"] for r in rows)
    fp_purch_usd = sum(r["purchase_usd"] for r in rows)

    return {
        "_meta": stamp("HMDA via CFPB / FFIEC data browser (aggregations API)", {
            "year": year,
            "counties": len(rows),
            "footprint_originations": fp_orig,
            "footprint_orig_usd": fp_usd,
            "footprint_denial_rate": round(100.0 * fp_denials / fp_apps, 1) if fp_apps else None,
            "footprint_applications": fp_apps,
            "footprint_avg_purchase": round(fp_purch_usd / fp_purch) if fp_purch else None,
            "conforming_ref": CONFORMING.get(year, max(CONFORMING.values())),
        }),
        "year": year,
        "counties": rows,
    }


def main():
    if "--force" not in sys.argv and _fresh():
        print("mortgage data is fresh (< %d days) - skipping HMDA pull "
              "(HMDA blocks CI; refresh from a non-blocked network)." % SKIP_DAYS)
        return
    year = latest_year()
    print("latest HMDA year:", year)
    print("pulling %d Texas counties (2 requests each)..." % len(FOOTPRINT))
    data = build(year)
    m = data["_meta"]
    print("footprint originations:", format(m["footprint_originations"], ","),
          "| volume $%.1fB" % (m["footprint_orig_usd"] / 1e9),
          "| denial rate %s%%" % m["footprint_denial_rate"])
    size = inject_data(HTML, data)
    print("injected %.0f KB into %s" % (size / 1024, HTML.name))


if __name__ == "__main__":
    main()
