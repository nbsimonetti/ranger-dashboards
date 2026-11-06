"""
Core processor data for the M&A target dashboard.

WHAT THIS DOES
  Injects ma/core_data.json into ranger-ma-targets.html between the
  /*__CORE_START__*/ ... /*__CORE_END__*/ markers, and (with --signals) collects
  machine-readable LEADS about each bank's technology stack.

WHAT THIS DELIBERATELY DOES NOT DO
  It never assigns a core processor automatically. The core is only ever set by a
  human in core_data.json, with evidence and a source.

  That is a finding, not a shortcut. Four passive approaches were tested against
  this roster of 95 Texas banks ($26-197M) and none can carry the question:

    * Bank websites       - many return HTTP 403 to non-browser requests. Spoofing
                            a browser User-Agent to get around a WAF is off limits,
                            so a block is recorded as a block.
    * Certificate Transparency (crt.sh)
                          - per-bank queries rate-limit quickly and small banks
                            expose almost no subdomains; vendor-wide queries
                            (%.netteller.com) return HTTP 502.
    * DNS CNAME probing   - one hit in ~40 probes, and it pointed at Kasasa, a
                            product vendor, not a core.
    * What a site DOES reveal is usually the DIGITAL vendor, which is not the core.
                            Forte Bank runs Apiture digital over a CSI NuPoint core.

  So the signals below exist to give the team leads worth confirming, never answers.

VENDOR SIGNAL STRENGTH (for whoever is filling in core_data.json by hand)
  Near-definitive : NetTeller, Banno (Jack Henry only) | csiweb (CSI)
                    | iCore360, dcihosted (DCI) | a CNAME straight to a vendor host
                    | a vendor press release naming the bank AND its city
  Suggestive only : Fiserv or FIS digital front ends - both sell digital standalone
  No inference    : Q2, Alkami, Apiture, Narmi, Lumin, Kasasa, website CMS hosts

Run:  python ma/core_lookup.py                 inject curated data only
      python ma/core_lookup.py --signals       also refresh technology leads
      python ma/core_lookup.py --selftest      offline checks
"""
import json
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
HTML = HERE / "ranger-ma-targets.html"
DATA_JSON = HERE / "core_data.json"
CORE_START = "/*__CORE_START__*/"
CORE_END = "/*__CORE_END__*/"
UA = {"User-Agent": "ranger-dashboards/1.0 (bank technology research; "
                    "contact via nbsimonetti.github.io/ranger-dashboards)"}

BUCKETS = ["FIS", "Fiserv", "Jack Henry", "CSI", "DCI", "Other", "Unknown"]

# token -> (vendor, strength). strength: 'core' = near-definitive core tell,
# 'digital' = that vendor's digital product (core NOT implied), 'none' = no bearing.
FINGERPRINTS = {
    "netteller": ("Jack Henry", "core"),
    "banno": ("Jack Henry", "core"),
    "jackhenry": ("Jack Henry", "core"),
    "jhacorp": ("Jack Henry", "core"),
    "silverlake": ("Jack Henry", "core"),
    "csiweb": ("CSI", "core"),
    "nupoint": ("CSI", "core"),
    "icore360": ("DCI", "core"),
    "dcihosted": ("DCI", "core"),
    "datacenterinc": ("DCI", "core"),
    "fiservapps": ("Fiserv", "digital"),
    "fiserv": ("Fiserv", "digital"),
    "onlineaccess1": ("Fiserv", "digital"),
    "fisglobal": ("FIS", "digital"),
    "digitalinsight": ("(digital vendor)", "none"),
    "q2online": ("(digital vendor)", "none"),
    "alkami": ("(digital vendor)", "none"),
    "apiture": ("(digital vendor)", "none"),
    "narmi": ("(digital vendor)", "none"),
    "nymbus": ("(digital vendor)", "none"),
    "kasasa": ("(product vendor)", "none"),
    "kasasapages": ("(product vendor)", "none"),
}
SUBDOMAINS = ["onlinebanking", "online", "secure", "banking", "ebanking", "ib",
              "netteller", "start", "web", "mybank"]


# --------------------------------------------------------------------- rows ---
def read_rows():
    """Pull the target roster out of the dashboard's DATA blob (read-only)."""
    html = HTML.read_text(encoding="utf-8")
    raw = re.search(r"const DATA\s*=\s*(\{.*)", html, re.S).group(1)
    depth = 0
    end = None
    for i, ch in enumerate(raw):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    rows = json.loads(raw[:end])["rows"]
    return [r for r in rows if isinstance(r, dict)]


# ------------------------------------------------------------------ signals ---
def registrable(website):
    host = re.sub(r"^https?://", "", (website or "").strip()).split("/")[0].lower()
    host = host.split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host or None


def cname_chain(host):
    """CNAME target via nslookup. No stdlib DNS, and this avoids touching the
    bank's web server at all."""
    try:
        out = subprocess.run(["nslookup", "-type=CNAME", host],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:  # noqa: BLE001
        return None
    m = re.search(r"canonical name\s*=\s*([A-Za-z0-9.\-]+)", out)
    return m.group(1).rstrip(".").lower() if m else None


def fetch(url, timeout=20):
    """GET with an honest User-Agent. A 403 is recorded, never worked around."""
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.geturl(), r.read(300000).decode("utf-8", "replace"), None
    except urllib.error.HTTPError as e:
        return None, "", "http_%s" % e.code
    except Exception as e:  # noqa: BLE001
        return None, "", type(e).__name__


def match_tokens(text):
    found = {}
    low = (text or "").lower()
    for tok, (vendor, strength) in FINGERPRINTS.items():
        if tok in low:
            found[tok] = {"vendor": vendor, "strength": strength}
    return found


def collect_signals(rows, limit=None, pause=1.5):
    """Gather leads. Returns {CERT: {...}}; never sets a core."""
    out = {}
    todo = [r for r in rows if registrable(r.get("website"))]
    if limit:
        todo = todo[:limit]
    for i, r in enumerate(todo, 1):
        dom = registrable(r.get("website"))
        rec = {"domain": dom, "cnames": {}, "tokens": {}, "fetch": None}

        for sub in SUBDOMAINS:
            tgt = cname_chain("%s.%s" % (sub, dom))
            if tgt:
                rec["cnames"]["%s.%s" % (sub, dom)] = tgt
                rec["tokens"].update(match_tokens(tgt))

        final, html, err = fetch(r["website"])
        rec["fetch"] = err or "ok"
        if html:
            rec["tokens"].update(match_tokens(html))
            if final:
                rec["final_url"] = final
                rec["tokens"].update(match_tokens(final))

        out[str(r["CERT"])] = rec
        tok = ",".join(sorted(rec["tokens"])) or "-"
        print("  [%2d/%d] %-30s %-26s %-10s %s"
              % (i, len(todo), str(r["NAME"])[:28], dom[:24], rec["fetch"], tok))
        time.sleep(pause)
    return out


# ------------------------------------------------------------------- inject ---
def inject(payload):
    html = HTML.read_text(encoding="utf-8")
    if CORE_START not in html or CORE_END not in html:
        raise SystemExit("core markers not found in %s - add them first" % HTML.name)
    before = html.index(CORE_START) + len(CORE_START)
    after = html.index(CORE_END)
    blob = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    out = html[:before] + blob + html[after:]
    HTML.write_text(out, encoding="utf-8")
    return len(blob)


def summarise(payload, rows):
    by = {}
    for r in rows:
        rec = payload["banks"].get(str(r["CERT"]), {})
        core = rec.get("core", "Unknown")
        by[core] = by.get(core, 0) + 1
    return by


def selftest():
    assert registrable("https://www.fsbjunction.com/x") == "fsbjunction.com"
    assert registrable("http://cnbss.com") == "cnbss.com"
    t = match_tokens("https://bank.netteller.com/login")
    assert t["netteller"]["vendor"] == "Jack Henry" and t["netteller"]["strength"] == "core"
    t2 = match_tokens("powered by Apiture digital banking")
    assert t2["apiture"]["strength"] == "none", "Apiture must not imply a core"
    t3 = match_tokens("start.kasasapages.com")
    assert t3["kasasapages"]["strength"] == "none"
    d = json.loads(DATA_JSON.read_text(encoding="utf-8"))
    assert d["ranger"]["core"] in BUCKETS
    for cert, rec in d["banks"].items():
        assert rec["core"] in BUCKETS, (cert, rec["core"])
        assert rec.get("evidence"), "every tagged bank needs evidence: %s" % cert
    print("selftest OK (%d curated banks, baseline=%s)"
          % (len(d["banks"]), d["ranger"]["core"]))


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    payload = json.loads(DATA_JSON.read_text(encoding="utf-8"))
    rows = read_rows()

    if "--signals" in sys.argv:
        print("collecting technology leads (DNS + homepage; 403s recorded, not bypassed)...")
        lim = None
        for a in sys.argv:
            if a.startswith("--limit="):
                lim = int(a.split("=", 1)[1])
        payload["signals"] = collect_signals(rows, limit=lim)
        DATA_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                             encoding="utf-8")
        print("signals written back to core_data.json for review")

    # keep the roster count honest in the payload
    payload["_meta"]["roster"] = len(rows)
    payload["_meta"]["tagged"] = sum(
        1 for r in rows
        if payload["banks"].get(str(r["CERT"]), {}).get("core", "Unknown") != "Unknown")
    n = inject(payload)
    by = summarise(payload, rows)
    print("injected %.1f KB | baseline=%s | %d of %d tagged | %s"
          % (n / 1024, payload["ranger"]["core"], payload["_meta"]["tagged"],
             len(rows), by))


if __name__ == "__main__":
    main()
