"""
Practice Transition & Solo-Target Radar - data refresh.

Derives a focused acquisition/deposit target list from the existing TX Physician
BD dataset: solo and small physician practices with the longest NPI tenure and
meaningful Medicare volume - the practices most likely to seek practice-acquisition
or partner buy-in/out financing and to move a banking relationship.

Source: the physician dashboard's embedded provider records (NPPES + CMS DAC +
Medicare Utilization + PECOS), re-read from physician/TX_Physician_Dashboard.html.
No network needed. (The scheduled workflow re-runs this; it changes only when the
underlying physician dataset is refreshed.)

Run:  python succession/refresh.py
"""
import sys
import json
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from footprint import inject_data, stamp  # noqa: E402

HERE = Path(__file__).resolve().parent
HTML = HERE / "succession-tx.html"
PHYS = HERE.parent / "physician" / "TX_Physician_Dashboard.html"
NOW_YEAR = dt.date.today().year


def load_physicians():
    txt = PHYS.read_text(encoding="utf-8", errors="replace")
    i = txt.find("RAW_DATA")
    start = txt.find("[", i)
    arr, _ = json.JSONDecoder().raw_decode(txt, start)
    return arr


def tenure(rec):
    d = rec.get("enumDate") or ""
    return NOW_YEAR - int(d[:4]) if d[:4].isdigit() else None


def is_solo(rec):
    if str(rec.get("practiceSizeCategory", "")).lower().startswith("solo"):
        return True
    sz = rec.get("estPracticeSize")
    return isinstance(sz, (int, float)) and sz <= 1


def score(rec, t):
    """0-100 transition-target score (honest proxy - see methodology caveats)."""
    s = 30
    if t is not None:
        s += 25 if t >= 15 else (15 if t >= 10 else 5)
    if is_solo(rec):
        s += 25
    pay = rec.get("totalMedicarePayment") or 0
    s += 15 if pay >= 50000 else (8 if pay >= 20000 else 0)
    if str(rec.get("practiceMaturity", "")).lower() in ("established", "mature"):
        s += 5
    return max(0, min(100, s))


def build(recs):
    out = []
    for r in recs:
        t = tenure(r)
        pay = r.get("totalMedicarePayment") or 0
        # focus: solo/small practices with a viable Medicare footprint
        if not (is_solo(r) or (isinstance(r.get("estPracticeSize"), (int, float)) and r["estPracticeSize"] <= 3)):
            continue
        if pay < 5000:
            continue
        out.append({
            "npi": r.get("npi"), "name": r.get("name"), "specialty": r.get("specialty"),
            "city": (r.get("city") or "").title(), "metro": r.get("metroArea") or "",
            "tenure": t, "solo": is_solo(r),
            "size": r.get("estPracticeSize"), "med_pay": round(pay),
            "benes": r.get("totalBeneficiaries"), "phone": r.get("phone") or "",
            "score": score(r, t),
        })
    out.sort(key=lambda x: -x["score"])
    by_spec, by_metro = {}, {}
    for p in out:
        by_spec[p["specialty"]] = by_spec.get(p["specialty"], 0) + 1
        if p["metro"]:
            by_metro[p["metro"]] = by_metro.get(p["metro"], 0) + 1
    solo_n = sum(1 for p in out if p["solo"])
    return {
        "_meta": stamp("TX Physician BD dataset (NPPES + CMS) - derived", {
            "targets": len(out), "solo": solo_n,
            "specialties": len(by_spec),
            "avg_tenure": round(sum(p["tenure"] for p in out if p["tenure"]) /
                                max(1, sum(1 for p in out if p["tenure"])), 1),
        }),
        "targets": out,
        "by_specialty": [{"k": k, "n": v} for k, v in sorted(by_spec.items(), key=lambda x: -x[1])[:20]],
        "by_metro": [{"k": k, "n": v} for k, v in sorted(by_metro.items(), key=lambda x: -x[1])],
    }


def main():
    recs = load_physicians()
    print("physician records read:", len(recs))
    data = build(recs)
    print("transition targets:", data["_meta"]["targets"],
          "| solo:", data["_meta"]["solo"], "| avg NPI tenure:", data["_meta"]["avg_tenure"])
    size = inject_data(HTML, data)
    print("injected %.0f KB into %s" % (size / 1024, HTML.name))


if __name__ == "__main__":
    main()
