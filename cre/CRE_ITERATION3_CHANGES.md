# CRE Prospecting — Iteration 3: Cross-link with Loan Maturity dashboard

The CRE Prospecting dashboard now shows which property owners have active SBA loans in our footprint, with a one-click jump to the Loan Maturity dashboard pre-filtered to that borrower.

## What shipped

### 1. New "SBA loans" column on the Table view
- Reads `../loan-maturity/loan_property_join.json` (5.2 MB) async on page load. Dashboard works if the file is missing.
- For each parcel row, looks up `LOAN_JOIN.reverse[parcel_id]` to find any SBA loans matched to the owner.
- Renders a `💵 N · $X.XM` badge when matches exist. Click opens a modal listing every matched loan with borrower, lender, loan $, maturity date, and confidence score.

### 2. Loan-detail modal (built on click)
- Lists each matched SBA loan for the parcel sorted by confidence.
- Includes "Open in Loan Maturity Dashboard →" button that links with `?borrower=<name>` query param.
- Lower-confidence rows render dimmed.
- Adds no permanent DOM weight when not clicked (modal is built on first open).

### 3. URL-param pre-filter
- Page reads `?owner=` on load and seeds the global search box.
- Lets click-throughs from Loan Maturity land on a filtered view.

### 4. Data extraction artifact
- The previously-inline `var ALL=[...]` blob (162,109 properties) was extracted to `cre-properties-tx.json` (47.4 MB) so it could be read by the offline join pipeline (`../loan-maturity/data-collection/join_to_cre.py`). The dashboard itself still loads from the inline blob — no change to runtime data path.

## Files changed

| File | Change |
|---|---|
| `cre-dashboard-tx.html` | Added "SBA loans" table column, `openLoanLink()` modal builder, async `LOAN_JOIN` fetcher, URL-param pre-filter |
| `cre-properties-tx.json` | New sibling JSON (used by join pipeline only; dashboard runtime still uses inline blob) |

## What's NOT changed

- No change to filter sidebar, score weights, charts, or map.
- No change to the inline `ALL` data blob — still the source of truth for the dashboard's runtime.
- Pipeline-saving feature (the existing star button) still uses its own localStorage key. Consolidation with the Loan Maturity dashboard's status key is deferred to iteration 4 (needs entity resolution).

## Verification

- `node --check` clean on extracted inline JS.
- CRE dashboard loads cleanly if `loan_property_join.json` is missing (badge column shows `—` for every row).
- Cross-link click goes to `../loan-maturity/loan-maturity-tx.html?borrower=<NAME>` and the borrower is pre-filtered.
