# Nebius Scientific AI — cheat sheet

Queue time is today's binding constraint. Sixteen teams share the platform and the **first call to a
model includes the model load**: 40 s for the cheapest, 22 min for the worst. Start the slow jobs
before the fast ones.

Sources: `Files from slack/extracted/participant-05/START-HERE.md`, `agent/nebius-scientific-ai/SKILL.md`,
`RECIPES.md`, `forge.py` (read line by line), and the hackathon resource map PDF. Nothing here is
invented; anything unverified is marked `TODO: confirm`. Nothing here has been run by the author of
this file — the times are the measurements from 11–12 Nov quoted in those sources.

## 60-second start

```bash
cd "Files from slack/extracted/participant-05"      # the folder with the creds file
bash agent/install.sh                               # copies the skill to ~/.claude/skills
export NEBIUS_CREDS="$PWD/credentials.private.json"
F=~/.claude/skills/nebius-scientific-ai/forge.py
python3 "$F" models
```

`bash agent/install.sh ./myproject` installs into `<project>/.claude/skills` instead. Never open,
print or commit the credentials file; `*.private.json` is gitignored. Refer to it as `$NEBIUS_CREDS`.

## Environment contract

| Thing | Rule |
|---|---|
| Credentials | `forge.py` looks in this order: `--creds PATH`, `$NEBIUS_CREDS`, `./credentials.private.json`, `~/credentials.private.json`. It needs `scientific_api.base_url`, `mcp_url` and `api_key` inside. |
| Secrets in output | every print is masked: the API key, login password and bucket keys come out as `<hidden>`. Do not defeat that by cat-ing the file. |
| Run receipts | `nebius-runs/<label>.json`, one per run, created on first run. Override the directory with `$NEBIUS_RUNS_DIR`. **`resume` and `runs` find the run by reading that folder, so keep working from one folder.** |
| Results | `results/<something>` — you pass it yourself as `fetch --dest`. |
| Commit both | `results/` and `nebius-runs/` hold no keys. We have to show where each score came from, so commit them. |
| Run id | `op-` plus 8 hex, e.g. `op-1234abcd`. Printed on submit and saved in the receipt. Keep it; you can close the laptop. |
| Never submit twice | a repeat sends the same idempotency key (`oslo-<model>-<label>`, or a hash of the payload when there is no `--label`) and **follows the existing run**. `submit` also sees the local receipt and follows it. You only wait twice otherwise. `--force` overrides; don't. |
| After a storage error | `forge.py resume op-xxxxxxxx`. Not a new submit. |
| Ctrl-C | kills the poller, not the run. `forge.py runs` to find it again. |

## forge.py command surface

Derived from `main()` in `forge.py`. Global flag: `--creds PATH` (goes **before** the subcommand).

| Subcommand | Positional | Flags | Returns |
|---|---|---|---|
| `models` | — | `--all` | tested models: name, lane (`inline`/`file`), first-call estimate, one-line use. `--all` lists every model id on the key, marking the tested ones. |
| `schema` | `model` | `--full` | the model schema, trimmed (drops `mcp_input_schema`, provenance, regions…) and capped at 40 000 chars; prints what it left out. `--full` prints everything including `input_artifact_contract`. |
| `run` | `model` | `--args JSON`, `--args-file PATH`, `--tool`, `--label`, `--budget 1800`, `--no-wait` | inline models only. Uploads any `{"$upload": path}`, inlines any `{"$text": path}`, prints the wait estimate, prints `Run id: op-…` and the receipt path, then polls. Refuses a file-based model and tells you to use `submit`. |
| `submit` | `model` | `--entry 'name\|semantic_type\|path[\|media_type]'` (repeatable, ≥1), `--params JSON`, `--operation`, `--tool`, `--service-class customer-batch`, `--display-name`, `--wrap-request`, `--label`, `--budget 1800`, `--no-wait`, `--force` | file-based models. Uploads each entry, builds the manifest, submits, polls. If a receipt with the same label already has an operation id it prints "This exact run already exists" and follows it. Refuses an inline model and tells you to use `run`. |
| `status` | `operation_id` | `--verbose` | one line: `op-xxxx: <state> (result ready: True/False)`. `--verbose` dumps the operation document. |
| `wait` | `operation_id` | `--budget 1800` | polls every 10 s, prints each state change with elapsed seconds, and on success prints the exact `fetch` command. On budget exhaustion it says the run keeps going and to come back. |
| `fetch` | `operation_id` | `--dest DIR` (**required**), `--max-bytes 52428800` | writes `result.json` (masked), then walks the result for artifacts, downloads each as `<artifact_id><ext>`, **verifies every sha256** (prints `checksum ok`/`WRONG`) and follows nested JSON manifests. Files over `--max-bytes` are skipped with a message. |
| `resume` | `operation_id` | `--key`, `--budget 1800` | re-issues the run with its idempotency key (from the receipt, or `--key`), then polls the same run. Use after *private storage is temporarily unavailable*. |
| `runs` | — | — | every receipt in `nebius-runs/`: submit time, model, state, run id, label. |

Terminal states: `succeeded`, `failed`, `cancelled`, `preempted`, `expired`.

**`run` vs `submit` is a property of the model, not a choice.** The "Call" column in the tables below
is authoritative; getting it wrong just produces an error that tells you the other one.

- **inline** (`run`): arguments in one JSON blob. `{"$upload": "x.pdb"}` uploads and becomes an
  artifact reference, `{"$text": "x.a3m"}` becomes the file's text.
- **file-based** (`submit`): one `--entry` per file; `name` and `semantic_type` come from the schema.

A model that is in neither table can still be called if `schema <model> --full` publishes an
`input_artifact_contract`: build exactly the file it describes and
`submit <model> --tool <tool_name> --operation <operation> --entry … --params …`. Tar rule:
`COPYFILE_DISABLE=1 tar -cf out.tar -C dir .` — listed paths at the archive root, no `./`, no macOS
extras. A 422 names the field; fix that one field, retry once, then stop.

## Models, by group, with first-call wait

First-call times measured 12 Nov on one account with ~25 jobs open, i.e. close to today. 34 models
have a tested input format; the account hosts ~60.

### Antibody

| Model | Call | First call | Use |
|---|---|---|---|
| `nanobodybuilder2` | submit | 2 min | VHH structure from one FASTA, header `H` |
| `abodybuilder3` | submit | 2 min | paired antibody, FASTA headers `H` and `L` |
| `antifold` | submit | 2 min | redesign CDR loops, keeps the framework |
| `igbert` | submit | 4 min | heavy + light chain embeddings from a CSV |

### Fold and align

| Model | Call | First call | Use |
|---|---|---|---|
| `msa-search-pdb70` | run | 40 s | real alignment; better than a one-line A3M |
| `boltz2` | run | 80 s | fold or co-fold chains. Needs an A3M per chain |
| `openfold3` | run | 3 min | second opinion on a sequence or complex |
| `bioemu2` | submit | 4 min | equilibrium conformations of one protein |
| `chai1` | submit | 5 min | complex from a Chai FASTA inside a tar |
| `esmfold2-fast` | submit | **11 min** | structure from sequence, long queue |
| `protenix-v2` | submit | **20 min** | complex structure, long queue |
| `esmfold2` | submit | **22 min** | structure from sequence, long queue |
| `openfold2` | run | **do not use** | endpoint never started on 12 Nov, twice, including on an idle queue. Burns 55 min per attempt. Use `openfold3` or `boltz2`. |

### Design

| Model | Call | First call | Use |
|---|---|---|---|
| `proteinmpnn` | run | ~100 s (resource map says 2 min) | sequences for a backbone. No antibody prior |
| `esm-if1` | submit | 5 min | inverse folding, same tar as AntiFold |
| `rfd4-proteina` | submit | 6 min | binder backbone from an annotated mmCIF. **Not a VHH.** Start early |
| `rfdiffusion` | submit | 6 min | backbone design from a constraint file |
| `saprot-inverse-folding` | submit | 9 min | structure-aware design at masked positions |
| `mosaic` | submit | **22 min** | binder from a target FASTA. Start early |

### Language models

| Model | Call | First call | Use |
|---|---|---|---|
| `esmc-300m` | submit | 3 min | embeddings or variant scores |
| `esmc-600m` | submit | 4 min | embeddings or variant scores |
| `esm2-650m` | submit | 4 min | sequence scores from a FASTA tar |
| `saprot-650m` | submit | 5 min | structure-aware embeddings from a PDB tar |
| `esm2-3b` | submit | 8 min | sequence scores, slower |
| `saprot-1-3b` | submit | 10 min | larger structure-aware embeddings |
| `stab-ddg` | submit | **12 min** | binding ddG for named point mutations across two partner chains |
| `esmc-6b` | submit | **15 min** | large embeddings (9–15 min first call) |

### Dock and MD

| Model | Call | First call | Use |
|---|---|---|---|
| `mdprecheck` | run | 10 s | checks an MD bundle and answers in the same call |
| `openmm` | submit | 2 min | run fields go inside `request` |
| `amber` | submit | 3 min | `--wrap-request`, gzipped tar |
| `namd` | submit | 3 min | `--wrap-request`, gzipped tar |
| `diffdock` | run | 5 min | dock a small molecule into a protein |
| `gromacs` | submit | 5 min | `--wrap-request`, gzipped tar |
| `lammps` | submit | 5 min | `--wrap-request`, gzipped tar |

**Start early (≥11 min of pure load):** `mosaic`, `esmfold2`, `protenix-v2`, `esmc-6b`, `stab-ddg`,
`esmfold2-fast`. Then fill the wait with the 40 s–3 min models.

## Recipes

Tested 11–12 Nov on a real participant account. `$F` = path to `forge.py`. Inputs go in
`nebius-runs/`, downloads in `results/`. `mkdir -p nebius-runs/inputs` first.

### VHH against a target — the 6-step chain

| # | Model | Input | Wait |
|---|---|---|---|
| 1 | `msa-search-pdb70` | target sequence | 40 s |
| 2 | `boltz2` or `openfold3` | target + A3M | 80 s – 3 min |
| 3 | `antifold` | VHH PDB + CDR regions | ~2 min |
| 4 | `nanobodybuilder2` | FASTA, header `H` | ~2 min |
| 5 | `boltz2` | candidate + target | 75 s |
| 6 | `openfold3` | best complex | ~3 min |

```bash
# 1. real alignment for the target
python3 "$F" run msa-search-pdb70 --label msa-1 --args '{
  "sequence": "<TARGET>", "databases": ["pdb70_220313"],
  "output_alignment_formats": ["a3m"]}'

# 2. fold the target alone, check it is sensible (boltz.json below)
python3 "$F" run boltz2 --args-file nebius-runs/boltz-target.json --label fold-target

# 3. new CDR loops on a known VHH framework, framework kept
COPYFILE_DISABLE=1 tar -cf nebius-runs/inputs/antifold.tar -C nebius-runs/inputs 1zvy.pdb
python3 "$F" submit antifold \
  --entry 'workload|inverse-folding-tar/v1|nebius-runs/inputs/antifold.tar' \
  --params '{"pdb_file":"1zvy.pdb","nanobody_chain":"A","nanobody_mode":true,
             "regions":"CDR1 CDR2 CDR3","num_seq_per_target":5,"sampling_temp":"0.20"}' \
  --label antifold-1

# 4. antibody-aware model of each new sequence
printf '>H\n%s\n' "$VHH" > nebius-runs/inputs/vhh.fasta
python3 "$F" submit nanobodybuilder2 \
  --entry 'sequence|nanobody-fasta/v1|nebius-runs/inputs/vhh.fasta' \
  --params '{"numbering_scheme":"imgt"}' --label nbb2-1

# 5. co-fold candidate against target, 75 s each — this is the screen
# 6. re-check the winners with openfold3
python3 "$F" run openfold3 --label of3-1 --args '{
  "request_id": "vhh-1",
  "inputs": [{"input_id": "VHH", "output_format": "cif",
    "molecules": [{"id": "A", "type": "protein", "sequence": "<SEQ>"}]}]}'
```

`boltz2` args, one polymer per chain, **one `msa` block per chain**:

```json
{"polymers": [
  {"id": "A", "molecule_type": "protein", "sequence": "<CANDIDATE>",
   "msa": {"msa_search": {"a3m": {"alignment": ">query\n<CANDIDATE>\n"}}}},
  {"id": "B", "molecule_type": "protein", "sequence": "<TARGET>",
   "msa": {"msa_search": {"a3m": {"alignment": ">query\n<TARGET>\n"}}}}]}
```

```bash
python3 "$F" run boltz2 --args-file nebius-runs/boltz-pair.json --label cofold-1
python3 "$F" fetch op-xxxxxxxx --dest results/cofold-1
```

Returns `structures`, `confidence_scores`, `ptm_scores`. Reference numbers from the 1ZVY pair:
confidence 0.77, pTM 0.57, against 0.93 for the VHH alone.

### Paired antibody (our Fab / scFv track)

Same call as `nanobodybuilder2`, one FASTA with headers `H` **and** `L`, entry
`sequences|antibody-fasta/v1`:

```bash
python3 "$F" submit abodybuilder3 \
  --entry 'sequences|antibody-fasta/v1|nebius-runs/inputs/fab.fasta' \
  --params '{"numbering_scheme":"imgt"}' --label abb3-1
```

### General binder (no antibody prior)

```bash
python3 "$F" submit rfd4-proteina \
  --entry 'annotated-cif|rfd4-proteina-annotated-cif/v1|target.cif' \
  --params '{"num_replicates":1,"batch_size":1,"seed":42,"nsteps":60,
             "recycle_strategy":"thinking_medium","compile":true,
             "save_trajectory_every":0,"save_chain_of_interest":false}' \
  --label binder-1
```

Test run: 385 s, returns a tar of **backbones, not VHHs**. Raise `num_replicates` for more and
expect the time to grow; read `schema rfd4-proteina` before changing anything. Then give the
backbone a sequence with ProteinMPNN:

```json
{"input_pdb": {"$upload": "1zvy.pdb", "media_type": "chemical/x-pdb"},
 "input_pdb_chains": ["A"], "num_seq_per_target": 4,
 "sampling_temp": 0.1, "random_seed": 42}
```

```bash
python3 "$F" run proteinmpnn --args-file nebius-runs/mpnn.json --label design-1
```

Returns `mfasta` plus `backbone_coverage` — positions it could not design because the structure does
not resolve them. Check that field before trusting a design. `omit_AAs` forbids residues; higher
`sampling_temp` gives more variety.

## Gotchas that cost real money today

- **Boltz2 returns no ipTM.** It gives `confidence_scores` and `ptm_scores` only. Do not report an
  ipTM from it. For an interface number either count cross-chain contacts in the returned mmCIF
  yourself, or get ipTM from the **Apheris Foundry** path on the VM: `rfd4-proteina refold-prepare`
  → fold with Predict Structure → `refold-score`, which reports `min_ipae`, `iptm` and
  `binder_plddt` (task PDF; for the HER2 exercise its pass column stays empty, so rank on those
  three). **TODO resolved (14 Nov, `forge.py schema`):** none of `openfold3`, `chai1` or
  `protenix-v2` report ipTM or PAE. `openfold3` states "CIF output only"; `chai1` and `protenix-v2`
  advertise no pae/iptm/ptm/confidence field at all. The `pae-probe` artifact confirms boltz2 returns
  exactly `confidence_scores`, `ptm_scores`, `structures` — nothing else. **`min_ipae` and `iptm` are
  unobtainable on the hosted lane; axis 1 as specified requires the Apheris Foundry path on the VM.**
  The only hosted binding signal is cross-chain contacts counted from a boltz2 co-fold mmCIF (75 s
  per design), which is a *different* metric and must not be reported as ipTM or min_ipae.
- **A3M per chain.** Boltz2 needs an alignment for *every* polymer. A one-line `">query\n<SEQ>\n"`
  works for a first look; `msa-search-pdb70` (40 s) is better and that is what goes into the final
  numbers. For a VHH, PDB70 often finds few relatives — that is normal, not a failure.
- **MD engines**: `--wrap-request` for GROMACS, AMBER, NAMD, LAMMPS, OpenMM, or you get
  `missing required fields: request`. Send the bundle **still gzipped** (`inputs.tar.gz` as it is);
  unpack it and the engine stops with "not a gzip file". Run `mdprecheck` first — 10 s, same call,
  catches broken topology. A pass is not proof the science is right.
- **Do not pull the full model catalog** into a Claude context: ~310 KB via MCP `tools/list`,
  ~930 KB in the browser answer. Use `models` and `schema <model>` instead, and read the schema of
  the one model you picked.
- **Antibody-aware beats general.** VHH → `nanobodybuilder2`, paired → `abodybuilder3`, new CDRs →
  `antifold` (keeps the framework) rather than `proteinmpnn` (no antibody prior). Use `boltz2` only
  when the target is in the question.
- **AlphaFold 3 is not available**: *weights not granted to tenant*. Use OpenFold3, Boltz2 or ESMFold2.
- **macOS certificate error** from Python: run `Install Certificates.command` from the Python folder
  in Applications.
- The official Nebius `scientific-ai` bundle (51 skills, one per model) is installed alongside and
  carries the parameter meaning and caveats. Read the model's own skill for the science; use this
  file and `forge.py` for getting the job to run. Its `scientific-gateway` instruction to use
  `/opt/bionemo/invoke-scientific-batch.py` does **not** work from a laptop — `forge.py submit`
  replaces it.

## What to run for OUR task

Improve trastuzumab against HER2; every design is judged on SPR affinity, epitope preservation and
thermostability vs the measured baseline. Split: **design on the VM, score on the platform** — that
is where the parallelism is.

| Our need | On Nebius | Note |
|---|---|---|
| HER2 alignment + reference fold | `msa-search-pdb70` → `boltz2`/`openfold3` | 40 s + 80 s–3 min. Do this first, everything reuses the A3M |
| De novo VHH candidates | `antifold` on a known VHH framework (antibody-aware) · `rfd4-proteina` or `mosaic` for a general backbone, then `proteinmpnn` | start `mosaic` (22 min) and `rfd4-proteina` (6 min) **now**, they are the long poles |
| Optimisation: point mutants of trastuzumab | `stab-ddg` — binding ddG for named point mutations across two partner chains | 12 min first call, start early. Design the mutant list on the VM with the Apheris HER2 weights |
| Candidate structures | `nanobodybuilder2` (VHH) · `abodybuilder3` (Fab/scFv, headers `H`+`L`) | ~2 min each, no alignment needed |
| Affinity screen | `boltz2` co-fold candidate + HER2, 75 s each | confidence + pTM, **no ipTM** |
| Confirmation of the shortlist | `openfold3`, and `protenix-v2` if we can afford 20 min | two dissimilar models agreeing is worth more than one high score |
| Ranking signal on sequences | `esm2-650m` / `esmc-300m`/`600m` scores, `saprot-650m` structure-aware embeddings, `igbert` for H/L | cheap, 3–5 min, useful as a second axis |
| Thermostability axis | no direct predictor exists — pick a proxy and name it | **TODO resolved (14 Nov):** nothing hosted predicts thermostability. `stab-ddg` is **binding** ddG. ThermoMPNN is not in the 34 and not in the install list. `OpenDDE` is in the install list (~1 h, VM-side) and is the only candidate direct predictor. Judges measure thermostability *experimentally* (`task.md` p335–341, Adaptyv), so `predicted_ddg` is a **selection prior, not a deliverable** — any defensible proxy is legitimate provided `thermostability_basis` states which one. Cheapest hosted proxy: `esm2-650m` pseudo-likelihood, 4 min |

Epitope preservation is judged by competitive binding against trastuzumab, so the trastuzumab–HER2
interface has to be an input to design, not an afterthought. The task PDF notes a known complex of
trastuzumab bound to HER2 can be used as a **template** by the Predict Structure models that support
one. TODO: confirm which PDB entry we standardise on, and pull it with the RCSB MCP on the VM.

### H100 VM vs hosted

The VM has Nvidia drivers and nothing else — no CUDA toolkit, no packages, no weights. pip PyTorch
wheels bring their own CUDA, so `uv pip install torch` then `torch.cuda.is_available() == True`
before anything else goes on. **Seven models are not hosted and would have to be installed there,
about an hour each**: RFantibody, Germinal, IgDiff, PXDesign, RFdiffusion3, nanoBERT, OpenDDE.
(SKILL.md prices only the first five at "about an hour"; the resource map's install table lists all
seven. TODO: confirm nanoBERT and OpenDDE cost the same.)

Everything else we would reach for is hosted since 12 Nov — NanoBodyBuilder2, ABodyBuilder3,
AntiFold, ESM-IF1, IgBert, Chai-1 and the ESM C, ESM-2 and SaProt families. **Installing those is
wasted time.** Check `forge.py models` before sending anyone to install anything.

## Known failures

| Symptom | Action |
|---|---|
| Looks stuck | `forge.py status op-xxxxxxxx`. A first call can wait 15 min. It is queued, not broken |
| *private storage is temporarily unavailable* | `forge.py resume op-xxxxxxxx`. Do not resubmit |
| *input does not match the schema* / 422 | `forge.py schema <model>`, fix the one named field, retry once, then stop |
| *missing required fields: request* | add `--wrap-request` (all five MD engines) |
| *synchronous calls only* | `mdprecheck` answers in the same call and refuses an idempotency key; `forge.py` already handles it |
| *weights not granted to tenant* | AlphaFold 3. Use OpenFold3, Boltz2 or ESMFold2 |
| OpenFold2 | endpoint does not start. 55 min per failed attempt. Use `openfold3` or `boltz2` |
| No credentials file | `export NEBIUS_CREDS=...` or `--creds PATH` |

Stuck beyond this: find a Nebius mentor on site, and bring the run id.
