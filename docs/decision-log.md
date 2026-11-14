# Decision log

Judgment is 40% of the score, and the judges ask where each number came from. This file is the
evidence. One entry per decision that changed what we submit. Append, never rewrite.

Template:

```
## [HH:MM] <decision in one line>
Options considered:
Chose: ... because ...
Evidence: <model + version, score, seed, or the paper/AMASS query>
Confidence: low | medium | high — and what would change our mind
```

Source labels used below:
`TASK p<n>` = the official task description PDF, page n.
`MAP` = the hackathon resource map PDF (first-call timings, 12 Nov).
`RECIPES` / `SKILL` = the Nebius job client docs in the Slack folder.
`GUIDE` = the organisers' participant field guide on the event website (printable view). Older
than the task PDF: where they disagree, `TASK` wins and we say so.
`SITE` = the event website front page (schedule, FAQ, prizes, judging).

First measured result of ours: the **13:20** entry (abguard pass rate by CDRH3 mutation count).
Everything above it is reasoning from the sources, labelled as such.

## Authorship

Claude Code (Anthropic) is pre-installed on the team VM with credits from the organisers, and we
use it. So that the Judgment score is assessed on the right basis, authorship is explicit:

- The **13:20** and **13:25** entries, `docs/abguard.md`, and everything under `pipeline/` were
  written by **Claude Code, working as W1 under Mark's direction**. Where those entries say "I",
  it is the agent, not a team member. The measurements in them are real — run on the VM against
  the organisers' own `abguard` and our own batch 1 — and every number names the file it came from
  and a command that reproduces it.
- Entries before 13:20 are the team's, reasoned from the task PDF and the Slack material.
- The agent's two errors so far are in the record on purpose: a gate script that exited 0 on
  failure (caught and fixed before use), and a synthetic-probe recommendation that real batch-1
  data overturned within the hour (13:20, superseded by 13:25). Neither was caught by review —
  one by testing, one by better data. **Treat agent output as a strong draft that needs checking,
  not as a result.** `python3 pipeline/status.py --how` and `bash pipeline/filter/gate.sh` exist
  so any claim here can be re-derived in one command.
- Decisions deliberately **not** made by the agent, because they are ours: whether to enter the
  de novo track, what to generate next, and launching anything on the shared H100.

---

## [10:55] Enter both tracks, but build the optimisation track first

Timestamps on the first three entries are when the log was reseeded against the task PDF, not
when each point was argued.

Options considered:
1. De novo only — design a new VHH/scFv/Fab to the trastuzumab epitope.
2. Optimisation only — point mutations on trastuzumab.
3. Both, split effort.

Chose: **both tracks, with optimisation first and de novo running in parallel on W3's second
owner**, because:
- The prize fund (€3000) is split **equally** between the two tracks, €800 / €500 / €200 per
  track, so a track with fewer strong teams is worth the same as the crowded one (`TASK p9`).
  (The event website front page says "3,000 USD" instead; `TASK p9` is the later and higher
  authority, so we use €3000. The currency does not change the split or this decision.)
- Submissions in the two tracks are **evaluated independently**, and we may submit any
  proportion of each (`TASK p8`).
- We do not choose the track. `abguard` classifies each design by identity to the nearest known
  antibody, and **a design is never moved between tracks** — miss your track's criteria and you
  are rejected, not reclassified (`TASK p3`). So "which track" is a consequence of how we
  generate, which means we have to generate deliberately on both.
- Optimisation first because the HER2-specific assets are optimisation-shaped: two Apheris
  weights fine-tuned on the trastuzumab FACS screen that **only redesign CDRH3**, plus 524,346
  measured CDRH3 variants and ~700 optimisation designs with 190 SPR affinities (`TASK p4, p5`).
  De novo has no comparable measured prior for this epitope.

Evidence: `TASK p3` (classification flowchart), `TASK p4` (supporting data counts), `TASK p5`
(weight table), `TASK p8–9` (independent evaluation, prize split).

Confidence: medium. What would change our mind: if `abguard` rejects most of our optimisation
output on novelty (see next entry), de novo becomes the cheaper route to eligible designs and we
move Abdelrahman onto it.

---

## [10:55] Primary generation weight is `her2-novel-2026-11-09`, with `her2-2026-11-07` **exploratory** (`--sequence-tsr-k 1`) as the diversity arm

Revised in the pre-pitch fact-check pass: this entry previously named `her2-2026-11-07`
**balanced** as the diversity arm, contradicting `docs/tools-apheris.md` and its own closing
paragraph. The decision is now exploratory, in both docs, for the reason given below.

The tension: on the trastuzumab CDRH3 task, the weights that hit known binders are the weights
that fail the novelty filter. The organisers' own table (`TASK p5–6`):

| Weight and setting | Known binders | Pass novelty filter | Interface error (Å) |
|---|---|---|---|
| `antibody-2026-10-30` (not fine-tuned) | 0% | 100% | 8.2 |
| `her2-2026-11-07`, conservative | 21% | 0% | 9.4 |
| `her2-2026-11-07`, balanced | 21% | 6% | 9.1 |
| `her2-2026-11-07`, exploratory | 0.3% | 74% | 9.1 |
| `her2-novel-2026-11-09` | 4% | 86% | 6.8 |

Options considered:
1. `her2-2026-11-07` conservative — best shot at real binders, **0% pass novelty**: every design
   is rejected before it is measured. Unusable as a submission source.
2. `antibody-2026-10-30` — everything passes novelty, 0% known binders, and **8.2 Å, the second
   best interface error in the table**: better than all three `her2-2026-11-07` rows (9.1–9.4),
   worse only than `her2-novel-2026-11-09` (6.8 Å).
3. `her2-novel-2026-11-09` — 86% pass novelty and the **best interface error in the table,
   6.8 Å**, while still recovering 4% known binders.

Chose: **`her2-novel-2026-11-09` as the primary**, and **`her2-2026-11-07` exploratory
(`--sequence-tsr-k 1`) as a second, smaller arm** for loop diversity. `antibody-2026-10-30` is
held in reserve for anything that needs a CDR other than CDRH3 — the HER2 weights redesign CDRH3
only (`TASK p6`) — and as the de novo fallback, since it is the only row at 100% pass.

Why `her2-novel-2026-11-09` over `antibody-2026-10-30`, now that 8.2 Å is read correctly: the
conclusion survives, but not on interface error alone. `her2-novel-2026-11-09` beats
`antibody-2026-10-30` on interface error (6.8 vs 8.2 Å) **and** on known-binder recovery (4% vs
0%), and the only axis it loses is pass rate (86% vs 100%) — a 14-point tax on a filter we can run
locally before spending anything. `antibody-2026-10-30` has never recovered a measured binder on
this task, i.e. it carries no HER2-specific signal; it is a generic antibody model that happens to
be novel by construction. So it is the fallback, not the primary. 8.2 Å being second best is the
reason it is a *credible* fallback rather than a bad one.

Why **exploratory**, not balanced, for the diversity arm — the actual decision:

| `her2-2026-11-07` setting | Known binders | Pass novelty | Interface error |
|---|---|---|---|
| balanced (`--sequence-tsr-k 2`) | 21% | 6% | 9.1 Å |
| exploratory (`--sequence-tsr-k 1`) | 0.3% | 74% | 9.1 Å |

- **Interface error is identical** at 9.1 Å. The structural-quality axis does not separate them.
- **The "known binders" column is not a benefit for anything we submit.** A known binder fails
  the novelty filter by definition (`TASK p6`), so that column counts designs `abguard` will
  reject. Balanced's 21% is a measure of how much of its output is ineligible, not of how good it
  is. It is useful only as a reference set — what the model thinks a binder looks like.
- **Pass rate is the only axis that decides eligible yield.** Per 100 designs: balanced ~6
  eligible, exploratory ~74. Same GPU batch, 12× the submittable output.

Exploratory therefore dominates balanced on every axis that maps to a submission. Decided:
diversity arm is `her2-2026-11-07` **exploratory**, `--sequence-tsr-k 1` (`TASK p5`: k=2 balanced,
k=1 exploratory). Do not run balanced or conservative for candidates.

Operational consequence, and the reason this is a decision and not a note: **a known binder fails
the novelty filter, so we filter before we rank** (`TASK p6`). Novelty check is step one of the
scoring pipeline, not a final sanity check. Ranking a pool that still contains known binders
wastes the compute we do not have.

**If this doc and `docs/tools-apheris.md` ever disagree on a weight, a setting or a flag, this
file wins** — it is the decision record the Judgment score is read from; `tools-apheris.md` is the
how-to and must be edited to match it.

Evidence: `TASK p5–6` weight table and the two sentences after it; `TASK p5` for the
`--sequence-tsr-k` values.

Confidence: high on the ordering (it is the organisers' own measurement), low on the absolute
rates for our settings — the table is their run, not ours. What would change our mind: our own
abguard pass rate on batch 1. If `her2-novel-2026-11-09` passes well below 86% for us, we shift
volume to the exploratory arm (74% in their run) and, failing that, to `antibody-2026-10-30`
(100%, 8.2 Å, no HER2 signal).

---

## [10:55] Rank on `min_ipae`, `iptm` and `binder_plddt`, from a template-taking refold

Options considered:
1. Use RFD4-Proteina `refold-score`'s own pass criteria as the gate. **Not available**: for the
   HER2 exercise "the pass column stays empty" (`TASK p6`).
2. Rank on a single confidence number.
3. Rank on the three scores the organisers point at, from a refold done with a model that takes a
   template.

Chose: option 3. Pipeline is `refold-prepare` → fold with a Predict Structure model → `refold-score`,
and we rank on **`min_ipae`, `iptm`, `binder_plddt`** (`TASK p5–6`).

Two mechanics that follow from the sources and are easy to get wrong:

- **Refold with a template-taking model.** Template support per `TASK p5`: OpenFold3 (OpenBind,
  preview 2) yes, Protenix v2/v1 yes, Boltz-2 yes, Mol-1 base yes, Boltz-1 **no**, ESMFold2 **no**.
  ESMFold2 works but folds the target unguided, which is an unfair check for a binder (`TASK p6`).
  So ESMFold2 is a second opinion, never the ranking fold.
- **Boltz2 on the Nebius platform returns no ipTM** (`RECIPES` §2: the 1ZVY pair gave confidence
  0.77 and pTM 0.57, with no ipTM in the output). Any `iptm` we report comes from `refold-score`
  or from OpenFold3 — not from a Boltz2 run. If we need an interface number out of Boltz2 we
  count cross-chain contacts in the returned mmCIF and label it as that.

Standing caveat, carried from `docs/hackathon-brief.md`: none of pLDDT, PAE, ipTM or ipSAE is a
KD. These three scores order candidates; they do not predict the SPR number we are judged on.
Thermostability in particular is not in this triple at all and needs its own evidence per design.

Evidence: `TASK p5` (template column), `TASK p6` (empty pass column, ESMFold2 caveat, the three
score names), `RECIPES` §2 (no ipTM from Boltz2).

Confidence: high — this is the organisers' stated ranking basis for this exercise. What would
change our mind: a pass column appearing in an actual `refold-score` output, or an organiser
saying otherwise on the day.

---

## [11:15] ipSAE is out as the ranking metric; openfold3 ipTM + local contact counting is in

Options considered:
1. ipSAE, as originally planned — **not computable**. ipSAE needs the per-residue PAE matrix; no
   reachable Nebius model documents returning one, and the gateway contract affirmatively excludes
   "full-PAE" for boltz2. boltz2 also returns no ipTM.
2. AlphaFold3 / openfold3-openbind on the batch lane — graph deadlines of 12.5 h and 25 h. **Not
   reachable before 18:00.**
3. `openfold3` ipTM (native, ~3 min) plus locally computed cross-chain heavy-atom contacts, pTM and
   interface ΔSASA.

Chose: option 3, with the local contact count as the primary and ipTM as the confirmation, because the
contact count depends on no undocumented adapter field and costs no platform budget. True PAE-derived
`min_ipae` is available only through Apheris Foundry `refold-score` on the VM, so if the pitch needs an
ipSAE-like number it comes from there.

Evidence: `forge.py schema` for boltz2/openfold3/chai1/alphafold3/openfold3-openbind/protenix-v2 (five
of six publish no output schema at all); `scientific-gateway/references/client-contract.md` on
"full-PAE"; `RECIPES.md` "The output has no ipTM, so do not report one"; `openfold3/SKILL.md` naming
`iptm` "as rendered by the adapter". See `docs/probe-findings.md` §1.

Confidence: high that ipSAE is unavailable. **Low that openfold3 returns ipTM** — that rests on skill-doc
prose, not a machine-readable contract. What would change our mind: the first real openfold3 co-fold.
Whoever runs it must read `result.json` and confirm the key as a deliverable of that run.

---

## [11:15] De novo generation runs on the VM, not through forge.py

`forge.py` exposes no checkpoint selector for `rfd4-proteina` and cannot be made to. The antibody and
HER2 weights exist only as Apheris Foundry Docker images on the team VM, selected by choosing the image.
Nebius's hosted endpoint is the general checkpoint, which emits "a general protein binder, not a VHH" —
not one of the three accepted formats, so it fails the format gate before anything else.

Consequence: whoever owns the de novo track needs SSH to the VM working before they can start. This was
previously recorded as an open unknown about forge.py; it is now closed in the other direction.

Evidence: `forge.py schema rfd4-proteina --full`; resource map "Not a VHH"; `TASK p5` weights table.
Confidence: high.

---

## [11:15] Correction: antifold does not win the epitope axis for free

Earlier reasoning for prioritising optimisation assumed that keeping the trastuzumab framework preserves
the epitope essentially by construction. **That is wrong as stated.** Eligibility forces a ≥4-residue
rewrite of CDRH3, and CDRH3 carries most of trastuzumab's HER2 contact — the heavy chain dominates
epitope residues 557–593. Rewriting it is precisely the change most likely to move the epitope.

Revised: epitope preservation must be screened by co-folding and epitope-overlap scoring on **both**
tracks. Optimisation is still the better expected value — sharper position control than the HER2 weights
and a ~110 s model versus 6 min plus queue — but one of the three axes is not free.

Also corrected: the RECIPES `sampling_temp` of 0.20 is too conservative to clear the identity window and
must be raised; a temperature ladder in one job yields a few hundred candidates.

Evidence: `forge.py schema antifold`; `RECIPES.md` antifold recipe; epitope computation below.
Confidence: high on the mechanism, medium on the mutation count — it depends on how abguard computes
CDRH3 identity, which is unspecified (open question for the organisers).

---

## [11:15] Thermostability is our weakest axis, and we will say so in the pitch

Nothing on the platform predicts thermostability. Of 59 catalog models, only `stab-ddg` matches any
stability-related name, and its single operation is `predict-binding-ddg` over two **disjoint** partner
sets — its own reference says it is "not a generic folding-stability calculation". FoldX, CamSol, Flex
ddG, PyRosetta, ThermoMPNN, Aggrescan, SoluProt and NetSolP are all absent from the catalog.

Chose, per track and format:
- Optimisation + Fab/scFv: `stab-ddg` repurposed to the **VH–VL interface**, labelled as a VH–VL
  interface ΔΔG and never as a folding ΔΔG.
- Optimisation + VHH: `esm2-650m score-variants` only — a single domain has no second partner.
- De novo: `esm2-650m score-sequences` (PLL, per-residue mean because lengths differ). Every ddG is
  **undefined** here, not merely noisy; there is no parent to subtract.
- All candidates, free and local: **framework germline-likeness** — count mutations outside the CDRs and
  drive it to zero. Antibody Tm is dominated by framework and VH–VL pairing, not loops.

Rejected: `bioemu2` — emits conformations, no ΔG/ΔΔG/Tm, needs an MSA per chain, and any number from 8
samples would be a metric we invented. Also noted: disulfide presence is useless as a discriminator,
because abguard already hard-rejects unpaired cysteines, so every ranked candidate has passed it.

Evidence: `forge.py schema stab-ddg` (`operations: ["predict-binding-ddg"]`, disjoint partner sets);
`protein-scoring/references/binding.md`; `models --all` (59 ids, one match); `esm2.md` on what PLL is
not. See `docs/probe-findings.md` §4.

Confidence: high on availability, low on every proxy's correlation with measured Tm — which is the
point, and is what we report.

---

## [11:15] Reference epitope fixed at the 4.5 Å contact set from 1N8Z

19 HER2 residues: P557 E558 D560 Q561 K569 D570 P571 P572 F573 P579 I591 K593 D596 E598 A600 Q602 P603
C604 P605. **Identical at 5.0 Å**, verified against an independent brute-force all-pairs cross-check, so
the set is not an artifact of the cutoff. Hotspots by ΔSASA: E558, P571, F573, P603, P572, D560.

This set is now (a) the hotspot spec for generation and (b) the reference for the epitope-overlap axis.

Two traps recorded so nobody loses a day to them: chain C residue *n* = UniProt P04626 residue *n+22*,
so the epitope is 579–627 in UniProt numbering and specs must state their convention; and C604 sits in
the epitope with no SSBOND record only because its partner lies past the construct end.

Evidence: `scripts/epitope.py` over RCSB 1N8Z, Biopython NeighborSearch + ShrakeRupley; artifacts in
`data/reference/epitope/`. Chain identities concluded from sequence motifs and contact counts, not from
the COMPND record. Confidence: high.

---

## [13:20] Generate CDRH3 at 5 mutations, not 3 — measured on abguard, not inferred

This is the first entry backed by a result of ours rather than by the task PDF.

Context: `abguard` was reported missing from the VM at ~13:00, which would have put the
submission at risk. It was never missing — it is a `uv` tool at `~/.local/bin/abguard`, and
`~/.local/bin` is on `PATH` in a **login shell only**, so every non-interactive check said
"command not found". Full write-up in [`abguard.md`](abguard.md).

Options considered: build to the ">2 mutations" bar the task PDF implies (3 mutations) and spend
the H100 budget on volume; or measure the real pass rate first and set the target from it.

Chose: **design CDRH3 at 5 mutations from trastuzumab**, because 3 is necessary but nowhere near
sufficient, and we can now prove it.

Evidence: `abguard team-validate` against its bundled reference (610,109 CDRH3s across
`trastuzumab`, `trastuzumab_her2_spr_all_768` and `tz_her2_facs_3classes_524346`). 100 synthetic
trastuzumab CDRH3 variants, 25 at each mutation count, seed 20261114, cysteine excluded from the
substitution alphabet:

| CDRH3 mutations from trastuzumab | Passed abguard |
|---|---|
| 3 | 3/25 (12%) |
| 4 | 16/25 (64%) |
| 5 | 23/25 (92%) |
| 6 | 23/25 (92%) |

Reproduce: `bash pipeline/filter/gate.sh designs/probe.csv` on the VM.

Why 3 fails so often: the mutation distance is counted against **every** provided loop, not just
the parent. A design 3 mutations from trastuzumab typically lands 1–2 mutations from some *other*
measured loop in the 524k FACS screen, and is rejected on that. The screen densely covers the
neighbourhood around trastuzumab's CDRH3 — which is exactly the neighbourhood the HER2 fine-tuned
weights were trained to generate in.

**This is the mechanism behind the PDF's novelty table** (`her2-2026-11-07` conservative: 0% pass,
balanced: 6%). We had read those numbers as a property of the weights; they are a property of the
reference set the weights were trained on. That strengthens the 10:55 decision to lead with
`her2-novel-2026-11-09` — it was trained on high/low binder *pairs* rather than to reproduce the
screen, which is why it reaches 86% — and it is now an argued conclusion rather than a bet on a
table we did not generate.

Two corrections to our own docs fall out of this, both now fixed in `README.md` and `workplan.md`:

- **There is no "< 70% CDRH3 identity to trastuzumab" requirement.** `abguard` never computes a
  CDRH3 identity threshold; the ≥70% figure only classifies a design as a trastuzumab variant
  rather than de novo. Our variants sit at 98–99% whole-sequence identity and are valid
  optimisations. Designing to the 70% reading would have meant rewriting a third of the loop for
  nothing, and would have cost us the optimisation track.
- **The 250 aa limit is per chain**, not VH + VL combined.

Confidence: high on the ordering and on the mechanism — it is the organisers' own tool and its
own reference, run by us. Medium on the absolute rates: the probe is random substitution, and
RFD4-Proteina's loops are not random, so our real pass rate will differ. What would change our
mind: the measured pass rate on generation batch 1. If `her2-novel-2026-11-09` at 5 mutations
comes in well under 92%, we raise the target to 6 rather than lower the mutation count.

Consequence for the plan: `pipeline/filter/novelty.py` (Abdelrahman, 13:15) is cancelled — it
would have reimplemented this against 525,063 loops and to the wrong threshold. The gate is
`pipeline/filter/gate.sh`, and `rank.py` joins `reports/novelty-report.csv` on `sequence_id`.

---

## [13:25] Supersedes 13:20 — target ≥ 6 CDRH3 mutations. 3–4 is a dead zone, and 5 is marginal

Batch 1 finished enough designs to measure the gate on real RFD4-Proteina output instead of my
synthetic probe. **The probe was wrong in the direction that mattered**, so this entry replaces the
13:20 recommendation. Keeping both because the error is informative.

Run: `~/mark/runs/b1-novel-s1`, `her2-novel-2026-11-09`, seed 1, 129 designs extracted mid-run
(`designs/raw/batch1-b1-novel-s1.csv`). Gated with `bash pipeline/filter/gate.sh`.

**91/129 eligible — 70.5%.** Zero hard errors: no format, length, alphabet, cysteine or `immunum`
failures in 129 designs. **All 38 rejections are novelty**, and the breakdown is the finding:

| CDRH3 mutations from trastuzumab | Passed |
|---|---|
| 2 | 0/3 |
| 3 | **0/5** |
| 4 | **0/7** |
| 5 | 4/9 (44%) |
| 6 | 15/18 (83%) |
| 7 | 44/56 (79%) |
| 8 | 25/28 (89%) |
| 9 | 3/3 |

**35 of the 38 rejections were ≥3 mutations from trastuzumab** and were killed by proximity to a
*different* measured loop. Only 3 failed on trastuzumab distance.

So the 13:20 advice to "design to 5" was the wrong lever, and the synthetic numbers (3 → 12%,
4 → 64%, 5 → 92%) do not transfer. Why the probe over-estimated: it substituted residues at random,
which scatters designs across the whole sequence space, whereas RFD4 draws loops toward the same
high-affinity motifs the FACS screen already explored. **At 3–4 mutations the real generator lands
inside the densest part of the reference every time — 0/12.** Random mutants do not.

Chose: **do not steer generation toward fewer mutations.** `her2-novel-2026-11-09` already produces
6–8 mutations unprompted (102/129 at ≥6) and that is precisely why it passes; that distribution is
the weight's value, not something to correct. Treat **≥6 as the floor**, 5 as marginal, 3–4 as
unusable. Over-generate ~1.4× the slots we need and let the gate decide.

Confidence: high — our own designs, our own run, the organisers' own tool. Caveats recorded: one
seed, one weight, and the run was still generating when sampled, so this is 129 of a larger batch.
What would change our mind: a second seed landing materially off 70%.

Two smaller things from the same run:

- **91 survivors contain only 85 unique heavy chains** — 6 duplicate pairs inside one batch.
  `abguard competition-validate` rejects sequences shared *between* teams, so duplicates are pure
  waste in a 20-slot list. Dedupe on `heavy_sequence` before ranking.
- 744 LAP liability occurrences across 129 designs (~5.8 each), none of them hard errors.
  `reports/batch1-liability.json` is the per-design detail; W4 should rank on it, since liabilities
  are a developability signal and developability is not one of the three judged axes but does
  decide whether a design expresses at all.

Our 70.5% sits below the PDF's 86% for this weight. Not alarming at n=129 on one seed, but it means
the 20-design list needs ~29 generated candidates minimum, and more if we also dedupe.

---

## [13:55] Batch 1 result: 14 of 20 eligible, and the failures tell us how to generate

First real designs of the day. `her2-novel-2026-11-09`, 100 designs (seed 1,
`--recycle-strategy high/front_loaded`), top 20 refolded with Boltz-2 and scored.

Design-stage quality (`b1_design_aggregated_metrics.csv`, mean over the batch): hotspot obedience
0.9375, sequence adherence 1.0 with 0 violations, `frac_atoms_clashing_1p5A` 0.0002, bond lengths 0%
unreasonable. Interface: 11.0 H-bond atoms, 1.75 salt bridges, 17.25 hydrophobic atoms.

Refold scores for the 14 eligible (`reports/b1_refold_metrics.csv`), best six:

| id | iptm | min_ipae | binder_plddt | CDRH3 |
|---|---|---|---|---|
| her2_cdrh3_74 | 0.912 | 0.3542 | 98.44 | SRDLSLSNYAHDY |
| her2_cdrh3_14 | 0.903 | 0.3544 | 97.95 | SRWHSLHEYYFDY |
| her2_cdrh3_88 | 0.900 | 0.3362 | 98.10 | SRSLSLGNYAFDY |
| her2_cdrh3_52 | 0.893 | 0.3568 | 98.42 | SRDLYLYNYSFDY |
| her2_cdrh3_28 | 0.888 | 0.3437 | 97.76 | SRSLTPLSDVFDY |
| her2_cdrh3_91 | 0.888 | 0.3492 | 96.85 | SRDRTPTDYSFDY |

`pass` is empty for every row, with `pass_note` "fewer than 3 target atoms fixed in absolute
coordinates, so target-aligned RMSDs are undefined" — exactly as `18-vm.md` predicts for this example,
so we rank on `min_ipae`, `iptm` and `binder_plddt`, and only within one folding model.

**The six rejections are the useful part.** None failed against trastuzumab — all were 6–9 mutations
away. Every one failed against the **FACS screen**: 1–2 mutations from a sequence already measured in
`tz_her2_facs_3classes_524346`. For example `her2_cdrh3_53` was 1 mutation from `SRWGSSDFYAFDY`.

Two consequences, and the second is a strategy rather than a fix:

1. **Pre-filter locally before spending refold compute.** CDRH3 Levenshtein against the 524k table is a
   cheap local computation; refolding a design that abguard will reject wastes GPU minutes we do not
   have. Our observed pass rate of 70% (14/20) is close to the organisers' claimed 86% for this weight,
   so the loss is real but not catastrophic.
2. **The screen is a map of what binds, and the gate forces us exactly 3 mutations off it.** A design
   sitting 3 mutations from a measured **high** binder is close enough to plausibly inherit binding and
   far enough to be eligible. That is a deliberate target, not a filter — and it is the one place where
   having 524,346 labelled sequences is an advantage over teams treating novelty as a hurdle.

Evidence: `abguard team-validate` output quoted in full in the issue #11 thread;
`designs/submission_b1_valid.csv` (14 rows) and `designs/submission_b1_all20.csv` (all 20, for the
record). Confidence: high on the measurements, medium on the strategy — untested.

---

## [13:58] Liability reading: the shared motifs are trastuzumab's own, not ours

`abguard liability-report` on the 20: **0 hard errors**, 116 liability occurrences.

All 20 designs carry `Isom`, `DeAmdH`, `TrpOx`, `DeAmdM` and `DeAmdL`. Because the framework and the
other five CDRs are held fixed by the design spec (sequence adherence 1.0), a motif present in all 20
is **inherited from trastuzumab itself** and cannot discriminate between our designs. Trastuzumab is an
approved drug carrying these liabilities, so they are not disqualifying.

The discriminating tags are the rare ones: `Ngly` (1 design), `MetOx` (3), `FragM` (2). Those sit in the
designed CDRH3 and are the ones worth penalising in the ranking, because a design without them is
strictly better on an axis the organisers' own tool measures.

`mCys`, `xCys`, `FragH`, `Hydro` and `IntBind`: zero occurrences.

Evidence: `abguard liability-report designs/submission_b1_all20.csv`. Confidence: high on the counts,
high on the framework-inheritance inference (it follows from sequence adherence 1.0).

---

## [14:05] NetSolP is a floor and a tiebreak, not a filter — calibrated against 190 measured binders

The organisers name NetSolP as one of four developability tools (`TASK p7`), so we ran it. The
question was what threshold to filter on. The answer is that **no threshold is defensible**, and we
can show that with the organisers' own SPR data.

Options considered: pick a plausible cut (0.5 is the natural midpoint of a probability); use the
distribution of our own designs and cut at some percentile; or calibrate against molecules already
known to express and bind, and only reject outside that range.

Chose: **calibrate.** Scored the 200 batch-1 designs and the 190 SPR-quantified trastuzumab
variants — molecules that demonstrably express *and* bind HER2.

| | n | min | p5 | median | p95 | max | sd |
|---|---|---|---|---|---|---|---|
| our designs | 200 | 0.4958 | 0.5110 | 0.5302 | 0.5489 | 0.5489 | 0.0113 |
| **measured binders** | 190 | 0.4960 | 0.5179 | 0.5426 | 0.5489 | 0.5489 | 0.0103 |

The distributions are the same to within noise, and the entire dynamic range is 0.05 wide. So any
cut that removes a meaningful share of designs removes a comparable share of **known good
molecules**: 0.515 drops 12% of designs and 4.2% of measured binders; 0.530 drops 47% of designs
and 14.2% of measured binders. And it carries no affinity signal —
**Pearson r(netsolp_min, KD nM) = −0.04** over the 190 binders.

This is not a failure of NetSolP. On diverse proteins it separates properly (SIV integrase 0.283,
human leptin 0.460, HhaI methyltransferase 0.765). It simply cannot resolve CDRH3 point variants of
one antibody: every design shares the trastuzumab framework and differs in ~10 of ~230 residues.
Our light chain is fixed trastuzumab VL and scores a constant 0.5489, so `netsolp_solubility_min`
is effectively the heavy-chain score.

So the rule we apply: **a hard floor at 0.4960, the minimum over the measured set** — a design
scoring below every molecule known to work is outside the supported range. On batch 1 that rejects
exactly one design, `her2_cdrh3_124` (0.4958). Above the floor, `netsolp_solubility_min` is a
ranking tiebreak only, never a gate.

Evidence: `reports/netsolp-calibration-spr190.csv` (the 190 scored binders),
`reports/batch1-solubility.csv`, `pipeline/filter/solubility.py` (the calibration is in its
docstring). NetSolP 1.0 quantized ONNX, Distilled model, installed on the VM at `~/tools/netsolp`
by a teammate; 3 designs score in 4.5 s on CPU, so it never competes with the GPU.

Confidence: high that no higher cut is defensible — it is a direct comparison against measured
binders on the organisers' own data. Medium on the floor's exact value: it is one dataset's minimum,
so it will move slightly with a different reference set. What would change our mind: a reference set
of measured NON-expressing variants. We have binders only, so we can bound the bottom but cannot
calibrate discrimination. If the organisers release the non-expressing arm of the FACS screen, this
becomes a real filter.

Caveat for Execution: `~/tools/netsolp` lives on the VM, not in this repo, and **the VM is wiped
tonight**. The calibration CSV and the scored outputs are committed; the tool itself is not. Either
vendor the installer or record the exact provenance before 17:40.

---

## [14:15] The ≥6-mutation target is deleting the paratope. Constrain *which* positions move, not how many

The 12:30 epitope deliverable was still missing, so nothing downstream had an interface term and
`scored` was 0. Built it: `1N8Z` pulled into `data/target/`, interface computed at 4.5 Å all-heavy-atom
by `pipeline/score/epitope.py`. Full result in [`epitope.md`](epitope.md). It reproduces the published
domain IV footprint, which is the check that it is right.

The finding is what it does to our generation target. Of the 10 VH contacts, only **4 sit inside the
generator's mutable window** (VH 99–107, `WGGDGFYAM`): **W99, G103, F104, Y105**. G103 is the closest
contact in the whole interface at 2.42 Å. Positions 100, 101, 102, 106, 107 touch nothing.

Measured on the 121 unique eligible designs (`pipeline/score/paratope_check.py`,
`reports/batch1-paratope.csv`):

| CDRH3 contacts preserved | Designs |
|---|---|
| 3 or 4 of 4 | **0 (0%)** |
| 2 of 4 | 16 (13.2%) |
| 1 of 4 | 68 (56.2%) |
| 0 of 4 | 37 (30.6%) |

**F104 is mutated in 121/121 designs. G103 in 117/121.** And it gets worse with mutation count: at
8–9 mutations, 34 of 53 designs keep zero contacts; at 5 mutations, all 6 keep two.

That is a structural conflict, not bad luck — the window is 9 residues, 4 of them are the interface,
so novelty and epitope preservation compete for the same positions. **The 13:25 ≥6 floor was derived
from the abguard gate alone, and the gate measures neither criterion 1 (SPR) nor criterion 2
(epitope).** We optimised the filter and let the binding site go.

Options considered: (a) lower the mutation floor to 5 so contacts survive — costs us novelty, 44%
pass, and 13:25 already showed fewer mutations is the wrong lever; (b) accept batch 1 and rank on
refold scores — but 0/121 keep 3 contacts, so there is nothing good to rank; (c) keep the floor and
constrain position choice.

Chose: **(c) — hold W99 + G103 + F104 fixed and let the other six positions (100, 101, 102, 105, 106,
107) move.** Six free positions still reach the **≥6 floor at the best measured pass rate in the
batch-1 table, 83%**, while preserving 3 of 4 contacts. It is a constraint on *which* residues move,
not how many, so it costs nothing against the gate. Y105 is the one contact we spend — it is already
preserved in 69% of designs unprompted, so it is the cheapest of the four to put in the free set.

Evidence: `reports/batch1-paratope.csv` (121 designs), the 13:25 abguard pass-rate table
(5 → 44%, 6 → 83%, 7 → 79%, 8 → 89%), 1N8Z at 4.5 Å.

Confidence: high that batch 1 ablates the measured contacts — it is 100% loss on F104 across 121
designs, far outside sampling noise. **Medium on what that costs us in binding.** Contact-residue
identity is a proxy, not the competitive binding assay: a conservative substitution can keep the
interaction and a redesigned loop can form new contacts holding the same epitope. We cannot run the
assay. What would change our mind: boltz2 co-folds against 1N8Z chain C showing batch-1 designs
keeping cross-chain contacts in the 557–605 footprint anyway — in which case the proxy is too strict
and the ≥6 floor stands.

Consequence for Generation: **batch 1 is not a submission.** Re-run `her2-novel-2026-11-09` with
positions 99, 103, 104 held — `antifold` keeps the framework and takes fixed positions, and RFD4-Proteina
takes it as a contig. Do **not** fall back to random substitution at the six free positions: it passes
novelty easily (the 13:20 probe over-estimated precisely because random scatters away from the
reference) but throws away the affinity prior that is the only reason to be on this track.

Still open, and the real bottleneck: **`scored` is 0.** The paratope proxy is free and needs no GPU;
the refold does. boltz2 is verified working at 63 s (`nebius-runs/pae-probe.json`), so the co-folds
can run against chain C in parallel with the constrained re-generation.

---

## [14:20] Batch 2 measured: `her2-exploratory` buys diversity at half the eligibility. Keep both arms, generation is done

The diversity arm finally ran. It had been dead since 12:41 UTC: `~/mark/generate.sh` asked the
**her2-novel image** for the **her2-exploratory model**, and each weight ships as its own Docker
image, so it failed on contact and left the GPU idle on our work for ~20 minutes. Relaunched through
`pipeline/generate/design.sh`, which derives the image from the model so the mismatch cannot recur.

Two arms, 200 designs each, both gated with `pipeline/filter/gate.sh`:

| Arm | Weight | Seed | Unique heavy | Eligible | PDF claimed |
|---|---|---|---|---|---|
| batch 1 | `her2-novel-2026-11-09` | 1 | 170/200 (85%) | **140/200 (70%)** | 86% |
| batch 2 | `her2-exploratory` (`her2-2026-11-07`) | 2 | **200/200 (100%)** | **70/200 (35%)** | 74% |

**Zero sequence overlap between the arms**, so the combined pool is **191 unique eligible designs**
— 9.6x the 20 slots. Generation is finished; nothing is gained by more of it.

The arms are genuinely complementary rather than redundant. `her2-exploratory` never repeats itself
(100% unique vs 85%) but only a third of its output is eligible, and it is worse *at equal distance
from trastuzumab* — at 6 mutations it passes 25% where `her2-novel` passes 83%:

| CDRH3 mutations from trastuzumab | batch 1 passed | batch 2 passed |
|---|---|---|
| 3 | 0/5 | 0/10 |
| 4 | 0/7 | 1/22 |
| 5 | 4/9 (44%) | 7/46 (15%) |
| 6 | 15/18 (83%) | 13/51 (25%) |
| 7 | 44/56 (79%) | 22/39 (56%) |
| 8 | 25/28 (89%) | 17/20 (85%) |

That is the 13:25 mechanism again, sharper: `her2-2026-11-07` was fine-tuned to reproduce the FACS
screen's binders, so even its exploratory samples stay inside screen-covered sequence space and
collide with measured loops. `her2-novel-2026-11-09` was trained on high/low binder *pairs*, so it
leaves that space. Distance from the parent is not what the gate measures.

Both our rates come in below the PDF's (70% vs 86%, 35% vs 74%). Consistent direction, so most
likely a difference in input conditioning or hotspot settings rather than a fluke. We report our own
numbers and say so.

Chose: **keep both arms in the candidate pool and rank across them.** The exploratory arm's 70
designs are all distinct and cost us nothing more to carry; dropping them would narrow the pool for
no benefit now that scoring, not eligibility, is the constraint.

Evidence: `designs/raw/b1-novel-s1.csv`, `designs/raw/b2-explor-s2-fixed.csv`,
`reports/*-eligible.csv`, `reports/*-novelty.csv`, `nebius-runs/b2-explor-s2-fixed.manifest.json`.

Confidence: high on both rates, n=200 each on the organisers' own tool. Medium on the mechanism.
What would change our mind: nothing before 18:00 — generation is closed.

**One defect found and fixed while harvesting:** RFD4 numbers designs `her2_cdrh3_0..199` *per run*,
so batch 1 and batch 2 shared every id. abguard requires a unique `sequence_id` and drops duplicates,
so concatenating the two batches into one submission table would have silently discarded rows.
`cif_to_submission.py` now namespaces ids with the run directory by default. Both batches have been
re-extracted and re-gated under unique ids.

---

## [14:35] Batch 2 confirms the position constraint, and the pipeline now has one entry point

Two things since 14:15, both verifiable by anyone on any machine.

**1. The constraint works.** `b2-explor-s2-fixed` landed at 14:25 with CDRH3 positions held, which
is the test of the 14:15 claim. Same script, same 1N8Z interface, 70 unique eligible designs:

| CDRH3 contacts preserved | b1-novel-s1 | b2-explor-s2-fixed |
|---|---|---|
| 3 of 4 | 0 (0%) | **18 (25.7%)** |
| 0 of 4 | 37 (30.6%) | 7 (10.0%) |

G103 preservation went **3.3% → 45.7%**, and the predicted band is populated: **8 designs at
6 mutations holding 3 of 4 contacts**, all keeping W99+G103+Y105 and spending F104 (the shallowest
contact, 4.27 Å, 1 partner). Six mutations sits at the 83% novelty band, so this costs nothing
against the gate — exactly as the window arithmetic said. 121 batch-1 designs never produced one.

Caveat, and it is a real one: b2 is the **exploratory** weight, which the task PDF scores at 0.3%
known-binder recovery. Contact residues surviving is not the loop being a good binder. **The
missing experiment is the same constraint on `her2-novel-2026-11-09`.** Confidence that the
constraint does what we claim: high. Confidence that these 8 are good binders: low, and nothing in
this repo measures it yet.

**2. One entry point, re-runnable by a judge.** `pipeline/README.md` promised "a judge can run it on
a target we have never seen" and there was no such command, plus three stages that only work on a VM
that is wiped tonight. Added:

- `pipeline/run.sh` — six stages, every batch, `--target/--chain/--offline/--stage/--list`.
  Exit 0 = all passed, 2 = a local stage failed, **3 = local passed but remote unavailable**, which
  is the expected off-VM result. Writes `reports/run-<UTC>.provenance.txt` with target sha256,
  python, uname, git rev and which stages skipped and why. Stage 5 (boltz2) is never launched
  implicitly — it spends shared GPU budget and must be asked for.
- `pipeline/selftest.sh` — **12 checks, 0 failed, runs in seconds with no network or GPU.**
  Determinism (byte-compare against `tests/expected/`, twice per stage to catch ordering leaks);
  **science** (assert the computed interface IS the published footprint: span 557-605, 19 residues,
  closest contact G103 at 2.42 Å, 1N8Z chain B VH identical to our declared parent); negative
  controls (all four must be rejected); and refusal (rank must exit 3 with axes empty).
- `pipeline/score/rank.py` — pools batches, dedupes on heavy chain, reads the 24-column schema from
  the existing `designs/submission.csv` so it cannot revert a teammate's extension, and **refuses
  to emit** when `min_ipae` or `predicted_ddg` is absent. `--allow-partial` overrides with `n/a`.
- `docs/REPRODUCE.md` — the judge-facing page.

The science checks are the ones that matter. A checksum proves we re-ran something; asserting
against a published footprint we did not produce proves we re-ran something *right*.

**A SKIP is now treated as suspicious.** The first version of the self-test hardcoded `batch1-*`
filenames; when the batches were renamed to `b1-novel-s1` the checks degraded silently into SKIPs
and it still reported success. Both loops now enumerate `designs/raw/*.csv` and fail loudly on an
empty directory. Worth remembering for anything else we assert on a filename.

Where this leaves the submission: **191 pooled candidates, 0 scored, stage 6 refusing.** `min_ipae`
is empty for every one. boltz2 is verified at 63 s/call (`nebius-runs/pae-probe.json`) and the
co-folds are the only thing between us and a defensible ranked list — the 8-design shortlist is the
obvious place to spend the first calls, with the other 183 behind them.

---

## [14:45] Scoring is unblocked: the full refold loop runs, ~15-17 s/design, and all three ranking metrics are obtainable

The submission was blocked on one unmeasured number. Nobody had run a refold, so nobody knew
whether 191 eligible designs could be scored before the 16:00 freeze. They can, comfortably.

The loop, proven end to end on the VM:

```
design run -> refold-prepare -> keep only abguard-eligible -> predict (OpenFold3-OpenBind) -> refold-score
```

**Measured: 2 designs in 54-59 s wall, ~15-17 s/design marginal.** So ~190 designs is roughly
50-55 minutes on the idle H100 — not the multi-hour wall it was feared to be. Using OpenFold3 as
the refold model also puts Apheris' OpenFold in our pipeline, which is the condition attached to
the monetary prize (`README.md`, `tools-apheris.md`).

Result on the first two designs (`her2_cdrh3_151`, `her2_cdrh3_43`, both abguard-eligible, CDRH3
distance 8 and 7):

| design | min_ipae | iptm | binder_plddt | binder_ptm | plddt |
|---|---|---|---|---|---|
| her2_cdrh3_151 | 0.651 | 0.569 | 89.50 | 0.943 | 87.21 |
| her2_cdrh3_43 | 0.598 | 0.592 | 90.28 | 0.946 | 88.23 |

**The one trap, and it cost us an hour of wrong conclusion.** `predict` omits PAE and per-atom
pLDDT **by default** — they grow with the square of the token count. Without them `refold-score`
returns `min_ipae` and `binder_plddt` **empty**, i.e. two of the three metrics the 10:55 decision
ranks on, with only a `pass_note` hinting why. The fix is one flag: `--write-detailed-scores true`.

I first concluded from the empty columns that the ranking triple was unobtainable from OpenFold3,
and checked Boltz-2 and Protenix v2, which return the same normalised summary schema with no PAE —
which looked like confirmation. It was not: the Foundry wrapper standardises the *summary* JSON
(this is what the PDF means by "every model gives the same outputs"), and PAE lives in the detailed
CBOR sidecar that the flag enables. **The 10:55 ranking decision stands unchanged.** Recording the
error because the shape of it generalises: an empty column in a normalised wrapper means "not
exported", not "not available".

Still genuinely unavailable: `target_aligned_binder_rmsd`, hence `pass` stays empty —
*"fewer than 3 target atoms fixed in absolute coordinates (coordinate group 0), so target-aligned
RMSDs are undefined"*. That matches what `tools-apheris.md` already said for the HER2 exercise, so
rank on `min_ipae`, `iptm`, `binder_plddt` and do not wait for a pass flag. Do **not** rank on
`backbone_rmsd` either: it comes back 18.9-21.6 A, but with target-aligned RMSD undefined it is not
a binder-vs-design deviation and quoting it as one would be wrong.

**One wiring defect found and handled:** `refold-prepare --top-n` ranks by RFD4's own design
metrics and knows nothing about abguard, so it will queue designs the gate rejects and spend GPU
time on candidates that can never be submitted. `pipeline/score/refold.sh` prunes the query set to
the eligible ids first (`pipeline/score/filter_queries.py`). The task PDF is explicit: filter before
you rank.

Evidence: `pipeline/score/refold.sh`, `mark/runs/refold-probe-scored2/refold_metrics.csv` on the VM.
Confidence: high — our designs, our GPU, the organisers' own modules, two designs scored with every
ranking metric present. What would change our mind: nothing; this is a capability check and it
passed.

---

## [15:05] The novelty gate is now checkable offline, and batch 2 is mostly ineligible

Options considered:
1. Keep sending every batch to `abguard` on the VM and wait for the verdict.
2. Reproduce the novelty arithmetic locally so a batch can be filtered before it costs GPU time.

Chose: **both** — `scripts/novelty_distance.py` as a pre-filter, `abguard team-validate` as the
verdict. The local check agrees with abguard on all 20 rows of batch 1 (same 14 pass, same 6
reject) in 38 s, standard library only, so any teammate can run it on a laptop.

What it found when pointed at batch 2 (`designs/raw/b2-explor-s2-fixed.csv`, 200 designs):
**70 pass, 129 reject, 1 unparseable.** Six designs are at distance 0 — exact duplicates of a
measured CDRH3. 103 of the 129 rejections are blocked by a HIGH-class measured binder, the same
pattern as batch 1 at more than double the rate. Batch 2's own novelty report had not caught this:
`filter/gate.sh` could not find `abguard` off the VM (`reports/b2-explor-s2-fixed-gate.stdout`),
so its `cdrh3_nearest_source` is `trastuzumab` on every row and `is_novel_enough` is empty.

Evidence: `reports/b2_novelty_distance.csv`, `reports/b1_novelty_distance.csv`. 525,027 unique
reference CDRH3s, re-extracted from `vh_sequence` in both organiser tables rather than read from
the `cdrh3` column, which holds the 10-mer core — see `docs/abguard.md` §4.

This corroborates the 13:25 and 14:15 entries from the other direction. "≥ 6 mutations from
trastuzumab" and "≥ 3 from every measured loop" are the same constraint measured from opposite
ends: the FACS screen is dense around the parent, so proximity to trastuzumab implies proximity
to something already measured. Both batch-1 designs at 4 mutations from trastuzumab were
rejected; 14 of the 18 at 6–9 passed.

Confidence: high on the arithmetic (20/20 agreement with abguard, and a batch-1 regression after
two bug fixes). Medium on completeness — our reference set is 525,027 rows and abguard's bundle is
610,109, so the local check can only ever be optimistic. It covers novelty alone; schema, cysteine
and numbering checks still belong to abguard.

Confidence: what would change our mind — if abguard on the VM rejects any design this check passes,
the 85k-row gap is the first place to look.

---

## [16:10] The trastuzumab affinity baseline is eight replicates spanning 6.2x, not one number

A design is tiered on whether it **improves on trastuzumab**, measured. We had been treating
trastuzumab's affinity as a single value. In the organisers' own SPR table it is eight rows:

  0.0285, 0.0379, 0.0792, 0.123, 0.146, 0.152, 0.165, 0.178 nM

Which replicate the comparison uses changes the answer by nearly an order of magnitude in hit
rate, over the 182 measured non-WT variants:

| Baseline used | Variants that beat it |
|---|---|
| best replicate, 0.0285 nM | 1 of 182 (0.5%) |
| mean, 0.1137 nM | 4 of 182 (2.2%) |
| worst replicate, 0.178 nM | 7 of 182 (3.8%) |

Two consequences. First, for the pitch: "improves affinity" is not a well-defined claim until the
baseline is named, and saying so demonstrates we understood what the tier actually measures --
judgment axis, and cheap. Second, for expectations: even at the most generous baseline the prior
on a CDRH3 substitution beating the parent is under 4%, among sequences already selected for
measurement. With 4 designs tested at base, the expected count of affinity improvements is well
below one. The epitope axis is where our evidence actually is.

Evidence: `trastuzumab_her2_spr_all_768.csv`, rows with `cdrh3 = WGGDGFYAMD`.

Confidence: high on the arithmetic. Unknown which baseline the judges use -- **TODO: ask an
organiser**, it is a 30-second question and it affects every tier claim any team makes today.

## [16:15] rank.py was refusing on an axis it already had

`score/rank.py` reported `candidates with a refold score : 0` while 20 designs carried a measured
`min_ipae` on disk. Three independent faults in the join, each silent:

1. `--refold` defaulted to `reports/batch1-refold.csv`, which does not exist. A missing file reads
   as an empty table, not as an error.
2. The score table names its key `query_id`; the candidate pool uses `design_id`.
3. The two live in different namespaces -- `her2_cdrh3_14` against
   `b1-novel-s1-her2_cdrh3_14`.

Fixed by normalising ids before the join (`design_key`), pooling score tables per batch the way
paratope tables already were, and counting coverage **over the candidate pool** rather than
counting rows in the score table -- a table whose ids join to nothing was the failure mode the
script could not see. Coverage is now printed, and a short count against the slots is called out.

Result: 16 of 191 candidates now carry a measured `min_ipae`, and the refusal is down from two
axes to one. `predicted_ddg` is genuinely absent -- `stab-ddg` has never run, and nothing in
`reports/` has ever held that column.

Confidence: high. `selftest.sh` still passes 5/0/2 and rank.py still exits 3, now for the right
reason.
