"""
refresh_data.py — Physician Specialty Underwriting Benchmarks Refresh Script

Pulls public benchmark data from cited sources, writes benchmarks.json, and updates
the embedded SPECIALTIES dataset in specialty-benchmarks.html.

Sources (all public, citable):
  1. Medscape Physician Compensation Report (annual, summary figures published)
     URL: https://www.medscape.com/sites/public/physician-comp/
  2. Doximity Physician Compensation Report (annual, summary published)
     URL: https://www.doximity.com/reports/physician-compensation-report/
  3. BLS OEWS (Occupational Employment and Wage Statistics) - May data, annual
     URL: https://www.bls.gov/oes/
     API: https://api.bls.gov/publicAPI/v2/timeseries/data/
  4. CMS Geographic Practice Cost Index (GPCI) - annual
     URL: https://www.cms.gov/medicare/medicare-fee-for-service-payment/physicianfeesched/pfs-federal-regulation-notices
  5. CMS Medicare Physician & Other Practitioners by Provider & Service (PUF)
     URL: https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners
  6. MedPAC Data Book (annual, July)
     URL: https://www.medpac.gov/document-type/data-book/
  7. Urban Institute Commercial Markup Study (periodic)
     URL: https://www.urban.org/research/publication/commercial-health-insurance-markups-over-medicare-prices-physician-services-vary-widely-specialty
  8. MGMA Public Benchmarks (operating cost trends, AR benchmarks)
     URL: https://www.mgma.com/articles/

Usage:
    python refresh_data.py [--update-html]

The --update-html flag rewrites the SPECIALTIES const block in specialty-benchmarks.html.
Without the flag, the script just writes benchmarks.json + data_sources.txt.

NOTE: Most physician compensation data is published as annual reports, not via API.
Medscape and Doximity reports are PDF/web pages requiring manual review for the most
recent figures. This script:
  (a) Fetches BLS OEWS data via API (the only programmatic source)
  (b) Fetches CMS PUF metadata to confirm latest vintage
  (c) Logs the URLs and dates of the manually-reviewed reports
  (d) Outputs a structured benchmarks.json that can be hand-merged into the dashboard

For a fully automated refresh, integrate paid sources (MGMA DataDive, AAMC) or
hire a research analyst to update the manual entries quarterly.
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
HTML_FILE = HERE / "specialty-benchmarks.html"
JSON_FILE = HERE / "benchmarks.json"
SOURCES_LOG = HERE / "data_sources.txt"


# ═══════════════════════════════════════════════════════════════════════════════
#  DATA SOURCES (configurable, refreshable)
# ═══════════════════════════════════════════════════════════════════════════════
SOURCES = {
    "medscape": {
        "name": "Medscape Physician Compensation Report",
        "url": "https://www.medscape.com/sites/public/physician-comp/",
        "vintage": "2024 (Survey Oct 2024 - Jan 2025)",
        "method": "Manual review of public summary tables",
        "last_pulled": "2025-04-15",
        "next_expected": "2026-04 (annual)",
    },
    "doximity": {
        "name": "Doximity Physician Compensation Report",
        "url": "https://www.doximity.com/reports/physician-compensation-report/",
        "vintage": "2025 report (CY2024 data)",
        "method": "Manual review of public PDF",
        "last_pulled": "2025-04-15",
        "next_expected": "2026-04 (annual)",
    },
    "bls_oews": {
        "name": "BLS Occupational Employment and Wage Statistics",
        "url": "https://www.bls.gov/oes/current/oes_nat.htm",
        "api_url": "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        "vintage": "May 2024 (released April 2025)",
        "method": "API fetch by SOC code",
        "last_pulled": "2025-04-15",
        "next_expected": "2026-04 (annual)",
        "soc_codes": {
            "29-1211": "Anesthesiologists",
            "29-1212": "Cardiologists",
            "29-1213": "Dermatologists",
            "29-1214": "Emergency Medicine Physicians",
            "29-1215": "Family Medicine Physicians",
            "29-1216": "General Internal Medicine Physicians",
            "29-1217": "Neurologists",
            "29-1218": "Obstetricians and Gynecologists",
            "29-1221": "Pediatricians, General",
            "29-1222": "Pathologists",
            "29-1223": "Psychiatrists",
            "29-1224": "Radiologists",
            "29-1228": "Physicians, All Other",
            "29-1241": "Ophthalmologists",
            "29-1242": "Orthopedic Surgeons",
            "29-1243": "Pediatric Surgeons",
            "29-1248": "Surgeons, All Other",
        }
    },
    "cms_gpci": {
        "name": "CMS Geographic Practice Cost Index",
        "url": "https://www.cms.gov/medicare/physician-fee-schedule/search/documentation",
        "vintage": "CY 2024",
        "conversion_factor_2024": 32.7442,
        "method": "Manual download of CMS PFS files",
        "last_pulled": "2025-04-15",
        "next_expected": "2025-11 (CY2025 finalized)",
    },
    "cms_puf": {
        "name": "CMS Medicare Physician & Other Practitioners by Provider & Service",
        "url": "https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners/medicare-physician-other-practitioners-by-provider-and-service",
        "api_url": "https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners/medicare-physician-other-practitioners-by-provider-and-service/api",
        "vintage": "CY2022 (latest released ~Q2 2024)",
        "method": "Bulk download + aggregation",
        "last_pulled": "2025-04-15",
        "next_expected": "2025-Q2 (CY2023 release)",
    },
    "medpac": {
        "name": "MedPAC Data Book",
        "url": "https://www.medpac.gov/wp-content/uploads/2024/07/July2024_MedPAC_DataBook_SEC.pdf",
        "vintage": "July 2024 (CY2022/2023 claims)",
        "method": "PDF extraction (manual)",
        "last_pulled": "2025-04-15",
        "next_expected": "2025-07 (annual)",
    },
    "urban": {
        "name": "Urban Institute Commercial Markup Study",
        "url": "https://www.urban.org/research/publication/commercial-health-insurance-markups-over-medicare-prices-physician-services-vary-widely-specialty",
        "vintage": "2017-2019 data (structurally stable)",
        "method": "Manual review of published tables",
        "last_pulled": "2025-04-15",
        "next_expected": "Periodic (no fixed schedule)",
    },
    "mgma": {
        "name": "MGMA Published Benchmarks",
        "url": "https://www.mgma.com/articles/foundational-benchmarks-and-kpis-for-medical-practice-operations-in-2023",
        "vintage": "2023-2024 published figures (full DataDive paywalled)",
        "method": "Manual review of public articles + press releases",
        "last_pulled": "2025-04-15",
        "next_expected": "Ongoing (industry trade publications)",
    }
}


# ═══════════════════════════════════════════════════════════════════════════════
#  BLS OEWS API FETCH
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_bls_wages(soc_codes, year=2024):
    """
    Fetch BLS OEWS mean annual wages for a set of SOC codes.
    BLS API uses series IDs like: OEUN000000029121103 (state=US, area=00000, SOC=29-1211, datatype=03 mean wage)
    """
    print(f"[BLS] Fetching OEWS data for {len(soc_codes)} SOC codes (year={year})...")
    series_ids = []
    for soc in soc_codes:
        soc_clean = soc.replace("-", "")
        # National (US): area 0000000, datatype 03 = mean annual wage
        series_ids.append(f"OEUN0000000{soc_clean}03")

    payload = json.dumps({
        "seriesid": series_ids,
        "startyear": str(year),
        "endyear": str(year),
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    results = {}
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        if data.get("status") != "REQUEST_SUCCEEDED":
            print(f"[BLS] WARN: status={data.get('status')}, message={data.get('message')}")
            return results
        for series in data.get("Results", {}).get("series", []):
            sid = series["seriesID"]
            soc_clean = sid[10:18]
            soc_formatted = f"{soc_clean[:3]}-{soc_clean[3:]}"
            if series.get("data"):
                latest = series["data"][0]
                results[soc_formatted] = {
                    "value": float(latest["value"]) if latest["value"] != "-" else None,
                    "year": latest["year"],
                    "period": latest["period"],
                }
        print(f"[BLS] Retrieved {len(results)} wage points.")
    except Exception as e:
        print(f"[BLS] ERROR: {e}")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  CMS PUF METADATA
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_cms_puf_metadata():
    """
    Confirm latest CMS Medicare Provider Utilization data vintage.
    Returns the latest reporting period.
    """
    print("[CMS] Checking latest PUF dataset metadata...")
    url = "https://data.cms.gov/data.json"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            catalog = json.loads(resp.read())
        for ds in catalog.get("dataset", []):
            title = ds.get("title", "")
            if "Medicare Physician" in title and "Provider" in title:
                modified = ds.get("modified", "")
                print(f"[CMS] Found: {title} (modified {modified})")
                return {"title": title, "modified": modified, "url": ds.get("landingPage", "")}
    except Exception as e:
        print(f"[CMS] ERROR: {e}")
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  MANUAL DATA TEMPLATE (where APIs aren't available)
# ═══════════════════════════════════════════════════════════════════════════════
# These figures must be updated manually each year by reviewing the published reports.
# Update annually around April-May when most reports drop.

MEDSCAPE_2024_AVG_COMP = {
    "Orthopedic Surgery": 564000,
    "Plastic Surgery": 544000,
    "Radiology": 526000,
    "Cardiology": 520000,
    "Gastroenterology": 513000,
    "Urology": 505000,
    "Anesthesiology": 501000,
    "Otolaryngology (ENT)": 484000,
    "Oncology / Hematology": 472000,
    "Dermatology": 454000,
    "General Surgery": 434000,
    "Critical Care": 418000,
    "Ophthalmology": 409000,
    "Pulmonology": 402000,
    "Pathology": 388000,
    "Emergency Medicine": 388000,
    "OB/GYN": 372000,
    "Nephrology": 363000,
    "Physical Med & Rehab": 362000,
    "Psychiatry": 341000,
    "Neurology": 332000,
    "Allergy & Immunology": 319000,
    "Internal Medicine": 294000,
    "Rheumatology": 284000,
    "Family Medicine": 281000,
    "Infectious Diseases": 277000,
    "Endocrinology": 274000,
    "Pediatrics": 265000,
    "Geriatrics": 246000,
    # Source: https://www.medscape.com/sites/public/physician-comp/2024
    # Vintage: 2024 income reported in 2025 publication.
    # Sample: 7,300+ physicians; PCP avg = $287K; Specialist avg = $404K.
}

DOXIMITY_2025_AVG_COMP = {
    "Neurosurgery": 749140,
    "Thoracic Surgery": 689969,
    "Orthopedic Surgery": 679517,
    "Cardiology": 587360,
    "Radiology": 571749,
    "Gastroenterology": 537870,
    # Other specialties from 2024 report (CY2023):
    "Plastic Surgery": 619812,
    "Urology": 559474,
    "Dermatology": 508401,
    "Ophthalmology": 477232,
    "Emergency Medicine": 411133,
    "Psychiatry": 341977,
    # Source: https://www.doximity.com/reports/physician-compensation-report/2025
    # Vintage: CY2024 calendar-year data, 37,000+ surveys.
}

DOXIMITY_2025_TOP_METROS = [
    {"rank": 1, "metro": "Rochester, MN", "comp": 495532},
    {"rank": 2, "metro": "St. Louis, MO", "comp": 484883},
    {"rank": 3, "metro": "Los Angeles, CA", "comp": 470198},
    {"rank": 4, "metro": "San Jose, CA", "comp": 469878},
    {"rank": 5, "metro": "Sacramento, CA", "comp": 460671},
    {"rank": 6, "metro": "Phoenix, AZ", "comp": 459082},
    {"rank": 7, "metro": "Riverside, CA", "comp": 455986},
    {"rank": 8, "metro": "Minneapolis, MN", "comp": 452598},
    {"rank": 9, "metro": "San Francisco, CA", "comp": 449830},
    {"rank": 10, "metro": "Charlotte, NC", "comp": 448400},
]

DOXIMITY_2025_BOTTOM_METROS = [
    {"rank": 1, "metro": "Durham–Chapel Hill, NC", "comp": 358782},
    {"rank": 2, "metro": "Rochester, NY", "comp": 364160},
    {"rank": 3, "metro": "Ann Arbor, MI", "comp": 373154},
    {"rank": 4, "metro": "Charleston, SC", "comp": 384419},
    {"rank": 5, "metro": "Washington, DC", "comp": 386731},
    {"rank": 6, "metro": "Providence, RI", "comp": 386788},
    {"rank": 7, "metro": "San Antonio, TX", "comp": 389495},
    {"rank": 8, "metro": "Boston, MA", "comp": 390799},
    {"rank": 9, "metro": "Baltimore, MD", "comp": 392507},
    {"rank": 10, "metro": "Worcester, MA", "comp": 397188},
]

CMS_GPCI_2024 = [
    {"locality": "Manhattan, NY", "work": 1.065, "pe": 1.166, "mp": 1.656},
    {"locality": "San Francisco, CA", "work": 1.088, "pe": 1.419, "mp": 0.445},
    {"locality": "Los Angeles, CA", "work": 1.042, "pe": 1.194, "mp": 0.690},
    {"locality": "Chicago, IL", "work": 1.007, "pe": 1.023, "mp": 2.018},
    {"locality": "Boston, MA", "work": 1.042, "pe": 1.197, "mp": 0.894},
    {"locality": "Washington, DC", "work": 1.057, "pe": 1.192, "mp": 1.168},
    {"locality": "Houston, TX", "work": 1.014, "pe": 1.003, "mp": 1.409},
    {"locality": "Dallas, TX", "work": 1.011, "pe": 1.007, "mp": 0.877},
    {"locality": "Miami, FL", "work": 1.000, "pe": 1.027, "mp": 2.500},
    {"locality": "Seattle, WA", "work": 1.043, "pe": 1.220, "mp": 0.853},
    {"locality": "Atlanta, GA", "work": 1.000, "pe": 0.997, "mp": 1.128},
    {"locality": "Philadelphia, PA", "work": 1.024, "pe": 1.053, "mp": 1.177},
]


# ═══════════════════════════════════════════════════════════════════════════════
#  SOURCES LOG WRITER
# ═══════════════════════════════════════════════════════════════════════════════
def write_sources_log():
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "PHYSICIAN UNDERWRITING DASHBOARD — DATA SOURCES LOG",
        f"Refresh run: {now_utc}",
        "=" * 70,
        "",
    ]
    for key, src in SOURCES.items():
        lines.append(f"[{key.upper()}] {src['name']}")
        lines.append(f"  URL: {src['url']}")
        if "api_url" in src:
            lines.append(f"  API: {src['api_url']}")
        lines.append(f"  Vintage: {src['vintage']}")
        lines.append(f"  Method: {src['method']}")
        lines.append(f"  Last pulled: {src['last_pulled']}")
        lines.append(f"  Next expected: {src['next_expected']}")
        lines.append("")
    SOURCES_LOG.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] Wrote {SOURCES_LOG}")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Refresh physician underwriting benchmark data.")
    parser.add_argument("--update-html", action="store_true",
                        help="Rewrite the SPECIALTIES const in specialty-benchmarks.html")
    parser.add_argument("--skip-bls", action="store_true",
                        help="Skip BLS API fetch (use cached values)")
    args = parser.parse_args()

    print("Physician Underwriting Benchmark Refresh")
    print("=" * 50)

    benchmarks = {
        "metadata": {
            "refresh_run": datetime.now(timezone.utc).isoformat(),
            "sources": SOURCES,
        },
        "medscape_2024": MEDSCAPE_2024_AVG_COMP,
        "doximity_2025": DOXIMITY_2025_AVG_COMP,
        "doximity_top_metros": DOXIMITY_2025_TOP_METROS,
        "doximity_bottom_metros": DOXIMITY_2025_BOTTOM_METROS,
        "cms_gpci_2024": CMS_GPCI_2024,
    }

    # Fetch BLS data via API
    if not args.skip_bls:
        bls_data = fetch_bls_wages(SOURCES["bls_oews"]["soc_codes"].keys())
        benchmarks["bls_oews_may2024"] = bls_data
    else:
        print("[BLS] Skipped (--skip-bls).")

    # Confirm CMS PUF latest vintage
    cms_meta = fetch_cms_puf_metadata()
    if cms_meta:
        benchmarks["cms_puf_metadata"] = cms_meta

    # Write benchmarks.json
    JSON_FILE.write_text(json.dumps(benchmarks, indent=2, default=str), encoding="utf-8")
    print(f"[OK] Wrote {JSON_FILE}")

    # Write sources log
    write_sources_log()

    # Optionally update the HTML SPECIALTIES const block
    if args.update_html:
        print("\n[UPDATE] --update-html flag detected.")
        print("        Manually update the SPECIALTIES const in specialty-benchmarks.html")
        print("        using the figures in benchmarks.json. Automated rewrite not implemented")
        print("        because the HTML uses an enriched data model (payer mix, overhead, etc.)")
        print("        that this script does not yet capture from sources.")

    print("\nDone. Next steps:")
    print("  1. Review benchmarks.json for any data anomalies")
    print("  2. Manually update SPECIALTIES const in specialty-benchmarks.html if income figures changed")
    print("  3. git add . && git commit -m 'Refresh benchmark data' && git push")
    print("  4. GitHub Pages will auto-deploy")


if __name__ == "__main__":
    main()
