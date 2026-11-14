# Official task — AI × Antibodies Hackathon (Oslo, 14 Nov 2026)

**Source.** `ai-antibodies-hackathon-apheris.pdf`, posted by Aygul Minnegalieva (organizer) at
09:56 on 14 Nov 2026 in Slack channel `fab-tastic-four`
(`app.slack.com/client/T0CG4UPMU8J/C0CHM1M1NCE`), plus the operational channel messages from the
same morning. The PDF itself is dated 6 November 2026.

Section 1 below is the PDF text reproduced faithfully: headings, criteria, tables, thresholds and
the worked allocation example are the organizers' own. Only PDF-extraction damage was repaired —
broken line wraps, repeated page footers, and the three figures, whose axis labels came out of the
extractor as unreadable soup and are given here as lists and tables with the same content. Nothing
was paraphrased or dropped. Our own interpretation does not go in this file — it goes in
`docs/decision-log.md`.

Deadline: pitch + design submission close 18:00 local.

---

## 1. Task description (as written in the PDF)

### The task

For the hackathon, participants have an ambitious task: improve an existing antibody, using the
capabilities of Apheris Foundry, Nebius and JapanFold, coupled with multi-modal data from the
hackathon organisers. This simulates a real-life scenario of reviving a real-life project from a
set of data of different modalities.

Namely, we want participants to develop a robust antibody pipeline, and show how it performs on a
well-known antibody, trastuzumab. Given some amount of multi-modal data, participants can decide
to either design a completely new antibody while preserving the original epitope, or make point
mutations to an existing antibody while improving its affinity and thermostability. The designs for
both modes, which we call **optimisation** and **de novo design**, will be judged by three
conditions:

1. Design should have comparable or better binding to its target, HER2, as measured by SPR.
2. Design should preserve the binding epitope, as judged by competitive binding assay.
3. Design should improve an antibody's thermostability, as a proxy of real-life developability.

Designs improving only one or two of these properties will be ranked strictly lower than those
improving all 3. See judging criteria for details.

### How a design is tiered

*(Figure 1 in the PDF: one triangle per design, one axis per judged property. Axes are affinity,
epitope preservation, thermostability. A filled vertex marks a property that beat the baseline;
ties and regressions are hollow. Tiers are counted per design, against the measured trastuzumab
baseline.)*

| Tier | Properties improved on trastuzumab |
|---|---|
| S-tier | 3 of 3 |
| A-tier | 2 of 3 |
| B-tier | 1 of 3 |
| Unsuccessful | 0 of 3 |

### Criteria for de novo vs optimisation

Briefly, submissions can be of one of three types: VHH, Fab (paired-chain variable fragment) or
scFv (the same as Fab, but connected with a linker into one chain). A design is considered **de
novo** if it has less than 70% sequence identity to any known antibody in known databases, and
those must have at least 2 CDRH3 mutations away from trastuzumab. All other designs are considered
**optimisation** designs, and only optimisations with less than 70% CDRH3 identity to trastuzumab
and at least 2 mutations from any provided antibody are considered valid.

### How a design is classified and checked

Everything below runs inside `abguard`. The track is decided for you, not chosen by the team.

*(Figure 2 in the PDF, as a flow:)*

1. **Submitted design.**
2. **Extract antibody sequence** — `immunum` strips tags and linkers.
3. **Shared hard checks — every design.** Fails → rejected.
   - Numbering confidence at least 0.1 (is it an antibody?)
   - Format is VHH, scFv or Fab
   - Total length at most 250 amino acids
   - No unpaired cysteines
4. **Type-aware identity comparison** — VHH against known VHHs and heavy chains; scFv and Fab
   split into paired chains.
5. **Identity to nearest known antibody under 70%?**
   - **yes → de novo track.** Extra check, de novo only: at least 2 CDRH3 mutations away from
     trastuzumab. Fails → rejected.
   - **no → optimisation track.** Extra checks, optimisation only: CDRH3 identity to trastuzumab
     under 70%; more than 2 point mutations from any provided antibody. Fails → rejected.
6. **Eligible for submission.**

A design is never moved between tracks. If it misses its track's criteria it is rejected, not
reclassified.

Organisers will provide a command-line tool to check design validity. Informally, the tool first
extracts the antibody sequence (that is, excludes potential tags and linkers) with the `immunum`
library, and then performs a type-aware similarity comparison: a VHH design is compared with known
VHHs or heavy chains, while scFvs are split into paired antibodies and compared as paired
antibodies.

### Supporting data

Organisers provide two bodies of data: general VHH–antigen data, and trastuzumab-specific data.

**General**

1. **VHH–antigen true negatives** — unpublished
   - 454 pairs, 21 of which score AlphaFold3 ipTM at or above 0.7
   - SPR, no measurable binding
2. **Non-cognate VHH–antigen interactions** — unpublished
   - 2 data points
   - Binary off-target label, no affinity
3. **Cognate VHH–antigen affinities** — unpublished
   - 15 data points
   - SPR, all sub-micromolar
4. **Cognate and non-cognate VHH–antigen complexes** — published
   - 1.8M AI-generated structures from 106 cognate and 11,342 non-cognate pairings, predicted by
     AlphaFold3, Boltz-2 and Chai-1 with 50 samples each
   - Described in Smorodina et al. · Zenodo · archive.sigma2.no

These are pairs that were measured and found not to bind, which is what lets you calibrate a
structure-prediction confidence filter before trusting it to rank designs.

**Trastuzumab**

1. **CDRH3 variants vs HER2** — published
   - 524,346 variants, up to 10 mutated positions in CDRH3
   - FACS, three affinity classes
   - Published in Chinery et al. · Zenodo
2. **Optimisation designs** — published
   - Around 700 designs from the same study, 190 with measurable affinity measured by SPR

### Tooling

#### Computing environment

Each team gets its own virtual machine on Nebius AI Cloud: one NVIDIA H100 GPU, 16 vCPUs, 200 GB
RAM and a 500 GB disk, running Ubuntu 24.04 LTS. You connect over SSH. At the start we give each
team its machine's IP address and a private key.

The machines are shut down at the end of Saturday 14 November. Copy anything you want to keep
before then.

Pre-installed on every machine:

- Claude Code, with credits provided by Anthropic.
- Apheris Foundry models as Docker images, already downloaded. `foundry-toolkit module list` lists
  them; `Tutorial.html` (Hackathon VM tab) shows how to run each one.
- RCSB MCP, for fast access to known protein structures.
- Read-only credentials for the hackathon data bucket (`s3://apheris-oslo-hackathon`). Copy the
  data you need onto your machine, for example with
  `aws s3 sync s3://apheris-oslo-hackathon/<folder> ./data`. We may add more data or scripts there
  during the event.
- `abguard`, the command-line tool that checks your designs against the hard filters before
  submission.

If something doesn't work on your machine, find the Apheris team on site.

#### Apheris

Apheris Foundry delivers packaged drug-discovery functionality that runs inside the user's own
infrastructure. For the hackathon specifically, multiple models are available.

**Structure prediction.** Predict Structure (`predict`) predicts the 3D structure of a complex with
a co-folding model. Every model takes the same inputs and gives the same outputs, so you can swap
models without changing the rest of your pipeline. It takes a template (a known structure of a
related complex, such as trastuzumab bound to HER2) for the models that support one. Each model is
its own Docker image on your machine.

| Model | Weights | Template |
|---|---|---|
| OpenFold3 | OpenBind, preview 2 | Yes |
| Protenix | v2, v1 | Yes |
| Boltz | Boltz-2 | Yes |
| Boltz | Boltz-1 | No |
| Mol-1 | base | Yes |
| ESMFold2 | release | No |

**Protein design with RFD4-Proteina.** RFD4-Proteina, from NVIDIA and the Baker Lab, designs a
protein's structure and sequence together. In Foundry it runs as one Docker image per model, in
research preview. Each image has these tasks:

- `design`: generate miniproteins, VHHs, Fv or new CDR loops from an annotated structure. Settings
  cover the number of designs, the seed, the recycling schedule, sequence randomness, hotspot
  resampling, partial diffusion (refine an earlier design) and inverse folding (new sequences for a
  kept backbone).
- `refold-prepare`: pick your best designs and write the inputs for refolding them with Predict
  Structure. All the models above are available for refolding.
- `refold-score`: score those refolds against RFD4-Proteina's own pass criteria, such as interface
  PAE, binder pLDDT and RMSD to the design.
- `finetune`: train the design model further on your own structures, including an antibody task mix.

Pick the model by choosing its image:

| Weight | What it is | Use it to |
|---|---|---|
| `release-2026-10-19` | NVIDIA's general RFD4-Proteina model | Design general proteins and miniproteins |
| `antibody-2026-10-30` | NVIDIA's antibody model | Design or redesign CDRs on a fixed antibody framework |
| `her2-2026-11-07` | The antibody model, fine-tuned by Apheris on HER2 binders from the trastuzumab FACS screen | Redesign trastuzumab's CDRH3. Set `--sequence-tsr-k` to 2 (balanced) or 1 (exploratory) for more varied loops |
| `her2-novel-2026-11-09` | The antibody model, trained by Apheris on pairs of high and low binders from the same screen | Get mostly new CDRH3 loops with the most confident predicted fit to HER2 |

On the trastuzumab CDRH3 task, the HER2 weights move designs toward measured binders. The more
varied settings give mostly new loops that pass the optimisation challenge's novelty filter:

| Weight and setting | Known binders | Pass novelty filter | Interface error (Å) |
|---|---|---|---|
| `antibody-2026-10-30` (not fine-tuned) | 0% | 100% | 8.2 |
| `her2-2026-11-07`, conservative | 21% | 0% | 9.4 |
| `her2-2026-11-07`, balanced | 21% | 6% | 9.1 |
| `her2-2026-11-07`, exploratory | 0.3% | 74% | 9.1 |
| `her2-novel-2026-11-09` | 4% | 86% | 6.8 |

These weights only redesign CDRH3. To change other CDRs, use `antibody-2026-10-30`. A known binder
fails the novelty filter, so filter designs before ranking them.

To check designs, run `refold-prepare` on your designs, fold the prepared inputs with any Predict
Structure model, then score them with `refold-score`. ESMFold2 works too, but for binders a model
that takes a template gives a fairer check, because ESMFold2 folds the target unguided. For the HER2
exercise the pass column stays empty, so rank on `min_ipae`, `iptm` and `binder_plddt`.

A step-by-step guide with example inputs and a ready-made HER2 script is in the hackathon data
bucket under `rfd4-proteina/docs/`. Open `Tutorial.html`.

#### Nebius Scientific AI platform

Nebius Tools is a no-code, agentic platform for protein structure prediction, protein design, and
molecular dynamics. It can be used directly in your browser or connected to Claude as a skill.

You can find all available models and tools in the Apps section of the Workbench, and at
`sciai.nebius.cloud/models`. Setup files will be shared with you in a Slack folder.

#### JapanFold

JapanFold is a drug discovery platform serving open-source bio models at high throughput, with
native agent integrations for harnesses like Claude Code and Claude Science. It uniquely complements
our toolbox with RoseTTAFold3, OpenDDE and AF2-IG, which can be connected as a skill and called
directly from Claude Code.

#### AMASS

AMASS lets participants search scientific papers, clinical trials, patents and drug records with
plain-language questions in Claude, and every answer links back to the source. It is useful for
checking claims against primary sources and finding leads for antibody design.

- Claim your credits. Each team gets $100 in API credits. One person per team claims them:
  `platform.amass.tech`
- The AMASS page for the hackathon, with example use cases and antibody data to start from.
- A setup walkthrough, screen by screen.
- How to add AMASS to Claude, for anyone who does not code.
- Short video guides to the AMASS app.

Mix and match tools, and divide jobs across platforms.

### Design selection criteria

Designs should be VHH, scFv or Fab, and must pass our hard filters. After that, teams rank their own
designs based on internal criteria of the team.

#### Hard filters

Every submission is checked automatically by a CLI tool, `abguard`, which implements novelty and
designability checks for each antibody. A design that fails is not submitted. The constraints known
so far:

- Format: VHH, scFv or Fab.
- No unpaired cysteines.
- Somewhat of an antibody: numbering with at least 0.1 confidence with `immunum`.
- Maximal total length of 250 amino acids (whole length of a single scFv or VHH, or combined for VH
  and VL).
- Novelty: under 70% sequence identity to any known antibody for the de novo track, and under 70%
  CDRH3 sequence identity to trastuzumab plus strictly more than 2 point mutations from any data
  point provided.

#### General recommendations

For a design to be measured correctly, it needs to be expressed experimentally. While we don't have
any hard filters for that, previous experience of Adaptyv tells us that expression success improved
once participants started scoring candidates with Aggrescan 3D, SoluProt, NetSolP, and ProteinMPNN
with soluble weights. Please check the whole write-up here.

### Ranking and submission

#### Pitch day

On the hackathon day itself, participants' pitches will be judged according to the criteria
announced at the hackathon website:

| Weight | Criterion |
|---|---|
| 40% | Judgment — clear reasoning behind the molecules you chose. |
| 20% | Execution — a reproducible pipeline in a GitHub repo. |
| 20% | User fit — what your design is for, and who needs it. |
| 20% | Path to value — a credible route to real use, for the molecule or the method. |

Winners of the pitch day will be given extra design submissions, and subsequently a higher chance to
win the monetary prize after experimental validation. Namely:

- Each team gets 4 designs whatever happens.
- 1st place gets 12 extra designs (16 total).
- 2nd place gets 8 extra designs (12 total).
- 3rd place gets 4 extra designs (8 total).
- Additionally, each of the 6 judges nominates their favourite team with 2 extra designs.

#### Design submission

Prior to pitch evaluation, each team compiles a ranked list of up to 20 designs: 16, assuming they
will be winners, plus 4 extra in case of duplication between teams. Teams are free to submit any
proportion of de novo vs optimisation track designs, as those will be evaluated independently during
experimental validation.

After design submissions are distributed on the pitch day, each team's top-N submissions will be
submitted to Adaptyv for validation.

#### Example

- 1st place: Team A
- 2nd place: Team B
- 3rd place: Team C
- 4 judges nominate Team D as their favourite
- 1 judge nominates Team B as their favourite
- 1 judge nominates Team E as their favourite

*(Figure 3 in the PDF: how many designs each team gets tested. Every team submits a ranked list of
up to 20; the top N of that list goes to Adaptyv.)*

| Team | Reason | Base allocation | Pitch placement | Judge nomination | Total tested |
|---|---|---|---|---|---|
| Team A | 1st place | 4 | 12 | — | 16 |
| Team B | 2nd place, 1 judge | 4 | 8 | 2 | 14 |
| Team D | 4 judges | 4 | — | 8 | 12 |
| Team C | 3rd place | 4 | 4 | — | 8 |
| Team E | 1 judge | 4 | — | 2 | 6 |
| All other teams | no placement | 4 | — | — | 4 |

Every team is tested whatever happens. Placement and judge nominations only add to the base four.

### Experimental evaluation

Adaptyv will do cell-free expression of designs and then measure binding while preserving epitope
(as measured by competitive binding), and thermostability.

| Property | How it is measured | Who |
|---|---|---|
| Binding to HER2 | SPR | Adaptyv |
| Epitope preservation | Competitive binding against trastuzumab | Adaptyv |
| Thermostability | Direct measurement | Adaptyv |

Finally, we'll measure these values also for the reference antibody, trastuzumab. That is the
baseline every design is compared against.

### Post-evaluation ranking

Teams will be ranked by number of designs that were able to improve on all three properties (S-tier
designs), then on only two properties (A-tier designs), and only 1 property (B-tier).

- **S-tier** — improves on all three: affinity, epitope preserved, thermostability
- **A-tier** — improves on two of the three
- **B-tier** — improves on one of the three

Teams with most S-tier designs win. If equal, with most A-tier, and so on. Ten designs that each
improve one property lose to two designs that improve all three.

### Prizes

The total prize fund of €3000 will be equally distributed between submissions in two tracks, de novo
and optimisation. As a result, participants can either diversify their chances and submit some
designs for each track, or bet on one of the tracks only.

Teams on each track will win €800, €500 and €200 for 1st, 2nd and 3rd place respectively.

Best Pitch gets an extra $500 prize on the day.

Based on the pitches, AMASS will also select the team that demonstrates the best use of their
platform and award them one month for free.

---

## 2. From the Slack channel

Channel `fab-tastic-four`, 14 Nov 2026. Timestamps as Slack showed them.

### Davide (before 09:56) — team VM

> Team: team-4
> VM IP: 89.169.99.24
> User: hackathon

SSH key: delivered as a **Bitwarden Send link** posted in Slack —
`<REDACTED - Bitwarden Send link is in Slack, do not commit it>`. Never paste that URL, or the key
itself, into this repo.

Everyone in the team uses the same user and key, so we all share one home directory and one GPU.
Davide suggests a folder each (for example `~/<your name>`) so we don't overwrite each other's work.

Connecting, once the key is downloaded (macOS/Linux):

```sh
mv ~/Downloads/team-4 ~/.ssh/team-4
chmod 600 ~/.ssh/team-4
ssh -i ~/.ssh/team-4 hackathon@89.169.99.24
```

On Windows the same `ssh` commands work from PowerShell or WSL, with the key path adjusted.

### Aygul Minnegalieva, organizer (09:56) — 3 attachments

| Attachment | What it is |
|---|---|
| `participant-05.zip` | Set-up information for the Nebius Scientific platform. Extracted in the repo under `Files from slack/extracted/participant-05/` — start at `START-HERE.md`. |
| `japanfold-oslo-hackathon-codes 4.txt` | JapanFold key, in plain text. **Secret — do not open, quote or commit.** |
| `ai-antibodies-hackathon-apheris.pdf` | The task description transcribed in section 1. |

### Lluis Artus (10:22) — suggested pipeline

Quoted as posted:

> Accept antigen structure (formats mmcif of pdb) use biopython library
> Find Antibody-antigen interface using ANARCII. Use it to find the epitope-paratope aminoacids
> Create the input for either RFD4-Proteina or Bindcraft
> Filter the results based on solubility, pLDDT, ipSAE

### Mark Owusu Ayim (10:28, 10:38) — resource map

At 10:28, updates to the team Slack doc (`F0CHP7486BG`). At 10:38, attached
`hackathon-resource-map.pdf`:

> This is a resource file for all we need now, you can pass a quick review. But this should get ius
> started with a mental mapping in here.

It is a Nebius model table with measured first-call timings from 12 Nov 2026: 34 models with a
tested call in `forge.py`, ~60 hosted, 7 on the H100. Extracted copy of the text is in the session
scratchpad, not in the repo.

### GitHub handles, as posted

| Person | Handle |
|---|---|
| Mark Owusu Ayim (10:28) | `markowusu` |
| abdelrahman.many.07 (10:30) | `Mannypython1` |
| Kevin Singh (10:30) | `kevinsinghjay-python` |
| Lluis Artus (10:33) | `LluisArtusSuarez` |
| Danielius Stanevicius (10:34) | `Doonse` |

Josef added Claude to the channel at 10:42.

---

## 3. Open questions for the organizers

Things that are genuinely ambiguous in the PDF and change what we submit:

1. **Mutation count: "at least 2" or "strictly more than 2"?** The de novo vs optimisation section
   says optimisations need "at least 2 mutations from any provided antibody"; the `abguard`
   flowchart says "More than 2 point mutations from any provided antibody"; the hard-filters list
   says "strictly more than 2 point mutations from any data point provided". Safe reading: **≥ 3**.
2. **De novo CDRH3 requirement.** De novo is defined by <70% identity to any known antibody, and
   "those must have at least 2 CDRH3 mutations away from trastuzumab" — is the CDRH3 condition
   measured against trastuzumab only, or against the nearest provided antibody as well?
3. **Novelty reference set.** "Any known antibody in known databases" — which databases, and what
   does `abguard` actually search? Also: is "any provided antibody / any data point provided"
   the full 524,346-variant FACS set, or only the ~700 optimisation designs?
4. **Identity metric.** Not specified: how identity is computed (global vs CDR-only alignment, per
   chain or concatenated) for the 70% thresholds, and for Fab/scFv whether both chains must clear
   70% or just one.
5. **Submission cap.** The cap is 20, but 1st place plus judge nominations can exceed 16+2; if a
   team places and gets several nominations, can N exceed 20?
6. **"Improve" with no margin.** Tiering says ties and regressions do not count, but no minimum
   effect size or replicate count is given for SPR KD, competitive binding or Tm.
7. **Epitope preservation for de novo.** A de novo design must preserve the epitope, yet is scored
   by competitive binding against trastuzumab — is partial competition a pass?
8. **Our pre-read contradicts the PDF.** `docs/hackathon-brief.md` and the README (from the
   participant guide) say ~5 designs per team, ≤10 submitted, and a 3,000 USD Apheris+OpenFold
   prize conditional on using Apheris' OpenFold. The PDF says up to 20 ranked designs, base 4
   tested, €3000 split across two tracks, and states no OpenFold requirement. Treat the PDF as
   authoritative; confirm whether the OpenFold condition still holds.
