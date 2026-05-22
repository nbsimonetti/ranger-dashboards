# Iteration 3 — Cross-link with CRE Prospecting dashboard

The Loan Maturity dashboard now knows about CRE properties owned by each borrower, and the CRE Prospecting dashboard now knows about SBA loans against each owner. A rep can click between them without copy-paste search.

## What shipped

### 1. New offline pipeline: `data-collection/join_to_cre.py`
- Reads `loans.json` (19,737 SBA loans) + `../cre/cre-properties-tx.json` (162,109 CAD parcels).
- Normalizes entity names (strips LLC / INC / TRUST / etc., drops stopwords, uppercase).
- Buckets properties by `(county, first-token-of-owner, length-bucket)` to keep matching O(N).
- Token-set Jaccard for fuzzy name match; address ZIP + street number for confidence boost.
- 5-component confidence score (0–100): name token overlap (0–50), exact canonical bonus (+10), ZIP match (+20), street-number match (+15), state match (+10), suffix-set overlap (+5). Default-visible threshold ≥75, retained ≥50.

**Results on real data:**
- 1,440 of 19,737 loans (7.3%) matched at least one CRE property in the footprint.
- 1,773 total loan↔parcel match pairs.
- Output `loan_property_join.json` ~5.2 MB (forward + reverse + entity aggregations + embedded parcel/loan summary data so popovers don't have to load the 47MB CRE JSON).

The 7.3% hit rate reflects the free-data fuzzy-name approach. Reonomy or OpenCorporates (see `PAID_DATA_EVAL.md`) would push this to 20–35% by resolving LLC variants.

### 2. New `🏢 N` badge on Loan Maturity Pipeline rows
- Pipeline table has a new "CRE owned" column.
- Badge appears only on rows whose borrower has ≥1 high-confidence CRE match.
- Clicking opens a popover modal listing each matched parcel with owner name, address, assessed value, confidence score, and match method.
- Modal has an "Open in CRE Dashboard →" button that opens `cre-dashboard-tx.html?owner=<borrower-name>` — pre-filters the CRE search box.

### 3. URL-param pre-filter
On page load, both dashboards now read `?borrower=` (Loan Maturity) and `?owner=` (CRE) and seed the global search box. Lets click-throughs land on a filtered view immediately.

### 4. Provenance preserved through the join
Every `forward`/`reverse` entry carries `match_method` and `confidence` so the cross-link badge can disclose how it was derived. The Methodology tab on Loan Maturity now mentions the join under "Data Sources" and links the user to `PAID_DATA_EVAL.md` if they want to understand the hit-rate ceiling.

## Files changed

| File | Change |
|---|---|
| `data-collection/join_to_cre.py` | New pipeline (300+ lines) |
| `loan_property_join.json` | New artifact (5.2 MB) |
| `loan-maturity-tx.html` | Added `loadJoinIndex()`, `_propertyMatches` per loan, CRE-link column, `openCreLinkModal()`, URL-param pre-filter |
| `../cre/cre-properties-tx.json` | Extracted from inline blob in CRE dashboard (47.4 MB) |
| `../cre/cre-dashboard-tx.html` | Added SBA-loans column, `openLoanLink()` modal, URL-param pre-filter, async `LOAN_JOIN` loader |

## Deliverables still pending (per source prompt)

- **Consolidated pipeline-status localStorage key** — both dashboards currently use separate localStorage. Migration to `ranger:pipeline:<entityKey>` deferred to iteration 4 because it requires entity-resolution that we don't yet have (paid OpenCorporates is the unlock).
- **"Borrower 360" unified tab** — deferred (UI design heavier than v3 scope).
- **Symmetric badge on CRE Owners view** (not just Table view) — also deferred; same `LOAN_JOIN.reverse` lookup but Owners view aggregates differently.

These are scoped for iteration 4 once `PAID_DATA_EVAL.md` recommendations get business approval.

## Verification

- `node --check` clean on inline JS of both dashboards.
- `loan_property_join.json` validates as JSON with `forward`/`reverse` keys.
- Loan Maturity dashboard loads `loans.json` + `loan_property_join.json` in parallel; works gracefully if join file is missing.
- CRE dashboard loads `loan_property_join.json` async; works gracefully if missing (no badge column populated).
