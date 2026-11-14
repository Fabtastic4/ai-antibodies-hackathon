#!/usr/bin/env python3
"""
Freeze trained weights into a versioned, self-contained release bundle.

The raw training checkpoints (models/facs/..., models/spr/...) only store state
dicts. Rebuilding the model from them relies on the *default* constructor
arguments in pipeline/affinity_model.py -- so editing those defaults later
silently breaks loading. This script writes a bundle that carries the
architecture config, the feature spec and the metrics alongside the weights,
plus a manifest with SHA-256 checksums so the weights can be verified.

Usage:
    python scripts/export_release_affinity_v2.py                  # -> models/release/v1
    python scripts/export_release_affinity_v2.py --version v2
    python scripts/export_release_affinity_v2.py --verify-only models/release/v1
"""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.score.affinity_v2.affinity_model import (  # noqa: E402
    AA_ALPHABET,
    AA_TO_IDX,
    VOCAB_SIZE,
    FACSClassifier,
    SPRRegressor,
    SequenceEncoder,
    compute_features,
    seq_to_indices,
)

# Architecture + preprocessing contract used by the 2026-11-14 training run.
# These mirror the defaults that were in effect during training; recording them
# explicitly is the whole point of the bundle.
ENCODER_CONFIG = {
    "vocab_size": VOCAB_SIZE,
    "embed_dim": 64,
    "num_heads": 4,
    "num_layers": 2,
    "hidden_dim": 128,
}
PREPROCESSING = {
    "max_len": 15,
    "reference_seq": "WGGDGFYAMD",
    "alphabet": AA_ALPHABET,
    "unknown_token": "X",
    "unknown_idx": AA_TO_IDX["X"],
    "feature_dim": 31,
    "target": "log10(kd_nM)",
}
FACS_CLASSES = ["low", "medium", "high"]  # index order = label_map in training


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_bundle(facs_ckpt: Path, spr_ckpt: Path) -> dict:
    facs = torch.load(facs_ckpt, map_location="cpu", weights_only=False)
    spr = torch.load(spr_ckpt, map_location="cpu", weights_only=False)

    feature_dim = int(spr.get("feature_dim", PREPROCESSING["feature_dim"]))
    if feature_dim != PREPROCESSING["feature_dim"]:
        raise SystemExit(
            f"feature_dim mismatch: checkpoint says {feature_dim}, "
            f"spec says {PREPROCESSING['feature_dim']}"
        )

    return {
        "format_version": 1,
        "encoder_config": ENCODER_CONFIG,
        "preprocessing": PREPROCESSING,
        "facs": {
            "state_dict": facs["model"],
            "classes": FACS_CLASSES,
            "metrics": {"val_accuracy": float(facs["accuracy"])},
            "epoch": int(facs["epoch"]),
        },
        "spr": {
            "state_dict": spr["model"],
            "feature_dim": feature_dim,
            # Target/feature standardisation fitted on the TRAIN split. The regressor
            # emits standardised units, so inference MUST feed (x - feat_mean)/feat_std
            # and rescale the output by y_std and y_mean. Older checkpoints predate
            # this and get identity scalers.
            "scalers": {
                "y_mean": float(spr.get("y_mean", 0.0)),
                "y_std": float(spr.get("y_std", 1.0)),
                "feat_mean": list(spr.get("feat_mean", [0.0] * feature_dim)),
                "feat_std": list(spr.get("feat_std", [1.0] * feature_dim)),
                "fitted": "y_mean" in spr,
            },
            "metrics": {"val_r2": float(spr["r2"]), "val_mae": float(spr["mae"])},
            "epoch": int(spr["epoch"]),
            "split_seed": spr.get("split_seed"),
            "split_fractions": spr.get("split_fractions"),
        },
        "provenance": {
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "torch_version": torch.__version__,
            "source_checkpoints": {
                "facs": str(facs_ckpt.relative_to(REPO)),
                "spr": str(spr_ckpt.relative_to(REPO)),
            },
            "training_data": {
                "facs": "data/bucket/extracted/hackathon-data/her2-trastuzumab/"
                        "tz_her2_facs_3classes_524346.csv.zip",
                "spr": "data/bucket/extracted/hackathon-data/her2-trastuzumab/"
                       "trastuzumab_her2_spr_all_768.csv",
            },
        },
    }


def smoke_test(bundle: dict) -> dict:
    """Rebuild both models from the bundle alone and run one forward pass."""
    enc_cfg = bundle["encoder_config"]
    pre = bundle["preprocessing"]

    facs = FACSClassifier(SequenceEncoder(**enc_cfg), num_classes=len(bundle["facs"]["classes"]))
    facs.load_state_dict(bundle["facs"]["state_dict"])
    facs.eval()

    spr = SPRRegressor(SequenceEncoder(**enc_cfg), feature_dim=bundle["spr"]["feature_dim"])
    spr.load_state_dict(bundle["spr"]["state_dict"])
    spr.eval()

    seq = pre["reference_seq"]
    x = seq_to_indices(seq, pre["max_len"]).unsqueeze(0)
    feats = torch.tensor(compute_features(seq, pre["reference_seq"]), dtype=torch.float32).unsqueeze(0)

    sc = bundle["spr"].get("scalers", {})
    fm = torch.tensor(sc.get("feat_mean", [0.0] * bundle["spr"]["feature_dim"]), dtype=torch.float32)
    fs = torch.tensor(sc.get("feat_std", [1.0] * bundle["spr"]["feature_dim"]), dtype=torch.float32)

    with torch.inference_mode():
        probs = torch.softmax(facs(x), dim=1)[0]
        raw = spr(x, (feats - fm) / fs).reshape(-1)[0].item()
        log_kd = raw * sc.get("y_std", 1.0) + sc.get("y_mean", 0.0)

    return {
        "sequence": seq,
        "facs_probs": {c: round(float(p), 4) for c, p in zip(bundle["facs"]["classes"], probs)},
        "pred_log_kd": round(log_kd, 4),
        "pred_kd_nM": round(10 ** log_kd, 4),
    }


def verify(release_dir: Path) -> int:
    manifest_path = release_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"FAIL  no manifest at {manifest_path}")
        return 1
    manifest = json.loads(manifest_path.read_text())
    ok = True
    for name, meta in manifest["files"].items():
        p = release_dir / name
        if not p.exists():
            print(f"FAIL  missing {name}")
            ok = False
            continue
        actual = sha256(p)
        if actual != meta["sha256"]:
            print(f"FAIL  checksum mismatch {name}\n      expected {meta['sha256']}\n      actual   {actual}")
            ok = False
        else:
            print(f"ok    {name}  ({meta['bytes']:,} bytes, sha256 {actual[:16]}...)")

    bundle_path = release_dir / "affinity_bundle.pt"
    if bundle_path.exists():
        result = smoke_test(torch.load(bundle_path, map_location="cpu", weights_only=False))
        print(f"ok    bundle rebuilds and runs: {result}")
    print("\nVERIFIED" if ok else "\nVERIFICATION FAILED")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", default="v1", help="release name (default: v1)")
    ap.add_argument("--facs-ckpt", default="models/facs/facs_classifier_best.pt")
    ap.add_argument("--spr-ckpt", default="models/spr/spr_regressor_best.pt")
    ap.add_argument("--out-root", default="models/release")
    ap.add_argument("--force", action="store_true", help="overwrite an existing release dir")
    ap.add_argument("--verify-only", metavar="DIR", help="verify an existing release and exit")
    args = ap.parse_args()

    if args.verify_only:
        return verify(Path(args.verify_only))

    facs_ckpt = (REPO / args.facs_ckpt).resolve()
    spr_ckpt = (REPO / args.spr_ckpt).resolve()
    for p in (facs_ckpt, spr_ckpt):
        if not p.exists():
            raise SystemExit(f"checkpoint not found: {p}")

    out = REPO / args.out_root / args.version
    if out.exists() and not args.force:
        raise SystemExit(f"{out} already exists (use --force to overwrite)")
    out.mkdir(parents=True, exist_ok=True)

    print(f"Building release {args.version} ...")
    bundle = build_bundle(facs_ckpt, spr_ckpt)

    print("  smoke-testing rebuilt models ...")
    smoke = smoke_test(bundle)
    print(f"  {smoke}")

    bundle_path = out / "affinity_bundle.pt"
    torch.save(bundle, bundle_path)
    # Keep byte-identical copies of the originals too, so nothing is lost.
    shutil.copy2(facs_ckpt, out / "facs_classifier.pt")
    shutil.copy2(spr_ckpt, out / "spr_regressor.pt")

    files = {}
    for p in sorted(out.glob("*.pt")):
        files[p.name] = {"sha256": sha256(p), "bytes": p.stat().st_size}

    manifest = {
        "version": args.version,
        "files": files,
        "encoder_config": bundle["encoder_config"],
        "preprocessing": bundle["preprocessing"],
        "facs": {
            "classes": bundle["facs"]["classes"],
            "metrics": bundle["facs"]["metrics"],
            "epoch": bundle["facs"]["epoch"],
        },
        "spr": {
            "metrics": bundle["spr"]["metrics"],
            "epoch": bundle["spr"]["epoch"],
            "feature_dim": bundle["spr"]["feature_dim"],
        },
        "provenance": bundle["provenance"],
        "smoke_test": smoke,
        "caveats": [
            "SPR regressor val R2 is negative (-1.73): its log-KD values are worse "
            "than predicting the dataset mean. Do not use the absolute kd_nM numbers.",
            "FACS classifier val accuracy 0.724 on 3 classes.",
            "Trained on CDRH3 only (max_len 15), HER2/trastuzumab context.",
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"\nWrote release to {out}")
    for name, meta in files.items():
        print(f"  {name:24} {meta['bytes']:>9,} bytes  sha256 {meta['sha256'][:16]}...")
    print(f"  {'manifest.json':24} {(out / 'manifest.json').stat().st_size:>9,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
