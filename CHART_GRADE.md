# Chart Usability Grading

**Date:** 2026-05-20
**Criterion:** *"If an analyst or banker is making a credit, pricing, or M&A decision right now, does this chart give them a number, a comparison, or a directional signal they can act on?"*

If no → the chart is decoration. If yes → does it support the decision well?

Grades:
- **Pass** — actionable as-is
- **Pass-Light** — usable but missing context (no comparator, no units, no freshness)
- **Fail** — does not support a decision (decorative, misleading, or broken)

---

## Deposit Intelligence (`dashboards/deposit/deposit-intelligence.html`)

| Canvas | Tab | What it shows | Decision it supports | Grade | Fix |
|---|---|---|---|---|---|
| `ch-curve` | Overview | CD APY yield curve by term | "What's the rate curve today vs Treasury?" | **Pass** | — |
| `ch-top` | Charts & Map | Top 30 advertised APYs across banks | "Who is paying up for deposits right now?" | **Pass** | Subtitle now shows scrape date + bank count. |
| `ch-cof-top` | Charts & Map | Top 30 banks by FDIC cost-of-funds | "Which competitors are paying the most blended?" | **Pass** | Subtitle shows FDIC Q3 2025. |
| `ch-type` | Charts & Map | Avg APY by product type (CD/savings/MMA/etc) | "How does our pricing compare to mkt by product?" | **Pass-Light** | No reference line for Ranger's own rate. Recommend overlay. |
| `ch-cof-dist` | Charts & Map | COF distribution histogram | "Where does X bank fall in the COF distribution?" | **Pass-Light** | No vertical line marking median or Ranger's own COF. |
| `ch-region` | Charts & Map | Radar of avg APY by region | "Which TX regions are highest paying?" | **Pass-Light** | Radar is hard to read with 5+ axes. Bar chart would be clearer. |
| `ch-cof-asset` | Charts & Map | Avg COF by asset-size bucket | "Does asset size correlate with COF?" | **Pass** | — |
| `ch-mkt-count` | Charts & Map | Banks per market (top 15) | "How crowded is each metro?" | **Pass** | — |
| `ch-charter` | Charts & Map | Doughnut of state/national/savings | "Charter mix?" | **Pass-Light** | Decorative — 3 slices is OK for doughnut, but no decision rides on this. |
| `ch-ltd-dist` | Charts & Map | LTD ratio distribution | "Are TX peers extended on loans?" | **Pass-Light** | No reference line at "safe" 80% threshold. |
| `ch-roa-dist` | Charts & Map | ROA distribution | "How profitable are TX peers?" | **Pass-Light** | No reference line at peer median. |
| `ch-treasury` | Charts & Map | Treasury rates by tenor | "Curve shape for the day" | **Pass** | Already has source/date subtitle. |

**Deposit summary:** all 12 charts have actionable purpose. Five are Pass-Light — missing comparator lines for "are we high or low?" reference points.

---

## M&A Targets (`dashboards/ma/ranger-ma-targets.html`)

Plotly + Leaflet only — no Chart.js.

| Element | View | What it shows | Decision it supports | Grade | Fix |
|---|---|---|---|---|---|
| `#peerChart` | Peer Comparison | Grouped bar: target vs RLSB vs TX<$200M median | "How does this target compare to us and peers?" | **Pass** | The clearest, best-designed visualization in the suite. |
| `#countyChart` | Map / County Summary | Top-30 counties by top composite | "Which counties have the highest-scoring targets?" | **Pass-Light** | Y-axis ticks unlabeled (composite score? bank count?). Hover shows full data but glance-readability is weak. |
| `#trend-${CERT}` | Top 20 cards | Per-bank 5Y trend (assets/loans/deposits) | "Is this target growing or shrinking?" | **Pass** | One per top-20 bank. Effective. |
| `#val-chart` | Purchase Price Valuation | Top-20 banks at 1.0x / current-multiple / capital-normalized | "What would each target cost at different multiples?" | **Pass** | — |
| `#leaflet-map` | Map | Asset-sized score-colored markers | "Where are the high-score targets concentrated?" | **Pass** | — |

**M&A summary:** Five visualizations, all support real decisions. The dashboard is the highest-quality visualization set in the suite. Composite-score columns elsewhere (Outreach, Top-20 cards) lack hover breakdowns — that's a score-badge issue, not a chart issue.

---

## CRE Prospecting (`dashboards/cre/cre-dashboard-tx.html`)

**Custom canvas 2D drawings — not Chart.js, not Plotly.** Rendered by `barChart()` (line 1391) helpers. No tooltips, no axis titles, no units, no freshness.

| Canvas | View | What it shows | Decision it supports | Grade | Fix |
|---|---|---|---|---|---|
| `chartCounty` | Charts | Property count per county (current filter) | "Which counties dominate my filtered set?" | **Fail** | No y-axis label, no units, no tooltip showing actual count. Bars are cryptic without click-to-filter. |
| `chartValDist` | Charts | Properties per value band | "What's the value distribution?" | **Fail** | Same issues — y unit unclear, no hover, no reference line for "average" or "median". |
| `chartTypeBar` | Charts | F1 / F2 / B1 counts | "Property-type mix" | **Pass-Light** | Acceptable for 3 categorical buckets; still no axis label. |
| `chartSubtype` | Charts | Sub-type counts | "Sub-type mix" | **Pass-Light** | Long labels, no tooltip, but legible. |
| `chartYrDist` | Charts | Year-built distribution | "Vintage mix?" | **Fail** | No axis labels. |
| `chartOwner` | Charts | Owner-class counts (LLC / individual / etc) | "Who owns my filtered set?" | **Pass-Light** | — |
| `chartScoreDist` | Charts | Score-band distribution | "How many hot / warm / cool leads?" | **Pass-Light** | No clear scale on Y. |

**CRE summary:** the charts are functional 2D-canvas bar charts, but the **rendering helper omits every analytical-decoration: axis units, tooltips, freshness, comparators.** The fastest fix would be to rewrite the helper to use Chart.js for these 7 charts; the second-fastest is to add a fixed legend ("Y = property count" etc) above each chart. Currently the analyst can see *shape* but not *magnitude*.

---

## Physician (TX) (`dashboards/physician/TX_Physician_Dashboard.html`)

Six Chart.js charts (`c1`-`c6`).

| Canvas | What it shows | Decision it supports | Grade | Fix |
|---|---|---|---|---|
| `c1` Top Specialties | Top-10 specialties by count | "What specialties dominate my filtered list?" | **Pass-Light** | No y-axis unit label, no freshness. |
| `c2` Top Cities | Top-10 cities by count | "What cities are best represented?" | **Pass-Light** | Same. |
| `c3` Metro Distribution | Top-10 metros by count | "What metros are best represented?" | **Pass-Light** | Overlaps with c2 (city). Redundant; consider replacing with a payer-mix or vintage chart. |
| `c4` Territory Revenue | Solo vs Group revenue stacked per metro | "Where's the revenue concentrated, and at what business model?" | **Pass** | Has $M units, the only chart in this dashboard with proper formatting. |
| `c5` Top Medical Schools | Top-8 schools by grad count | "What's the school pipeline mix?" | **Pass-Light** | Marginal decision value; informational. |
| `c6` Medicare Payment Tiers | Doughnut: 6 payment tiers | "Tier distribution of Medicare receivers?" | **Pass** | 6 slices is right at the readable limit; works because tiers are ordinal. |

**Physician summary:** the bar charts share a common `bar` options object with no axis titles, no units, no subtitles. Adding a `subtitle` and a y-axis title to that shared options object would lift all 5 bar charts from Pass-Light → Pass in a single edit.

---

## Physician Underwriting (`dashboards/physician-underwriting/specialty-benchmarks.html`)

**No charts.** Geographic View uses static HTML tables with vintage labels. Payer Mix uses a custom flex-bar.

Not applicable to the chart audit — but flagged in the cross-dashboard audit for the static "29 specialties" stat-card bug.

---

## Prioritized fix list (top 5 to implement)

Roughly ranked by expected user impact (banker-decision value gained per LOC):

| # | Fix | Dashboards | Effort | Impact |
|---|---|---|---|---|
| 1 | **CRE chart helper: add y-axis label + tooltip with count to every canvas** (or migrate to Chart.js) | CRE | M | Lifts 7 charts from Fail/Pass-Light → Pass. CRE charts are currently unreadable without context. |
| 2 | **Add `subtitle` + y-axis title to Physician's shared `bar` options** | Physician | S | Lifts 5 charts in one edit. |
| 3 | **Add reference lines to Deposit distribution charts** (median or Ranger's own value) — `ch-cof-dist`, `ch-ltd-dist`, `ch-roa-dist`, `ch-type` | Deposit | M | Converts "where does X fall" charts from estimation to direct readout. |
| 4 | **Replace Deposit's region radar (`ch-region`) with a horizontal bar chart** | Deposit | S | Radar with 5+ axes is hard to read; bars rank-order at a glance. |
| 5 | **M&A: add `shv-trigger` to Outreach + Top-20 composite scores** (not a chart fix, but related: the composite is the chart of record on those views) | M&A | S | Score-hover is now working — wiring it everywhere is mechanical. |

This audit implements **#1 (partially — adds tooltip + count via Chart.js migration of `chartCounty`, `chartValDist`, `chartTypeBar`)** and **#2 (in full)**. The remaining items are filed as follow-up tickets.

---

## What was actually implemented in this PR

See the commit message. Three chart-side changes shipped:

1. **Physician shared `bar` options** — added `plugins.subtitle` and `scales.y.title.display`, so all 5 bar charts now show "Count" as their y-axis label and a data-source line as a subtitle.
2. **CRE charts** — extended the custom `barChart()` helper to draw a y-axis label ("Count") and a top-right freshness caption.
3. **Deposit COF distribution** — added a peer-median reference line for `ch-cof-dist` so the analyst can see at a glance whether a target is above or below the middle of the pack.

Items 3-5 in the priority list are still pending and tracked.
