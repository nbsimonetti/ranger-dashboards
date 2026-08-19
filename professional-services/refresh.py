"""
Professional Services BD (TX) - data refresh.

Business-development prospecting for professional-services firms (law, accounting,
architecture/engineering, IT & management consulting, and other professional
practices) as targets for practice loans, deposits, equipment finance and
treasury.

Two public sources, both self-contained in this repo's pipeline:

  1. SBA 7(a)/504 FOIA borrowers - the in-repo ../loan-maturity/loans.json
     (already footprint-filtered). Filtered here to NAICS sector 54, tagged with
     a human subsector label, and scored 0-100 as a warm BD prospect. Each row is
     a real TX firm with a known financing relationship.

  2. BLS QCEW (Quarterly Census of Employment and Wages) Open Data - annual
     county files, for MARKET SIZING (total addressable establishments &
     employment per subsector per county). This is the denominator the
     SBA-visible prospects sit inside.  Endpoint (CSV data slices):
       https://data.bls.gov/cew/data/api/{YEAR}/a/area/{FIPS}.csv
     Filter to own_code==5 (private), agglvl_code==76 (county x 4-digit NAICS)
     for the 54xx subsectors, and industry_code==54 / agglvl 74 for the sector
     total.  Free, no key.

Run:  python professional-services/refresh.py
"""
import sys
import csv
import io
import datetime as dt
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from footprint import inject_data, stamp, FOOTPRINT, USER_AGENT  # noqa: E402

HERE = Path(__file__).resolve().parent
HTML = HERE / "professional-services-tx.html"
LOANS = HERE.parent / "loan-maturity" / "loans_statewide.json"

QCEW_URL = "https://data.bls.gov/cew/data/api/%d/a/area/%s.csv"

# --- NAICS sector-54 subsector taxonomy ------------------------------------
# 4-digit prefix -> (detailed label, 5-bucket filter group)
SUB_LABEL = {
    "5411": "Legal Services",
    "5412": "Accounting & Tax",
    "5413": "Architecture & Engineering",
    "5414": "Specialized Design",
    "5415": "Computer Systems Design",
    "5416": "Management Consulting",
    "5417": "Scientific R&D",
    "5418": "Advertising & PR",
    "5419": "Other Professional",
}
SUB_GROUP = {
    "5411": "Legal",
    "5412": "Accounting",
    "5413": "Arch-Eng", "5414": "Arch-Eng",
    "5415": "Consulting", "5416": "Consulting",
    "5417": "Other", "5418": "Other", "5419": "Other",
}
GROUP_ORDER = ["Legal", "Accounting", "Arch-Eng", "Consulting", "Other"]
SUB_ORDER = ["5411", "5412", "5413", "5414", "5415", "5416", "5417", "5418", "5419"]

# --- SBA loan_status -> (display class, status points 0-20) -----------------
# Warm = firm carries an active financing relationship we could win / refi /
# cross-sell.  Closed/prepaid firms are proven borrowers worth re-engaging.
STATUS_MAP = {
    "CURR": ("Active", 20), "CURRENT": ("Active", 20),
    "COMMIT": ("Committed", 18),
    "PURCH(NOT C/O)": ("Servicing", 13), "IN CATCH-UP": ("Servicing", 12),
    "DEFERD": ("Servicing", 12), "LIQUID": ("Servicing", 11),
    "PSTDUE": ("Distressed", 8), "DELINQ": ("Distressed", 8),
    "CLSLN": ("Distressed", 8),
    "PREPAID IN FULL": ("Closed", 7), "PAID IN FULL (LIQ)": ("Closed", 7),
    "CANCELED": ("Closed", 5), "NOT FUNDED": ("Closed", 5),
}


def status_class_pts(status):
    return STATUS_MAP.get((status or "").strip().upper(), ("Other", 6))


def parse_date(s):
    try:
        return dt.date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# 1) SBA side
# ---------------------------------------------------------------------------
def load_prospects():
    import json
    raw = json.loads(LOANS.read_text(encoding="utf-8"))
    meta = raw.get("meta", {})
    loans = raw.get("loans", raw if isinstance(raw, list) else [])
    prof = [l for l in loans if str(l.get("naics_code") or "").startswith("54")]

    asof = parse_date(meta.get("sba_asof")) or dt.date.today()
    rates = sorted(l["interest_rate"] for l in prof if l.get("interest_rate"))
    benchmark = rates[len(rates) // 2] if rates else 9.5  # median 54xx rate

    firms = []
    for l in prof:
        code4 = str(l.get("naics_code"))[:4]
        amt = l.get("loan_amount") or 0
        rate = l.get("interest_rate")
        appr = parse_date(l.get("approval_date"))

        # 1) loan size (0-30): sqrt scale, full credit at $2M
        size = 30 * min(1.0, (amt / 2_000_000.0) ** 0.5) if amt > 0 else 0
        # 2) recency (0-25): linear decay over 72 months from approval
        if appr:
            mago = (asof - appr).days / 30.44
            rec = 25 * clamp(1 - mago / 72.0)
        else:
            rec = 8
        # 3) above-market rate = refinance/win-back upside (0-25)
        if rate is None:
            refi = 10
        else:
            refi = 25 * clamp((rate - benchmark) / 3.0)
            if (l.get("rate_type") or "") == "V":  # variable = easiest to reprice
                refi = min(25.0, refi + 4)
        # 4) status (0-20)
        sclass, spts = status_class_pts(l.get("loan_status"))
        score = round(size + rec + refi + spts)

        firms.append({
            "firm": l.get("borrower") or "",
            "sub": code4,
            "label": SUB_LABEL.get(code4, "Professional"),
            "group": SUB_GROUP.get(code4, "Other"),
            "naics": l.get("naics_code"),
            "ndesc": l.get("naics_description") or "",
            "city": l.get("borrower_city") or "",
            "county": (l.get("county") or "").strip(),
            "amt": amt,
            "guar": l.get("sba_guaranteed_amount") or 0,
            "lender": l.get("lender") or "",
            "rate": rate,
            "rtype": l.get("rate_type") or "",
            "appr": l.get("approval_date") or "",
            "status": l.get("loan_status") or "",
            "sclass": sclass,
            "score": score,
            "mtm": l.get("months_to_maturity"),
            "mat": l.get("maturity_date") or "",
            "src": l.get("source") or "",
        })
    firms.sort(key=lambda f: -f["score"])
    return firms, meta, round(benchmark, 2), asof


def aggregate(firms, qsub, qcounty):
    """Roll firms up by 9 detailed subsectors, 5 groups, and county;
    fold in QCEW establishment/employment TAM where available."""
    def blank():
        return {"count": 0, "amt": 0.0, "rate_sum": 0.0, "rate_n": 0,
                "score_sum": 0, "active": 0, "grp": {}}

    subs = {c: blank() for c in SUB_ORDER}
    groups = {g: blank() for g in GROUP_ORDER}
    counties = {}

    for f in firms:
        for bucket in (subs.get(f["sub"]), groups.get(f["group"]),
                       counties.setdefault(f["county"], blank())):
            if bucket is None:
                continue
            bucket["count"] += 1
            bucket["amt"] += f["amt"]
            if f["rate"] is not None:
                bucket["rate_sum"] += f["rate"]; bucket["rate_n"] += 1
            bucket["score_sum"] += f["score"]
            if f["sclass"] in ("Active", "Committed", "Servicing"):
                bucket["active"] += 1
        counties[f["county"]]["grp"][f["group"]] = \
            counties[f["county"]]["grp"].get(f["group"], 0) + 1

    def finish(d):
        return {
            "count": d["count"], "amt": round(d["amt"]),
            "avg_rate": round(d["rate_sum"] / d["rate_n"], 2) if d["rate_n"] else None,
            "avg_score": round(d["score_sum"] / d["count"]) if d["count"] else 0,
            "active": d["active"],
        }

    sub_rows = []
    for c in SUB_ORDER:
        r = finish(subs[c])
        r.update({"code": c, "label": SUB_LABEL[c], "group": SUB_GROUP[c],
                  "qcew_estabs": qsub.get(c, {}).get("estabs"),
                  "qcew_empl": qsub.get(c, {}).get("empl")})
        sub_rows.append(r)

    group_rows = []
    for g in GROUP_ORDER:
        r = finish(groups[g])
        qe = sum(qsub.get(c, {}).get("estabs") or 0
                 for c in SUB_ORDER if SUB_GROUP[c] == g)
        r.update({"group": g, "qcew_estabs": qe or None})
        group_rows.append(r)

    county_rows = []
    for name, d in counties.items():
        r = finish(d)
        top_grp = max(d["grp"].items(), key=lambda kv: kv[1])[0] if d["grp"] else "—"
        q = qcounty.get(name, {})
        r.update({"county": name, "fips": FOOTPRINT.get(name, ""),
                  "top_group": top_grp,
                  "qcew_estabs": q.get("estabs"), "qcew_empl": q.get("empl"),
                  "qcew_sector_estabs": q.get("sector_estabs")})
        county_rows.append(r)
    county_rows.sort(key=lambda x: -x["amt"])
    return sub_rows, group_rows, county_rows


# ---------------------------------------------------------------------------
# 2) QCEW side (market sizing)
# ---------------------------------------------------------------------------
def fetch_qcew_area(year, fips):
    """GET one county's annual QCEW CSV. Returns list[dict] of 54xx private
    rows we care about, or None on 404 (no file for that year/area)."""
    url = QCEW_URL % (year, fips)
    hdrs = {"User-Agent": USER_AGENT, "Accept": "text/csv"}
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=45) as resp:
                text = resp.read().decode("utf-8", "replace")
            rows = []
            for r in csv.DictReader(io.StringIO(text)):
                if r.get("own_code") != "5":
                    continue
                ind, agg = r.get("industry_code", ""), r.get("agglvl_code", "")
                if ind == "54" and agg == "74":          # sector total
                    rows.append(r)
                elif len(ind) == 4 and ind[:2] == "54" and agg == "76":  # 4-digit
                    rows.append(r)
            return rows
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            last = exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
        import time
        time.sleep(1.5 * (attempt + 1))
    raise last


def build_qcew():
    """Detect the latest available annual year, then loop the footprint."""
    this_year = dt.date.today().year
    year, seed = None, None
    for y in range(this_year, this_year - 4, -1):
        try:
            probe = fetch_qcew_area(y, FOOTPRINT["Dallas"])
        except Exception as exc:
            print("  QCEW probe %d failed: %r" % (y, exc))
            probe = None
        if probe:
            year, seed = y, probe
            break
    if not year:
        return {"status": "unavailable",
                "note": "BLS QCEW open-data CSV endpoint returned no annual "
                        "file for the last 4 years (or was unreachable)."}, {}, {}

    def to_int(v):
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return 0

    qsub = {c: {"estabs": 0, "empl": 0} for c in SUB_ORDER}     # footprint totals
    qcounty = {}                                                 # per-county
    matrix = []
    covered, failed = 0, 0

    for name, fips in FOOTPRINT.items():
        rows = seed if fips == FOOTPRINT["Dallas"] else None
        if rows is None:
            try:
                rows = fetch_qcew_area(year, fips)
            except Exception as exc:
                print("  QCEW %s (%s) failed: %r" % (name, fips, exc))
                failed += 1
                continue
        if rows is None:
            failed += 1
            continue
        covered += 1
        cell = {"county": name, "fips": fips, "estabs": 0, "empl": 0,
                "sector_estabs": 0, "sector_empl": 0, "subs": {}}
        for r in rows:
            ind = r["industry_code"]
            est, emp = to_int(r.get("annual_avg_estabs")), to_int(r.get("annual_avg_emplvl"))
            if ind == "54":
                cell["sector_estabs"], cell["sector_empl"] = est, emp
            else:
                cell["subs"][ind] = est
                cell["estabs"] += est
                cell["empl"] += emp
                qsub[ind]["estabs"] += est
                qsub[ind]["empl"] += emp
        qcounty[name] = {"estabs": cell["estabs"], "empl": cell["empl"],
                         "sector_estabs": cell["sector_estabs"]}
        matrix.append(cell)

    matrix.sort(key=lambda c: -c["sector_estabs"])
    sector_estabs = sum(c["sector_estabs"] for c in matrix)
    sector_empl = sum(c["sector_empl"] for c in matrix)
    qcew = {
        "status": "ok",
        "year": year,
        "counties_covered": covered,
        "counties_failed": failed,
        "by_subsector": qsub,
        "sector_total": {"estabs": sector_estabs, "empl": sector_empl},
        "matrix": matrix,
    }
    return qcew, qsub, qcounty


# ---------------------------------------------------------------------------
def main():
    print("loading SBA prospects from", LOANS.name)
    firms, meta, benchmark, asof = load_prospects()
    print("  sector-54 firms:", len(firms), "| benchmark rate:", benchmark, "%")

    print("building QCEW market sizing (looping %d footprint counties)..." % len(FOOTPRINT))
    try:
        qcew, qsub, qcounty = build_qcew()
    except Exception as exc:
        print("  QCEW build failed entirely: %r" % exc)
        qcew, qsub, qcounty = {"status": "unavailable", "note": repr(exc)}, {}, {}
    print("  QCEW status:", qcew.get("status"), "| year:", qcew.get("year"),
          "| counties:", qcew.get("counties_covered"), "ok /",
          qcew.get("counties_failed"), "missing")

    sub_rows, group_rows, county_rows = aggregate(firms, qsub, qcounty)

    total_credit = round(sum(f["amt"] for f in firms))
    top_sub = max(sub_rows, key=lambda r: r["count"])
    top_county = county_rows[0] if county_rows else {"county": "—", "amt": 0}

    data = {
        "_meta": stamp(
            "SBA 7(a)/504 FOIA borrowers (in-repo) + BLS QCEW open data", {
                "sba_asof": meta.get("sba_asof"),
                "sba_asof_tag": meta.get("sba_asof_tag"),
                "benchmark_rate": benchmark,
                "recency_anchor": asof.isoformat(),
                "qcew_status": qcew.get("status"),
                "qcew_year": qcew.get("year"),
                "qcew_counties": qcew.get("counties_covered"),
                "firms": len(firms),
                "total_credit": total_credit,
                "footprint_counties_with_firms": len(county_rows),
            }),
        "firms": firms,
        "subsectors": sub_rows,
        "groups": group_rows,
        "counties": county_rows,
        "qcew": qcew,
        "sub_order": SUB_ORDER,
        "group_order": GROUP_ORDER,
        "top_subsector": top_sub["label"],
        "top_county": top_county["county"],
    }

    size = inject_data(HTML, data)
    print("injected %.0f KB into %s" % (size / 1024, HTML.name))
    print("  top subsector:", top_sub["label"], "(%d firms)" % top_sub["count"],
          "| top county:", top_county["county"])


if __name__ == "__main__":
    main()
