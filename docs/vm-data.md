# What is actually on the VM — data inventory and what it changes

**Source.** Direct survey of the team VM (`hackathon@89.169.99.24`), 14 Nov 2026, after
`aws s3 sync` of `s3://apheris-oslo-hackathon` completed. 4.7 GB synced. This file records what was
**observed on disk**, not what the task PDF promises — where the two differ, the disk wins and the
difference is called out.

Companion to [`scripts/fetch_hackathon_data.py`](../scripts/fetch_hackathon_data.py) (issue #5),
which re-syncs and verifies these counts. Provenance of each claim below is marked:
**[disk]** observed on the VM · **[abguard]** from `abguard`'s own help text · **[PDF]** from
[`task.md`](task.md) · **[inferred]** our arithmetic, not a source.

---

## 1. `hackathon-data/` — the organisers' bucket, fully synced

4.7 GB. Sizes **[disk]**.

| Folder | Size | What is usable | Verdict |
|---|---|---|---|
| `her2-trastuzumab/` | 6 MB | 524,346 CDRH3 variants with FACS high/med/low classes, **plus a 768-row SPR table of which 190 carry a real K<sub>D</sub>** (0.023–13,863 nM). Trastuzumab itself appears 8× at 0.03–0.18 nM. | **The only data that maps to a judged axis.** Affinity ranking lives here, and the 8 trastuzumab replicates are the baseline every design is scored against. |
| `zenodo-18390239-ab-ag-complexes/` | 560 MB | ipTM matrices, top-model accuracy and replica RMSD for 106 cognate + 11,342 shuffled nanobody–antigen pairs | **Calibration only.** Tells you how much to trust ipTM *before* ranking on it. Not a source of designs. |
| `sigma2-ab-ag-champloo/` | 1.7 GB | Per-replica AF3 / Chai-1 confidence JSONs, 50 samples per pair, plus a **29-pair SPR supplement** | Lets us compute **ipSAE / PAE-based** scores instead of raw ipTM. This is the PAE that [`probe-findings.md` §1](probe-findings.md) established no reachable Nebius model will return — it exists here as *data*. |
| `zenodo-10831512-trastuzumab-ngs/` | 2.4 GB, **still zipped** | Clonotype-split train/val/test of the FACS set, small-data splits, and the shanehsazzadeh 198 binders with log-affinity | Ready-made splits if we train an affinity model. **Clonotype-split matters**: a split we choose ourselves leaks near-duplicate CDRH3s across folds and flatters the model. |

### The SPR number is not a contradiction

Issue #5's priority list says "190 with SPR affinities"; Leonardo's layout in the same issue says
"SPR affinities (768 variants)". Both are right **[disk]**: the SPR table has **768 rows**, of which
**190 have a measurable K<sub>D</sub>**. The other 578 are measured non-binders, which are useful in
their own right — they are negatives on exactly our target. Nothing needs resolving with the
organisers.

The 190 span 0.023–13,863 nM, i.e. **5.8 orders of magnitude**. Anything we fit on this must be fit
on log K<sub>D</sub>, and a model that looks good in linear nM is fooling us.

---

## 2. Tooling and in-flight work (outside the bucket)

All **[disk]**.

- **`rfd4/`** — the full Apheris tutorial: 18 docs, `Tutorial.html`, example inputs.
  **`rfd4/12-her2.md` is the one that matters**: the four HER2 weights with their measured
  trade-offs. `18-vm.md` is the "run on your hackathon VM" entry point.
- **`Data/12-her2/`** — a *working* RFD4 input, already built: `her2_cdrh3.yaml` +
  `her2_fv_1n8z.cif`. Trastuzumab Fv on HER2 domain IV (1N8Z), CDRH3 **B99–108** free, 4 HER2
  hotspot atoms, everything else sequence- and geometry-fixed.
- **`josef/Scripts/run-her2.sh`** — complete `design → refold-prepare → Boltz-2 → refold-score`
  pipeline. A 4-design smoke run with `her2-novel-2026-11-09` was on the GPU at 11:22 UTC, 100%
  utilisation.
- **`lluis/`** is empty. **`foundry-assistant/`** is an unrelated side project (local Qwen KB
  server) — ignore it today.
- **All 19 Foundry Docker images are pre-pulled**: 6 folding models, 3 RFD4 weights.
  `abguard` is installed at `~/.local/bin/abguard`.

### Note on the CDRH3 span

`Data/12-her2/her2_cdrh3.yaml` leaves **B99–108** free. Our own reference puts trastuzumab's CDRH3
at **B99–109** (`WGGDGFYAMDY`, 11 residues, motif-anchored in
[`1n8z_epitope_report.json`](../data/reference/epitope/1n8z_epitope_report.json) and used by
[`pipeline/thermostability.py`](../pipeline/thermostability.py)). 99–108 is 10 residues. **Someone
should reconcile these before trusting a mutation count across the two** — a 10- vs 11-residue
window changes the identity denominator, and [`probe-findings.md` §3](probe-findings.md) already
warns that the ≥4-substitution floor holds only if identity is computed over the loop alone. Not yet
established which is right; flagged, not resolved.

---

## 3. Three findings that change the plan

### 3.1 `abguard` resolves open questions #1–#3. Read its help text, not the PDF.

**[abguard]** `abguard` states the rule directly: a design must differ from trastuzumab and from
every known CDRH3 by **≥3 mutations in CDRH3 if it is a trastuzumab variant** (≥70% identity), or
**≥2 if it is de novo**.

- [`task.md` §3 Q1](task.md) — "at least 2" vs "strictly more than 2". **Settled: ≥3 for
  optimisation.** The safe reading in `common.HARD_LIMITS["min_point_mutations_opt"] = 3` was right.
- [`task.md` §3 Q2](task.md) — de novo CDRH3 condition. **Settled: ≥2, against trastuzumab.**
- [`task.md` §3 Q3](task.md) — the novelty reference set. **Settled, and better than hoped:**
  `abguard` **ships its own reference DB** (`abguard_cdrh3.parquet`), so the novelty gate runs out
  of the box. Nobody needs to chase the organisers for a reference set.

**Correction this forces on our own work:** issue #5 and PR #17 record an **[inferred]** arithmetic
result — 524,346 FACS + 717 optimisation designs = 525,063, the corpus size quoted in #12 — with
the advice that the novelty pre-check should concatenate those two tables and assert 525,063. That
arithmetic still holds as a *description*, but the advice is now unnecessary: the gate that matters
runs from `abguard`'s own parquet, not from a corpus we assemble. Assembling one would be a second,
unvalidated implementation of a check `abguard` already owns, and `abguard` is the authority
([PDF]: "`abguard` decides, we do not argue").

### 3.2 `abguard` enforces something the PDF never mentions: LAP liabilities

**[abguard]** It reports sequence liabilities against the LAP reference (PLOS Comput Biol 2024).
The expected submission schema is:

```
sequence_id, kind, heavy_sequence, light_sequence, design_description
```

split on `kind ∈ {vhh, scfv, paired}`.

**Run `team-validate` and `liability-report` early.** A liability flag that first appears at 17:50
costs designs outright. Note this is a *different* list from the motif counts in
[`pipeline/04_score.py`](../pipeline/04_score.py) `LIABILITY_MOTIFS`, which were taken from
[`hackathon-brief.md`](hackathon-brief.md) — ours is a local prompt-to-look, `abguard`'s is a gate.
Where they disagree, `abguard` wins.

### 3.3 The real strategic hole is thermostability — and it is the axis that decides the ranking

Teams are ranked on **S-tier count first** **[PDF]**, and S-tier needs **all three** properties
improved. Of the three:

| Axis | Status |
|---|---|
| 2 — epitope preservation | **nearly free in the optimisation track.** CDRH3-only redesign on a fixed 1N8Z framework preserves the epitope by construction. |
| 1 — affinity | **covered.** The SPR table plus the 524k FACS classes are a real ranking signal. |
| 3 — thermostability | **zero provided data, zero model support** ([`probe-findings.md` §4](probe-findings.md)). |

So a CDRH3-only variant will **tie or regress** on Tm, and ties do not count **[PDF]**: "ties and
regressions are hollow". That caps the optimisation track at **A-tier no matter how good the binding
is**.

**The lever [inferred, worth checking with a mentor]:** the novelty rule constrains **only CDRH3**.
Framework and other-CDR mutations are unrestricted. So thermostabilising **framework** mutations are
legal, and are the only route to S-tier in the optimisation track.

Separately: **VHHs are intrinsically more thermostable** than a trastuzumab Fab/scFv, so a de novo
VHH gets axis 3 close to free — but then has to win axes 1 and 2 the hard way, and
[`probe-findings.md` §4](probe-findings.md) notes de novo + VHH has no model-based stability signal
at all.

---

## 4. What 3.3 means for the thermostability axis as implemented

This is a limitation of [`pipeline/thermostability.py`](../pipeline/thermostability.py) (issue #10)
and it should be understood before anyone ranks on it.

`framework_mutations` counts substitutions outside the CDRs, relative to trastuzumab, and the module
says to drive it to zero. That is a **destabilisation-risk** term: trastuzumab's framework is
already humanised and already stable, so drift away from it is, on average, downhill.

But **S-tier requires Tm to *improve*, not to be preserved.** Zero framework mutations means Tm ≈
baseline, which is a tie, which scores nothing. So the term is:

- **right** for screening out designs that have wandered off a stable framework by accident;
- **wrong** as the thing you maximise, because maximising it selects for exactly the designs that
  cannot clear axis 3.

It is also blind to *which* substitution was made: the module counts every framework substitution as
1 regardless of identity or burial, so a known stabilising mutation and a random destabilising one
score identically. A deliberate thermostabilising design and a sloppy one are indistinguishable to
it.

**Consequence for use:** treat `framework_mutations` as a liability filter, not as the axis-3 score.
A real axis-3 claim needs *targeted* stabilising mutations with a stated reason per mutation — and
since nothing on the platform predicts Tm, that reason has to come from the literature (germline
reversion, consensus substitution, proline/disulfide engineering) and be argued in the pitch, not
computed. [`probe-findings.md` §4](probe-findings.md)'s conclusion stands: weight axis 3 as our
weakest-evidence axis and say so. Judgment is 40%.

---

## 5. Open, after this survey

1. **CDRH3 window: B99–108 or B99–109?** `Data/12-her2/her2_cdrh3.yaml` says 10 residues, our
   reference says 11. Changes the identity denominator and the substitution floor (§2 above).
2. **Does `abguard`'s CDRH3 identity use the loop alone or a wider window?**
   [`probe-findings.md` §3](probe-findings.md)'s ≥4-substitution arithmetic depends on it. `abguard`
   ships the reference DB but that does not by itself tell us the window.
3. **Which ipTM column in `zenodo-18390239-...` is the AF3 one?** Computing the 454/21 true-negative
   split is how you confirm it (see `scripts/fetch_hackathon_data.py`, `derived` expectation).
4. **Does the participant guide's "include Apheris' OpenFold to qualify" condition still hold?**
   Unchanged from [`task.md` §3 Q8](task.md); the PDF states no such requirement.
