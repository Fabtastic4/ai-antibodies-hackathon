#!/usr/bin/env python3
"""Pull designed VH/VL pairs out of RFD4-Proteina CIFs into our submission table.

RFD4-Proteina writes one `*_generated.cif` per design, holding four polymer entities:
the trastuzumab light chain, the heavy chain with the redesigned CDRH3, and two HER2
fragments. We want the first two and must drop the antigen - submitting the target
would be an instant rejection.

Entities are identified by framework motif, not by index, because entity order is not
guaranteed across runs.

Usage:
    python3 pipeline/filter/cif_to_submission.py <run-dir> -o designs/raw/batch1.csv \
        --method rfd4-proteina --model-version her2-novel-2026-11-09 --seed 1

Then gate it:
    bash pipeline/filter/gate.sh designs/raw/batch1.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

# Framework motifs. Both are trastuzumab's own framework, which the HER2 weights keep
# fixed while redesigning CDRH3 only - so they are stable anchors for this task.
LIGHT_MOTIF = "DIQMTQSPSSLSASVGDRVTITC"
HEAVY_MOTIFS = ("WGQGTLVTVSS", "EVQLVESGGG")
MIN_LEN = 60  # a variable domain; shorter blocks are HER2 fragments or junk

BLOCK = re.compile(r"\n;\s*\n?(.*?)\n;", re.DOTALL)


def sequences(cif_text: str) -> list[str]:
    """Every semicolon-delimited sequence block, whitespace stripped, order preserved."""
    out: list[str] = []
    for raw in BLOCK.findall(cif_text):
        seq = "".join(raw.split()).upper()
        if seq and seq.isalpha() and seq not in out:
            out.append(seq)
    return out


def classify(seqs: list[str]) -> tuple[str | None, str | None]:
    heavy = light = None
    for seq in seqs:
        if len(seq) < MIN_LEN:
            continue
        if light is None and LIGHT_MOTIF in seq:
            light = seq
        elif heavy is None and any(m in seq for m in HEAVY_MOTIFS):
            heavy = seq
    return heavy, light


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path, help="directory searched recursively for *_generated.cif")
    ap.add_argument("-o", "--output", type=Path, default=repo / "designs" / "raw" / "batch.csv")
    ap.add_argument("--method", default="rfd4-proteina design")
    ap.add_argument("--model-version", default="", help="the weight, e.g. her2-novel-2026-11-09")
    ap.add_argument("--seed", default="")
    ap.add_argument("--prefix", default=None,
                    help="prepended to each design_id. Defaults to the run directory name, because\n"
                         "RFD4 numbers designs her2_cdrh3_0..N per run, so two runs collide - and\n"
                         "abguard requires a unique sequence_id, so a collision silently drops rows.\n"
                         "Pass --prefix '' to opt out.")
    args = ap.parse_args()

    prefix = f"{args.run_dir.name}-" if args.prefix is None else args.prefix
    cifs = sorted(args.run_dir.rglob("*_generated.cif"))
    if not cifs:
        print(f"{args.run_dir}: no *_generated.cif found", file=sys.stderr)
        return 2

    hdr = [
        'design_id', 'format', 'sequence', 'light_sequence',
        'parent', 'mutations', 'track', 'method',
        'model_version', 'seed', 'run_id', 'plddt',
        'iptm', 'ipsae', 'min_ipae', 'binder_plddt',
        'predicted_ddg', 'epitope_overlap_frac', 'thermostability_basis', 'liability_flags',
        'netsolp_solubility_min', 'cysteine_count', 'rank', 'reason_for_selection',
    ]
    rows, skipped = [], []

    for cif in cifs:
        heavy, light = classify(sequences(cif.read_text(errors="replace")))
        if not heavy or not light:
            skipped.append(f"{cif.parent.name}: heavy={bool(heavy)} light={bool(light)}")
            continue
        row = {k: "" for k in hdr}
        row.update(
            design_id=f"{prefix}{cif.parent.name}",
            format="fab",
            sequence=heavy,
            light_sequence=light,
            parent="trastuzumab",
            method=args.method,
            model_version=args.model_version,
            seed=args.seed,
            reason_for_selection=f"RFD4-Proteina CDRH3 redesign, {args.model_version or 'unspecified weight'}",
        )
        rows.append(row)

    if skipped:
        print(f"{len(skipped)} CIF(s) skipped (no VH/VL pair found):", file=sys.stderr)
        for s in skipped[:10]:
            print(f"  - {s}", file=sys.stderr)

    if not rows:
        print("no designs extracted", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=hdr)
        w.writeheader()
        w.writerows(rows)

    uniq = len({r["sequence"] for r in rows})
    print(f"{args.output}: {len(rows)} design(s) from {len(cifs)} CIF(s), {uniq} unique heavy chain(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
