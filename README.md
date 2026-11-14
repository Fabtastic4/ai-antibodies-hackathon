# Fab4 — AI × Antibodies Hackathon (Oslo, 14 Nov 2026)

Team **fab-tastic-four** / `team-4`, 6 people. We are improving **trastuzumab** against **HER2**
on the optimisation track: CDRH3 redesigns, submitted as Fabs.

**Pitch submission deadline 18:00.** Presentations 18:05–19:00, awards 19:30.

- [Where we are](#where-we-are)
- [Run it](#run-it)
- [The website and keynote](#the-website-and-keynote)
- [The pipeline](#the-pipeline)
- [The task](#the-task) · [scoring](#how-we-are-scored) · [hard filters](#hard-filters--abguard) · [submission shape](#submission-shape) · [pitch](#pitch-criteria) · [prizes](#prizes)
- [Docs](#docs) · [Repo map](#repo-map) · [Open questions](#open-questions)

## Where we are

> Full picture, in a browser: **[`docs/status-report.html`](docs/status-report.html)** (the funnel,
> the novelty/affinity trade-off, the measured SPR ceiling) and
> **[`docs/run-sheet.html`](docs/run-sheet.html)** (progress, owners, the clock).

**The ranked 20 exist:** [`designs/submission.csv`](designs/submission.csv) (our table, with scores
and reasoning) and [`designs/fab-tastic-four.csv`](designs/fab-tastic-four.csv) (the `abguard`-format
hand-in). All 20 are Fabs on the optimisation track, 4–7 CDRH3 mutations from trastuzumab, light
chain wild-type.

The funnel, as counted from the files by `python3 pipeline/status.py`:

| Stage | Designs | |
|---|---|---|
| Generated (RFD4-Proteina, two batches) | 400 | `designs/raw/` |
| Eligible (pass the `abguard` novelty gate) | 210 | 52.5% of generated |
| Unique heavy chains | 191 | 91.0% of eligible |
| Shortlisted (keep paratope contact G103) | 35 | [`designs/shortlist_g103.csv`](designs/shortlist_g103.csv) |
| Ranked for submission | 20 | 18 from batch 2, 2 from batch 1 |

What each judged axis rests on, for the 20:

| Axis | Evidence in `submission.csv` | Coverage | Caveat |
|---|---|---|---|
| Binding / epitope | `cofold_epitope_frac`: share of the 19 published 1N8Z epitope residues the Boltz-2 co-fold touches | 18 of 20 | Not ipTM or PAE — the hosted lane returns neither. Ranks 1–10 hit 5–11 epitope residues; ranks 13–20 co-fold off-epitope (0 of 19) and are demoted, not hidden; ranks 11–12 have no co-fold |
| Thermostability | `predicted_ddg`: ESM-2 650M pseudo-log-likelihood | 20 of 20 | A proxy, labelled as one in `thermostability_basis`. Not a ddG in kcal/mol; nothing hosted predicts thermostability |
| Expression | `netsolp_solubility_min` | 20 of 20 | Floor 0.4960, calibrated on 190 measured binders; all 20 clear it |

**ipTM cross-check.** OpenFold3 ipTM now exists for all 210 eligible designs and Boltz-2 ipTM for
139 of batch 1: [`reports/iptm-of3-vs-boltz2-all210.csv`](reports/iptm-of3-vs-boltz2-all210.csv).
The two models barely agree on which design binds (Pearson r = 0.15), so the 20 stay ranked on
epitope contact. On OpenFold3 the 20 score 0.47–0.63 against a field median of 0.57.
[`designs/top31-consensus.csv`](designs/top31-consensus.csv) is the two-model consensus shortlist,
all batch 1 — a cross-check, not a submission candidate.

Built but not used to rank the 20: the thermostability stage
[`pipeline/thermostability.py`](pipeline/thermostability.py) (issue #10), the VH–VL interface
`stab-ddg` job (`scripts/stab_ddg_*`), and two learned affinity models —
[`pipeline/score/affinity_model.py`](pipeline/score/affinity_model.py) and
[`pipeline/score/affinity_v2/`](pipeline/score/affinity_v2/README.md).

## Run it

No credentials, no GPU; `python3` 3.9+ and `bash` only. Under a minute.

```bash
bash pipeline/selftest.sh        # 12 checks: determinism, science, negative controls, rank refusal
bash pipeline/run.sh             # the whole pipeline, every batch
bash pipeline/run.sh --list      # which stages need hardware you do not have
python3 pipeline/status.py --how # the funnel, with a command to re-derive each number
```

Off the VM, `run.sh` runs the local stages, skips the remote ones cleanly and falls back to their
committed outputs. Its last stage **refuses to write a submission** when a judged axis has no
score, rather than rank on proxies; the committed `submission.csv` is produced by
[`pipeline/score/apply_cofold_rank.py`](pipeline/score/apply_cofold_rank.py) from the co-fold
evidence. Walkthrough for a judge or a new machine: **[`docs/REPRODUCE.md`](docs/REPRODUCE.md)**.

## The website and keynote

A local site that shows each of the 20 designs in 3D against HER2, which CDRH3 residues changed,
and how each compares with wild-type trastuzumab. The pitch keynote lives in the same site, with
the viewer as its live-demo slide.

```bash
python3 viz/server.py                 # then open http://127.0.0.1:8765
python3 viz/server.py --host 0.0.0.0  # also prints a LAN URL for the room
```

| Page | What it is |
|---|---|
| `http://127.0.0.1:8765/` | The viewer: design list, 3D structure, CDRH3 changes, improvement over wild type, scores, provenance |
| `http://127.0.0.1:8765/keynote.html` | The 10-slide keynote. Slide 9 is the live viewer. Arrow keys or the bottom bar to move, `n` for speaker notes |

Standard library only, nothing to install. The 3D panel needs the co-fold structures in
`results/cofold/<id>/model.cif`, which are not in git, and 3Dmol.js from the network; every
number works without either. Loading the site bills nothing. Details and the inference lanes:
[`viz/README.md`](viz/README.md).

## The pipeline

| Stage | What it does | Needs | On a laptop? |
|---|---|---|---|
| fetch | HER2–trastuzumab structure 1N8Z | network, or `--offline` | yes |
| epitope | interface at 4.5 Å: 19 residues, span 557–605 | stdlib | yes |
| paratope | which of trastuzumab's key contacts each design keeps | stdlib | yes |
| gate | `abguard` novelty, liability, validation | team VM | no — verdicts committed |
| solubility | NetSolP floor | VM binary | no — scores committed |
| refold | Boltz-2 co-fold on Nebius | Nebius key | no — metrics committed |
| rank | ranked table → `designs/submission.csv` | stdlib | yes |

Generation (RFD4-Proteina CDRH3 redesign) runs outside `run.sh`: see
[`pipeline/generate/design.sh`](pipeline/generate/design.sh). Stage-by-stage detail is in
[`pipeline/README.md`](pipeline/README.md).

Setup for the VM, Nebius and credentials: **[`docs/SETUP.md`](docs/SETUP.md)**. Credentials live only
in the Slack folder (`credentials.private.json`); `*.private.json` is gitignored. **Never commit a
key or paste one into a chat** — point tools at `$NEBIUS_CREDS`. Sixteen teams share the platform
and a model's first call can wait 15 minutes, so start long jobs early.

## The task

Source of truth: the organisers' task PDF (`ai-antibodies-hackathon-apheris.pdf`, in the Slack
folder; pasted in [`docs/task.md`](docs/task.md)). Where the pre-read guide or the event site
disagree with it, the PDF wins.

Improve **trastuzumab** against **HER2**. Submissions are **VHH, scFv or Fab** — not whole IgG.
Two tracks, and **the track is decided for us by `abguard`, not chosen**: a design that misses its
track's criteria is rejected, never reclassified.

| Track | Criteria (all must hold) |
|---|---|
| De novo | < 70% sequence identity to any known antibody **and** ≥ 2 CDRH3 mutations from every known CDRH3 |
| Optimisation | everything else (≥ 70% identity to trastuzumab); valid only if the CDRH3 is **≥ 3 mutations from trastuzumab *and* from every one of the 610,109 CDRH3s `abguard` knows** |

There is **no 70% CDRH3-identity threshold** to clear; identity only picks the track. The real
optimisation bar is the mutation count against all 610,109 known CDRH3s, so 3 mutations from
trastuzumab is necessary but nowhere near sufficient. Measured on our first batch, by distance from
trastuzumab: **3–4 mutations → 0/12 eligible, 5 → 44%, 6+ → 79–89%.** Details in
[`docs/abguard.md`](docs/abguard.md).

Identity comparison is type-aware: a VHH is compared against known VHHs and heavy chains; scFv and
Fab are split into paired chains and compared as paired antibodies. Tags and linkers are stripped
first (`immunum`).

### How we are scored

Adaptyv measures every design that gets tested and compares it to the **measured** trastuzumab
baseline (task PDF p8):

| Judged property | Measurement |
|---|---|
| Binding to HER2 | SPR |
| Epitope preservation | competitive binding against trastuzumab |
| Thermostability | direct measurement |

Tier = how many of the three beat the baseline. **S = 3/3, A = 2/3, B = 1/3, 0/3 = unsuccessful.**
Ties and regressions do not count.

**Teams are ranked on S-tier count first**, then A, then B. Ten designs that each improve one
property lose to two that improve all three, so we optimise for designs that plausibly move all
three axes, not for volume.

### Hard filters — `abguard`

A failing design is not submitted. Do not hand-check; run the gate on the VM:

```bash
bash pipeline/filter/gate.sh            # exit 0 = eligible, non-zero = not a submission
```

- Format is **VHH, scFv or Fab** (Fab goes in as `kind=paired`)
- **No unpaired cysteines**, per chain and per domain
- `immunum` numbering confidence **≥ 0.1**
- Length **≤ 250 aa per chain** (not VH + VL combined); canonical 20 amino acids only
- Novelty: ≥ 3 CDRH3 mutations (optimisation) or ≥ 2 (de novo) from **every** known CDRH3
- Soft, but it decides whether we get measured at all: expression

`abguard` is pre-installed on the team VM at `~/.local/bin/abguard` — **login shell only**, so
scripts need `bash -lc`. The tool enforces more than the PDF states;
[`docs/abguard.md`](docs/abguard.md) is the record of what it actually does. Off the VM,
[`scripts/novelty_distance.py`](scripts/novelty_distance.py) reproduces its novelty verdict.

### Submission shape

A ranked list of **up to 20 designs**, any mix of tracks (the tracks are evaluated independently).
Only the **top N** gets tested:

| | Designs tested |
|---|---|
| Every team, whatever happens | 4 |
| 1st place | +12 → 16 |
| 2nd place | +8 → 12 |
| 3rd place | +4 → 8 |
| Each of the 6 judges nominates one favourite team | +2 each |

Rank order matters more than list length: design #1 is tested in every scenario, #17 almost never.

### Pitch criteria

| Weight | Criterion |
|---|---|
| 40% | **Judgment** — clear reasoning behind the molecules we chose |
| 20% | Execution — reproducible pipeline in this GitHub repo |
| 20% | User fit — what the design is for, and who needs it |
| 20% | Path to value — credible route to real use, for the molecule or the method |

More in [`docs/pitch-and-rubrics.md`](docs/pitch-and-rubrics.md).

### Prizes

From task PDF p9. The event site says "3,000 USD" instead; the PDF wins.

- **€3000 total, split equally between the two tracks.** Per track: **€800 / €500 / €200**.
- **Best Pitch: extra $500** on the day (the PDF writes this one in dollars).
- **AMASS** picks the team with the best use of their platform → one month free. Each team also gets
  $100 in AMASS API credits; one person per team claims them at platform.amass.tech (task PDF p6).

## Docs

| | |
|---|---|
| **Status** | [`status-report.html`](docs/status-report.html) · [`run-sheet.html`](docs/run-sheet.html) · [`decision-log.md`](docs/decision-log.md) (why each call was made, timestamped) |
| **Pitch** | [`pitch-and-rubrics.md`](docs/pitch-and-rubrics.md) · the 5-minute keynote, *The Novelty Wall*, 10 slides with speaker notes — a private Claude artifact, team access only, so it is linked from Slack rather than here |
| **Running things** | [`REPRODUCE.md`](docs/REPRODUCE.md) · [`SETUP.md`](docs/SETUP.md) · [`pipeline/README.md`](pipeline/README.md) |
| **The gate** | [`abguard.md`](docs/abguard.md) · [`probe-findings.md`](docs/probe-findings.md) |
| **Science** | [`epitope.md`](docs/epitope.md) · [`optimisation-track-plan.md`](docs/optimisation-track-plan.md) · [`hackathon-brief.md`](docs/hackathon-brief.md) (molecule and model primer) |
| **Tools and data** | [`tools-nebius.md`](docs/tools-nebius.md) · [`tools-apheris.md`](docs/tools-apheris.md) · [`data-inventory.md`](docs/data-inventory.md) · [`vm-data.md`](docs/vm-data.md) |
| **Task and pitch** | [`task.md`](docs/task.md) · [`pitch-and-rubrics.md`](docs/pitch-and-rubrics.md) · [`apheris-slides.md`](docs/apheris-slides.md) · [`workplan.md`](docs/workplan.md) |

## Repo map

```
pipeline/  the reproducible run: run.sh, selftest.sh, status.py
           generate/ -> score/ -> filter/, plus thermostability.py
viz/       the website: 3D design review and the keynote (python3 viz/server.py)
scripts/   one-off tools: novelty distance, G103 shortlist, stab-ddg prep, VM data fetch
designs/   raw/ (the two generated batches), shortlist_g103.csv,
           submission.csv (the ranked 20), fab-tastic-four.csv (the hand-in)
reports/   every score table and where it came from; run provenance files
data/      inputs: target structure, bucket extracts (large files stay out of git)
docs/      see the table above
tests/     expected outputs the self-test byte-compares against
```

`Files from slack/` (organiser handouts and credentials) and `nebius-runs/` are local only and
gitignored.

## Open questions

- **Apheris OpenFold and the prize money.** The participant guide says "to qualify for that prize,
  include Apheris' version of Openfold in your pipeline". The task PDF's prize section neither
  repeats nor contradicts this. If we want the €3000, assume it must appear in the pipeline.
  **TODO: confirm with an organiser or the Apheris team on site.**
- **Team size.** The event-site FAQ says "Maximum team size is 5 people"; we are 6. The task PDF is
  silent. **TODO: confirm a 6-person team is eligible.**
- **`abguard` `novelty-report` oddity.** It prints a `--no-novelty: prior art was not checked`
  warning even when a reference is passed, and its nearest-neighbour column only ever reports
  `trastuzumab`. `team-validate` uses the full reference correctly. Cosmetic bug, or a second code
  path?
- **IP.** Tested designs are **published on Proteinbase under the open ODC-BY licence** — sequence,
  predicted structure, design method, measurements, our names. Relevant to "path to value": nothing
  we submit stays private.

Closed: the "≥ 2 vs > 2 mutations" wording (`abguard` enforces ≥ 3) and the supposed 70%
CDRH3-identity bar (it does not exist) — both in [`docs/abguard.md`](docs/abguard.md).

Links: [event site](https://oslo-ai-antibodies-hackathon.vercel.app/) ·
[terms](https://proteinbase.com/competitions/anthropic-adaptyv-2026/terms)
