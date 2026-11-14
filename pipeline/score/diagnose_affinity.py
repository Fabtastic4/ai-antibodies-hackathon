#!/usr/bin/env python3
"""Why does the FACS-trained ranker not transfer to SPR? Test four hypotheses.

H1  Range restriction. The SPR set is the subset of designs with *measurable* affinity,
    so it is conditioned on the outcome. Correlation inside a pre-selected band of good
    binders is structurally weaker than across the full range.
H2  Data ceiling. FACS class itself may not track SPR KD in the >=3 band. If the label
    we train on does not correlate with the label we are judged on, no model on this
    data can work, and the fix is not a better model.
H3  Saturation. The model may predict one class for nearly everything in the >=3 band,
    so there is no spread left to correlate.
H4  Coverage. The >=3 SPR variants may be far from anything in the training library,
    making every prediction an extrapolation.

Run:  diagnose_affinity.py --data ~/hackathon-data/her2-trastuzumab
"""

from __future__ import annotations

import argparse
import pathlib
import zipfile

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

TRAS = "WGGDGFYAMD"


def nmut(s: str) -> int:
    return sum(1 for a, b in zip(s, TRAS) if a != b) + abs(len(s) - len(TRAS))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=pathlib.Path)
    a = ap.parse_args()

    zp = next(a.data.glob("tz_her2_facs_*classes_*.csv.zip"))
    with zipfile.ZipFile(zp) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv") and "MACOSX" not in n)
        with z.open(name) as fh:
            facs = pd.read_csv(fh, usecols=["cdrh3", "binding_class", "edit_distance"])

    spr = pd.read_csv(next(a.data.glob("trastuzumab_her2_spr_all_*.csv")))
    spr["n_mut"] = spr["cdrh3"].map(nmut)

    print("=" * 78)
    print("WHAT IS ACTUALLY IN THE SPR TABLE")
    print("=" * 78)
    print(f"total rows: {len(spr)}")
    print("\nbinding_result:")
    print(spr["binding_result"].value_counts().to_string())
    print(f"\nrows with a usable kd_nM: {spr['kd_nM'].notna().sum()}")

    # ---- H1: range restriction -------------------------------------------------
    print("\n" + "=" * 78)
    print("H1  RANGE RESTRICTION — is the measured set conditioned on binding?")
    print("=" * 78)
    meas = spr[spr["kd_nM"].notna() & (spr["kd_nM"] > 0)].copy()
    meas["logkd"] = np.log10(meas["kd_nM"])
    print(f"measurable: {len(meas)} of {len(spr)} rows "
          f"({len(meas)/len(spr):.0%}) — the rest have no reportable KD")
    for lo, hi, label in ((0, 2, "< 3 mutations"), (3, 99, ">= 3 mutations")):
        s = meas[(meas["n_mut"] >= lo) & (meas["n_mut"] <= hi)]
        if len(s) < 3:
            continue
        print(f"\n  {label}: n={len(s)}")
        print(f"    KD nM   min={s['kd_nM'].min():.3g}  median={s['kd_nM'].median():.3g}  "
              f"max={s['kd_nM'].max():.3g}")
        print(f"    log10KD spread (SD) = {s['logkd'].std():.3f}   range = {s['logkd'].max()-s['logkd'].min():.2f} logs")
    # Fraction of the FULL design set that even got measured, by mutation count:
    print("\n  measurement rate by mutation count (selection pressure):")
    for n in sorted(spr["n_mut"].unique()):
        sub = spr[spr["n_mut"] == n]
        if len(sub) < 5:
            continue
        rate = sub["kd_nM"].notna().mean()
        print(f"    {n:2d} mut: {len(sub):4d} designs, {rate:5.1%} measurable")

    # ---- H2: data ceiling ------------------------------------------------------
    print("\n" + "=" * 78)
    print("H2  DATA CEILING — does the FACS label itself track SPR KD?")
    print("=" * 78)
    j = meas.merge(facs[["cdrh3", "binding_class", "edit_distance"]].drop_duplicates("cdrh3"),
                   on="cdrh3", how="inner")
    print(f"SPR variants also present in the FACS library: {len(j)} of {len(meas)}")
    if len(j) >= 10:
        order = {"low": 0, "medium": 1, "high": 2}
        j["class_ord"] = j["binding_class"].map(order)
        for lo, hi, label in ((0, 99, "all overlapping"), (3, 99, ">= 3 mutations")):
            s = j[(j["n_mut"] >= lo) & (j["n_mut"] <= hi)]
            if len(s) < 10 or s["class_ord"].nunique() < 2:
                print(f"  {label}: n={len(s)} — too few or single-class")
                continue
            rho, p = spearmanr(s["class_ord"], -s["logkd"])
            print(f"  {label}: n={len(s)}  rho(FACS class, -log KD) = {rho:+.3f}  p={p:.2e}")
            print("    median KD per FACS class:")
            for c in ("low", "medium", "high"):
                t = s[s["binding_class"] == c]
                if len(t):
                    print(f"      {c:7s} n={len(t):4d}  median KD = {t['kd_nM'].median():.3g} nM")
        print("\n  ^ THIS IS THE CEILING. A model trained on FACS cannot beat the")
        print("    correlation between the FACS label and SPR KD. If it is near zero")
        print("    in the >= 3 band, the training signal does not exist there.")
    else:
        print("  Not enough overlap to measure the ceiling directly.")

    # ---- H4: coverage ----------------------------------------------------------
    print("\n" + "=" * 78)
    print("H4  COVERAGE — mutation profile, training library vs SPR set")
    print("=" * 78)
    print("  FACS library edit_distance distribution:")
    print("   ", facs["edit_distance"].value_counts().sort_index().to_dict())
    print("  SPR measured n_mut distribution:")
    print("   ", meas["n_mut"].value_counts().sort_index().to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
