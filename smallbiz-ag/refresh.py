"""
Small Business & Agricultural Lending (TX) - data refresh.

The small-business and agricultural lending landscape across the footprint, by
sector, county, and lender - with a dedicated agriculture view (the rural-footprint
lending gap the suite otherwise omits). Built from the in-repo SBA 7(a)/504 borrower
data (real originations with borrower, NAICS, county, lender).

Sources: SBA 7(a)/504 FOIA borrowers (loan-maturity/loans.json, in-repo).
NOTE ON CRA: the definitive competitive small-business lending census is the FFIEC
CRA disclosure data, but ffiec.gov bot-blocks automated pulls (HTTP 403); it needs a
manual bulk download. USDA agricultural context (NASS QuickStats) needs a free API
key. Both are documented as augmentation paths in the dashboard methodology.

Run:  python smallbiz-ag/refresh.py
"""
import sys
import json
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from footprint import inject_data, stamp  # noqa: E402

HERE = Path(__file__).resolve().parent
HTML = HERE / "smallbiz-ag-tx.html"
LOANS = HERE.parent / "loan-maturity" / "loans_statewide.json"

SECTORS = {
    "11": "Agriculture, Forestry & Fishing", "21": "Mining & Oil/Gas", "22": "Utilities",
    "23": "Construction", "31": "Manufacturing", "32": "Manufacturing", "33": "Manufacturing",
    "42": "Wholesale Trade", "44": "Retail Trade", "45": "Retail Trade",
    "48": "Transportation & Warehousing", "49": "Transportation & Warehousing",
    "51": "Information", "52": "Finance & Insurance", "53": "Real Estate & Rental",
    "54": "Professional Services", "55": "Management", "56": "Admin & Support",
    "61": "Educational Services", "62": "Health Care & Social Assistance",
    "71": "Arts & Recreation", "72": "Accommodation & Food", "81": "Other Services",
    "92": "Public Administration",
}


def sector_of(naics):
    s = str(naics or "")[:2]
    return SECTORS.get(s, "Unclassified"), s


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def build(loans):
    by_sector, by_county, by_lender = {}, {}, {}
    ag_by_county, ag_by_lender = {}, {}
    ag_loans = []
    total_amt = 0.0
    for ln in loans:
        amt = num(ln.get("loan_amount"))
        sec_name, sec2 = sector_of(ln.get("naics_code"))
        county = (ln.get("county") or "").title()
        lender = ln.get("lender") or "Undisclosed"
        total_amt += amt

        s = by_sector.setdefault(sec_name, {"sector": sec_name, "n": 0, "amt": 0.0})
        s["n"] += 1
        s["amt"] += amt
        c = by_county.setdefault(county, {"county": county, "n": 0, "amt": 0.0, "ag_amt": 0.0})
        c["n"] += 1
        c["amt"] += amt
        by_lender[lender] = by_lender.get(lender, 0.0) + amt

        if sec2 == "11":
            c["ag_amt"] += amt
            ag_by_county[county] = ag_by_county.get(county, 0.0) + amt
            ag_by_lender[lender] = ag_by_lender.get(lender, 0.0) + amt
            ag_loans.append({
                "borrower": ln.get("borrower"), "county": county,
                "city": (ln.get("borrower_city") or "").title(),
                "lender": lender, "amount": round(amt),
                "naics": ln.get("naics_code"),
                "rate": ln.get("interest_rate"), "status": ln.get("loan_status"),
                "approved": (ln.get("approval_date") or "")[:10],
            })

    ag_loans.sort(key=lambda x: -(x["amount"] or 0))
    fmt_sector = sorted(by_sector.values(), key=lambda x: -x["amt"])
    for s in fmt_sector:
        s["amt"] = round(s["amt"])
    counties = sorted(by_county.values(), key=lambda x: -x["amt"])
    for c in counties:
        c["amt"] = round(c["amt"])
        c["ag_amt"] = round(c["ag_amt"])
    lenders = sorted(({"lender": k, "amt": round(v)} for k, v in by_lender.items()),
                     key=lambda x: -x["amt"])[:40]
    ag_lenders = sorted(({"lender": k, "amt": round(v)} for k, v in ag_by_lender.items()),
                        key=lambda x: -x["amt"])[:25]

    ag_total = sum(ag_by_county.values())
    return {
        "_meta": stamp("SBA 7(a)/504 FOIA borrowers (in-repo)", {
            "loans": len(loans), "total_credit": round(total_amt),
            "sectors": len(by_sector), "counties": len(by_county),
            "ag_loans": len(ag_loans), "ag_credit": round(ag_total),
        }),
        "by_sector": fmt_sector,
        "counties": counties,
        "lenders": lenders,
        "ag": {"by_lender": ag_lenders, "loans": ag_loans[:500]},
    }


def main():
    raw = json.loads(LOANS.read_text(encoding="utf-8"))
    loans = raw.get("loans", raw) if isinstance(raw, dict) else raw
    print("SBA loans read:", len(loans))
    data = build(loans)
    m = data["_meta"]
    print("sectors:", m["sectors"], "| counties:", m["counties"],
          "| total $%.1fM" % (m["total_credit"] / 1e6),
          "| ag loans:", m["ag_loans"], "($%.1fM)" % (m["ag_credit"] / 1e6))
    size = inject_data(HTML, data)
    print("injected %.0f KB into %s" % (size / 1024, HTML.name))


if __name__ == "__main__":
    main()
