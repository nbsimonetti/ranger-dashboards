"""
Report what a dashboard actually holds after a refresh.

The refresh workflow can't tell "worked" from "ran but produced nothing" by exit
code alone — a script can exit 0 having fetched zero rows (dental did exactly that
when NPPES was unreachable). This reads the dashboard's own embedded data block and
reports the row count and the data's as-of stamp, so the job summary shows the truth.

Usage:  python .github/scripts/dashboard_state.py <folder>
Prints: "<rows> | <as-of>"   (rows = -1 when no data block could be read)
Exit 0 always — this is a reporter, not a gate.
"""
import glob
import json
import os
import re
import sys

START = "/*__DATA_START__*/"
END = "/*__DATA_END__*/"


def biggest_list(obj):
    """Row count = the largest list of records in the payload."""
    best = 0
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, list):
                best = max(best, len(v))
            elif isinstance(v, dict):
                best = max(best, biggest_list(v))
    return best


def main():
    if len(sys.argv) < 2:
        print("-1 | no folder given")
        return
    folder = sys.argv[1]
    pattern = re.compile(re.escape(START) + r"(.*?)" + re.escape(END), re.S)

    for path in sorted(glob.glob(os.path.join(folder, "*.html"))):
        try:
            html = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        m = pattern.search(html)
        if not m:
            continue
        blob = m.group(1).strip()
        if not blob or blob == "null":
            print("0 | (no data block populated)")
            return
        try:
            data = json.loads(blob)
        except ValueError as exc:
            print("-1 | unparseable data block (%s)" % str(exc)[:40])
            return
        meta = data.get("_meta", {}) if isinstance(data, dict) else {}
        as_of = (meta.get("generated_at") or meta.get("as_of")
                 or meta.get("sba_asof") or "unknown")
        print("%d | %s" % (biggest_list(data), as_of))
        return

    # dashboards whose data lives in a side-car JSON rather than the HTML
    for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
        try:
            data = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        meta = data.get("meta", data.get("_meta", {})) if isinstance(data, dict) else {}
        as_of = meta.get("generated_at") or meta.get("as_of") or "unknown"
        print("%d | %s (%s)" % (biggest_list(data), as_of, os.path.basename(path)))
        return

    print("-1 | no data block found")


if __name__ == "__main__":
    main()
