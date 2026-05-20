# Cross-Dashboard Functionality Audit

**Date:** 2026-05-20
**Scope:** All five Ranger Dashboards reviewed for tab/view activation, render refresh, filter coupling, empty-state handling, and drift from the Deposit Intelligence patterns shipped in commits `0ecdf12` / `30075c1` / `8fe8f97`.

Status legend:
- **OK** — works and matches new patterns
- **Broken** — does not work as intended
- **Drift** — works but inconsistent with new patterns (e.g., stale counts, no freshness indicator, missing data-driven render)

---

## 1. Deposit Intelligence — `dashboards/deposit/deposit-intelligence.html`

Reference dashboard. Recent changes already verified.

| Tab | Status | Notes |
|---|---|---|
| Overview | OK | Yield curve chart + stat cards driven by `S.banks` / `S.allScraped`. |
| Bank Directory | OK | Composite badge uses `shv-trigger` (line 2616); Update Data re-renders via `renderBankDirectory()`. |
| Market Intel | OK | Market opportunity badge uses `shv-trigger` (line 1491). |
| Rate Scanner | OK | Source-URL column visible; freshness ribbon shows scrape age. |
| Cost of Funds | OK | COF subscript now `Q3 2025` via `formatRepdte()`. |
| CD Analysis | OK | Re-renders on filter + Update Data via `renderCdMatrix()`. |
| Charts & Map | OK | All 11 Chart.js panels carry `subtitle:_subtitleCfg(...)` for FDIC period or scrape date. Map re-renders on Update Data. |
| Methodology | OK | Fully data-driven via `renderMethodology()` — coverage, sources, weights, as-of dates. |

---

## 2. M&A Targets — `dashboards/ma/ranger-ma-targets.html`

Uses `data-view` button pattern (not `data-tab`). View dispatch: lines 626-638. Per-view renderers documented below.

| View | Status | Notes |
|---|---|---|
| Summary Rankings | **OK** | Initial-rendered at load (line 2208 `renderRankings()`). Composite badges use `shv-trigger` (line 807). Score-hover now works after fix. |
| Top 20 Detail | **Drift** | `renderTop20()` line 949 — guarded by `cont.dataset.rendered` so renders **only once**. If `MA_WEIGHTS` change via the drawer, top-20 cards display stale composites. Composite is plain `fmtNum` (no `shv-trigger`) — no hover breakdown for top-20 cards. |
| Purchase Price Valuation | OK | Plotly bar (`#val-chart`) refreshes via `renderValuation()` on view click. |
| Peer Comparison | OK | Plotly grouped bar via `renderPeer()` (line 1050). Has `#peerSelect` dropdown — picks up `.ranger-select` styling. |
| Map | OK | Leaflet map with score-color markers, asset-sized. Has its own `#mSearch`, asset/score/geo/county/holdco filters. |
| Outreach List | **Drift** | Composite renders plain `fmtNum` (line 1145), no `shv-trigger`. CSV export works. |
| Methodology | **Drift** | Static HTML weight tables (lines 507-543) do not reference `MA_WEIGHTS`. When user retunes weights via the drawer, methodology copy keeps showing the v2 defaults. Three dynamic injection points exist (`#planBlock`, `#rank-audit`, `#coverageBlock`) for plan + rank audit + contacts, but weights remain hardcoded. Hardcoded "95-bank universe" (line 518), "71 of 95" (line 566), "Only 2 of 95 targets are SEC-registered" (line 565). |

**Filter coupling:** per-view, not global. Rankings/outreach/map each have separate text inputs (`#search`, `#oSearch`, `#mSearch`). Switching views does not preserve search state — generally fine for this dashboard's workflow.

**CSV export:** only on Rankings (line 848) and Outreach (line 1160). Top-20, valuation, peer, map, county-summary have **no export**.

**Empty states:** not explicitly handled. Filtering to zero rows in Rankings leaves the table header visible with an empty body. Acceptable.

---

## 3. CRE Prospecting (TX) — `dashboards/cre/cre-dashboard-tx.html`

View activation via inline `onclick="setView('home'|'table'|...)"` (lines 438-444). `setView()` at line 1276 toggles `.active`/`.visible`/`.hidden` and dispatches to the appropriate renderer.

| View | Status | Notes |
|---|---|---|
| Home | OK | `renderHome()` line 1075 — Hot Leads + Recent Deeds. **Drift:** score badges on Home (lines 1112, 1133) **do not have `shv-trigger`** — no hover breakdown. |
| Table | OK | `renderTable()` line 913. Score badge uses `shv-trigger` (line 928). |
| Owners | **Drift** | Score badges in Owners view (lines 1174, 1184) **do not have `shv-trigger`** — no hover breakdown. |
| Pipeline | **Drift** | Pipeline cards (line 1232) **do not have `shv-trigger`**. Pipeline view is NOT re-rendered on filter change (it shows saved leads, not `filtered`). This is intentional but should be documented. |
| Charts | OK | Custom canvas 2D drawings (not Chart.js): `chartCounty`, `chartValDist`, `chartTypeBar`, `chartSubtype`, `chartYrDist`, `chartOwner`, `chartScoreDist`. All re-render via `drawAllCharts()` (line 1385) on filter change. **Drift:** no axis units, no freshness indicator, no chart subtitles. |
| Map | OK | Leaflet map via `renderMap()` line 1246. Re-renders on filter change. |
| Method | **Drift** | Static HTML — scoring rubric prose ("$10M+ = 30pts...", line 558) is duplicated outside `CRE_WEIGHTS`/`calcScore()`. If weights drawer adjusts max points, prose stays stale. Hardcoded counts: "Loading 162,109 properties" (line 296), header subtitle "162,109 properties · 32 Texas Counties" (line 307). |

**NEW (fixed in this audit):** Select All/None buttons on County (32 boxes) and Property Type (3 boxes) filter groups via the new shared `bulk-toggle.js`. The existing Sub-Type all/none button was migrated to the same shared utility for consistency.

**Filter coupling:** `applyFilters()` (line 869) rebuilds `filtered`, calls `renderTable()` + `updateStats()`, then conditionally re-renders the currently visible panel. Pipeline view is the exception.

**Empty states:** when filters return zero properties, the chart canvases render with no bars and no message. Should display "No properties match the current filters" instead.

---

## 4. Physician (TX) — `dashboards/physician/TX_Physician_Dashboard.html`

Uses `data-tab` buttons + inline `onclick="switchTab(...)"`. `switchTab()` lines 707-724. Active-tab matching uses `textContent.toLowerCase().replace(/\s/g,'')` — fragile if labels are renamed.

| Tab | Status | Notes |
|---|---|---|
| Dashboard | OK | Charts c1-c6 destroyed and rebuilt on every activation (line 1075). Re-renders on filter via `go()` → `renderAll()`. |
| Directory | OK | Score badges use `shv-trigger` (lines 632-635). |
| Call List | OK | Only populated on `generateCallList()` button click (line 1255). |
| Insights | OK | `renderInsights()` (lines 1312-1396) — dynamic from filtered set. |
| Methodology | **Drift** | Pure static HTML with hardcoded point allocations ("25pts, 20pts, 15pts, 5pts" line 465, "Solo=20, small group=12" line 477). Does not reference `PHYS_WEIGHTS`. No date stamp / freshness indicator. |

**Bug (separate):** `applyFilters()` is referenced at lines 913 and 921 (Select-All/Clear-All on checkbox dropdowns) **but is never defined**. Silent ReferenceError — bulk Select-All/Clear-All on the metro/city/specialty checkbox dropdowns currently does nothing. Listed as a follow-up fix (not addressed in this audit; out of scope for the prompt's "Select All/None on CRE").

**Resize handler:** debounced full `charts()` rebuild on resize (line 1414) — expensive when on directory/insights tabs where charts aren't visible.

---

## 5. Physician Underwriting — `dashboards/physician-underwriting/specialty-benchmarks.html`

Standard `data-tab` button pattern. `switchTab(name)` at lines 1175-1179.

| Tab | Status | Notes |
|---|---|---|
| Overview | OK | `renderTable()` populates `#tbl-body`. |
| Detail | OK | Row-click triggers `selectSpecialty()` + `switchTab('detail')`. |
| Comparison | OK | Bound to `#btn-evaluate` button. |
| Geographic View | **Drift** | `renderGeo()` invoked once on init (line 1568) — does not re-render when filters change. HTML `<table>`s with static `<span>` data-vintage labels (e.g. line 505 "Doximity 2025 (CY2024 data)"). |
| Methodology | **Drift** | Entirely static — hardcodes "7,300+ physicians" (line 577), "37,000+ surveys" (586), "Conversion factor: $32.7442" (612). None pulled from live state. |

**Filter coupling:** filters only re-render Overview. Detail/Comparison/Geo are triggered by separate actions.

**Stale stat card (BUG):** Line 279 `<div class="stat-value">29</div>` "Specialties Tracked" — but the `SPECIALTIES` array contains 33 entries. Header meta line 257 also reads "29 specialties". **Cosmetic bug — should be `${SPECIALTIES.length}` populated at load.** Not fixed in this audit; listed as follow-up.

**No charts** in this dashboard — Geographic View uses HTML tables, Payer Mix uses a custom flex-bar (line 1230). Not applicable to the chart audit.

---

## Cross-cutting findings

### Shared modules now in `dashboards/shared/`
| Module | Status |
|---|---|
| `score-hover.{js,css}` | **FIXED** — inline `opacity:0` was defeating the `.shv-show` class rule via specificity. Now hover tooltips work on every dashboard. Also fixed `pointer-events:none` paradox so the keep-alive-on-hover handler can actually fire. |
| `score-weights.{js,css}` | OK |
| `filter-chips.{js,css}` | OK |
| `column-picker.{js,css}` | OK |
| `dual-range.{js,css}` | OK |
| `resizable-cols.{js,css}` | OK |
| **`bulk-toggle.{js,css}`** | **NEW** — declarative `<span data-bt-group=".ccd" data-bt-after="applyFilters">` syntax. Renders All/None buttons + a count pill. Wired into CRE for County, Property Type, and Sub-Type. |
| **`ranger-select.{js,css}`** | **NEW** — auto-applies `.ranger-select` class to every native `<select>` on the page (opt-out via `.no-ranger-select`). Linked into all 5 dashboards. |

### Recurring drift patterns
1. **Static methodology tabs** — every dashboard except Deposit ships hardcoded counts/weights/dates in the methodology panel. Should be migrated to a `renderMethodology()` pattern mirroring what was built for Deposit.
2. **Top-N cards rendered once** — both M&A Top-20 and Physician Underwriting Geographic only render on first activation. Should re-render on data change.
3. **Score-hover only on primary views** — table-row score badges have `shv-trigger`, but the same scores rendered in summary cards, pipeline boards, or owners views do not. The fix is mechanical: ensure every place a score is shown carries the hover attributes.
4. **No data-freshness indicator** — Deposit has the freshness ribbon; the other four dashboards do not surface "data is current as of …" anywhere on screen. M&A is the most data-rich and most overdue for this.

### Follow-up issues created (recommend filing as tickets)
1. M&A Top-20 cards don't re-render when `MA_WEIGHTS` change — `delete cont.dataset.rendered` before re-render or drop the guard.
2. M&A Outreach list and Top-20 cards should use `shv-trigger` for composite scores.
3. CRE Home / Owners / Pipeline score badges should use `shv-trigger`.
4. CRE charts should add subtitles + axis-unit labels (deferred — see `CHART_GRADE.md`).
5. Physician `applyFilters()` is undefined but referenced at lines 913/921 — define it or remove the calls.
6. Physician Underwriting "29 specialties" should be `${SPECIALTIES.length}` (currently shows 29; array has 33).
7. Each dashboard's methodology tab should be rewritten as a `renderMethodology()` function that reads from live state.

### Summary

**What's working after this audit:**
- Score-hover tooltip is alive again across all 5 dashboards (root-cause fix in shared CSS).
- CRE filter sidebar has Select All / None on every multi-checkbox group via the new shared utility.
- All native `<select>` elements share the same compact (30px) styling via the new shared CSS+JS.

**What still has drift but isn't broken:**
- Methodology tabs are still static text on 4/5 dashboards.
- Several score-badge render paths skip `shv-trigger` (documented above).
- No freshness indicator outside Deposit.

**What is broken:**
- Physician dashboard's `applyFilters()` ReferenceError.
- Physician Underwriting hardcoded "29" specialty count.

Neither broken item is in scope for the original prompt's three named bugs. Both are filed as follow-ups in the list above.
