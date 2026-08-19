"""
Dental & Allied Practice BD - data refresh.

Pulls Texas dental (and allied: optometry) providers from the NPPES NPI Registry
and scores them as business-development prospects for practice loans, deposits,
equipment finance, and treasury - mirroring the physician BD dashboard for an
adjacent, high-value practice-lending segment.

Public source: NPPES API (npiregistry.cms.gov/api) - free, no key.
Note: npiregistry.cms.gov is not resolvable from some sandboxes; this script is
designed to run in the scheduled GitHub Action, where it resolves normally.
The NPPES API caps each query at 1,200 records (limit<=200, skip<=1000), so we
bucket by taxonomy x ZIP-prefix and de-duplicate by NPI.

Run:  python dental/refresh.py            (full pull + inject)
      python dental/refresh.py --selftest (validate scoring/aggregation offline)
"""
import sys
import time
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from footprint import http_get_json, inject_data, stamp  # noqa: E402

HERE = Path(__file__).resolve().parent
HTML = HERE / "dental-tx.html"
API = "https://npiregistry.cms.gov/api/"

# Dental + allied taxonomy descriptions (NPPES `taxonomy_description`).
TAXONOMIES = [
    ("Dentist", "General Dentistry"),
    ("Orthodontics and Dentofacial Orthopedics", "Orthodontics"),
    ("Oral and Maxillofacial Surgery", "Oral Surgery"),
    ("Endodontics", "Endodontics"),
    ("Periodontics", "Periodontics"),
    ("Pediatric Dentistry", "Pediatric Dentistry"),
    ("Prosthodontics", "Prosthodontics"),
    ("Optometrist", "Optometry"),
]
# TX ZIP prefixes covering the footprint metros (DFW/East, FtWorth/West-central,
# Houston/SE, San Antonio/Austin/South, Far-West). Keeps each query < 1,200.
ZIP_PREFIXES = ["75", "76", "77", "78", "79"]

METRO_BY_ZIP3 = None  # (kept simple: we group by city)


def fetch_bucket(desc, zip_prefix):
    out = []
    for skip in range(0, 1001, 200):
        url = ("%s?version=2.1&country_code=US&state=TX"
               "&taxonomy_description=%s&postal_code=%s*&limit=200&skip=%d"
               % (API, urllib_quote(desc), zip_prefix, skip))
        data = http_get_json(url, headers={"User-Agent": "Mozilla/5.0 ranger-dashboards"})
        results = data.get("results") or []
        out.extend(results)
        if len(results) < 200:
            break
        time.sleep(0.3)
    return out


def urllib_quote(s):
    import urllib.parse
    return urllib.parse.quote(s)


def parse_provider(rec, specialty_label):
    basic = rec.get("basic", {}) or {}
    loc = next((a for a in rec.get("addresses", [])
                if a.get("address_purpose") == "LOCATION"), {}) or {}
    org = basic.get("organization_name")
    name = org or (" ".join(x for x in [basic.get("first_name"), basic.get("last_name")] if x)).strip()
    enum = basic.get("enumeration_date") or ""
    tenure = None
    if enum[:4].isdigit():
        tenure = dt.date.today().year - int(enum[:4])
    solo = str(basic.get("sole_proprietor", "")).upper() == "YES"
    return {
        "npi": rec.get("number"),
        "name": name,
        "cred": basic.get("credential") or "",
        "specialty": specialty_label,
        "city": (loc.get("city") or "").title(),
        "zip": (loc.get("postal_code") or "")[:5],
        "phone": loc.get("telephone_number") or "",
        "tenure": tenure,
        "solo": solo,
        "is_org": bool(org),
    }


def score(p):
    """Simple 0-100 BD prospect score; mirrors the physician-BD idiom."""
    s = 40
    t = p.get("tenure")
    if t is not None:
        if 5 <= t <= 25:
            s += 25          # established but not near-retirement
        elif t < 3:
            s += 5           # brand-new practice = startup-loan candidate
        elif t > 35:
            s += 8           # succession candidate
        else:
            s += 15
    if p.get("solo"):
        s += 20              # solo practice = the target relationship
    if p.get("phone"):
        s += 8               # contactable
    if p.get("specialty") in ("Oral Surgery", "Orthodontics", "Periodontics"):
        s += 7               # higher-capex specialties
    return max(0, min(100, s))


def build(providers):
    for p in providers:
        p["score"] = score(p)
    providers.sort(key=lambda p: -p["score"])
    by_spec, by_city = {}, {}
    for p in providers:
        by_spec[p["specialty"]] = by_spec.get(p["specialty"], 0) + 1
        if p["city"]:
            by_city[p["city"]] = by_city.get(p["city"], 0) + 1
    solo_n = sum(1 for p in providers if p["solo"])
    return {
        "_meta": stamp("NPPES NPI Registry API", {
            "providers": len(providers), "solo": solo_n,
            "specialties": len(by_spec),
        }),
        "providers": providers,
        "by_specialty": [{"k": k, "n": v} for k, v in sorted(by_spec.items(), key=lambda x: -x[1])],
        "by_city": [{"k": k, "n": v} for k, v in sorted(by_city.items(), key=lambda x: -x[1])[:25]],
    }


def selftest():
    rec = {"number": "1234567890",
           "basic": {"first_name": "Jane", "last_name": "Doe", "credential": "DDS",
                     "enumeration_date": "2009-05-01", "sole_proprietor": "YES"},
           "addresses": [{"address_purpose": "LOCATION", "city": "DALLAS",
                          "state": "TX", "postal_code": "75201-1234",
                          "telephone_number": "214-555-0100"}]}
    p = parse_provider(rec, "General Dentistry")
    p["score"] = score(p)
    data = build([p])
    assert p["npi"] == "1234567890" and p["solo"] and p["tenure"] == dt.date.today().year - 2009
    assert p["city"] == "Dallas" and p["score"] > 60, p
    assert data["_meta"]["providers"] == 1 and data["by_specialty"][0]["k"] == "General Dentistry"
    print("selftest OK:", {k: p[k] for k in ("name", "specialty", "city", "tenure", "solo", "score")})


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    seen, providers = set(), []
    for desc, label in TAXONOMIES:
        for zp in ZIP_PREFIXES:
            try:
                recs = fetch_bucket(desc, zp)
            except Exception as exc:  # noqa: BLE001
                print("WARN %s/%s: %s" % (label, zp, exc))
                continue
            for rec in recs:
                npi = rec.get("number")
                if npi in seen:
                    continue
                seen.add(npi)
                providers.append(parse_provider(rec, label))
            print("  %-22s zip %s* -> %d (running total %d)" % (label, zp, len(recs), len(providers)))
    print("total unique providers:", len(providers))
    data = build(providers)
    size = inject_data(HTML, data)
    print("injected %.0f KB into %s" % (size / 1024, HTML.name))


if __name__ == "__main__":
    main()
