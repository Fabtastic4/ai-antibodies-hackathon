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
    "predicted_ddg": "axis 3 (thermostability) - NO hosted thermostability predictor exists; "
                     "stab-ddg is BINDING ddG. Whatever fills this column is a proxy and must "
                     "name itself in thermostability_basis. Not yet run",
}

TZ_LIGHT = ("DIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPKLLIYSASFLYSGVPSRFSGSRSG"
            "TDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVEIK")


def read_csv(path):
    if not path or not os.path.exists(path):
        return []
    with open(path) as fh:
        return list(csv.DictReader(fh))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paratope", action="append", default=None,
                    help="per-batch paratope table; repeatable, batches are pooled")
    ap.add_argument("--refold", default="reports/batch1-refold.csv")
    ap.add_argument("--ddg", default="reports/batch1-ddg.csv")
    # Developability tables are keyed on sequence_id, not design_id, and live in their own
    # files. Without these the netsolp/liability columns silently fell through to 'n/a' even
    # though reports/*-solubility.csv held a score for every design. Repeatable, like --paratope.
    ap.add_argument("--solubility", action="append", default=None)
    ap.add_argument("--liability", action="append", default=None)
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

    refold = {r.get("design_id"): r for r in read_csv(a.refold)}
    ddg = {r.get("design_id"): r for r in read_csv(a.ddg)}

    # sequence_id in the developability tables == design_id in the paratope table.
    solub = {}
    for t in (a.solubility or []):
        for r in read_csv(t):
            solub[r.get("sequence_id")] = r
    liab = {}
    for t in (a.liability or []):
        for r in read_csv(t):
            liab[r.get("sequence_id")] = r
    if solub:
        print(f"candidates with a solubility score: {len(solub)}")

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

    have = {"contacts_kept": True, "min_ipae": bool(refold), "predicted_ddg": bool(ddg)}
    missing = [k for k, v in have.items() if not v]

    print(f"candidates with a paratope score : {len(para)}")
    print(f"candidates with a refold score   : {len(refold)}")
    print(f"candidates with a ddG score      : {len(ddg)}")
    print(f"slots                            : {a.slots}")

    if missing and not a.allow_partial:
        print("\nREFUSING to write a submission. Missing required evidence:")
        for m in missing:
            print(f"  - {m:<16} {REQUIRED[m]}")
        print("\nTwo of the three judged axes would be empty, so a rank order here would be")
        print("the paratope proxy wearing a scores table's clothes. Run stage 5 (refold),")
        print("or pass --allow-partial to emit with 'n/a' in every unmeasured column.")
        return 3

    # Rank: contacts preserved first (axis 2), then interface error, then mutation count.
    def key(r):
        ipae = refold.get(r["design_id"], {}).get("min_ipae")
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
            rf = refold.get(r["design_id"], {})
            dg = ddg.get(r["design_id"], {})
            sb = solub.get(r["design_id"], {})
            lb = liab.get(r["design_id"], {})
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
                "netsolp_solubility_min": sb.get("netsolp_solubility_min",
                                                 r.get("netsolp_solubility_min", "n/a")),
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
                "liability_flags": lb.get("liability_flags",
                                          sb.get("solubility_flag",
                                                 r.get("liability_flags", "n/a"))),
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
