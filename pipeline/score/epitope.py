#!/usr/bin/env python3
"""Compute the trastuzumab-HER2 interface from a PDB file at a heavy-atom cutoff.

Usage: epitope.py <pdb> [cutoff]
Chains: A = VL, B = VH (Fab), C = HER2 ECD.
Pure stdlib, no BioPython. Paratope and epitope are reported in PDB residue numbers.
"""
import sys
from collections import defaultdict

AA3 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V",
}


def load(path):
    """chain -> {resseq: (resname, [(x,y,z), ...])} for the first model, heavy atoms."""
    chains = defaultdict(dict)
    with open(path) as fh:
        for line in fh:
            rec = line[:6]
            if rec == "ENDMDL":
                break
            if rec not in ("ATOM  ", "HETATM"):
                continue
            altloc = line[16]
            if altloc not in (" ", "A"):
                continue
            resname = line[17:20].strip()
            if resname not in AA3:
                continue
            element = line[76:78].strip() or line[12:16].strip()[0]
            if element == "H":
                continue
            chain = line[21]
            resseq = line[22:27].strip()  # resseq + icode
            xyz = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
            entry = chains[chain].setdefault(resseq, (resname, []))
            entry[1].append(xyz)
    return chains


def contacts(a, b, cutoff):
    """Residue pairs within cutoff (heavy-atom min distance), plus per-residue min dist."""
    c2 = cutoff * cutoff
    pairs = []
    for ra, (na, aa) in a.items():
        for rb, (nb, ab) in b.items():
            best = None
            for x1, y1, z1 in aa:
                for x2, y2, z2 in ab:
                    d2 = (x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2
                    if best is None or d2 < best:
                        best = d2
            if best is not None and best <= c2:
                pairs.append((ra, na, rb, nb, best ** 0.5))
    return pairs


def keynum(r):
    digits = "".join(ch for ch in r if ch.isdigit())
    return (int(digits) if digits else 0, r)


def main():
    pdb = sys.argv[1]
    cutoff = float(sys.argv[2]) if len(sys.argv) > 2 else 4.5
    chains = load(pdb)
    present = {k: len(v) for k, v in sorted(chains.items())}
    print(f"# {pdb}  cutoff {cutoff} A  chains(residues): {present}\n")

    ab_chains = [c for c in ("B", "A") if c in chains]
    target = "C"
    if target not in chains:
        sys.exit(f"no chain {target} in {pdb}")

    epitope = {}      # HER2 resseq -> (resname, min dist, [ab partners])
    paratope = {}     # (chain, resseq) -> (resname, min dist, [her2 partners])

    for ch in ab_chains:
        for ra, na, rb, nb, d in contacts(chains[ch], chains[target], cutoff):
            e = epitope.setdefault(rb, [nb, d, []])
            e[1] = min(e[1], d)
            e[2].append(f"{ch}:{na}{ra}")
            p = paratope.setdefault((ch, ra), [na, d, []])
            p[1] = min(p[1], d)
            p[2].append(f"{nb}{rb}")

    print(f"## Epitope - HER2 chain {target}, {len(epitope)} residues")
    print("| HER2 residue | min dist (A) | contacts |")
    print("|---|---|---|")
    for r in sorted(epitope, key=keynum):
        nb, d, partners = epitope[r]
        print(f"| {AA3[nb]}{r} ({nb}) | {d:.2f} | {len(partners)} |")

    seq_e = ",".join(f"{AA3[epitope[r][0]]}{r}" for r in sorted(epitope, key=keynum))
    print(f"\nEpitope residue list: {seq_e}\n")

    print(f"## Paratope - Fab, {len(paratope)} residues")
    print("| chain | Fab residue | min dist (A) | contacts |")
    print("|---|---|---|---|")
    for ch, r in sorted(paratope, key=lambda k: (k[0], keynum(k[1]))):
        na, d, partners = paratope[(ch, r)]
        label = "VH" if ch == "B" else "VL"
        print(f"| {ch} ({label}) | {AA3[na]}{r} ({na}) | {d:.2f} | {len(partners)} |")

    for ch in ab_chains:
        rs = [r for (c, r) in paratope if c == ch]
        label = "VH" if ch == "B" else "VL"
        if rs:
            lo, hi = min(rs, key=keynum), max(rs, key=keynum)
            print(f"\n{label} (chain {ch}) paratope: {len(rs)} residues, "
                  f"{lo}-{hi}: " + ",".join(
                      f"{AA3[paratope[(ch, r)][0]]}{r}" for r in sorted(rs, key=keynum)))

    nums = [keynum(r)[0] for r in epitope]
    print(f"\n# HER2 epitope span: {min(nums)}-{max(nums)}")


if __name__ == "__main__":
    main()
