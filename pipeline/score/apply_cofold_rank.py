#!/usr/bin/env python3
"""Re-rank the draft submission using measured Boltz-2 co-fold interface evidence.

Why this exists. rank.py's sort key is (-contacts_kept, min_ipae, -mutations), and
min_ipae is unobtainable on the hosted Nebius lane -- no PAE, no ipTM (docs/tools-nebius.md).
Slot 2 therefore collapsed to +inf for every design, leaving 18 designs tied at an
identical 0.75 contact-retention proxy.

cofold_epitope_frac fills that slot with a measured quantity: the fraction of the 19
published 1N8Z epitope residues the binder actually touches in the returned complex. It
is NOT ipTM and NOT min_ipae, and it is written only to its own columns.

Order: primary key unchanged (epitope_overlap_frac), then evidence tier, then the measured
fraction, then mutation count, then draft order.

  tier A  co-folded, frac > 0    measured on-epitope
  tier B  not co-folded          no evidence either way
  tier C  co-folded, frac == 0   measured OFF-epitope, demoted

Usage:
    python3 pipeline/score/apply_cofold_rank.py \
        --draft reports/draft-ranked-1540.csv \
        --cofold reports/cofold-contacts.csv \
        --out designs/submission.csv
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

NEW_COLS = ["cofold_epitope_frac", "cofold_n_epitope_hit", "cofold_n_contacts"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", type=Path, default=Path("reports/draft-ranked-1540.csv"))
    ap.add_argument("--cofold", type=Path, default=Path("reports/cofold-contacts.csv"))
    ap.add_argument("--out", type=Path, default=Path("designs/submission.csv"))
    a = ap.parse_args()

    draft = list(csv.DictReader(a.draft.open()))
    cof = {r["design_id"]: r for r in csv.DictReader(a.cofold.open())}

    def frac(did):
        r = cof.get(did)
        return float(r["cofold_epitope_frac"]) if r else None

    def tier(r):
        f = frac(r["design_id"])
        return 1 if f is None else (0 if f > 0 else 2)

    def sort_key(i_r):
        i, r = i_r
        f = frac(r["design_id"])
        return (
            -float(r["epitope_overlap_frac"]),
            tier(r),
            -(f if f is not None else 0.0),
            -int(r["mutations"]),
            i,
        )

    ranked = [r for _, r in sorted(enumerate(draft), key=sort_key)]

    for n, r in enumerate(ranked, 1):
        c = cof.get(r["design_id"])
        r["cofold_epitope_frac"] = c["cofold_epitope_frac"] if c else "n/a"
        r["cofold_n_epitope_hit"] = c["cofold_n_epitope_hit"] if c else "n/a"
        r["cofold_n_contacts"] = c["cofold_n_contacts"] if c else "n/a"

        # Keep the description to one line: what changed, which contacts survived, what the
        # co-fold measured. abguard wants free text, not an essay.
        m = re.search(r"\(([^)]*)\)", r["reason_for_selection"])
        contacts = m.group(1) if m else "see paratope table"
        base = f"CDRH3 redesign, {r['mutations']} mut; contacts {contacts} kept"
        if c and float(c["cofold_epitope_frac"]) > 0:
            base += f"; co-fold {c['cofold_n_epitope_hit']}/19 epitope residues"
        elif c:
            base += "; co-fold 0/19 epitope - off-epitope"
        else:
            base += "; no co-fold"
        r["reason_for_selection"] = base
        r["rank"] = str(n)

    cols = list(draft[0].keys()) + [c for c in NEW_COLS if c not in draft[0]]
    with a.out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(ranked)

    n_on = sum(1 for r in ranked if tier(r) == 0)
    n_off = sum(1 for r in ranked if tier(r) == 2)
    print(f"{a.out}: {len(ranked)} designs ranked "
          f"({n_on} measured on-epitope, {len(ranked)-n_on-n_off} unmeasured, {n_off} off-epitope)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
