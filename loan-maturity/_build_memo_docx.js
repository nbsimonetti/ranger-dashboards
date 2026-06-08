// Build PAID_DATA_EVAL.docx from the rewritten memo content.
// Run with:  NODE_PATH=$(npm root -g) node _build_memo_docx.js
'use strict';
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, Header, Footer,
  AlignmentType, PageOrientation, LevelFormat, ExternalHyperlink, HeadingLevel,
  BorderStyle, WidthType, ShadingType, PageNumber, TabStopType, TabStopPosition,
} = require('docx');

// ─── Helpers ────────────────────────────────────────────────────────────────
const cellBorder = { style: BorderStyle.SINGLE, size: 6, color: 'D5D5D5' };
const cellBorders = { top: cellBorder, bottom: cellBorder, left: cellBorder, right: cellBorder };
const cellMargins = { top: 100, bottom: 100, left: 140, right: 140 };

function p(text, opts = {}) {
  return new Paragraph({
    spacing: opts.spacing || { after: 140 },
    alignment: opts.alignment,
    children: Array.isArray(text)
      ? text.map(t => (typeof t === 'string' ? new TextRun(t) : t))
      : [new TextRun({ text, ...(opts.run || {}) })],
  });
}
function h1(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 180 }, children: [new TextRun({ text, bold: true, size: 30 })] });
}
function h2(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 260, after: 120 }, children: [new TextRun({ text, bold: true, size: 24 })] });
}
function h3(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_3, spacing: { before: 200, after: 80 }, children: [new TextRun({ text, bold: true, size: 22 })] });
}
function bullet(text) {
  return new Paragraph({ numbering: { reference: 'bullets', level: 0 }, spacing: { after: 80 }, children: typeof text === 'string' ? [new TextRun(text)] : text });
}
function tcell(content, opts = {}) {
  const paras = (Array.isArray(content) ? content : [content]).map(c =>
    typeof c === 'string'
      ? new Paragraph({ children: [new TextRun({ text: c, size: opts.size || 20, bold: !!opts.bold })] })
      : c
  );
  return new TableCell({
    borders: cellBorders,
    margins: cellMargins,
    width: opts.width ? { size: opts.width, type: WidthType.DXA } : undefined,
    shading: opts.shade ? { fill: opts.shade, type: ShadingType.CLEAR } : undefined,
    children: paras,
  });
}

// ─── Recommendation summary table ───────────────────────────────────────────
const recRows = [
  ['Vendor', 'Recommendation', 'Annual cost band', 'Confidence'],
  ['Melissa Data',             'Buy',     '$60 one-time PAYG',               'High'],
  ['SBA PPP FOIA enrichment',  'Wire in', '$0',                              'High'],
  ['TX County Clerks (×5)',    'Quote',   '$3–8K aggregate (target)',        'Medium'],
  ['Reonomy',                  'Buy',     '$4,800/yr/seat',                  'High'],
  ['OpenCorporates Essentials','Buy',     '~$2,800/yr',                      'High'],
  ['Google Places API',        'Buy',     '$300–1,500/yr',                   'High'],
  ['ATTOM Data Solutions',     'Pilot',   '$499/yr seat; $12–30K API',       'High / Medium'],
  ['CompStak Exchange',        'Pilot',   '$0 (contribute-to-access)',       'High'],
  ['Dun & Bradstreet',         'Defer',   '$529/yr Hoovers Essentials',      'High'],
  ['CoStar (single market)',   'Defer',   '$12–25K',                         'Med–High'],
  ['CoreLogic RealQuest',      'Defer',   '$3–8K seat; $15–40K API',         'Low'],
  ['Trepp',                    'Defer',   '$15–40K (TX-only)',               'Low'],
  ['CompStak Enterprise',      'Decline', '$25–60K',                         'Low–Med'],
  ['Real Capital Analytics',   'Decline', '$15–30K (regional)',              'Low'],
  ['Cherre',                   'Decline', '$150K+',                          'Medium'],
];

const recTable = new Table({
  width: { size: 9360, type: WidthType.DXA },
  columnWidths: [2700, 1700, 3260, 1700],
  rows: recRows.map((row, i) =>
    new TableRow({
      tableHeader: i === 0,
      children: row.map((cell, j) =>
        tcell(cell, {
          width: [2700, 1700, 3260, 1700][j],
          bold: i === 0,
          size: i === 0 ? 20 : 19,
          shade: i === 0 ? 'E8E8E8' : (i % 2 === 0 ? 'F7F7F7' : null),
        })
      ),
    })
  ),
});

// ─── Vendor analysis blocks ─────────────────────────────────────────────────
// Written as continuous prose, not bullet template. Numbers + recommendations
// preserved verbatim from the markdown source.

function vendorBlock(name, recommendation, paras) {
  const head = new Paragraph({
    spacing: { before: 260, after: 80 },
    children: [
      new TextRun({ text: name, bold: true, size: 22 }),
      new TextRun({ text: '   ' }),
      new TextRun({ text: recommendation, bold: true, italics: true, color: '666666', size: 20 }),
    ],
  });
  return [head, ...paras.map(t => p(t))];
}

const vendors = [
  vendorBlock(
    'ATTOM Data Solutions',
    '— Pilot the $499 self-serve seat.',
    [
      'ATTOM publishes a Property Navigator Professional seat at $499 per year. The seat gets one user, 200 reports per month, 2,000 list exports per month, and access to ATTOM’s 150M-property file with foreclosure flags, sales searches, mortgage records, and AVMs. Going beyond the self-serve seat into the Property Data API (mortgage and transaction history at call volume) lands in the $12K to $30K range depending on add-ons. The seat is annual, cancellable, and offers a free trial.',
      'The relevant coverage for our footprint is non-SBA mortgage records on commercial property. ATTOM’s file is broad nationally but residential-leaning. True commercial depth (tenant rolls, leases) is thinner than what CoStar or Reonomy carry. Realistic uplift in the 32-county footprint is 30 to 40 percent additional non-SBA mortgage coverage.',
      'A 60-day pilot at $499 has bounded downside and gives us a real read on TX coverage. Decide on the API tier only after the pilot.',
    ]
  ),
  vendorBlock(
    'CoreLogic RealQuest',
    '— Defer.',
    [
      'CoreLogic is the more enterprise-favored peer to ATTOM, and prices accordingly. A single seat is in the $3K to $8K range. API access starts around $15K and runs to $40K, with a 1-year minimum. CoreLogic posts essentially no public pricing; the band is anchored on rate-card leaks via Trestle ($11.50 per Involuntary Lien call, $2.30 per Finance History call) and a handful of community-bank disclosures.',
      'Coverage is comparable to ATTOM at two to four times the cost. We can revisit only if the ATTOM pilot fails and we specifically need the per-call lien API.',
    ]
  ),
  vendorBlock(
    'Cherre',
    '— Decline.',
    [
      'Cherre is a data-unification platform, not a data source. Pricing starts at $150K and runs to $1M-plus per year. It is plumbing: an entity-resolution layer (Cherre ID) plus connectors to fifty-odd CRE sources that the customer licenses separately. We do not yet have a portfolio of licensed CRE data sources that needs unifying. Re-evaluate only when we are running five or more paid CRE feeds in parallel.',
    ]
  ),
  vendorBlock(
    'Reonomy (Altus Group)',
    '— Buy after a successful free trial.',
    [
      'Reonomy is the most consequential single recommendation in this memo. The standalone web app subscribes at $4,800 per year per seat ($400/mo), confirmed independently by CRE Daily and Mashvisor. The seven-day free trial gives full functionality and is the right way to validate TX coverage before we commit.',
      'What we get: roughly 50M US properties, LLC-piercing to true beneficial owners, owner phone numbers, owner email and mailing addresses, mortgage data, debt history, and tenant information. The coverage that matters here is contactability. Our SBA file has borrower mailing addresses; it does not have phones or principals. Reonomy adds both. Empirically we should expect 50 to 70 percent of our SBA borrowers to gain a phone number after enrichment, plus another 30 to 50 percent uplift on non-SBA mortgage records via Reonomy’s deed and mortgage layer.',
      'Engineering work to integrate is small: a new reonomy_enrich.py step in the offline pipeline and a phone/email column on the Pipeline table. The downstream payoff is large; this is the line item that turns the dashboard from a list into a prospect list.',
    ]
  ),
  vendorBlock(
    'CompStak',
    '— Decline Enterprise. Pilot the free Exchange tier.',
    [
      'CompStak Enterprise sits in the $25K to $60K range for a single market or region. It is excellent for lease and sale comps with debt comps in major metros. It is the wrong tool for top-of-funnel prospecting: comps are an underwriting input, not a prospect list. We should keep the free Exchange tier (contribute-to-access) handy for once a deal is in motion, but skip Enterprise.',
    ]
  ),
  vendorBlock(
    'Trepp',
    '— Defer.',
    [
      'Trepp’s community-bank tier (TreppBank Navigator) is in the $15K to $40K range; the full CMBS plus CRE bundle runs $50K to $150K. Pricing is opaque; the band is anchored on a small number of community-bank vendor reviews. Trepp is a risk-benchmarking tool, not a prospect list, and T-ALLR is anonymized — we cannot pull borrower names from it. Reconsider only if the bank ever needs CRE concentration reporting for regulators.',
    ]
  ),
  vendorBlock(
    'Real Capital Analytics (MSCI)',
    '— Decline.',
    [
      'RCA’s smallest meaningful subscription is regional, around $15K to $30K. The database is institutional-grade but skewed to deals above $2.5M. The bulk of TX community-bank CRE sits below that threshold, so the coverage we actually need is sparse. Not the right shape for us.',
    ]
  ),
  vendorBlock(
    'CoStar',
    '— Defer.',
    [
      'A CoStar single-market license (DFW only, say, or Houston only) is in the $12K to $25K range; multi-market US runs $40K to $70K. CoStar’s coverage in TX major metros is the best in the market. The catch is that it overlaps heavily with Reonomy at three to five times the cost. If the Reonomy pilot succeeds, CoStar becomes redundant. If it disappoints, a CoStar Houston-only seat at $12K to $15K is a reasonable fallback.',
    ]
  ),
  vendorBlock(
    'OpenCorporates',
    '— Buy.',
    [
      'The Essentials API plan is £2,250 per year, roughly $2,800 USD. Higher tiers ($8,200 and $15,000) raise call volume. OpenCorporates pulls registry data from 130-plus jurisdictions, including all 50 US states, with officer and director links and filings.',
      'This is the cheapest tool that solves the LLC-variant problem permanently. Today our join pipeline guesses that "ABC HOLDINGS LLC" and "A.B.C. Holdings, L.L.C." refer to the same entity by fuzzy string match. OpenCorporates lets us resolve both to a single TX-SOS-keyed entity ID and stop guessing. Expect 80 to 90 percent of our 19,737 borrowers to resolve to a TX registry record after enrichment. Once we have stable entity IDs, parent and subsidiary relationships become traversable, which downstream feeds the Borrower 360 view.',
    ]
  ),
  vendorBlock(
    'Dun & Bradstreet',
    '— Defer.',
    [
      'D&B Hoovers Essentials is $529 per year for 1,800 credits, which works out to about five lookups per day. That is not enough to enrich a 19,737-record file; we would need to either upgrade or batch over multiple years. Full Hoovers plans run $5K to $10K, and the D&B Direct+ API starts at $25K plus a $5K to $15K setup fee. The median D&B deal across all SKUs is $41K per year per Vendr’s buyer database.',
      'OpenCorporates plus Reonomy together cover most of what D&B gives us at a fraction of the price. Revisit only if we need DUNS-keyed credit scores for underwriting.',
    ]
  ),
  vendorBlock(
    'Melissa Data',
    '— Buy ($60 PAYG).',
    [
      'Pay-as-you-go pricing is $285 per 100K credits, which means cleaning our 19,737-record file once costs about $60. The annual address-verification plan is $5,145 per 1M records if we ever need more volume. Melissa does not add new prospects — it normalizes addresses (USPS CASS), standardizes business names, and resolves light entity variations. Expected uplift to our loan-to-property join accuracy is 10 to 15 percent fewer false negatives.',
      'This is the smallest dollar amount in the memo and the highest return per dollar spent. There is no procurement step worth speaking of: a credit card on the website and the credits are usable in minutes.',
    ]
  ),
  vendorBlock(
    'Google Places API',
    '— Buy (pay-as-you-go).',
    [
      'Realistic spend for our use case is $300 to $1,500 per year, lookup-volume dependent. Each billing account gets a free monthly cap (10K Essentials / 5K Pro / 1K Enterprise events), enough to enrich most of our rows over two to three months at no marginal cost. Google’s Places file leans retail and consumer-facing, so expect a 50 to 70 percent match rate on a CRE-borrower list — which is exactly where Reonomy is weakest. The two are complementary: Reonomy carries the industrial and B2B side, Google fills the retail and storefront side.',
    ]
  ),
];

// ─── Build the document ─────────────────────────────────────────────────────
const doc = new Document({
  creator: 'Ranger Bank — Engineering',
  description: 'Paid data evaluation memo for the Loan Maturity Intelligence dashboard.',
  title: 'Loan Maturity — Paid Data Evaluation',
  styles: {
    default: { document: { run: { font: 'Calibri', size: 22 } } },
    paragraphStyles: [
      { id: 'Title',    name: 'Title',    basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 40, bold: true, color: '1B365D' },
        paragraph: { spacing: { before: 0, after: 120 }, outlineLevel: 0 } },
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 30, bold: true, color: '1B365D' },
        paragraph: { spacing: { before: 360, after: 160 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 24, bold: true, color: '254a7a' },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 22, bold: true, color: '254a7a' },
        paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [
      { reference: 'bullets', levels: [{
        level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 540, hanging: 270 } } },
      }] },
      { reference: 'numbers', levels: [{
        level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 540, hanging: 270 } } },
      }] },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },  // US Letter
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          children: [new TextRun({ text: 'Ranger Bank · Loan Maturity Intelligence', size: 18, color: '888888', italics: true })],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: 'Page ', size: 18, color: '888888' }),
            new TextRun({ children: [PageNumber.CURRENT], size: 18, color: '888888' }),
            new TextRun({ text: ' of ', size: 18, color: '888888' }),
            new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 18, color: '888888' }),
          ],
        })],
      }),
    },
    children: [
      // Title
      new Paragraph({
        style: 'Title',
        children: [new TextRun({ text: 'Paid Data Evaluation — Loan Maturity Intelligence', bold: true, size: 40, color: '1B365D' })],
      }),
      new Paragraph({
        spacing: { after: 240 },
        children: [
          new TextRun({ text: 'Date: ', bold: true, size: 20 }),
          new TextRun({ text: 'May 21, 2026', size: 20 }),
          new TextRun({ text: '          Audience: ', bold: true, size: 20 }),
          new TextRun({ text: 'CFO and Head of Commercial Lending', size: 20 }),
        ],
      }),

      // Overview
      p('The Loan Maturity Intelligence dashboard surfaces 19,737 active SBA 7(a) and 504 loans across the 32-county TX footprint — $16.3B in tracked balances. Every record traces back to a free public source. The dashboard works, but its ceiling is set by what the SBA file alone can tell us, which is roughly 5 to 10 percent of the commercial-lending universe nationally. This memo evaluates twelve commercial-real-estate and lending data vendors (plus one free source) for closing the gap.'),
      p('Cost bands are stated honestly throughout. Most vendors here gate pricing behind sales calls, so several of the figures below carry low confidence and would need to be confirmed by a quote. Where pricing is public, confidence is high.'),
      p('The bottom line is on the next page. Recommended year-one commitment, before any vendor negotiation, is in the range of $8,000 to $15,000 — driven mostly by Reonomy and OpenCorporates plus quotes from five county clerks. Several frequently-discussed vendors (Cherre, RCA, CoStar, Trepp) are declined or deferred for the reasons spelled out in their sections.'),

      h1('Year-one plan'),
      p('Sequenced by procurement difficulty rather than dollar value. Items at the top can be done today; items lower down need quotes or pilots.'),
      bullet([
        new TextRun({ text: 'Wire in SBA PPP FOIA bulk now ', bold: true }),
        new TextRun('($0). Adds incumbent-lender history per borrower as enrichment. No procurement step required.'),
      ]),
      bullet([
        new TextRun({ text: 'Buy Melissa Data PAYG credits ', bold: true }),
        new TextRun('(~$60 one-time, possibly $5K/yr if we need to refresh at scale). Improves every downstream entity-and-address join by 10 to 15 percent. Smallest dollar amount with the largest accuracy lift per dollar.'),
      ]),
      bullet([
        new TextRun({ text: 'Request quotes from the five major TX county clerks ', bold: true }),
        new TextRun('— Dallas, Harris, Tarrant, Bexar, Travis — for monthly Deed-of-Trust index feeds. Expected aggregate cost from prior community-banker conversations is $3,000 to $8,000. If quotes come in at that level, this unlocks the non-SBA bank balance-sheet loan universe in the counties that hold roughly 70 percent of footprint commercial value. Maturity dates live inside PDF instruments and will need OCR on our side as a one-time engineering cost.'),
      ]),
      bullet([
        new TextRun({ text: 'Buy Reonomy after a successful free trial ', bold: true }),
        new TextRun('($4,800/yr per seat). The largest UX gap in the current dashboard is contactability — borrower phone numbers and principals. Reonomy is the one vendor at community-bank pricing that solves this for TX commercial property.'),
      ]),
      bullet([
        new TextRun({ text: 'Add OpenCorporates Essentials ', bold: true }),
        new TextRun('(~$2,800/yr). Resolves the LLC-variant problem in our join pipeline. Once we have stable entity IDs, parent and subsidiary relationships are traversable, which is the foundation for any future Borrower 360 view across dashboards.'),
      ]),
      bullet([
        new TextRun({ text: 'Pilot ATTOM Property Navigator ', bold: true }),
        new TextRun('($499 self-serve seat for 60 days). Decide on the more expensive API tier only after the pilot tells us what TX coverage actually looks like.'),
      ]),
      bullet([
        new TextRun({ text: 'Add Google Places PAYG ', bold: true }),
        new TextRun('($300 to $1,500/yr depending on volume). Fills the retail-and-storefront gap that Reonomy is weakest on.'),
      ]),

      p('Cherre, Real Capital Analytics, CoStar, Trepp, CompStak Enterprise, and CoreLogic are declined or deferred. The reasoning is in each vendor section.', { run: { italics: true, color: '666666' } }),

      h1('Recommendation summary'),
      recTable,
      p('', { spacing: { after: 200 } }),

      h1('Vendor analysis'),
      h2('Gap A — Non-SBA commercial mortgages'),
      ...vendors.slice(0, 5).flat(),

      h2('Gap B — CMBS and institutional CRE debt'),
      ...vendors.slice(5, 8).flat(),

      h2('Gap C — Entity resolution and contactability'),
      ...vendors.slice(8, 12).flat(),

      h2('Gap D — County-level public records'),
      p('The five major TX counties (Dallas, Harris, Tarrant, Bexar, Travis) hold roughly 70 percent of commercial value in our footprint and have already been confirmed as bulk-blocked: each county’s online portal allows free per-document download but gates bulk feeds behind a paid Data Sales contract. The contracts are typically modest. From conversations with peers, the expected aggregate cost for monthly Deed-of-Trust index feeds across all five counties lands somewhere between $3,000 and $8,000 per year.'),
      p('Contact points: Dallas County Clerk Data Sales; Harris County Clerk Data Sales (datasales@cco.hctx.net, 713-274-6390); Tarrant County Clerk Central Library; Bexar County Clerk; Travis County Clerk Public Information Request.'),
      p('If actual quotes land in the expected band, this is the buy with the most additional coverage per dollar in the whole memo. It unlocks the non-SBA bank-balance-sheet commercial loan universe in the counties that matter. If quotes exceed $15K aggregate, defer until ATTOM pilot results are in: ATTOM may cover the same deed-of-trust data nationally at lower marginal cost.'),
      p('Engineering cost on our side is a one-time OCR pipeline to extract maturity dates from instrument PDFs. Manageable; covered in the dashboard’s offline data-collection layer.'),

      h2('Gap E — Free, no procurement step'),
      h3('SBA PPP FOIA bulk — wire in now ($0)'),
      p('Roughly 11.5M PPP records nationally, about 1M for Texas. Every record carries borrower name, address, NAICS, and lender name. PPP is not a maturity source (the program is closed and most loans were forgiven), but the borrower-to-lender pairing is durable signal. Where a TX borrower took PPP from a particular bank in 2020-2021, that bank usually still has primary deposit and treasury management with them. Adds an "incumbent lender history" enrichment column to our Pipeline table at zero cost and zero procurement friction. Already on the engineering backlog.'),

      h1('Deployment-architecture caveat'),
      p('Every licensed vendor in this memo prohibits redistribution of their data. Once we buy any of them, the resulting loans.json cannot be hosted on a public GitHub Pages repo. The dashboard suite as it stands today is public. We need to pick a path before signing the first contract:'),
      bullet('Make the dashboards repo private and use a paid GitHub Pages plan with the appropriate runner. Cheapest path. Requires changing how users access the suite.'),
      bullet('Migrate to a private host such as Render (already configured via render.yaml), Vercel, or Cloudflare Pages with access auth. Adds $0 to $20 per month.'),
      bullet('Run two tiers: a free-data-only version stays public on GitHub Pages, and a full version (free + licensed feeds) moves behind auth. Operationally heavier, but lets the marketing-friendly version stay public.'),
      p('Pick before the first signature. Vendors take redistribution leaks seriously: the realistic downside is contract termination plus litigation.'),

      h1('Appendix — what would change in the dashboard'),
      p('If the full Buy and Wire-In set is procured, here is what the Loan Maturity dashboard looks like. Each item below is its own engineering ticket.'),
      bullet([
        new TextRun({ text: 'Pipeline table gains four to five columns: ', bold: true }),
        new TextRun('phone number (Reonomy), website (Google Places), entity_id link (OpenCorporates), historical-lender badge (PPP FOIA), and an expanded source set covering ATTOM mortgage records and county Deed-of-Trust records.'),
      ]),
      bullet([
        new TextRun({ text: 'Total loan count grows roughly 3x to 5x. ', bold: true }),
        new TextRun('From 20K SBA-only loans today to a realistic 60K to 100K with county deeds and ATTOM mortgage data layered in. Total $ tracked grows from $16.3B to a projected $40B to $80B across the footprint.'),
      ]),
      bullet([
        new TextRun({ text: 'Methodology tab loses several blocked-source bullets ', bold: true }),
        new TextRun('and gains source-attribution rows for each licensed feed.'),
      ]),
      bullet([
        new TextRun({ text: 'Freshness ribbon gains three to five additional pills, ', bold: true }),
        new TextRun('one per licensed source, mirroring the existing SBA / county / session pattern.'),
      ]),
      bullet([
        new TextRun({ text: 'A Borrower 360 unified view becomes meaningful, ', bold: true }),
        new TextRun('joining loans, properties, contacts, and historical lender relationships into a single drill-down panel per entity.'),
      ]),
    ],
  }],
});

Packer.toBuffer(doc).then(buf => {
  const outPath = path.join(__dirname, 'PAID_DATA_EVAL.docx');
  fs.writeFileSync(outPath, buf);
  console.log('Wrote ' + outPath + '  (' + (buf.length/1024).toFixed(1) + ' KB)');
});
