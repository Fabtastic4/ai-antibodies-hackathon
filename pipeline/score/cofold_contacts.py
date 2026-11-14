#!/usr/bin/env python3
"""Interface metrics from a Boltz-2 co-fold mmCIF, because the hosted lane gives no ipTM.

Confirmed 14 Nov with `forge.py schema`: boltz2, openfold3, chai1 and protenix-v2 on Nebius
report NO ipTM and NO PAE. openfold3 states "CIF output only". So `min_ipae`/`iptm` -- what
rank.py wants for axis 1 -- are unobtainable without the Apheris Foundry path on the VM.

`docs/tools-nebius.md` names the fallback: "count cross-chain contacts in the returned mmCIF
yourself". That is what this does. It is a DIFFERENT metric from ipTM and is written to its own
column, never to `iptm` or `min_ipae`.

Reported per design:
    n_contacts        heavy-atom pairs < cutoff between the binder chain and the target chain
    n_epitope_hit     how many of the trastuzumab epitope residues the binder touches
    epitope_frac      n_epitope_hit / len(epitope list)
    contact_residues  which target residues are touched

Usage:
    cofold_contacts.py model.cif --binder H --target C [--cutoff 4.5]
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys

# HER2 epitope, trastuzumab, from docs/epitope.md (PDB 1N8Z, 4.5 A, 19 residues, subdomain IV).
HER2_EPITOPE = [557, 558, 560, 561, 563, 570, 571, 573, 593, 594, 595, 596,
                598, 599, 600, 601, 602, 603, 604]


def parse_cif_atoms(path):
    """Minimal mmCIF atom_site reader: (chain, resseq, element, x, y, z) for heavy atoms."""
    cols, rows, in_loop, header = {}, [], False, []
    for line in pathlib.Path(path).read_text().splitlines():
        s = line.strip()
        if s.startswith("_atom_site."):
            header.append(s.split(".", 1)[1])
            in_loop = True
            continue
        if in_loop and header and not s.startswith("_"):
            if s.startswith("#") or not s:
                if rows:
                    break
                continue
            parts = s.split()
            if len(parts) < len(header):
                continue
            if not cols:
                cols = {n: i for i, n in enumerate(header)}
            rows.append(parts)
    if not cols:
        sys.exit(f"{path}: no _atom_site loop found")

    def pick(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    ci = pick("auth_asym_id", "label_asym_id")
    ri = pick("auth_seq_id", "label_seq_id")
    ei = pick("type_symbol")
    xi, yi, zi = pick("Cartn_x"), pick("Cartn_y"), pick("Cartn_z")
    out = []
    for p in rows:
        try:
            if ei is not None and p[ei].upper() == "H":
                continue  # heavy atoms only
            out.append((p[ci], int(p[ri]), float(p[xi]), float(p[yi]), float(p[zi])))
        except (ValueError, IndexError):
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cif")
    ap.add_argument("--binder", default="H")
    ap.add_argument("--target", default="C")
    ap.add_argument("--cutoff", type=float, default=4.5)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    atoms = parse_cif_atoms(a.cif)
    b = [t for t in atoms if t[0] == a.binder]
    c = [t for t in atoms if t[0] == a.target]
    if not b or not c:
        chains = sorted({t[0] for t in atoms})
        sys.exit(f"chain {a.binder!r} or {a.target!r} absent; file has {chains}")

    cut2 = a.cutoff ** 2
    pairs, touched = 0, set()
    for _, _, x1, y1, z1 in b:
        for _, r2, x2, y2, z2 in c:
            d2 = (x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2
            if d2 < cut2:
                pairs += 1
                touched.add(r2)

    hits = sorted(touched & set(HER2_EPITOPE))
    res = {
        "n_contacts": pairs,
        "n_target_residues": len(touched),
        "n_epitope_hit": len(hits),
        "epitope_frac": round(len(hits) / len(HER2_EPITOPE), 4),
        "epitope_residues_hit": hits,
        "cutoff": a.cutoff,
        "metric_note": "cross-chain heavy-atom contacts, NOT ipTM and NOT min_ipae",
    }
    print(json.dumps(res, indent=2) if a.json else
          " ".join(f"{k}={v}" for k, v in res.items() if not isinstance(v, list)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
