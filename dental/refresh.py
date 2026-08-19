"""
Dental & Allied Practice BD - data refresh (NPPES bulk file).

Pulls Texas dental and optometry providers from the monthly NPPES Data
Dissemination file and scores them as business-development prospects.

Why the bulk file and not the API: the NPPES query API (npiregistry.cms.gov) is
DNS-unreachable from both the Claude sandbox and GitHub Actions runners. The
monthly full-file dissemination on download.cms.gov IS reachable, so we stream it
instead. It is ~1.15 GB zipped / ~10 GB CSV, so:
  * we auto-discover the current month's file from the NPPES listing,
  * stream the main CSV (never loading it all into memory),
  * and skip the download entirely if the dashboard already holds fresh data
    (< SKIP_DAYS old) - keeping the weekly workflow cheap since the source is
    only updated monthly.

Public source: NPPES Data Dissemination (download.cms.gov) - free, no key.
Run:  python dental/refresh.py              (download + parse + inject)
      python dental/refresh.py --force      (ignore the freshness skip)
      python dental/refresh.py --selftest   (validate parse/score offline)
"""
import sys
import io
import csv
import zipfile
import tempfile
import datetime as dt
import re
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from footprint import http_get, inject_data, stamp, USER_AGENT, DATA_START, DATA_END  # noqa: E402

HERE = Path(__file__).resolve().parent
HTML = HERE / "dental-tx.html"
LISTING = "https://download.cms.gov/nppes/NPI_Files.html"
BASE = "https://download.cms.gov/nppes/"
SKIP_DAYS = 25

# Taxonomy family -> label. We match dental by the 1223* prefix and optometry by
# 152W*, and refine common dental specialties by exact code.
DENTAL_LABEL = {
    "122300000X": "General Dentistry", "1223G0001X": "General Dentistry",
    "1223X0400X": "Orthodontics", "1223X2210X": "Orofacial Pain",
    "1223S0112X": "Oral & Maxillofacial Surgery", "1223E0200X": "Endodontics",
    "1223P0221X": "Pediatric Dentistry", "1223P0300X": "Periodontics",
    "1223P0700X": "Prosthodontics", "1223D0001X": "Dental Public Health",
    "1223D0004X": "Dentist Anesthesiologist", "1223X0008X": "Oral & Maxillofacial Radiology",
    "1223P0106X": "Oral & Maxillofacial Pathology",
}
NOW = dt.date.today()
csv.field_size_limit(10 ** 7)


def label_for(code):
    if not code:
        return None
    if code in DENTAL_LABEL:
        return DENTAL_LABEL[code]
    if code.startswith("1223") or code == "122300000X":
        return "Dentistry (other)"
    if code.startswith("152W"):
        return "Optometry"
    return None


def latest_file_url():
    html = http_get(LISTING, retries=3).decode("utf-8", "replace")
    files = re.findall(r"NPPES_Data_Dissemination_[A-Za-z]+_\d{4}_V\d+\.zip", html)
    monthly = sorted(set(f for f in files if "Weekly" not in f))
    if not monthly:
        raise SystemExit("no monthly NPPES file found in listing")
    # newest by (year, month)
    months = {m: i for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"], 1)}

    def key(f):
        mo, yr = re.search(r"_([A-Za-z]+)_(\d{4})_", f).groups()
        return (int(yr), months.get(mo.lower(), 0))
    return BASE + max(monthly, key=key)


def existing_fresh():
    if not HTML.exists():
        return False
    txt = HTML.read_text(encoding="utf-8")
    m = re.search(re.escape(DATA_START) + r"(.*?)" + re.escape(DATA_END), txt, re.S)
    if not m or m.group(1).strip() in ("", "null"):
        return False
    import json
    try:
        d = json.loads(m.group(1))
    except ValueError:
        return False
    meta = d.get("_meta", {})
    if not d.get("providers"):
        return False
    try:
        gen = dt.datetime.strptime(meta["generated_at"], "%Y-%m-%dT%H:%M:%SZ").date()
    except (KeyError, ValueError):
        return False
    return (NOW - gen).days < SKIP_DAYS


def download(url):
    tmp = Path(tempfile.gettempdir()) / "nppes_full.zip"
    print("downloading", url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        total = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
            if total % (100 << 20) < (1 << 20):
                print("  ...%d MB" % (total >> 20))
    print("downloaded %d MB" % (tmp.stat().st_size >> 20))
    return tmp


def main_csv_name(zf):
    for n in zf.namelist():
        low = n.lower()
        if low.startswith("npidata_pfile") and low.endswith(".csv") and "fileheader" not in low:
            return n
    raise SystemExit("main npidata CSV not found in zip")


def parse_rows(row_iter):
    """row_iter yields CSV rows (lists); first is the header. Yields provider dicts."""
    header = next(row_iter)
    idx = {name: i for i, name in enumerate(header)}

    def col(row, name):
        i = idx.get(name)
        return row[i] if i is not None and i < len(row) else ""

    tax_cols = [("Healthcare Provider Taxonomy Code_%d" % k,
                 "Healthcare Provider Primary Taxonomy Switch_%d" % k) for k in range(1, 16)]

    for row in row_iter:
        # pick primary taxonomy (or first dental/optometry one present)
        primary, any_match = None, None
        for code_c, sw_c in tax_cols:
            code = col(row, code_c).strip()
            if not code:
                continue
            lab = label_for(code)
            if lab and any_match is None:
                any_match = (code, lab)
            if col(row, sw_c).strip().upper() == "Y" and label_for(code):
                primary = (code, lab)
                break
        chosen = primary or any_match
        if not chosen:
            continue
        state = col(row, "Provider Business Practice Location Address State Name").strip().upper()
        if state != "TX":
            continue
        org = col(row, "Provider Organization Name (Legal Business Name)").strip()
        name = org or (" ".join(x for x in [
            col(row, "Provider First Name").strip(),
            col(row, "Provider Last Name (Legal Name)").strip()] if x)).title()
        enum = col(row, "Provider Enumeration Date").strip()  # MM/DD/YYYY
        yr = enum[-4:] if len(enum) >= 4 and enum[-4:].isdigit() else ""
        tenure = NOW.year - int(yr) if yr else None
        yield {
            "npi": col(row, "NPI").strip(),
            "name": name, "cred": col(row, "Provider Credential Text").strip(),
            "specialty": chosen[1],
            "city": col(row, "Provider Business Practice Location Address City Name").strip().title(),
            "zip": col(row, "Provider Business Practice Location Address Postal Code").strip()[:5],
            "phone": col(row, "Provider Business Practice Location Address Telephone Number").strip(),
            "tenure": tenure,
            "solo": col(row, "Is Sole Proprietor").strip().upper() == "Y",
        }


def score(p):
    s = 40
    t = p.get("tenure")
    if t is not None:
        s += 25 if 5 <= t <= 25 else (5 if t < 3 else (8 if t > 35 else 15))
    if p.get("solo"):
        s += 20
    if p.get("phone"):
        s += 8
    if p.get("specialty") in ("Oral & Maxillofacial Surgery", "Orthodontics", "Periodontics"):
        s += 7
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
    return {
        "_meta": stamp("NPPES Data Dissemination (download.cms.gov, monthly bulk file)", {
            "providers": len(providers),
            "solo": sum(1 for p in providers if p["solo"]),
            "specialties": len(by_spec),
        }),
        "providers": providers,
        "by_specialty": [{"k": k, "n": v} for k, v in sorted(by_spec.items(), key=lambda x: -x[1])],
        "by_city": [{"k": k, "n": v} for k, v in sorted(by_city.items(), key=lambda x: -x[1])[:25]],
    }


def selftest():
    header = (["NPI", "Entity Type Code", "Provider Organization Name (Legal Business Name)",
               "Provider Last Name (Legal Name)", "Provider First Name", "Provider Credential Text",
               "Provider Business Practice Location Address City Name",
               "Provider Business Practice Location Address State Name",
               "Provider Business Practice Location Address Postal Code",
               "Provider Business Practice Location Address Telephone Number",
               "Provider Enumeration Date", "Is Sole Proprietor"]
              + ["Healthcare Provider Taxonomy Code_%d" % k for k in range(1, 16)]
              + ["Healthcare Provider Primary Taxonomy Switch_%d" % k for k in range(1, 16)])
    row = ["1234567890", "1", "", "DOE", "JANE", "DDS", "DALLAS", "TX", "75201-1234",
           "214-555-0100", "05/01/2009", "Y"] + ["1223X0400X"] + [""] * 14 + ["Y"] + [""] * 14
    non_tx = ["9", "1", "", "SMITH", "AL", "OD", "RENO", "NV", "89501", "", "01/01/2015", "N"] \
        + ["152W00000X"] + [""] * 14 + ["Y"] + [""] * 14
    provs = list(parse_rows(iter([header, row, non_tx])))
    assert len(provs) == 1, provs                          # NV row filtered out
    p = provs[0]
    p["score"] = score(p)
    assert p["specialty"] == "Orthodontics" and p["solo"] and p["city"] == "Dallas"
    assert p["tenure"] == NOW.year - 2009 and p["score"] >= 90, p
    d = build([p])
    assert d["_meta"]["providers"] == 1 and d["by_specialty"][0]["k"] == "Orthodontics"
    print("selftest OK:", {k: p[k] for k in ("name", "specialty", "city", "tenure", "solo", "score")})


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    if "--force" not in sys.argv and existing_fresh():
        print("dental data is fresh (< %d days) - skipping bulk download." % SKIP_DAYS)
        return
    url = latest_file_url()
    zpath = download(url)
    try:
        with zipfile.ZipFile(zpath) as zf:
            csv_name = main_csv_name(zf)
            print("parsing", csv_name)
            with zf.open(csv_name) as raw:
                reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline=""))
                providers = list(parse_rows(reader))
    finally:
        try:
            zpath.unlink()
        except OSError:
            pass
    print("TX dental/optometry providers:", len(providers))
    data = build(providers)
    size = inject_data(HTML, data)
    print("injected %.0f KB into %s (providers=%d, solo=%d)"
          % (size / 1024, HTML.name, data["_meta"]["providers"], data["_meta"]["solo"]))


if __name__ == "__main__":
    main()
