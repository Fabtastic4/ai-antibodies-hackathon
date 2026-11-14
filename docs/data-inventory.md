# Data inventory — what we actually have

Verified on the VM (`hackathon@89.169.99.24`) at 13:05 CET by reading the files, not the brief.
Everything is already synced to `~/hackathon-data` (4.7 GB) — a teammate did this at 09:35.
**VM clock is UTC, about an hour behind CET.** Times below are CET unless marked.

---

## The two numbers everything is measured against

From row 1 of the SPR table, which is wild-type trastuzumab:

| | |
|---|---|
| **Trastuzumab CDRH3** | `WGGDGFYAMD` — **10 residues** |
| **Trastuzumab KD** | **0.152 nM** |

**Eligibility arithmetic, now exact.** CDRH3 is 10 residues, and the optimisation track needs
< 70% CDRH3 identity. 7/10 identical is 70%, which does *not* pass, so we need ≤ 6 identical —
**at least 4 mutations in CDRH3**, every time. That is a hard floor on every design we submit, and
it is checkable with a string comparison.

---

## 1. `her2-trastuzumab/` — 6 MB — the ranking data

### `trastuzumab_her2_spr_all_768.csv` (200 KB, 768 rows)

```
cdrh3, vh_sequence, vl_sequence, kd_nM, binding_result
WGGDGFYAMD, EVQLVESGG…, DIQMTQSPS…, 0.152, quantified_binding
```

**This is the validation set for lever 1.** Real KD values in nM on the assay modality we are judged
on. `binding_result` separates quantified binders from non-quantifiable ones.

### `tz_her2_facs_3classes_524346.csv.zip` (6 MB → 130 MB, 524,346 rows)

```
cdrh3, binding_class, vh_sequence, vl_sequence, edit_distance
WGHCCLYQLG, medium, EVQLVESGG…, DIQMTQSPS…, 7
FYKGVFYAYE, medium, EVQLVESGG…, DIQMTQSPS…, 7
```

**Two things here we did not expect and should exploit:**

- **`edit_distance` is precomputed.** Selecting the ≥ 4-mutation subset — the only region we are
  allowed to submit from — is a single filter, not a computation. The honest-metric problem in the
  plan becomes trivial to implement: `df[df.edit_distance >= 4]`.
- The VH/VL sequences are carried per row, so the full construct is reconstructible for any variant
  without us assembling it.

Also note `WGHCCLYQLG` in row 1: **two cysteines**. The library contains variants that would fail
`abguard`'s unpaired-cysteine check. Our novelty set and our own designs both need that filter.

This is also the **novelty set**: a design's CDRH3 must differ from every CDRH3 in these two tables
(525,114 rows combined — the task PDF's 525,063 plus overlap).

---

## 2. `zenodo-18390239-ab-ag-complexes/` — 560 MB — the find of the afternoon

### `iptm_confidence_scores.zip` → three 91×91 matrices (150 KB total)

`af3_matrix_clean.csv`, `boltz2_matrix_clean.csv`, `chai1_matrix_clean.csv`. All-vs-all ipTM:
rows and columns are antigen PDB ids, so the **diagonal is a cognate (real binding) pair and every
off-diagonal cell is a non-cognate pair**. Same pairs, scored independently by all three models.

**That is ~91 positives and ~8,190 labelled negatives, in a file small enough to open instantly.**
It is everything lever 4 needs, and it means the 152 GB archive is irrelevant to us.

Observed values for antigen `3OGO`:

| Pair | Type | AF3 | Boltz-2 | Chai-1 |
|---|---|---|---|---|
| 3OGO–3OGO | **cognate** | 0.89 | 0.93 | **0.18** |
| 3OGO–3RJQ | non-cognate | 0.12 | **0.64** | 0.13 |
| 3OGO–4M3K | non-cognate | 0.16 | **0.90** | 0.24 |

Read that table carefully, because it is the strongest evidence we have:

1. **Boltz-2 gives 0.90 ipTM to a pair that does not bind** — higher than AF3 gives some real pairs.
2. **Chai-1 gives the genuine cognate pair 0.18** — it would reject the true answer.
3. **The three models disagree violently on the same pair.** So "we took a second opinion from
   another predictor" is not automatically reassuring, and the plan's second-opinion step needs to
   report disagreement rather than average it away.

This is a far sharper version of the 454-negatives argument, on matched data, computable in minutes.

### `topmodel_structure_accuracy.zip` (~115 MB) — per-model accuracy for the top model of each pair
### `rmsd_between_replicas.zip` — replica spread, i.e. how reproducible each prediction was

---

## 3. `sigma2-ab-ag-champloo/` — 1.8 GB — and the organisers' own paper

`README.txt` names the associated publication:

> **"Structural Plausibility Without Binding Specificity: Limits of AI-Based Antibody-Antigen
> Structure Prediction Confidence Scores"** — Smorodina, Ali, Kropivšek Brumat, Salicari, Miklavc,
> Kappassov, Fu, Sormanni, de Marco, **Greiff**. DOI 10.64898/2026.03.02.709004

**Our central argument is the thesis of the organisers' own paper.** We are not inventing a critique
of confidence scores; we are applying the result whose dataset they handed us. Cite it in the deck —
it converts "clever hack" into "we read the literature attached to the data."

| File | Contents |
|---|---|
| `af3_real_per_replica_confidence_metrics.tar.zst` (1.3 GB) | per-replica `confidences.json` for **123 real** VHH–antigen systems |
| `chai1_all_per_replica_confidence_metrics.zip` (487 MB) | per-replica `.npz` scores, one per model_idx (50 samples/pair) |
| `spr-supplementary/spr_table_s1_pairwise.csv` | measured SPR per pair: `pair_type` (cognate / non-cognate), `spr_outcome`, `kd_nM`, `af3_iptm` |
| `spr-supplementary/spr_crossreactivity_14target.csv` | cross-reactivity across 14 targets |

**`spr_table_s1_pairwise.csv` is the cleanest thing in the whole bucket** for calibration: measured
cognate/non-cognate label *and* `af3_iptm` in the same row. That is a direct, honest ROC.

### Not available locally, and we do not need it

`af3_shuffled_per_replica_confidence_metrics.tar.zst` is **162 GB** and
`boltz2_all_per_replica_confidence_metrics.zip` is **1.7 TB** (sizes from
`table_of_contents_10.11582_2026.owjnnp5q.csv`). Neither is downloaded. **Do not try** — they are
the per-replica raw form of what the 150 KB matrices already summarise. Anyone who starts that sync
will fill the 359 GB of free disk and stall the box.

---

## 4. `zenodo-10831512-trastuzumab-ngs/` — 2.5 GB

A single `data.zip` holding the ready-made train/val/test splits of the FACS data plus earlier HER2
datasets. **Not yet unzipped — do this before training.** Use these splits rather than making our
own, so our numbers are comparable to the published ones.

---

## 5. `~/Data/12-her2/` — the organisers' ready-made HER2 design input

Not part of the data bucket; it ships with the RFD4 examples. **It removes most of Step 2 from the
plan.**

| File | What |
|---|---|
| `her2_fv_1n8z.cif` (302 KB) | PDB 1N8Z cropped to the Fv and HER2 domain IV |
| `her2_cdrh3.yaml` (1.3 KB) | the annotated design spec, fully commented |

From the YAML, already decided for us:

- **CDRH3 to redesign: chain B residues 99–108.** Left out of all conditions, so the model designs
  both its sequence and structure.
- Chain A = VL, chain B = VH. **Both chains present — this is an Fv, so we stay paired (scFv/Fab),
  which is what we wanted anyway.**
- HER2 is **split into chains C (489–580) and D (591–607)** because input validation rejects a
  numbering gap, and 1N8Z has an unresolved loop at 581–590.
- **Epitope hotspots already annotated**: `D/593/NZ`, `C/573/CD1`, `D/591/CG2`, `C/572/CD` — the
  HER2 atoms nearest CDRH3 in 1N8Z.

So Lluis's epitope task shrinks from "derive the interface" to "expand these four annotated atoms
into the full 4.5 Å contact list and record it in both numberings."

---

## VM state — verified, not assumed

| Thing | Status |
|---|---|
| All RFD4 weights | **present as local Docker images**, and **one image holds all of them** — select with `--model release\|antibody\|her2-conservative\|her2-balanced\|her2-exploratory\|her2-novel` |
| OpenFold3 | present, incl. `-of3ob` (OpenBind) and `-of3p2` |
| Protenix v2 / v1, Mol-1 base, ESMFold2, MSA | all present |
| H100 80 GB | was **idle at 0% until 12:53** — generation now running at 100% |
| Disk | 359 GB free of 484 GB |
| `foundry-toolkit module list` | **fails**: `no stored credential: run foundry-toolkit login`. Harmless — images are already pulled locally. |
| **`abguard`** | **NOT ON THE BOX.** Not in `PATH`, not in `~/.local/bin`, nothing from a filesystem search. **This is the submission gate. Ask the Apheris team in person.** |

Shared home directory, one user, one GPU — `~/josef/`, `~/mark/`, `~/data-inventory/` are per-person
working folders. Keep to your own.

### Proven working command, from Josef's smoke run

4 designs on `her2-novel` in **2m37s**, checkpoint
`rfd4-proteina-her2-novel-2026-11-09-ema.ckpt`. The design metrics CSV already returns
`hotspot_obedience` (0.75 and 1.0 on those two designs), interchain H-bond / salt-bridge /
hydrophobic contact counts, clash fractions and secondary-structure fractions —
**an epitope-contact signal at design time, before any refold.**

### Running now

`~/mark/generate.sh`, launched 12:53 CET, logging to `~/mark/logs/generate.log`:
200 × `her2-novel` seed 1, then 64 × `her2-exploratory` seed 2, both `high/front_loaded`, `--compile`.
Output: `~/mark/runs/b1-novel-s1/`, `~/mark/runs/b2-explor-s2/`.

**Designs are written incrementally per sample, so a partial run is still usable.** Whatever exists
at the 15:30 cutoff is the batch — there is no need to kill the job to harvest it.
