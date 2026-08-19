"""
Deposit Market Share & Branch Network - data refresh.

Pulls the FDIC Summary of Deposits (branch-level deposits, as of June 30 each
year) for all Texas branches, aggregates to county market share + institution
rankings + a sparse institution x county deposit matrix (which powers the
client-side M&A overlap tool), and injects the result into the dashboard HTML.

Public source: FDIC BankFind Suite SOD API (banks.data.fdic.gov) - free, no key.
Run:  python refresh.py         (auto-detects the latest SOD year)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from footprint import (http_get_json, inject_data, stamp, FOOTPRINT, in_footprint)  # noqa: E402

HERE = Path(__file__).resolve().parent
HTML = HERE / "deposit-share-tx.html"
SOD = "https://banks.data.fdic.gov/api/sod"


def latest_year():
    url = SOD + "?filters=STALPBR:TX&fields=YEAR&sort_by=YEAR&sort_order=DESC&limit=1&format=json"
    return int(http_get_json(url)["data"][0]["data"]["YEAR"])


def pull_year(year):
    fields = "CERT,NAMEFULL,NAMEBR,CITYBR,CNTYNAMB,DEPSUMBR,SIMS_LATITUDE,SIMS_LONGITUDE,BKMO"
    rows, offset = [], 0
    while True:
        url = (SOD + "?filters=STALPBR:TX%%20AND%%20YEAR:%d"
               "&fields=%s&limit=10000&offset=%d&format=json" % (year, fields, offset))
        page = http_get_json(url)["data"]
        rows.extend(r["data"] for r in page)
        if len(page) < 10000:
            break
        offset += 10000
    return rows


def build(year, rows):
    insts = {}   # cert -> institution accumulator
    counties = {}  # county -> {dep, branches, banks:set, by_cert:{cert:dep}}
    branches = []  # footprint branch points for the map

    for r in rows:
        cert = r.get("CERT")
        dep = r.get("DEPSUMBR") or 0
        county = (r.get("CNTYNAMB") or "").strip()
        name = r.get("NAMEFULL") or ""
        fp = in_footprint(county)

        inst = insts.setdefault(cert, {
            "cert": cert, "name": name, "tx_dep": 0, "branches": 0,
            "fp_dep": 0, "fp_branches": 0, "by_county": {},
            "ranger": "robert lee" in name.lower(),
        })
        inst["tx_dep"] += dep
        inst["branches"] += 1
        if county:
            inst["by_county"][county] = inst["by_county"].get(county, 0) + dep
        if fp:
            inst["fp_dep"] += dep
            inst["fp_branches"] += 1

        if county:
            c = counties.setdefault(county, {"dep": 0, "branches": 0, "by_cert": {}, "fp": fp})
            c["dep"] += dep
            c["branches"] += 1
            c["by_cert"][cert] = c["by_cert"].get(cert, 0) + dep

        lat, lng = r.get("SIMS_LATITUDE"), r.get("SIMS_LONGITUDE")
        if fp and lat and lng:
            branches.append({
                "c": cert, "n": name, "b": r.get("NAMEBR") or "",
                "ci": r.get("CITYBR") or "", "co": county,
                "la": round(lat, 5), "lo": round(lng, 5),
                "d": dep, "mo": 1 if r.get("BKMO") == 1 else 0,
            })

    name_of = {cert: i["name"] for cert, i in insts.items()}

    # County market share (footprint counties only in the table; share within full county)
    county_rows = []
    for county, c in counties.items():
        if not c["fp"]:
            continue
        ranked = sorted(c["by_cert"].items(), key=lambda kv: -kv[1])
        total = c["dep"] or 1
        hhi = sum((v / total * 100) ** 2 for v in c["by_cert"].values())
        county_rows.append({
            "county": county, "deposits": c["dep"], "branches": c["branches"],
            "banks": len(c["by_cert"]), "hhi": round(hhi),
            "top": [{"cert": cert, "name": name_of.get(cert, ""), "dep": dep,
                     "share": round(dep / total * 100, 1)} for cert, dep in ranked[:5]],
        })
    county_rows.sort(key=lambda x: -x["deposits"])

    # Institution rankings
    inst_rows = []
    for i in insts.values():
        i["counties"] = len(i["by_county"])
        i["dep_per_branch"] = round(i["tx_dep"] / i["branches"]) if i["branches"] else 0
        inst_rows.append(i)
    inst_rows.sort(key=lambda x: -x["tx_dep"])

    fp_dep_total = sum(c["deposits"] for c in county_rows)
    return {
        "_meta": stamp("FDIC Summary of Deposits (SOD) API", {
            "year": year, "as_of": "%d-06-30" % year,
            "branches_tx": len(rows), "institutions_tx": len(insts),
            "footprint_counties": len(county_rows),
            "footprint_deposits_000": fp_dep_total,
        }),
        "year": year,
        "counties": county_rows,
        "institutions": inst_rows,
        "branches": branches,
    }


def main():
    year = latest_year()
    print("latest SOD year:", year)
    rows = pull_year(year)
    print("TX branches pulled:", len(rows))
    data = build(year, rows)
    print("footprint counties:", len(data["counties"]),
          "| institutions:", len(data["institutions"]),
          "| map branches:", len(data["branches"]))
    size = inject_data(HTML, data)
    print("injected %.0f KB into %s" % (size / 1024, HTML.name))


if __name__ == "__main__":
    main()
