#!/usr/bin/env python3
"""Turn the verified manifest into a stab-ddg request body.

Kept separate from the runner so the payload can be inspected, diffed and committed without
credentials, and so the shape is in one place when the live schema turns out to differ.

The structure is inlined as text because every other file-based model in this repo's recipes
takes its input that way; if the live schema wants an uploaded artifact instead, change
`structure_inline` to the upload id and nothing else moves.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=os.path.join(REPO, "reports/stab_ddg_request.json"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--inline-structure", action="store_true", default=True)
    a = ap.parse_args()

    man = json.load(open(a.manifest))
    cif_path = os.path.join(REPO, man["structure"])
    if not os.path.exists(cif_path):
        print(f"{man['structure']} missing -- run scripts/stab_ddg_prep.py", file=sys.stderr)
        return 2

    partners = man["partners"]
    if len(partners) != 2 or set(partners[0]) & set(partners[1]):
        print(f"partners must be two disjoint sets, got {partners}", file=sys.stderr)
        return 2

    body = {
        "operation": "predict-binding-ddg",
        "partners": {"first": partners[0], "second": partners[1]},
        "variants": [
            {
                "id": d["design_id"],
                "mutations": [
                    {"chain": m["chain"], "position": m["position"],
                     "wild_type": m["wild_type"], "mutant": m["mutant"]}
                    for m in d["mutations"]
                ],
            }
            for d in man["designs"]
        ],
    }
    if a.inline_structure:
        body["structure"] = {"format": "mmcif", "data": open(cif_path).read()}

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w") as fh:
        json.dump(body, fh)

    nmut = sum(len(v["mutations"]) for v in body["variants"])
    size = os.path.getsize(a.out) / 1e6
    print(f"{len(body['variants'])} variants, {nmut} mutations, {size:.1f} MB -> {a.out}",
          file=sys.stderr)
    print("partners: " + " vs ".join("+".join(p) for p in partners), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
