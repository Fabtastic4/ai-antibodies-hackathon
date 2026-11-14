#!/usr/bin/env python3
"""Score eligible designs on conservation of the measured CDRH3 paratope.

The four VH residues that actually touch HER2 inside the mutable CDRH3 window,
from 1N8Z at 4.5 A heavy-atom cutoff: W99, G103, F104, Y105.
VH numbering here is 1-based over the VH sequence and coincides with 1N8Z chain B.

Usage: paratope_check.py <eligible.csv> [raw_batch.csv] [-o out.csv]

Writes the per-design table to -o, or next to the eligible table as *-paratope.csv.
Stdout is the summary. Deterministic: run it twice, get identical bytes.
"""
import csv
import os
import sys
from collections import Counter

TZ_VH = ("EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKG"
         "RFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS")

# VH position (1-based) -> wild-type residue, min distance to HER2 in 1N8Z
CDRH3_CONTACTS = {99: ("W", 4.05), 103: ("G", 2.42), 104: ("F", 4.27), 105: ("Y", 3.32)}
WINDOW = range(99, 108)  # the generator's mutable span


def load_rows(path):
    with open(path) as fh:
        return list(csv.DictReader(fh))


def heavy_of(row):
    for k in ("heavy_sequence", "sequence", "heavy"):
        if row.get(k):
            return row[k].strip()
    return ""


def main():
    args = [a for a in sys.argv[1:]]
    out_path = None
    if "-o" in args:
        i = args.index("-o")
        out_path = args[i + 1]
        del args[i:i + 2]
    if not args:
        sys.exit(__doc__)
    elig_path = args[0]
    eligible = load_rows(elig_path)
    raw = load_rows(args[1]) if len(args) > 1 else []
    byseq = {heavy_of(r): r for r in raw}
    if out_path is None:
        base = os.path.basename(elig_path)
        for suffix in ("-eligible.csv", ".csv"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        out_path = os.path.join(os.path.dirname(elig_path) or ".", base + "-paratope.csv")

    for p, (wt, _) in CDRH3_CONTACTS.items():
        assert TZ_VH[p - 1] == wt, (p, TZ_VH[p - 1], wt)

    out = []
    seen = set()
    for r in eligible:
        h = heavy_of(r)
        if not h or len(h) != len(TZ_VH):
            continue
        if h in seen:
            continue
        seen.add(h)
        muts = [p for p in WINDOW if h[p - 1] != TZ_VH[p - 1]]
        lost = [f"{TZ_VH[p-1]}{p}{h[p-1]}" for p in CDRH3_CONTACTS if h[p - 1] != TZ_VH[p - 1]]
        kept = [p for p in CDRH3_CONTACTS if h[p - 1] == TZ_VH[p - 1]]
        src = byseq.get(h, {})
        out.append({
            "design_id": r.get("sequence_id") or r.get("design_id") or src.get("design_id", "?"),
            "cdrh3": h[98:107],
            "cdrh3_mutations": len(muts),
            "contacts_kept": len(kept),
            "contacts_kept_pos": "+".join(f"{TZ_VH[p-1]}{p}" for p in sorted(kept)) or "none",
            "contacts_lost": ",".join(sorted(lost)) or "none",
            "g103_kept": "yes" if h[102] == "G" else "no",
            "heavy_sequence": h,
        })

    out.sort(key=lambda d: (-d["contacts_kept"], -d["cdrh3_mutations"]))

    n = len(out)
    print(f"Unique eligible designs analysed: {n}")
    print(f"Wild-type CDRH3 window 99-107: {TZ_VH[98:107]}")
    print("Measured CDRH3-HER2 contacts: W99 (4.05 A), G103 (2.42 A), F104 (4.27 A), Y105 (3.32 A)\n")

    dist = Counter(d["contacts_kept"] for d in out)
    print("| CDRH3 contact residues preserved | designs | share |")
    print("|---|---|---|")
    for k in sorted(dist, reverse=True):
        print(f"| {k} of 4 | {dist[k]} | {100*dist[k]/n:.1f}% |")

    g = Counter(d["g103_kept"] for d in out)
    print(f"\nG103 (closest contact, 2.42 A) preserved: {g['yes']}/{n} ({100*g['yes']/n:.1f}%)")

    per = Counter()
    for d in out:
        for lost in d["contacts_lost"].split(","):
            if lost != "none":
                per[lost[:-1]] += 1
    print("\n| Contact | designs that mutate it | share |")
    print("|---|---|---|")
    for pos in ("W99", "G103", "F104", "Y105"):
        c = sum(v for k, v in per.items() if k.startswith(pos))
        print(f"| {pos} | {c} | {100*c/n:.1f}% |")

    print("\nCross-tab: CDRH3 mutation count x contacts preserved")
    print("| mutations | 4 kept | 3 | 2 | 1 | 0 | total |")
    print("|---|---|---|---|---|---|---|")
    xt = Counter((d["cdrh3_mutations"], d["contacts_kept"]) for d in out)
    for m in sorted({d["cdrh3_mutations"] for d in out}):
        cells = [xt.get((m, k), 0) for k in (4, 3, 2, 1, 0)]
        print(f"| {m} | " + " | ".join(str(c) for c in cells) + f" | {sum(cells)} |")

    cols = ["design_id", "cdrh3", "cdrh3_mutations", "contacts_kept",
            "contacts_kept_pos", "contacts_lost", "g103_kept", "heavy_sequence"]
    dest = out_path
    with open(dest, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    print(f"\nWrote {dest} ({n} rows)")

    top = [d for d in out if d["contacts_kept"] >= 3 and d["cdrh3_mutations"] >= 6]
    print(f"\nPriority for refold scoring (>=3 contacts kept AND >=6 mutations): {len(top)}")
    for d in top[:15]:
        print(f"  {d['design_id']:<28} {d['cdrh3']}  muts={d['cdrh3_mutations']} "
              f"kept={d['contacts_kept_pos']:<18} lost={d['contacts_lost']}")


if __name__ == "__main__":
    main()
