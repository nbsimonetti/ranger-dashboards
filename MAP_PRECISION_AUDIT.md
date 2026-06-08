# Map Precision Audit

**Date:** 2026-05-26
**Scope:** All six dashboards in the Ranger Bank suite.
**Sources reviewed:** `dashboards/{deposit,ma,cre,loan-maturity,physician,physician-underwriting}/*.html`

This audit answers four questions for each map (or absent map): what decision does the user need to make from it; what precision is required for that decision; what precision do we ship today; and what's the smallest delta from today's state to the required state.

---

## Decision matrix

| Dashboard | Decision the map supports | Required precision | Today | Action |
|---|---|---|---|---|
| Deposit Intelligence | Where are competitor banks dense; where could Ranger plant a new branch | Per-branch at high zoom | Institution HQ only | **Improve** — add per-branch layer at zoom ≥ 10 |
| M&A Targets | Which targets are geographically near our footprint | Institution HQ | Institution HQ | **Keep** + UX cleanup |
| CRE Prospecting | Every parcel matching a filter, with adjacency visible | Parcel-level (street address) | County centroid (32 markers for 162K parcels) | **Replace** — geocode all parcels |
| Loan Maturity | Borrowers within X-mile drive of a Ranger branch | Borrower-address-level | County centroid + golden-angle spiral jitter | **Improve** — geocode SBA borrowers |
| Physician (TX) | Practice locations for territory + outreach planning | Practice-address-level | None (`c4` canvas mis-labeled "map"; it's a bar chart) | **Add** — new Leaflet map + rename `c4` |
| Physician Underwriting | Cross-state benchmark variance | State boundaries | None (HTML tables on Geo View tab) | **Add** — US-state choropleth |

The two precision gaps that matter are CRE (5,000:1 information loss) and Loan Maturity (county-bucket distortion). Both are fixable with free Census Geocoder + better Leaflet rendering. No new data vendor required.

---

## Geocoder decision

The US Census Geocoder is the right starting point for every address-based dataset in the suite:

- **Free**, no API key, no signup
- **Bulk batch** endpoint accepts 10K addresses per HTTP POST
- US-only — perfect for our TX-focused suite
- Realistic match rate **70–85% on clean SBA / NPPES / CAD addresses**
- Returns lat/lng plus a confidence indicator and the matched canonical address

**Residual addresses that Census misses** (rural routes, PO boxes, multi-unit) — defer to a paid fallback only if the unmatched fraction is materially blocking a use case. Mapbox (100K free requests/month, then $5/1K) is the budget fallback if needed. Realistic total annual spend across the suite if we end up using paid for the residual: **<$200/year**.

| Dataset | Records | Expected match rate | Estimated batch runtime | Fallback budget |
|---|---|---|---|---|
| SBA loans (loan-maturity) | 19,737 | 80–85% (clean business addresses) | ~5 min (2 batches) | $0 — Census only |
| CRE parcels | 162,109 | 70–80% (mixed quality) | ~45 min (17 batches) | $0–100/yr Mapbox |
| Physician practices | 24,800 | 85–90% (NPPES is curated) | ~6 min (3 batches) | $0 — Census only |
| Total | **206,646** | — | **~60 min one-time** | **<$200/yr ongoing** |

Cache results to `*-geocoded.json` files in the repo. Re-geocode quarterly (when SBA refreshes) or annually (when CAD / NPPES refresh).

---

## Per-dashboard findings

### A. Deposit Intelligence — Keep with improvement
- **Current:** `L.circleMarker([b.lat, b.lng])` per institution, with `markerClusterGroup` clustering enabled (deposit-intelligence.html:2016, 2039-2043). FDIC institution HQ coords are correct unit of analysis for "which holding companies operate in TX."
- **Gap:** Wells Fargo's 1,300 TX branches collapse to one marker in San Francisco. Useless for the "where could Ranger plant a new branch" sub-question.
- **Fix:** Add a per-branch layer that activates at zoom ≥ 10. FDIC `/locations` data is *already pulled* by `fetchBranchCounts()` but only counted — coords are discarded. Re-pull retaining LAT/LON; render as small distinct circles.

### B. M&A Targets — Keep
- **Current:** `L.circleMarker([r.latitude, r.longitude])` per target, asset-sized, score-colored; `preferCanvas: true`; custom star for Ranger HQ (ranger-ma-targets.html:1433, 1486, 1520).
- **Verdict:** Precision is correct. The unit of acquisition is the holding company, and HQ is the right marker location.
- **Improvement opportunity:** at zoom < 6, multi-bank-holding-companies (`multi_bank_holdco === true`) could cluster under a single marker showing the holdco rollup. Low priority; defer.

### C. CRE Prospecting — Replace
- **Current:** `function renderMap()` aggregates 162,109 parcels into per-county counts and renders 32 circles using a hardcoded `COUNTY_COORDS` lookup (cre-dashboard-tx.html:1263-1290). Marker size encodes parcel count, color encodes top-score-in-county.
- **Gap:** **5,000:1 information loss.** The dashboard's primary use case is "show me the buildings matching my filter" and the map shows none of them at parcel level.
- **Fix:** Replace the render entirely. Two-tier rendering based on zoom:
  - Zoom < 9: keep county-bucket view (but show real counts, not the misleading aggregation).
  - Zoom ≥ 9: `Leaflet.markercluster` with `chunkedLoading: true`, `disableClusteringAtZoom: 14`, canvas renderer.
  - Falls back to current county-only view if `cre-coords-tx.json` is missing.

### D. Loan Maturity — Improve
- **Current:** `COUNTY_CENTROIDS[r.county]` + golden-angle spiral jitter (loan-maturity-tx.html:1190-1224). Every Bell-County loan plotted within a fraction of a mile of every other Bell-County loan.
- **Gap:** Useless for route planning ("which borrowers can I see on a Tuesday afternoon in Dallas?").
- **Fix:** Geocode SBA borrower addresses to `loans-geocoded.json`. At zoom ≥ 9, plot per-borrower. Below zoom 9, fall back to a real county-count view (not the spiral). Falls back to current view if geocode JSON is missing.

### E. Physician (TX) — Add
- **Current:** No real map. `<canvas id="c4">` carries the label "Territory Revenue Map" but renders a stacked bar chart of solo vs group Medicare $ by metro (TX_Physician_Dashboard.html:346, 1104-1136). Misleading.
- **Action:** Per user direction, **add a real practice-location map** as a new tab/section (not a replacement). Rename `c4` from "Territory Revenue Map" to "Top Metros by Medicare Revenue" so it's labeled honestly. Build a new Leaflet map plotting geocoded practice addresses, sized by Medicare payment volume, colored by specialty group (PCP / Surgical / Medical Specialty / Hospital-Based).

### F. Physician Underwriting — Add
- **Current:** Geographic View tab is HTML tables only — state names + numbers.
- **Action:** Add a US-state choropleth via free GeoJSON. State-level granularity is correct (Doximity / MedPAC income data is reported per-state). Color scale = state-median specialty income. No geocoding needed.

---

## Cross-cutting UX cleanup

To be applied to all four existing maps + the two new ones:

1. **Tile layer choice.** Default OSM is functional but visually heavy when overlaid with score-colored markers. Add CartoDB Positron as an alternate base layer with a Leaflet `L.control.layers` switcher.
2. **Standardized popups.** Every popup shows: bold name, address, key metric, source link. Today they vary.
3. **Legends.** Every map needs a fixed legend explaining marker color and size.
4. **"Fit to filter" button.** When sidebar filters change, current viewport stays put; user has to manually pan. Add a button that re-bounds to visible markers.
5. **Print rule.** `@media print { .map-wrap, #map { display: none } }` per dashboard.

---

## Performance constraints reference

| Marker count | Required Leaflet approach |
|---|---|
| < 1,000 | SVG renderer fine |
| 1,000 – 10,000 | Canvas renderer (`preferCanvas: true`) OR markercluster |
| 10,000 – 100,000 | Both: markercluster with `chunkedLoading: true` + canvas |
| > 100,000 (CRE) | markercluster + canvas + `disableClusteringAtZoom: 14` |

The 162K-parcel CRE map is the tightest budget. If markercluster + canvas isn't smooth in testing, fall back to `Leaflet.glify` (WebGL point rendering, no clustering needed).

---

## What ships in this iteration

Tracked in the engineering changelog. In summary:

- New `dashboards/_geocoding/` directory with a shared Census Geocoder Python utility (`census_geocoder.py`) and three per-dataset wrappers (`geocode_loans.py`, `geocode_parcels.py`, `geocode_physicians.py`).
- Three `*-geocoded.json` cache files (gitignored if > 10 MB; included if smaller).
- CRE map rebuild.
- Loan Maturity map upgrade.
- Deposit per-branch layer.
- Physician dashboard real map + `c4` rename.
- Physician Underwriting state choropleth.
- Per-dashboard UX cleanup (tile switcher, popups, legend, fit-to-filter, print rule).

All maps continue to work gracefully if their respective geocode cache is missing.
