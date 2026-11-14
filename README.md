# Fab4 — AI × Antibodies Hackathon (Oslo, 14 Nov 2026)

Team **fab-tastic-four** / `team-4`, 6 people.

> **Status report, in plain language: [`docs/status-eli5.html`](docs/status-eli5.html)** — open it in a
> browser. Where we are, why our best-gripping designs were rejected, and what the 525k measured
> CDRH3s say about where to look next. Every chart is drawn from
> [`reports/b1_novelty_distance.json`](reports/b1_novelty_distance.json); each one has a
> "grown-up version" line under it with the actual metrics.

Two different events — do not blur them:

- **09:30 — "Opening: welcome, task & mentor intro"** (event-site schedule; the participant guide says
  "Brief at 09:30" and "the task is released at 09:30 on the day"). The schedule is marked
  "preliminary and subject to slight changes".
- **09:56 — the task PDF actually landed in Slack**, posted by Aygul Minnegalieva, organizer
  (`docs/task.md`). The brief and the document are 26 min apart; dates and deadlines come from the
  document.

**Pitch submission deadline 18:00** (event-site schedule and participant guide "Submit by 18:00").
Then presentations 18:05–19:00, jury deliberates, awards 19:30 (event-site schedule).

Source of truth: the organisers' task PDF (`ai-antibodies-hackathon-apheris.pdf`, in the Slack folder).
This README is the 60-second version. Deeper docs are linked, not duplicated.

## The task

Improve **trastuzumab** against its target **HER2**. Submissions are **VHH, scFv or Fab** — not whole IgG.
Two tracks: **de novo design** (new antibody, original epitope preserved) and **optimisation**
(point mutations on trastuzumab). **The track is decided for us by `abguard`, not chosen** — a design
that misses its track's criteria is rejected, never reclassified.

| Track | Criteria (all must hold) |
|---|---|
| De novo | < 70% sequence identity to any known antibody in known databases **and** ≥ 2 CDRH3 mutations away from trastuzumab |
| Optimisation | everything else; valid only if < 70% **CDRH3** identity to trastuzumab **and** > 2 point mutations from any provided antibody |

Identity comparison is type-aware: a VHH is compared against known VHHs and heavy chains; scFv and Fab
are split into paired chains and compared as paired antibodies. Tags and linkers are stripped first
(`immunum`).

## How we are scored

Adaptyv measures every design **that gets tested** (see the submission cap below) and compares it to
the **measured** trastuzumab baseline — "we'll measure these values also for the reference antibody,
trastuzumab. That is the baseline every design is compared against" (task PDF p8):

| Judged property | Measurement |
|---|---|
| Binding to HER2 | SPR |
| Epitope preservation | competitive binding against trastuzumab |
| Thermostability | direct measurement |

Tier = how many of the three beat the baseline. **S = 3/3, A = 2/3, B = 1/3, 0/3 = unsuccessful.**
Ties and regressions do not count as improvements.

**Teams are ranked on S-tier count first**, then A-tier, then B-tier. Ten designs that each improve one
property lose to two designs that improve all three. So: do not optimise for volume. Optimise for
designs that plausibly move all three axes at once.

## Hard filters — `abguard` checklist

Run before anything goes on the submission list. A failing design is not submitted.

- [ ] Format is **VHH, scFv or Fab**
- [ ] **No unpaired cysteines**
- [ ] `immunum` numbering confidence **≥ 0.1** ("is it an antibody?")
- [ ] Total length **≤ 250 aa** (whole single scFv or VHH; VH + VL combined for Fab)
- [ ] Novelty: de novo → < 70% identity to any known antibody. Optimisation → < 70% CDRH3 identity to
      trastuzumab **and** strictly > 2 point mutations from any provided data point
- [ ] Soft, no filter but it decides whether we get measured at all: expression. Prior Adaptyv rounds
      improved once teams scored candidates with **Aggrescan 3D, SoluProt, NetSolP, ProteinMPNN
      (soluble weights)**

`abguard` is pre-installed on the team VM and organisers provide it as a CLI (task PDF p4, p7).
The constraints above are the PDF's own list, and it labels them "the constraints known so far" (p7) —
the tool may enforce more than this.

## Submission shape

- Ranked list of **up to 20 designs**, any mix of de novo and optimisation (the two tracks are evaluated
  independently). 20 = 16 assuming we win, + 4 spare in case of duplication between teams.
- Only the **top N** of that list gets tested. N depends on pitch day:

| | Designs tested |
|---|---|
| Every team, whatever happens | 4 |
| 1st place | +12 → 16 |
| 2nd place | +8 → 12 |
| 3rd place | +4 → 8 |
| Each of the 6 judges nominates one favourite team | +2 each |

Rank order matters more than list length: design #1 is tested in every scenario, #17 almost never.

## Pitch criteria

| Weight | Criterion |
|---|---|
| 40% | **Judgment** — clear reasoning behind the molecules we chose |
| 20% | Execution — reproducible pipeline in this GitHub repo |
| 20% | User fit — what the design is for, and who needs it |
| 20% | Path to value — credible route to real use, for the molecule or the method |

## Prizes

All from task PDF p9 unless noted. The event site says "3,000 USD" instead — the PDF wins, see the
contradictions list below.

- **€3000 total, split equally between the two tracks.** Per track: **€800 / €500 / €200** for 1st / 2nd / 3rd.
  So a track can be diversified across or bet on.
- **Best Pitch: extra $500** on the day (the PDF writes this one in dollars, not euros).
- **AMASS** picks the team with the best use of their platform → one month free. Each team also gets
  $100 in AMASS API credits; one person per team claims them at platform.amass.tech (task PDF p6).

## Start here

1. **[`docs/SETUP.md`](docs/SETUP.md)** — VM access, Nebius, JapanFold, credentials. Do this first.
2. **[`docs/run-sheet.html`](docs/run-sheet.html)** — the optimisation-route plan on one page: progress,
   the eligibility window, the three judged axes, owners and the clock. Open it in a browser.
3. **[`docs/workplan.md`](docs/workplan.md)** — who is doing what, and the run order.
4. Long jobs queue: a model's **first call can wait 15 min**, and `mosaic` and `esmfold2` are ~22 min
   (resource map). Start those before the short folds — the resource map says so directly.
   **Sixteen teams share the platform** (`START-HERE.md`, in the Slack folder: "Sixteen teams share
   this, so start long jobs early"), which is why queue position is the binding constraint today.

Credentials live only in the Slack folder (`credentials.private.json`, JapanFold codes txt). `*.private.json`
is gitignored. **Never commit a key or paste one into a chat** — point tools at `$NEBIUS_CREDS`.

## Repo map

```
docs/      task.md (Slack paste: VM, mentor pipeline), hackathon-brief.md (pre-read:
           molecule + model primer), SETUP.md, workplan.md, decision-log.md
pipeline/  the reproducible run: generate -> score -> filter
scripts/   one-off tools and glue
data/      inputs; data/task/ holds task attachments (large files stay out of git)
designs/   candidate sets + submission.csv (the ranked ≤20)
reports/   score tables (where every score came from), figures, pitch material
notebooks/ exploration
Files from slack/   organiser handouts + credentials. Not for committing secrets.
```

## Open questions / contradictions in the sources

- The task PDF contradicts itself: "at least 2 mutations from any provided antibody" (p2) vs "strictly
  more than 2 point mutations from any data point provided" in the hard-filter list (p7) and "More than
  2 point mutations" in the `abguard` flowchart (p3). Treat **> 2** as the bar — two of three say so.
  TODO: confirm with a mentor.
- Optimisation requiring **< 70% CDRH3 identity to trastuzumab** (p2, p3, p7) is a large change for a
  "point mutation" track: trastuzumab's CDRH3 is 11 residues, so it means ≥ 4 substitutions — see
  [docs/probe-findings.md](docs/probe-findings.md) §3 for the arithmetic and its one assumption.
  TODO: confirm with a mentor before committing the optimisation list.
- The pre-read material disagrees with the task PDF on four numbers. **The PDF wins.** The old numbers
  are not in this repo — they are on the event website and in the participant field guide, so here is
  each one with where it comes from:

| Pre-read source says | Task PDF says | Use |
|---|---|---|
| "end with **up to 10** designs to present" / "Select up to 10 to validate" (participant guide, design-funnel + judging sections) | "each team compiles a ranked list of **up to 20** designs: 16, assuming they win, + 4 spare" (p7) | **20** |
| "**~5 tested**" / "We can probably test five designs per team" (participant guide) | base **4** tested for every team, +12/+8/+4 by placement, +2 per judge nomination, max 16 (p8, Figure 3) | **4 base, up to 16** |
| "Prize money of **3,000 USD**" (event site, prizes + FAQ) | "total prize fund of **€3000**... equally distributed between... two tracks", €800/€500/€200 per track (p9) | **€3000, split per track** |
| "Apheris and Openfold are the monetary prize sponsors; **to qualify for that prize, include Apheris' version of Openfold in your pipeline**" (participant guide, prizes) | prize section names no such condition (p9) | **unresolved — see below** |

- The Apheris-OpenFold qualification condition is **not superseded, just unrepeated**. The task PDF
  does not restate it and does not contradict it. Treat it as live: if we want the €3000, assume
  Apheris OpenFold must appear in the pipeline. **TODO: confirm with an organiser or the Apheris team
  on site** (task PDF p4: "If something doesn't work on your machine, find the Apheris team on site").
- **Team size:** the event-site FAQ says "Maximum team size is 5 people"; we are 6. The task PDF says
  nothing about team size, so the FAQ is not superseded. The schedule does list "team adjustments (if
  necessary)" at 09:00, which is presumably how we got to 6. **TODO: confirm with an organiser that a
  6-person team is eligible.** Do not assume it is fine because nobody stopped us.
- Links: event site https://oslo-ai-antibodies-hackathon.vercel.app/ · competition terms
  https://proteinbase.com/competitions/anthropic-adaptyv-2026/terms (linked from the event-site FAQ).
- IP, from the same FAQ: tested designs are **published on Proteinbase under the open ODC-BY licence**
  — sequence, predicted structure, design method, measurements, our name and team name. Submitting
  gives Anthropic and Adaptyv permission to use and publish the design; they do not become its owners.
  Relevant to the 20% "path to value" criterion — nothing we submit stays private.
