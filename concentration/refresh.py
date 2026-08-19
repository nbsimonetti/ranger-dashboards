"""
Bank CRE & Credit Concentration (TX) - data refresh.

Pulls call-report (Consolidated Reports of Condition & Income) financials for
every active Texas-chartered bank from the FDIC BankFind Suite API, joins them
to institution names/counties, computes the supervisory CRE and C&D
concentration ratios (the 2006 interagency 300% CRE / 100% C&D screen), and
injects the result into the dashboard HTML.

Public source: FDIC BankFind Suite API (banks.data.fdic.gov) - free, no key.
Run:  python refresh.py         (auto-detects the latest call-report quarter)
"""
import sys
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from footprint import (http_get_json, inject_data, stamp, in_footprint, FOOTPRINT_FIPS)  # noqa: E402

HERE = Path(__file__).resolve().parent
HTML = HERE / "concentration-tx.html"
INST = "https://banks.data.fdic.gov/api/institutions"
FIN = "https://banks.data.fdic.gov/api/financials"

# Financial line items verified against a live record before use (see below).
FIN_FIELDS = ",".join([
    "CERT", "REPDTE", "NAME", "STCNTY", "CITY",
    "ASSET", "DEP", "LNLSNET", "EQ",
    "LNRECONS",  # construction & land development (C&D)
    "LNREMULT",  # multifamily residential
    "LNRENRES",  # nonfarm nonresidential (CRE)
    "LNATRES",   # allowance for loan & lease losses (ALLL)
    "RBCT1J",    # tier-1 (core) capital, $000s
    "ROA", "NPERFV",
])

CRE_THRESHOLD = 300.0   # % of capital (2006 interagency CRE guidance)
CD_THRESHOLD = 100.0    # % of capital (2006 interagency C&D guidance)


def latest_repdte():
    url = FIN + "?sort_by=REPDTE&sort_order=DESC&limit=1&fields=REPDTE&format=json"
    return int(http_get_json(url)["data"][0]["data"]["REPDTE"])


def pull_institutions():
    """CERT -> {NAME, CITY, COUNTY, ...} for active TX-chartered banks."""
    fields = "CERT,NAME,CITY,COUNTY,STCNTY,ASSET"
    rows, offset = {}, 0
    while True:
        url = (INST + "?filters=STALP:TX%%20AND%%20ACTIVE:1"
               "&fields=%s&limit=10000&offset=%d&format=json" % (fields, offset))
        page = http_get_json(url)["data"]
        for r in page:
            d = r["data"]
            rows[d["CERT"]] = d
        if len(page) < 10000:
            break
        offset += 10000
    return rows


def pull_financials(repdte):
    """CERT -> financial record for every TX bank at the given quarter-end."""
    rows, offset = {}, 0
    while True:
        url = (FIN + "?filters=STALP:TX%%20AND%%20REPDTE:%d"
               "&fields=%s&limit=10000&offset=%d&format=json" % (repdte, FIN_FIELDS, offset))
        page = http_get_json(url)["data"]
        for r in page:
            d = r["data"]
            rows[d["CERT"]] = d
        if len(page) < 10000:
            break
        offset += 10000
    return rows


def build(repdte, insts, fins):
    banks = []
    used_eq_fallback = 0
    for cert, f in fins.items():
        inst = insts.get(cert, {})
        asset = f.get("ASSET") or 0
        cd = f.get("LNRECONS") or 0
        mf = f.get("LNREMULT") or 0
        nr = f.get("LNRENRES") or 0
        cre = cd + mf + nr
        alll = f.get("LNATRES") or 0
        t1 = f.get("RBCT1J")
        eq = f.get("EQ") or 0
        if t1 and t1 > 0:
            capital = t1 + alll
        else:
            capital = eq + alll
            used_eq_fallback += 1
        if capital <= 0:
            continue  # can't form a concentration ratio without positive capital
        loans = f.get("LNLSNET") or 0
        name = inst.get("NAME") or f.get("NAME") or ""
        county = (inst.get("COUNTY") or "").strip()
        stcnty = str(f.get("STCNTY") or inst.get("STCNTY") or "")
        fp = in_footprint(county) or (stcnty in FOOTPRINT_FIPS)
        cre_ratio = round(cre / capital * 100, 1)
        cd_ratio = round(cd / capital * 100, 1)
        banks.append({
            "cert": cert,
            "name": name,
            "county": county,
            "city": inst.get("CITY") or f.get("CITY") or "",
            "asset": asset,
            "dep": f.get("DEP") or 0,
            "creRatio": cre_ratio,
            "cdRatio": cd_ratio,
            "creAssets": round(cre / asset * 100, 1) if asset else None,
            "creLoans": round(cre / loans * 100, 1) if loans else None,
            "roa": round(f["ROA"], 2) if f.get("ROA") is not None else None,
            "npl": round(f["NPERFV"], 2) if f.get("NPERFV") is not None else None,
            "creAmt": cre,
            "cdAmt": cd,
            "capital": capital,
            "fp": 1 if fp else 0,
            "ranger": 1 if "robert lee" in name.lower() else 0,
            "overCre": 1 if cre_ratio >= CRE_THRESHOLD else 0,
            "overCd": 1 if cd_ratio >= CD_THRESHOLD else 0,
        })

    banks.sort(key=lambda b: -b["creRatio"])
    over_cre = sum(b["overCre"] for b in banks)
    over_cd = sum(b["overCd"] for b in banks)
    fp_banks = sum(b["fp"] for b in banks)
    median_cre = round(statistics.median(b["creRatio"] for b in banks), 1) if banks else 0
    median_cd = round(statistics.median(b["cdRatio"] for b in banks), 1) if banks else 0
    capital_basis = ("Tier 1 capital + ALLL" if used_eq_fallback == 0
                     else "Tier 1 capital + ALLL (equity + ALLL for %d banks)" % used_eq_fallback)
    as_of = "%s-%s-%s" % (str(repdte)[:4], str(repdte)[4:6], str(repdte)[6:8])

    return {
        "_meta": stamp("FDIC BankFind Suite API (call-report financials)", {
            "repdte": repdte,
            "as_of": as_of,
            "banks_analyzed": len(banks),
            "institutions_tx": len(insts),
            "over_cre": over_cre,
            "over_cd": over_cd,
            "footprint_banks": fp_banks,
            "median_cre": median_cre,
            "median_cd": median_cd,
            "capital_basis": capital_basis,
            "eq_fallback_banks": used_eq_fallback,
        }),
        "repdte": repdte,
        "as_of": as_of,
        "thresholds": {"cre": CRE_THRESHOLD, "cd": CD_THRESHOLD},
        "banks": banks,
    }


def main():
    repdte = latest_repdte()
    print("latest call-report REPDTE:", repdte)
    insts = pull_institutions()
    print("active TX institutions:", len(insts))
    fins = pull_financials(repdte)
    print("TX financials pulled:", len(fins))
    data = build(repdte, insts, fins)
    m = data["_meta"]
    print("banks analyzed:", m["banks_analyzed"],
          "| over 300%% CRE:", m["over_cre"],
          "| over 100%% C&D:", m["over_cd"],
          "| footprint:", m["footprint_banks"],
          "| median CRE:", m["median_cre"], "%")
    size = inject_data(HTML, data)
    print("injected %.0f KB into %s" % (size / 1024, HTML.name))


if __name__ == "__main__":
    main()
