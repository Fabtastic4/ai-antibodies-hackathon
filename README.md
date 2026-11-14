# Fab4 — AI × Antibodies Hackathon (Oslo, 14 Nov 2026)

Team **fab-tastic-four** / `team-4`, 6 people. Task dropped 09:30. **Design list + pitch due 18:00.**

Source of truth: the organisers' task PDF (`ai-antibodies-hackathon-apheris.pdf`, in the Slack folder).
This README is the 60-second version. Deeper docs are linked, not duplicated.

## The task

Improve **trastuzumab** against its target **HER2**. Submissions are **VHH, scFv or Fab** — not whole IgG.
Two tracks: **de novo design** (new antibody, original epitope preserved) and **optimisation**
(point mutations on trastuzumab). **The track is decided for us by `abguard`, not chosen** — a design
that misses its track's criteria is rejected, never reclassified.

| Track | Criteria (all must hold) |
|---|---|
| De novo | < 70% sequence identity to any known antibody in known databases **and** ≥ 2 CDRH3 mutations from every known CDRH3 |
| Optimisation | everything else (≥ 70% identity to trastuzumab); valid only if the CDRH3 is **≥ 3 mutations from trastuzumab *and* from every one of the 610,109 CDRH3s abguard knows** |

> Measured on our own batch 1, not read off the PDF — see **[`docs/abguard.md`](docs/abguard.md)**.
> There is **no 70% CDRH3-identity threshold** to clear: identity only picks your track. The real
> optimisation bar is the mutation count, counted against all 610,109 known CDRH3s, so 3 mutations
> from trastuzumab is necessary but **nowhere near sufficient**. Batch 1, 129 real designs:
> **91 eligible (70.5%), zero hard errors, every rejection on novelty.** By distance from
> trastuzumab: **3–4 mutations → 0/12, 5 → 44%, 6+ → 79–89%.** **Target ≥ 6.**

Identity comparison is type-aware: a VHH is compared against known VHHs and heavy chains; scFv and Fab
are split into paired chains and compared as paired antibodies. Tags and linkers are stripped first
(`immunum`).

## How we are scored

Adaptyv measures every design and compares it to the **measured** trastuzumab baseline:

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

Do not hand-check these. **Run the gate:**

```bash
bash pipeline/filter/gate.sh            # on the VM; exit 0 = eligible, non-zero = not a submission
```

- [ ] Format is **VHH, scFv or Fab** (Fab goes in as `kind=paired`). Not a whole IgG
- [ ] **No unpaired cysteines**, per chain and per domain
- [ ] `immunum` numbering confidence **≥ 0.1** ("is it an antibody?")
- [ ] Length **≤ 250 aa per chain** — *not* VH + VL combined. Canonical 20 amino acids only, no `X`
- [ ] Novelty: ≥ 3 CDRH3 mutations (optimisation) or ≥ 2 (de novo) from **every** known CDRH3
- [ ] Soft, no filter but it decides whether we get measured at all: expression. Prior Adaptyv rounds
      improved once teams scored candidates with **Aggrescan 3D, SoluProt, NetSolP, ProteinMPNN
      (soluble weights)**

`abguard` is pre-installed on the team VM at `~/.local/bin/abguard` — **login shell only**, so
scripts need `bash -lc`. It is not a Foundry Docker module. Its novelty reference is bundled and on
by default; nothing to build. Full write-up: **[`docs/abguard.md`](docs/abguard.md)**.

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

- **€3000 total, split equally between the two tracks.** Per track: **€800 / €500 / €200** for 1st / 2nd / 3rd.
  So a track can be diversified across or bet on.
- **Best Pitch: extra $500** on the day.
- **AMASS** picks the team with the best use of their platform → one month free. Each team also gets
  $100 in AMASS API credits; one person per team claims them at platform.amass.tech.

## Start here

1. **[`docs/SETUP.md`](docs/SETUP.md)** — VM access, Nebius, JapanFold, credentials. Do this first.
2. **[`docs/workplan.md`](docs/workplan.md)** — who is doing what, and the run order.
3. Long jobs queue (first call to a model can wait 15 min; `mosaic` and `esmfold2` ~22 min). Start those
   before the short folds. 16 teams share the platform.

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

- ~~The task PDF says optimisation needs "at least 2 mutations" on p2 but "strictly more than 2" in
  the hard-filter list.~~ **Closed 13:10** — `abguard` enforces **≥ 3** and says so in every
  rejection message. No mentor needed.
- ~~Optimisation requiring **< 70% CDRH3 identity to trastuzumab** is a large change for a "point
  mutation" track.~~ **Closed 13:10 — the premise was wrong.** `abguard` never computes a CDRH3
  identity threshold. The ≥70% figure only classifies a design as a trastuzumab variant rather than
  de novo; our CDRH3 variants sit at 98–99% whole-sequence identity and are perfectly valid
  optimisations. See [`docs/abguard.md`](docs/abguard.md) §3.
- Still open, and the only `abguard` question worth a mentor's time: `novelty-report` prints a
  `--no-novelty: prior art was not checked` warning even when a reference is passed, and its
  nearest-neighbour column only ever reports `trastuzumab`. `team-validate` uses the full reference
  correctly. Cosmetic bug, or a second code path?
- The pre-read guide's numbers (≤10 designs, ~5 tested, team max 5, 3000 USD tied to Apheris OpenFold)
  are superseded by the task PDF everywhere they disagree. Use the PDF.
- Links: event site https://oslo-ai-antibodies-hackathon.vercel.app/ ·
  terms https://proteinbase.com/competitions/anthropic-adaptyv-2026/terms
