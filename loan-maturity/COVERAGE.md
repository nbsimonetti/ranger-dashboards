# Per-County Data Coverage — Loan Maturity Intelligence (TX)

**As-of pull:** SBA bulk snapshot `asof-260331` (data through 2026-03-31), fetched 2026-05-21.

This document records what we can and cannot see, by data source, at the time of the build. It will go stale — re-run the pipeline and regenerate this file every quarter.

---

## Active sources (data in the dashboard)

| Source | Coverage | Rows in 32-county TX footprint | Notes |
|---|---|---|---|
| **SBA 7(a) loans** | FY1991–FY2026Q1 | See `loans.json` `sources_seen` for live count | Bulk CSV from `data.sba.gov`. Free, no API key. Refresh quarterly. |
| **SBA 504 loans** | FY1991–FY2026Q1 | See `loans.json` `sources_seen` for live count | Bulk CSV from `data.sba.gov`. Free, no API key. Refresh quarterly. |

Each loan record carries: `borrower`, `borrower_address`, `lender`, `lender_state`, `county`, `loan_amount`, `approval_date`, `term_months`, `maturity_date` (computed), `interest_rate`, `naics_code`, `loan_status`, `source_context`, `scraped_at`, `source_url`.

Records are filtered to:
- `project_state = 'TX'`
- `project_county ∈ 32-county footprint` (mirrors `cre/cre-dashboard-tx.html` sidebar)
- `loan_status NOT IN ('PIF', 'CHGOFF', 'CANCLD')`
- `maturity_date >= today` (still in active maturity window)

---

## Blocked sources (and why)

### State UCC bulk filings — BLOCKED for bulk
- **Texas SOSDirect** (`https://direct.sos.state.tx.us/uccsearch/`) — Free single-debtor browser search; bulk download requires paid SOSDirect subscription.
- **California / Florida / New York / Indiana / Iowa / Oklahoma** — Mixed; most paywall bulk. CA bulk is available but requires monthly subscription.
- **Workaround status:** Per-borrower enrichment via SOSDirect search is feasible but rate-limited and out of scope for v1. UCC-1 lapse-date inference (`lapse_date = filing_date + 5y`) requires the underlying filing data which we don't have.

### County Clerk Deeds of Trust — BLOCKED for bulk
For commercial real estate loans secured by real property (the bulk of bank CRE), the maturity-bearing instrument is the Deed of Trust filed at the county clerk. We confirmed the following:

| County | Portal | Free per-doc | Free bulk export | Status |
|---|---|---|---|---|
| Dallas | dallas.tx.publicsearch.us | ✓ | ✗ — paid Data Sales contract | BLOCKED |
| Harris (Houston) | cclerk.hctx.net/applications/websearch | ✓ | ✗ — paid Data Sales contact (datasales@cco.hctx.net) | BLOCKED |
| Tarrant (Fort Worth) | tarrant.tx.publicsearch.us | ✓ (registration) | ✗ — paid Central Library Bulk Data | BLOCKED |
| Bexar (San Antonio) | bexar.tx.publicsearch.us | ✓ (registration) | ✗ — paid | BLOCKED |
| Travis (Austin) | countyclerk.traviscountytx.gov | ✓ | ✗ — paid Public Information Request | BLOCKED |
| 27 smaller counties | Various — many in-person only | Varies | None known | BLOCKED |

All 5 of the major counties use vendor portals (mostly publicsearch.us) that offer free per-document download but block bulk acquisition. The maturity dates are typically embedded inside PDF instruments and would require OCR to extract.

**To unblock this in iteration 3:** either (a) acquire a small Data Sales contract with the 5 major counties (~$3-5K/yr aggregate, business approval required), or (b) hand-scrape the publicly accessible portals respecting their TOS at 1 doc/3sec (slow but feasible for high-priority counties).

### Texas Open Data Portal — NOT APPLICABLE
- `data.texas.gov` searched for keywords "lien", "deed", "mortgage", "ucc", "commercial loan". No statewide loan-level or deed-level dataset published.

### SEC EDGAR CMBS 10-D filings — PARTIAL / DEFERRED
- 10-D and 8-K filings from CMBS trusts contain loan-level remittance and delinquency exhibits with property address, current balance, and maturity date.
- EDGAR full-text search is free, no API key.
- **What's blocked:** Each trustee (Wells Fargo, Computershare, etc.) uses a different HTML/PDF template for the loan-level exhibits. No standardized XBRL schema. Parsing is per-trustee engineering work.
- **Decision:** Defer to iteration 3. CMBS borrowers rarely refinance at community banks anyway — the highest-value targets are the SBA borrowers.

### HMDA business-purpose loans — DEFERRED
- CFPB HMDA snapshot exposes a `business_or_commercial_purpose` field but covers only loans secured by 1–4 unit dwellings (small CRE / investor SFR / mixed-use). Not the main CRE universe.
- **Decision:** Defer to iteration 3 — the expected coverage gain is <5% of current SBA coverage and the data joinin is well-defined when we want it.

---

## Coverage by county (live)

The Methodology tab in the dashboard renders the actual per-county loan counts from `loans.json` at page load. The Maturity Pipeline + map views are filtered to the 32-county footprint that mirrors the CRE dashboard.

Counties with zero loans surfaced after filtering have either (a) no SBA-listed projects in our date window, (b) been filtered out by the active sidebar filters, or (c) are not in the 32-county footprint.

---

## How to refresh this file

```bash
cd dashboards/loan-maturity/data-collection
python pull_sba.py     # downloads + filters
python merge_loans.py  # writes ../loans.json
# Manually update the "SBA bulk snapshot asof-..." line at top with the
# current 'asof_tag' value from data.sba.gov.
```

The dashboard's freshness ribbon will automatically reflect the new `sba_asof` value from `loans.json` metadata.
