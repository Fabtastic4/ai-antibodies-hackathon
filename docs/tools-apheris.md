# Apheris Foundry — Predict Structure and RFD4-Proteina

> **Corrected 14:10.** This doc's novelty criteria were wrong. There is no <70% CDRH3-identity
> requirement - identity only classifies the track. The real bar is the CDRH3 mutation count,
> counted against all 610,109 known CDRH3s. Measured on batch 1: 3-4 mutations pass 0/12, 5 passes
> 44%, 6+ passes 79-89%, so **generate at >=6**. See [`abguard.md`](abguard.md).

Source: the official task description PDF, Tooling → Apheris section. Numbers here are the
PDF's, not estimates. Anything not in the PDF is marked `TODO: confirm`.

Foundry runs **inside our own VM**: every model is a Docker image, already downloaded.
`foundry-toolkit module list` lists them. `Tutorial.html` (Hackathon VM tab) shows how to run each.

**Why this doc matters twice over.** Foundry is the only place that ships **HER2-specific
fine-tuned RFD4-Proteina weights** — nobody else at the hackathon has a model that has seen the
trastuzumab FACS screen. And the organisers' participant guide on the event website says, verbatim:

> Apheris and Openfold are the monetary prize sponsors; to qualify for that prize, include
> Apheris' version of Openfold in your pipeline.

(participant guide, website, Chapter 2 "Tools and tutorials" → Prizes.)

Three things to keep straight about that sentence:

- In Foundry, "Apheris' version of Openfold" is `OpenFold3` (OpenBind, preview 2) under Predict
  Structure — that is the only OpenFold build Foundry ships (`TASK p5` model table). The guide
  does not name the image, so this identification is ours, not the organisers'.
- **The task PDF does not repeat the condition.** Its prize section (`TASK p9`) says only: €3000
  total, split equally between the two tracks, €800 / €500 / €200 per track, plus an extra $500
  Best Pitch prize on the day. No pipeline requirement attached. So this is a **guide-only
  claim** — `TODO: confirm with an organiser on site` (whoever gets to the Apheris desk first).
  Do not state it to judges as a rule.
- Cheapest way to satisfy it either way, confirmed or not: use OpenFold3 as the refolding model
  in the check loop below. We want a template-taking refold regardless, so this costs nothing.

(Noted for drift: the website front page calls the fund "3,000 USD"; `TASK p9` says €3000. The
task PDF wins.)

## Predict Structure (`predict`)

Predicts the 3D structure of a complex with a co-folding model. **Every model takes the same
inputs and gives the same outputs**, so models are swappable without changing the rest of the
pipeline. It takes a template (a known structure of a related complex, e.g. trastuzumab bound to
HER2) for the models that support one.

| Model | Weights | Template |
|---|---|---|
| OpenFold3 | OpenBind, preview 2 | Yes |
| Protenix | v2, v1 | Yes |
| Boltz | Boltz-2 | Yes |
| Boltz | Boltz-1 | No |
| Mol-1 | base | Yes |
| ESMFold2 | release | No |

**Template is the thing to care about.** We have a known trastuzumab–HER2 complex, so we can hand
the folder the answer for the target and let it spend its confidence on the binder. ESMFold2 (and
Boltz-1) fold the target unguided, so for binders they are a weaker check — the PDF says a
template-taking model "gives a fairer check". ESMFold2 still works; use it for cheap triage, not
for the number we rank on.

## RFD4-Proteina

From NVIDIA and the Baker Lab. Designs structure and sequence together. One Docker image per
model, **research preview**. Four tasks per image:

| Task | Takes | Produces |
|---|---|---|
| `design` | an annotated structure | miniproteins, VHHs, Fv or new CDR loops |
| `refold-prepare` | your best designs | the inputs for refolding them with Predict Structure (all models above available) |
| `refold-score` | those refolds | scores against RFD4-Proteina's own pass criteria |
| `finetune` | your own structures (incl. an antibody task mix) | a further-trained design model |

`design` exposes: **number of designs**, **seed**, **recycling schedule**, **sequence
randomness**, **hotspot resampling**, **partial diffusion** (refine an earlier design) and
**inverse folding** (new sequences for a kept backbone).

### Weights — pick the model by choosing its image

| Weight | What it is | Use it to |
|---|---|---|
| `release-2026-10-19` | NVIDIA's general RFD4-Proteina model | Design general proteins and miniproteins |
| `antibody-2026-10-30` | NVIDIA's antibody model | Design or redesign CDRs on a fixed antibody framework |
| `her2-2026-11-07` | The antibody model, fine-tuned by Apheris on HER2 binders from the trastuzumab FACS screen | Redesign trastuzumab's CDRH3. Set `--sequence-tsr-k` to **2** (balanced) or **1** (exploratory) for more varied loops |
| `her2-novel-2026-11-09` | The antibody model, trained by Apheris on pairs of high and low binders from the same screen | Get mostly new CDRH3 loops with the most confident predicted fit to HER2 |

**The HER2 weights only redesign CDRH3.** To change any other CDR, use `antibody-2026-10-30`.

## The benchmark, and the trap inside it

PDF numbers, trastuzumab CDRH3 task:

| Weight and setting | Known binders | Pass novelty filter | Interface error (Å) |
|---|---|---|---|
| `antibody-2026-10-30` (not fine-tuned) | 0% | 100% | 8.2 |
| `her2-2026-11-07`, conservative | 21% | 0% | 9.4 |
| `her2-2026-11-07`, balanced | 21% | 6% | 9.1 |
| `her2-2026-11-07`, exploratory | 0.3% | 74% | 9.1 |
| `her2-novel-2026-11-09` | 4% | 86% | 6.8 |

Read it in this order:

1. **The best-binding setting is the one that gets us zero submissions.** `her2-2026-11-07`
   conservative recovers measured binders 21% of the time — and passes the novelty filter **0%**
   of the time. A known binder fails the novelty filter by definition. Those designs are
   **rejected by abguard**. They never reach Adaptyv. 21% of nothing.
2. **Balanced barely fixes it** — 21% known binders, **6%** pass. Still a rejection machine.
3. **Exploratory inverts the problem**: 74% pass, but 0.3% known binders. It gets through the
   gate and tells us almost nothing about whether the loop binds. Note though that the "known
   binders" column is **not** a benefit for designs we intend to submit — it counts designs
   abguard will reject — and exploratory has the **same** interface error as balanced, 9.1 Å. So
   between the two `her2-2026-11-07` settings exploratory loses nothing we can use and yields
   ~74 eligible designs per 100 against balanced's ~6. That is why exploratory is our diversity
   arm; reasoning in full in `docs/decision-log.md` [10:55].
4. **`her2-novel-2026-11-09` is the only row that is good at both ends**: 86% pass *and* the best
   interface error in the table, **6.8 Å** (vs 9.1–9.4 for every `her2-2026-11-07` row and 8.2 for
   the un-fine-tuned antibody model).

**What that implies, per track:**

| Track | Run | Why |
|---|---|---|
| **Optimisation** (CDRH3; needs >=3 CDRH3 mutations from trastuzumab AND from all 610,109 known CDRH3s - target >=6, see `abguard.md`) | `her2-novel-2026-11-09` as the default; `her2-2026-11-07` **exploratory** (`--sequence-tsr-k 1`) as the diversity arm | Only settings with a pass rate that survives abguard, and her2-novel has the best interface error |
| **De novo** (<70% identity to any known antibody; >=2 CDRH3 mutations) | `her2-novel-2026-11-09`, or `antibody-2026-10-30` if we need CDRs other than H3 | Novelty is the binding constraint on this track; `antibody-2026-10-30` passes 100% but has found 0% known binders |
| Anything touching CDRH1/H2/L | `antibody-2026-10-30` | HER2 weights physically cannot |

The weight/setting choices in that table are the decisions recorded in `docs/decision-log.md`
[10:55]. **If these two files ever disagree on a weight, a setting or a flag, `decision-log.md`
wins** and this file gets edited to match.

Do **not** spend H100 hours on `her2-2026-11-07` conservative or balanced. Their designs are mostly or entirely unsubmittable.
If someone wants the conservative or balanced output, it is useful as a *reference set* (what the
model thinks a binder looks like), not as candidates.

The PDF says it plainly: *filter designs before ranking them.* Run `abguard` on a batch **before**
you score it, not after.

## The check loop

```
design  ->  refold-prepare  ->  predict (any Predict Structure model)  ->  refold-score
```

`refold-score` scores against RFD4-Proteina's pass criteria: **interface PAE**, **binder pLDDT**,
**RMSD to the design**.

**Important:** for the HER2 exercise **the pass column stays empty**. Do not wait for a pass flag
that will never arrive. Rank on:

- `min_ipae`
- `iptm`
- `binder_plddt`

Use a template-taking model for the refold (OpenFold3 — which also covers the prize condition).

## Where the guide lives

Hackathon data bucket, read-only creds already on the VM:

```
s3://apheris-oslo-hackathon/rfd4-proteina/docs/      # step-by-step guide, example inputs,
                                                     # ready-made HER2 script
aws s3 sync s3://apheris-oslo-hackathon/rfd4-proteina ./data/rfd4-proteina
```

Open **`Tutorial.html`**. Whoever runs the first design job reads that first and posts the exact
command in Slack so the rest of us do not rediscover it.

Credentials: on the VM already, and in the Slack folder
(`Files from slack/extracted/participant-05/`). Never paste a key into this repo —
`<REDACTED - see Slack folder>`.

If a module does not run, find the Apheris team on site. That is faster than debugging it.
