# Iteration 2 — CRE-Head Critique + Improvements

After building v1, I stepped into the shoes of a head of CRE at a community bank and walked through the dashboard with one question: *"could I actually open this Monday morning and produce a list of 20 borrowers I should call this week?"* The answer to v1 was *"sort of — but I'd have to do too much mental work."* These are the changes that moved it to *"yes."*

---

## 1. Lead every screen with dollars, not row counts

**v1:** Stat cards on Overview were borrower count / lender count first. Pipeline table sorted by score.

**v2:** Top stat card is now `Total $ rolling off`. `Maturing ≤12 mo` card shows the dollar total alongside the row count. Top Lenders chart was already $-sorted; By Borrower and By Lender tabs now both sort by total $ descending. The Maturity Wall stacks dollars (not loan count).

**Why a CRE head cares:** 50 small loans at $250K each is roughly half the revenue opportunity of 5 loans at $5M. If row count drives the eye, the rep wastes their best hours on small fish.

## 2. Sister-loan signaling per borrower

**v1:** Borrower concentration only existed inside the Opportunity Score's components.

**v2:** Every pipeline row now shows a `Sister loans` cell: `👥 +N` purple badge for borrowers with multiple loans on the platform, or `—` for single-loan borrowers. Hover surfaces the count.

**Why a CRE head cares:** A borrower with 3 SBA loans rolling off in 18 months is a relationship play, not a one-loan refi. The conversation, the term sheet, and the credit committee pitch are all different. The dashboard now flags this at a glance.

## 3. Rate Δ vs current market

**v1:** Pipeline showed `Rate` as a plain number.

**v2:** New `Rate Δ` column shows the loan's origination rate **and** its delta vs a `MARKET_BENCHMARK_RATE` constant (10.5%, current SBA Prime + spread). Positive Δ in green ("borrower is paying above market — easy displacement"); negative Δ in red ("borrower has a cheap loan, they will fight to keep it"). Tooltip on hover explains the math.

**Why a CRE head cares:** This is the conversation hook. "Mr. Borrower, you're paying 7.8% on a 5-year-old loan and the current refi market is 10.5% — but Ranger can structure a deal that beats both your current payment and the prevailing market." The dashboard now puts that opening line in the rep's mouth.

## 4. Branch proximity column

**v1:** Geo fit was a binary score-component (in footprint or not).

**v2:** New `Branch dist` column shows the haversine miles from the county centroid to the nearest of 4 Ranger branch anchors (DFW, Austin, Houston, San Antonio). Sortable. This makes "which prospects can I reasonably take to lunch this month" a one-click sort.

**Why a CRE head cares:** A 60-mi drive vs a 300-mi flight is the difference between an in-person pitch and an email blast. Real conversion rates track distance.

## 5. Borrower address tooltip

**v1:** Borrower cell showed only name + city.

**v2:** Hover the borrower name → full mailing address (street + city + state + zip) surfaces as a `title=` tooltip. The address ships with every SBA record; we were already storing it.

**Why a CRE head cares:** Inside-out, the prospect list dies on contactability. The dashboard now feeds the address directly into the same hover muscle reps already use for scores.

## 6. Recency-of-origination filter

**v1:** No filter for loan age.

**v2:** New `Originated Within` filter section in the sidebar with 4 buckets (≤2y / 2–5y / 5–10y / 10y+). Each carries a live count. Defaults to all checked.

**Why a CRE head cares:** A loan originated 18 months ago that matures in 9 months is a **balloon refi candidate** — the borrower knew this day was coming, has been shopping for 6 months, and is actively comparing offers. A loan originated 9 years ago that matures in 6 months is a **full-term refi** — the borrower may have never refinanced in their life and will move on relationship terms, not price. Different sales motion. The filter lets reps slice on which world they're in.

## 7. Pipeline status tracking (localStorage)

**v1:** No way to mark progress on a prospect.

**v2:** Every pipeline row has a `Status` dropdown with 6 options (Not contacted / Contacted / Meeting set / Proposal sent / Won / Lost). Color-coded border on the dropdown matches the status. Status persists per-loan in `localStorage` under key `rangerLoanMaturity:status`. New filter section (`Pipeline Status`) lets the user hide closed/lost rows. Defaults to showing only `new / contacted / meeting / proposal`.

**Why a CRE head cares:** Without state tracking, the rep is comparing today's list against last Monday's list manually. With persistence, the dashboard becomes the prospect log. CRM-lite for a job that doesn't need a CRM.

## 8. Lender concentration view (deferred)

**v1:** By Lender tab shows total $ exposure per lender, sorted by $.

**v2 status:** Already adequate — the By Lender tab IS the lender-concentration view. Considered adding a Herfindahl index or top-3 lender share but decided it would be vanity. The sort-by-$ table is the actionable read.

## 9. Maturity wall chart on Overview

**v1 and v2:** Already on Overview as `ch-wall`, stacked bars by quarter showing $ rolling off split by source. Y-axis is dollars. ✓ no change needed.

## 10. Honest per-county coverage on Methodology

**v1:** Counties listed with their loan count.

**v2:** Methodology tab additionally lists the four blocked source categories (UCC, county clerks, Texas Open Data, EDGAR CMBS) with the specific reason each is blocked. The COVERAGE.md sidecar document repeats this with file-level numbers from the actual pull.

## Items deferred to a future iteration

- **EDGAR CMBS 10-D parsing** — per-trustee table format variance is a real engineering lift; deferred until a CRE head explicitly requests CMBS-secured loans (which they probably won't since CMBS borrowers don't typically refi at community banks).
- **HMDA business-purpose** — small subset (1-4 unit dwellings); estimated <5% of decision value. Build only when SBA coverage is exhausted.
- **Sortable headers on the new columns** — partially supported via the shared `sortable-table` module's auto-attach (text comparison works on Rate Δ and Branch dist; the Sister-loans column needs a `data-sort` override to sort by the numeric value behind the `👥 +N` badge). Filed as a small follow-up.
- **Click-through to the borrower's website / phone** — SBA dataset has neither; would require a Google Places API key.

---

## Files changed in this iteration

| File | Change |
|---|---|
| `loan-maturity-tx.html` | Added 2 sidebar filter sections (origination age, pipeline status), 3 new pipeline columns (Rate Δ, Sister loans, Branch dist), status dropdown per row, 2 helper functions (`haversineMi`, `nearestBranchMiles`), 3 new per-loan computed fields (`_origAgeMonths`, `_rateDelta`, `_sisterCount`, `_status`), branch-proximity constants, MARKET_BENCHMARK_RATE constant, localStorage persistence for statuses |
| `LOAN_MATURITY_ITERATION2_CHANGES.md` | This document |

The data pipeline (`pull_sba.py`, `merge_loans.py`) was not touched during iteration 2 — the changes are all rendering/UX/filtering. The same `loans.json` feeds both v1 and v2.
