# Workplan — Saturday 14 Nov 2026

Backward-planned from the 18:00 submission. Task dropped 09:30. This file was written at 10:55.
**About seven hours left, of which the last two are not build time.**

What we hand in at 18:00: a ranked list of **up to 20 designs** (16 if we win, plus 4 spare in case
of duplication with another team), this repo, and a pitch. Every team gets 4 designs tested
whatever happens; placement only adds to that. Source: `scratchpad/task_apheris.txt` p7–8.

How we are scored on the day: **Judgment 40%**, Execution 20%, User fit 20%, Path to value 20%.
User fit + path to value is 40% — the same as Judgment. **The pitch narrative cannot start at
17:00.** It is a workstream from now (W5).

## Timeline

| Time | Milestone | Owner |
|---|---|---|
| 11:00 | 15-min standup. Claim a workstream. Every laptop: SSH to the VM works, `NEBIUS_CREDS` exported. No long discussion. | all |
| 11:15 | **Long jobs launched first, before anything short.** `mosaic` (~22 min first call), `esmfold2` (~22 min), `protenix-v2` (~20 min), `rfd4-proteina` (~6 min). Launch on the best input we have at 11:15, not the perfect one. | W1 + W3 |
| 11:30 | AMASS credits claimed ($100, one person per team). | W5 |
| 12:00 | HER2 target structure in `data/`, folded and sanity-checked. First Apheris Foundry job has returned something. Trastuzumab baseline sequence + numbering committed. | W1, W2 |
| 12:30 | Epitope residue list committed (`docs/epitope.md`): which HER2 residues trastuzumab touches, in **PDB residue numbers as well as IMGT**. Everything downstream depends on this. | W2 |
| 13:00 | `abguard` located on the VM and run once as a control. First candidate batch exists on both tracks. Scoring harness runs end-to-end on one design. | W1, W3, W4 |
| 14:00 | **Last big generation launch.** Second batch out the door. Bulk scoring running. Pitch skeleton written with placeholder numbers. | W3, W4, W5 |
| 15:00 | Draft ranked table with real numbers in `reports/`. Developability scores attached to every surviving candidate. | W4, W5 |
| 15:30 | **HARD CUTOFF: stop generating, start filtering.** No new generation job after 15:30. A job queued at 15:30 may still be waiting at 16:00. | all |
| 16:00 | Candidate pool frozen. `abguard` run on every candidate, verdict recorded. `designs/submission.csv` has its rows ranked. | W4, W5 |
| 16:30 | `docs/decision-log.md` complete. Score tables committed with provenance (model, weight, seed, run id). Repo clean and reproducible — that is the 20% Execution. | all |
| 17:00 | **Pitch rehearsal #1**, full, timed, out loud. Pitch prep slot per the event schedule. | W5 presents, all listen |
| 17:20 | Rehearsal #2 with the fixes from #1. | W5 |
| 17:40 | Freeze. Final `git push`. **Pull everything off the VM — the machines are shut down at the end of today** (task PDF p4). | all |
| 18:00 | Submission closes (event schedule). | W5 |
| 18:05 | Presentations (event schedule). | W5 |

Rule for the whole day: **if you are blocked for more than 20 minutes, post it in Slack.** Do not
debug a queue alone.

## Workstreams

| # | Workstream | Owner | Deliverable |
|---|---|---|---|
| W1 | VM + tooling, first Foundry job | Mark Owusu Ayim | Everyone can SSH in and run a job; `foundry-toolkit module list` output committed; one Predict Structure job returned; `abguard` working and documented in one command |
| W2 | Target + interface prep, epitope definition | Lluis Artus | HER2 structure in `data/target/`, trastuzumab–HER2 complex, `docs/epitope.md` with the epitope/paratope residue list in both numberings |
| W3 | Generation, both tracks | Abdelrahman (optimisation / CDRH3) + Danielius Stanevicius (de novo) | Candidate sequences in `designs/raw/`, one file per batch, with the weight, settings and seed in the file |
| W4 | Scoring + developability | Kevin Singh | `pipeline/score/` runs refold → refold-score on a batch; a table per candidate with `min_ipae`, `iptm`, `binder_plddt`, plus developability flags |
| W5 | Selection, pitch, user fit + path to value | Josef | `designs/submission.csv` ranked, `docs/decision-log.md`, and the pitch: who the molecule is for and the credible route to real use |

W2 posted the shape of the interface step in Slack already (antigen structure via BioPython →
interface via ANARCII → input for the generator → filter on solubility, pLDDT, ipSAE) — that is
W2 handing off to W3 and W4.

Handles, from `docs/task.md`: Abdelrahman `Mannypython1`, Kevin `kevinsinghjay-python`,
Lluis `LluisArtusSuarez`, Danielius `Doonse`. TODO: confirm GitHub handles for Josef and Mark.

## Critical path and what blocks what

```
credentials + VM (W1)
  └─> long jobs queued (W1/W3)        <- do this at 11:15, it is pure latency
  └─> abguard working (W1)            <- DONE 13:20. `bash pipeline/filter/gate.sh`, docs/abguard.md
  └─> target structure (W2)
        └─> epitope residue list (W2)
              └─> generation inputs (W3)
                    └─> refold + refold-score (W4)
                          └─> ranked table (W5)
                                └─> pitch numbers (W5)
```

**Queue discipline.** A first model call can wait 15 minutes, and 16 teams share the platform
(`START-HERE.md`). Measured first-call times from 12 Nov, ~25 jobs open (`resource_map.txt`):

| Start these early | First call | Short, run them while waiting | First call |
|---|---|---|---|
| `mosaic` | 22 min | `msa-search-pdb70` | 40 s |
| `esmfold2` | 22 min | `boltz2` | 80 s |
| `protenix-v2` | 20 min | `proteinmpnn` | 2 min |
| `esmfold2-fast` | 11 min | `nanobodybuilder2`, `antifold`, `abodybuilder3` | 2 min |
| `stab-ddg` | 12 min | `openfold3` | 3 min |
| `rfd4-proteina` | 6 min | `mdprecheck` | seconds |

Do not use `openfold2`: it failed twice on 12 Nov after burning 55 minutes each time. Use
`openfold3` or `boltz2`.

Never submit the same job twice — you only wait twice. A stuck run is queued: `forge.py status`.
After a storage error use `forge.py resume`, not a resubmit.

Split the machines: generation on our H100 VM, scoring on the hosted platform. That is where
parallelism comes from. Do not install a model that is already hosted.

## Git conventions for six simultaneous committers

Remote: `github.com/Fabtastic4/ai-antibodies-hackathon`. Branch `main` is what the judges read.

1. **Branch per workstream**, not per person: `ws1-setup`, `ws2-target`, `ws3-generate`,
   `ws4-score`, `ws5-pitch`. Two people on W3 share `ws3-generate` and stay in separate files.
2. **Commit small and often**, prefix the message with the workstream: `ws4: score batch 2`.
   A commit every 20 minutes beats one commit at 16:00.
3. **Path ownership.** Only the owner edits these; anyone else opens an issue in Slack instead.

   | Paths | Owner |
   |---|---|
   | `pipeline/env/`, `scripts/setup*`, `docs/vm.md` | W1 Mark |
   | `data/target/`, `data/task/`, `docs/epitope.md` | W2 Lluis |
   | `designs/raw/`, `pipeline/generate/` | W3 Abdelrahman, Danielius |
   | `pipeline/score/`, `reports/scores/` | W4 Kevin |
   | `designs/submission.csv`, `docs/*.md`, `reports/pitch/` | W5 Josef |

4. **Pull before push, rebase not merge:** `git pull --rebase origin main && git push`. No
   `--force` on a shared branch, ever.
5. **`designs/` and `results/` are append-only.** New batch = new file, named
   `<track>-<owner>-<batch>.csv`. Never edit or delete another person's rows; if a design is
   out, mark it rejected in your own file and say why. The submission table is assembled from
   these by W5, once.
6. **Secrets never enter the repo.** `*.private.json`, the JapanFold codes txt, SSH keys and the
   Bitwarden link stay in the Slack folder. Reference credentials by path or by `NEBIUS_CREDS`.
   `.gitignore` already covers them — check it before your first commit.
7. `results/` and `nebius-runs/` hold run ids and no keys, so they are safe to keep. Keeping them
   is how we show where each score came from. They are currently gitignored: if we want the run
   ids in the repo for Execution, W1 un-ignores `nebius-runs/*.json` deliberately, with a check
   that no key is inside.
8. **W5 is the only one who merges to `main`** after 16:00, so the final state is one person's
   responsibility.

## Definition of done for a design

Run this against any candidate before it goes in the submission table. All of it, in order.
Anything you cannot fill in is a blocker, not a rounding error.

Hard filters — `abguard` decides, we do not argue. **Do not hand-check these, run the gate:**

```bash
bash pipeline/filter/gate.sh designs/submission.csv   # on the VM. exit 0 = eligible
```

It converts our table to abguard's columns, writes `reports/novelty-report.csv` and
`reports/liability-report.json`, then gates. Verified working end to end on the VM at 13:20 —
both the fail path (exit 1) and the pass path (exit 0). Details and the measured numbers:
[`abguard.md`](abguard.md).

- [ ] Gate exits 0. That single check covers format, length, alphabet, cysteines, `immunum`
      confidence and novelty — it is the same tool the organisers run.
- [ ] Verdict and the novelty row recorded in the candidate's row (from `reports/novelty-report.csv`).
- [ ] Track recorded as abguard assigned it. **A design is never moved between tracks** — if it
      misses its own track's criteria it is rejected, not reclassified.

What the gate is actually enforcing, so generation aims at the right target:

- Length ≤ **250 aa per chain** — *not* VH + VL combined. Canonical 20 amino acids only.
- Cysteines paired per chain **and** per domain.
- Optimisation (≥70% identity to trastuzumab): CDRH3 **≥ 3 mutations** from trastuzumab *and from
  every one of the 610,109 known CDRH3s*, including the full 524k FACS screen. De novo: ≥ 2.
- **There is no < 70% CDRH3-identity requirement.** Identity only picks the track. Measured on
  batch 1 (129 real designs, `her2-novel-2026-11-09`, seed 1): **91 eligible, 70.5%, zero hard
  errors, all 38 rejections on novelty.** By distance from trastuzumab: **3–4 → 0/12, 5 → 44%,
  6 → 83%, 7 → 79%, 8 → 89%.** **Target ≥ 6 mutations.** 35 of the 38 rejections were ≥3 from
  trastuzumab and died on proximity to a *different* measured loop — the parent is not the
  binding constraint, the 524k screen is. Over-generate ~1.4× and dedupe on `heavy_sequence`
  (batch 1's 91 survivors held only 85 unique chains).

Ranking evidence — we rank our own designs, so the numbers have to exist:

- [ ] Refolded with a model that **takes a template** (OpenFold3, Protenix, Boltz-2, Mol-1), not
      ESMFold2: ESMFold2 folds the target unguided, which is an unfair check for a binder.
- [ ] `refold-score` run; `min_ipae`, `iptm` and `binder_plddt` recorded. For the HER2 exercise
      the pass column stays empty, so these three are the ranking (task PDF p6).
- [ ] Do **not** report an ipTM from Boltz2 on Nebius — that output has none (`RECIPES.md` §2).
      If you need an interface number from Boltz2, count cross-chain contacts in the mmCIF.
- [ ] Second opinion from a different predictor. Two models agreeing beats one high score.
      Where they disagree, record it as uncertainty.
- [ ] Epitope: contacts overlap the trastuzumab epitope list from `docs/epitope.md`. Judged
      experimentally by competitive binding, so epitope drift is a lost property, not a detail.
- [ ] Developability: at least one of Aggrescan 3D, SoluProt, NetSolP, ProteinMPNN with soluble
      weights (the organisers name these four, p7). Sequence liability motifs checked.
- [ ] Thermostability has a stated reason — this is 1 of the 3 judged properties and it is the
      one we are most likely to forget. `stab-ddg` gives binding ddG for named point mutations.
- [ ] Any liability fix was followed by **re-scoring binding**. A fix that breaks the interface
      is not a fix.

Provenance — this is the 40% Judgment:

- [ ] Row in `reports/` naming model, weight (e.g. `her2-novel-2026-11-09`), settings, seed and
      the Nebius run id (`op-xxxx`) or the Foundry job.
- [ ] If the candidate changed the ranking, there is an entry in `docs/decision-log.md`.
