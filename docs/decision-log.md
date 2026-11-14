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

No experimental or model result of ours appears in this file yet. We have not run anything.

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
