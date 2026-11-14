# abguard: setup, the gate, and what the control run measured (W1)

> Written by Claude Code as W1, under Mark's direction — see the Authorship note in
> [`decision-log.md`](decision-log.md). "I" below is the agent. Every measurement here was run on
> the VM and names a command that reproduces it; check them rather than trusting them.

Status: working. Control run done on the VM at 13:10. The 13:00 gate item is met.
Everything below is observed output from `abguard` on our VM, not from the task PDF.

## It is a PATH problem, not a missing tool

```
/home/hackathon/.local/bin/abguard -> ~/.local/share/uv/tools/abguard/bin/abguard
```

Installed 11:17 today as a `uv` tool. `~/.local/bin` is on `PATH` in a login shell only.
So it works when you SSH in and type `abguard`, and it does not work from:

- `ssh hackathon@... 'abguard ...'` (non-login shell)
- scripts run with `#!/bin/bash` without `-l`
- anything spawned by a non-login harness

A second, older copy exists in a teammate-built uv venv (`abguard 0.1.0` + `immunum 2.0.0`,
built 11 Nov): `/home/hackathon/.cache/uv/archive-v0/LQ7GYqqqANyUP63G/bin`. Confirm the two
agree (`abguard --version`) before trusting either; its `direct_url.json` points at a repo that
no longer exists, so treat that cached venv as fragile.

If a script needs it, use `bash -lc "abguard ..."` or the absolute path. **Do not reinstall it**
and do not go looking for a Docker module — it is not a Foundry image, and it is not in
`foundry-toolkit module list`. (`foundry-toolkit` itself needs `foundry-toolkit login`; that is a
separate thing and blocks nothing, every image is already pulled.)

## Use the gate, not the raw commands

```bash
bash pipeline/filter/gate.sh                     # designs/submission.csv
bash pipeline/filter/gate.sh designs/batch2.csv  # one generation batch
```

Verified end to end on the VM at 13:20: fail path exits 1, pass path exits 0. It converts our
table to abguard's columns, writes `reports/novelty-report.csv` and
`reports/liability-report.json`, then gates. See [`../pipeline/README.md`](../pipeline/README.md).

The raw commands, for reference:

```bash
abguard team-validate <submission.csv>            # gate: exit 1 if any row fails
abguard team-validate <submission.csv> --drop -o kept.csv   # keep the survivors, exit 0
abguard novelty-report <submission.csv>           # per-design detail, filters nothing
abguard liability-report <submission.csv>         # LAP liability counts
```

- The reference database is bundled and on by default — `INFO using the reference bundled
  with abguard`. No `--reference-db` needed. We do not have to build one.
- Exit code is the verdict: 1 without `--drop` if anything fails, 0 with `--drop`.
  The scoring harness should use the no-`--drop` form as the gate.
- `--no-novelty` exists but turns the novelty gate off. **Never use it for a submission check.**

### Required columns — our `designs/submission.csv` does not match

`team-validate` requires exactly:

```
sequence_id, kind, heavy_sequence, light_sequence, design_description
```

`kind` is one of `vhh` / `scfv` / `paired`; rows are partitioned on it and each gets its own
schema. Resolved: `pipeline/filter/to_abguard.py` generates this view from our table, so
`designs/submission.csv` keeps its rank/score/provenance columns and nobody hand-maintains two
tables. One additive change was needed: `submission.csv` gained a `light_sequence` column, because
a Fab has two chains and the old header had nowhere to put the second one.

Read off `abguard/schemas.py` on the VM, since the PDF does not state these:

| Rule | Detail |
|---|---|
| `sequence_id` | primary key — must be unique, or the row is dropped |
| Fab | submitted as `kind=paired`, both `heavy_sequence` and `light_sequence` required |
| `vhh` / `scfv` | single chain in `heavy_sequence`; `light_sequence` **must be empty** (rule `has_no_light_chain`). An scFv's linker goes in the one string |
| Length | **≤ 250 aa per chain**, not VH + VL combined. Our docs had this wrong |
| Alphabet | the 20 canonical amino acids only — no `X`, no gaps |
| Cysteines | checked per chain *and* per domain (`heavy_domain_cysteines_are_paired`) |
| `design_description` | non-empty. The converter falls back to method/model/seed if we left the reasoning blank |

`to_abguard.py` enforces all of these before abguard sees the file, so a mistake costs one named
row rather than a confusing `0 of 20 valid`.

## What the control run changes about our plan

### 1. The mutation bar is 3, and the open TODO is closed

`abguard --help`, verbatim: a design must differ from trastuzumab and from every known CDRH3 by
**at least 3 mutations in CDRH3** if it is a trastuzumab variant (≥70% identity), or 2 if it
is de novo. Every rejection message says `a novel design needs at least 3`.

So the README / `task.md` ambiguity ("at least 2" vs "strictly more than 2") resolves to ≥ 3
for the optimisation track. `task.md` open question 1 is answered. Build to 3.

### 2. Distance is measured against the whole provided set, not just trastuzumab

This is the one that costs us designs. A synthetic control with 3 mutations from trastuzumab
was still rejected:

```
[novelty] ctrl_3mut: CDRH3 SRWKGEGFYQMDY is 2 mutation(s) from SRWGGEGFYPMDY
          in tz_her2_facs_3classes_524346; a novel design needs at least 3
```

The nearest neighbour was a *different* loop in the 524,346-variant FACS set. The bundled
reference holds 610,109 CDRH3s across three tables:

| Table | What it is |
|---|---|
| `trastuzumab` | the parent loop, `SRWGGDGFYAMDY` |
| `trastuzumab_her2_spr_all_768` | the 768-row SPR set |
| `tz_her2_facs_3classes_524346` | the full 524k FACS screen |

So `task.md` open question 3 is answered: it is the full FACS set, not just the ~700
optimisation designs. A design must be ≥3 mutations from *every measured loop*, and the FACS set
densely covers the neighbourhood around trastuzumab's CDRH3 — exactly the neighbourhood
`her2-2026-11-07` was fine-tuned to generate in. That is the mechanism behind the PDF's 0% and
6% novelty pass rates, and it confirms the `her2-novel-2026-11-09` choice in the decision log on
measured grounds rather than inferred ones.

Practical consequence: 3 mutations from trastuzumab is necessary but nowhere near sufficient.

### Measured on batch 1 — the number to plan against

129 real designs from `~/mark/runs/b1-novel-s1` (`her2-novel-2026-11-09`, seed 1), sampled
mid-run. `designs/raw/batch1-b1-novel-s1.csv`, gated with `pipeline/filter/gate.sh`.

91/129 eligible — 70.5%. Zero hard errors: no format, length, alphabet, cysteine or `immunum`
failure in 129 designs. All 38 rejections are novelty.

| CDRH3 mutations from trastuzumab | Passed |
|---|---|
| 2 | 0/3 |
| 3 | 0/5 |
| 4 | 0/7 |
| 5 | 4/9 (44%) |
| 6 | 15/18 (83%) |
| 7 | 44/56 (79%) |
| 8 | 25/28 (89%) |
| 9 | 3/3 |

**Target ≥ 6 mutations.** 5 is marginal, 3–4 is a dead zone. 35 of the 38 rejections were ≥3
mutations from trastuzumab and died on proximity to a *different* measured loop — the parent is
not the binding constraint, the 524k screen is.

Do not steer generation toward fewer mutations: `her2-novel-2026-11-09` produces 6–8 unprompted
(102/129 at ≥6), and that distribution is why it passes. Over-generate ~1.4× the slots needed.

> Superseded: an earlier synthetic probe (100 random CDRH3 mutants, `designs/probe.csv`) gave
> 3 → 12%, 4 → 64%, 5 → 92% and I recommended designing to 5. Real output gives 0/12 at 3–4.
> Random substitution scatters across sequence space; RFD4 draws loops toward the same motifs the
> FACS screen already explored, so it lands in the densest part of the reference. The probe is kept
> only as the contrast — plan against batch 1.

Also from this run: 91 survivors hold only 85 unique heavy chains. `competition-validate`
rejects sequences shared between teams, so dedupe on `heavy_sequence` before ranking.

### 3. There is no 70% CDRH3-identity threshold to hit

`novelty-report` reports `identity_to_trastuzumab` as whole-sequence identity — our CDRH3
variants score 0.986–0.996, and they are still classified `novelty_class = novel` with
`required_cdrh3_mutations = 3`. abguard never computes a CDRH3-identity threshold; the ≥70%
identity figure only *classifies* a design as a trastuzumab variant rather than de novo.

So `README.md` and `workplan.md` are wrong where they say optimisation is "valid only if < 70%
CDRH3 identity to trastuzumab". Nothing requires us to rewrite 30% of the loop. The real bar is
the mutation count in §1–2. Both docs should be corrected before anyone designs to the wrong
target. (`README.md` open TODO 2 — "a large change for a point-mutation track" — dissolves: it was
never the requirement.)

### 4. Trastuzumab's CDRH3 is the 13-mer `SRWGGDGFYAMDY` — and this one bites any local check

Confirmed live: `novelty-report` returns `cdrh3 = SRWGGDGFYAMDY`, `cdrh3_confidence = 0.875`. We
had the 11-mer `WGGDGFYAMDY` from the structure, and **the HER2 assay tables use the 10-mer core
`WGGDGFYAMD`**. The code warns about exactly the mistake that invites:

> *the HER2 assay tables name its 10-mer core `WGGDGFYAMD`; comparing a design's IMGT CDR3 against
> those cores would hand every design three free mutations from the flanks alone.*

**Any local novelty pre-check must compare IMGT 13-mers**, which means re-extracting the reference
CDRH3 from each table's `vh_sequence` rather than reading its `cdrh3` column. Read the column and
every design looks three mutations newer than it is, so the check passes designs abguard rejects.

### 5. Two traps that reject silently

- **Cysteines are checked twice**: the whole column count must be even *and* each domain's count
  must be even independently. An scFv with one spare Cys in VH and one in VL is even overall and
  still fails.
- **Swapped heavy/light columns are rejected.** `paired` needs heavy to number `H` and light `K`/`L`.

Full error vocabulary: `invalid_amino_acids`, `sequence_too_long`, `unpaired_cysteine`,
`numbering_failed`, `wrong_domain_count`, `missing_sequence`, `unexpected_sequence`,
`duplicate_sequence_id`, `unknown_kind`, `insufficient_cdrh3_novelty`.

## immunum — numbering confidence is computable

`immunum 2.0.0`, a Rust CLI beside abguard. Trastuzumab VH numbers at **0.8754**, far above the
0.1 floor, so that hard check is satisfied and no longer indeterminate in our pipeline.

```bash
immunum number  "<SEQ>" --min-confidence 0.1 -f tsv
immunum segment "<SEQ>" --min-confidence 0.1 -f json   # prefix fr1 cdr1 fr2 cdr2 fr3 cdr3 fr4 postfix
```

**Pass `--min-confidence 0.1` explicitly — the CLI default is 0.5.** At 0.5, abguard's own comment
notes 343 of 2,306 real nanobodies get rejected as `low_confidence`. Numbering is IMGT and not
configurable, because the cysteine rules are defined on IMGT positions 23 and 104.

## A developability axis we did not know we had

`abguard` implements the **LAP Antibody Liability Reference** (Satława et al., PLOS Comput Biol
2024; 20(3):e1011881) — 13 motif rules, computed per design for free by `liability-report`:

| Severity | Tags |
|---|---|
| high | `DeAmdH` N[GS] · `FragH` DP · `Isom` D[DGHST] · `mCys` no C at IMGT 23/104 · `xCys` C outside 23/104 · `Ngly` N[^P][ST] |
| medium | `DeAmdM` N[AHNT] · `Hydro` NP · `FragM` TS · `TrpOx` W · `MetOx` M |
| low | `DeAmdL` [STK]N · `IntBind` GPR\|RGD\|RYD\|LDV\|DGE\|KGD\|NGR |

CDR-scoped motifs include one residue of framework flank each side, per LAP's convention. These are
**advisory, not gating** — only `mCys`/`xCys` overlap the hard checks. Measured on batch 1: 0 hard
errors, and the motifs shared by all 20 designs are inherited from trastuzumab's own framework, so
they cannot discriminate. Only `Ngly`, `MetOx` and `FragM` are design-specific and worth ranking on.

## Checking novelty without the VM — `scripts/novelty_distance.py`

abguard is the verdict, but it is on the VM and answers in batches. The same novelty arithmetic
runs offline on any laptop, standard library only:

```bash
python3 -I scripts/novelty_distance.py                      # batch 1, default paths
python3 -I scripts/novelty_distance.py --designs <file.csv>  # any batch
```

20 designs against all 525,027 measured references in 38 s, and it agrees with
`abguard team-validate` on all 20 rows of batch 1 — same 14 pass, same 6 reject. It is a
pre-filter, not a replacement: it covers the novelty gate only, against the references we were
shipped, while abguard's bundle is 610,109 rows and it also runs the schema, cysteine and numbering
checks. Use it to throw away doomed designs before spending GPU time, then let abguard decide.

**The two measurements agree from opposite ends.** The table above says to generate at ≥ 6
mutations *from trastuzumab*; the pre-check measures distance *to the nearest of all 525k measured
loops* and needs ≥ 3. Same rule: the FACS screen is dense around trastuzumab, so a design close to
the parent is almost certainly within 2 of something already measured. Batch 1 bears it out — both
designs at 4 mutations from trastuzumab were rejected, and 14 of the 18 at 6–9 passed.

## Control run, for the record

`pipeline/filter/abguard-control.csv`, 4 paired designs built from
`~/hackathon-data/her2-trastuzumab/trastuzumab_her2_spr_all_768.csv` row 1 (wild-type
trastuzumab, KD 0.152 nM). Result: 0/4 valid, each for the reason we designed it to trip.

| Design | Built to be | Verdict |
|---|---|---|
| `ctrl_wt` | wild-type trastuzumab | rejected, 0 mutations from `trastuzumab` |
| `ctrl_1mut` | known binder, 1 CDRH3 mutation (KD 0.142) | rejected, 0 mutations from the SPR table |
| `ctrl_3mut` | 3 synthetic CDRH3 mutations | rejected, 2 mutations from a FACS loop |
| `ctrl_freecys` | extra unpaired cysteine in CDRH3 | rejected, `[paired] heavy_cysteines_are_paired` |

The hard checks and the novelty gate both fire. `cdrh3_confidence` came back 0.876 on our
framework, well over the 0.1 `immunum` bar — that filter is not a risk for us.

Reproduce on the VM:

```bash
cd ~/mark/abguard-control && abguard team-validate control.csv
```

## Still open

- `novelty-report` prints `WARNING --no-novelty: prior art was not checked` even when
  `--reference-db` is passed, and its `cdrh3_nearest_source` column only ever said
  `trastuzumab`. `team-validate` *does* use the full reference. So: trust `team-validate` for the
  verdict; treat `novelty-report`'s nearest-neighbour column as trastuzumab-only. Worth 30 seconds
  with the Apheris team to confirm it is a cosmetic bug and not a second code path.
- `competition-validate` "rejects shared sequences" across teams. We cannot run it, but it means
  a design duplicated by another team is dropped for both of us — the README's "+4 spare in
  case of duplication between teams" is the right instinct. Diversity in the final 20 has value
  beyond scoring.
