#!/usr/bin/env python3
"""Turn our submission table into the table `abguard team-validate` expects.

We keep two tables on purpose:

  designs/submission.csv          our ranked table - provenance, scores, rank, reasoning
  designs/submission.abguard.csv  the five columns abguard requires, generated, never edited

abguard's input contract (read off abguard/schemas.py on the VM, 14 Nov):

  sequence_id         unique, non-empty          (primary key)
  kind                vhh | scfv | paired        (Fab is submitted as `paired`)
  heavy_sequence      canonical amino acids, 1..250
  light_sequence      required for `paired`, MUST be empty for vhh/scfv
  design_description  non-empty

The 250-residue limit is **per chain**, not VH+VL combined, and the alphabet is the 20
canonical amino acids only - no X, no gaps, no stop characters.

This script fails loudly on our own mistakes before abguard ever sees them, so the
13:00-16:00 loop is "fix one named row", not "0/20 valid, why".

Usage:
    python3 pipeline/filter/to_abguard.py                      # submission.csv -> submission.abguard.csv
    python3 pipeline/filter/to_abguard.py -i x.csv -o y.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

MAX_CHAIN_LENGTH = 250
MAX_SUBMISSION_ROWS = 20   # task PDF p8: a ranked list of up to 20
CANONICAL = set("ACDEFGHIKLMNPQRSTVWY")

# What people will actually type in the `format` column -> abguard's `kind`.
KIND_ALIASES = {
    "vhh": "vhh",
    "nanobody": "vhh",
    "sdab": "vhh",
    "vh": "vhh",
    "scfv": "scfv",
    "sc-fv": "scfv",
    "fab": "paired",
    "paired": "paired",
    "fv": "paired",
}

SINGLE_CHAIN = {"vhh", "scfv"}
OUT_COLUMNS = ("sequence_id", "kind", "heavy_sequence", "light_sequence", "design_description")


def clean_sequence(raw: str) -> str:
    """Uppercase and strip every kind of whitespace FASTA copy-paste brings along."""
    return "".join(raw.split()).upper()


def describe(row: dict[str, str]) -> str:
    """abguard requires a non-empty description. Prefer our reasoning, fall back to provenance."""
    reason = (row.get("reason_for_selection") or "").strip()
    if reason:
        return reason
    bits = [
        row.get("method", "").strip(),
        row.get("model_version", "").strip(),
        f"seed={row['seed'].strip()}" if (row.get("seed") or "").strip() else "",
        f"parent={row['parent'].strip()}" if (row.get("parent") or "").strip() else "",
    ]
    provenance = ", ".join(b for b in bits if b)
    return provenance or "no description recorded"


def convert(in_path: Path, out_path: Path, submission: bool = False) -> int:
    with in_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    if not rows:
        print(f"{in_path}: no design rows yet - nothing to validate.", file=sys.stderr)
        return 3

    out: list[dict[str, str]] = []
    problems: list[str] = []
    seen_ids: set[str] = set()

    for n, row in enumerate(rows, start=2):  # 2 = first data line, matches a spreadsheet
        where = f"{in_path.name}:{n}"

        design_id = (row.get("design_id") or row.get("sequence_id") or "").strip()
        if not design_id:
            problems.append(f"{where}: no design_id")
            continue
        if design_id in seen_ids:
            problems.append(f"{where}: duplicate design_id {design_id!r} - abguard needs unique ids")
            continue
        seen_ids.add(design_id)

        raw_format = (row.get("format") or row.get("kind") or "").strip().lower()
        kind = KIND_ALIASES.get(raw_format.replace(" ", ""))
        if kind is None:
            problems.append(
                f"{where}: {design_id}: format {raw_format!r} is not one of "
                f"{sorted(set(KIND_ALIASES))} - a whole IgG is not submittable"
            )
            continue

        heavy = clean_sequence(row.get("heavy_sequence") or row.get("sequence") or "")
        light = clean_sequence(row.get("light_sequence") or "")

        if not heavy:
            problems.append(f"{where}: {design_id}: no sequence")
            continue

        if kind in SINGLE_CHAIN and light:
            problems.append(
                f"{where}: {design_id}: kind={kind} must leave light_sequence empty "
                f"(abguard rule has_no_light_chain). For two chains use format=fab."
            )
            continue
        if kind == "paired" and not light:
            problems.append(
                f"{where}: {design_id}: kind=paired needs a light_sequence. "
                f"If this is a single chain with a linker, format=scfv."
            )
            continue

        for chain_name, seq in (("heavy", heavy), ("light", light)):
            if not seq:
                continue
            bad = sorted(set(seq) - CANONICAL)
            if bad:
                problems.append(
                    f"{where}: {design_id}: {chain_name}_sequence has non-canonical residue(s) "
                    f"{bad} - abguard accepts the 20 amino acids only"
                )
            if len(seq) > MAX_CHAIN_LENGTH:
                problems.append(
                    f"{where}: {design_id}: {chain_name}_sequence is {len(seq)} aa, "
                    f"limit is {MAX_CHAIN_LENGTH} per chain"
                )

        out.append(
            {
                "sequence_id": design_id,
                "kind": kind,
                "heavy_sequence": heavy,
                "light_sequence": light,
                "design_description": describe(row),
            }
        )

    # --- Submission-only checks -------------------------------------------------
    # abguard validates designs; it does not validate OUR handover rules. Without these a
    # 25-row table, or 20 rows with blank or duplicated ranks, passed the gate as "eligible".
    # Batch files legitimately hold 200 rows, so these run only in submission mode.
    if submission:
        if len(out) > MAX_SUBMISSION_ROWS:
            problems.append(
                f"{in_path.name}: {len(out)} rows, but the submission is capped at "
                f"{MAX_SUBMISSION_ROWS} (task PDF p8). Cut it before gating."
            )
        ranks = [(r["sequence_id"], (rows[i].get("rank") or "").strip()) for i, r in enumerate(out)]
        missing = [sid for sid, rk in ranks if not rk]
        if missing:
            problems.append(
                f"{in_path.name}: {len(missing)} row(s) have no rank "
                f"({', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}). "
                f"Rank order decides what gets tested - design #1 is tested in every scenario."
            )
        else:
            try:
                nums = sorted(int(rk) for _, rk in ranks)
            except ValueError:
                problems.append(f"{in_path.name}: non-integer rank value")
            else:
                if nums != list(range(1, len(nums) + 1)):
                    problems.append(
                        f"{in_path.name}: ranks must be the unique integers 1..{len(nums)}, got "
                        f"{nums[:8]}{'...' if len(nums) > 8 else ''} - duplicates or gaps make the "
                        f"'top N' ambiguous."
                    )

    # Identical sequences waste a slot, and abguard's competition-validate rejects a sequence
    # shared between teams for BOTH teams - so a duplicate is worse than a wasted row.
    by_seq: dict[tuple[str, str], list[str]] = {}
    for r in out:
        by_seq.setdefault((r["heavy_sequence"], r["light_sequence"]), []).append(r["sequence_id"])
    dupes = {k: v for k, v in by_seq.items() if len(v) > 1}
    if dupes:
        n_extra = sum(len(v) - 1 for v in dupes.values())
        detail = "; ".join(", ".join(v) for v in list(dupes.values())[:3])
        msg = (f"{in_path.name}: {n_extra} duplicate sequence(s) across {len(dupes)} group(s): {detail}"
               f"{' ...' if len(dupes) > 3 else ''}")
        if submission:
            problems.append(msg + " - dedupe before submitting; a duplicate wastes a slot.")
        else:
            print(f"NOTE  {msg}", file=sys.stderr)
            print("      Fine in a batch; dedupe on heavy_sequence before ranking.", file=sys.stderr)

    if problems:
        print(f"{len(problems)} row(s) cannot be submitted as written:\n", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\nFix these in designs/submission.csv. Nothing was written.", file=sys.stderr)
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUT_COLUMNS)
        writer.writeheader()
        writer.writerows(out)

    kinds = ", ".join(f"{k}={sum(r['kind'] == k for r in out)}" for k in ("vhh", "scfv", "paired"))
    print(f"{out_path}: {len(out)} design(s) ready for abguard ({kinds})")
    return 0


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-i", "--input", type=Path, default=repo / "designs" / "submission.csv")
    ap.add_argument("-o", "--output", type=Path, default=repo / "designs" / "submission.abguard.csv")
    ap.add_argument("--submission", action="store_true",
                    help="apply the handover rules too: <=20 rows, ranks = unique 1..N, no duplicate sequences")
    args = ap.parse_args()

    if not args.input.exists():
        print(f"{args.input}: not found", file=sys.stderr)
        return 2
    return convert(args.input, args.output, submission=args.submission)


if __name__ == "__main__":
    raise SystemExit(main())
