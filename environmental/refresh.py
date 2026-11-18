"""
environmental/refresh.py -- build the data behind the CRE Environmental Screening dashboard.

Every regulatory list is pulled from its public source, every point is assigned to
the Texas county whose boundary contains it, and the results are written as one
small JSON shard per county so the page only loads the counties near a subject:

  data/index.json          per-source vintage, counts, status; county bounding boxes
  data/sites/<fips>.json   listed environmental sites (compact arrays)
  data/parcels/<fips>.json CRE parcels with location, use and SBA-loan context
  data/parcels/ids.json    parcel id -> county FIPS (for pipeline / ?parcel= links)
  data/cache/*.json        geocode cache for dry cleaner registrations (address only)

Dense layers (1.4M Railroad Commission well locations, pipelines, FEMA flood zones,
wetlands) are queried live from the page, so they are not built here.

Failure handling (weekly CI glob runs every */refresh.py): each source runs inside
its own try/except. A source that fails keeps the records it had in the previous
shards and is marked stale in index.json; the script still exits 0.

Run:  python environmental/refresh.py            all sources
      python environmental/refresh.py --only tceq,rrc
      python environmental/refresh.py --parcels  rebuild CRE parcel shards too
      python environmental/refresh.py --selftest offline geometry/normalisation checks
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "_geocoding"))
from footprint import http_get, http_get_json, stamp  # noqa: E402

DATA = HERE / "data"
SITES = DATA / "sites"
PARCELS = DATA / "parcels"
CACHE = DATA / "cache"
GEOJSON = ROOT / "shared" / "tx-counties.geojson"
CRE_HTML = ROOT / "cre" / "cre-dashboard-tx.html"
CRE_COORDS = ROOT / "cre" / "cre-coords-tx.json"
SBA_LOANS = ROOT / "loan-maturity" / "loans_statewide.json"

# Record layout in data/sites/<fips>.json -> "r": [[...], ...]
#   0 list code   1 lat   2 lng   3 name   4 address   5 city
#   6 record id   7 status   8 link kind   9 link id   10 detail
SITE_FIELDS = ["list", "lat", "lng", "name", "addr", "city", "rid", "status", "lk", "lid", "detail"]

# Which source produces which list codes (used to carry records forward on failure)
SOURCE_LISTS = {
    "epa_frs": ["npl", "npl_del", "sems", "sems_arch", "rcra_tsd", "rcra_gen", "brown_epa", "tri", "enf",
                "npdes_ind"],
    "tceq_gis": ["sf_state", "lpst", "pst", "vcp", "brown_tceq", "ihwca", "iop", "dcrp", "landfill", "msd"],
    "tceq_lpst_status": [],
    "tceq_drycleaners": ["dc_reg"],
    "rrc": ["rrc_orphan", "rrc_inj", "rrc_disp", "rrc_ocp", "rrc_vcp", "rrc_brown", "rrc_cwds"],
}

TCEQ = "https://gisweb.tceq.texas.gov/arcgis/rest/services/Public"
RRC = "https://gis.rrc.texas.gov/server/rest/services/rrc_public/RRC_Public_Viewer_Srvs/MapServer"
FRS_ZIP = "https://ordsext.epa.gov/FLA/www3/state_files/state_combined_tx.zip"
SOCRATA = "https://data.texas.gov/resource/"

SOURCE_TITLES = {
    "epa_frs": ("EPA Facility Registry Service, Texas combined state file", FRS_ZIP),
    "tceq_gis": ("TCEQ Remediation and Petroleum Storage Tank GIS layers", TCEQ),
    "tceq_lpst_status": ("TCEQ Leaking Petroleum Storage Tank case list (Texas Open Data Portal)",
                         SOCRATA + "hedz-nn4q"),
    "tceq_drycleaners": ("TCEQ Operating and Historical Dry Cleaner Registrations (Texas Open Data Portal)",
                         SOCRATA + "qfph-9bnd"),
    "rrc": ("Railroad Commission of Texas Public GIS Viewer services", RRC),
    "cre_parcels": ("Ranger Bank CRE Prospecting dashboard parcel data (county appraisal district rolls)", ""),
}

PAUSE = 0.6  # seconds between paged requests to one host


def log(msg):
    print(msg, flush=True)


# --------------------------------------------------------------- geometry ----
class Counties:
    """Point-in-county lookup against shared/tx-counties.geojson (ray casting)."""

    def __init__(self, path=GEOJSON):
        g = json.loads(Path(path).read_text(encoding="utf-8"))
        self.items = []
        for f in g["features"]:
            p = f["properties"]
            geom = f["geometry"]
            polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
            rings = [poly for poly in polys]
            xs = [pt[0] for poly in polys for ring in poly for pt in ring]
            ys = [pt[1] for poly in polys for ring in poly for pt in ring]
            self.items.append({
                "fips": p["fips"], "name": p["name"], "polys": rings,
                "bbox": (min(ys), min(xs), max(ys), max(xs)),
            })
        self.by_fips = {c["fips"]: c for c in self.items}
        self.by_name = {c["name"].upper(): c["fips"] for c in self.items}
        # quarter-degree grid of candidate counties, so a lookup tests a handful of
        # polygons instead of all 254
        self.grid = defaultdict(list)
        for c in self.items:
            b = c["bbox"]
            for gy in range(int(math.floor(b[0] * 4)), int(math.floor(b[2] * 4)) + 1):
                for gx in range(int(math.floor(b[1] * 4)), int(math.floor(b[3] * 4)) + 1):
                    self.grid[(gy, gx)].append(c)

    @staticmethod
    def _in_ring(x, y, ring):
        inside = False
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i][0], ring[i][1]
            xj, yj = ring[j][0], ring[j][1]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
                inside = not inside
            j = i
        return inside

    def contains(self, c, lat, lng):
        b = c["bbox"]
        if not (b[0] <= lat <= b[2] and b[1] <= lng <= b[3]):
            return False
        for poly in c["polys"]:
            if self._in_ring(lng, lat, poly[0]) and not any(self._in_ring(lng, lat, h) for h in poly[1:]):
                return True
        return False

    def locate(self, lat, lng, hint_fips=None):
        if lat is None or lng is None:
            return None
        if hint_fips and hint_fips in self.by_fips and self.contains(self.by_fips[hint_fips], lat, lng):
            return hint_fips
        for c in self.grid.get((int(math.floor(lat * 4)), int(math.floor(lng * 4))), []):
            if self.contains(c, lat, lng):
                return c["fips"]
        return None


def fnum(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def clean(s, n=90):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s[:n]


def site(list_code, lat, lng, name, addr, city, rid, status, lk, lid, detail=""):
    return [list_code, round(lat, 5), round(lng, 5), clean(name, 70), clean(addr, 60),
            clean(city, 30), str(rid or ""), status or "", lk or "", str(lid or ""), clean(detail, 80)]


# ------------------------------------------------------------ ArcGIS paging ----
def arcgis_all(layer_url, out_fields="*", page=1000, geometry=True, where="1=1"):
    """Every feature of an ArcGIS REST layer, paged by OBJECTID order."""
    rows, offset = [], 0
    while True:
        q = urllib.parse.urlencode({
            "where": where, "outFields": out_fields, "returnGeometry": "true" if geometry else "false",
            "outSR": 4326, "f": "json", "resultOffset": offset, "resultRecordCount": page,
            "orderByFields": "OBJECTID",
        })
        d = http_get_json(layer_url + "/query?" + q, timeout=120)
        if "error" in d:
            raise RuntimeError("%s: %s" % (layer_url, d["error"]))
        feats = d.get("features", [])
        rows.extend(feats)
        if not feats or not d.get("exceededTransferLimit") and len(feats) < page:
            break
        offset += len(feats)
        time.sleep(PAUSE)
    return rows


def feat_latlng(f, latf=None, lngf=None):
    a = f.get("attributes", {})
    lat = fnum(a.get(latf)) if latf else None
    lng = fnum(a.get(lngf)) if lngf else None
    g = f.get("geometry") or {}
    if (lat is None or lng is None) and "x" in g:
        lat, lng = fnum(g.get("y")), fnum(g.get("x"))
    if lat is not None and lng is not None and lng > 0:  # some layers store W longitude as positive
        lng = -lng
    return lat, lng


# ------------------------------------------------------------- TCEQ (GIS) ----
def src_tceq_gis(ctx):
    out = []
    lpst_status = ctx.get("lpst_status", {})
    specs = [
        # layer, list code, id field, lat, lng, name, addr, city
        ("Superfund", "sf_state", "SF_ID", "LAT_DD", "LONG_DD", "SITE_NAME", "PHYS_ADDR", "CITY"),
        ("LPST", "lpst", "LPST_ID", "LAT_DD", "LONG_DD", "SITE_NAME", "PHYS_ADDR", "CITY"),
        ("VCP", "vcp", "VCP_ID", "LAT_DD", "LONG_DD", "SITE_NAME", "PHYS_ADDR", "CITY"),
        ("Brownfield", "brown_tceq", "BSA_ID", "LAT_DD", "LONG_DD", "SITE_NAME", "PHYS_ADDR", "CITY"),
        ("IHWCA", "ihwca", "IHWCA_ID", "LAT_DD", "LONG_DD", "SITE_NAME", "PHYS_ADDR", "CITY"),
        ("IOP", "iop", "IOP_ID", "LAT_DD", "LONG_DD", "SITE_NAME", "PHYS_ADDR", "CITY"),
        ("DryCleaner", "dcrp", "DCRP_ID", "LAT_DD", "LONG_DD", "SITE_NAME", "PHYS_ADDR", "CITY"),
        ("MSD_Points", "msd", "MSD_ID", "LAT_DD", "LONG_DD", "SITE_NAME", "PHYS_ADDR", "CITY"),
    ]
    counts = {}
    for layer, code, idf, latf, lngf, nf, af, cf in specs:
        feats = arcgis_all("%s/%s/MapServer/0" % (TCEQ, layer))
        n = 0
        for f in feats:
            a = f["attributes"]
            lat, lng = feat_latlng(f, latf, lngf)
            if lat is None:
                continue
            status, detail = "", ""
            if code == "lpst":
                st = lpst_status.get(str(a.get("LPST_ID") or "").lstrip("0"))
                if st:
                    status = "closed" if st.get("closure_date") else "open"
                    rep = (st.get("reported_date") or "")[:10]
                    clo = (st.get("closure_date") or "")[:10]
                    detail = ("Reported %s" % rep if rep else "") + ("; closed %s" % clo if clo else "")
            elif code == "sf_state":
                detail = "EPA ID %s" % a["EPA_TXID"] if a.get("EPA_TXID") else ""
            if code == "sf_state" and a.get("WEB_URL"):
                lk, lid = "url", a["WEB_URL"]
            elif a.get("RN"):
                lk, lid = "rn", a["RN"]
            else:
                lk, lid = "", ""
            out.append(site(code, lat, lng, a.get(nf), a.get(af), a.get(cf), a.get(idf), status, lk, lid, detail))
            n += 1
        counts[code] = n
        log("    TCEQ %-11s %6d" % (layer, n))
        time.sleep(PAUSE)

    # Registered petroleum storage tanks
    feats = arcgis_all("%s/PST/MapServer/0" % TCEQ, page=1000)
    n = 0
    for f in feats:
        a = f["attributes"]
        lat, lng = feat_latlng(f, "lat_dd", "long_dd")
        if lat is None:
            continue
        act = int(fnum(a.get("NUM_ACTIVE_UST")) or 0)
        status = "active" if act > 0 else "inactive"
        detail = "%d active tank%s" % (act, "" if act == 1 else "s")
        if a.get("UST_TYPE"):
            detail += "; " + str(a["UST_TYPE"])
        out.append(site("pst", lat, lng, a.get("FACILITY_NAME"), a.get("ADDRESS"), a.get("CITY"),
                        a.get("pst_id"), status, "rn" if a.get("rn") else "", a.get("rn"), detail))
        n += 1
    counts["pst"] = n
    log("    TCEQ %-11s %6d" % ("PST", n))

    # Active municipal solid waste landfills
    feats = arcgis_all("%s/Landfills/MapServer/0" % TCEQ)
    n = 0
    for f in feats:
        a = f["attributes"]
        lat, lng = feat_latlng(f, "LATITUDE", "LONGITUDE")
        if lat is None:
            continue
        out.append(site("landfill", lat, lng, a.get("FACILITY_N"), a.get("ADDRESS"), "",
                        a.get("PERMIT_NUM"), "active", "", "", a.get("LANDFILL_T") or ""))
        n += 1
    counts["landfill"] = n
    log("    TCEQ %-11s %6d" % ("Landfills", n))
    return out, {"counts": counts}


def src_tceq_lpst_status(ctx):
    """LPST case reported/closure dates, keyed by LPST id (joins to the GIS points)."""
    rows, off = [], 0
    while True:
        q = urllib.parse.urlencode({"$select": "lpst_id,reported_date,closure_date", "$limit": 50000,
                                    "$offset": off, "$order": "lpst_id"})
        page = http_get_json(SOCRATA + "hedz-nn4q.json?" + q, timeout=120)
        rows.extend(page)
        if len(page) < 50000:
            break
        off += 50000
        time.sleep(PAUSE)
    status = {}
    for r in rows:
        k = str(r.get("lpst_id") or "").lstrip("0")
        if k:
            status[k] = {"reported_date": r.get("reported_date"), "closure_date": r.get("closure_date")}
    ctx["lpst_status"] = status
    open_n = sum(1 for v in status.values() if not v["closure_date"])
    log("    LPST cases %d (open %d)" % (len(status), open_n))
    return [], {"counts": {"lpst_cases": len(status), "lpst_open": open_n}}


# ----------------------------------------------------------- dry cleaners ----
def src_tceq_drycleaners(ctx, geocode_limit=None):
    """Operating and historical dry cleaner registrations. These carry an address
    only, so each unique address is geocoded once with the US Census batch
    geocoder and cached in data/cache/drycleaner-geocodes.json."""
    from census_geocoder import geocode_batches
    recs = {}
    for ds, era in (("qfph-9bnd", "operating"), ("xcc6-2a52", "historical")):
        off = 0
        while True:
            q = urllib.parse.urlencode({
                "$select": "registration_id,regulated_entity_number_rn,regulated_entity_name,location_type,"
                           "location_address,location_city,location_zip_code,status_year",
                "$limit": 50000, "$offset": off, "$order": "registration_id"})
            page = http_get_json(SOCRATA + ds + ".json?" + q, timeout=180)
            for r in page:
                rid = r.get("registration_id")
                if not rid or not r.get("location_address"):
                    continue
                prev = recs.get(rid)
                yr = r.get("status_year") or ""
                if prev and prev["era"] == "operating" and era == "historical":
                    continue
                if prev and era == prev["era"] and yr <= prev["yr"]:
                    continue
                recs[rid] = {
                    "rid": rid, "rn": r.get("regulated_entity_number_rn") or "",
                    "name": r.get("regulated_entity_name") or "", "type": r.get("location_type") or "",
                    "street": r.get("location_address"), "city": r.get("location_city") or "",
                    "zip": (r.get("location_zip_code") or "")[:5], "state": "TX", "era": era, "yr": yr,
                }
            if len(page) < 50000:
                break
            off += 50000
            time.sleep(PAUSE)
    log("    dry cleaner registrations %d" % len(recs))
    cache_path = CACHE / "drycleaner-geocodes.json"
    CACHE.mkdir(parents=True, exist_ok=True)
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    todo = [r for r in recs.values() if r["rid"] not in cache]
    if geocode_limit is not None:
        todo = todo[:geocode_limit]
    if todo:
        log("    geocoding %d new dry cleaner addresses (US Census batch geocoder)" % len(todo))
        tmp = Path(tempfile.mkdtemp()) / "dc.json"
        geocode_batches(todo, tmp, id_key="rid", resume=False, label="dry cleaners")
        fresh = json.loads(tmp.read_text(encoding="utf-8")) if tmp.exists() else {}
        cache.update(fresh)
        cache_path.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")
        shutil.rmtree(tmp.parent, ignore_errors=True)
    out, matched = [], 0
    for r in recs.values():
        g = cache.get(r["rid"]) or {}
        if not g.get("matched") or g.get("lat") is None:
            continue
        matched += 1
        detail = ("%s, %s" % (r["type"].title().replace(" Registration", ""), r["era"])) + \
                 (" (last listed %s)" % r["yr"] if r["era"] == "historical" and r["yr"] else "")
        status = "active" if r["era"] == "operating" else "inactive"
        out.append(site("dc_reg", float(g["lat"]), float(g["lng"]), r["name"], r["street"], r["city"],
                        r["rid"], status, "rn" if r["rn"] else "", r["rn"], detail))
    log("    dry cleaner registrations geocoded %d of %d" % (matched, len(recs)))
    return out, {"counts": {"dc_reg": matched, "dc_reg_total": len(recs)}}


# ------------------------------------------------------------- EPA (FRS) ----
FRS_MAP = {
    # (program, interest type) -> list code; status rules applied below
    ("SEMS", "SUPERFUND NPL"): "npl",
    ("SEMS", "SUPERFUND (NON-NPL)"): "sems",
    ("RCRAINFO", "TSD"): "rcra_tsd",
    ("RCRAINFO", "LQG"): "rcra_gen",
    ("RCRAINFO", "SQG"): "rcra_gen",
    ("RCRAINFO", "VSQG"): "rcra_gen",
    ("ACRES", "BROWNFIELDS PROPERTY"): "brown_epa",
    ("TRIS", "TRI REPORTER"): "tri",
    ("ICIS", "FORMAL ENFORCEMENT ACTION"): "enf",
    ("NPDES", "STORM WATER INDUSTRIAL"): "npdes_ind",
}


def src_epa_frs(ctx):
    if ctx.get("frs_zip"):
        raw = Path(ctx["frs_zip"]).read_bytes()
        log("    using local copy %s" % Path(ctx["frs_zip"]).name)
    else:
        raw = http_get(FRS_ZIP, timeout=600, retries=3)
    z = zipfile.ZipFile(io.BytesIO(raw))

    def rows(name):
        return csv.DictReader(io.TextIOWrapper(z.open(name), encoding="latin-1"))

    want = defaultdict(list)  # registry id -> [(code, pgm id, status, detail)]
    for r in rows("TX_ENVIRONMENTAL_INTEREST_FILE.CSV"):
        code = FRS_MAP.get((r["PGM_SYS_ACRNM"], r["INTEREST_TYPE"]))
        if not code:
            continue
        st = (r.get("ACTIVE_STATUS") or "").upper()
        detail = r["INTEREST_TYPE"].title()
        if code == "npl":
            if "DELETED" in st:
                code, detail = "npl_del", "Deleted from the final NPL"
            elif "PROPOSED" in st:
                detail = "Proposed for the NPL"
            else:
                detail = "Final NPL"
        elif code == "sems":
            if st:
                detail = st.capitalize()
            else:
                code, detail = "sems_arch", "No current SEMS status (treated as archived)"
        elif code == "npdes_ind":
            detail = "Industrial stormwater permit" + (" (%s)" % st.lower() if st else "")
        elif code == "rcra_gen":
            detail = {"LQG": "Large quantity generator", "SQG": "Small quantity generator",
                      "VSQG": "Very small quantity generator"}.get(r["INTEREST_TYPE"], detail)
        if code in ("npl", "sems"):
            status = "active"
        elif code in ("npl_del", "sems_arch"):
            status = "inactive" if code == "npl_del" else ""
        elif st:
            # permits and registrations: terminated or expired is inactive; effective,
            # active and administratively continued permits are still in force
            status = "inactive" if re.search(r"TERMINAT|EXPIR|INACTIVE|RETIRE|CLOSED|DELETED|WITHDRAW", st) \
                else "active"
        else:
            status = ""
        if code == "enf":
            end = r.get("END_DATE") or ""
            detail = "Formal enforcement action" + (" (ended %s)" % end if end else "")
            # the state file rarely carries an end date, so an action with none is shown
            # as listed rather than claimed to be active; "open" is for cleanup cases
            status = "inactive" if end else ""
        want[r["REGISTRY_ID"]].append((code, r["PGM_SYS_ID"], status, detail))
    out, missing = [], 0
    for r in rows("TX_FACILITY_FILE.CSV"):
        hits = want.get(r["REGISTRY_ID"])
        if not hits:
            continue
        lat, lng = fnum(r.get("LATITUDE83")), fnum(r.get("LONGITUDE83"))
        if lat is None or lng is None:
            missing += 1
            continue
        seen = set()
        for code, pid, status, detail in hits:
            key = (code, pid)
            if key in seen:
                continue
            seen.add(key)
            if code in ("npl", "npl_del", "sems", "sems_arch"):
                lk, lid = "frs", r["REGISTRY_ID"]   # FRS detail report lists the SEMS record
            else:
                lk, lid = "echo", r["REGISTRY_ID"]
            out.append(site(code, lat, lng, r.get("PRIMARY_NAME"), r.get("LOCATION_ADDRESS"),
                            r.get("CITY_NAME"), pid, status, lk, lid, detail))
    c = Counter(s[0] for s in out)
    log("    EPA FRS " + ", ".join("%s %d" % kv for kv in sorted(c.items())) + " (no coordinates: %d)" % missing)
    return out, {"counts": dict(c), "no_coordinates": missing}


# ------------------------------------------------------------------- RRC ----
def src_rrc(ctx):
    out, counts = [], {}
    for lid, code, label in ((2, "rrc_orphan", "Orphan well"), (4, "rrc_inj", "Injection/disposal well"),
                             (3, "rrc_disp", "Commercial disposal well")):
        feats = arcgis_all("%s/%d" % (RRC, lid), out_fields="OBJECTID,API")
        n = 0
        for f in feats:
            lat, lng = feat_latlng(f)
            if lat is None:
                continue
            api = (f["attributes"].get("API") or "")
            out.append(site(code, lat, lng, label + (" API " + api if api else ""), "", "", api,
                            "", "rrcapi" if api else "", api, label))
            n += 1
        counts[code] = n
        log("    RRC %-26s %6d" % (label, n))
        time.sleep(PAUSE)
    feats = arcgis_all("%s/33" % RRC)
    for f in feats:
        a = f["attributes"]
        lat, lng = feat_latlng(f, "LATITUDE", "LONGITUDE")
        if lat is None:
            continue
        st = (a.get("STATUS") or "").strip()
        out.append(site("rrc_ocp", lat, lng, a.get("SITE_NAME"), "", "", a.get("OCP_ID"),
                        "closed" if re.search(r"CLOS|COMPLET", st, re.I) else ("open" if st else ""),
                        "", "", "Operator Cleanup Program" + (": " + st if st else "")))
    counts["rrc_ocp"] = sum(1 for s in out if s[0] == "rrc_ocp")
    for lid, code, prog in ((34, "rrc_vcp", "RRC Voluntary Cleanup Program"),
                            (35, "rrc_brown", "RRC Brownfield Response Program")):
        for f in arcgis_all("%s/%d" % (RRC, lid)):
            a = f["attributes"]
            lat, lng = feat_latlng(f, "LATITUDE", "LONGITUDE")
            if lat is None:
                continue
            st = (a.get("STATUS") or "").strip()
            out.append(site(code, lat, lng, a.get("SITENAME"), "", "", a.get("SITENUM"),
                            "closed" if re.search(r"CLOS|COMPLET|CERTIF", st, re.I) else ("open" if st else ""),
                            "", "", prog + (": " + st if st else "") +
                            ("; " + a["COC"] if a.get("COC") else "")))
        counts[code] = sum(1 for s in out if s[0] == code)
    for f in arcgis_all("%s/36" % RRC):
        a = f["attributes"]
        lat, lng = feat_latlng(f, "LATITUDE", "LONGITUDE")
        if lat is None:
            continue
        out.append(site("rrc_cwds", lat, lng, a.get("LEASE_OR_FACILITY_NAME") or a.get("OPERATOR_NAME"),
                        "", "", a.get("PERMIT_NO"), "active", "url" if a.get("PERMIT_URL") else "",
                        a.get("PERMIT_URL") or "", "Commercial waste disposal: %s" % (a.get("PERMIT_TYPE") or "")))
    counts["rrc_cwds"] = sum(1 for s in out if s[0] == "rrc_cwds")
    log("    RRC cleanup/disposal sites ocp %d, vcp %d, brownfield %d, commercial waste %d"
        % (counts["rrc_ocp"], counts["rrc_vcp"], counts["rrc_brown"], counts["rrc_cwds"]))
    return out, {"counts": counts}


# --------------------------------------------------------------- parcels ----
SUFFIX = {"STREET": "ST", "AVENUE": "AVE", "AV": "AVE", "ROAD": "RD", "DRIVE": "DR", "BOULEVARD": "BLVD",
          "HIGHWAY": "HWY", "LANE": "LN", "PARKWAY": "PKWY", "FREEWAY": "FWY", "EXPRESSWAY": "EXPY",
          "PLACE": "PL", "COURT": "CT", "CIRCLE": "CIR", "TRAIL": "TRL", "NORTH": "N", "SOUTH": "S",
          "EAST": "E", "WEST": "W", "FARM TO MARKET": "FM", "COUNTY ROAD": "CR", "INTERSTATE": "IH",
          "I-": "IH ", "IH-": "IH "}


def norm_addr(s):
    s = (s or "").upper()
    s = re.sub(r"\b(STE|SUITE|UNIT|APT|BLDG|#)\s*\S+.*$", "", s)
    s = re.sub(r"[.,]", " ", s)
    for k, v in SUFFIX.items():
        s = re.sub(r"\b%s\b" % re.escape(k), v, s) if not k.endswith("-") else s.replace(k, v)
    return re.sub(r"\s+", " ", s).strip()


# SBA SOP 50 10 8.1 Appendix 6 prefixes (the page carries the labels). 447 is the
# pre-2022 NAICS code for gasoline stations (457 since 2022); SBA loans in the FOIA
# file carry the code in force when they were approved.
SBA_SENSITIVE = ["211", "212", "213", "237", "311", "312", "313", "314", "316", "321", "322", "323", "324",
                 "325", "326", "327", "331", "332", "333", "334", "335", "336", "337", "339", "42311",
                 "42314", "4235", "42393", "4246", "4247", "441", "457", "447", "481", "482", "484", "486",
                 "488", "53212", "53241", "53249", "54138", "56171", "562", "6221", "713990", "71391",
                 "71392", "71393", "7212", "8111", "8112", "8113", "8122", "8123", "812921"]


def sba_sensitive(naics):
    n = str(naics or "")
    for p in SBA_SENSITIVE:
        if n.startswith(p):
            if p == "312" and n.startswith("31212"):
                continue
            return p
    return None


# CRE sub-types (from the CRE dashboard's getSubtype) that name a Section 8.3 trigger
# use, and those that only call for heightened diligence (industrial and warehouse
# collateral that is not itself a listed use).
TRIGGER_SUBTYPES = {"Manufacturing/Industrial", "Light Industrial/Flex", "Gas/Convenience/Auto",
                    "Auto Service/Repair", "Auto Dealership", "Airport/Aviation"}
HEIGHTEN_SUBTYPES = {"Warehouse/Distribution", "Cold Storage", "Energy/Utility"}

# Use words in the appraisal legal description or owner name. Kept to phrases that
# describe a use; brand names are left to the CRE sub-type rule.
USE_RULES = [
    ("fuel", r"\b(GAS(OLINE)? (SERVICE )?STATION|SERVICE STATION|FILLING STATION|FUEL|TRUCK STOP|"
             r"TRAVEL (CENTER|PLAZA)|MINI[- ]?MART|CONVENIENCE STORE|CONV STORE|PETROLEUM|BULK PLANT|TANK FARM)\b"),
    ("auto", r"\b(AUTO(MOTIVE)? (REPAIR|SERVICE|BODY)|BODY SHOP|AUTO SALVAGE|SALVAGE YARD|JUNK ?YARD|"
             r"WRECKING YARD|QUICK LUBE|OIL CHANGE|LUBE CENTER|TRANSMISSION SHOP|MUFFLER|TIRE (SHOP|STORE|CENTER))\b"),
    ("dryclean", r"\b(DRY ?CLEAN\w*|CLEANERS)\b"),
    ("industrial", r"\b(MANUFACTUR\w*|FACTORY|FOUNDRY|MACHINE SHOP|METAL (PLATING|FINISHING)|PLATING|"
                   r"FABRICAT\w*|REFINERY|CHEMICAL|PLASTICS|PRINTING PLANT|SCRAP (METAL|YARD)|RECYCLING)\b"),
    ("agchem", r"\b(FERTILIZER|PESTICIDE|AG(RICULTURAL)? CHEMICAL|CROP DUST\w*|AERIAL APPLICAT\w*|"
               r"GRAIN ELEVATOR|COTTON GIN|FEED ?LOT)\b(?! (ADD|ADDN|ADDITION|SUBD|ESTATES|RD|ROAD|ST|DR|LN|LLC)\b)"),
]
USE_RX = [(k, re.compile(rx)) for k, rx in USE_RULES]


def cre_parcels_and_subtypes():
    html = CRE_HTML.read_text(encoding="utf-8")
    m = re.search(r"^var ALL=(\[.*\]);?\s*$", html, re.M)
    rows = json.loads(m.group(1))
    i = html.index("function getSubtype(p){")
    depth, j = 0, i
    while True:
        ch = html[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    fn = html[i:j + 1]
    tmp = Path(tempfile.mkdtemp())
    (tmp / "in.json").write_text(json.dumps([{"cd": r.get("cd"), "legal": r.get("legal"),
                                               "owner": r.get("owner")} for r in rows]), encoding="utf-8")
    (tmp / "run.js").write_text(
        fn + "\nconst fs=require('fs');const a=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));"
        "fs.writeFileSync(process.argv[3],JSON.stringify(a.map(getSubtype)));\n", encoding="utf-8")
    subprocess.run(["node", str(tmp / "run.js"), str(tmp / "in.json"), str(tmp / "out.json")],
                   check=True, timeout=300)
    subs = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
    shutil.rmtree(tmp, ignore_errors=True)
    return rows, subs, hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]


def build_parcels(counties):
    rows, subs, cre_hash = cre_parcels_and_subtypes()
    coords = json.loads(CRE_COORDS.read_text(encoding="utf-8"))
    sba = defaultdict(list)
    if SBA_LOANS.exists():
        for ln in json.loads(SBA_LOANS.read_text(encoding="utf-8"))["loans"]:
            fips = counties.by_name.get((ln.get("county") or "").upper())
            a = norm_addr(ln.get("borrower_address"))
            if fips and a:
                sba[(fips, a)].append(ln)
    shards = defaultdict(list)
    ids = {}
    stats = Counter()
    for r, sub in zip(rows, subs):
        fips = counties.by_name.get((r.get("county") or "").upper())
        if not fips:
            stats["no_county"] += 1
            continue
        c = coords.get(r["id"]) or {}
        lat = lng = None
        if c.get("matched") and c.get("lat") is not None:
            la, lo = float(c["lat"]), float(c["lng"])
            # parcel ids repeat across counties, so a coordinate is kept only when it
            # falls inside the parcel's own county
            if counties.contains(counties.by_fips[fips], la, lo):
                lat, lng = round(la, 5), round(lo, 5)
                stats["located"] += 1
            else:
                stats["coord_outside_county"] += 1
        else:
            stats["no_coord"] += 1
        text = " ".join([r.get("legal") or "", r.get("owner") or ""]).upper()
        uses = [k for k, rx in USE_RX if rx.search(text)]
        if sub in TRIGGER_SUBTYPES:
            uses.append("sub")
        elif sub in HEIGHTEN_SUBTYPES:
            uses.append("subh")
        if r.get("cd") == "F2":
            uses.append("f2")
        loans = []
        for ln in sba.get((fips, norm_addr(r.get("addr"))), [])[:4]:
            p = sba_sensitive(ln.get("naics_code"))
            loans.append([str(ln.get("naics_code") or ""), clean(ln.get("naics_description"), 50),
                          clean(ln.get("borrower"), 50), p or "", ln.get("source", "")])
        if loans:
            stats["sba_match"] += 1
        for u in uses:
            stats["use_" + u] += 1
        shards[fips].append([r["id"], lat, lng, clean(r.get("addr"), 50), clean(r.get("city"), 25),
                             r.get("cd") or "", sub or "", ",".join(sorted(set(uses))), clean(r.get("owner"), 50),
                             clean(r.get("legal"), 90), r.get("val"), r.get("yr"), loans])
        ids.setdefault(r["id"], []).append(fips)
    PARCELS.mkdir(parents=True, exist_ok=True)
    for old in PARCELS.glob("48*.json"):
        if old.stem not in shards:
            old.unlink()
    for fips, recs in shards.items():
        (PARCELS / ("%s.json" % fips)).write_text(json.dumps({"r": recs}, separators=(",", ":")), encoding="utf-8")
    (PARCELS / "ids.json").write_text(json.dumps({k: v if len(v) > 1 else v[0] for k, v in ids.items()},
                                                 separators=(",", ":")), encoding="utf-8")
    log("    CRE parcels %d in %d counties; %s" % (sum(len(v) for v in shards.values()), len(shards),
                                                   ", ".join("%s %d" % kv for kv in sorted(stats.items()))))
    return {"counts": dict(stats), "cre_hash": cre_hash,
            "parcels_by_county": {k: len(v) for k, v in shards.items()}}


# ----------------------------------------------------------------- shards ----
DATA_START, DATA_END = "/*__DATA_START__*/", "/*__DATA_END__*/"


def embed_into_page(html_path, obj):
    """Splice JSON between the page's DATA markers. Plain string slicing, so
    backslashes in error messages cannot be read as regex escapes."""
    html = Path(html_path).read_text(encoding="utf-8")
    i = html.find(DATA_START)
    j = html.find(DATA_END, i + 1)
    if i < 0 or j < 0:
        raise SystemExit("data markers not found in %s" % html_path)
    payload = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    Path(html_path).write_text(html[:i + len(DATA_START)] + payload + html[j:], encoding="utf-8")


def previous_records():
    prev = defaultdict(list)
    for f in SITES.glob("48*.json"):
        try:
            for rec in json.loads(f.read_text(encoding="utf-8"))["r"]:
                prev[rec[0]].append(rec)
        except Exception:
            pass
    return prev


def write_sites(all_sites, counties):
    shards = defaultdict(list)
    dropped = 0
    for s in all_sites:
        fips = counties.locate(s[1], s[2])
        if not fips:
            dropped += 1
            continue
        shards[fips].append(s)
    SITES.mkdir(parents=True, exist_ok=True)
    for old in SITES.glob("48*.json"):
        if old.stem not in shards:
            old.unlink()
    for fips, recs in shards.items():
        recs.sort(key=lambda r: (r[0], r[1], r[2]))
        (SITES / ("%s.json" % fips)).write_text(json.dumps({"r": recs}, separators=(",", ":")), encoding="utf-8")
    return shards, dropped


def main():
    ap = argparse.ArgumentParser(description="Build CRE Environmental Screening data")
    ap.add_argument("--only", help="comma list of sources: epa_frs,tceq_gis,tceq_drycleaners,rrc")
    ap.add_argument("--parcels", action="store_true", help="rebuild CRE parcel shards (needs node)")
    ap.add_argument("--geocode-limit", type=int, default=None,
                    help="cap on new dry cleaner addresses geocoded this run")
    ap.add_argument("--frs-zip", help="use a downloaded copy of the EPA FRS Texas state file")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    counties = Counties()
    idx_path = DATA / "index.json"
    old_idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {}
    sources = dict(old_idx.get("sources", {}))
    only = set(args.only.split(",")) if args.only else None
    prev = previous_records()
    ctx = {"frs_zip": args.frs_zip}
    collected = {}
    order = ["tceq_lpst_status", "tceq_gis", "tceq_drycleaners", "epa_frs", "rrc"]
    if only and "tceq_gis" in only:
        only.add("tceq_lpst_status")
    for key in order:
        title, url = SOURCE_TITLES[key]
        if only and key not in only:
            collected[key] = [r for code in SOURCE_LISTS[key] for r in prev.get(code, [])]
            continue
        t0 = time.time()
        log("[%s] %s" % (key, title))
        try:
            if key == "tceq_drycleaners":
                recs, meta = src_tceq_drycleaners(ctx, args.geocode_limit)
            else:
                recs, meta = globals()["src_" + key](ctx)
            collected[key] = recs
            sources[key] = {"title": title, "url": url, "status": "ok",
                            "fetched": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
                            "seconds": round(time.time() - t0, 1), **meta}
        except Exception as exc:  # freshness-skip: keep last good records
            carried = [r for code in SOURCE_LISTS[key] for r in prev.get(code, [])]
            collected[key] = carried
            s = dict(sources.get(key, {"title": title, "url": url}))
            s.update({"status": "stale", "error": str(exc)[:300], "carried_forward": len(carried)})
            sources[key] = s
            log("    FAILED (%s); kept %d previous records" % (str(exc)[:160], len(carried)))

    all_sites = [r for key in order for r in collected.get(key, [])]
    shards, dropped = write_sites(all_sites, counties)
    county_meta = {}
    for c in counties.items:
        recs = shards.get(c["fips"], [])
        county_meta[c["fips"]] = {
            "name": c["name"], "bbox": [round(v, 4) for v in c["bbox"]], "sites": len(recs),
            "by_list": dict(Counter(r[0] for r in recs)),
            "open": sum(1 for r in recs if r[7] == "open"),
        }
    parcels_meta = old_idx.get("parcels", {})
    if args.parcels or not (PARCELS / "ids.json").exists():
        try:
            log("[cre_parcels] %s" % SOURCE_TITLES["cre_parcels"][0])
            parcels_meta = build_parcels(counties)
            parcels_meta["built"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        except Exception as exc:
            log("    parcel build FAILED (%s); previous parcel shards kept" % str(exc)[:200])
    if not parcels_meta.get("parcels_by_county"):
        parcels_meta["parcels_by_county"] = {
            f.stem: len(json.loads(f.read_text(encoding="utf-8"))["r"]) for f in PARCELS.glob("48*.json")}
    for fips, n in parcels_meta.get("parcels_by_county", {}).items():
        if fips in county_meta:
            county_meta[fips]["parcels"] = n
    idx = {
        "_meta": stamp("environmental/refresh.py", {"sites": len(all_sites) - dropped,
                                                     "dropped_outside_texas": dropped}),
        "fields": SITE_FIELDS,
        "lists": dict(Counter(r[0] for key in order for r in collected.get(key, []))),
        "sources": sources,
        "parcels": parcels_meta,
        "counties": county_meta,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    idx_path.write_text(json.dumps(idx, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    # Embed the index in the page too: the page reads it without a second request, and
    # the CI health check (dashboard_state.py) reads row counts and the as-of stamp from
    # the HTML data block. county_rows gives that check a meaningful row count.
    embed = dict(idx, county_rows=[[f, c["sites"], c["open"]] for f, c in sorted(county_meta.items())])
    embed_into_page(HERE / "environmental-screen-tx.html", embed)
    size = sum(f.stat().st_size for f in DATA.rglob("*.json"))
    log("wrote %d sites in %d county shards (%d outside Texas dropped); data folder %.1f MB"
        % (len(all_sites) - dropped, len(shards), dropped, size / 1e6))
    stale = [k for k, v in sources.items() if v.get("status") == "stale"]
    if stale:
        log("stale sources (previous data kept): " + ", ".join(stale))
    return 0


def selftest():
    c = Counties()
    # Taylor County courthouse (Abilene) and Dallas City Hall
    assert c.locate(32.4487, -99.7331) == "48441", c.locate(32.4487, -99.7331)
    assert c.locate(32.7763, -96.7969) == "48113"
    assert c.locate(35.0, -90.0) is None
    assert norm_addr("1618 Vogel Avenue, Suite 200") == "1618 VOGEL AVE", norm_addr("1618 Vogel Avenue, Suite 200")
    assert norm_addr("4302 Oldham Lane") == "4302 OLDHAM LN"
    assert sba_sensitive("447110") == "447" and sba_sensitive("812320") == "8123"
    assert sba_sensitive("312120") is None and sba_sensitive("722511") is None
    assert USE_RX[0][1].search("MINI-MART/GAS SERVICE STATION, SHELL")
    assert not any(rx.search("HAMPTON ROAD BAPTIST CHURCH") for _, rx in USE_RX)
    assert not any(rx.search("LAUNDROMAT, BRIDGEPORT APTS") for _, rx in USE_RX)
    assert not any(rx.search("COTTON GIN ADD, BLOCK A, LOT 1") for _, rx in USE_RX)
    assert USE_RX[4][1].search("A0887BC R WILLS, 4-3, TEXAS LIQUID FERTILIZER")
    print("selftest OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
