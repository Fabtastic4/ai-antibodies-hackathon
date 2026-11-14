#!/usr/bin/env python3
"""How many designs do we need, how many do we have, and where are they being lost.

    python3 pipeline/status.py

Read-only. Every number prints the file it was counted from and the arithmetic that
produced it, so any of them can be checked by hand in one command - see `--how`.

The yields are measured from our own runs, not assumed. Re-measure after each batch:
the numbers that matter move.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

SLOTS = 20           # task PDF p8: a ranked list of up to 20
SELECTION = 3        # we want to pick 20 out of at least 3x that, or ranking is meaningless
REPO = Path(__file__).resolve().parents[1]

SCORE_COLS = ("iptm", "min_ipae", "ipsae", "plddt", "binder_plddt", "predicted_ddg")


def read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def reports(pattern: str) -> list[Path]:
    """Report files for real designs. Control and probe runs are deliberately excluded -
    they are test fixtures, and counting them would inflate every number below."""
    return sorted(
        p for p in (REPO / "reports").glob(pattern)
        if not any(w in p.name.lower() for w in ("control", "probe"))
    )


def dedupe(rows: list[dict[str, str]], key: str = "sequence_id") -> list[dict[str, str]]:
    """One row per design, even if a design appears in two report files."""
    seen: set[str] = set()
    out = []
    for r in rows:
        k = r.get(key, "")
        if k and k not in seen:
            seen.add(k)
            out.append(r)
    return out


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def bar(part: int, whole: int, width: int = 24) -> str:
    if not whole:
        return ""
    filled = round(width * part / whole)
    return "#" * filled + "." * (width - filled)


def line(label: str, n: int, source: str, note: str = "") -> None:
    print(f"  {label:<14}{n:>6}   {source:<42}{note}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--how", action="store_true", help="print the command that verifies each number by hand")
    ap.add_argument("--slots", type=int, default=SLOTS)
    ap.add_argument("--selection", type=float, default=SELECTION)
    args = ap.parse_args()

    raw_files = sorted((REPO / "designs" / "raw").glob("*.csv"))
    generated: list[dict[str, str]] = []
    for f in raw_files:
        generated += read(f)
    generated = dedupe(generated, "design_id")

    elig_files = reports("*-eligible.csv")
    eligible: list[dict[str, str]] = []
    for f in elig_files:
        eligible += read(f)
    eligible = dedupe(eligible)

    novelty: list[dict[str, str]] = []
    for f in reports("*novelty*.csv"):
        novelty += read(f)
    novelty = dedupe(novelty)

    submission = read(REPO / "designs" / "submission.csv")

    n_gen = len(generated)
    n_elig = len(eligible)
    uniq_elig = len({r.get("heavy_sequence", "") for r in eligible if r.get("heavy_sequence")})
    n_scored = sum(1 for r in submission if any((r.get(c) or "").strip() for c in SCORE_COLS))
    n_ranked = sum(1 for r in submission if (r.get("rank") or "").strip())

    print()
    print(f"SUBMISSION BUDGET - {args.slots} slots (task PDF p8: a ranked list of up to 20)")
    print("Read from the repo just now. Every number names its source file.")
    print()

    print("FUNNEL")
    src = ", ".join(f.name for f in raw_files) or "designs/raw/ is empty"
    line("generated", n_gen, src[:42])
    line("eligible", n_elig, ", ".join(f.name for f in elig_files)[:42] or "no *-eligible.csv yet",
         f"{pct(n_elig, n_gen)} of generated")
    line("unique", uniq_elig, "distinct heavy_sequence among eligible",
         f"{pct(uniq_elig, n_elig)} of eligible")
    line("scored", n_scored, "submission.csv rows with any score col")
    line("ranked", n_ranked, "submission.csv rows with a rank")
    print()
    if n_gen:
        print(f"  generated  {bar(n_gen, n_gen)}  {n_gen}")
        print(f"  eligible   {bar(n_elig, n_gen)}  {n_elig}")
        print(f"  unique     {bar(uniq_elig, n_gen)}  {uniq_elig}")
        print(f"  scored     {bar(n_scored, n_gen)}  {n_scored}")
        print()

    # Track split: abguard's own classification, not ours.
    if novelty:
        opt = sum(1 for r in novelty if r.get("novelty_class") == "novel")
        den = sum(1 for r in novelty if r.get("novelty_class") == "de_novo")
        print("TRACK SPLIT (abguard's classification - we do not choose the track)")
        line("optimisation", opt, "novelty_class=novel")
        line("de novo", den, "novelty_class=de_novo",
             "<-- separate podium, no candidates" if den == 0 else "")
        print()

    # Yield, measured rather than assumed.
    y_elig = n_elig / n_gen if n_gen else 0.0
    y_uniq = uniq_elig / n_elig if n_elig else 0.0
    usable = y_elig * y_uniq

    print("TARGET")
    print(f"  slots to fill                {args.slots}")
    if usable:
        print(f"  measured usable yield    {usable * 100:>5.1f}%   "
              f"({y_elig:.3f} eligible x {y_uniq:.3f} unique)")
        need_min = math.ceil(args.slots / usable)
        need_sel = math.ceil(args.slots * args.selection / usable)
        print(f"  minimum to generate      {need_min:>5.0f}   fills {args.slots} slots with no choice left")
        print(f"  for {args.selection:g}x selection          {need_sel:>5.0f}   so the top {args.slots} is actually the top")
        print(f"  generated so far         {n_gen:>5}", end="")
        if n_gen >= need_sel:
            print(f"   OK - {n_gen / (args.slots / usable):.1f}x selection")
        elif n_gen >= need_min:
            print(f"   thin - fills the list, little room to rank")
        else:
            print(f"   SHORT by {need_min - n_gen:.0f}")
    else:
        print("  no measured yield yet - gate one batch first:")
        print("    bash pipeline/filter/gate.sh designs/raw/<batch>.csv")
    print()

    if n_scored < min(uniq_elig, args.slots) and uniq_elig:
        print(f"BOTTLENECK: {uniq_elig} eligible designs, {n_scored} scored.")
        print("  Generation is ~13.7 s/design (4.37/min, measured on batch 1 - data-inventory.md),")
        print("  so candidates are cheap. Scoring is the scarce resource, and an unscored design")
        print("  cannot be ranked, so it cannot be submitted. Refold can run on Nebius, off the")
        print("  shared H100, in parallel with generation.")
        print()

    if args.how:
        print("VERIFY EACH NUMBER BY HAND")
        print("  generated     tail -n +2 designs/raw/batch1-b1-novel-s1.csv | grep -c .")
        print("  eligible      tail -n +2 reports/batch1-eligible.csv | grep -c .")
        print("  unique        cut -d, -f2 reports/batch1-eligible.csv | tail -n +2 | sort -u | wc -l")
        print("  track split   cut -d, -f5 reports/batch1-novelty.csv | tail -n +2 | sort | uniq -c")
        print("  re-gate       bash pipeline/filter/gate.sh designs/raw/<batch>.csv")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
