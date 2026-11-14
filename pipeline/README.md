# Pipeline

One command per stage, each writing a file the next stage reads, so a judge can run it on a
target we have never seen. Record model version and seed in every output.

```
generate/   target + contig -> candidate sequences/structures   (JapanFold, RFD4-Proteina, inverse folding)
score/      candidates -> structure, interface, affinity-proxy and developability scores
filter/     scores -> ranked table -> designs/submission.csv (<= 20)
```

## How many designs do we need? — `pipeline/status.py`

```bash
python3 pipeline/status.py --how     # read-only, prints the funnel and the arithmetic
```

Answers it from the files rather than from anyone's memory: generated → eligible → unique →
scored → ranked, the track split as `abguard` classified it, and how many designs 20 slots needs
at our **measured** yield. `--how` prints a one-line shell command to re-derive each number by
hand, so none of it has to be trusted. Control and probe runs are excluded from the counts.

## `filter/` — the submission gate (built, verified on the VM)

```bash
bash pipeline/filter/gate.sh [table.csv]   # exit 0 = eligible, non-zero = not a submission
```

| File | Does |
|---|---|
| `to_abguard.py` | `designs/submission.csv` -> `designs/submission.abguard.csv`, the five columns `abguard` requires. Fails first on our own mistakes (bad format, non-canonical residue, chain > 250 aa, duplicate id, missing light chain) with the row named |
| `gate.sh` | convert -> `novelty-report` -> `liability-report` -> `team-validate`. Writes `reports/novelty-report.csv` and `reports/liability-report.json` |
| `cif_to_submission.py` | RFD4-Proteina `*_generated.cif` -> our table. Identifies VH/VL by framework motif (not entity index, which is not stable) and **drops the two HER2 entities** — submitting the target would be an instant rejection |
| `abguard-control.csv` | the 4-design control run: wild-type, a 1-mutation known binder, a 3-mutation variant, a free cysteine. All four are rejected, each for its own reason — that is the proof the gate is live |

Two tables on purpose: `submission.csv` is ours (rank, scores, provenance, reasoning),
`submission.abguard.csv` is generated and never hand-edited. `rank.py` joins the verdict back on
`sequence_id`. Run on the VM — `abguard` is login-shell-only, see [`../docs/abguard.md`](../docs/abguard.md).

Rules we hold ourselves to:

- Every score column names its model and version. No anonymous numbers.
- Multiple seeds, and the spread reported — not the best run.
- Re-score binding after any liability fix.
- One unseen case run end to end before the pitch. The judges will do this to us.
