#!/usr/bin/env python3
"""
Inference engine for the two-stage HER2/trastuzumab affinity model.

Loads a frozen release bundle (see scripts/export_release_affinity_v2.py) once, then scores
CDRH3 sequences in batches on GPU or CPU. Exposes three entry points:

  Python:  from pipeline.score.affinity_v2.inference import AffinityEngine
           eng = AffinityEngine()
           df = eng.predict(["WGGDGFYAMD", "WGNDGFYMLD"])

  CLI:     python pipeline/score/affinity_v2/inference.py predict --input seqs.fasta --output preds.csv
           python pipeline/score/affinity_v2/inference.py predict --input cands.csv --seq-col cdrh3 -o preds.csv
           echo WGGDGFYAMD | python pipeline/score/affinity_v2/inference.py predict --input - -o preds.csv
           python pipeline/score/affinity_v2/inference.py selftest          # metrics on the SPR set

  HTTP:    python pipeline/score/affinity_v2/inference.py serve --port 8008
           curl -s localhost:8008/predict -H 'content-type: application/json' \
                -d '{"sequences":["WGGDGFYAMD"]}'

IMPORTANT -- model quality: the FACS head (3-class binder strength) is usable
(test accuracy 0.719, balanced 0.720). The SPR head, after train-split-only
standardisation of its target and features, reaches test R2 0.399 and Spearman
rho 0.752 on a held-out 20% split -- useful for RANKING designs, but its absolute
KD numbers carry ~0.7 log10 units of error, and R2 on 38 test points varies by
~0.1 between runs. Rank by pred_kd_nM; do not quote the nM value as a measurement.
Caveats are derived from the loaded bundle's own metrics at runtime.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
import torch

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from pipeline.score.affinity_v2.affinity_model import (  # noqa: E402
    AA_ALPHABET,
    FACSClassifier,
    SPRRegressor,
    SequenceEncoder,
    compute_features,
    seq_to_indices,
)

DEFAULT_BUNDLE = REPO / "models" / "release" / "v2" / "affinity_bundle.pt"
LEGACY_FACS = REPO / "models" / "facs" / "facs_classifier_best.pt"
LEGACY_SPR = REPO / "models" / "spr" / "spr_regressor_best.pt"

# log10(nM) clamp for the reported linear KD, so a wild extrapolation cannot
# turn into inf/0 in a CSV. 1e-4 nM .. 1e9 nM brackets anything physical.
LOG_KD_CLAMP = (-4.0, 9.0)

VALID_AA = set(AA_ALPHABET)


@dataclass
class EngineInfo:
    bundle: str
    device: str
    encoder_config: dict
    preprocessing: dict
    facs_classes: list
    facs_metrics: dict
    spr_metrics: dict
    caveats: list = field(default_factory=list)


class AffinityEngine:
    """Loads the models once; scores many sequences."""

    def __init__(
        self,
        bundle_path: str | Path | None = None,
        device: str | None = None,
        allow_legacy: bool = True,
    ):
        self.device = torch.device(
            device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        )
        # Guards the forward pass: one CUDA model shared by all HTTP threads.
        self._lock = threading.Lock()

        bundle_path = Path(bundle_path) if bundle_path else DEFAULT_BUNDLE
        if bundle_path.exists():
            self._load_bundle(bundle_path)
        elif allow_legacy and LEGACY_FACS.exists() and LEGACY_SPR.exists():
            self._load_legacy()
        else:
            raise FileNotFoundError(
                f"No release bundle at {bundle_path} and no raw checkpoints at "
                f"{LEGACY_FACS} / {LEGACY_SPR}. Run scripts/export_release_affinity_v2.py first."
            )

        self.facs.to(self.device).eval()
        self.spr.to(self.device).eval()

    # ---- loading -----------------------------------------------------------

    def _load_bundle(self, path: Path) -> None:
        b = torch.load(path, map_location="cpu", weights_only=False)
        self.source = str(path)
        self.encoder_config = b["encoder_config"]
        self.pre = b["preprocessing"]
        self.facs_classes = b["facs"]["classes"]
        self.facs_metrics = b["facs"]["metrics"]
        self.spr_metrics = b["spr"]["metrics"]
        self.caveats = b.get("caveats", []) or _default_caveats(self.facs_metrics, self.spr_metrics)

        self.facs = FACSClassifier(
            SequenceEncoder(**self.encoder_config), num_classes=len(self.facs_classes)
        )
        self.facs.load_state_dict(b["facs"]["state_dict"])

        self.spr = SPRRegressor(
            SequenceEncoder(**self.encoder_config), feature_dim=b["spr"]["feature_dim"]
        )
        self.spr.load_state_dict(b["spr"]["state_dict"])
        self._set_scalers(b["spr"].get("scalers", {}), b["spr"]["feature_dim"])

    def _set_scalers(self, sc: dict, feature_dim: int) -> None:
        """Target/feature standardisation fitted on the training split.

        The SPR regressor emits standardised units, so features must be centred
        and the output rescaled. Checkpoints from before standardisation carry no
        scalers and fall back to identity, which reproduces their old behaviour.
        """
        self.y_mean = float(sc.get("y_mean", 0.0))
        self.y_std = float(sc.get("y_std", 1.0))
        self.feat_mean = torch.tensor(
            sc.get("feat_mean", [0.0] * feature_dim), dtype=torch.float32
        ).to(self.device)
        self.feat_std = torch.tensor(
            sc.get("feat_std", [1.0] * feature_dim), dtype=torch.float32
        ).to(self.device)
        self.scalers_fitted = bool(sc.get("fitted", "y_mean" in sc))

    def _load_legacy(self) -> None:
        """Fall back to the raw training checkpoints (constructor defaults)."""
        facs_ck = torch.load(LEGACY_FACS, map_location="cpu", weights_only=False)
        spr_ck = torch.load(LEGACY_SPR, map_location="cpu", weights_only=False)
        self.source = f"{LEGACY_FACS} + {LEGACY_SPR} (legacy, no bundle)"
        self.encoder_config = {}
        self.pre = {"max_len": 15, "reference_seq": "WGGDGFYAMD"}
        self.facs_classes = ["low", "medium", "high"]
        self.facs_metrics = {"val_accuracy": float(facs_ck["accuracy"])}
        self.spr_metrics = {"val_r2": float(spr_ck["r2"]), "val_mae": float(spr_ck["mae"])}
        self.caveats = _default_caveats(self.facs_metrics, self.spr_metrics)

        self.facs = FACSClassifier(SequenceEncoder(), num_classes=3)
        self.facs.load_state_dict(facs_ck["model"])
        self.spr = SPRRegressor(SequenceEncoder(), feature_dim=int(spr_ck["feature_dim"]))
        self.spr.load_state_dict(spr_ck["model"])
        self._set_scalers(
            {k: spr_ck[k] for k in ("y_mean", "y_std", "feat_mean", "feat_std") if k in spr_ck},
            int(spr_ck["feature_dim"]),
        )

    def info(self) -> EngineInfo:
        return EngineInfo(
            bundle=self.source,
            device=str(self.device),
            encoder_config=self.encoder_config,
            preprocessing=self.pre,
            facs_classes=list(self.facs_classes),
            facs_metrics=self.facs_metrics,
            spr_metrics=self.spr_metrics,
            caveats=list(self.caveats),
        )

    # ---- prediction --------------------------------------------------------

    def predict(
        self,
        sequences: Iterable[str],
        batch_size: int = 512,
        ids: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        """Score sequences. Returns one row per input, in input order.

        Invalid inputs (empty / non-letter) get NaN predictions and a note in
        the `warning` column rather than killing the whole batch.
        """
        raw = list(sequences)
        if ids is not None and len(ids) != len(raw):
            raise ValueError(f"ids length {len(ids)} != sequences length {len(raw)}")
        if not raw:
            return pd.DataFrame(
                columns=["id", "cdrh3", "facs_class", "facs_confidence", "p_low",
                         "p_medium", "p_high", "pred_log_kd", "pred_kd_nM", "warning"]
            )

        max_len = int(self.pre.get("max_len", 15))
        ref = self.pre.get("reference_seq", "WGGDGFYAMD")

        cleaned, warnings, keep = [], [], []
        for i, s in enumerate(raw):
            s = ("" if s is None else str(s)).strip().upper()
            note = ""
            if not s:
                note = "empty sequence"
            elif not s.isalpha():
                note = "non-letter characters"
            else:
                unknown = sorted(set(s) - VALID_AA)
                if unknown:
                    note = f"unknown residues mapped to X: {','.join(unknown)}"
                if len(s) > max_len:
                    note = (note + "; " if note else "") + f"truncated to {max_len}"
                keep.append(i)
            cleaned.append(s)
            warnings.append(note)

        n = len(raw)
        probs = np.full((n, len(self.facs_classes)), np.nan, dtype=np.float32)
        log_kd = np.full(n, np.nan, dtype=np.float32)

        for start in range(0, len(keep), batch_size):
            idx = keep[start : start + batch_size]
            seqs = [cleaned[i] for i in idx]
            x = torch.stack([seq_to_indices(s, max_len) for s in seqs]).to(self.device)
            feats = torch.from_numpy(
                np.stack([compute_features(s, ref) for s in seqs])
            ).to(self.device)

            with self._lock, torch.inference_mode():
                p = torch.softmax(self.facs(x), dim=1)
                k = self.spr(x, (feats - self.feat_mean) / self.feat_std).reshape(-1)
                k = k * self.y_std + self.y_mean

            probs[idx] = p.float().cpu().numpy()
            log_kd[idx] = k.float().cpu().numpy()

        class_idx = np.where(np.isnan(probs[:, 0]), -1, probs.argmax(axis=1))
        facs_class = [self.facs_classes[i] if i >= 0 else None for i in class_idx]
        confidence = np.where(class_idx >= 0, probs.max(axis=1), np.nan)

        kd_nM = np.where(
            np.isnan(log_kd), np.nan, 10 ** np.clip(log_kd, *LOG_KD_CLAMP)
        )

        out = pd.DataFrame(
            {
                "id": list(ids) if ids is not None else [f"seq_{i+1}" for i in range(n)],
                "cdrh3": cleaned,
                "facs_class": facs_class,
                "facs_confidence": confidence,
                "p_low": probs[:, 0],
                "p_medium": probs[:, 1],
                "p_high": probs[:, 2],
                "pred_log_kd": log_kd,
                "pred_kd_nM": kd_nM,
                "warning": warnings,
            }
        )
        return out


def _default_caveats(facs_metrics: dict, spr_metrics: dict) -> list:
    """Caveats derived from the loaded metrics, never hard-coded."""
    r2 = spr_metrics.get("val_r2", float("nan"))
    out = [
        f"FACS classifier val accuracy {facs_metrics.get('val_accuracy', float('nan')):.3f} (3 classes).",
    ]
    if not (r2 == r2) or r2 <= 0:
        out.append(
            f"SPR regressor val R2 {r2:.2f} is not positive -- predicted KD is no better "
            "than the dataset mean. Treat pred_kd_nM as unusable."
        )
    else:
        out.append(
            f"SPR regressor val R2 {r2:.2f}. Absolute pred_kd_nM carries roughly "
            "+/- 0.7 log10 units of error, so rank designs by it rather than quoting "
            "the nM value; rank correlation is the metric it was validated on."
        )
    return out


# ============================================================================
# INPUT LOADING
# ============================================================================

def load_sequences(path: str, seq_col: str | None = None, id_col: str | None = None):
    """Read sequences from FASTA, CSV/TSV, plain text, or '-' for stdin."""
    if path == "-":
        lines = [ln.strip() for ln in sys.stdin if ln.strip()]
        return lines, None

    p = Path(path)
    if not p.exists():
        raise SystemExit(f"input not found: {p}")

    suffix = p.suffix.lower()
    if suffix in {".fa", ".fasta", ".faa", ".fas"}:
        from Bio import SeqIO

        recs = list(SeqIO.parse(str(p), "fasta"))
        if not recs:
            raise SystemExit(f"no FASTA records in {p}")
        return [str(r.seq) for r in recs], [r.id for r in recs]

    if suffix in {".csv", ".tsv", ".txt"}:
        # .txt with one sequence per line is common; try that only if CSV parse
        # yields a single unnamed column.
        sep = "\t" if suffix == ".tsv" else ","
        if suffix == ".txt":
            lines = [ln.strip() for ln in p.read_text().splitlines() if ln.strip()]
            if lines and all(ln.isalpha() for ln in lines):
                return lines, None
        df = pd.read_csv(p, sep=sep)
        col = seq_col or _guess_seq_col(df, p)
        ids = df[id_col].astype(str).tolist() if id_col else None
        return df[col].astype(str).tolist(), ids

    raise SystemExit(f"unsupported input extension '{suffix}' (use .fasta/.csv/.tsv/.txt or -)")


def _guess_seq_col(df: pd.DataFrame, path: Path) -> str:
    for cand in ("cdrh3", "CDRH3", "sequence", "seq", "cdr_h3"):
        if cand in df.columns:
            return cand
    raise SystemExit(
        f"could not find a sequence column in {path}; columns are "
        f"{list(df.columns)} -- pass --seq-col"
    )


# ============================================================================
# COMMANDS
# ============================================================================

def cmd_predict(args) -> int:
    seqs, ids = load_sequences(args.input, args.seq_col, args.id_col)
    eng = AffinityEngine(args.bundle, device=args.device)
    info = eng.info()
    print(f"[engine] {info.bundle}", file=sys.stderr)
    print(f"[engine] device={info.device}  n_sequences={len(seqs)}", file=sys.stderr)

    df = eng.predict(seqs, batch_size=args.batch_size, ids=ids)

    if args.sort:
        df = df.sort_values("p_high", ascending=False, na_position="last")
    if args.top:
        df = df.head(args.top)

    if args.output in ("-", "/dev/stdout"):
        df.to_csv(sys.stdout, index=False)
    else:
        outp = Path(args.output)
        outp.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(outp, index=False)
        print(f"[engine] wrote {len(df)} rows to {outp}", file=sys.stderr)

    bad = int(df["warning"].astype(bool).sum())
    if bad:
        print(f"[engine] {bad} row(s) had input warnings", file=sys.stderr)
    for c in info.caveats:
        print(f"[caveat] {c}", file=sys.stderr)
    return 0


def cmd_info(args) -> int:
    eng = AffinityEngine(args.bundle, device=args.device)
    print(json.dumps(eng.info().__dict__, indent=2, default=str))
    return 0


def cmd_selftest(args) -> int:
    """Score the labelled SPR set and report how the engine actually does."""
    from scipy.stats import spearmanr  # optional; fall back if absent
    return _selftest(args, spearmanr)


def _selftest(args, spearmanr=None) -> int:
    from sklearn.metrics import mean_absolute_error, r2_score

    csv = REPO / ("data/bucket/extracted/hackathon-data/her2-trastuzumab/"
                  "trastuzumab_her2_spr_all_768.csv")
    if args.data:
        csv = Path(args.data)
    df = pd.read_csv(csv)
    df = df[df["binding_result"] == "quantified_binding"].dropna(subset=["kd_nM"]).copy()
    df["log_kd"] = np.log10(df["kd_nM"])

    eng = AffinityEngine(args.bundle, device=args.device)
    info = eng.info()
    print(f"[engine] {info.bundle}")
    print(f"[engine] device={info.device}")

    preds = eng.predict(df["cdrh3"].tolist(), batch_size=args.batch_size)
    ok = preds["pred_log_kd"].notna().to_numpy()
    y_true = df["log_kd"].to_numpy()[ok]
    y_pred = preds["pred_log_kd"].to_numpy()[ok]

    print(f"\nScored {ok.sum()} / {len(df)} labelled SPR sequences")
    print(f"  R2            {r2_score(y_true, y_pred):+.4f}   (<= 0 = no better than the mean)")
    print(f"  MAE           {mean_absolute_error(y_true, y_pred):.4f}  log10 units")
    print(f"  pred spread   {y_pred.std():.4f}  vs true spread {y_true.std():.4f}")
    if spearmanr is not None:
        rho, p = spearmanr(y_true, y_pred)
        print(f"  Spearman rho  {rho:+.4f}  (p={p:.3g})   <- ranking usefulness")
    print("\nNOTE: these are TRAINING-SET-INCLUSIVE numbers (the 190 rows include "
          "the rows the model trained on), so they are optimistic.")
    for c in info.caveats:
        print(f"[caveat] {c}")
    return 0


def cmd_serve(args) -> int:
    """Minimal stdlib HTTP server -- no extra dependencies."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    eng = AffinityEngine(args.bundle, device=args.device)
    info = eng.info()

    # Token auth. --token auto generates one; --token "" disables the check.
    token = args.token
    if token == "auto":
        token = secrets.token_urlsafe(24)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _authed(self) -> bool:
            """True if the request may proceed. /health is always open."""
            if not token:
                return True
            header = self.headers.get("authorization") or ""
            prefix = "bearer "
            if not header.lower().startswith(prefix):
                return False
            return secrets.compare_digest(header[len(prefix):].strip(), token)

        def _send(self, code: int, payload: dict) -> None:
            body = json.dumps(payload, default=str).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path.rstrip("/") in ("/health", ""):
                self._send(200, {"status": "ok", "device": info.device})
            elif self.path.rstrip("/") == "/info":
                if not self._authed():
                    self._send(401, {"error": "missing or bad bearer token"})
                    return
                self._send(200, info.__dict__)
            else:
                self._send(404, {"error": "try GET /health, GET /info, POST /predict"})

        def do_POST(self):  # noqa: N802
            if self.path.rstrip("/") != "/predict":
                self._send(404, {"error": "POST /predict"})
                return
            if not self._authed():
                self._send(401, {"error": "missing or bad bearer token"})
                return
            try:
                length = int(self.headers.get("content-length") or 0)
                if length <= 0 or length > 10_000_000:
                    raise ValueError("missing or oversized body")
                payload = json.loads(self.rfile.read(length))
                seqs = payload.get("sequences")
                if not isinstance(seqs, list) or not seqs:
                    raise ValueError("body must be {\"sequences\": [...]}")
                if len(seqs) > args.max_batch:
                    raise ValueError(f"at most {args.max_batch} sequences per request")
                df = eng.predict([str(s) for s in seqs], batch_size=args.batch_size)
            except Exception as exc:  # noqa: BLE001
                self._send(400, {"error": f"{type(exc).__name__}: {exc}"})
                return
            self._send(
                200,
                {
                    "predictions": json.loads(df.to_json(orient="records")),
                    "caveats": info.caveats,
                },
            )

        def log_message(self, fmt, *a):  # quieter logs
            sys.stderr.write("[http] %s - %s\n" % (self.address_string(), fmt % a))

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[engine] {info.bundle}")
    print(f"[engine] device={info.device}")
    print(f"[serve]  http://{args.host}:{args.port}  (GET /health, GET /info, POST /predict)")
    if token:
        print(f"[serve]  auth: REQUIRED on /info and /predict (/health stays open)")
        print(f"[serve]  token: {token}")
        print(f"[serve]  e.g. curl -H 'Authorization: Bearer {token}' ...")
    else:
        print("[serve]  auth: DISABLED -- do not bind this to a reachable interface")
    for c in info.caveats:
        print(f"[caveat] {c}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[serve] shutting down")
    finally:
        srv.server_close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Affinity model inference engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--bundle", default=None, help=f"release bundle (default: {DEFAULT_BUNDLE})")
    ap.add_argument("--device", default=None, help="cuda | cpu (default: auto)")
    ap.add_argument("--batch-size", type=int, default=512)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("predict", help="score sequences from a file/stdin")
    p.add_argument("--input", "-i", required=True, help="FASTA, CSV, TSV, TXT, or - for stdin")
    p.add_argument("--output", "-o", required=True, help="output CSV path, or - for stdout")
    p.add_argument("--seq-col", default=None, help="sequence column for CSV/TSV input")
    p.add_argument("--id-col", default=None, help="id column for CSV/TSV input")
    p.add_argument("--sort", action="store_true", help="sort by P(high binder) descending")
    p.add_argument("--top", type=int, default=None, help="keep only the top N rows")
    p.set_defaults(func=cmd_predict)

    p = sub.add_parser("info", help="print loaded model metadata")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("selftest", help="score the labelled SPR set and report metrics")
    p.add_argument("--data", default=None)
    p.set_defaults(func=cmd_selftest)

    p = sub.add_parser("serve", help="run a local JSON HTTP endpoint")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8008)
    p.add_argument("--max-batch", type=int, default=5000)
    p.add_argument(
        "--token",
        default="auto",
        help="bearer token for /info and /predict; 'auto' generates one (default), "
             "empty string disables auth",
    )
    p.set_defaults(func=cmd_serve)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
