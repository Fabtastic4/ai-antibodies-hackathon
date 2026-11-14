#!/usr/bin/env python3
"""Rank CDRH3 designs by predicted HER2 affinity, learned from measured data.

Why this exists. The structural confidence scores cannot order a submission: on the
organisers' own 91x91 labelled matrices, ipTM at 0.7 admits 94.3% of measured
non-binders for Boltz-2, and the best model (AF3) reaches only AUC 0.754. So we rank
on something that was actually measured.

    train    -> 524,346 CDRH3 variants, FACS binding classes      (Chinery et al.)
    validate -> 768 variants with measured SPR KD, held out       (same study)

The validation is cross-modality on purpose: train on the cheap noisy screen, test on
the expensive assay we are judged by. If Spearman rho on the SPR set is near zero, this
model does not belong in the ranking and we say so -- that is a result, not a failure.

Two honest constraints, enforced in code rather than noted in prose:

1. Metrics are reported BOTH on the whole test split and on the >= 3-mutation band.
   abguard requires a trastuzumab variant to differ from trastuzumab and from every
   known CDRH3 by at least 3 mutations, so the >= 3 band is the only region we may
   actually submit from. The full split is dominated by low-mutation variants that are
   easy to call and ineligible, and it flatters the model. Lead with the restricted
   number.
2. Any design whose CDRH3 falls outside the training library's length is refused rather
   than silently scored.

Usage:
    affinity_model.py --data ~/hackathon-data/her2-trastuzumab --out reports/
    affinity_model.py --data ... --score designs/raw/b1-novel-s1.csv -o scored.csv
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import zipfile

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, roc_auc_score
from sklearn.model_selection import train_test_split

AA = "ACDEFGHIKLMNPQRSTVWY"
AA_IDX = {a: i for i, a in enumerate(AA)}
TRASTUZUMAB_CDRH3 = "WGGDGFYAMD"
ELIGIBLE_MIN_MUTATIONS = 3  # abguard's threshold for a trastuzumab variant


def onehot(seqs: pd.Series, length: int) -> np.ndarray:
    """One-hot encode fixed-length CDRH3s. Position-specific, which is the point:
    a mutation's effect depends on where it sits in the loop."""
    x = np.zeros((len(seqs), length * len(AA)), dtype=np.float32)
    for row, s in enumerate(seqs):
        for pos, ch in enumerate(s[:length]):
            j = AA_IDX.get(ch)
            if j is not None:
                x[row, pos * len(AA) + j] = 1.0
    return x


def load_facs(folder: pathlib.Path) -> pd.DataFrame:
    zp = next(folder.glob("tz_her2_facs_*classes_*.csv.zip"))
    with zipfile.ZipFile(zp) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv") and "MACOSX" not in n)
        with z.open(name) as fh:
            df = pd.read_csv(fh, usecols=["cdrh3", "binding_class", "edit_distance"])
    return df.dropna(subset=["cdrh3", "binding_class"])


def load_spr(folder: pathlib.Path) -> pd.DataFrame:
    df = pd.read_csv(next(folder.glob("trastuzumab_her2_spr_all_*.csv")))
    df = df.dropna(subset=["cdrh3", "kd_nM"])
    df = df[df["kd_nM"] > 0]
    # Tighter binding = lower KD. Use -log10(KD) so that bigger is better, matching
    # the direction of the model's score.
    df["neg_log_kd"] = -np.log10(df["kd_nM"].astype(float))
    return df


def mutations_from_wt(seqs: pd.Series) -> pd.Series:
    wt = TRASTUZUMAB_CDRH3
    return seqs.map(lambda s: sum(1 for a, b in zip(s, wt) if a != b) + abs(len(s) - len(wt)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=pathlib.Path,
                    help="folder holding the two her2-trastuzumab tables")
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("reports"))
    ap.add_argument("--score", type=pathlib.Path,
                    help="a design table with a 'sequence' column (full VH) to score")
    ap.add_argument("-o", "--scored-out", type=pathlib.Path)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    facs = load_facs(args.data)
    length = int(facs["cdrh3"].str.len().mode()[0])
    facs = facs[facs["cdrh3"].str.len() == length]
    # Order matters and alphabetical order is wrong: sorted() gives high < low < medium,
    # which would make the expected-class score meaningless. The classes are ordinal, so
    # pin the order explicitly, weakest first.
    CANONICAL = ["low", "medium", "high"]
    present = set(facs["binding_class"].unique())
    classes = [c for c in CANONICAL if c in present]
    unknown = present - set(CANONICAL)
    if unknown:
        raise SystemExit(f"unrecognised binding_class values {unknown}; "
                         f"add them to CANONICAL in the correct ordinal position")
    print(f"FACS      {len(facs):,} variants, CDRH3 length {length}, classes {classes}")
    print(f"          class counts: {facs['binding_class'].value_counts().to_dict()}")
    print(f"          edit_distance >= {ELIGIBLE_MIN_MUTATIONS}: "
          f"{(facs['edit_distance'] >= ELIGIBLE_MIN_MUTATIONS).mean():.1%} of the library")

    # Ordinal encoding: the three classes are ordered, so rank on an expected class
    # value rather than treating them as unrelated labels.
    order = {c: i for i, c in enumerate(classes)}
    y = facs["binding_class"].map(order).to_numpy()
    x = onehot(facs["cdrh3"], length)

    x_tr, x_te, y_tr, y_te, ed_tr, ed_te = train_test_split(
        x, y, facs["edit_distance"].to_numpy(), test_size=0.2,
        random_state=args.seed, stratify=y)

    model = LogisticRegression(max_iter=2000, C=1.0)  # multinomial is the default in sklearn >=1.5
    model.fit(x_tr, y_tr)

    def expected_class(xx: np.ndarray) -> np.ndarray:
        p = model.predict_proba(xx)
        return p @ np.arange(p.shape[1])

    report: dict = {"classes": classes, "cdrh3_length": length,
                    "n_train": int(len(y_tr)), "n_test": int(len(y_te))}

    print("\n-- held-out FACS test split --")
    for label, mask in (("all", np.ones(len(y_te), dtype=bool)),
                        (f">= {ELIGIBLE_MIN_MUTATIONS} mutations (submittable band)",
                         ed_te >= ELIGIBLE_MIN_MUTATIONS)):
        if mask.sum() < 20:
            print(f"   {label}: too few rows ({mask.sum()})")
            continue
        acc = model.score(x_te[mask], y_te[mask])
        # One-vs-rest AUC for the top class: "is this a strong binder?"
        top = (y_te[mask] == len(classes) - 1).astype(int)
        auc = (roc_auc_score(top, expected_class(x_te[mask]))
               if 0 < top.sum() < len(top) else float("nan"))
        print(f"   {label}: n={mask.sum():,}  accuracy={acc:.3f}  AUC(top class)={auc:.3f}")
        report[f"facs_{'all' if label == 'all' else 'eligible_band'}"] = {
            "n": int(mask.sum()), "accuracy": round(float(acc), 4),
            "auc_top_class": None if np.isnan(auc) else round(float(auc), 4)}

    cm = confusion_matrix(y_te, model.predict(x_te))
    print(f"   confusion matrix (rows=true {classes}):\n{cm}")
    report["confusion_matrix"] = cm.tolist()

    # ---- the headline: cross-modality validation on measured SPR ----
    spr = load_spr(args.data)
    spr = spr[spr["cdrh3"].str.len() == length].copy()
    spr["pred"] = expected_class(onehot(spr["cdrh3"], length))
    spr["n_mut"] = mutations_from_wt(spr["cdrh3"])

    print(f"\n-- cross-modality validation: {len(spr)} measured SPR affinities --")
    for label, sub in (("all measured", spr),
                       (f">= {ELIGIBLE_MIN_MUTATIONS} mutations",
                        spr[spr["n_mut"] >= ELIGIBLE_MIN_MUTATIONS])):
        if len(sub) < 10:
            print(f"   {label}: too few rows ({len(sub)})")
            continue
        rho, p = spearmanr(sub["pred"], sub["neg_log_kd"])
        print(f"   {label}: n={len(sub)}  Spearman rho={rho:+.3f}  p={p:.2e}")
        report[f"spr_{'all' if label == 'all measured' else 'eligible_band'}"] = {
            "n": int(len(sub)), "spearman_rho": round(float(rho), 4), "p_value": float(p)}

    verdict = report.get("spr_eligible_band", report.get("spr_all", {}))
    rho = verdict.get("spearman_rho", 0.0)
    report["verdict"] = (
        "USE as primary ranker" if rho >= 0.3 else
        "USE as tie-breaker only" if rho >= 0.15 else
        "DO NOT RANK ON THIS -- report the negative result and fall back to the structural triple")
    print(f"\nVERDICT: {report['verdict']}  (rho={rho:+.3f})")

    (args.out / "affinity_model_report.json").write_text(json.dumps(report, indent=2))
    print(f"wrote {args.out / 'affinity_model_report.json'}")

    if args.score:
        d = pd.read_csv(args.score)
        if "sequence" not in d.columns:
            print("--score table has no 'sequence' column", file=sys.stderr)
            return 2
        # The designed CDRH3 sits between the framework motif 'YYC' and 'WGQG'.
        def extract(vh: str) -> str | None:
            i, j = vh.find("YYC"), vh.find("WGQG")
            if i < 0 or j < 0 or j <= i:
                return None
            loop = vh[i + 3:j]
            return loop[2:-1] if len(loop) == length + 3 else (loop if len(loop) == length else None)
        d["cdrh3_10"] = d["sequence"].map(extract)
        ok = d["cdrh3_10"].notna()
        d.loc[ok, "affinity_score"] = expected_class(onehot(d.loc[ok, "cdrh3_10"], length))
        d.loc[~ok, "affinity_note"] = "CDRH3 not extractable at training length - scored structurally only"
        out = args.scored_out or args.score.with_suffix(".scored.csv")
        d.to_csv(out, index=False)
        print(f"scored {int(ok.sum())}/{len(d)} designs -> {out}")
        if (~ok).any():
            print(f"   {int((~ok).sum())} refused (out of distribution), flagged not silently scored")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
