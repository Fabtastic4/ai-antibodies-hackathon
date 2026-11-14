#!/usr/bin/env python3
"""Keep only abguard-eligible designs in a refold-prepare queries.json.

    python3 pipeline/score/filter_queries.py \
        --queries mark/runs/x/prepare/holo/queries.json \
        --eligible reports/b1-novel-s1-eligible.csv \
        --prefix b1-novel-s1-

`refold-prepare` ranks designs by RFD4's own design metrics and knows nothing about abguard, so
its --top-n happily includes designs the gate rejects. Refolding those wastes GPU time on
candidates that can never be submitted - and the task PDF is explicit: filter before you rank.

Ids differ by construction: abguard rows carry our namespaced `<run>-her2_cdrh3_N` while the
queries carry RFD4's bare `her2_cdrh3_N`, so --prefix is stripped before matching.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--queries", type=Path, required=True)
    ap.add_argument("--eligible", type=Path, required=True)
    ap.add_argument("--prefix", default="", help="stripped from eligible ids before matching")
    ap.add_argument("--out", type=Path, help="default: overwrite --queries in place")
    args = ap.parse_args()

    for p in (args.queries, args.eligible):
        if not p.exists():
            print(f"{p}: not found", file=sys.stderr)
            return 2

    with args.eligible.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    id_col = "sequence_id" if rows and "sequence_id" in rows[0] else "design_id"
    keep = set()
    for r in rows:
        sid = r[id_col]
        keep.add(sid[len(args.prefix):] if args.prefix and sid.startswith(args.prefix) else sid)

    doc = json.loads(args.queries.read_text())
    qs = doc.get("queries", [])
    before = len(qs)
    kept = [q for q in qs if q.get("query_id") in keep]
    dropped = [q.get("query_id") for q in qs if q.get("query_id") not in keep]

    if not kept:
        print(f"{args.queries}: none of its {before} queries are eligible. "
              f"Check --prefix (eligible ids look like {rows[0][id_col]!r}, "
              f"queries like {qs[0].get('query_id')!r}).", file=sys.stderr)
        return 1

    doc["queries"] = kept
    out = args.out or args.queries
    out.write_text(json.dumps(doc, indent=1))
    print(f"{out}: kept {len(kept)}/{before} eligible queries, dropped {len(dropped)}")
    if dropped:
        print(f"   dropped (abguard rejects): {', '.join(dropped[:8])}"
              f"{' ...' if len(dropped) > 8 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
