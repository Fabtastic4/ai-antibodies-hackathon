# Pitch — answers to all four judging rubrics

Written 12:40. Owner: Josef (W5). Everyone reads it before 17:00 rehearsal, because Q&A hits
whoever ran the thing, not whoever presented it.

Weights: **Judgment 40% · Execution 20% · User fit 20% · Path to value 20%.**
User fit + path to value = 40%, the same as Judgment. Two of these four rubrics are not about
science at all, and until now nothing in the repo addressed them.

`[FILL]` marks a number that requires a run we have not done. **A `[FILL]` left in at 17:00 is a
hole in the pitch** — either the run happens or the claim comes out.

---

## 1. Judgment — 40%

What the judges are testing: did you make defensible choices, can you show where each number came
from, and do you know what you don't know.

### The headline answer — lead with this

> The organisers gave us 454 VHH–antigen pairs **measured not to bind**, and told us **21 of them
> score AlphaFold3 ipTM ≥ 0.7**. So at the threshold most teams will treat as "this binds," roughly
> **5% of genuinely non-binding pairs get through**. That is not enough to rank 20 designs on. So we
> use structural confidence as a *filter* and rank on something measured: a CDRH3→affinity model
> trained on the **524,346 FACS variants**, tested on the mutation range our designs actually
> occupy.

Held-out test metrics: `[FILL — lever 1]`. Confusion matrix in `reports/`.
Structure filter cutoff: `min_ipae [FILL]`, `iptm [FILL]`.

**Do not overstate this, it is the claim most likely to be challenged.** Two honest limits, both of
which we volunteer before a judge finds them:

- **21/454 is a ~4.6% false-positive rate, not a scandal.** The defensible claim is "ipTM cannot be
  the sole ranker," **not** "ipTM is unreliable." A structural-biology judge will know the
  difference and will respect the narrower claim more.
- **Those negatives are VHH–antigen pairs across various antigens.** Our candidates are
  trastuzumab-derived scFv/Fab against HER2. Different modality, different target — so they
  calibrate the metric *in general*, they are not a matched control for our pipeline. Say
  "indicative," not "calibrated," unless we have run our own refolds on them.

### Four more decisions, each with its basis

**The novelty trap, and why we run `her2-novel-2026-11-09`.** The organisers' own table: the weight
that recovers measured binders 21% of the time passes the novelty filter **0%** of the time. A known
binder fails novelty by definition, so those designs are rejected by `abguard` before anyone
measures them — 21% of nothing. `her2-novel-2026-11-09` is the only row good at both ends: 86% pass
*and* the best interface error in the table, 6.8 Å vs 8.2–9.4. Operational consequence: **we filter
before we rank**, because ranking a pool that still contains known binders spends compute we don't
have. (`TASK p5–6`)

**We cannot reach S-tier on CDRH3 alone — so we didn't try.** Teams are ranked on S-tier count
first; S-tier is 3 of 3; one of the three is thermostability. The HER2 weights redesign **CDRH3
only**, and CDR loop mutations rarely raise Tm — they more often lower it. A CDRH3-only pipeline is
therefore structurally capped at A-tier however good its binding is. We pair every loop redesign
with stability work outside the loop, and we treat VHH/scFv/Fab format as a thermostability
decision with a written reason. *This is the single most non-obvious thing we figured out about the
task; say it out loud.*

**Refold with a template, and not with ESMFold2.** We hold a trastuzumab–HER2 complex (1N8Z), so we
hand the folder the answer for the target and let it spend its confidence on the binder. ESMFold2
folds the target unguided, which is an unfair check for a binder — it is our second opinion, never
our ranking fold. (`TASK p5–6`)

**We report no ipTM from Boltz2.** That output has none on the Nebius platform. Where we need an
interface number from Boltz2 we count cross-chain contacts in the mmCIF and label it as exactly
that. (`RECIPES §2`)

### What we don't know — volunteer this, don't wait to be asked

- **None of pLDDT, PAE, ipTM or ipSAE is a KD.** They order candidates; they do not predict the SPR
  number we're judged on.
- **Our affinity model is valid inside a neighbourhood, not everywhere.** The 524k library varies
  CDRH3 only, up to 10 positions. Designs inside that neighbourhood — which is where
  optimisation-track designs live — are scored by the model. Anything outside it is flagged and
  scored structurally instead. Count of candidates flagged out-of-distribution: `[FILL]`.
- **`stab-ddg` returns binding ddG, not folding stability** `[VERIFY — Kevin]`. Thermostability is
  measured directly by Adaptyv, so if that's what it gives us, our thermostability evidence comes
  from elsewhere and we say so. No binding-ddG column gets labelled "thermostability."
- **An unresolved ambiguity in the spec.** `TASK p2` says "at least 2" point mutations, `p3` and
  `p7` say "more than 2." We built to **> 2** and let `abguard` arbitrate. We asked an organiser.
- **We missed our own 11:15 launch window.** When it became clear we had three hours of build time,
  we cut generation volume rather than cutting the calibration work — fewer designs, each with
  evidence behind it. Ten designs improving one property lose to two improving all three.

---

## 2. Execution — 20%

What the judges are testing: can someone else run this, and do the numbers have provenance.

- **Every stage writes a file the next stage reads.** `generate/ → score/ → filter/ →
  designs/submission.csv`. A judge can run it on a target we have never seen.
- **No anonymous numbers.** Every score column names its model and version. Every submission row
  carries weight, settings, seed and the Nebius run id (`op-xxxx`) or Foundry job id.
- **Multiple seeds, spread reported** — not the best run.
- **`designs/` and `results/` are append-only.** New batch, new file. A rejected design is marked
  rejected in its own file with a reason; rows are never deleted.
- **Branch per workstream**, one person merges to `main` after 16:00, so the final state is one
  person's responsibility.
- **Secrets never entered the repo.** Credentials referenced by path or `NEBIUS_CREDS`.
- **One unseen case, end to end, before the pitch.** `[FILL — which target]`. The judges will do
  this to us; better that we do it first.

Demo if asked: `[FILL — the one command]`.

---

## 3. User fit — 20%

What the judges are testing: do you know who this is for. "Pharma" is not an answer.

### Who

**A biologics team sitting on a stalled program and a pile of multimodal data that doesn't speak to
itself.** A FACS screen from two years ago. A hundred-odd SPR points. Some predicted structures. A
molecule that nearly worked and a team that moved on. The organisers' framing was "reviving a
real-life project from a set of data of different modalities" — that is not a hackathon conceit, it
is the most common state of an antibody program.

Today, reviving one means a scientist spending weeks re-deriving what their own data already says.
Our pipeline turns that pile into a ranked, eligibility-checked design list in hours, and tells you
which of your old assays to trust.

### Why trastuzumab/HER2 is exactly the right proving ground — not just the data we were given

Trastuzumab is off-patent. The commercial activity on HER2 is **biobetters**: same epitope, better
affinity, better thermostability, better developability. Look at what we're judged on — SPR binding,
epitope preservation by competitive binding, thermostability. **The judging criteria are the
biobetter target product profile.** That alignment is not luck, and it's worth naming:

| Judged axis | What it is commercially |
|---|---|
| Binding (SPR) | efficacy, and dose |
| **Epitope preservation** | **clinical precedent retained — the regulatory de-risking that makes a biobetter financeable** |
| Thermostability | formulation, subcutaneous delivery, cold-chain cost |

Epitope preservation is the one that looks like a scientific nicety and is actually the commercial
crux: a molecule that binds HER2 somewhere else is a new drug with a new risk profile. One that
binds *the trastuzumab epitope* better inherits a decade of clinical evidence.

### Why it runs where it runs

Apheris Foundry executes **inside the user's own infrastructure**. Our pipeline therefore works for
the user whose data cannot leave the firewall — the hospital FACS screen, the proprietary SPR table,
the partner's structures under a restrictive MTA. That user is currently locked out of most
AI-design tooling, and they are the user with the most un-mined measured data. This is the group we
are for.

---

## 4. Path to value — 20%

What the judges are testing: is there a credible route from this to real use.

### The asset is the ranker, not the molecules

Say this plainly, because it's the strongest thing we have:

> The 20 designs are this round's output. **The model that ranked them is the compounding asset.**
> Adaptyv measures our designs and returns SPR. Those measurements go back into the affinity model
> as new training data, and the next round's ranker is better than this one's. We're not handing
> over a list, we're handing over a loop that tightens every time someone runs an assay.

That is active learning on a wet-lab loop, and it is the thing a biologics team can actually buy.

### The route, in order

1. **Days — already in motion.** Every team gets 4 designs measured whatever happens; placement adds
   more. Our designs are measured this round, so the loop closes in days, not quarters. Traditional
   affinity maturation on a program like this is months of campaign work.
2. **Weeks — close the loop once.** Retrain on the returned SPR, re-rank, resubmit. Report whether
   round 2 beat round 1. That single number is the entire commercial claim, and it's measurable
   immediately.
3. **Months — target-agnostic.** Swap the complex and the measured screen; nothing in the pipeline
   is HER2-specific except the fine-tuned weights and the novelty set. Trastuzumab is our test case
   because it has public measured data. The method is the product.

### What would have to be true for this to work at scale

Name these; a path to value with no preconditions reads as naive.

- **More measured negatives.** 454 is enough to show ipTM is a leaky filter, not enough to train a
  sharp one. Negatives are the scarce resource in this field and nobody publishes them.
- **A real folding-stability predictor in the loop**, plus a Tm assay. Thermostability is one third
  of the tier and the axis with the thinnest computational support — ours included.
- **The novelty constraint is an artefact of the exercise, not of drug discovery.** A real program
  wants the best binder; the hackathon requires a *novel* one. In production that filter is replaced
  by freedom-to-operate analysis, which has different thresholds.

### What this is not

We are not claiming a drug. No immunogenicity assessment, no developability package beyond the
in-silico flags, no in-vivo anything. This is a pipeline that produces a ranked, eligibility-checked
shortlist with the evidence attached — which is the step that currently takes a team weeks.

---

## "What makes this different, and would industry use it?"

This will be asked. The answer that scores is not the most exciting one.

### Start by conceding what is not novel

Say this first. It buys credibility for everything after it, and an industry judge already knows it:

> Nothing in our method is new science. Training a sequence–activity model on display/NGS screening
> data and using it to rank designs is standard practice in ML-driven antibody engineering. That
> AlphaFold-family confidence scores are weak affinity predictors is well documented. Filtering for
> eligibility before spending compute is just engineering discipline.

A team that claims novelty here gets corrected by the panel. A team that says the above and then
explains *why they did the standard thing properly in three hours* is making a judgment argument.

### What is actually differentiated

**Relative to the other teams today, not relative to the field:** in a one-day hackathon the default
is to run the generator and sort by confidence score. We spent our scarcest resource — the three
hours — on the ranking evidence rather than on design volume, because we worked out that generation
is not the bottleneck. That is a prioritisation claim, and it is defensible.

The specific judgment calls that are ours: refusing the weight with 21% binder recovery because it
passes novelty 0% of the time; noticing the CDRH3-only tooling leaves a third of the tier to chance
and designing around it; reporting our model's accuracy on the ≥ 4-mutation subset we're actually
allowed to submit rather than the flattering full-split number. None of those are inventions. All of
them are the difference between a pipeline that works and one that looks like it works.

### The industrial proposition, in the only unit that matters

**Measurement is the bottleneck in industry, not design.** Anyone can generate a million sequences.
Nobody can assay a million sequences. A biologics group is rate-limited by SPR capacity, plate
count, protein production and calendar time.

So the value of a better ranker is expressible directly in money:

> If ranking lifts the hit rate on a 96-well SPR plate from ~5% to ~15%, that is three times fewer
> plates per lead, and weeks off the campaign. The designs are not the product — the **reduction in
> wasted assay slots** is the product.

That is the sentence a biologics director responds to. **We cannot demonstrate that lift today** —
it requires the round-2 measurement that closes the loop. Say that it is the number we would go and
get, not a number we have.

### The genuinely interesting angle — and it is the sponsor's, not ours

A sequence–activity model is only as good as the measured library behind it, and **in industry those
libraries are fragmented and unshareable**: inside one company's LIMS, under an MTA, in a CRO's
system, in a hospital's records. The reason this approach underperforms its potential in the real
world is not algorithmic, it is that the data cannot be pooled.

Apheris Foundry runs the compute **inside the data holder's infrastructure**. That makes the
interesting version of this pipeline a *federated* one: train the ranker across several
institutions' screening data without any of them exporting it. Three partners' libraries make a
materially better ranker than one, and today none of them can combine them.

We cannot build that in an afternoon and should not claim to have. But it is the credible route from
what we built to something a pharma would actually deploy, and it is worth naming because it shows
we understand why the platform we were given exists.

### Where it can be used today, honestly

| | |
|---|---|
| **Usable now** | Any target with (a) a complex structure and (b) a measured variant library. Narrow but real, and growing fast as display + NGS gets cheaper. Affinity maturation of an existing lead is the natural fit — which is exactly the optimisation track. |
| **Not usable now** | As a product. No prospective validation, no developability or immunogenicity package, one target, three hours old. The repo is a method and an evidence trail, not a platform. |
| **What would change that** | One closed loop (round 2 beats round 1), a larger measured negative set, a real folding-stability predictor, and a Tm assay in the loop. |

**Pitch-safe phrasing.** Say "a correct instantiation of current best practice, built in three hours,
with the evidence trail to prove each choice." Do not say "novel," "breakthrough," or "state of the
art." The first is defensible under questioning. The others are not.

## Likely Q&A — have an answer ready

| Question | Answer |
|---|---|
| "Why should we believe your ranking?" | Held-out test split on 524k measured variants, plus a structural cutoff calibrated against 454 measured non-binders. `[FILL]` accuracy. |
| "Your ipTM is lower than team X's." | ipTM ≥ 0.7 admits 21 of the organisers' 454 measured non-binders. We're not optimising that number, and we can show why it doesn't survive contact with their own data. |
| "How do you know the epitope is preserved?" | Contact overlap with the 1N8Z epitope list in `docs/epitope.md`, in PDB and IMGT numbering. `[FILL]` overlap fraction per design. It's judged by competitive binding, so we treat drift as a lost property. |
| "What's your thermostability evidence?" | `[FILL]` — and if it's thin, say it's thin and say which axis we chose to spend our three hours on. Do not dress up a binding-ddG number. |
| "What would you do with another day?" | Close the loop once on returned SPR. Expand the negative set. Get a folding-stability predictor in. |
| "What broke?" | We missed the 11:15 launch window and had three hours, so we cut generation volume to protect the calibration. Here's the decision-log entry. |

## What we build, and what we actually show

Decided 12:35, with `pipeline/` containing nothing but a README and ~3h to the generation cutoff.

### No webapp. Here is the reasoning, so nobody relitigates it at 15:00

- **Nothing in the rubric rewards a UI.** Judgment, Execution, User fit, Path to value. Execution
  is "a judge can rerun this on a target we've never seen" — that is a CLI and a provenance trail,
  not a frontend.
- **What we hand in is a CSV, a repo and a pitch.** A webapp is not a submission artifact.
- **It costs exactly the hours lever 1 needs.** An afternoon spent on a frontend is an afternoon not
  spent on the affinity model, and the affinity model *is* the Judgment score.
- A polished UI over empty results reads worse than a plain table full of real numbers. Judges at a
  science hackathon have seen the former many times.

If someone wants to build it, that is a post-17:40 activity on their own time.

### The five files that have to exist (pipeline/ is empty — this is the whole build)

| File | Does | Owner | By |
|---|---|---|---|
| `pipeline/filter/novelty.py` | CDRH3 → `(is_duplicate, identity_to_tras, n_mutations)` against all 525,063 provided loops | Abdelrahman | 13:15 |
| `pipeline/score/affinity_model.py` | train on the 524k FACS splits; `predict(cdrh3) → class + score`; prints held-out test metrics | Danielius | 14:00 |
| `pipeline/score/rank.py` | join novelty + abguard verdict + refold-score + affinity + developability → one row per candidate | Kevin | 14:30 |
| `pipeline/report/make_report.py` | the table + figures → `reports/report.html`, regenerated on every run | Kevin | 15:30 |
| `run_all.sh` | target in → ranked table out, one command, for the unseen-case test | Mark | 16:00 |

Five files. Nothing else. Anything not on this list is scope creep today.

### The one visual worth building — build this before any other figure

**The calibration plot.** x-axis ipTM, y-axis count, two overlaid distributions: the organisers' 454
measured non-binders, and our candidates. A vertical line at 0.7 with the 21 non-binders sitting to
the right of it, annotated.

That single figure *is* the headline Judgment argument, made visible in one image. It is the slide
people will remember, and it takes ~20 minutes of matplotlib once the refolds are back. Second
figure, if there's time: the affinity model's held-out confusion matrix. Third: epitope overlap per
design. In that order, and stop when the clock says stop.

`reports/report.html` is generated by `make_report.py`, not hand-written — a report the pipeline
emits is an Execution artifact; a report a human typed is a document.

### Skills: not now, maybe at 15:30

Do not build Claude Code skills on the critical path. `agent/nebius-scientific-ai/SKILL.md` and
`forge.py` are already on the box and already work — use them, don't rebuild them.

**But** there is a cheap, genuinely good version of this *after* generation stops: wrap `run_all.sh`
in a thin `SKILL.md` so the pipeline is driven in natural language. Claude Code is pre-installed on
every team's VM with credits from Anthropic, and our stated user is a bench scientist who does not
write Python. "Our pipeline ships as a skill, so the scientist who ran the FACS screen can rerun the
ranking themselves" is a real path-to-value and user-fit answer, and it is a 20-minute markdown file
once the CLI exists. **Strictly optional, strictly after 15:30.**

### The deck

Content is this file; it does not need rewriting into slides from scratch. Six slides:

1. The user and the stalled program — who this is for *(user fit)*
2. The task, and the novelty trap in one table *(judgment)*
3. **The calibration plot** — why we don't rank on ipTM *(judgment, the money slide)*
4. The pipeline, five boxes, and the ranked table with provenance *(execution)*
5. The loop: Adaptyv SPR → retrain → round 2 beats round 1 *(path to value)*
6. What we don't know, and what we'd do with another day *(judgment again — close here, not on a win claim)*

`TODO: confirm the pitch length and format with an organiser.` We are building to six slides and
assuming short; if it's 10 minutes we add the data-exploration detail, if it's 3 we drop slides 4
and 6. Nobody should discover this at 17:00.

## Rehearsal discipline

The workplan puts rehearsal #1 at 17:00, full and timed and out loud, and #2 at 17:20 with the fixes
from #1. **The narrative does not start at 17:00** — this file gets drafted from the moment lever 1
has a test number, with placeholder numbers in the slots.

Lead with the 454 negatives. It is the most interesting sentence we have.
