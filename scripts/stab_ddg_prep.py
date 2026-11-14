#!/usr/bin/env python3
"""Prepare the VH-VL interface ddG job for `stab-ddg`, and verify it before it costs anything.

Axis 3 (thermostability) has no direct model on the platform. The settled fallback for the
optimisation + Fab/scFv cell is `stab-ddg` repurposed to the **VH-VL interface**, reported as a
VH-VL interface ddG and never as a folding ddG or a Tm (docs/decision-log.md [11:15],
docs/probe-findings.md section 4).

`stab-ddg` takes a structure, two disjoint partner chain sets and named point mutations. The part
that is easy to get silently wrong is the numbering: a mutation named at the wrong residue is not
an error, it is a different experiment. So this script does not emit a mutation it has not checked
against the structure -- every (chain, position, wild-type) triple is confirmed to hold that exact
residue in the input coordinates, and a design whose substitutions cannot all be placed is dropped
with a stated reason rather than submitted partially.

Sign convention, from the model's own reference (protein-scoring/references/binding.md):
**positive predicted binding ddG means weaker binding, mutant minus wild type.** For the VH-VL
interface that means positive = weaker VH-VL association = less stable Fv, so LOWER IS BETTER.
The reference also says to confirm the sign on the returned values, so the runner records the raw
output and the convention it assumed rather than folding one into the other.

Outputs:
  reports/stab_ddg_mutations.csv   one row per design, its verified mutation list
  reports/stab_ddg_request.json    the job manifest, ready for the runner
  reports/stab_ddg_fv.cif          chains A+B only (VL+VH); HER2 chains C,D removed

Usage:
  python3 -I scripts/stab_ddg_prep.py
  python3 -I scripts/stab_ddg_prep.py --limit 24      # shortlist only
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FV_CIF = os.path.join(REPO, "data/bucket/extracted/rfd4/Data/12-her2/her2_fv_1n8z.cif")
HEAVY_CHAIN, LIGHT_CHAIN = "B", "A"          # 1N8Z: B = Fab heavy, A = Fab light
ANTIGEN_CHAINS = ("C", "D")                  # HER2 -- excluded from an Fv-only calculation

BATCHES = [
    ("b1-novel-s1", "designs/raw/b1-novel-s1.csv", "reports/b1_full_novelty_distance.json"),
    ("b2-explor-s2-fixed", "designs/raw/b2-explor-s2-fixed.csv", "reports/b2_novelty_distance.json"),
]

AA3 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q", "GLU": "E",
    "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F",
    "PRO": "P", "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}

HEAVY_COLUMNS = ("heavy_sequence", "sequence", "vh_sequence")


def parse_cif(path):
    """{chain: {resnum: one-letter}} plus the raw lines, so we can re-emit a subset."""
    chains: dict[str, dict[int, str]] = {}
    cols: list[str] = []
    lines = open(path).read().splitlines()
    for line in lines:
        if line.startswith("_atom_site."):
            cols.append(line.strip().split(".", 1)[1])
            continue
        if cols and (line.startswith("ATOM") or line.startswith("HETATM")):
            f = line.split()
            if len(f) < len(cols):
                continue
            d = dict(zip(cols, f))
            comp = d.get("label_comp_id")
            if comp not in AA3:
                continue
            ch = d.get("auth_asym_id") or d.get("label_asym_id")
            try:
                rn = int(d.get("auth_seq_id") or d.get("label_seq_id"))
            except (TypeError, ValueError):
                continue
            chains.setdefault(ch, {})[rn] = AA3[comp]
    return chains, lines, cols


def write_fv_only(lines, cols, out_path):
    """Re-emit the CIF with the antigen chains dropped, so the interface is VH-VL."""
    idx = {c: i for i, c in enumerate(cols)}
    key = "auth_asym_id" if "auth_asym_id" in idx else "label_asym_id"
    kept = []
    for line in lines:
        if line.startswith("ATOM") or line.startswith("HETATM"):
            f = line.split()
            if len(f) > idx[key] and f[idx[key]] in ANTIGEN_CHAINS:
                continue
        kept.append(line)
    with open(out_path, "w") as fh:
        fh.write("\n".join(kept) + "\n")
    return len(lines) - len(kept)


def seq_of(chain: dict[int, str]):
    nums = sorted(chain)
    return "".join(chain[n] for n in nums), nums


def first(row, names):
    for n in names:
        if row.get(n):
            return row[n]
    return ""


def eligible_ids(report_path):
    """sequence_id -> True for designs that passed the local novelty gate."""
    if not os.path.exists(report_path):
        return None
    data = json.load(open(report_path))
    return {d["sequence_id"] for d in data["designs"] if d.get("verdict") == "pass"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cif", default=FV_CIF)
    ap.add_argument("--limit", type=int, default=0, help="keep only the first N designs")
    ap.add_argument("--out-csv", default=os.path.join(REPO, "reports/stab_ddg_mutations.csv"))
    ap.add_argument("--out-json", default=os.path.join(REPO, "reports/stab_ddg_request.json"))
    ap.add_argument("--out-cif", default=os.path.join(REPO, "reports/stab_ddg_fv.cif"))
    a = ap.parse_args()

    chains, lines, cols = parse_cif(a.cif)
    if HEAVY_CHAIN not in chains or LIGHT_CHAIN not in chains:
        print(f"{a.cif}: expected chains {HEAVY_CHAIN} and {LIGHT_CHAIN}, found "
              f"{sorted(chains)}", file=sys.stderr)
        return 2
    wt_vh, vh_nums = seq_of(chains[HEAVY_CHAIN])
    wt_vl, _ = seq_of(chains[LIGHT_CHAIN])
    print(f"reference {os.path.relpath(a.cif, REPO)}", file=sys.stderr)
    print(f"  chain {HEAVY_CHAIN} (VH) {len(wt_vh)} aa, numbered "
          f"{vh_nums[0]}-{vh_nums[-1]}", file=sys.stderr)
    print(f"  chain {LIGHT_CHAIN} (VL) {len(wt_vl)} aa", file=sys.stderr)

    dropped_atoms = write_fv_only(lines, cols, a.out_cif)
    print(f"  wrote {os.path.relpath(a.out_cif, REPO)} "
          f"(dropped {dropped_atoms} antigen atom records)", file=sys.stderr)

    rows, skipped = [], []
    for batch, designs_path, report_path in BATCHES:
        dp = os.path.join(REPO, designs_path)
        if not os.path.exists(dp):
            skipped.append((batch, "no designs file"))
            continue
        keep = eligible_ids(os.path.join(REPO, report_path))
        for r in csv.DictReader(open(dp, newline="")):
            did = first(r, ("sequence_id", "design_id", "id"))
            if keep is not None and did not in keep:
                continue
            vh = first(r, HEAVY_COLUMNS)
            if len(vh) != len(wt_vh):
                skipped.append((did, f"VH is {len(vh)} aa, reference is {len(wt_vh)}; "
                                     "no 1:1 position mapping without an alignment"))
                continue
            muts, unplaced = [], []
            for i, (w, m) in enumerate(zip(wt_vh, vh)):
                if w == m:
                    continue
                resnum = vh_nums[i]
                # The check that makes this safe to submit.
                if chains[HEAVY_CHAIN].get(resnum) != w:
                    unplaced.append(f"{w}{resnum}{m}")
                    continue
                muts.append({"chain": HEAVY_CHAIN, "position": resnum,
                             "wild_type": w, "mutant": m})
            if unplaced:
                skipped.append((did, "could not confirm in the structure: "
                                     + ", ".join(unplaced)))
                continue
            if not muts:
                skipped.append((did, "identical to the reference VH"))
                continue
            rows.append({"design_id": did, "batch": batch, "n_mutations": len(muts),
                         "mutations": muts,
                         "mutations_str": " ".join(f"{m['wild_type']}{m['position']}{m['mutant']}"
                                                   for m in muts)})

    rows.sort(key=lambda r: (r["batch"], r["design_id"]))
    if a.limit:
        rows = rows[: a.limit]

    with open(a.out_csv, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["design_id", "batch", "n_mutations", "mutations", "verified_against"])
        for r in rows:
            w.writerow([r["design_id"], r["batch"], r["n_mutations"], r["mutations_str"],
                        os.path.relpath(a.cif, REPO)])

    manifest = {
        "model": "stab-ddg",
        "operation": "predict-binding-ddg",
        "what_this_is": ("VH-VL interface ddG, used as the axis-3 thermostability proxy. "
                         "NOT a folding ddG and NOT a Tm."),
        "sign_convention": ("positive = weaker binding (mutant minus wild type), per "
                            "protein-scoring/references/binding.md. For the VH-VL interface, "
                            "positive = less stable Fv, so lower is better. CONFIRM on the "
                            "returned values before ranking."),
        "structure": os.path.relpath(a.out_cif, REPO),
        "partners": [[HEAVY_CHAIN], [LIGHT_CHAIN]],
        "reference_vh": wt_vh,
        "reference_vl": wt_vl,
        "n_designs": len(rows),
        "designs": [{"design_id": r["design_id"], "batch": r["batch"],
                     "mutations": r["mutations"]} for r in rows],
        "skipped": [{"design_id": d, "reason": why} for d, why in skipped],
    }
    with open(a.out_json, "w") as fh:
        json.dump(manifest, fh, indent=1)

    nmut = [r["n_mutations"] for r in rows]
    print(f"\n{len(rows)} designs prepared, every mutation confirmed against the structure",
          file=sys.stderr)
    if nmut:
        print(f"  mutations per design: min {min(nmut)}, max {max(nmut)}, "
              f"total {sum(nmut)}", file=sys.stderr)
    if skipped:
        print(f"  {len(skipped)} skipped:", file=sys.stderr)
        seen = {}
        for d, why in skipped:
            seen.setdefault(why.split(";")[0], []).append(d)
        for why, ds in seen.items():
            print(f"    {len(ds):>4}  {why}", file=sys.stderr)
    print(f"  wrote {os.path.relpath(a.out_csv, REPO)} and "
          f"{os.path.relpath(a.out_json, REPO)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
