# Pipeline

Five CLIs, antigen structure to ranked submission table. Each stage reads a file
and writes a file, so stages run independently, resume, and a judge can run them
on a target we have never seen.

Execution is 20% of the pitch score. This is the artefact that earns it.

**This is six commands, not five: stage 03 runs twice.** At the default
`--dispatch none` it writes the job spec and the commands and *no* candidate
file, because no designs exist yet. The generator runs in between, outside the
pipeline, and stage 03 runs again to ingest what it produced.

```bash
S=pipeline
python3 $S/01_prepare_target.py data/her2.cif --chains A -o runs/target.json
python3 $S/02_interface.py data/complex.cif --antibody-chains H,L --antigen-chains A \
        --target runs/target.json --numbering-json runs/numbering.json \
        -o runs/interface.json

# 03, first call: job spec + the exact command to run. Writes NO candidates.
python3 $S/03_generate.py --interface runs/interface.json --target-cif data/her2.cif \
        --track optimisation --sequence-tsr-k 2 --seed 42 --job-dir runs/jobs \
        -o runs/candidates.jsonl

# run the generator yourself: runs/jobs/commands.json has the command

# 03, second call: ingest the designs. --jobspec carries the CDRH3 onto each
# record, which stage 05's novelty check needs.
python3 $S/03_generate.py --from-sequences results/designs.fasta --format VHH \
        --track optimisation --seed 42 --jobspec runs/jobs/jobspec.json \
        -o runs/candidates.jsonl

python3 $S/04_score.py runs/candidates.jsonl --refold-scores results/refold_score.json \
        --dev-scores results/dev/ -o runs/scored.jsonl
python3 $S/05_filter_rank.py runs/scored.jsonl -o designs/ranked.csv
```

Two things that bite on a first run:

- The first 03 call **refuses** if `interface.json` carries no CDR assignment
  while the chosen weight redesigns CDRH3 only (both HER2 weights do). Give
  stage 02 a `--numbering-json`, or pick `antibody-2026-10-30`, or pass
  `--allow-missing-cdrh3` and accept a job with nothing to redesign.
- The last line normally writes a **header-only** `ranked.csv`. See
  [Hard filters](#hard-filters--stage-05-before-any-ranking): without the real
  abguard the pre-check cannot pass anything. Add `--include-unverified` to see
  rows, labelled `needs_abguard`.

Every stage has `--help`, `--version`, `--run-id` (resume under the same id) and
`-q`. Every stage runs with nothing installed except what its own work needs.
A missing or unreadable input file is one line of text and exit 1, not a
traceback.

## Stage contract

| Stage | Reads | Writes | Needs |
|---|---|---|---|
| `01_prepare_target.py` | antigen `.cif`/`.mmcif`/`.pdb` | `target.json` | biopython |
| `02_interface.py` | complex structure, `target.json`, optional `numbering.json` | `interface.json` | biopython; anarcii for CDRs |
| `03_generate.py` | `interface.json` + target mmCIF, **or** `--from-sequences` FASTA/JSONL | `jobs/jobspec.json` + `jobs/commands.json` at `--dispatch none`; `candidates.jsonl` only on the `--from-sequences` path | stdlib; generator backend |
| `04_score.py` | `candidates.jsonl`, refold scores, developability scores | `scored.jsonl` | stdlib |
| `05_filter_rank.py` | `scored.jsonl` | `ranked.csv`, `rejected.csv`, `ranked.jsonl`, `submission_manifest.json` | stdlib; `abguard` if on PATH |

`pipeline/common.py` holds the schema, the provenance stamp, the hard-filter
constants and the IO. Nothing else defines a threshold.

## Formats between stages

JSON for one-object-per-run files, JSONL for one-candidate-per-line, CSV only
for the final tables. All writes are atomic, so a half-written file is never
read by the next stage.

**`target.json`** (`fab4.target/v1`) — per chain: observed sequence, SEQRES
sequence, residue ids `[chain, resseq, icode]`, unresolved residues, numbering
gaps, residues missing backbone atoms, hetero/non-standard residues, plus a
`warnings` list.

**`interface.json`** (`fab4.interface/v1`) — `contacts` (residue pairs with
`min_distance` and atom-pair count), `epitope`, `paratope` (with `region` and
`imgt_position` where the numbering join is sound), `numbering` per antibody
chain, and `contact_definition` with the cutoff used.

**`candidates.jsonl`** (`fab4.candidate/v1`) — one JSON object per design:

```json
{"schema":"fab4.candidate/v1","candidate_id":"cand-0001","format":"VHH",
 "track_intent":"optimisation","parent":"trastuzumab",
 "chains":{"H":"QVQ..."},
 "provenance":{"stage":"03_generate","model":"rfd4-proteina",
   "model_image":null,"weights":"her2-2026-11-07","seed":42,
   "settings":{"sequence_tsr_k":2},"timestamp":"2026-11-14T...Z",
   "inputs":[{"path":"...","sha256":"..."}],"pipeline_version":"0.1.0"},
 "scores":{},"checks":{},"notes":[]}
```

`chains` is `{"H"}` for a VHH, `{"H","L"}` for a Fab, `{"H","linker","L"}` for an
scFv, and stage 03 refuses a record whose chains do not match its format on
every ingestion path. `track_intent` is what we aimed for — **abguard decides
the real track** and never reclassifies a design, so nothing downstream treats
it as the track.

A record also carries `cdrh3` plus `cdrh3_source` when stage 03 could establish
the loop: from `--cdrh3`, from a `cdrh3` field in the input JSONL, or from
`--jobspec` when the parent loop is still present verbatim in the H chain.
Stage 05's novelty check — the one hard filter that decides the track — reads
this field, so a record without it gets `novelty: indeterminate`. Numbering a
*redesigned* loop needs ANARCII or immunum on the design itself. Stage 04 adds
keys and never drops it.

**`scored.jsonl`** — the same records with `scores[name] = {value, model,
version, seed, source_file, higher_is_better, note, recorded_at}`. A score we did
not read is `value: null` with a `note` saying why. Stage 05 treats null as
missing, never as zero. `liabilities` holds local motif counts, which are flags,
not scores.

**`ranked.csv`** — the submission table, up to 20 rows: rank, id, format,
abguard track and verdict, `filter_source`, `rank_score`, the three interface
scores, the four developability scores, **the five thermostability columns**
(`framework_mutations`, `framework_identity`, `vh_vl_interface_ddg`,
`esm2_pll_per_residue`, `esm2_variant_score` — see
[`thermostability.py`](thermostability.py)), length, cysteine count, missing
scores, and generator / model_image / weights / seed / pipeline_version /
timestamp on every row. `submission_manifest.json` records the hard limits applied, the
ranking weights and the bucket counts.

## Hard filters — stage 05, before any ranking

abguard is the authority. Stage 05 shells out to the real CLI when
`--abguard-cmd` names one and it is on PATH, and otherwise falls back to a local
re-implementation that is labelled a **pre-check** in every output row. The
pre-check does not replace abguard; it catches cheap mistakes before a job runs,
and on its own it produces an empty table (first bullet below).

| Check | Threshold | Pre-check can decide? |
|---|---|---|
| Format | VHH, scFv or Fab | yes |
| Total length | ≤ 250 aa (one scFv/VHH, or VH+VL combined) | only where both counting rules agree — see below |
| Unpaired cysteines | none allowed | odd count = fail, unless a tag was detected; even = indeterminate (pairing needs structure) |
| Numbering confidence | ≥ 0.1, with `immunum` | no — we do not have immunum. ANARCII's score is a different number and is not substituted |
| Track | identity to nearest known antibody < 70% → de novo, else optimisation | only with a reference set in `data/reference/antibodies.json` |
| de novo extra | ≥ 2 CDRH3 mutations from trastuzumab | only with a reference set |
| optimisation extra | CDRH3 identity to trastuzumab < 70% **and** > 2 point mutations from any provided antibody | only with a reference set |

All thresholds from the task PDF (p3 Figure 2, p7). They live in
`common.HARD_LIMITS`, nowhere else.

Six things to know before trusting a pre-check verdict:

- **The pre-check can only reject, never pass.** Unpaired cysteines are
  indeterminate for every even count, and numbering confidence needs `immunum`,
  which we do not have — so no design ever collects a full pass locally. Without
  abguard the normal result is `eligible 0` and a **header-only `ranked.csv`**.
  A non-empty table needs either `--abguard-cmd "<the real invocation>"` or
  `--include-unverified`, which puts the designs in the table with verdict
  `needs_abguard`. Stage 05 says this on stdout as well. The direction is
  deliberate: a local guess must not put a design in the submission table.
- **`indeterminate` is a real answer.** A design whose checks are indeterminate
  lands in `needs_abguard` and stays out of `ranked.csv` unless you pass
  `--include-unverified`.
- **The PDF counts length two ways and we do not pick one.** p3 Figure 2 runs
  "Extract antibody sequence — immunum strips tags and linkers" *before* the
  shared hard checks; p7 states the limit as the "whole length of a single scFv
  or VHH, or combined for VH and VL". So stage 05 reports both counts, passes
  when both are ≤ 250, fails when both are over, and reports indeterminate when
  they straddle the limit — a 255 aa scFv that is 240 aa without its linker is
  not rejected here. Cysteines are counted without the linker for the same
  reason; a detected tag (a poly-His run, our heuristic, not a sourced
  definition) makes an odd count indeterminate instead of a fail.
  TODO: confirm which count abguard applies, by running it on one scFv that
  straddles 250 with and without its linker.
- **`--abguard-cmd` has no default.** The bare word `abguard` is not a confirmed
  invocation, so unset means the pre-check only. A nonzero exit from abguard
  aborts the stage (exit 1) with the returncode and the first stderr line — its
  verdicts are never used, because output from a failed run once put two
  designs in the submission table.
- **The reference sequences are not in this repo.** The task PDF contains no
  trastuzumab sequence, so `data/reference/antibodies.json` does not exist yet
  rather than holding a sequence written from memory. Until someone creates it
  from RCSB or the organisers' bucket, every novelty check is indeterminate. The
  shape it needs is in `common.load_reference_set()`, and it needs **three**
  keys: `trastuzumab` (with its `cdrh3`), `provided` (the organisers' data
  points, for the > 2 point-mutation check, task PDF p7) and `known` (known
  antibodies from known databases, for the < 70% identity track decision, task
  PDF p2 and p3 Figure 2). A file without `known` leaves the track and the
  novelty check indeterminate.
- **Source contradiction, unresolved.** The optimisation point-mutation count is
  "at least 2" on p2 of the task PDF but "strictly more than 2" on p3 and p7. We
  take the strict reading (≥ 3). TODO: confirm with the organisers.

## Ranking — survivors only

For the HER2 exercise the task PDF says refold-score's pass column stays empty,
so we rank on `min_ipae` (lower better), `iptm` and `binder_plddt`. Each is
min-max normalised across the candidate set and averaged with equal weights.

- Equal weights are a **team choice**, not from the task description. Change with
  `--weight min_ipae=2`; the weights used are written into the manifest.
- `rank_score` orders designs within one run. It is not a quantity and is not
  comparable between runs.
- **Thermostability terms (stage 04b).** Three are weightable:
  `framework_mutations` (lower better), `framework_identity` and
  `esm2_pll_per_residue`. Two are **recorded as columns but refused as ranking
  terms** — `vh_vl_interface_ddg` and `esm2_variant_score` — because our sources
  do not state which sign is stabilising; see `DIRECTION_UNCONFIRMED` in
  `05_filter_rank.py`. Weights must be finite and `>= 0`: direction belongs in
  `HIGHER_IS_BETTER`, not in a weight's sign.
- **`framework_mutations` is null for de novo** (no parent to measure drift
  from), so weighting it in a mixed-track run sends every de novo design to the
  bottom — not because they are worse, but because the term does not exist for
  them. The stage now warns when a weighted score is null for a whole track.
  Rank within track, or weight it only in an optimisation-only run.
- A candidate missing any weighted score gets `rank_score` null and sorts last,
  flagged in `missing_scores`. Nothing is imputed — an imputed score is a
  fabricated score.
- Developability is reported as columns and used only as a tiebreak: the task PDF
  recommends the four tools but gives no threshold for any of them.
- The table is up to 20 rows (16 if we place first, plus 4 against duplication
  between teams).

## What is real and what is not

Judge-facing honesty, so nobody demos a stub by accident.

| Piece | State |
|---|---|
| 01 structure parsing, chain selection, unresolved/gap report | **Works.** Run against RCSB 1ZVY, both `.pdb` and `.cif`: chain A reports 125 observed vs 136 in the entity. The 11 unresolved tag residues are *named* (126–136) only for an mmCIF input — `unobserved_from_mmcif()` reads the mmCIF unobserved-residue block, so a `.pdb` input gives the count without the identities |
| 02 contacts, epitope, paratope | **Works.** 1ZVY A↔B at 4.5 Å: 41 contacts, 14 epitope, 19 paratope residues |
| 02 IMGT↔PDB join and CDR spans | **Works** from a `--numbering-json`, and refuses to emit a shifted map on a length or sequence mismatch |
| 02 ANARCII call | **Stub.** Entry point not in our sources. Exits 3 with what to confirm on the VM |
| 03 job spec, hotspots from epitope, candidate records, FASTA/JSONL ingestion | **Works** |
| 03 Foundry dispatch | **Stub.** Exits 3. CLI not in our sources |
| 03 Nebius `forge.py` dispatch | **Written from RECIPES.md recipe 6, not run by us.** Needs `NEBIUS_CREDS` |
| 04 score ingestion, coverage table, liability counts | **Works** |
| 04 refold-prepare / refold-score / the four developability tools | **Stubs.** Exit 3. Produce the numbers outside and pass `--refold-scores` / `--dev-scores` |
| 05 hard filters, bucketing, ranking, tables | **Works**, with one thing to know: on the local pre-check alone the table is empty by design (see above). Tested against a stub abguard that returns JSON and exits 0, a stub that exits nonzero (verdicts discarded, stage aborts), and the pre-check |
| 05 real abguard flags | **Not confirmed.** No default: pass them yourself, `--abguard-cmd "abguard check --json"`. Run `abguard --help` on the VM first. The accepted verdict words are `pass`/`eligible` and `fail`/`fails`/`reject`/`rejected`, from task PDF p3 Figure 2; anything else becomes `needs_abguard` |

A stub exits **3** and prints exactly what to confirm on the VM, named down to
the function to edit.

| Exit | Meaning |
|---|---|
| 0 | success |
| 1 | missing dependency, a missing or unreadable input file, or abguard exited nonzero — always one line of text, never a traceback |
| 2 | bad arguments (argparse) |
| 3 | a stub: the stage needs an interface confirmed on the VM first |
| 130 | interrupted |

## Generator weights (Apheris Foundry, RFD4-Proteina)

The weights are selected by choosing the Docker image. Organisers' measured
numbers on the trastuzumab CDRH3 task — theirs, not ours:

| Weight / setting | Known binders | Pass novelty | Interface error (Å) |
|---|---|---|---|
| `antibody-2026-10-30` (not fine-tuned) | 0% | 100% | 8.2 |
| `her2-2026-11-07`, conservative | 21% | 0% | 9.4 |
| `her2-2026-11-07`, balanced (`--sequence-tsr-k 2`) | 21% | 6% | 9.1 |
| `her2-2026-11-07`, exploratory (`--sequence-tsr-k 1`) | 0.3% | 74% | 9.1 |
| `her2-novel-2026-11-09` | 4% | 86% | 6.8 |

A known binder fails the novelty filter, so filter before ranking. The HER2
weights redesign CDRH3 only; other CDRs need `antibody-2026-10-30`. Our defaults
are `her2-2026-11-07` for the optimisation track and `her2-novel-2026-11-09` for
de novo — a team choice over those numbers, set in `pick_weights()`.

Note on the other path: the Nebius-hosted `rfd4-proteina` is the **general**
model with no antibody prior, and RECIPES.md says its output is a general protein
binder, not a VHH. It needs a sequence-design step after it, and it is not an
antibody until something makes it one — while abguard requires VHH, scFv or Fab.

## Two traps this code is built around

**IMGT positions are not PDB residue numbers.** They meet in exactly one place,
`interface.json → numbering[chain].map`, and only when `map_status == "ok"`.
Unresolved residues inside the numbered region shift the walk, so stage 02
refuses to emit a map rather than emitting a shifted one. Never index
coordinates with an IMGT number.

**Confidence is not affinity.** min_ipae, iptm, binder_plddt and the solubility
predictions rank candidates. None of them is a KD, and the three judged
properties — affinity by SPR, epitope preservation by competitive binding,
thermostability — are measured by Adaptyv after the event, not here.

## Dependencies

Python 3, stdlib, plus `biopython` for stages 01 and 02 and `anarcii` for
numbering. Stages 03–05 are stdlib only. A missing dependency prints the install
line; `--help` always works without any of them.

```bash
pip install biopython anarcii
```

## Credentials

Never in this repo. `03_generate.py --dispatch forge` reads the path in
`NEBIUS_CREDS` and never reads, prints or stores the key itself. Setup is in the
Slack folder's `START-HERE.md`.
