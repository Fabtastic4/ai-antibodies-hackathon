# What is actually on the VM — data, models and confidence scores

**Source.** Direct survey of the team VM (`hackathon@89.169.99.24`), 14 Nov 2026, 11:30–11:31, after
`aws s3 sync` of `s3://apheris-oslo-hackathon` completed. 4.7 GB synced. This file records what was
**observed on disk**, not what the task PDF or the bucket README promise — where they differ, the
disk wins and the difference is called out. Three such overclaims are recorded below.

Companion to [`scripts/fetch_hackathon_data.py`](../scripts/fetch_hackathon_data.py) (issue #5).
Provenance of each claim is marked: **[disk]** observed on the VM · **[abguard]** from `abguard`'s
help text · **[PDF]** from [`task.md`](task.md) · **[inferred]** our arithmetic or reading, not a
source.

---

## 1. `hackathon-data/` — the organisers' bucket, fully synced

4.7 GB. Sizes **[disk]**.

| Folder | Size | What is usable | Verdict |
|---|---|---|---|
| `her2-trastuzumab/` | 6 MB | 524,346 CDRH3 variants with FACS high/med/low classes, plus `trastuzumab_her2_spr_all_768.csv` — **768 SPR rows, 190 with a real K<sub>D</sub>** (0.0234–13,863 nM). Trastuzumab itself appears 8×. | **The only data that maps to a judged axis.** Affinity ranking lives here, and those 8 wild-type rows are the baseline every design is scored against. |
| `zenodo-18390239-ab-ag-complexes/` | 560 MB | ipTM matrices, top-model accuracy, replica RMSD for 106 cognate + 11,342 shuffled nanobody–antigen pairs | **Calibration only.** How much to trust ipTM *before* ranking on it. See §2 — this is where the usable cross-class comparison lives. |
| `sigma2-ab-ag-champloo/` | 1.7 GB | Per-replica AF3 / Chai-1 confidence archives, plus a **29-pair SPR supplement** | **Much narrower than it looks.** See §2 — pLDDT exists for 123 systems only, and the README overclaims. |
| `zenodo-10831512-trastuzumab-ngs/` | 2.4 GB, **still zipped** | Clonotype-split train/val/test of the FACS set, small-data splits, shanehsazzadeh 198 binders with log-affinity | Ready-made splits if we train an affinity model. **Clonotype-split matters**: a split we pick ourselves leaks near-duplicate CDRH3s across folds and flatters the model. |

### The SPR number is not a source conflict

Issue #5 quotes both "190 with SPR affinities" and "SPR affinities (768 variants)". Both are right
: the table has **768 rows**, of which **190 carry a measurable K<sub>D</sub>**. Nothing needs
resolving with the organisers.

**[verified in-repo]** — the table is now committed at
`data/bucket/extracted/hackathon-data/her2-trastuzumab/trastuzumab_her2_spr_all_768.csv`
(columns `cdrh3, vh_sequence, vl_sequence, kd_nM, binding_result`), so these were counted rather
than taken on report. The `binding_result` breakdown matters, and an earlier draft of this file got
it wrong by calling all 578 non-K<sub>D</sub> rows "measured non-binders":

| `binding_result` | rows | usable as |
|---|---|---|
| `quantified_binding` | 190 | affinity labels |
| `no_reportable_kd` | 460 | genuine negatives on our exact target |
| `inconclusive` | 104 | **nothing** — not a negative |
| `not_reported` | 14 | **nothing** |

The usable negative set is therefore **460, not 578**. Treating the 118 inconclusive/not-reported
rows as non-binders would poison any classifier trained on them.

The 190 span **0.0234–13,863 nM — 5.8 orders of magnitude**. Fit anything on log K<sub>D</sub>; a
model that looks good in linear nM is fooling us.

---

## 2. Confidence scores: what actually exists locally

This section exists because the bucket README is wrong about it, and the error points at the one
thing the dataset was built to answer.

### pLDDT: 6,150 predictions, one archive, 123 systems **[disk]**

pLDDT exists locally **only** in
`sigma2-ab-ag-champloo/af3_real_per_replica_confidence_metrics.tar.zst`: exactly
**123 systems × 50 diffusion samples = 6,150** `confidences.json` files, each with an
`atom_plddts` array — **per-atom, not per-residue** (e.g. 2,256 values for one system). Any
per-residue or whole-complex pLDDT has to be reduced from that array by us, and the reduction is our
choice, so it has to be stated wherever the number is quoted.

Those 123 systems are the **real, experimentally validated VHH–antigen pairs only**.

Nothing else carries pLDDT **[disk]**:

| Source | What it actually has |
|---|---|
| `chai1_all_per_replica_confidence_metrics.zip` (735,172 npz, 14,722 systems) | `aggregate_score`, `ptm`, `iptm`, `per_chain_ptm`, `per_chain_pair_iptm`, clash flags — **no pLDDT** |
| `topmodel_structure_accuracy.zip` | two columns, `ID,score` |
| `iptm_confidence_scores.zip` | ipTM matrices only |
| `rmsd_between_replicas.zip` | pairwise RMSD only |
| `her2-trastuzumab/*` (FACS, SPR) | sequences and measurements — **no structural confidence at all** |

### The README overclaims, and it costs us the dataset's central question

The bucket README says this folder holds "ipTM, pLDDT, PAE". That is true **only for the AF3 real
pairs**. The AF3 **shuffled** pairs and the Boltz-2 per-replica archive are listed in
`table_of_contents_10.11582_2026.owjnnp5q.csv` but **were not downloaded**. **[verified in-repo]**
from that file, now committed: shuffled = 162,691,164,832 B (**162.7 GB**), Boltz-2 =
1,699,040,788,429 B (**1.70 TB**), af3_real = 1.34 GB. Together **1.86 TB**. Do not start that
sync: it would fill the box. (An earlier draft said 152 GB for the shuffled archive, taken on
report; the figure above is read from the table of contents.)

**Consequence:** we **cannot** compare *pLDDT* between real and shuffled pairs from local data.
That is a narrower loss than it first looks, because the cross-class comparison itself **is**
available — the small `iptm_confidence_scores.zip` matrices summarise both classes, and the huge
archives are only their per-replica raw form. So the dataset's central question (does a
confidence score separate binders from non-binders) is answerable here; only the pLDDT-specific
version of it is not. Use:

- **ipTM**, full matrices, **both classes** — the comparison is available here.
- **Chai-1 `ptm`/`iptm`** across all 14,722 systems.

### What this corrects in our own docs

[`probe-findings.md` §1](probe-findings.md) concluded PAE is unobtainable from Nebius and that
Foundry `refold-score` is the only PAE-derived route. An earlier draft of this file claimed
`sigma2-ab-ag-champloo/` "lets us compute ipSAE/PAE-based scores instead of raw ipTM". **That was
too strong.** What is confirmed on disk is per-atom **pLDDT** for 123 real VHH–antigen systems.
Whether those same `confidences.json` files carry a **PAE matrix** was *not* verified in this survey
— AF3 output usually does, but "usually" is not a read. **Someone should open one
`confidences.json` and check for a `pae` key before any ipSAE plan depends on it.**

And even if PAE is there: 123 systems of VHH–antigen pairs, **none of them HER2 or trastuzumab**. It
is a calibration set for *how much to trust a confidence score*, not a source of scores for our
designs.

---

## 3. The best tested candidate, and the substitution prior it gives us

From `her2-trastuzumab/trastuzumab_her2_spr_all_768.csv` **[disk]**.

**`WGSQGFYAYD` — K<sub>D</sub> = 0.0234 nM (23 pM)**, the tightest binder in the SPR table. Same
VH/VL scaffold as the trastuzumab rows; only CDRH3 differs, so it is a genuine trastuzumab variant.

**Do not call it an improvement.** It appears **once** — a single measurement with no replicate.
**[verified in-repo]** the eight wild-type replicates are 0.0285, 0.0379, 0.0792, 0.123, 0.146,
0.152, 0.165, 0.178 nM. So `WGSQGFYAYD` does sit below all eight, but its margin over the best of
them is **1.22×**, while those eight replicates of a *single* molecule span **6.2×** among
themselves. A 1.22× edge from one unreplicated measurement, against a reference whose own spread is
five times larger, is not a detected difference. The safe claim is **"as tight as trastuzumab"**, and the
defensible pitch line is that the data contains no demonstrated affinity improvement, only
equivalence. It is also **absent from the 524,346-row FACS table** — it exists only in the SPR set.

Top three non-wild-type designs, and the eligibility check on each **[inferred]**:

| CDRH3 | K<sub>D</sub> (nM) | Substitutions vs `WGGDGFYAMD` | CDRH3 identity | Optimisation rule (<70%) |
|---|---|---|---|---|
| `WGSQGFYAYD` | 0.0234 | 3 — pos 3 G→S, 4 D→Q, 9 M→Y | 70% | **fails** |
| `WGSDGWYAMD` | 0.0608 | 2 — pos 3 G→S, 6 F→W | 80% | **fails** |
| `WGGQGFYAMD` | 0.090 | 1 — pos 4 D→Q | 90% | **fails** |

**All three would be rejected by the novelty filter.** That is not a defect in the data, it is the
point: the measured optima sit tight against the wild-type, and the challenge forbids us from going
there. Any design we submit is, by rule, in less-explored sequence space than the best thing anyone
has measured.

**The usable signal is the substitution pattern, not the sequences.** Across these three, the
positions that tolerate change are **3, 4, 6 and 9**; positions **1, 2, 5, 7, 8, 10** are conserved
(`WG··G·YA·D`) **[inferred]**. That is a reasonable prior for where to let a design model explore —
and note it is a prior about *tolerance*, drawn from only three sequences, not a constraint.

### This resolves the CDRH3 window question

The SPR table writes trastuzumab's CDRH3 as `WGGDGFYAMD` — **10 residues** — while our reference
([`1n8z_epitope_report.json`](../data/reference/epitope/1n8z_epitope_report.json)) has
`WGGDGFYAMDY`, **11**, and `Data/12-her2/her2_cdrh3.yaml` frees **B99–108**, also 10. An earlier
draft of this file flagged that as an unresolved contradiction. **It is not one.**

**[PDF]** the library has "up to 10 mutated **positions** in CDRH3". So the 10-mer is the library's
**mutable window**, with the terminal Y held fixed — not a CDR boundary. Structurally CDRH3 is the
11-mer ending at Y109, immediately before the conserved `WGQG` of FR4. The two definitions are
**compatible**, and the correct reading is:

- **B99–109 (11 residues)** — the structural CDRH3. What
  [`pipeline/thermostability.py`](../pipeline/thermostability.py) uses for the framework/CDR split.
  No change needed there.
- **B99–108 (10 positions)** — the design/mutation window. What the organisers' variant library,
  their SPR table and `her2_cdrh3.yaml` all use.

**[verified in-repo]** The SPR table settles this directly. Its `vh_sequence` column carries
`…YYCSR` **`WGGDGFYAMDY`** `WGQGTLVTVSS` — the 11-mer is present in the construct, at 1-based
position **99**, immediately followed by FR4's conserved `WGQGT` — while the `cdrh3` column holds
only the 10-mer. Two different windows in the same row of the same file.

**And the same check validated the parent our whole axis rests on.** The organisers' `vh_sequence`
(120 aa) and `vl_sequence` (107 aa) are **byte-identical** to the VH and VL that
[`pipeline/thermostability.py`](../pipeline/thermostability.py) derives from 1N8Z via the CH1/CL
start motifs. Two independent sources — a crystal structure and the organisers' own library
construct — agree exactly, so the parent sequences and the VH=1–120 / VL=1–107 domain boundaries are
confirmed, not assumed. It also means `common.load_reference_set()`'s "this repo ships no
trastuzumab sequence" is now wrong in **two** places.

The **≥4-substitution floor survives either way** **[inferred]**: on a 10-mer, 3 substitutions give
7/10 = 70.0%, which is *not* under 70% and fails; 4 give 60% and pass. Same floor
[`probe-findings.md` §3](probe-findings.md) derived for the 11-mer. Still unconfirmed, and still
worth a mentor's answer: **which window `abguard` itself uses** for its identity denominator.

---

## 4. RFD4-Proteina: three images, four usable models

**[disk]** Three images present (`apheris-rfd4-proteina-v0.3.0-…`), each exposing the same tasks:
`design`, `refold-prepare`, `refold-score`, `metrics`, `finetune`.

| Weight | Image tag suffix | For |
|---|---|---|
| `antibody-2026-10-30` | `…-antibody-2026-10-30` | VHH, paired VH/VL, **any CDR** on a fixed framework; antibodies for other targets |
| `her2-2026-11-07` | `…-her2-2026-11-07` | Trastuzumab CDRH3 redesign; fine-tuned on the Chinery FACS **high binders** |
| `her2-novel-2026-11-09` | `…-her2-novel-2026-11-09` | Mostly new CDRH3 loops, trained on **binder/non-binder pairs** |

The two HER2 weights give four models through one knob, **`--sequence-tsr-k` (lower = more varied;
default 4)** **[disk]**:

| Model | Weight | `--sequence-tsr-k` | Distinct | Known binders | Pass filter | Interface error |
|---|---|---|---|---|---|---|
| HER2 conservative | `her2-2026-11-07` | unset (4) | 7% | 21% | **0%** | 9.4 Å |
| HER2 balanced | `her2-2026-11-07` | 2 | 64% | 21% | **6%** | 9.1 Å |
| HER2 exploratory | `her2-2026-11-07` | 1 | 100% | 0.3% | **74%** | 9.1 Å |
| HER2 novel | `her2-novel-2026-11-09` | unset | 90%¹ | 4% | **86%** | 6.8 Å |
| Antibody (untuned) | `antibody-2026-10-30` | unset | 77%¹ | 0% | **100%** | 8.2 Å |

The **Distinct** column is new information from this survey; the other three columns match the table
in [`task.md`](task.md) §1 exactly, which is a useful cross-check that the survey and the PDF
describe the same measurements.

¹ **[inferred]** — these two cells were merged in the survey output, so the 90%/77% are read as
*Distinct* by column position and the remaining values taken from the PDF. Low stakes, but not
directly observed.

### This is now the third independent confirmation of the generation-weight problem

`her2-novel-2026-11-09` passes the novelty filter **86%** of the time with the **best** interface
error (6.8 Å). `her2-2026-11-07` balanced passes **6%**. Yet
[`pipeline/03_generate.py:112`](../pipeline/03_generate.py) `pick_weights()` returns
`her2-2026-11-07` for the optimisation track, and `pipeline/README.md` documents the run as
`--sequence-tsr-k 2`, i.e. **balanced — the 6% arm**, on one shared H100 against a 15:30 cutoff.
[`decision-log.md`](decision-log.md) [10:55] and [`tools-apheris.md`](tools-apheris.md) both already
say to use `her2-novel`. **The code is the outlier and should be changed by its owner** (W3,
issue #7/#8). Not touched here.

### The general checkpoint is not usable out of the box

**[disk]** `release-2026-10-19` is **not** a separate image, and its weights are not extracted —
`~/weights-release` does not exist. Using it means copying weights out of an older image by digest,
then running a design image with `-v ~/weights-release:/release:ro --data-path /release`. And
`docker images --digests` shows **no local digest** for that sha256, so it may need a pull.

Only the monomer, miniprotein, enzyme, ligand and DNA tasks need it. **None of those is our task**,
so this is a "do not spend time here today" note rather than a gap. Own checkpoints can also be
fine-tuned (`module-run finetune --task-mix … --checkpoint …`).

---

## 5. Folding models — all eight present, with the exact `--model` labels

**[disk]** The label strings matter: they are what `refold-score` is passed, and guessing one costs
a job.

| Model | Image | `--model` label | Template |
|---|---|---|---|
| Boltz-2 | `apheris-boltz-v1.3.0-boltz2` | `boltz2` | Yes |
| OpenFold3 OpenBind | `apheris-openfold3-v1.3.0-of3ob` | `openfold3-of3ob` | Yes |
| OpenFold3 preview 2 | `apheris-openfold3-v1.3.0-of3p2` | `openfold3-of3p2` | Yes |
| Protenix v2 | `apheris-protenix-v1.3.0-v2` | `protenix-v2` | Yes |
| Protenix v1 | `apheris-protenix-v1.3.0-v1-default` | `protenix-v1` | Yes |
| Mol-1 | `apheris-mol1-v1.3.0-base` | `mol1-base` | Yes |
| Boltz-1 | `apheris-boltz-v1.3.0-boltz1` | `boltz1` | **No** |
| ESMFold2 | `apheris-esmfold2-v1.4.0-release` | `esmfold2-release` | **No** |

Note OpenFold3 is **two** images, not one — the PDF's single "OpenBind, preview 2" row is two
selectable weights. Support images `apheris-data-v1.1.3`/`v1.2.0` and `apheris-msa-v1.1.0` are also
present.

**For binders, prefer a template model** — it folds the design against HER2 rather than unguided,
which is why [`task.md`](task.md) warns off ESMFold2 for this purpose.

### A ranking constraint we did not have before

**[disk]** Two practical notes from the Foundry docs:

1. The refold adapter **rejects ligand and DNA** tasks — those stop at design metrics.
2. On the HER2 example the **`pass` column stays empty** (the input fixes HER2 and the framework
   *relatively*, not absolutely), so rank on `min_ipae`, `iptm` and `binder_plddt`
   **within a single folding model**.

That last clause is a real constraint on [`pipeline/05_filter_rank.py`](../pipeline/05_filter_rank.py)
and is **not currently enforced**: `rank_candidates()` min-max normalises each score across the whole
candidate set, so folding two batches with different models and ranking them together silently
compares numbers that are not comparable. Either fold every ranked candidate with **one** model, or
rank within model and merge afterwards. Belongs to the ranking harness (#9) / score tables (#14),
flagged not fixed.

---

## 6. Tooling and in-flight work (outside the bucket)

All **[disk]**.

- **`rfd4/`** — the full Apheris tutorial: 18 docs, `Tutorial.html`, example inputs.
  **`rfd4/12-her2.md`** is the one that matters (the four HER2 weights with measured trade-offs);
  `18-vm.md` is the "run on your hackathon VM" entry point.
- **`Data/12-her2/`** — a *working* RFD4 input, already built: `her2_cdrh3.yaml` +
  `her2_fv_1n8z.cif`. Trastuzumab Fv on HER2 domain IV (1N8Z), CDRH3 **B99–108** free, 4 HER2
  hotspot atoms, everything else sequence- and geometry-fixed. (On the 10-vs-11 window, see §3.)
- **`josef/Scripts/run-her2.sh`** — complete `design → refold-prepare → Boltz-2 → refold-score`
  pipeline. A 4-design smoke run with `her2-novel-2026-11-09` was on the GPU at 11:22 UTC, 100%
  utilisation.
- **`lluis/`** is empty. **`foundry-assistant/`** is an unrelated side project — and its
  `models/` holds two small local LLMs (`qwen2.5-0.5b-*.gguf`), **not** protein models. Ignore it
  today.
- **All 19 Foundry Docker images are pre-pulled.** `abguard` is at `~/.local/bin/abguard`.

---

## 7. Three findings that change the plan

### 7.1 `abguard` resolves open questions #1–#3. Read its help text, not the PDF.

**[abguard]** A design must differ from trastuzumab and from every known CDRH3 by **≥3 mutations in
CDRH3 if it is a trastuzumab variant** (≥70% identity), or **≥2 if it is de novo**.

- [`task.md` §3 Q1](task.md) — "at least 2" vs "strictly more than 2". **Settled: ≥3 for
  optimisation.** `common.HARD_LIMITS["min_point_mutations_opt"] = 3` was right.
- [`task.md` §3 Q2](task.md) — **settled: ≥2, against trastuzumab.**
- [`task.md` §3 Q3](task.md) — the novelty reference set. **Settled, better than hoped:** `abguard`
  **ships its own reference DB** (`abguard_cdrh3.parquet`), so the gate runs out of the box.

**Correction this forces on our own work:** issue #5 and PR #17 record an **[inferred]** result —
524,346 + 717 = 525,063, the corpus size in #12 — with the advice to concatenate those tables and
assert it. The arithmetic still holds as a *description*, but the advice is now unnecessary and
mildly dangerous: assembling a second corpus would be an unvalidated reimplementation of a gate
`abguard` already owns, and **[PDF]** `abguard` decides.

### 7.2 `abguard` enforces something the PDF never mentions: LAP liabilities

**[abguard]** It reports sequence liabilities against the LAP reference (PLOS Comput Biol 2024).
Expected submission schema:

```
sequence_id, kind, heavy_sequence, light_sequence, design_description
```

split on `kind ∈ {vhh, scfv, paired}`.

**Run `team-validate` and `liability-report` early.** A liability flag that first appears at 17:50
costs designs. This is a *different* list from `LIABILITY_MOTIFS` in
[`pipeline/04_score.py`](../pipeline/04_score.py), which came from
[`hackathon-brief.md`](hackathon-brief.md): ours is a local prompt-to-look, `abguard`'s is a gate.
Where they disagree, `abguard` wins.

### 7.3 The strategic hole is thermostability, and it decides the ranking

Teams are ranked on **S-tier count first** **[PDF]**, and S-tier needs **all three** improved.

| Axis | Status |
|---|---|
| 2 — epitope | **nearly free in optimisation.** CDRH3-only redesign on a fixed 1N8Z framework preserves the epitope by construction. |
| 1 — affinity | **covered.** SPR table + 524k FACS classes. Though see §3: the data contains no *demonstrated* improvement over trastuzumab. |
| 3 — thermostability | **zero provided data, zero model support** ([`probe-findings.md` §4](probe-findings.md)). |

A CDRH3-only variant will **tie or regress** on Tm, and **[PDF]** "ties and regressions are hollow".
That caps the optimisation track at **A-tier however good the binding is**.

**The lever [inferred, worth a mentor's confirmation]:** the novelty rule constrains **only CDRH3**.
Framework and other-CDR mutations are unrestricted, so thermostabilising **framework** mutations are
legal and are the only route to S-tier in the optimisation track.

Separately, **VHHs are intrinsically more thermostable** than a trastuzumab Fab/scFv, so a de novo
VHH gets axis 3 close to free — but must win axes 1 and 2 the hard way, and
[`probe-findings.md` §4](probe-findings.md) notes de novo + VHH has no model-based stability signal
at all. Note also that `antibody-2026-10-30` is the only weight that can redesign **CDRs other than
CDRH3** (§4), which is the other unrestricted direction.

---

## 8. What §7.3 means for the thermostability axis as implemented

A limitation of [`pipeline/thermostability.py`](../pipeline/thermostability.py) (issue #10), written
down rather than left implicit.

`framework_mutations` counts substitutions outside the CDRs relative to trastuzumab, and the module
says to drive it to zero. That is a **destabilisation-risk** term: trastuzumab's framework is already
humanised and already stable, so drift away from it is on average downhill.

But **S-tier requires Tm to *improve*, not to be preserved.** Zero framework mutations means
Tm ≈ baseline, which is a tie, which scores nothing. So the term is:

- **right** for screening out designs that wandered off a stable framework by accident;
- **wrong** as the thing to maximise, because maximising it selects for exactly the designs that
  cannot clear axis 3.

It is also blind to *which* substitution was made — every framework substitution counts as 1
regardless of identity or burial, so a known stabilising mutation and a random destabilising one
score identically.

**Use it as a liability filter, not as the axis-3 score.** A real axis-3 claim needs *targeted*
stabilising mutations with a stated reason per mutation, and since nothing on the platform predicts
Tm, that reason comes from the literature (germline reversion, consensus substitution,
proline/disulfide engineering) and is argued in the pitch, not computed.
[`probe-findings.md` §4](probe-findings.md) stands: weight axis 3 as our weakest-evidence axis and
say so. Judgment is 40%.

---

## 9. Resolved by this survey, and still open

**Resolved:** the SPR 190-vs-768 "conflict" (§1) · the CDRH3 10-vs-11 window (§3) · the novelty
reference set, mutation floors and de novo CDRH3 rule (§7.1) · which `--model` label each folding
model takes (§5) · where pLDDT does and does not exist (§2).

**Still open:**

1. **Does `confidences.json` in the AF3 real archive carry a `pae` key?** Open one and look (§2).
   Any ipSAE plan depends on it, and it was not verified.
2. **Which CDRH3 window does `abguard` use for its identity denominator** — the 11-residue loop or a
   wider one? [`probe-findings.md` §3](probe-findings.md)'s floor depends on it, and shipping the
   reference DB does not by itself answer it (§3).
3. ~~Which ipTM column is the AF3 one?~~ **Answered:** `sigma2-ab-ag-champloo/spr-supplementary/`
   `spr_table_s1_pairwise.csv` carries `pair_type`, `spr_outcome`, `kd_nM` and **`af3_iptm`** in the
   same row — a measured label and the confidence score together, i.e. a direct ROC. Computing the
   454/21 split is still a useful cross-check (`fetch_hackathon_data.py`, `derived` expectation).
4. **Cross-model score comparability in stage 05** (§5) — fold all ranked candidates with one model,
   or rank within model and merge.
5. **Does the participant guide's "include Apheris' OpenFold to qualify" condition still hold?**
   Unchanged from [`task.md` §3 Q8](task.md); the PDF states no such requirement.
