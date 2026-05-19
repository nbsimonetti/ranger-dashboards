"""
recompute_rankings.py — Refined M&A Target Ranking Methodology

Recomputes the composite ranking for all 95 targets using a refined formula
that incorporates deal economics and shareholder accessibility alongside the
existing financial-fundamentals signals.

NEW COMPOSITE:
    composite_score = 0.50 × quant_score
                    + 0.25 × deal_econ_score    (NEW)
                    + 0.25 × qual_score

QUANT SCORE (50%) — unchanged. Existing 9 inputs at their existing weights.
    T1 Leverage, L/D Ratio, 5Y Equity/Asset/Loan CAGR, ROA, ROE, CoF, Assets.

DEAL ECONOMICS SCORE (25%) — NEW. 5 sub-components, weights:
    - Capital efficiency 30%  — closer to 10% T1 target = better
    - Goodwill burden 15%     — lower GW/equity = better
    - TBVE size fit 25%       — $25M-$100M sweet spot
    - CoF franchise 15%       — lower CoF = better
    - Credit quality proxy 15% — asset growth ≤ equity growth = better

QUALITATIVE SCORE (25%) — updated weights:
    - Geographic fit 30%      (existing)
    - Shareholder access 25%  (NEW, derived from FR Y-6/SEC structure)
    - HoldCo structure 15%    (NEW, multi-bank holdco penalty)
    - Loan mix 10%, Deposit quality 10%, LMH synergy 10% (existing)

OUTPUT:
    - ranger-ma-targets.html (updated const DATA block with new scores and ranks)
    - rankings_v1_v2.json (side-by-side comparison for audit)

USAGE:
    python recompute_rankings.py
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
HTML = HERE / "ranger-ma-targets.html"
AUDIT = HERE / "rankings_v1_v2.json"


def load_data():
    text = HTML.read_text(encoding="utf-8")
    m = re.search(r"const DATA = (\{.*?\});", text, re.DOTALL)
    if not m:
        sys.exit("ERROR: const DATA not found in HTML")
    raw = m.group(1)
    raw_json = re.sub(r"\bNaN\b", "null", raw)
    return text, m.start(1), m.end(1), json.loads(raw_json)


def safe(v, default=None):
    return v if (v is not None and not (isinstance(v, float) and v != v)) else default


def percentile_rank(values, value, lower_is_better=True):
    """
    Returns 0-100 score where 100 = most attractive (lowest if lower_is_better else highest).
    """
    vals = sorted(v for v in values if v is not None and not (isinstance(v, float) and v != v))
    if not vals or value is None or (isinstance(value, float) and value != value):
        return 50.0
    n = len(vals)
    # Rank: # of values strictly worse than value
    if lower_is_better:
        worse = sum(1 for v in vals if v > value)
    else:
        worse = sum(1 for v in vals if v < value)
    return (worse / n) * 100


# ─────────────────────────────────────────────────────────────────────────────
# QUANT SCORE (preserve existing methodology)
# ─────────────────────────────────────────────────────────────────────────────
QUANT_WEIGHTS = [
    # (key, weight, lower_is_better)
    ("leverage_ratio",  0.15, True),
    ("loan_to_deposit", 0.15, True),
    ("equity_cagr_5y",  0.10, True),
    ("asset_cagr_5y",   0.10, True),
    ("loan_cagr_5y",    0.10, True),
    ("roa",             0.10, True),
    ("roe",             0.10, True),
    ("cost_of_funds",   0.10, True),
    ("ASSET",           0.10, False),  # higher = more priority
]


def compute_quant_score(rows):
    """Per-bank quant score 0-100 using percentile ranks across the universe."""
    for r in rows:
        score = 0.0
        for key, weight, lower_better in QUANT_WEIGHTS:
            all_vals = [x.get(key) for x in rows]
            pct = percentile_rank(all_vals, r.get(key), lower_is_better=lower_better)
            score += weight * pct
        r["quant_score_v2"] = round(score, 2)


# ─────────────────────────────────────────────────────────────────────────────
# DEAL ECONOMICS SCORE (NEW)
# ─────────────────────────────────────────────────────────────────────────────
DEAL_TARGET_LEVERAGE_PCT = 10.0  # Tier 1 normalization target


def deal_economics_score(r):
    """0-100 composite from 5 sub-components."""
    components = {}

    # 1. Capital efficiency (30%): penalize both excess and shortfall vs 10% T1
    asset_k = safe(r.get("ASSET"), 0)
    eqtot_k = safe(r.get("EQTOT"), 0)
    if asset_k > 0 and eqtot_k > 0:
        required = asset_k * (DEAL_TARGET_LEVERAGE_PCT / 100.0)
        excess = eqtot_k - required
        excess_pct = (excess / asset_k) * 100.0  # signed %, e.g. +3.2% means 3.2% over target
        # Score: 100 at 0 deviation; ramps down ±10% deviation reaches 0
        components["capital_efficiency"] = max(0.0, 100.0 - abs(excess_pct) * 10.0)
    else:
        components["capital_efficiency"] = 50.0  # neutral when data missing

    # 2. Goodwill burden (15%): lower GW/equity = better
    gw = safe(r.get("GOODWILL"), 0) or 0
    if eqtot_k > 0:
        gw_ratio = gw / eqtot_k  # 0..1+
        components["goodwill_burden"] = max(0.0, 100.0 - gw_ratio * 200.0)  # 50% gw → 0 pts
    else:
        components["goodwill_burden"] = 50.0

    # 3. TBVE size fit (25%): $25M-$100M sweet spot
    tbve_m = (safe(r.get("TBVE"), 0) or 0) / 1000.0  # to $M
    if tbve_m < 5:
        components["tbve_size_fit"] = 30.0
    elif tbve_m < 25:
        # Linear ramp 5 → 25 maps to 60 → 100... actually 30 → 60
        # Spec: <$5M=30; $5-25M=60; $25-100M=100; $100-200M=70; >$200M=40
        components["tbve_size_fit"] = 60.0
    elif tbve_m <= 100:
        components["tbve_size_fit"] = 100.0
    elif tbve_m <= 200:
        components["tbve_size_fit"] = 70.0
    else:
        components["tbve_size_fit"] = 40.0

    # 4. CoF franchise (15%): lower CoF = better
    cof = safe(r.get("cost_of_funds"))
    if cof is not None:
        # Score = max(0, 100 - cof * 25). 1% CoF → 75 pts; 4% → 0 pts.
        components["cof_franchise"] = max(0.0, 100.0 - cof * 25.0)
    else:
        components["cof_franchise"] = 50.0  # neutral when missing

    # 5. Credit quality proxy (15%): asset growth ≤ equity growth = better
    asset_cagr = safe(r.get("asset_cagr_5y"))
    equity_cagr = safe(r.get("equity_cagr_5y"))
    if asset_cagr is not None and equity_cagr is not None:
        gap = asset_cagr - equity_cagr  # positive gap = leveraging up
        components["credit_quality"] = max(0.0, 100.0 - max(0.0, gap) * 5.0)
    else:
        components["credit_quality"] = 50.0

    # Weighted composite
    weights = {
        "capital_efficiency": 0.30,
        "goodwill_burden": 0.15,
        "tbve_size_fit": 0.25,
        "cof_franchise": 0.15,
        "credit_quality": 0.15,
    }
    score = sum(components[k] * weights[k] for k in weights)
    return round(score, 2), components


# ─────────────────────────────────────────────────────────────────────────────
# QUALITATIVE SCORE (refined)
# ─────────────────────────────────────────────────────────────────────────────
def shareholder_accessibility_1_5(r):
    """Returns 1-5 score and a label string."""
    is_public = bool(r.get("is_public"))
    multi_bhc = bool(r.get("multi_bank_holdco"))
    status = r.get("shareholder_status") or ""
    asset_k = safe(r.get("ASSET"), 0)

    if is_public:
        return 5, "Public (SEC filings)"
    if status == "private_holdco":
        return (3, "Multi-bank holdco (carve-out)") if multi_bhc else (4, "Single-bank holdco (FR Y-6)")
    # status == 'no_holdco' or unknown
    if status == "no_holdco":
        if asset_k > 50_000:  # > $50M
            return 2, "No holdco — larger bank (unusual)"
        return 1, "No holdco — direct outreach required"
    return 3, "Unknown structure"


def holdco_structure_1_5(r):
    """Returns 1-5 score and label."""
    if r.get("multi_bank_holdco"):
        return 2, "Multi-bank holdco (penalty)"
    if r.get("shareholder_status") == "private_holdco":
        return 4, "Single-bank holdco (preferred)"
    if r.get("is_public"):
        return 4, "Public holdco"
    if r.get("shareholder_status") == "no_holdco":
        return 3, "No holdco"
    return 3, "Neutral"


def compute_qualitative_score(r):
    """0-100 qualitative score from 6 dimensions."""
    # Geographic fit: existing geo_fit_score is 1-5; convert to 0-100
    geo = safe(r.get("geo_fit_score"), 3) or 3
    geo_pts = (geo / 5.0) * 100.0

    # Shareholder accessibility: 1-5 → 0-100
    sh_score, sh_label = shareholder_accessibility_1_5(r)
    sh_pts = (sh_score / 5.0) * 100.0

    # Holdco structure: 1-5 → 0-100
    hc_score, hc_label = holdco_structure_1_5(r)
    hc_pts = (hc_score / 5.0) * 100.0

    # Analyst overrides default to 3 (neutral) when not present
    loan_mix = safe(r.get("loan_mix_score"), 3) or 3
    dep_quality = safe(r.get("deposit_quality_score"), 3) or 3
    lmh_synergy = safe(r.get("lmh_synergy_score"), 3) or 3

    loan_pts = (loan_mix / 5.0) * 100.0
    dep_pts = (dep_quality / 5.0) * 100.0
    lmh_pts = (lmh_synergy / 5.0) * 100.0

    score = (
        0.30 * geo_pts +
        0.25 * sh_pts +
        0.15 * hc_pts +
        0.10 * loan_pts +
        0.10 * dep_pts +
        0.10 * lmh_pts
    )
    return round(score, 2), {
        "geo_fit_pts": round(geo_pts, 1),
        "shareholder_access_pts": round(sh_pts, 1),
        "shareholder_access_score": sh_score,
        "shareholder_access_label": sh_label,
        "holdco_structure_pts": round(hc_pts, 1),
        "holdco_structure_score": hc_score,
        "holdco_structure_label": hc_label,
        "loan_mix_pts": round(loan_pts, 1),
        "deposit_quality_pts": round(dep_pts, 1),
        "lmh_synergy_pts": round(lmh_pts, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# OUTREACH APPROACH classification
# ─────────────────────────────────────────────────────────────────────────────
def outreach_approach(r):
    if r.get("is_public"):
        return "Public — investor relations / banker contact"
    if r.get("shareholder_status") == "private_holdco":
        if r.get("multi_bank_holdco"):
            return "Multi-BHC — engage parent company first"
        return "Family-controlled (FR Y-6) — direct CEO/Chairman outreach"
    return "No HoldCo — ownership discovery required"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    text, lo, hi, data = load_data()
    rows = data["rows"]
    print(f"Loaded {len(rows)} target banks.")

    # Preserve v1 composite and rank for audit
    for r in rows:
        r["composite_score_v1"] = r.get("composite_score")
        r["rank_v1"] = r.get("rank")
        r["quant_score_v1"] = r.get("quant_score")
        r["qual_score_v1"] = r.get("qual_score")

    # Compute new quant score (universe-relative percentile ranks)
    compute_quant_score(rows)

    # Compute new deal economics and qualitative scores
    for r in rows:
        deal_score, deal_components = deal_economics_score(r)
        r["deal_econ_score"] = deal_score
        r["deal_econ_components"] = deal_components

        qual_score, qual_components = compute_qualitative_score(r)
        r["qual_score_v2"] = qual_score
        r["qual_components"] = qual_components

        # Outreach approach
        r["outreach_approach"] = outreach_approach(r)

    # New composite
    for r in rows:
        c = 0.50 * r["quant_score_v2"] + 0.25 * r["deal_econ_score"] + 0.25 * r["qual_score_v2"]
        r["composite_score_v2"] = round(c, 2)

    # Re-rank by new composite (descending)
    rows.sort(key=lambda x: -x["composite_score_v2"])
    for i, r in enumerate(rows, 1):
        r["rank_v2"] = i
        # Compute rank delta (v1 - v2). Positive delta = moved UP in priority.
        if r.get("rank_v1") is not None:
            r["rank_delta"] = r["rank_v1"] - i
        else:
            r["rank_delta"] = None

    # Replace canonical fields so existing UI keeps working
    for r in rows:
        r["composite_score"] = r["composite_score_v2"]
        r["rank"] = r["rank_v2"]
        r["quant_score"] = r["quant_score_v2"]
        r["qual_score"] = r["qual_score_v2"]

    # Re-sort by new rank for cleanliness
    rows.sort(key=lambda x: x["rank"])

    print("\nTop 10 by refined methodology:")
    print(f"{'Rank':<5} {'v1Rank':<7} {'Delta':<6} {'Bank':<35} {'Comp':<6} {'Q':<5} {'DE':<5} {'Qual':<5}")
    for r in rows[:10]:
        delta = r.get("rank_delta")
        delta_str = f"+{delta}" if delta and delta > 0 else (str(delta) if delta is not None else "—")
        print(f"{r['rank']:<5} {r.get('rank_v1',''):<7} {delta_str:<5} {r['NAME'][:33]:<35} "
              f"{r['composite_score']:<6} {r['quant_score']:<5} {r['deal_econ_score']:<5} {r['qual_score']:<5}")

    # Save audit JSON
    audit = []
    for r in rows:
        audit.append({
            "name": r["NAME"],
            "city": r.get("CITY"),
            "rank_v1": r.get("rank_v1"),
            "composite_v1": r.get("composite_score_v1"),
            "rank_v2": r["rank_v2"],
            "composite_v2": r["composite_score_v2"],
            "rank_delta": r.get("rank_delta"),
            "quant_v2": r["quant_score_v2"],
            "deal_econ_v2": r["deal_econ_score"],
            "qual_v2": r["qual_score_v2"],
        })
    AUDIT.write_text(json.dumps({"rankings": audit}, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {AUDIT}")

    # Write back to HTML
    new_data_str = json.dumps(data)
    new_html = text[:lo] + new_data_str + text[hi:]
    HTML.write_text(new_html, encoding="utf-8")
    print(f"Wrote refreshed {HTML}")


if __name__ == "__main__":
    main()
