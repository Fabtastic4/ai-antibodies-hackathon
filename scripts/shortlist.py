#!/usr/bin/env python3
"""Build the refold shortlist: eligible designs that still touch HER2 where it matters.

Why a shortlist at all. We have 211 novelty-eligible designs and 20 submission slots, and the
refold is the stage everything is blocked on. Refolding all of them is ~50 min of H100; refolding
the ones that can actually win an axis is ~10.

The filter that does the work is G103. It is the closest paratope contact to HER2 in 1N8Z, at
2.42 A, and 175 of the 211 eligible designs mutate it away. Epitope preservation is judged
experimentally by competitive binding against trastuzumab, so a design that has dropped the
closest contact is carrying a much weaker claim on that axis than its contact count suggests.
`contacts_kept` alone does not express this: a design can keep two peripheral contacts, lose
G103, and still look mid-table.

Hard filters (a design must pass both):
  * passes the local novelty pre-check -- scripts/novelty_distance.py
  * retains G103

Then ranked on, in order:
  1. contacts_kept          descending -- axis 2, the evidence we actually hold
  2. novelty distance       descending -- margin against abguard's 610,109-row reference,
                                          which is 85k rows wider than the one we can see
  3. netsolp_solubility_min descending -- developability floor, a tiebreak and not a filter
                                          (decision log [14:05])
  4. design_id                          -- so the order is stable across runs

Deduped on heavy chain: `competition-validate` rejects sequences shared between teams, so a
duplicate inside our own 20 is pure waste.

Outputs:
  designs/shortlist_g103.csv                      ranked, with every number and its source
  reports/shortlist-<batch>-eligible.csv          per batch, in the shape refold.sh --eligible wants

Usage:
  python3 -I scripts/shortlist.py
  python3 -I scripts/shortlist.py --top 20
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BATCHES = [
    {
        "batch": "b1-novel-s1",
        "paratope": "reports/b1-novel-s1-paratope.csv",
        "solubility": "reports/b1-novel-s1-solubility.csv",
        "novelty": "reports/b1_full_novelty_distance.json",
        "eligible": "reports/b1-novel-s1-eligible.csv",
    },
    {
        "batch": "b2-explor-s2-fixed",
        "paratope": "reports/b2-explor-s2-fixed-paratope.csv",
        "solubility": "reports/b2-explor-s2-fixed-solubility.csv",
        "novelty": "reports/b2_novelty_distance.json",
        "eligible": "reports/b2-explor-s2-fixed-eligible.csv",
    },
]
REFOLD_TABLES = ["reports/b1_refold_metrics.csv", "reports/b2_refold_metrics.csv"]
BATCH_PREFIXES = ("b1-novel-s1-", "b2-explor-s2-fixed-")


def rel(p):
    return os.path.join(REPO, p)


def read_csv(path):
    p = rel(path)
    if not os.path.exists(p):
        return []
    with open(p, newline="") as fh:
        return list(csv.DictReader(fh))


def bare(did):
    for p in BATCH_PREFIXES:
        if did.startswith(p):
            return did[len(p):]
    return did


def num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top", type=int, default=0, help="keep only the best N overall")
    ap.add_argument("--out", default="designs/shortlist_g103.csv")
    a = ap.parse_args()

    # refold metrics are keyed on the bare id
    # Qualify bare score ids up into their file's batch. b1 and b2 both number designs
    # from 0, so matching on the bare id alone hands b2 design 26 batch 1's scores.
    refold = {}
    for path in REFOLD_TABLES:
        prefix = next((p for tok, p in (("b1", BATCH_PREFIXES[0]), ("b2", BATCH_PREFIXES[1]))
                       if os.path.basename(path).startswith(tok)), None)
        for r in read_csv(path):
            raw = r.get("query_id") or r.get("design_id") or ""
            if not raw:
                continue
            key = raw if raw.startswith(BATCH_PREFIXES) else (prefix or "") + bare(raw)
            refold[key] = r

    rows, stats = [], {}
    for b in BATCHES:
        nov = {}
        np_ = rel(b["novelty"])
        if os.path.exists(np_):
            for d in json.load(open(np_))["designs"]:
                nov[d["sequence_id"]] = d
        sol = {r.get("sequence_id"): r for r in read_csv(b["solubility"])}
        elig_rows = {r.get("sequence_id"): r for r in read_csv(b["eligible"])}

        para = read_csv(b["paratope"])
        n_g103 = n_elig = 0
        for r in para:
            did = r["design_id"]
            n = nov.get(did)
            passes = bool(n and n.get("verdict") == "pass")
            keeps = (r.get("g103_kept") or "").strip().lower() == "yes"
            n_elig += passes
            n_g103 += keeps
            if not (passes and keeps):
                continue
            rf = refold.get(did, {})
            s = sol.get(did, {})
            rows.append({
                "design_id": did,
                "batch": b["batch"],
                "cdrh3": r.get("cdrh3"),
                "cdrh3_mutations": r.get("cdrh3_mutations"),
                "contacts_kept": int(num(r.get("contacts_kept"), 0)),
                "contacts_kept_pos": r.get("contacts_kept_pos"),
                "contacts_lost": r.get("contacts_lost"),
                "g103_kept": "yes",
                "novelty_distance": n.get("distance_display"),
                "_novelty_sort": num(n.get("distance_to_nearest_measured"), 0) or 0,
                "netsolp_solubility_min": s.get("netsolp_solubility_min"),
                "solubility_flag": s.get("solubility_flag"),
                "min_ipae": rf.get("min_ipae") or "",
                "iptm": rf.get("iptm") or "",
                "binder_plddt": rf.get("binder_plddt") or "",
                "refold_status": "done" if rf.get("min_ipae") else "needed",
                "heavy_sequence": r.get("heavy_sequence") or elig_rows.get(did, {}).get("heavy_sequence", ""),
                "light_sequence": elig_rows.get(did, {}).get("light_sequence", ""),
                "kind": elig_rows.get(did, {}).get("kind", "paired"),
                "design_description": elig_rows.get(did, {}).get("design_description", ""),
            })
        stats[b["batch"]] = {"scored": len(para), "eligible": n_elig, "g103_kept": n_g103}

    # dedupe on heavy chain -- competition-validate drops sequences shared between teams
    seen, deduped, dropped = set(), [], 0
    for r in sorted(rows, key=lambda r: r["design_id"]):
        h = r["heavy_sequence"]
        if h and h in seen:
            dropped += 1
            continue
        seen.add(h)
        deduped.append(r)

    deduped.sort(key=lambda r: (
        -r["contacts_kept"],
        -r["_novelty_sort"],
        -(num(r["netsolp_solubility_min"], 0) or 0),
        r["design_id"],
    ))
    for i, r in enumerate(deduped, 1):
        r["rank"] = i
    if a.top:
        deduped = deduped[: a.top]

    cols = ["rank", "design_id", "batch", "cdrh3", "cdrh3_mutations", "contacts_kept",
            "contacts_kept_pos", "contacts_lost", "g103_kept", "novelty_distance",
            "netsolp_solubility_min", "solubility_flag", "min_ipae", "iptm", "binder_plddt",
            "refold_status", "kind", "heavy_sequence", "light_sequence", "design_description"]
    out = rel(a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(deduped)

    # per-batch inputs in the shape refold.sh --eligible expects
    written = []
    for b in BATCHES:
        sub = [r for r in deduped if r["batch"] == b["batch"]]
        if not sub:
            continue
        p = rel(f"reports/shortlist-{b['batch']}-eligible.csv")
        with open(p, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["sequence_id", "heavy_sequence", "design_description", "kind",
                        "light_sequence"])
            for r in sub:
                w.writerow([r["design_id"], r["heavy_sequence"],
                            r["design_description"] or "G103-retaining shortlist",
                            r["kind"], r["light_sequence"]])
        written.append((os.path.relpath(p, REPO), len(sub)))

    for bname, s in stats.items():
        print(f"{bname}: {s['scored']} scored, {s['eligible']} eligible, "
              f"{s['g103_kept']} retain G103", file=sys.stderr)
    print(f"\nshortlist: {len(deduped)} designs"
          + (f" ({dropped} dropped as duplicate heavy chains)" if dropped else ""),
          file=sys.stderr)
    need = sum(1 for r in deduped if r["refold_status"] == "needed")
    print(f"  already refolded : {len(deduped) - need}", file=sys.stderr)
    print(f"  refold needed    : {need}  (~{need * 16 // 60}m{need * 16 % 60}s at 16 s/design)",
          file=sys.stderr)
    print(f"  wrote {os.path.relpath(out, REPO)}", file=sys.stderr)
    for p, n in written:
        print(f"  wrote {p}  ({n} designs, for refold.sh --eligible)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
