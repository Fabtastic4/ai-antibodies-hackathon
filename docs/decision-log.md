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

## [10:55] Primary generation weight is `her2-novel-2026-11-09`, with `her2-2026-11-07` balanced as the diversity arm

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
2. `antibody-2026-10-30` — everything passes novelty, 0% known binders, worst interface error of
   the HER2-relevant rows at 8.2 Å.
3. `her2-novel-2026-11-09` — 86% pass novelty and the **best interface error in the table,
   6.8 Å**, while still recovering 4% known binders.

Chose: **`her2-novel-2026-11-09` as the primary**, because it is the only row that is good on both
axes at once, and **`her2-2026-11-07` balanced (`--sequence-tsr-k 2`) as a second, smaller arm**
for loop diversity, accepting that ~94% of that arm is discarded. `antibody-2026-10-30` is held in
reserve for anything that needs a CDR other than CDRH3 — the HER2 weights redesign CDRH3 only
(`TASK p6`).

Operational consequence, and the reason this is a decision and not a note: **a known binder fails
the novelty filter, so we filter before we rank** (`TASK p6`). Novelty check is step one of the
scoring pipeline, not a final sanity check. Ranking a pool that still contains known binders
wastes the compute we do not have.

Evidence: `TASK p5–6` weight table and the two sentences after it.

Confidence: high on the ordering (it is the organisers' own measurement), low on the absolute
rates for our settings — the table is their run, not ours. What would change our mind: our own
abguard pass rate on batch 1. If `her2-novel-2026-11-09` passes well below 86% for us, we shift
volume to the exploratory setting (74% pass).

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
