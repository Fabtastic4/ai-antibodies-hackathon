#!/usr/bin/env python3
"""How far is each design from the nearest CDRH3 anyone has already measured?

This is the number abguard rejects on, computed locally, with no dependencies
beyond the standard library so that it runs on any teammate's laptop.

Why it exists: all six rejections in batch 1 failed novelty against the measured
HER2 screen, not against trastuzumab (see docs/abguard.md). abguard is on the VM
and holds a 610,109-row reference database inside its wheel; this script
reproduces the part of that check we can run offline, against the 525k CDRH3s
the organisers actually shipped us, so a batch can be filtered before any GPU
time is spent on it.

Three details that decide whether the answer is right at all:

1. abguard compares IMGT CDRH3s. The FACS table's `cdrh3` column holds the
   10-mer core, and comparing against those cores hands every design three free
   mutations from the flanks. So every reference CDRH3 here is re-extracted from
   its `vh_sequence` -- the segment between the conserved cysteine and the
   WGxG motif -- which yields the true 13-mer (SR + core + Y for a trastuzumab
   variant) and also handles the rows that are a different antibody entirely.
2. The metric is Levenshtein distance, not identity and not Hamming distance:
   a design can be 10 substitutions from a measured sequence and still only 2
   edits away from it if the loop is shifted.
3. The bar is >= 3 for our track (whole-Fv identity >= 0.70), not >= 4.

Distances are computed exactly up to --cutoff and reported as cutoff+1 beyond
it, written in the output as ">N". The eligibility verdict only ever needs 3.

Usage:
    python3 -I scripts/novelty_distance.py                   # batch 1, default paths
    python3 -I scripts/novelty_distance.py --designs x.csv --cutoff 5
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
import zipfile
from collections import Counter, defaultdict

# Wild-type trastuzumab, IMGT CDRH3 (13-mer). Confirmed live against
# `abguard novelty-report`, which returns cdrh3_confidence 0.875 for it.
TRASTUZUMAB_CDRH3 = "SRWGGDGFYAMDY"

# Our track's bar. abguard: MUTATIONS_REQUIRED = {novel: 3, de_novo: 2}, and
# whole-Fv identity only selects which bar applies.
MUTATIONS_REQUIRED = 3

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HER2 = os.path.join(REPO, "data/bucket/extracted/hackathon-data/her2-trastuzumab")
FACS_ZIP = os.path.join(HER2, "tz_her2_facs_3classes_524346.csv.zip")
SPR_CSV = os.path.join(HER2, "trastuzumab_her2_spr_all_768.csv")
DESIGNS = os.path.join(REPO, "designs/submission_b1_all20.csv")
REFOLD = os.path.join(REPO, "reports/b1_refold_metrics.csv")

# The conserved cysteine at IMGT 104, then the loop, then the J-region WGxG.
# Non-greedy, and we take the LAST match so a cysteine earlier in the V-region
# cannot capture the loop.
CDR3_RE = re.compile(r"C([ACDEFGHIKLMNPQRSTVWY]{3,30}?)(?=W[GA][QKRGS]G)")


def extract_cdrh3(vh: str) -> str | None:
    """The IMGT CDRH3 of a heavy chain, or None if the motifs are not found."""
    last = None
    for last in CDR3_RE.finditer(vh):
        pass
    return last.group(1) if last else None


def lev_cutoff(a: str, b: str, k: int) -> int:
    """Levenshtein distance, exact while <= k, else k + 1.

    Full-width rows with a (k + 1) sentinel outside the band, so cells the band
    excludes can never be read as a real value. Aborts as soon as a whole row
    exceeds k, which is what makes a 525k-row scan tractable in pure Python.
    """
    # Equal prefixes and suffixes never contribute to an optimal alignment.
    i = 0
    la, lb = len(a), len(b)
    while i < la and i < lb and a[i] == b[i]:
        i += 1
    a, b = a[i:], b[i:]
    while a and b and a[-1] == b[-1]:
        a, b = a[:-1], b[:-1]
    la, lb = len(a), len(b)
    if la == 0:
        return lb if lb <= k else k + 1
    if lb == 0:
        return la if la <= k else k + 1
    if abs(la - lb) > k:
        return k + 1

    big = k + 1
    prev = list(range(lb + 1))
    for p in range(k + 1, lb + 1):
        prev[p] = big
    for i in range(1, la + 1):
        lo = i - k if i - k > 1 else 1
        hi = i + k if i + k < lb else lb
        cur = [big] * (lb + 1)
        if lo == 1:
            cur[0] = i
        ca = a[i - 1]
        rowmin = big
        for j in range(lo, hi + 1):
            v = prev[j - 1] if ca == b[j - 1] else prev[j - 1] + 1
            d = prev[j] + 1
            if d < v:
                v = d
            d = cur[j - 1] + 1
            if d < v:
                v = d
            cur[j] = v
            if v < rowmin:
                rowmin = v
        if rowmin > k:
            return big
        prev = cur
    d = prev[lb]
    return d if d <= k else big


def load_references(facs_zip: str, spr_csv: str, verbose: bool = True):
    """Every measured CDRH3 the organisers gave us, as IMGT 13-mers.

    Returns (list of unique cdrh3, meta) where meta maps cdrh3 -> dict with the
    FACS binding class, the number of rows carrying it, the best measured KD in
    nM if the SPR table has one, and the core edit distance from wild type.
    """
    meta: dict[str, dict] = {}
    dropped = Counter()

    def add(cdrh3, source, binding_class=None, kd=None, core_ed=None, core=None):
        m = meta.get(cdrh3)
        if m is None:
            m = meta[cdrh3] = {
                "cdrh3": cdrh3,
                "core": core,
                "class": binding_class,
                "kd_nM": kd,
                "core_edit_distance": core_ed,
                "rows": 0,
                "sources": set(),
            }
        m["rows"] += 1
        m["sources"].add(source)
        if binding_class and not m["class"]:
            m["class"] = binding_class
        if core_ed is not None and m["core_edit_distance"] is None:
            m["core_edit_distance"] = core_ed
        if kd is not None and (m["kd_nM"] is None or kd < m["kd_nM"]):
            m["kd_nM"] = kd

    t0 = time.time()
    zf = zipfile.ZipFile(facs_zip)
    inner = next(
        n for n in zf.namelist()
        if n.endswith(".csv") and not n.startswith("__MACOSX")
    )
    with zf.open(inner) as fh:
        for row in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8")):
            cdrh3 = extract_cdrh3(row["vh_sequence"])
            if cdrh3 is None:
                dropped["facs_no_motif"] += 1
                continue
            try:
                core_ed = int(row["edit_distance"])
            except (KeyError, TypeError, ValueError):
                core_ed = None
            add(cdrh3, "facs", row.get("binding_class"), None, core_ed, row.get("cdrh3"))
    if verbose:
        print(f"  FACS   {sum(m['rows'] for m in meta.values()):>7,} rows "
              f"-> {len(meta):>7,} unique CDRH3  ({time.time() - t0:.1f}s)", file=sys.stderr)

    before = len(meta)
    with open(spr_csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            cdrh3 = extract_cdrh3(row["vh_sequence"])
            if cdrh3 is None:
                dropped["spr_no_motif"] += 1
                continue
            kd = None
            if row.get("kd_nM"):
                try:
                    kd = float(row["kd_nM"])
                except ValueError:
                    kd = None
            add(cdrh3, "spr", None, kd, None, row.get("cdrh3"))
    if verbose:
        print(f"  SPR        768 rows -> {len(meta) - before:>7,} new unique CDRH3",
              file=sys.stderr)
        if dropped:
            print(f"  dropped (no C...WGxG motif): {dict(dropped)}", file=sys.stderr)

    for m in meta.values():
        m["sources"] = sorted(m["sources"])
    return list(meta), meta


def nearest(query: str, refs: list[str], cutoff: int):
    """(distance, [reference cdrh3 at that distance]) -- distance is cutoff+1 if beyond."""
    best = cutoff + 1
    hits: list[str] = []
    for ref in refs:
        d = lev_cutoff(query, ref, best if best <= cutoff else cutoff)
        if d < best:
            best = d
            hits = [ref]
            if best == 0:
                break
        elif d == best and d <= cutoff:
            hits.append(ref)
    return best, hits


def load_designs(path: str):
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            heavy = row.get("heavy_sequence", "")
            cdrh3 = extract_cdrh3(heavy)
            out.append({
                "sequence_id": row.get("sequence_id"),
                "kind": row.get("kind"),
                "cdrh3": cdrh3,
                "heavy_len": len(heavy),
                "light_len": len(row.get("light_sequence") or ""),
            })
    return out


def load_refold(path: str):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            def num(key):
                try:
                    return float(row[key])
                except (KeyError, TypeError, ValueError):
                    return None
            out[row["query_id"]] = {
                "iptm": num("iptm"),
                "ptm": num("ptm"),
                "min_ipae": num("min_ipae"),
                "binder_plddt": num("binder_plddt"),
                "plddt": num("plddt"),
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--designs", default=DESIGNS)
    ap.add_argument("--refold", default=REFOLD)
    ap.add_argument("--facs", default=FACS_ZIP)
    ap.add_argument("--spr", default=SPR_CSV)
    ap.add_argument("--cutoff", type=int, default=5,
                    help="exact distances up to this value (default 5)")
    ap.add_argument("--out", default=os.path.join(REPO, "reports/b1_novelty_distance.json"))
    ap.add_argument("--csv", default=os.path.join(REPO, "reports/b1_novelty_distance.csv"))
    args = ap.parse_args()

    print("Loading measured references", file=sys.stderr)
    refs, meta = load_references(args.facs, args.spr)

    designs = load_designs(args.designs)
    refold = load_refold(args.refold)
    print(f"Scanning {len(designs)} designs x {len(refs):,} references, "
          f"cutoff {args.cutoff}", file=sys.stderr)

    results = []
    t0 = time.time()
    for n, d in enumerate(designs, 1):
        q = d["cdrh3"]
        if not q:
            d.update(verdict="error", reason="no C...WGxG motif in heavy_sequence")
            results.append(d)
            continue
        t1 = time.time()
        d_wt = lev_cutoff(q, TRASTUZUMAB_CDRH3, 13)
        dist, hits = nearest(q, refs, args.cutoff)
        beyond = dist > args.cutoff
        hit_meta = [
            {k: v for k, v in meta[h].items() if k != "sources"}
            for h in sorted(hits, key=lambda h: (meta[h]["kd_nM"] is None,
                                                 meta[h]["kd_nM"] or 0))[:5]
        ]
        novelty_ok = beyond or dist >= MUTATIONS_REQUIRED
        wt_ok = d_wt >= MUTATIONS_REQUIRED
        d.update(
            distance_to_trastuzumab=d_wt,
            distance_to_nearest_measured=None if beyond else dist,
            distance_display=f">{args.cutoff}" if beyond else str(dist),
            n_at_that_distance=None if beyond else len(hits),
            nearest=hit_meta,
            eligible=bool(novelty_ok and wt_ok),
            verdict="pass" if (novelty_ok and wt_ok) else "reject",
            reason=None,
            refold=refold.get(d["sequence_id"], {}),
        )
        if d["verdict"] == "reject":
            if d_wt < MUTATIONS_REQUIRED:
                d["reason"] = (f"{d_wt} edit(s) from trastuzumab, needs "
                               f"{MUTATIONS_REQUIRED}")
            else:
                near = hit_meta[0] if hit_meta else {}
                d["reason"] = (
                    f"{dist} edit(s) from {near.get('cdrh3')} "
                    f"(measured {near.get('class') or 'n/a'}"
                    + (f", KD {near['kd_nM']:.3g} nM" if near.get("kd_nM") else "")
                    + f"), needs {MUTATIONS_REQUIRED}"
                )
        results.append(d)
        print(f"  [{n:>2}/{len(designs)}] {d['sequence_id']:<16} {q}  "
              f"wt={d_wt}  nearest={d['distance_display']}  {d['verdict']}"
              f"  ({time.time() - t1:.1f}s)", file=sys.stderr)

    npass = sum(1 for r in results if r.get("verdict") == "pass")
    print(f"\n{npass} of {len(results)} pass the local novelty pre-check "
          f"({time.time() - t0:.0f}s)", file=sys.stderr)

    # --- context tables the status report draws on -------------------------
    landscape = defaultdict(Counter)
    for m in meta.values():
        if m["core_edit_distance"] and m["class"]:
            landscape[m["core_edit_distance"]][m["class"]] += 1
    affinity = sorted(
        ({"cdrh3": m["cdrh3"], "core": m["core"], "kd_nM": m["kd_nM"],
          "core_edit_distance": m["core_edit_distance"]}
         for m in meta.values() if m["kd_nM"] is not None),
        key=lambda r: r["kd_nM"],
    )
    # Which loop positions did the generator actually move?
    loops = [d["cdrh3"] for d in results if d.get("cdrh3")
             and len(d["cdrh3"]) == len(TRASTUZUMAB_CDRH3)]
    positions = [
        {"position": i + 1, "wild_type": wt,
         "kept": sum(1 for loop in loops if loop[i] == wt), "of": len(loops),
         "letters": Counter(loop[i] for loop in loops).most_common()}
        for i, wt in enumerate(TRASTUZUMAB_CDRH3)
    ]

    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "inputs": {"designs": os.path.relpath(args.designs, REPO),
                   "facs": os.path.relpath(args.facs, REPO),
                   "spr": os.path.relpath(args.spr, REPO),
                   "refold": os.path.relpath(args.refold, REPO)},
        "method": {
            "metric": "Levenshtein distance on IMGT CDRH3",
            "cutoff": args.cutoff,
            "mutations_required": MUTATIONS_REQUIRED,
            "trastuzumab_cdrh3": TRASTUZUMAB_CDRH3,
            "references_unique": len(refs),
            "note": ("reference CDRH3s re-extracted from vh_sequence, not read "
                     "from the cdrh3 column, which holds the 10-mer core"),
        },
        "summary": {"designs": len(results), "pass": npass,
                    "reject": len(results) - npass},
        "designs": results,
        "landscape": {str(k): dict(v) for k, v in sorted(landscape.items())},
        "affinity": affinity,
        "loop_positions": positions,
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, sort_keys=False, default=str)
    print(f"wrote {os.path.relpath(args.out, REPO)}", file=sys.stderr)

    with open(args.csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["sequence_id", "cdrh3", "distance_to_trastuzumab",
                    "distance_to_nearest_measured", "n_at_that_distance",
                    "nearest_cdrh3", "nearest_class", "nearest_kd_nM",
                    "iptm", "min_ipae", "binder_plddt", "verdict", "reason"])
        for r in results:
            near = (r.get("nearest") or [{}])[0]
            ref = r.get("refold") or {}
            w.writerow([r.get("sequence_id"), r.get("cdrh3"),
                        r.get("distance_to_trastuzumab"), r.get("distance_display"),
                        r.get("n_at_that_distance"), near.get("cdrh3"),
                        near.get("class"), near.get("kd_nM"),
                        ref.get("iptm"), ref.get("min_ipae"), ref.get("binder_plddt"),
                        r.get("verdict"), r.get("reason")])
    print(f"wrote {os.path.relpath(args.csv, REPO)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
