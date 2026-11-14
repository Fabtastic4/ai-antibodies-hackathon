# `affinity_v2` — learned CDRH3 affinity scoring, with a serving path

Ranks trastuzumab CDRH3 variants by predicted HER2 affinity. Two-stage transfer
learning: pretrain a sequence encoder on the 524k-variant FACS screen, then fit a
KD regressor on the 190 variants with measured SPR.

**This is a second, independent model.** `pipeline/score/affinity_model.py` (one-hot
features, 215 lines) solves the same problem a different way and came first. Neither
has been chosen for the submission ranking — see [Which model should rank the
submission?](#which-model-should-rank-the-submission) for the comparison that decision
needs.

---

## What it predicts

| Output | Head | Use it for |
|---|---|---|
| `p_low`, `p_medium`, `p_high` | FACS classifier | Coarse binder strength. Saturates near wild type. |
| `pred_log_kd`, `pred_kd_nM` | SPR regressor | **Ranking** designs by affinity. |

Rank on `pred_kd_nM`; do not quote it as a measured number. Held-out MAE is 0.72
log10 units, so a prediction of 1 nM means "roughly 0.2–5 nM."

## Measured performance

Splits are 70/10/20 with `SPLIT_SEED = 42`, stratified for FACS. The test split is
used for neither training nor model selection.

**Stage 1 — FACS classifier** (n_train 367,042 / val 52,434 / test 104,870)

| | Value |
|---|---|
| Test accuracy | **0.7194** |
| Test balanced accuracy | 0.7197 |
| Val accuracy | 0.7183 |
| Majority-class baseline | 0.3624 |

Val and test agree to within 0.2%, so the model generalises rather than fitting its
selection set. Errors are mostly one bin off; `low`↔`high` confusions are ~6% of rows.

**Stage 2 — SPR regressor** (n_train 133 / val 19 / test 38)

| | Test | Val |
|---|---|---|
| R² | **0.399** | 0.585 |
| Spearman ρ | **0.752** | — |
| MAE (log10 KD) | 0.716 | 0.656 |
| RMSE (log10 KD) | 0.863 | — |

Quote the test numbers. `test_mae_kd_nM` in `models/spr/spr_metrics.json` (464 nM) is
MAE in linear space, where a few weak binders dominate the mean — it is not a useful
summary; use the log-space MAE.

### Performance in the submittable band

abguard only admits variants ≥3 mutations from trastuzumab and from every known
CDRH3, so that band is the only region a submission can come from. Low-mutation
variants are easier to score *and* ineligible, so whole-panel metrics flatter the
model. Measured over all 190 SPR rows (**train-inclusive, therefore optimistic**):

| Band | n | R² | Spearman ρ |
|---|---|---|---|
| All | 190 | 0.628 | 0.800 |
| 1–2 mutations (ineligible) | 37 | 0.642 | 0.819 |
| **≥3 mutations (submittable)** | **153** | **0.464** | **0.729** |

Performance does drop where it counts, but ρ=0.73 over 153 submittable variants is
still a usable ranker. A clean held-out ≥3 number would need the 38-row test split
restricted further, which leaves too few rows to estimate from.

## Architecture

```
                 CDRH3 (<=15 aa)
                       |
          nn.Embedding(21, 64, padding_idx=X)
                       |
        TransformerEncoder: 2 layers, 4 heads,
        dim_feedforward=128, dropout=0.1
                       |
         masked mean-pool over residues  ->  [64]
                 /                \
   FACS head                        SPR head (encoder frozen)
   64 -> 256 -> 128 -> 3            [64 | 31 hand-crafted] = 95
   ReLU, dropout 0.3                95 -> 192 -> 128 -> 64 -> 1
   softmax: low/medium/high         ReLU, dropout 0.2 -> log10 KD
```

The 31 hand-crafted features: sequence length, edit distance from wild-type
`WGGDGFYAMD`, 20 amino-acid composition fractions, mean hydrophobicity/charge/size,
and the first-3 and last-3 residue indices.

Both the features and the regression target are **standardised** (`feat_mean`,
`feat_std`, `y_mean=1.4562`, `y_std=1.0726`, stored in the checkpoint). This is not
cosmetic: without it the regressor collapsed to a constant predictor at R²=−1.73.
Any retrain must keep it.

### Known limitation: the encoder is order-blind

There is **no positional encoding**. A transformer over token embeddings with no
positional signal is permutation-invariant, so the encoder sees amino-acid
*composition* and not order:

```
WGGDGFYAMD   p_high = 0.9403
DMAYFGDGGW   p_high = 0.9403     <- same residues, scrambled
MDAGGWYFGD   p_high = 0.9403
```

Consequences worth knowing before you trust a ranking:

- The FACS head cannot distinguish any permutation of a CDRH3.
- The SPR head has *partial* position awareness, but only through the first-3/last-3
  residue features — 6 of 31 inputs.
- Scoring is least reliable exactly where designs differ most from wild type.

Adding a positional embedding (`nn.Embedding(max_len, embed_dim)` summed onto the
token embedding) is the highest-value open fix, and the seeded test split now makes
the improvement measurable.

### Second caveat: a compositional artifact

In a single-mutant scan of wild type, the ten tightest predicted binders were all
X→M substitutions. "More methionine is better" is more plausibly a compositional
shortcut than biology, and methionine in a CDR is a known oxidation liability. Treat
methionine-enriched hits as suspect pending orthogonal evidence.

---

## Install

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r scripts/requirements_affinity_v2.txt
```

Needs torch, pandas, numpy, scikit-learn, scipy, biopython, tqdm. CUDA is optional —
everything falls back to CPU.

## Run inference

All commands are run from the repository root.

```bash
# FASTA in, CSV out, ranked by P(high binder)
python3 pipeline/score/affinity_v2/inference.py predict \
    -i designs/candidates.fasta -o reports/affinity_v2.csv --sort

# a CSV column instead
python3 pipeline/score/affinity_v2/inference.py predict \
    -i designs/raw/b1-novel-s1.csv --seq-col cdrh3 -o scored.csv

# stdin, straight to stdout
echo WGGDGFYAMD | python3 pipeline/score/affinity_v2/inference.py predict -i - -o -

# loaded model config, metrics and caveats
python3 pipeline/score/affinity_v2/inference.py info

# reproduce the metrics above against the labelled SPR panel
python3 pipeline/score/affinity_v2/inference.py selftest
```

Output columns: `id`, `cdrh3`, `facs_class`, `facs_confidence`, `p_low`, `p_medium`,
`p_high`, `pred_log_kd`, `pred_kd_nM`, `warning`.

Malformed input never fails the batch. Sequences with non-letter characters get `null`
predictions, unknown residues are mapped to `X`, over-length sequences are truncated —
each flagged in `warning`. Always check that column before using a scored table.

### From Python

```python
from pipeline.score.affinity_v2.inference import AffinityEngine

eng = AffinityEngine()                      # loads models/release/v2 by default
df  = eng.predict(["WGGDGFYAMD", "WGNDGFYMLD"])
df  = eng.predict(seqs, batch_size=4096)    # ~35k sequences/sec on an H100
```

The engine loads the weights once; reuse the instance across batches.

## Deploy as an HTTP service

```bash
python3 pipeline/score/affinity_v2/inference.py serve --host 127.0.0.1 --port 8008
```

Stdlib `http.server` — no extra dependencies. It prints a generated bearer token on
startup.

| Route | Auth | Returns |
|---|---|---|
| `GET /health` | open | `{"status":"ok","device":"cuda"}` |
| `GET /info` | bearer | config, metrics, caveats |
| `POST /predict` | bearer | `{"sequences":[...]}` → predictions + caveats |

```bash
curl -s localhost:8008/predict \
  -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"sequences":["WGGDGFYAMD","WGNDGFYMLD"]}'
```

Up to 5000 sequences per request (2000 round-trips in ~0.15 s). `/predict` and
`/info` require the token; `/health` stays open for liveness checks.

### Deployment notes

- **Default bind is `127.0.0.1`.** `--host 0.0.0.0` exposes the service to the whole
  network. There is no TLS and no per-user auth, so prefer an SSH tunnel:
  `ssh -L 8008:localhost:8008 user@vm`.
- **Token handling.** `--token auto` (the default) generates one per start;
  `--token <value>` pins it; `--token ""` disables auth entirely — only ever safe on
  a loopback bind. Never commit a token: `.gitignore` excludes `.inference_token*`.
- **Concurrency.** `ThreadingHTTPServer` with a lock around the forward pass, so one
  CUDA model serves concurrent requests safely. Throughput is bounded by the GPU, not
  the thread count.
- **Not a managed service.** It will not survive a reboot. Use `systemd --user`, or
  supervise it, if it needs to stay up.
- **Pin the bundle** with `--bundle models/release/v2/affinity_bundle.pt` in anything
  automated, so a later default change cannot silently swap the model under you.

## Retrain

```bash
bash scripts/train_affinity_v2.sh        # both stages; ~15 min on an H100
```

Then freeze the weights into a verifiable release:

```bash
python3 scripts/export_release_affinity_v2.py --version v3
python3 scripts/export_release_affinity_v2.py --verify-only models/release/v3
```

The export writes a self-contained `affinity_bundle.pt` carrying the architecture
config, the preprocessing contract, the metrics and the provenance — so loading never
depends on constructor defaults in this file staying unchanged — plus byte-identical
copies of the raw checkpoints and a `manifest.json` with SHA-256 sums. `--verify-only`
re-checks the sums and rebuilds both models from the bundle alone.

## Weights

```
models/release/v2/
    affinity_bundle.pt     978,387 B   self-contained: weights + config + metrics
    facs_classifier.pt     490,023 B   raw checkpoint, unmodified
    spr_regressor.pt       497,645 B   raw checkpoint, unmodified
    manifest.json                      SHA-256 sums, metrics, provenance, caveats
```

v1 is deliberately not included: its SPR head was a constant predictor at R²=−1.73
and should not be used.

## Which model should rank the submission?

Unresolved, and worth settling with a measurement rather than a preference. The two
models have never been compared on the same footing. A fair comparison needs:

1. Both scored on the **same** held-out rows, restricted to the **≥3-mutation band**.
2. **Spearman ρ** as the headline metric — the ranking is what the submission uses.
3. A note on which rows each model trained on, since the panels overlap.

`affinity_v2` reports ρ=0.729 on 153 submittable rows, but that figure is
train-inclusive and so not comparable to a clean held-out number. Run the comparison
before either model gates a submission.

## Open work

- [ ] Add positional encoding to the encoder; re-measure on the seeded test split.
- [ ] Head-to-head against `pipeline/score/affinity_model.py` on the ≥3 band.
- [ ] Use the 578 discarded SPR rows (460 `no_reportable_kd`, 104 `inconclusive`,
      14 `not_reported`). These are mostly weak or non-binders — real signal about
      what breaks binding, currently thrown away. Censored regression or an auxiliary
      binder/non-binder head over all 768 rows.
- [ ] Investigate the methionine enrichment; add a developability filter if it is an
      artifact.
- [ ] Ridge regression on the 31 features as a baseline, to confirm the network earns
      its complexity at n=133.
