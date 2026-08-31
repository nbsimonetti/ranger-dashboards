"""
Competitor Terms (West Texas) - data refresh.

What competitors actually charge and require, by market and product, so a loan can
be priced competitively on the first conversation.

SOURCES
  1. HMDA loan-level (CFPB data browser CSV) - the core. Post-2018 HMDA carries the
     actual note rate, LTV, DTI, term, points/fees and balloon/IO/prepay flags for
     every dwelling-secured origination, by lender and county.
       https://ffiec.cfpb.gov/v2/data-browser-api/view/csv?years=YYYY&counties=FIPS
     VERIFIED QUIRKS (do not "fix" these):
       * Accept MUST be */*  -  Accept: text/csv returns HTTP 406
       * User-Agent must look like a browser or the API returns 403
       * pass counties= WITHOUT states=; sending both silently ignores the county
         filter and returns the whole state
       * ffiec.cfpb.gov blocks GitHub Actions runner IPs (403), so this refresh
         cannot run in CI. Run it from a normal network and commit the result; the
         freshness-skip below keeps the weekly CI job from failing on it.
  2. SBA 7(a)/504 FOIA (in-repo loan-maturity/loans_statewide.json) - real
     business-loan pricing: initial rate, fixed/variable, term, size, lender.
  3. FDIC call reports - portfolio yield (INTINCY) and funding cost (INTEXPY) per
     bank, as a pricing proxy for CRE/C&I which HMDA barely covers.
  4. FDIC Summary of Deposits - which lenders actually have branches in each market.

Run:  python competitor-terms/refresh.py            (skips if data is fresh)
      python competitor-terms/refresh.py --force     (always re-pull)
      python competitor-terms/refresh.py --selftest  (offline logic check)
"""
import csv
import io
import json
import re
import sys
import tempfile
import time
import datetime as dt
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from footprint import (inject_data, stamp, http_get_json, COUNTY_GEO,   # noqa: E402
                       WEST_TEXAS, WEST_TEXAS_MARKET, DATA_START, DATA_END)

HERE = Path(__file__).resolve().parent
HTML = HERE / "competitor-terms-wtx.html"
SBA = HERE.parent / "loan-maturity" / "loans_statewide.json"
HMDA = "https://ffiec.cfpb.gov/v2/data-browser-api/view/csv?years=%d&counties=%s&actions_taken=1"
FILERS = "https://ffiec.cfpb.gov/v2/data-browser-api/view/filers?years=%d&states=TX"
HDRS = {"User-Agent": "Mozilla/5.0", "Accept": "*/*"}
SKIP_DAYS = 30
csv.field_size_limit(10 ** 7)

SIZE_BUCKETS = [(0, 150000, "< $150k"), (150000, 300000, "$150-300k"),
                (300000, 500000, "$300-500k"), (500000, 1000000, "$500k-1M"),
                (1000000, float("inf"), "$1M+")]


def size_bucket(v):
    for lo, hi, lab in SIZE_BUCKETS:
        if lo <= v < hi:
            return lab
    return SIZE_BUCKETS[-1][2]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# HMDA reports several fields as BANDS, not numbers. Parsing them with float()
# silently drops every banded row - which biased DTI to the 36-49 band only and
# made every "5-24" unit property look like a single-family home.
DTI_BANDS = {"<20%": 15.0, "20%-<30%": 25.0, "30%-<36%": 33.0,
             "50%-60%": 55.0, ">60%": 65.0}


def parse_dti(v):
    """DTI is 36-49 as integers, everything else as a band. Map bands to midpoints."""
    if v is None:
        return None
    s = str(v).strip()
    if s in DTI_BANDS:
        return DTI_BANDS[s]
    return num(s)


def multifamily(v):
    """total_units is '1'..'4' then '5-24', '25-49', '50-99', '100-149', '>149'."""
    s = str(v or "").strip()
    if not s or s in ("1", "2", "3", "4"):
        return False
    return True


def pctile(sorted_vals, p):
    """Linear-interpolated percentile of an ascending list."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 4)
    k = (len(sorted_vals) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return round(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo), 4)


def deciles(vals):
    s = sorted(vals)
    return [pctile(s, i / 10.0) for i in range(11)]


def med(vals):
    s = sorted(v for v in vals if v is not None)
    return pctile(s, 0.5) if s else None


def classify(row):
    """HMDA row -> product label. Order matters: most specific first."""
    if multifamily(row.get("total_units")):
        return "Multifamily (5+)"
    if str(row.get("business_or_commercial_purpose", "")).strip() == "1":
        return "Business-purpose (dwelling-secured)"
    if str(row.get("lien_status", "")).strip() == "2":
        return "Home equity / 2nd lien"
    lp = str(row.get("loan_purpose", "")).strip()
    if lp == "2":
        return "Home improvement"
    lt = str(row.get("loan_type", "")).strip()
    if lt in ("2", "3", "4"):
        return "FHA / VA / USDA"
    if str(row.get("conforming_loan_limit", "")).strip().upper() == "NC":
        return "Jumbo"
    if lp == "1":
        return "Conventional purchase"
    if lp in ("31", "32"):
        return "Conventional refinance"
    return "Other / unclassified"


# --------------------------------------------------------------------- HMDA ---
def latest_hmda_year():
    y = dt.date.today().year
    for yr in range(y, y - 4, -1):
        try:
            req = urllib.request.Request(HMDA % (yr, "48329"), headers=HDRS)
            with urllib.request.urlopen(req, timeout=120) as r:
                if len(r.read(4000).splitlines()) > 1:
                    return yr
        except Exception:  # noqa: BLE001
            continue
    raise SystemExit("no HMDA year returned data")


CACHE = Path(tempfile.gettempdir()) / "ranger_hmda_cache"


def fetch_county(year, fips, tries=3):
    """Fetch a county's loan-level CSV, caching the raw payload on disk.

    The full 101-county pull takes ~20 minutes; caching means a classification fix
    can be re-applied in seconds instead of re-downloading. Pass --refetch to
    ignore the cache.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    cf = CACHE / ("%d_%s.csv" % (year, fips))
    if cf.exists() and "--refetch" not in sys.argv:
        return cf.read_text(encoding="utf-8", errors="replace")
    for t in range(tries):
        try:
            req = urllib.request.Request(HMDA % (year, fips), headers=HDRS)
            with urllib.request.urlopen(req, timeout=300) as r:
                txt = r.read().decode("utf-8", "replace")
            try:
                cf.write_text(txt, encoding="utf-8")
            except OSError:
                pass
            return txt
        except Exception as exc:  # noqa: BLE001
            if t + 1 >= tries:
                print("    ! %s failed: %s" % (fips, exc))
                return None
            time.sleep(2.5 * (t + 1))


def lender_names(year):
    try:
        d = http_get_json(FILERS % year, headers=HDRS, timeout=120)
        return {i["lei"]: i.get("name", i["lei"]) for i in d.get("institutions", [])}
    except Exception as exc:  # noqa: BLE001
        print("  filers lookup failed (%s) - LEIs will show unnamed" % exc)
        return {}


# ---------------------------------------------------------------------- SBA ---
SBA_PRODUCT = {"sba-7a": "SBA 7(a) business loan", "sba-504": "SBA 504 (CRE/equipment)"}


def sba_terms(wt_names):
    if not SBA.exists():
        return [], []
    raw = json.loads(SBA.read_text(encoding="utf-8"))
    loans = raw.get("loans", raw) if isinstance(raw, dict) else raw
    groups, lenders = {}, {}
    for ln in loans:
        county = (ln.get("county") or "").title()
        if county not in wt_names:
            continue
        rate = num(ln.get("interest_rate"))
        amt = num(ln.get("loan_amount")) or 0
        prod = SBA_PRODUCT.get(ln.get("source"), "SBA")
        mkt = WEST_TEXAS_MARKET.get(county, "Rural West Texas")
        g = groups.setdefault((mkt, prod), {"rates": [], "terms": [], "amts": [], "var": 0, "n": 0})
        g["n"] += 1
        g["amts"].append(amt)
        if rate:
            g["rates"].append(rate)
        if ln.get("term_months"):
            g["terms"].append(num(ln["term_months"]))
        if str(ln.get("rate_type", "")).upper().startswith("V"):
            g["var"] += 1
        lender = ln.get("lender") or "Undisclosed"
        L = lenders.setdefault(lender, {"lender": lender, "n": 0, "amt": 0.0, "rates": []})
        L["n"] += 1
        L["amt"] += amt
        if rate:
            L["rates"].append(rate)
    out = []
    for (mkt, prod), g in groups.items():
        out.append({
            "market": mkt, "product": prod, "n": g["n"],
            "rate_deciles": deciles(g["rates"]) if g["rates"] else None,
            "med_rate": med(g["rates"]), "med_term_mo": med(g["terms"]),
            "med_amt": med(g["amts"]), "var_share": round(100.0 * g["var"] / g["n"], 1),
        })
    out.sort(key=lambda r: (-r["n"], r["market"]))
    lend = sorted(({"lender": v["lender"], "n": v["n"], "amt": round(v["amt"]),
                    "med_rate": med(v["rates"])} for v in lenders.values()),
                  key=lambda r: -r["n"])[:40]
    return out, lend


# --------------------------------------------------------------------- FDIC ---
def fdic_context(wt_names):
    """Bank-level yield/funding proxies + branch presence per market."""
    base = "https://banks.data.fdic.gov/api"
    yields_by_cert, presence = {}, {}
    repdte = sod_year = None
    try:
        latest = http_get_json(base + "/financials?filters=STALP:TX&fields=REPDTE"
                               "&sort_by=REPDTE&sort_order=DESC&limit=1&format=json")
        repdte = latest["data"][0]["data"]["REPDTE"]
        f = "CERT,NAME,INTINCY,INTEXPY,NIMY,ASSET,LNLSNET,LNRENRES,LNRECONS,LNCI,LNAG"
        d = http_get_json(base + "/financials?filters=STALP:TX%%20AND%%20REPDTE:%s"
                          "&fields=%s&limit=10000&format=json" % (repdte, f))
        for rec in d["data"]:
            r = rec["data"]
            yields_by_cert[r["CERT"]] = {
                "yield": r.get("INTINCY"), "cof": r.get("INTEXPY"), "nim": r.get("NIMY"),
                "cre": r.get("LNRENRES"), "constr": r.get("LNRECONS"),
                "ci": r.get("LNCI"), "ag": r.get("LNAG"), "loans": r.get("LNLSNET"),
            }
    except Exception as exc:  # noqa: BLE001
        print("  FDIC financials unavailable (%s)" % exc)
    try:
        sod_year = http_get_json(base + "/sod?filters=STALPBR:TX&fields=YEAR&sort_by=YEAR"
                                 "&sort_order=DESC&limit=1&format=json")["data"][0]["data"]["YEAR"]
        offset = 0
        while True:
            d = http_get_json(base + "/sod?filters=STALPBR:TX%%20AND%%20YEAR:%d"
                              "&fields=CERT,NAMEFULL,CNTYNAMB,DEPSUMBR&limit=10000"
                              "&offset=%d&format=json" % (sod_year, offset))
            page = d["data"]
            for rec in page:
                r = rec["data"]
                county = (r.get("CNTYNAMB") or "").strip()
                if county not in wt_names:
                    continue
                mkt = WEST_TEXAS_MARKET.get(county, "Rural West Texas")
                key = (r.get("NAMEFULL") or "").strip()
                p = presence.setdefault(key, {"bank": key, "cert": r.get("CERT"),
                                              "branches": 0, "dep": 0, "markets": {}})
                p["branches"] += 1
                p["dep"] += r.get("DEPSUMBR") or 0
                p["markets"][mkt] = p["markets"].get(mkt, 0) + 1
            if len(page) < 10000:
                break
            offset += 10000
    except Exception as exc:  # noqa: BLE001
        print("  FDIC SOD unavailable (%s)" % exc)
    rows = sorted(presence.values(), key=lambda p: -p["branches"])[:60]
    for p in rows:
        y = yields_by_cert.get(p["cert"])
        if y:
            p.update({"yield": y["yield"], "cof": y["cof"], "nim": y["nim"],
                      "cre": y["cre"], "ci": y["ci"], "ag": y["ag"]})
        p["markets"] = sorted(p["markets"], key=lambda k: -p["markets"][k])[:4]
    return rows, repdte, sod_year


# -------------------------------------------------------------------- build ---
def build(year, county_rows, lei_names, sba_bench, sba_lenders, presence, repdte, sod_year):
    bench, bench_size, lender_agg, lender_mkt, counties = {}, {}, {}, {}, []

    for fips, rows in county_rows.items():
        cname = COUNTY_GEO.get(fips, (fips, None, None))[0]
        mkt = WEST_TEXAS_MARKET.get(cname, "Rural West Texas")
        crates, cvol = [], 0.0
        for r in rows:
            prod = classify(r)
            rate = num(r.get("interest_rate"))
            amt = num(r.get("loan_amount")) or 0
            cvol += amt
            if rate:
                crates.append(rate)
            b = bench.setdefault((mkt, prod), {"rates": [], "ltv": [], "dti": [], "term": [],
                                               "fees": [], "amt": [], "n": 0, "vol": 0.0,
                                               "arm": 0, "io": 0, "balloon": 0, "prepay": 0})
            b["n"] += 1
            b["vol"] += amt
            if rate:
                b["rates"].append(rate)
            ltv = num(r.get("loan_to_value_ratio"))
            if ltv and 0 < ltv <= 200:
                b["ltv"].append(ltv)
            dti = parse_dti(r.get("debt_to_income_ratio"))
            if dti and 0 < dti <= 100:
                b["dti"].append(dti)
            trm = num(r.get("loan_term"))
            if trm:
                b["term"].append(trm)
            fee = num(r.get("total_loan_costs"))
            if fee:
                b["fees"].append(fee)
            if amt:
                b["amt"].append(amt)
            if (num(r.get("intro_rate_period")) or 0) > 0:
                b["arm"] += 1
            if str(r.get("interest_only_payment", "")).strip() == "1":
                b["io"] += 1
            if str(r.get("balloon_payment", "")).strip() == "1":
                b["balloon"] += 1
            if (num(r.get("prepayment_penalty_term")) or 0) > 0:
                b["prepay"] += 1
            if rate and amt:
                bench_size.setdefault((mkt, prod, size_bucket(amt)), []).append(rate)

            lei = (r.get("lei") or "").strip()
            if lei:
                L = lender_agg.setdefault(lei, {"lei": lei, "name": lei_names.get(lei, lei),
                                                "n": 0, "vol": 0.0, "rates": [], "amts": [],
                                                "markets": {}, "products": {}})
                L["n"] += 1
                L["vol"] += amt
                if rate:
                    L["rates"].append(rate)
                if amt:
                    L["amts"].append(amt)
                L["markets"][mkt] = L["markets"].get(mkt, 0) + 1
                L["products"][prod] = L["products"].get(prod, 0) + 1
                lm = lender_mkt.setdefault((lei, mkt, prod), {"rates": [], "n": 0, "vol": 0.0})
                lm["n"] += 1
                lm["vol"] += amt
                if rate:
                    lm["rates"].append(rate)

        counties.append({"fips": fips, "county": cname, "market": mkt,
                         "n": len(rows), "vol": round(cvol), "med_rate": med(crates)})

    bench_rows = []
    for (mkt, prod), b in bench.items():
        sr = sorted(b["rates"])
        bench_rows.append({
            "market": mkt, "product": prod, "n": b["n"], "vol": round(b["vol"]),
            "rate_deciles": deciles(b["rates"]) if sr else None,
            "p10": pctile(sr, .1) if sr else None, "med_rate": med(b["rates"]),
            "p90": pctile(sr, .9) if sr else None,
            "med_ltv": med(b["ltv"]), "med_dti": med(b["dti"]), "med_term": med(b["term"]),
            "med_fees": med(b["fees"]), "med_amt": med(b["amt"]),
            "arm_share": round(100.0 * b["arm"] / b["n"], 1),
            "io_share": round(100.0 * b["io"] / b["n"], 1),
            "balloon_share": round(100.0 * b["balloon"] / b["n"], 1),
            "prepay_share": round(100.0 * b["prepay"] / b["n"], 1),
        })
    bench_rows.sort(key=lambda r: (-r["n"], r["market"]))

    size_rows = [{"market": m, "product": p, "size": s, "n": len(v),
                  "rate_deciles": deciles(v), "med_rate": med(v)}
                 for (m, p, s), v in bench_size.items() if len(v) >= 15]
    size_rows.sort(key=lambda r: -r["n"])

    lenders = []
    for L in lender_agg.values():
        lenders.append({
            "lei": L["lei"], "name": L["name"], "n": L["n"], "vol": round(L["vol"]),
            "med_rate": med(L["rates"]), "med_amt": med(L["amts"]),
            "markets": sorted(L["markets"], key=lambda k: -L["markets"][k])[:4],
            "n_markets": len(L["markets"]),
            "top_product": max(L["products"], key=lambda k: L["products"][k]),
        })
    lenders.sort(key=lambda r: -r["n"])

    lm_rows = [{"lei": lei, "name": lei_names.get(lei, lei), "market": m, "product": p,
                "n": v["n"], "vol": round(v["vol"]), "med_rate": med(v["rates"])}
               for (lei, m, p), v in lender_mkt.items() if v["n"] >= 5]
    lm_rows.sort(key=lambda r: -r["n"])

    total_n = sum(c["n"] for c in counties)
    return {
        "_meta": stamp("HMDA loan-level (CFPB) + SBA FOIA + FDIC call reports & SOD", {
            "hmda_year": year, "counties": len(counties), "loans": total_n,
            "markets": len(set(c["market"] for c in counties)),
            "lenders": len(lenders), "products": len(set(b["product"] for b in bench_rows)),
            "fdic_repdte": repdte, "sod_year": sod_year,
            "median_rate_overall": med([b["med_rate"] for b in bench_rows if b["med_rate"]]),
        }),
        "benchmarks": bench_rows,
        "by_size": size_rows,
        "lenders": lenders[:300],
        "lender_market": lm_rows[:1500],
        "counties": counties,
        "sba": {"benchmarks": sba_bench, "lenders": sba_lenders},
        "presence": presence,
        "markets": sorted(set(c["market"] for c in counties)),
        "products": sorted(set(b["product"] for b in bench_rows)),
        "size_buckets": [b[2] for b in SIZE_BUCKETS],
    }


def fresh():
    if not HTML.exists():
        return False
    txt = HTML.read_text(encoding="utf-8")
    m = re.search(re.escape(DATA_START) + r"(.*?)" + re.escape(DATA_END), txt, re.S)
    if not m or m.group(1).strip() in ("", "null"):
        return False
    try:
        d = json.loads(m.group(1))
        gen = dt.datetime.strptime(d["_meta"]["generated_at"], "%Y-%m-%dT%H:%M:%SZ").date()
    except Exception:  # noqa: BLE001
        return False
    return bool(d.get("benchmarks")) and (dt.date.today() - gen).days < SKIP_DAYS


def selftest():
    rows = [{"total_units": "1", "loan_type": "1", "loan_purpose": "1", "lien_status": "1",
             "conforming_loan_limit": "C", "business_or_commercial_purpose": "2"},
            {"total_units": "1", "loan_type": "1", "loan_purpose": "1", "lien_status": "1",
             "conforming_loan_limit": "NC", "business_or_commercial_purpose": "2"},
            {"total_units": "8", "loan_type": "1", "loan_purpose": "1", "lien_status": "1",
             "conforming_loan_limit": "C", "business_or_commercial_purpose": "1"},
            {"total_units": "1", "loan_type": "2", "loan_purpose": "1", "lien_status": "1",
             "conforming_loan_limit": "C", "business_or_commercial_purpose": "2"}]
    got = [classify(r) for r in rows]
    assert got == ["Conventional purchase", "Jumbo", "Multifamily (5+)", "FHA / VA / USDA"], got
    assert deciles([1, 2, 3, 4, 5])[5] == 3
    assert size_bucket(200000) == "$150-300k" and size_bucket(2e6) == "$1M+"
    assert med([3, 1, 2]) == 2
    assert pctile([1, 2, 3, 4], 0.5) == 2.5
    # regressions: HMDA banded fields must not be silently dropped
    assert classify({"total_units": "5-24", "loan_type": "1", "loan_purpose": "1",
                     "lien_status": "1", "conforming_loan_limit": "C",
                     "business_or_commercial_purpose": "2"}) == "Multifamily (5+)"
    assert multifamily("5-24") and multifamily(">149") and not multifamily("4")
    assert parse_dti("<20%") == 15.0 and parse_dti("50%-60%") == 55.0
    assert parse_dti("43") == 43.0 and parse_dti("NA") is None
    print("selftest OK:", got)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    if "--force" not in sys.argv and fresh():
        print("competitor-terms data is fresh (< %d days) - skipping HMDA pull." % SKIP_DAYS)
        return

    year = latest_hmda_year()
    print("HMDA year:", year)
    names = lender_names(year)
    print("lender names:", len(names))

    wt_names = set(WEST_TEXAS)
    county_rows, tot = {}, 0
    items = sorted(WEST_TEXAS.items())
    for i, (cname, fips) in enumerate(items, 1):
        txt = fetch_county(year, fips)
        if not txt:
            continue
        rows = list(csv.DictReader(io.StringIO(txt)))
        if rows:
            county_rows[fips] = rows
        tot += len(rows)
        print("  [%3d/%d] %-14s %-6s %6d loans (running %d)"
              % (i, len(items), cname, fips, len(rows), tot))
        time.sleep(0.25)

    print("HMDA rows total:", tot)
    sba_bench, sba_lenders = sba_terms(wt_names)
    print("SBA benchmark groups:", len(sba_bench))
    presence, repdte, sod_year = fdic_context(wt_names)
    print("FDIC presence rows:", len(presence), "| repdte:", repdte, "| SOD:", sod_year)

    data = build(year, county_rows, names, sba_bench, sba_lenders, presence, repdte, sod_year)
    size = inject_data(HTML, data)
    m = data["_meta"]
    print("injected %.0f KB | loans=%d lenders=%d markets=%d products=%d"
          % (size / 1024, m["loans"], m["lenders"], m["markets"], m["products"]))


if __name__ == "__main__":
    main()
