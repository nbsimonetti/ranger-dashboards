"""
refresh_valuation_data.py — M&A Target Dashboard Valuation Refresh

Pulls Tangible Book Value of Equity (TBVE) inputs from the FDIC BankFind Financials
API for all 95 target banks in the dashboard. Also documents the FR Y-6 shareholder
data access pattern via FFIEC NIC.

Sources:
  1. FDIC BankFind Financials API (public, no auth)
     Endpoint: https://banks.data.fdic.gov/api/financials
     Fields used: CERT, REPDTE, EQTOT, ASSET, GOODWILL, INTAN
     Used for: Tangible book value calculation (EQTOT - INTAN)

  2. FFIEC National Information Center (NIC)
     Profile URL: https://www.ffiec.gov/npw/Institution/Profile/<rssd_id>
     FR Y-6 filings: published as PDFs accessible through the NIC profile page
     IMPORTANT: FFIEC NIC uses CAPTCHA-based bot protection that blocks automated
     scraping. Programmatic retrieval requires either:
       (a) Manual download via browser (recommended for community bank M&A research)
       (b) Selenium/Playwright with CAPTCHA solver (complex; not implemented)
       (c) Direct subscription to FFIEC bulk data feed (commercial)
     The dashboard surfaces direct NIC profile links for each target's holding
     company so users can click through to retrieve FR Y-6 filings manually.

  3. SEC EDGAR (for SEC-registered holdcos only)
     API: https://data.sec.gov/submissions/CIK<cik>.json
     Fields used: DEF 14A proxy filings (shareholder ownership disclosures)
     Only 2 of 95 targets have SEC-registered holdcos.

Usage:
    python refresh_valuation_data.py [--cert <cert>] [--out <path>]

Outputs:
    tbve_data.json — dict keyed by CERT with EQTOT, GOODWILL, INTAN, REPDTE
    shareholder_links.json — dict keyed by CERT with NIC profile URL + status

To incorporate refreshed data into the dashboard, run with --update-html flag,
or manually merge the JSON into the const DATA block in ranger-ma-targets.html.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
DASHBOARD_HTML = HERE / "ranger-ma-targets.html"
TBVE_JSON = HERE / "tbve_data.json"
SHAREHOLDER_LINKS_JSON = HERE / "shareholder_links.json"

USER_AGENT = "Ranger Bank M&A Research"

# ═══════════════════════════════════════════════════════════════════════════════
#  FDIC TBVE FETCH
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_tbve_for_certs(certs, batch_size=20):
    """
    Fetch most recent EQTOT, GOODWILL, INTAN, ASSET, REPDTE for a list of FDIC certs.

    Returns: dict keyed by CERT (str) with the financial fields.
    """
    print(f"[FDIC] Fetching TBVE inputs for {len(certs)} banks...")
    tbve = {}
    for i in range(0, len(certs), batch_size):
        batch = certs[i:i + batch_size]
        filter_str = "CERT:(" + " OR ".join(str(c) for c in batch) + ")"
        params = {
            "filters": filter_str,
            "fields": "CERT,REPDTE,EQTOT,ASSET,GOODWILL,INTAN",
            "sort_by": "REPDTE",
            "sort_order": "DESC",
            "limit": "1000",
        }
        url = "https://banks.data.fdic.gov/api/financials?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                j = json.loads(resp.read())
            for item in j.get("data", []):
                d = item.get("data", {})
                cert = str(d.get("CERT"))
                if cert in tbve:
                    continue  # keep most recent only
                eqtot = d.get("EQTOT") or 0
                intan = d.get("INTAN") or 0
                goodwill = d.get("GOODWILL") or 0
                tbve[cert] = {
                    "EQTOT": eqtot,
                    "GOODWILL": goodwill,
                    "INTAN": intan,
                    "OTHER_INTAN": max(0, intan - goodwill),
                    "TBVE": eqtot - intan,
                    "ASSET_RPT": d.get("ASSET"),
                    "REPDTE": d.get("REPDTE"),
                }
        except Exception as e:
            print(f"  [WARN] batch {i}: {e}")
        time.sleep(0.3)
        print(f"  Fetched {len(tbve)} so far...")
    print(f"[FDIC] Complete. {len(tbve)} records retrieved.")
    return tbve


# ═══════════════════════════════════════════════════════════════════════════════
#  FR Y-6 ACCESS LINKS
# ═══════════════════════════════════════════════════════════════════════════════
def build_nic_links(rows):
    """
    Build direct NIC profile links for each target's holding company. Users can
    click through to retrieve FR Y-6 filings manually.

    The NIC profile page lists all reports filed by the holdco, including FR Y-6.
    The 'Holdings' tab shows the organizational structure; the 'Reports' tab
    shows filed reports with download links.

    Returns: dict keyed by CERT (str) with NIC URLs and access status.
    """
    print(f"[NIC] Building shareholder access links for {len(rows)} banks...")
    links = {}
    for r in rows:
        cert = str(r.get("CERT", ""))
        holdco_rssd = r.get("holdco_rssd")
        holdco_name = r.get("holdco_name")
        sec_cik = r.get("sec_cik")
        is_public = r.get("is_public")

        entry = {
            "holdco_name": holdco_name,
            "holdco_rssd": holdco_rssd,
            "is_public": bool(is_public),
            "sec_cik": sec_cik,
            "nic_profile_url": None,
            "sec_filings_url": None,
            "fry6_search_url": None,
            "status": None,
            "status_note": None,
        }

        if holdco_rssd:
            entry["nic_profile_url"] = f"https://www.ffiec.gov/npw/Institution/Profile/{holdco_rssd}"
            # NIC report search URL (page that lists FR Y-6 filings; manually accessed)
            entry["fry6_search_url"] = (
                f"https://www.ffiec.gov/npw/FinancialReport/FinancialReportSearch"
                f"?reportType=FRY-6&rssd_id={holdco_rssd}"
            )

        if is_public and sec_cik:
            cik_padded = str(sec_cik).zfill(10)
            entry["sec_filings_url"] = (
                f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                f"&CIK={cik_padded}&type=DEF+14A&dateb=&owner=include&count=10"
            )

        # Status classification
        if is_public:
            entry["status"] = "public"
            entry["status_note"] = "SEC-registered. DEF 14A proxy has 5%+ holders, insider ownership."
        elif holdco_rssd:
            entry["status"] = "private_holdco"
            entry["status_note"] = (
                "Private bank holding company. FR Y-6 filed annually with Federal Reserve. "
                "Click NIC link to download most recent filing (CAPTCHA may apply)."
            )
        else:
            entry["status"] = "no_holdco"
            entry["status_note"] = (
                "No holding company on file. Ownership requires direct outreach disclosure."
            )

        links[cert] = entry

    pub = sum(1 for v in links.values() if v["status"] == "public")
    priv = sum(1 for v in links.values() if v["status"] == "private_holdco")
    nohc = sum(1 for v in links.values() if v["status"] == "no_holdco")
    print(f"[NIC] Public: {pub} · Private (with holdco): {priv} · No holdco: {nohc}")
    return links


# ═══════════════════════════════════════════════════════════════════════════════
#  HTML INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════
def merge_into_html(html_path, tbve, shareholder_links):
    """
    Merge TBVE and shareholder link data into the dashboard's embedded DATA block.

    Each row in the DATA.rows array gets new fields:
        EQTOT, GOODWILL, INTAN, OTHER_INTAN, TBVE, REPDTE
        nic_profile_url, fry6_search_url, sec_filings_url, shareholder_status, shareholder_note
    """
    print(f"[HTML] Merging refreshed data into {html_path}...")
    text = html_path.read_text(encoding="utf-8")
    match = re.search(r"const DATA = (\{.*?\});", text, re.DOTALL)
    if not match:
        print("[HTML] ERROR: const DATA not found")
        return
    raw = match.group(1)
    raw_for_json = re.sub(r"\bNaN\b", "null", raw)
    data = json.loads(raw_for_json)

    updated = 0
    for r in data.get("rows", []):
        cert = str(r.get("CERT", ""))
        t = tbve.get(cert)
        if t:
            r["EQTOT"] = t["EQTOT"]
            r["GOODWILL"] = t["GOODWILL"]
            r["INTAN"] = t["INTAN"]
            r["OTHER_INTAN"] = t["OTHER_INTAN"]
            r["TBVE"] = t["TBVE"]
            r["REPDTE"] = t["REPDTE"]
            updated += 1
        s = shareholder_links.get(cert)
        if s:
            r["nic_profile_url"] = s["nic_profile_url"]
            r["fry6_search_url"] = s["fry6_search_url"]
            r["sec_filings_url"] = s["sec_filings_url"]
            r["shareholder_status"] = s["status"]
            r["shareholder_note"] = s["status_note"]

    print(f"[HTML] Updated {updated} rows with TBVE data.")
    # Re-emit with NaN preserved as null
    new_data_str = json.dumps(data)
    new_html = text[:match.start(1)] + new_data_str + text[match.end(1):]
    html_path.write_text(new_html, encoding="utf-8")
    print(f"[HTML] Wrote updated {html_path}")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    p = argparse.ArgumentParser(description="Refresh M&A target valuation data")
    p.add_argument("--cert", help="Refresh single CERT only")
    p.add_argument("--no-update-html", action="store_true", help="Just write JSON, don't update HTML")
    args = p.parse_args()

    # Load existing dashboard to get cert list
    text = DASHBOARD_HTML.read_text(encoding="utf-8")
    match = re.search(r"const DATA = (\{.*?\});", text, re.DOTALL)
    if not match:
        print("ERROR: const DATA not found in HTML")
        sys.exit(1)
    raw = re.sub(r"\bNaN\b", "null", match.group(1))
    data = json.loads(raw)
    rows = data["rows"]

    if args.cert:
        rows = [r for r in rows if str(r.get("CERT")) == args.cert]

    certs = [str(r["CERT"]) for r in rows if r.get("CERT")]
    print(f"Targets: {len(rows)} banks")

    # Fetch TBVE
    tbve = fetch_tbve_for_certs(certs)
    TBVE_JSON.write_text(json.dumps(tbve, indent=2, default=str), encoding="utf-8")
    print(f"[OK] Wrote {TBVE_JSON}")

    # Build shareholder links
    sh_links = build_nic_links(rows)
    SHAREHOLDER_LINKS_JSON.write_text(json.dumps(sh_links, indent=2, default=str), encoding="utf-8")
    print(f"[OK] Wrote {SHAREHOLDER_LINKS_JSON}")

    # Merge into HTML
    if not args.no_update_html:
        merge_into_html(DASHBOARD_HTML, tbve, sh_links)

    print("\nDone.")
    print("Note: FR Y-6 shareholder details (5%+ holders, insider ownership) require")
    print("manual retrieval via the NIC profile links surfaced in the dashboard's")
    print("Purchase Price Valuation tab. FFIEC's CAPTCHA-based bot protection prevents")
    print("automated bulk parsing.")


if __name__ == "__main__":
    main()
