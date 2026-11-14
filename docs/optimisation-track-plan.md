# Optimisation track — execution plan

Written 12:30. **Generation cutoff 15:30 (workplan). That is 3h00m of build time, not more.**
Submission 18:00.

State when this was written: `data/` empty, `designs/submission.csv` header-only, decision log says
"We have not run anything." The 11:15 "launch long jobs first" milestone was missed. Everything
below is ordered so the queue waits are paid in parallel instead of in series.

> ## STATUS — verified on the VM at 13:05, supersedes the assumptions below
>
> Full detail in [`docs/data-inventory.md`](data-inventory.md). What changed:
>
> Confirmed, so the plan stands. `her2-novel-2026-11-09` is on the box, and one image holds every
> weight (`--model her2-novel|her2-exploratory|…`) — no image juggling. OpenFold3 (incl.
> OpenBind), Protenix v2, Mol-1, ESMFold2 all present. Josef's smoke run already produced 4 designs
> in 2m37s, so the command is proven. The antifold/proteinmpnn fallback is not needed.
>
> Generation is running. Launched 12:53 from `~/mark/generate.sh`: 200 × `her2-novel` seed 1,
> then 64 × `her2-exploratory` seed 2. The H100 was idle at 0% until then. Samples are written
> incrementally, so whatever exists at 15:30 is the batch — no need to kill the job to harvest.
>
> `abguard` works. Resolved 13:10, and it was never missing: it is a `uv` tool at
> `~/.local/bin/abguard`, on `PATH` in a login shell only, so `ssh host 'abguard'` and any script
> without `-l` report "command not found". Use `bash -lc`, or the gate,
> `bash pipeline/filter/gate.sh`. Control run 13:10, gate verified end to end 13:20. Nobody needs
> to go and ask the Apheris team. See [`abguard.md`](abguard.md). (`foundry-toolkit module list`
> still fails on a missing login, and that one is still harmless — the images are local.)
>
> Step 2 is largely done for us. `~/Data/12-her2/` ships `her2_fv_1n8z.cif` plus a fully
> commented `her2_cdrh3.yaml`: CDRH3 is chain B 99–108, HER2 is split into chains C/D at the
> unresolved 581–590 loop, and four 1N8Z epitope hotspots are already annotated. Lluis's job
> shrinks to expanding those into the full 4.5 Å contact list in both numberings.
>
> The eligibility floor. Trastuzumab CDRH3 is `WGGDGFYAMD` — 10 residues. The floor is ≥ 3 CDRH3
> mutations from trastuzumab and from all 610,109 known CDRH3s, and we aim at ≥ 6; see the 13:20
> note below. The FACS table ships a precomputed `edit_distance` column, so the subset we can
> actually submit is `df[df.edit_distance >= 6]`.
>
> **Baseline to beat: KD 0.152 nM** (wild-type trastuzumab, row 1 of the SPR table).
>
> Lever 4 got much stronger and much cheaper — see the revision in that section below.
>
> Free epitope signal. The design metrics CSV already returns `hotspot_obedience` per design,
> before any refold, plus interchain H-bond / salt-bridge / hydrophobic counts and clash fractions.

Scope: optimisation track only — point mutations on trastuzumab, CDRH3 redesign. De novo stays
with Danielius on `ws3-generate`; this plan does not touch it.

The one sentence that determines everything: on this track a design is valid only if its CDRH3 has
≥ 3 mutations from trastuzumab *and* from all 610,109 known CDRH3s — and the HER2 fine-tuned weights
that find real binders fail that novelty filter 94–100% of the time (`docs/tools-apheris.md`). So we
filter before we rank, and we generate from `her2-novel-2026-11-09`. Measured on batch 1: 70.5%
eligible, and 3–4 mutations from trastuzumab is a dead zone (0/12) because those designs collide
with the FACS screen. Target ≥ 6. See [`abguard.md`](abguard.md).

Changed 13:20: the plan previously assumed a < 70% CDRH3 identity bar and > 2 point mutations from
any provided antibody; `abguard` never computes an identity figure — identity only picks the track —
so the real bar is ≥ 3 CDRH3 mutations from trastuzumab and from all 610,109 known CDRH3s. Filter
before ranking still holds, and holds harder.

---

## Corrections to the interface-prep shape W2 posted in Slack

The Slack shape was: antigen structure via BioPython → interface via ANARCII → input for
RFD4-Proteina or BindCraft → filter on solubility, pLDDT, ipSAE. Four changes for this track:

1. Drop BindCraft. It designs de novo binders from scratch. On the optimisation track we are
   mutating a known Fab on a fixed framework — that is RFD4-Proteina `design` with the HER2
   weights, which redesign CDRH3 only. BindCraft output would be classified de novo by `abguard`
   and a design is never moved between tracks.
2. ANARCII does not find the interface. It is an antibody *numbering* tool: it gives us IMGT
   numbering and therefore the exact CDRH3 span to mark as the redesign region. The
   epitope/paratope contact list comes from BioPython `NeighborSearch` on the trastuzumab–HER2
   complex. Two separate jobs, both needed.
3. ipSAE is not the ranking metric. The organisers rank this exercise on `min_ipae`, `iptm`,
   `binder_plddt` from `refold-score`, and the pass column stays empty (`TASK p6`). Keep ipSAE as a
   supporting column, never as the gate.
4. Thermostability is missing from that shape and it is one third of the tier. S-tier needs
   affinity *and* epitope *and* thermostability. On this track the designs are point mutations, so
   `stab-ddg` applies directly — it is the cheapest thermostability evidence we will get. It has a
   ~12 min first call, so it gets launched in step 1, not at 15:00.

---

## The levers that decide whether we place

Steps 0–6 below are table stakes: every team will run the generator and sort by a confidence score.
These are where the placement comes from. **If time forces a cut, cut generation volume, not
these.**

### Lever 1 — rank on measured affinity, not on structural confidence

The organisers gave us 454 VHH–antigen pairs measured not to bind, and told us 21 of them score
AlphaFold3 ipTM ≥ 0.7. That is not trivia; it is them telling us the metric everyone else
will rank on admits false positives at the threshold everyone else will use. Their own interface
error for the HER2 weights is 6.8–9.4 Å.

So: train a CDRH3 → affinity-class model on the 524,346 measured FACS variants and make it the
primary ranker. `zenodo-10831512-trastuzumab-ngs` ships ready-made train/val/test splits, so there
is no excuse for an uncalibrated model.

- Baseline, ~40 min: ESM-2 embeddings of the CDRH3 (or one-hot, it is a fixed-length loop) →
  logistic regression / small MLP on the three affinity classes. Report held-out test accuracy and
  the confusion matrix. A simple model with an honest test number beats a clever model with none.
- **The test metric must be computed on the ≥ 6-mutation subset, not the full test split.** This is
  the difference between a number that means something and a number that flatters us. Eligibility
  needs ≥ 3 CDRH3 mutations from trastuzumab and we are aiming at ≥ 6 — and the library spans up to
  10 mutated positions, so the full test split is dominated by low-mutation variants that are easy
  to call and that we are not allowed to submit. Accuracy on the whole split will look great and
  tell us nothing about our actual candidates. Report both, lead with the restricted one, and expect
  the restricted number to be substantially worse. If it is near chance on that subset, the model is
  not a ranker and we fall back to the structural triple and say so.
- Then validate it against the SPR set, and lead the pitch with that number. The
  `her2-trastuzumab` folder has 768 variants with measured SPR affinities (~190 with measurable
  affinity, per `TASK p5`) from the same study. Train on the FACS classes, then test whether the
  model ranks those SPR affinities correctly. Report Spearman ρ on held-out SPR.

  This is the highest-value 30 minutes available to us today, and here is why: it is a
  **cross-modality validation**. We train on a cheap, noisy, high-throughput assay (FACS classes)
  and test on the expensive, precise assay we are actually judged on (SPR). If ρ is decent, we can
  say something no other team will be able to say:

  > "Our ranker was validated against 190 independently measured SPR affinities. ρ = `[FILL]`. We
  > know it transfers from the screen to the assay, because we tested it."

  That converts the pitch from *"we have a method"* to *"we have a measured ranker."* It is also a
  genuine falsification test: if ρ is near zero, the affinity model does not belong in the ranking,
  we drop to the structural triple, and we report the negative result — which is still a
  stronger Judgment answer than an unvalidated model.
- Then calibrate the structure filter against the true negatives: run our refold pipeline on a
  sample of the 454 non-binders and find the `min_ipae` / `iptm` threshold that actually excludes
  them. Now our cutoff is a measured operating point instead of a guess.

Honest limit, state it in the pitch rather than being caught on it: the 524k library varies CDRH3
only, up to 10 positions, so the model is trustworthy inside that mutational neighbourhood and
not outside it. Optimisation-track designs live inside it; de novo loops do not. Flag any candidate
whose loop falls outside the training distribution and score it structurally instead.

### Lever 2 — design into the eligible region instead of sampling and praying

Eligibility needs ≥ 3 CDRH3 mutations from trastuzumab and from all 610,109 known CDRH3s, and 3–4
mutations is a dead zone, so the eligible region starts above the floor. Rather than generating
broadly and discarding 14–26%, use the affinity model from lever 1 in the loop: enumerate or sample
CDRH3 variants at ≥ 6 mutations, score them with the model, keep the top band, and only then spend
GPU on refolding those. Generation becomes a proposal mechanism and the measured data becomes the
selector.

### Lever 3 — we cannot reach S-tier on CDRH3 alone. Fix that now.

Teams are ranked on S-tier count first, S-tier is 3 of 3, and one of the three is
thermostability. The HER2 weights redesign CDRH3 only, and loop mutations are a weak and
unreliable lever on Tm — they can help (removing an aggregation-prone or flexible motif does raise
stability) but more often they cost it. So a CDRH3-only pipeline leaves one third of every tier to
chance, which makes S-tier a coin flip however good the binding is. Deliberate stability work
outside the loop is the only reliable lever we have.

*(Earlier drafts of this plan said CDRH3-only gives "no lever at all." That was too strong — loop
changes do affect stability. The conclusion is unchanged: don't rely on it.)*

Two consequences:

1. **Pair every CDRH3 redesign with explicit stability engineering outside the loop.** That means
   `antibody-2026-10-30` (the only weight that can touch anything other than H3) or hand-specified
   framework mutations with literature support. This also helps the mutation-count requirement, so
   it costs us nothing on eligibility.
2. Format is a thermostability decision — but VHH is a trap on this track. VHH, scFv and Fab
   differ materially in measured Tm and we get to choose, so choose deliberately and write the
   reason in the decision log. But trastuzumab binds HER2 through a paired VH+VL interface. Cut
   it down to a single-domain VHH and we are very likely to lose most of the affinity we are being
   judged on — trading one axis for another and landing at the same tier. **Stay in scFv or Fab**,
   which keep both chains, unless someone has a specific reason not to. A disulfide-stabilised
   construct is worth considering: `abguard` checks for *unpaired* cysteines, so an engineered pair
   is allowed.

**Verify before relying on it:** the workplan describes `stab-ddg` as giving binding ddG for
named point mutations. Binding ddG is not folding stability, and thermostability is measured
directly by Adaptyv. If `stab-ddg` is binding-only, our thermostability evidence has to come from
somewhere else (a folding-ddG predictor, FoldX if licensed, or structure-based packing arguments) —
so whoever runs it first checks what it actually returns and says so in Slack. Do not let a
binding-ddG column get labelled "thermostability" in the submission table; that is exactly the kind
of thing a judge asks about.

### Lever 4 — a learned structural filter

Revised 13:05 after opening the files: this got stronger and about 1000× cheaper than planned.

Forget the 1.8M complexes and the per-replica archives. `iptm_confidence_scores.zip` inside
`zenodo-18390239-ab-ag-complexes/` unpacks to three 91×91 all-vs-all ipTM matrices —
`af3_matrix_clean.csv`, `boltz2_matrix_clean.csv`, `chai1_matrix_clean.csv` — 150 KB in total.

Rows and columns are antigen PDB ids, so the diagonal is a cognate (real) pair and every
off-diagonal cell is a non-cognate pair: ~91 positives and ~8,190 labelled negatives, with the
same pairs scored independently by all three models. Everything this lever needs, openable instantly.

*(The per-replica archives are 162 GB and 1.7 TB. Do not sync them — they are the raw form of what
these matrices already summarise, and they would fill the disk.)*

Observed values for antigen `3OGO`:

| Pair | Type | AF3 | Boltz-2 | Chai-1 |
|---|---|---|---|---|
| 3OGO–3OGO | cognate | 0.89 | 0.93 | 0.18 |
| 3OGO–3RJQ | non-cognate | 0.12 | 0.64 | 0.13 |
| 3OGO–4M3K | non-cognate | 0.16 | 0.90 | 0.24 |

Three things fall out of that, and they are better than the 454-negatives argument we had:

1. Boltz-2 assigns 0.90 to a pair that does not bind.
2. Chai-1 assigns the genuine cognate pair 0.18 — it would throw away the right answer.
3. The three models disagree violently on identical input. So the plan's "second opinion from a
   different predictor" step must *report* disagreement, not average it away. Agreement between two
   models is only reassuring if we have shown the models agree on things we know the answer to.

And the clincher, from `sigma2-ab-ag-champloo/README.txt` — the dataset's own paper is:

> "Structural Plausibility Without Binding Specificity: Limits of AI-Based Antibody-Antigen
> Structure Prediction Confidence Scores" — Smorodina et al., incl. Greiff.
> DOI 10.64898/2026.03.02.709004

Our central argument is the thesis of the organisers' own paper. We are not inventing a critique
of confidence scores, we are applying the published result whose data they handed us. Cite it.

Also in there: `spr-supplementary/spr_table_s1_pairwise.csv` has measured `pair_type`
(cognate/non-cognate), `spr_outcome`, `kd_nM` and `af3_iptm` in the same row — a direct,
honest ROC on measured ground truth. Use it as the headline figure if the matrices prove awkward.

**So stop thresholding ipTM and learn the filter instead.** Per-sample scores across 50 samples means
we have a *distribution*, not a point estimate. Features per pair, all cheap and tabular:

- mean / std / max / 90th percentile of ipTM, pLDDT, PAE across the 50 samples
- fraction of samples above a given ipTM
- cross-model agreement — does AF3 agree with Boltz-2 and Chai-1 on this pair?
- the spread itself: a confident-but-inconsistent ensemble is a different animal from a
  confident-and-tight one

Train a gradient-boosted classifier on cognate vs non-cognate. No GPU, no queue — it is pandas and
sklearn on tabular data, ~45 minutes. Report held-out AUC and the operating point we choose.

Why this is the strongest version of our argument:

1. It fixes the hole in our current ipTM story. We were leaning on 454 negatives of the wrong
   modality. This is ~11,448 labelled pairs with full sampling distributions — 25× the data, and
   an actual trained discriminator rather than a hand-picked cutoff.
2. It is properly differentiating. "We replaced the confidence threshold with a discriminator
   trained on 11,448 labelled complexes, and here is its held-out AUC" is a sentence no other team
   will have.
3. It gives us two orthogonal evidence streams: sequence→affinity from 524k measured variants,
   and structure-ensemble→binds from 11,448 labelled complexes. When they agree, we rank high with
   confidence. Where they disagree, that is our uncertainty column — and disagreement we can
   point at is worth more to a judge than a single confident number.

Honest limit, state it: those are nanobody–antigen cognate/non-cognate pairs. That answers *"does
this look like a real complex?"*, not *"is this a better binder than trastuzumab?"* So it stays a
filter, never the ranker. Which is exactly the role we assigned structural confidence anyway —
the two levers are consistent, not competing.

Cheap extension if the queue allows: apply the same ensemble logic to our own designs. Refold the
top ~10 candidates with 5 seeds instead of 1 and feed the distribution through the same classifier,
rather than trusting a single refold. Do this only for the shortlist, and only after 15:30 when
generation has stopped freeing up queue slots.

### Two more cheap wins, in priority order

- A quantitative epitope-overlap number. Epitope preservation is one of three judged axes and
  most teams will hand-wave it. Contact map of each refold vs the 1N8Z contact list → a single
  `epitope_overlap_frac` per design. It is ~20 lines of BioPython once the refolds exist, and it
  turns a judged axis from an assertion into a column.
- A negative control in the submission. Deliberately include one design our pipeline ranks
  *low*, flagged as such, and say so: "we predict this one fails." If it does fail, our ranker is
  validated prospectively by the organisers' own measurements. Costs one of 20 slots and buys a real
  experiment. *(W5's call — it trades a slot for evidence. Discuss, don't decide alone.)*

### What this means for the 40% that is not science

Judgment 40%, Execution 20%, User fit 20%, Path to value 20%. The three levers above *are* the
Judgment answer — "we calibrated our filter on 454 measured non-binders and found ipTM ≥ 0.7 admits
21 of them, so we rank on a model trained on 524k measured variants instead" is a better answer than
any ipTM we could report. W5 should be drafting that narrative from the moment lever 1 has a test
number, not at 17:00.

---

## If we fall behind — cut in this order, and decide out loud

This plan asks six people who have run nothing yet to do epitope prep, a novelty set, two generation
arms, a scoring pipeline and a trained affinity model in under three hours. Something will be cut.
Deciding now which, in advance and in writing, is worth more than hoping it all lands.

**The floor — minimum viable submission.** Designs from `her2-novel-2026-11-09`, `abguard`-eligible,
refolded with OpenFold3 against the 1N8Z template, ranked on `min_ipae` / `iptm` / `binder_plddt`
with full provenance. That is a legitimate submission that answers the task. **Protect this above
everything else.** If at 15:00 we have only this, we are fine.

Then, in strict priority order, each one upside on top of the floor:

| Priority | Thing | Drop it if | Costs us |
|---|---|---|---|
| 1 | Novelty filter — `pipeline/filter/gate.sh` (abguard); `novelty.py` cancelled 13:20 | never — it is eligibility, not upside | the submission itself |
| 2 | Epitope overlap column | not done by 15:30 | one judged axis of evidence |
| 3 | Affinity model (lever 1) | restricted-subset metric is near chance, or not trained by 14:30 | the Judgment headline — fall back to the structural triple and say why |
| 4 | Stability work outside the loop (lever 3) | not started by 15:00 | realistic S-tier chance; we aim at A-tier deliberately |
| 5 | Second-opinion refold (Protenix) | queue is congested | one uncertainty check |
| 6 | Diversity arm (`--sequence-tsr-k 1`) | first | nothing much — it is the cheapest cut |

**Cut from the bottom.** The diversity arm goes first, the novelty filter never goes. And whatever
we cut gets one line in `docs/decision-log.md` saying we cut it and why — a judge reading "we chose
to spend our remaining hour on X instead of Y" sees judgment; a judge finding an empty column sees
an oversight.

## Step 0 — now, 12:30, before anything else (15 min, W1)

Nothing in this step waits on anything. Do it in three terminals at once.

```bash
# A. the organisers' own HER2 script — they shipped one, do not rewrite it
aws s3 sync s3://apheris-oslo-hackathon/rfd4-proteina/docs/ ~/rfd4
open ~/rfd4/Tutorial.html        # Hackathon VM tab; 18-vm.md first

# B. confirm the weights are actually on the box
foundry-toolkit module list | tee docs/vm-modules.txt

# C. find the gate — login shell, or ~/.local/bin is not on PATH
bash -lc 'which abguard && abguard --help' | tee docs/abguard-help.txt
```

Post the exact working `design` command in Slack the moment it runs. Nobody rediscovers it.

Then launch a throwaway `design` job on the tutorial's example input immediately, defaults, one
seed, before our own input exists. `rfd4-proteina` first call is ~6 min; we need to know the command
is correct while the input is still being prepared, not after. Also fire `stab-ddg` once on
wild-type trastuzumab to warm it (~12 min first call).

Exit criterion: one RFD4-Proteina `design` job has returned *something*, and `abguard --help` is in
the repo.

**This step is load-bearing for the entire plan, and it is now verified.** Josef's smoke run
returned 4 designs in 2m37s on `her2-novel`, so the weights are on the box and `design` accepts our
annotation format. `foundry-toolkit module list` fails on a missing login, which turned out not to
matter — every image is already pulled locally. The fallback below is kept for the record rather
than because we expect to need it. If the HER2 weights
are missing or `design` rejects our input, the fallback is loop redesign on the fixed framework with
what *is* available — `antifold` or `proteinmpnn` (2 min first calls, per the resource map) scoring
and proposing CDRH3 sequences on the 1N8Z backbone, then the same filter-and-score pipeline
downstream. Less powerful, entirely workable, and the rest of the plan is unchanged. **Find this out
at 12:40, not at 14:00** — and if it happens, find the Apheris team on site rather than debugging it
ourselves.

## Step 1 — the novelty set (25 min, CPU only, runs in parallel with step 0)

This is the gate that kills most of our output, and it costs no GPU and no queue. Build it first so
every later batch is filtered in seconds.

```bash
aws s3 sync s3://apheris-oslo-hackathon/data/her2-trastuzumab/ data/her2-trastuzumab/
aws s3 sync s3://apheris-oslo-hackathon/data/zenodo-10831512-trastuzumab-ngs/ data/ngs-splits/
```

Deliverable: `bash pipeline/filter/gate.sh`. `pipeline/filter/novelty.py` + `data/cdrh3-known.txt` —
cancelled 13:20, superseded by `gate.sh`: abguard's bundled reference already holds 610,109 CDRH3s
and its verdict is the one that counts. What `novelty.py` would have built, for the record: the
de-duplicated set of all 610,109 CDRH3s in abguard's bundled reference (the PDF's 524,346 FACS
variants plus the SPR set and trastuzumab), and a function that takes a candidate CDRH3 and returns
`(is_exact_duplicate, identity_to_trastuzumab, n_point_mutations)`. Our design must differ from
every one of them, and carry ≥ 3 CDRH3 mutations from trastuzumab.

While the file is open: the FACS data has three affinity classes. Pull the CDRH3s in the highest
class and keep them as a reference set — not as candidates (they are known binders, instant
rejection), but as the answer to "does our generated loop look anything like a measured binder?"
That comparison is a ranking signal we get for free, and it is a Judgment point in the pitch.

## Step 2 — target and CDRH3 span (40 min, W2, parallel with steps 0–1)

1. Structure. `1N8Z` — trastuzumab Fab bound to HER2 extracellular domain — via the RCSB MCP
   already on the VM. Into `data/target/`, provenance (accession, date, source) in
   `data/README.md`. This is also the template for every refold, which is the whole reason we
   beat an unguided fold.
2. Epitope/paratope. BioPython: parse the complex, `NeighborSearch` over heavy-atom pairs at
   4.5 Å, write every HER2 residue contacting the Fab and every Fab residue contacting HER2.
   Output `docs/epitope.md`, in PDB residue numbers and IMGT, per the workplan.
3. Numbering. ANARCII on the trastuzumab heavy chain → IMGT numbering → the exact CDRH3 start
   and end. Cross-check against the known trastuzumab CDRH3 (`WGGDGFYAMDY`) before trusting it.
4. Annotated input. Mark CDRH3 as the redesign region and the paratope residues outside H3 as
   fixed, in whatever annotation format `Tutorial.html` specifies for `design`. Hotspots = the HER2
   contact residues from (2).

Exit criterion: `docs/epitope.md` committed and one annotated CIF in `data/target/` that
`rfd4-proteina design` accepts. **Everything downstream blocks on this, so it is the thing to
escalate in Slack if it slips past 13:30.**

## Step 3 — generation, two arms (13:15 → 15:30 hard stop, W3)

| Arm | Weight | Setting | Why |
|---|---|---|---|
| Primary (~75% of compute) | `her2-novel-2026-11-09` | defaults | 86% novelty pass and best interface error in the organisers' table, 6.8 Å |
| Diversity (~25%) | `her2-2026-11-07` | `--sequence-tsr-k 1` (exploratory) | 74% pass; different loop distribution so we are not ranking one model's opinion |

**Do not run `her2-2026-11-07` conservative or balanced.** 0% and 6% novelty pass — those designs
are rejected before they are ever measured.

Rules: ≥ 3 seeds per arm, report the spread not the best run. One file per batch,
`designs/raw/opt-<owner>-<batch>.csv`, with weight, every setting and the seed written *inside* the
file. Batch 1 out by 13:15 even if the annotation is imperfect; batch 2 by 14:00 using what batch 1
taught us. **No new generation job after 15:30** — a job queued then may still be waiting at 16:00.

Reserve for later, not now: `partial diffusion` to refine the best batch-1 design, and
`inverse folding` for new sequences on a kept backbone. Both are cheap second passes if we have
time after 14:30; neither is worth delaying batch 1 for.

## Step 4 — filter, then score (from 13:30, W4)

Order matters and it is the organisers' own instruction: **filter before ranking.**

```
raw batch
  -> gate.sh             (step 1; ~1 min, local)         -> abguard: hard filters + novelty,
                                                            drops ineligible and duplicates,
                                                            records the track and the verdict
  -> refold-prepare
  -> predict  [OpenFold3, template = 1N8Z]                -> the ranking fold
  -> refold-score                                         -> min_ipae, iptm, binder_plddt
  -> predict  [Protenix v2, template]                     -> second opinion
```

- OpenFold3 is the ranking fold: it takes a template, and per `docs/tools-apheris.md` the prize
  condition plausibly requires Apheris' OpenFold in the pipeline (`TODO: confirm on site`).
- Not ESMFold2 for the ranking fold — it folds the target unguided, an unfair check for a
  binder. Cheap triage only.
- **Never report an ipTM from Boltz2 on Nebius**; that output has none. If an interface number from
  Boltz2 is needed, count cross-chain contacts in the mmCIF and label it as exactly that.
- Record the Nebius run id (`op-xxxx`) or Foundry job id in every row. Never resubmit a job — use
  `forge.py status`, and `forge.py resume` after a storage error.

Hard filters `abguard` enforces, so build to them: VHH/scFv/Fab (not IgG), ≤ 250 aa total, no
unpaired cysteines, numbering confidence ≥ 0.1.

## Step 5 — the other two axes (from 14:00, W4)

Affinity is one third of a tier. Both of these are needed for S-tier and both are easy to skip.

- Epitope preservation. For each survivor, check the refold's contact residues overlap the HER2
  epitope list from `docs/epitope.md`. Judged experimentally by competitive binding, so epitope
  drift is a lost property, not a rounding error. Column: `epitope_overlap_frac`.
- Thermostability. `stab-ddg` on the point mutations each design carries, against wild-type
  trastuzumab. Every submitted design needs a stated thermostability reason in its row — "no
  evidence" is a reason to rank it lower, not to leave the cell empty.
- Developability. At least one of Aggrescan 3D, SoluProt, NetSolP, or ProteinMPNN with soluble
  weights (the four the organisers name). Plus sequence liability motifs (deamidation NG/NS,
  isomerisation DG/DS, unpaired Cys, free Met, N-glyc NxS/NxT) across CDRH3.
- Any liability fix is followed by re-scoring binding. A fix that breaks the interface is not a
  fix.

## Step 6 — rank and submit (16:00 freeze, W5)

Up to 20 rows in `designs/submission.csv`, ranked. Rank on the organisers' triple
(`min_ipae`, `iptm`, `binder_plddt`), then break ties by: two predictors agreeing > one high score;
epitope overlap; thermostability evidence; developability clean.

**Prefer a design that plausibly moves all three axes over a design with the single best ipTM.**
Teams are ranked on S-tier count first — ten designs each improving one property lose to two
improving all three.

Every row: model, weight, settings, seed, run id. Anything that changed the ranking gets an entry
in `docs/decision-log.md`. That provenance is the 40% Judgment score.

---

## Owner split (6 people, optimisation track)

| Who | Step | First deliverable |
|---|---|---|
| Mark (W1) | 0 | working `design` command in Slack + `abguard --help` committed |
| Lluis (W2) | 2 | `docs/epitope.md` + annotated CIF by 13:30 |
| Abdelrahman (W3) | 1, 3 | `novelty.py` cancelled 13:20, superseded by `gate.sh`; batch 2 at >=6 CDRH3 mutations, a second seed, gated with `gate.sh` |
| Kevin (W4) | 4, lever 3 | score table per candidate; what `stab-ddg` actually returns |
| Danielius | lever 1 | affinity model with a held-out test number by 14:00, then the true-negative calibration |
| Josef (W5) | 6, lever 3 | ranked `submission.csv`, decision log, format/stability decision, pitch |

If we are optimisation-only, Danielius is freed from the de novo arm and lever 1 is his
workstream — it is pure CPU/local GPU work, it never touches the shared queue, and it is the
single highest-leverage thing anyone on the team can be doing between now and 15:30.

## Open items to resolve, not to guess

- Answered 13:20. The "at least 2" (`TASK p2`) vs "more than 2" (`TASK p3`, `p7`) ambiguity is
  settled by the tool: `abguard` requires at least 3 CDRH3 mutations for a trastuzumab variant, and
  every rejection message says so. No organiser needed. The binding constraint is not the parent
  anyway — it is distance from all 610,109 known CDRH3s, so we build to ≥ 6.
- Whether the OpenFold-in-pipeline prize condition is real. Ask on site; we satisfy it either way
  by using OpenFold3 as the refold model.
- Exact annotation format `design` expects for a fixed-framework CDRH3 redesign — from
  `Tutorial.html`, not from us.

## A note on repo convention

`docs/*.md` is W5 Josef's path under the workplan's path-ownership rule. This file was added from
outside that ownership — say so in Slack rather than letting Josef find it in a rebase.
