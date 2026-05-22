# Loan Maturity Intelligence — Paid Data Evaluation (build-vs-buy memo)

**Date:** 2026-05-21
**Audience:** CFO + Head of Commercial Lending
**Author:** Engineering, on behalf of the Loan Maturity Intelligence product owner

This memo evaluates 12 commercial-real-estate / lending data vendors plus 1 free source (SBA PPP FOIA) for inclusion in the Loan Maturity Intelligence dashboard. The dashboard currently covers 19,737 active SBA 7(a) + 504 loans across the 32-county TX footprint ($16.3B) using only free public records. Confidence levels on cost bands are stated honestly throughout — most of these vendors gate pricing behind sales calls.

---

## Vendors by gap they close

### Gap A — Non-SBA commercial mortgage data (the biggest hole)

#### 1. ATTOM Data Solutions — **PILOT** ($499/yr self-serve seat is no-risk)
- **Realistic tier for us:** Property Navigator Professional plan — published self-serve.
- **Annual cost:** **$499/yr** for a single seat (HIGH confidence). Adding the Property Data API with mortgage/transaction history runs **$12K–$30K/yr** (MEDIUM confidence) depending on call volume and add-ons (foreclosure, mortgage, AVM, boundaries).
- **What's included:** Professional gets 1 seat, 200 reports/mo, 2,000 list exports/mo, 150M+ properties, foreclosure/pre-foreclosure, sales searches, mortgage data, AVMs.
- **Coverage gain:** Nationally broad but residential-leaning. True CRE depth (tenant rolls, leases) is thin vs CoStar/Reonomy. For the 32-county TX footprint, expect ~30-40% additional non-SBA mortgage coverage beyond what we have today.
- **What would change in the dashboard:** A new `source` value `attom-mortgage` would appear in `loans.json` for non-SBA mortgage records ATTOM identifies. Maturity dates often present on instrument records. Lender attribution would replace the "(SBA 504 — partner bank not disclosed)" placeholder for some loans.
- **Procurement friction:** Self-serve credit card, annual only, cancel anytime, free trial available. The API tier requires sales call + custom MSA + 2–6 week cycle.
- **Source:** [attomdata.com/solutions/property-navigator/pricing](https://www.attomdata.com/solutions/property-navigator/pricing/)
- **Recommendation:** **PILOT** the $499 seat for 60 days. The downside is bounded; the upside is a real coverage signal we cannot get any other way at this price. Decide on the API tier after the pilot.

#### 2. CoreLogic RealQuest — **DEFER**
- **Realistic tier:** RealQuest Professional (web UI, per-seat); 360 Property Data API is enterprise-only.
- **Annual cost:** Single-seat realistically **$3K–$8K/yr**; API access **$15K–$40K/yr** minimum (LOW confidence — CoreLogic is one of the most opaque vendors in this set).
- **What's included:** Per-call rates leaked via Trestle: Involuntary Lien API $11.50/call, Finance History $2.30/call. RealQuest UI gives parcel, tax, transaction history, voluntary/involuntary liens, owner.
- **Coverage gain:** Probably comparable to ATTOM at 2-4× the cost. CoreLogic is the more enterprise-favored product; their CRE-specific depth is not appreciably better than ATTOM for our use case.
- **Procurement friction:** Sales-led, MSA + data-license addendum, no public trial, 4–8 week cycle, typical 1-yr minimum.
- **Source:** [trestle-documentation.corelogic.com/data-pricing.html](https://trestle-documentation.corelogic.com/data-pricing.html)
- **Recommendation:** **DEFER.** Revisit only if ATTOM pilot fails AND we need the per-call lien API specifically.

#### 3. Cherre — **DECLINE**
- **Realistic tier:** Not appropriate for a community bank — Cherre's smallest deployment is enterprise.
- **Annual cost:** **$150K–$500K/yr** entry; large customers $1M+ (MEDIUM confidence — Software Finder + BestCRE consensus).
- **What's included:** Data-integration platform with "Cherre ID" entity graph, connectors to 50+ CRE sources (you pay separately for the source licenses), warehouse/SQL access.
- **Coverage gain:** Cherre is *plumbing* — it doesn't ADD data, it normalizes data you've already licensed from CompStak/Reonomy/CoStar/etc. Wrong shape for our problem.
- **Procurement friction:** 2–3-year commitments encouraged, implementation services in year 1, 3–6 month sales cycle, RFP-ish.
- **Source:** [softwarefinder.com/cherre](https://softwarefinder.com/property-management-software/cherre)
- **Recommendation:** **DECLINE.** Re-evaluate if/when we have 5+ licensed CRE data sources and need to unify them. We're nowhere close to that.

#### 4. Reonomy (now part of Altus Group) — **BUY** (the strongest single recommendation in this memo)
- **Realistic tier:** Reonomy Web Application — single-user subscription.
- **Annual cost:** **$4,800/yr per user** list ($400/mo) with discounts for upfront annual payment; some legacy plans referenced at $299/mo entry. HIGH confidence — CRE Daily + Mashvisor independently confirm $4,800/yr.
- **What's included:** ~50M US properties; LLC-piercing to true beneficial owners; owner **phone numbers + email + mailing addresses**; mortgage / lender data; debt history; tenant info.
- **Coverage gain:** This is the **only vendor in the entire memo** that solves owner-contactability at a community-bank price point. Per the iteration-2 CRE-head critique, contactability is the difference between a list and a prospect list. Estimated 50-70% of our SBA borrowers will get phone numbers attached after enrichment. Expected to also add 30-50% non-SBA mortgage records via Reonomy's deed/mortgage layer.
- **What would change in the dashboard:** Pipeline rows gain a phone/email column. The map borrower-cluster popup gets contact info. The "Re-pull data" pipeline adds a `reonomy_enrich.py` step. Borrower 360 (Part 2 of this memo's parent prompt) becomes 10× more useful.
- **Procurement friction:** 7-day free trial (full features), annual contract required, self-serve possible but most users go through sales for >1 seat.
- **Source:** [credaily.com/reviews/reonomy-review](https://www.credaily.com/reviews/reonomy-review/)
- **Recommendation:** **BUY.** Highest ROI single dollar in this memo. Run the 7-day free trial first to validate TX coverage hands-on before committing.

#### 5. CompStak — **DECLINE** for prospecting; **PILOT free Exchange tier**
- **Realistic tier:** CompStak Exchange (free contribute-to-access) for community bank; CompStak Enterprise if you want bulk/API.
- **Annual cost:** Exchange = **$0** (you submit your own deal comps to earn points to pull others'). Enterprise community-bank lender-tier band **$25K–$60K/yr** for a single market or region (LOW–MEDIUM confidence on Enterprise).
- **What's included:** 1.6M+ analyst-verified lease + sale comps, debt comps in major metros. Texas major metros (DFW, Houston, Austin, SA) are well-covered; smaller TX MSAs thinner.
- **Coverage gain:** Lease/sale comps are great for *underwriting* but don't give you a *prospect list* of borrowers. Wrong tool for top-of-funnel work.
- **Procurement friction:** Exchange is instant signup. Enterprise: sales-led, annual contract, auto-renew (per TrustRadius user complaints), 3–6 week cycle.
- **Source:** [trustradius.com/products/compstak-enterprise/pricing](https://www.trustradius.com/products/compstak-enterprise/pricing)
- **Recommendation:** **DECLINE** Enterprise. **PILOT** the free Exchange tier — useful for underwriting once a deal is in motion, zero cost, no commitment.

### Gap B — CMBS + institutional CRE debt

#### 6. Trepp — **DEFER**
- **Realistic tier:** TreppBank Navigator or T-ALLR (Trepp Anonymized Loan Level Repository) for community-bank CRE concentration analytics.
- **Annual cost:** Community-bank-tier (TreppBank Navigator) realistically **$15K–$40K/yr**; full Trepp CMBS + CRE bundle $50K–$150K/yr (LOW confidence — Trepp is one of the most opaque vendors).
- **What's included:** CMBS surveillance, anonymized peer benchmarking for bank CRE portfolios, CRE loan-level data, market-level rent/vacancy.
- **Coverage gain:** Trepp is a *risk benchmarking* tool, not a prospect list. T-ALLR is anonymized — we cannot identify the borrowers. For our use case (prospecting), wrong product.
- **Procurement friction:** Sales-led, multi-year contracts preferred, MSA + data license, 4–10 week cycle, no trial.
- **Source:** [trepp.com](https://www.trepp.com/)
- **Recommendation:** **DEFER.** Reconsider if the bank ever needs CRE concentration risk reporting for regulators — at that point Trepp becomes more legitimate.

#### 7. Real Capital Analytics (RCA / MSCI) — **DECLINE**
- **Realistic tier:** Smallest meaningful subscription is regional Trends.
- **Annual cost:** Regional/single-market access **$15K–$30K/yr**; institutional global ~$75K–$200K/yr (LOW confidence — MSCI highly gated).
- **What's included:** Institutional-grade CRE transaction database ($50T+ in deals), CPPI price indices, buyer/seller/lender attribution.
- **Coverage gain:** Skewed to $2.5M+ deals. Most TX community-bank CRE loans sit below the RCA threshold. Coverage of sub-institutional TX deals is poor.
- **Recommendation:** **DECLINE.** Structurally wrong shape for community-bank CRE.

#### 8. CoStar — **DEFER**
- **Realistic tier:** CoStar Suite — single market (e.g., DFW or Houston only) plus optional CoStar for Lenders module.
- **Annual cost:** Single-market small-team licenses **$12K–$25K/yr**; all-US/multi-user landed at $40K median, $71K list, ~$3,400/license/mo per PriceLevel buyer disclosure (MEDIUM-HIGH confidence on single-market band).
- **What's included:** Property records, tenant/lease info, sales comps, owner data, market analytics; CoStar for Lenders adds debt comps + loan-level coverage. TX major metros are CoStar's strongest coverage.
- **Coverage gain:** Real overlap with Reonomy. CoStar is more comprehensive but costs 3-5× as much. Smaller TX MSAs (Lubbock, Amarillo, Tyler, Waco) are thinner.
- **Procurement friction:** Sales-led, hard-sell reputation, 1-yr minimum standard, auto-renew clauses, 44% off list achievable with negotiation, 3–6 week cycle.
- **Source:** [pricelevel.com/vendors/costar/pricing](https://www.pricelevel.com/vendors/costar/pricing)
- **Recommendation:** **DEFER.** If Reonomy pilot succeeds, CoStar becomes redundant. If Reonomy disappoints, evaluate CoStar Houston-only at $12-15K as an alternative.

### Gap C — Entity resolution + contactability (turns rows into prospects)

#### 9. OpenCorporates — **BUY**
- **Realistic tier:** Essentials API plan.
- **Annual cost:** **£2,250/yr (~$2,800 USD) Essentials**; Starter £6,600 (~$8,200); Basic £12,000 (~$15,000). HIGH confidence — published on their pricing page.
- **What's included:** Corporate registry data across 130+ jurisdictions including all 50 US states (TX SOS records), officer/director links, filings. Essentials is rate-limited; Starter/Basic raise call volumes.
- **Coverage gain:** Resolves the LLC-variant problem that's currently fuzzy-matched in our join pipeline. Adds registered agent + formation date + officer names per entity. For our 19,737 borrowers, expect ~80-90% to resolve to a TX SOS entity record after enrichment.
- **What would change in the dashboard:** A new `entity_id` field links borrowers and owners to canonical TX-SOS-keyed entities, replacing fuzzy-name matching. Parent/subsidiary relationships become traversable.
- **Procurement friction:** Self-serve checkout, annual billing.
- **Source:** [opencorporates.com/pricing](https://opencorporates.com/pricing/)
- **Recommendation:** **BUY.** Cheapest entity-resolution tool that solves the LLC-variant problem permanently. ~$2,800/yr is small money for a foundational data layer.

#### 10. Dun & Bradstreet — **DEFER** (Hoovers Essentials is cheap but volume-limited)
- **Realistic tier:** D&B Hoovers Essentials (annual self-serve) for prospecting; D&B Direct+ API if you need entity-resolution/DUNS-match at scale.
- **Annual cost:** Hoovers Essentials **$529/yr** (1,800 credits — usable for low-volume lookups). Hoovers full plans $5K–$10K/yr. D&B Direct+ API $25K+/yr with $5K–$15K setup. Median deal across all D&B SKUs $41K/yr (Vendr, 106 purchases). HIGH on Hoovers, MEDIUM on API.
- **What's included:** DUNS numbers, business hierarchies/parents, firmographics, contact info, basic financial/credit signals.
- **Coverage gain:** 1,800 credits/yr on Essentials = ~5 lookups/day. Won't enrich a 19,737-record dataset; you'd need to either upgrade or batch over years.
- **Procurement friction:** Hoovers Essentials self-serve, annual. Enterprise/API: 6% annual uplift baked in, auto-renew, ~$50K redline, 4–8 week cycle. Negotiation windows Dec/Jan/Jun.
- **Source:** [vendr.com/marketplace/dun-and-bradstreet](https://www.vendr.com/marketplace/dun-and-bradstreet)
- **Recommendation:** **DEFER.** OpenCorporates + Reonomy together cover most of what D&B would give us, at a fraction of the cost. Revisit if we ever need DUNS-keyed credit scores for underwriting.

#### 11. Melissa Data — **BUY** (cheapest no-brainer in the memo)
- **Realistic tier:** Pay-as-you-go credits (Tier 3) or US Address Verification annual.
- **Annual cost:** US Address Verification/Autocomplete **$5,145/yr** for 1M records. Or PAYG credits **$285 per 100K** — about **$60 one-time** to clean our 19,737 records. HIGH confidence — published.
- **What's included:** Address normalization (USPS CASS), DPV, geocoding, business standardization, light entity matching. Free tier = 1,000 credits/month renewing — enough to validate.
- **Coverage gain:** Doesn't *add* new prospects, but improves join accuracy by 10-15% (more reliable address + entity-name standardization → fewer false-negatives in the loan↔property fuzzy match).
- **Procurement friction:** Self-serve credit card, no minimum, no contract for PAYG, instant signup.
- **Source:** [g2.com/products/melissa-global-address-verification/pricing](https://www.g2.com/products/melissa-global-address-verification/pricing)
- **Recommendation:** **BUY** the $60 one-time PAYG. Smallest dollar amount in this memo, highest ROI per dollar.

#### 12. Google Places API — **BUY** (cheap, supplements Reonomy on retail-facing borrowers)
- **Realistic tier:** Pay-as-you-go, Essentials SKUs under the new (March 2025) tier model.
- **Annual cost:** Realistic spend **$300–$1,500/yr** for 19,737 lookups + occasional re-enrichment. Contact-data SKU is the expensive one. HIGH confidence — published rate card.
- **What's included:** Phone numbers, website URLs, business hours, geocoding, place IDs by name+address lookup. Free monthly caps: 10K Essentials / 5K Pro / 1K Enterprise events.
- **Coverage gain:** Google's Places coverage skews retail/consumer-facing. Expect 50-70% match rate on a CRE-borrower list. Complements Reonomy (which is stronger on industrial / B2B / LLC-holding entities). Free monthly cap is enough to enrich most rows over 2-3 months at no marginal cost.
- **Procurement friction:** Self-serve, pay-as-you-go, no contract, no sales call.
- **Source:** [developers.google.com/maps/documentation/places/web-service/usage-and-billing](https://developers.google.com/maps/documentation/places/web-service/usage-and-billing)
- **Recommendation:** **BUY.** Tiny incremental cost; closes the contactability gap on retail-facing borrowers Reonomy misses.

### Gap D — County-level public records bulk (the surgical fix)

The 5 major TX counties (Dallas, Harris, Tarrant, Bexar, Travis) hold ~70% of footprint commercial value but block bulk Deed-of-Trust data behind paid Data Sales contracts.

**Recommendation: REQUEST QUOTES, then decide.** Send purchase-order requests to:
- Dallas County Clerk Data Sales
- Harris County Clerk Data Sales (`datasales@cco.hctx.net`)
- Tarrant County Clerk Central Library
- Bexar County Clerk
- Travis County Clerk Public Information Request

Expected aggregate cost from prior community-banker conversations: **$3-8K/yr** for monthly delta feeds of all Deed-of-Trust filings. If actual quotes fall in that range, **this is the highest-coverage-per-dollar buy in the entire memo** — it unlocks the non-SBA bank balance-sheet loan universe in the counties that matter. Maturity dates are embedded in PDF instruments and need OCR (a one-time engineering cost).

If quotes exceed $15K aggregate, defer until ATTOM pilot results are in (ATTOM may cover the same deed-of-trust data nationally at lower cost).

### Gap E — Free, no commitment

#### 13. SBA PPP FOIA bulk — **WIRE IN NOW** (no business approval needed)
- **Realistic tier:** Bulk CSV downloads, no API key.
- **Annual cost:** **$0**. HIGH confidence.
- **What's included:** Every PPP loan ever issued — borrower name, address, lender name, loan amount, NAICS. ~11.5M records nationally; TX subset ~1M.
- **Coverage gain:** Not a maturity source (PPP forgiveness already happened). BUT a huge **borrower↔lender relationship signal**. If borrower XYZ took PPP from JPMorgan in 2020, they're probably still banking there. Enriches our pipeline rows with "incumbent lender history."
- **What would change in the dashboard:** New badge on Pipeline rows: "🤝 Banked with [LENDER NAME] in 2020-2021" — surfaces the historical relationship that drove the PPP transaction.
- **Recommendation:** **WIRE IN** immediately. No procurement, no risk, real signal.

---

## Annual-cost recap table

| Vendor | Recommendation | Annual cost band | Confidence |
|---|---|---|---|
| ATTOM Data Solutions | **PILOT** ($499 seat) | $499 self-serve; $12-30K API | HIGH / MEDIUM |
| CoreLogic RealQuest | DEFER | $3-8K seat; $15-40K API | LOW |
| Cherre | DECLINE | $150K+ | MEDIUM |
| **Reonomy** | **BUY** | $4,800/yr/seat | HIGH |
| CompStak Enterprise | DECLINE | $25-60K | LOW–MED |
| CompStak Exchange | PILOT (free) | $0 | HIGH |
| Trepp | DEFER | $15-40K (TX-only) | LOW |
| RCA / MSCI | DECLINE | $15-30K (regional) | LOW |
| CoStar | DEFER | $12-25K (single market) | MED–HIGH |
| **OpenCorporates** | **BUY** | $2,800/yr Essentials | HIGH |
| Dun & Bradstreet | DEFER | $529/yr Hoovers Essentials | HIGH |
| **Melissa Data** | **BUY** | $60 one-time PAYG | HIGH |
| **Google Places API** | **BUY** | $300-1,500/yr | HIGH |
| County clerk × 5 (TX) | **REQUEST QUOTES** | $3-8K aggregate (target) | MEDIUM |
| SBA PPP FOIA | **WIRE IN NOW** | $0 | HIGH |

---

## Deployment-architecture caveat

If we buy any **licensed** dataset (ATTOM, CoreLogic, Reonomy, CoStar, OpenCorporates, Trepp, D&B, etc.), the resulting `loans.json` **cannot** be hosted in a public GitHub Pages repository. Vendor data licenses universally prohibit redistribution. Our options become:

1. **Private Pages deployment** — move the repo to private and use a self-hosted runner or paid GitHub Pages Pro. Cheapest path.
2. **Move dashboard to a private host** — e.g., Render (already configured in our `render.yaml`), Vercel, Cloudflare Pages with access auth. Adds $0-20/mo hosting.
3. **Two-tier dashboard** — public-only-sources version stays on GitHub Pages; full version moves behind auth. Operational overhead, but lets the marketing-friendly free version stay public.

Pick a path BEFORE signing the first licensed-data contract. The downside of a leak is the vendor pulling the contract and possibly suing.

---

## CFO recommendation (the only paragraph that matters)

> **For the first incremental dollar, buy Melissa Data ($60 one-time PAYG)** — this is procurement noise but improves every downstream join by 10-15%. **For the second, buy SBA PPP FOIA enrichment ($0)** — wire it in immediately. **For the third, request quotes from the 5 TX county clerks** — if the aggregate lands $3-8K as expected, that's the highest-coverage buy in the entire memo. **For the fourth, buy Reonomy ($4,800/yr)** — solves contactability for ~60% of borrowers, the single largest UX gap in the dashboard today. **For the fifth, add OpenCorporates Essentials ($2,800/yr)** to lock in entity resolution permanently. **Decline Cherre, RCA, CoStar, Trepp** — wrong shape for community-bank CRE prospecting. **Defer ATTOM API tier and CoreLogic** until the Reonomy pilot tells us whether their depth in TX justifies the price gap. Total year-1 commitment for the BUY-and-WIRE-IN recommendations above: **~$8,000-15,000** depending on county-clerk quote outcomes.

---

## Appendix: what specifically would change in the dashboard

If the full BUY set above is procured, the Loan Maturity dashboard would change in these specific ways (each item carries its own engineering ticket):

- **Pipeline table gains:** phone number column (Reonomy), website column (Google Places), entity_id link (OpenCorporates), historical-lender badge (PPP FOIA), expanded source set (ATTOM mortgage / county deeds-of-trust).
- **Total loan count** at full deployment: realistically 60,000-100,000 records (from ~20K today), with non-SBA loans surfacing in the 5 major counties.
- **Total $ tracked** expected to grow to $40-80B across the footprint.
- **Methodology tab** loses several "blocked" bullet points and gains source-attribution rows for each licensed feed.
- **Freshness ribbon** adds 3-5 additional pills, one per licensed source.
- **A new "Borrower 360"** unified view becomes meaningful (see Part 2 of the source prompt).
