"""
Ranger Dashboards - shared refresh utilities.

Canonical TX footprint (counties + FIPS), HTTP helpers with retry, and a
marker-based data-injection helper so each refresh script can rewrite its
self-contained dashboard HTML in place. Kept dependency-free (stdlib only) to
match the rest of the pipeline and run cleanly inside GitHub Actions.
"""
import json
import time
import re
import datetime as dt
import urllib.request
import urllib.error
from pathlib import Path

USER_AGENT = "ranger-dashboards/1.0 (+https://nbsimonetti.github.io/ranger-dashboards)"

# 33-county TX footprint = the 32-county CRE footprint (mirrors
# cre/cre-dashboard-tx.html) plus Harris. name -> 5-digit state+county FIPS.
FOOTPRINT = {
    "Angelina": "48003", "Bell": "48027", "Bexar": "48029", "Brazoria": "48039",
    "Brazos": "48041", "Caldwell": "48055", "Cameron": "48061", "Chambers": "48071",
    "Coryell": "48099", "Dallas": "48113", "Ector": "48135", "Fort Bend": "48157",
    "Galveston": "48167", "Grayson": "48181", "Gregg": "48183", "Hardin": "48199",
    "Harris": "48201", "Jefferson": "48245", "Johnson": "48251", "Kaufman": "48257",
    "Kerr": "48265", "Liberty": "48291", "Nueces": "48355", "Panola": "48365",
    "Rusk": "48401", "Tarrant": "48439", "Taylor": "48441", "Titus": "48449",
    "Travis": "48453", "Victoria": "48469", "Wichita": "48485", "Williamson": "48491",
    "Wise": "48497",
}

# Priority-MSA core counties named in the RLSB business plan. Some sit outside
# the CRE footprint above (Midland, Smith/Tyler, Tom Green/San Angelo) and are
# useful for market-intelligence dashboards that look at where to *grow*.
PRIORITY_MSA = {
    "Midland": "48329", "Ector": "48135", "Taylor": "48441",
    "Smith": "48423", "Tom Green": "48451", "Dallas": "48113", "Tarrant": "48439",
}

FOOTPRINT_UPPER = {name.upper(): fips for name, fips in FOOTPRINT.items()}
FOOTPRINT_FIPS = set(FOOTPRINT.values())


def in_footprint(county_name):
    if not county_name:
        return False
    return county_name.strip().upper() in FOOTPRINT_UPPER


def http_get(url, headers=None, timeout=45, retries=4, backoff=2.0):
    """GET raw bytes with a shared UA and simple exponential-ish backoff."""
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise last


def http_get_json(url, headers=None, timeout=45, retries=4):
    return json.loads(http_get(url, headers=headers, timeout=timeout, retries=retries))


DATA_START = "/*__DATA_START__*/"
DATA_END = "/*__DATA_END__*/"


def inject_data(html_path, data_obj):
    """Replace the JSON between the DATA markers in a self-contained dashboard."""
    path = Path(html_path)
    html = path.read_text(encoding="utf-8")
    payload = json.dumps(data_obj, separators=(",", ":"), ensure_ascii=False)
    pattern = re.compile(re.escape(DATA_START) + r".*?" + re.escape(DATA_END), re.S)
    if not pattern.search(html):
        raise SystemExit("data markers (%s ... %s) not found in %s"
                         % (DATA_START, DATA_END, html_path))
    path.write_text(pattern.sub(DATA_START + payload + DATA_END, html, count=1),
                    encoding="utf-8")
    return len(payload)


def stamp(source, extra=None):
    """Standard freshness/provenance block embedded with every dashboard's data."""
    block = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
    }
    if extra:
        block.update(extra)
    return block
