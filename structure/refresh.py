"""
TX Bank Structure & M&A Activity - data refresh.

Reconstructs the shape and change of the Texas community-banking landscape from
the FDIC BankFind Suite: active bank counts over time, de-novo formations, exits
(mergers / absorptions / voluntary closures), and outright failures. The output
powers a competitive-situational-awareness dashboard - how many charters remain,
who is forming or disappearing, and where M&A is thinning the field inside the
33-county footprint.

Public sources (free, no key):
  - Institutions:  banks.data.fdic.gov/api/institutions   (active + historical)
  - Failures:      banks.data.fdic.gov/api/failures

Run:  python refresh.py
"""
import sys
import datetime as dt
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from footprint import (http_get_json, inject_data, stamp, FOOTPRINT, in_footprint)  # noqa: E402

HERE = Path(__file__).resolve().parent
HTML = HERE / "structure-tx.html"

INST = "https://banks.data.fdic.gov/api/institutions"
FAIL = "https://banks.data.fdic.gov/api/failures"

# Reconstructed active-count / flow charts start here (FDIC BankFind retains
# historical charters back to 1934; 1980 captures the full Texas boom -> 1980s
# oil-bust & S&L collapse -> long consolidation arc without survivorship noise).
START_YEAR = 1980

# Footprint county centroids, derived once from the mean of every FDIC Summary
# of Deposits branch coordinate reported in that county (187,975 branch-years).
# Authentic FDIC-sourced geography - used only to place the footprint bubble map.
# [lat, lng]
CENTROIDS = {
    "Angelina": [31.3040, -94.7144], "Bell": [31.0844, -97.5398],
    "Bexar": [29.5407, -98.5213], "Brazoria": [29.3516, -95.4233],
    "Brazos": [30.6552, -96.4240], "Caldwell": [29.7896, -97.6683],
    "Cameron": [26.0540, -97.5351], "Chambers": [29.8024, -94.6422],
    "Coryell": [31.2820, -97.8422], "Dallas": [32.8345, -96.8693],
    "Ector": [31.8678, -102.3598], "Fort Bend": [29.6404, -95.7270],
    "Galveston": [29.4257, -95.0170], "Grayson": [33.6348, -96.6291],
    "Gregg": [32.4808, -94.8166], "Hardin": [30.2856, -94.2947],
    "Harris": [29.8327, -95.5474], "Jefferson": [30.0555, -94.1885],
    "Johnson": [32.4251, -97.3500], "Kaufman": [32.6476, -96.3654],
    "Kerr": [30.0566, -99.1736], "Liberty": [30.1594, -94.8913],
    "Nueces": [27.7585, -97.4066], "Panola": [32.1395, -94.3749],
    "Rusk": [32.0983, -94.8261], "Tarrant": [32.7704, -97.3037],
    "Taylor": [32.4379, -99.7419], "Titus": [33.1785, -94.9796],
    "Travis": [30.3241, -97.7990], "Victoria": [28.8229, -96.9990],
    "Wichita": [33.8387, -98.5182], "Williamson": [30.5711, -97.7179],
    "Wise": [33.1972, -97.6609],
}


def year_of(s):
    """FDIC dates are MM/DD/YYYY; 12/31/9999 is the 'still active' sentinel."""
    if not s:
        return None
    try:
        y = int(str(s).strip().split("/")[-1])
    except (ValueError, IndexError):
        return None
    return None if y >= 9999 else y


def pull(url, fields):
    rows, offset = [], 0
    while True:
        page = http_get_json(
            "%s?filters=%s&fields=%s&limit=10000&offset=%d&format=json"
            % (url["base"], url["filter"], fields, offset))["data"]
        rows.extend(r["data"] for r in page)
        if len(page) < 10000:
            break
        offset += 10000
    return rows


def build(inst, fail, cur):
    last5 = range(cur - 5, cur)        # 5 most-recent complete years
    last15 = range(cur - 15, cur)

    # --- normalise institutions ---
    recs = []
    for x in inst:
        recs.append({
            "cert": x.get("CERT"),
            "name": x.get("NAME") or "",
            "city": x.get("CITY") or "",
            "county": (x.get("COUNTY") or "").strip(),
            "assets": x.get("ASSET"),
            "bkclass": x.get("BKCLASS") or "",
            "active": 1 if x.get("ACTIVE") == 1 else 0,
            "est": year_of(x.get("ESTYMD")),
            "end": year_of(x.get("ENDEFYMD")),
        })

    cert_to_county = {r["cert"]: r["county"] for r in recs if r["cert"] is not None}
    active = [r for r in recs if r["active"]]

    # --- reconstructed active-count series & formation/exit flow ---
    formations = Counter(r["est"] for r in recs if r["est"] is not None)
    exits = Counter(r["end"] for r in recs
                    if not r["active"] and r["end"] is not None)
    active_series, flow_series = [], []
    for y in range(START_YEAR, cur + 1):
        live = sum(1 for r in recs if r["est"] is not None and r["est"] <= y
                   and (r["active"] or (r["end"] is not None and r["end"] > y)))
        active_series.append({"year": y, "active": live})
        flow_series.append({"year": y, "formations": formations.get(y, 0),
                            "exits": exits.get(y, 0)})

    # --- recent-activity tables ---
    def row(r):
        return {"year": None, "name": r["name"], "city": r["city"],
                "county": r["county"], "assets": r["assets"],
                "bkclass": r["bkclass"], "fp": in_footprint(r["county"])}

    recent_denovos = []
    for r in recs:
        if r["est"] is not None and r["est"] >= cur - 30:
            d = row(r); d["year"] = r["est"]; recent_denovos.append(d)
    recent_exits = []
    for r in recs:
        if not r["active"] and r["end"] is not None and r["end"] >= cur - 20:
            d = row(r); d["year"] = r["end"]; recent_exits.append(d)
    recent_denovos.sort(key=lambda d: (-d["year"], -(d["assets"] or 0)))
    recent_exits.sort(key=lambda d: (-d["year"], -(d["assets"] or 0)))

    # --- failures (county recovered via CERT -> institutions join) ---
    fail_rows = []
    for f in fail:
        try:
            fy = int(f.get("FAILYR"))
        except (TypeError, ValueError):
            fy = year_of(f.get("FAILDATE"))
        county = cert_to_county.get(f.get("CERT"), "")
        cityst = (f.get("CITYST") or "").rsplit(",", 1)
        fail_rows.append({
            "year": fy, "name": f.get("NAME") or "", "city": cityst[0].strip(),
            "county": county, "assets": f.get("QBFASSET"),
            "deposits": f.get("QBFDEP"), "cost": f.get("COST"),
            "restype": f.get("RESTYPE") or "", "fp": in_footprint(county),
        })
    fail_rows.sort(key=lambda d: (-(d["year"] or 0), -(d["assets"] or 0)))
    fail_by_county = Counter(f["county"] for f in fail_rows if f["county"])

    # --- footprint focus (33 counties) ---
    fp_active = Counter(r["county"] for r in active if in_footprint(r["county"]))
    fp_denovo5 = Counter(r["county"] for r in recs
                         if in_footprint(r["county"]) and r["est"] in last5)
    fp_exit5 = Counter(r["county"] for r in recs
                       if in_footprint(r["county"]) and not r["active"]
                       and r["end"] in last5)
    footprint = []
    for county, fips in FOOTPRINT.items():
        c = CENTROIDS.get(county, [None, None])
        footprint.append({
            "county": county, "fips": fips, "lat": c[0], "lng": c[1],
            "active": fp_active.get(county, 0),
            "denovos5": fp_denovo5.get(county, 0),
            "exits5": fp_exit5.get(county, 0),
            "failures": fail_by_county.get(county, 0),
        })
    footprint.sort(key=lambda d: -d["active"])

    # --- headline counts ---
    active_n = len(active)
    fp_active_n = sum(1 for r in active if in_footprint(r["county"]))
    denovos_5y = sum(1 for r in recs if r["est"] in last5)
    exits_5y = sum(1 for r in recs
                   if not r["active"] and r["end"] in last5)
    failures_15y = sum(1 for f in fail_rows if f["year"] in last15)
    fp_failures = sum(1 for f in fail_rows if f["fp"])

    return {
        "_meta": stamp("FDIC BankFind Suite - Institutions & Failures APIs", {
            "current_year": cur,
            "start_year": START_YEAR,
            "active_banks": active_n,
            "fp_active": fp_active_n,
            "denovos_5y": denovos_5y,
            "exits_5y": exits_5y,
            "failures_15y": failures_15y,
            "failures_total": len(fail_rows),
            "fp_failures": fp_failures,
            "institutions_records": len(recs),
            "window_5y": "%d–%d" % (cur - 5, cur - 1),
            "window_15y": "%d–%d" % (cur - 15, cur - 1),
        }),
        "current_year": cur,
        "start_year": START_YEAR,
        "active_series": active_series,
        "flow_series": flow_series,
        "recent_denovos": recent_denovos,
        "recent_exits": recent_exits,
        "failures": fail_rows,
        "footprint": footprint,
    }


def main():
    cur = dt.date.today().year
    inst = pull({"base": INST, "filter": "STALP:TX"},
                "CERT,NAME,CITY,COUNTY,ASSET,ESTYMD,ENDEFYMD,ACTIVE,BKCLASS")
    print("TX institution records (active + historical):", len(inst))
    fail = pull({"base": FAIL, "filter": "PSTALP:TX"},
                "NAME,CERT,FAILYR,FAILDATE,CITYST,QBFDEP,QBFASSET,COST,RESTYPE")
    print("TX failure records:", len(fail))
    data = build(inst, fail, cur)
    m = data["_meta"]
    print("active banks: %d  |  de-novos %s: %d  |  exits %s: %d  |  failures %s: %d"
          % (m["active_banks"], m["window_5y"], m["denovos_5y"],
             m["window_5y"], m["exits_5y"], m["window_15y"], m["failures_15y"]))
    print("active-count series: %d (%d) -> %d (%d)"
          % (data["active_series"][0]["active"], data["active_series"][0]["year"],
             data["active_series"][-1]["active"], data["active_series"][-1]["year"]))
    size = inject_data(HTML, data)
    print("injected %.0f KB into %s" % (size / 1024, HTML.name))


if __name__ == "__main__":
    main()
