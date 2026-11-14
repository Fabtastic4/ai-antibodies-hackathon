#!/usr/bin/env python3
"""NetSolP solubility, calibrated against measured binders, applied as a FLOOR not a cut.

    python3 pipeline/filter/solubility.py designs/raw/batch1-b1-novel-s1.csv
    python3 pipeline/filter/solubility.py <in.csv> --strict          # exit 1 if anything is below the floor
    python3 pipeline/filter/solubility.py <in.csv> --calibrate data/spr_quantified.netsolp.csv

NetSolP (DTU, Bioinformatics 2022) predicts probability of soluble expression in E. coli.
The organisers name it as one of four developability tools (task PDF p7), so we run it.

WHY THIS IS A FLOOR AND NOT A THRESHOLD
---------------------------------------
Measured on 14 Nov against the organisers' own SPR data. Scored 200 batch-1 designs and the
190 SPR-quantified trastuzumab variants - molecules that demonstrably express AND bind HER2:

                        n     min      p5    median     p95     max      sd
  our designs         200  0.4958  0.5110  0.5302   0.5489  0.5489  0.0113
  MEASURED binders    190  0.4960  0.5179  0.5426   0.5489  0.5489  0.0103

The two distributions are the same to within noise. The whole dynamic range is 0.05 wide,
because every design shares the trastuzumab framework and differs only in ~10 CDRH3 residues
out of ~230. NetSolP itself is fine - on diverse proteins it spreads properly (SIV integrase
0.283, human leptin 0.460, HhaI methyltransferase 0.765) - it simply cannot resolve CDRH3
point variants of one antibody.

So any cut that removes a meaningful share of designs removes a comparable share of KNOWN
GOOD molecules:

  cut 0.515  keeps 88.0% of designs  but also drops  4.2% of measured binders
  cut 0.520  keeps 81.5% of designs  but also drops  6.8% of measured binders
  cut 0.530  keeps 53.0% of designs  but also drops 14.2% of measured binders

And it carries no affinity signal: Pearson r(netsolp_min, KD nM) = -0.04 over the 190 binders.

Using it as a hard threshold would therefore discard good designs for a number that does not
track what we are judged on. The one defensible hard line is the floor of the measured set:
a design scoring BELOW every molecule known to work is outside the supported range. On batch 1
that rejects exactly 1 of 200. Everything above the floor is reported as a ranking tiebreak,
not a gate.

Note: `netsolp_solubility_min` is effectively the heavy-chain score for our designs, because the
light chain is fixed trastuzumab VL and scores a constant 0.5489.
"""

from __future__ import annotations

import argparse
import csv
import os
import statistics as st
import subprocess
import sys
from pathlib import Path

# Floor = minimum netsolp_solubility_min over the 190 SPR-quantified trastuzumab variants.
# Recompute with --calibrate if the reference set changes; do not hand-tune it upward.
MEASURED_FLOOR = 0.4960
SCORE_COL = "netsolp_solubility_min"
NETSOLP_HOME = os.environ.get("NETSOLP_HOME", str(Path.home() / "tools" / "netsolp"))


def run_netsolp(src: Path, dest: Path, model: str) -> bool:
    """Score with the NetSolP install on the VM. Returns False if it is not available."""
    runner = Path(NETSOLP_HOME) / "netsolp_csv.py"
    if not runner.exists():
        print(f"NetSolP not found at {runner}.", file=sys.stderr)
        print("  It lives on the team VM at ~/tools/netsolp (installed by the team, with the", file=sys.stderr)
        print("  quantized ONNX models). Set NETSOLP_HOME to point elsewhere.", file=sys.stderr)
        return False
    cmd = [sys.executable, str(runner), str(src), "-o", str(dest), "-m", model]
    print(f"== running NetSolP ({model}) on {src.name}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        return False
    return True


def scores(path: Path) -> list[float]:
    out = []
    with path.open(newline="") as fh:
        for r in csv.DictReader(fh):
            v = (r.get(SCORE_COL) or "").strip()
            if v:
                try:
                    out.append(float(v))
                except ValueError:
                    pass
    return out


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_in", type=Path)
    ap.add_argument("-o", "--out", type=Path, help="default: <input>.solubility.csv")
    ap.add_argument("-m", "--model", default="Distilled", choices=["Distilled", "ESM12", "ESM1b", "Both"])
    ap.add_argument("--floor", type=float, default=MEASURED_FLOOR)
    ap.add_argument("--calibrate", type=Path,
                    help="a scored reference CSV of MEASURED binders; sets the floor to its minimum")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any design is below the floor, so this can act as a gate")
    ap.add_argument("--skip-run", action="store_true",
                    help="input already has NetSolP columns; just apply the floor")
    args = ap.parse_args()

    if not args.csv_in.exists():
        print(f"{args.csv_in}: not found", file=sys.stderr)
        return 2

    floor = args.floor
    if args.calibrate:
        if not args.calibrate.exists():
            print(f"{args.calibrate}: not found", file=sys.stderr)
            return 2
        ref = scores(args.calibrate)
        if not ref:
            print(f"{args.calibrate}: no {SCORE_COL} column to calibrate from", file=sys.stderr)
            return 2
        floor = min(ref)
        print(f"== calibrated floor {floor:.4f} = min over {len(ref)} measured binders "
              f"in {args.calibrate.name} (median {st.median(ref):.4f})")

    scored = args.csv_in
    if not args.skip_run:
        scored = args.csv_in.with_suffix(".netsolp.csv")
        if not run_netsolp(args.csv_in, scored, args.model):
            return 3

    with scored.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print(f"{scored}: no rows", file=sys.stderr)
        return 2
    if SCORE_COL not in rows[0]:
        print(f"{scored}: no {SCORE_COL} column. Run without --skip-run.", file=sys.stderr)
        return 2

    id_col = next((c for c in ("design_id", "sequence_id") if c in rows[0]), None) or list(rows[0])[0]

    below, vals = [], []
    for r in rows:
        raw = (r.get(SCORE_COL) or "").strip()
        if not raw:
            r["solubility_flag"] = "not_scored"
            continue
        v = float(raw)
        vals.append(v)
        if v < floor:
            r["solubility_flag"] = "below_measured_floor"
            below.append((r[id_col], v))
        else:
            r["solubility_flag"] = "in_measured_range"

    out = args.out or args.csv_in.with_suffix(".solubility.csv")
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"\n== NetSolP solubility, floor {floor:.4f} (calibrated on measured binders)")
    if vals:
        print(f"   {len(vals)} scored | min {min(vals):.4f} | median {st.median(vals):.4f} | max {max(vals):.4f}")
    print(f"   in measured range : {sum(1 for r in rows if r.get('solubility_flag') == 'in_measured_range')}")
    print(f"   BELOW floor       : {len(below)}")
    for sid, v in below:
        print(f"      {sid}  {v:.4f}  < {floor:.4f}")
    print(f"\n   wrote {out}")
    print("   Use `solubility_flag` to drop below-floor rows and `netsolp_solubility_min` as a")
    print("   RANKING TIEBREAK only - it cannot separate good designs from bad here. See the")
    print("   docstring in this file for the calibration against 190 measured binders.")

    if args.strict and below:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
