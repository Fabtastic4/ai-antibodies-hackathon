#!/usr/bin/env python3
"""Rank designs into designs/submission.csv - and refuse to when the evidence is not there.

The judged axes are (1) SPR binding, (2) epitope preserved, (3) thermostability. Of those,
only (2) has a proxy that runs without hardware. So this script will NOT emit a ranked
submission from the paratope proxy alone: it exits 3 and says what is missing. That is
deliberate. A ranked list implies we measured something we did not.

  rank.py --paratope reports/batch1-paratope.csv --out designs/submission.csv
  rank.py ... --allow-partial     # emit anyway, every missing score written as 'n/a'

Exit 0 = submission written. Exit 3 = refused, required scores missing. Exit 2 = error.
"""
import argparse
import csv
import os
import sys

# Fallback only. The real column order is read from the existing designs/submission.csv
# header so this script never silently reverts a schema a teammate extended.
SUBMISSION_COLS = [
    "design_id", "format", "sequence", "light_sequence", "parent", "mutations", "track",
    "method", "model_version", "seed", "run_id", "plddt", "iptm", "ipsae", "min_ipae",
    "binder_plddt", "predicted_ddg", "epitope_overlap_frac", "thermostability_basis",
    "liability_flags", "netsolp_solubility_min", "cysteine_count", "rank",
    "reason_for_selection",
]

# A score column is "required" if one of the three judged axes rests on it.
REQUIRED = {
    "min_ipae": "axis 1 (binding) - boltz2 co-fold interface error, stage 5 refold",
    "contacts_kept": "axis 2 (epitope) - paratope proxy, stage 2",
    "predicted_ddg": "axis 3 (thermostability) - stab-ddg, not yet run",
}

TZ_LIGHT = ("DIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPKLLIYSASFLYSGVPSRFSGSRSG"
            "TDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVEIK")

# Score tables and candidate tables disagree about identifiers, in two ways, and a
# mismatch here is silent: the join misses, every score reads as absent, and the script
# refuses while the numbers sit on disk. So normalise before joining.
#   column:    paratope tables say design_id, refold tables say query_id
#   namespace: candidates are b1-novel-s1-her2_cdrh3_14, refold rows are her2_cdrh3_14
BATCH_PREFIXES = ("b1-novel-s1-", "b2-explor-s2-fixed-", "batch1-", "batch2-")
ID_COLUMNS = ("design_id", "query_id", "sequence_id", "id")


def design_key(row_or_id):
    """A join key that survives both disagreements above."""
    if isinstance(row_or_id, dict):
        val = ""
        for c in ID_COLUMNS:
            if row_or_id.get(c):
                val = row_or_id[c]
                break
    else:
        val = row_or_id or ""
    for p in BATCH_PREFIXES:
        if val.startswith(p):
            return val[len(p):]
    return val


def score_table(paths):
    """Pool one or more score tables, keyed on the normalised design id."""
    out = {}
    for path in paths or []:
        for r in read_csv(path):
            k = design_key(r)
            if k:
                out[k] = r
    return out


def read_csv(path):
    if not path or not os.path.exists(path):
        return []
    with open(path) as fh:
        return list(csv.DictReader(fh))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paratope", action="append", default=None,
                    help="per-batch paratope table; repeatable, batches are pooled")
    ap.add_argument("--refold", action="append", default=None,
                    help="per-batch refold metrics; repeatable, batches are pooled")
    ap.add_argument("--ddg", action="append", default=None,
                    help="per-batch stab-ddg output; repeatable")
    ap.add_argument("--out", default="designs/submission.csv")
    ap.add_argument("--slots", type=int, default=20)
    ap.add_argument("--seed", default="20261114")
    ap.add_argument("--allow-partial", action="store_true")
    a = ap.parse_args()

    tables = a.paratope or ["reports/b1-novel-s1-paratope.csv"]
    para, seen_seq = [], set()
    for t in tables:
        rows = read_csv(t)
        print(f"  {t}: {len(rows)} designs")
        for r in rows:
            # Pool across batches, deduping on heavy chain: abguard competition-validate
            # rejects sequences shared between teams, so a duplicate in a 20-slot list is
            # pure waste. Batch 1 alone held 6 duplicate pairs.
            h = r.get("heavy_sequence", "")
            if h and h in seen_seq:
                continue
            seen_seq.add(h)
            r["_source"] = os.path.basename(t)
            para.append(r)

    refold = score_table(a.refold or ["reports/b1_refold_metrics.csv",
                                      "reports/b2_refold_metrics.csv"])
    ddg = score_table(a.ddg or ["reports/b1_ddg.csv", "reports/b2_ddg.csv"])

    if not para:
        print(f"no paratope rows from {tables} - run stage 2 first", file=sys.stderr)
        return 2

    cols = SUBMISSION_COLS
    if os.path.exists(a.out):
        with open(a.out) as fh:
            existing = csv.reader(fh)
            hdr = next(existing, None)
        if hdr and "design_id" in hdr:
            cols = hdr
            print(f"  schema: {len(cols)} columns read from existing {a.out}")

    # Count coverage over the candidate pool, not rows in the score table: a score table
    # full of ids that join to nothing is the failure mode this script was blind to.
    n_refold = sum(1 for r in para if design_key(r) in refold)
    n_ddg = sum(1 for r in para if design_key(r) in ddg)

    have = {"contacts_kept": True, "min_ipae": n_refold > 0, "predicted_ddg": n_ddg > 0}
    missing = [k for k, v in have.items() if not v]

    print(f"candidates with a paratope score : {len(para)}")
    print(f"candidates with a refold score   : {n_refold}"
          + (f"  ({len(refold)} rows loaded)" if refold and not n_refold else ""))
    print(f"candidates with a ddG score      : {n_ddg}"
          + (f"  ({len(ddg)} rows loaded)" if ddg and not n_ddg else ""))
    print(f"slots                            : {a.slots}")
    if n_refold and n_refold < a.slots:
        print(f"  NOTE only {n_refold} of {a.slots} slots can carry a measured min_ipae; "
              f"the rest would rank on the paratope proxy alone.")

    if missing and not a.allow_partial:
        print("\nREFUSING to write a submission. Missing required evidence:")
        for m in missing:
            print(f"  - {m:<16} {REQUIRED[m]}")
        n = len(missing)
        print(f"\n{n} of the three judged axes would be empty, so a rank order here would be")
        print("the remaining proxies wearing a scores table's clothes. Fill the axis above,")
        print("or pass --allow-partial to emit with 'n/a' in every unmeasured column.")
        return 3

    # Rank: contacts preserved first (axis 2), then interface error, then mutation count.
    def key(r):
        ipae = refold.get(design_key(r), {}).get("min_ipae")
        try:
            ipae = float(ipae)
        except (TypeError, ValueError):
            ipae = float("inf")
        return (-int(r.get("contacts_kept", 0)), ipae, -int(r.get("cdrh3_mutations", 0)))

    ranked = sorted(para, key=key)[: a.slots]

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore", restval="")
        w.writeheader()
        for i, r in enumerate(ranked, 1):
            rf = refold.get(design_key(r), {})
            dg = ddg.get(design_key(r), {})
            kept = r.get("contacts_kept", "0")
            w.writerow({
                "track": "optimisation",
                "run_id": r.get("_source", ""),
                "min_ipae": rf.get("min_ipae", "n/a"),
                "binder_plddt": rf.get("binder_plddt", "n/a"),
                # Axis 2, stated as what it is: fraction of the 4 measured CDRH3-HER2
                # contacts retained. Not the competitive binding assay.
                "epitope_overlap_frac": f"{int(kept)/4:.2f}",
                "thermostability_basis": dg.get("thermostability_basis", "not yet measured"),
                "netsolp_solubility_min": r.get("netsolp_solubility_min", "n/a"),
                "design_id": r["design_id"],
                "format": "fab",
                "sequence": r.get("heavy_sequence", ""),
                "light_sequence": TZ_LIGHT,
                "parent": "trastuzumab",
                "mutations": r.get("cdrh3_mutations", ""),
                "method": "rfd4-proteina CDRH3 redesign",
                "model_version": "her2-novel-2026-11-09",
                "seed": a.seed,
                "plddt": rf.get("binder_plddt", "n/a"),
                "iptm": rf.get("iptm", "n/a"),
                "ipsae": rf.get("min_ipae", "n/a"),
                "predicted_ddg": dg.get("predicted_ddg", "n/a"),
                "liability_flags": r.get("liability_flags", "n/a"),
                "cysteine_count": r.get("heavy_sequence", "").count("C"),
                "rank": i,
                "reason_for_selection": (
                    f"{r.get('contacts_kept','?')}/4 CDRH3-HER2 contacts preserved "
                    f"({r.get('contacts_kept_pos','?')}); {r.get('cdrh3_mutations','?')} CDRH3 mutations"
                ),
            })
    print(f"\nwrote {a.out} - {len(ranked)} rows")
    if missing:
        print(f"PARTIAL: {', '.join(missing)} written as 'n/a'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
