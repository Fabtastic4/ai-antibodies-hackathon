# abguard — the real eligibility rules, read from the code

`abguard` **is on the VM.** It was not found at 11:10 UTC and was present at 11:17, so it appeared
during the morning. Two copies exist:

```bash
# The teammate-built venv (abguard 0.1.0 + immunum 2.0.0, built 11 Nov 16:17). Prefer this one.
export ABG=/home/hackathon/.cache/uv/archive-v0/LQ7GYqqqANyUP63G/bin
$ABG/abguard --help
$ABG/immunum --help

# A uv tool symlink that appeared at 11:17 UTC today
~/.local/bin/abguard -> ~/.local/share/uv/tools/abguard/bin/abguard
```

Confirm the two agree before trusting either (`abguard --version`, `immunum --version`). Do **not**
`pip install` anything: the venv is complete and its versions are the graded ones. Its
`direct_url.json` points at `/home/hackathon/repos/apheris-abguard-demo`, which no longer exists, so
the cached venv is the only local copy — treat it as fragile.

Verified live on wild-type trastuzumab, which the gate correctly rejects:

```
$ABG/abguard team-validate submission.csv
ERROR submission is not compliant (0 of 1 row(s) pass the schema).
  - [novelty] TZ_WT: CDRH3 SRWGGDGFYAMDY is 0 mutation(s) from
    SRWGGDGFYAMDY in trastuzumab; a novel design needs at least 3
```

---

## Three things we had wrong, and they change what we generate

### 1. There is no 70% CDRH3 identity test. The bar is a Levenshtein count of 3.

From the code:

```
identity = 1 - (d_H + d_L) / (max(|VH|, |ref VH|) + max(|VL|, |ref VL|))
IDENTITY_THRESHOLD = 0.70        # >= 0.70 -> "novel" (trastuzumab variant);  < 0.70 -> "de_novo"
MUTATIONS_REQUIRED = {novel: 3, de_novo: 2}
```

Identity is computed over the **whole Fv** (`fr1 cdr1 fr2 cdr2 fr3 cdr3 fr4`, prefix and postfix
excluded, so linkers and tags are invisible to it). It is used **only to choose which bar applies** —
it is not itself a pass/fail test. Then the actual gate is:

> **CDRH3 Levenshtein distance ≥ 3** from trastuzumab **and** from every reference CDRH3
> (≥ 2 if the design classifies as de novo).

**Issue [#12](../../issues/12) is settled: 3 mutations for our track.** The Apheris slides' "≥2" applies
to the de novo track only.

This also retires the arithmetic in [probe-findings.md](probe-findings.md) §3: that derived "≥4 residues"
from a 70%-identity-over-11-residues calculation **that abguard never performs**. We were
over-constraining CDRH3 generation by a full mutation, and in the direction that costs binding.

### 2. Trastuzumab's CDRH3 is the 13-mer `SRWGGDGFYAMDY`

Confirmed live: `novelty-report` returns `cdrh3 = SRWGGDGFYAMDY`, `cdrh3_confidence = 0.875`. We had
the 11-mer `WGGDGFYAMDY` from the structure, and the FACS tables use the 10-mer core `WGGDGFYAMD`.

The code warns about precisely the mistake we were about to make:

> *the HER2 assay tables name its 10-mer core `WGGDGFYAMD`; comparing a design's IMGT CDR3 against those
> cores would hand every design three free mutations from the flanks alone.*

**Any local novelty pre-check must use the IMGT 13-mer**, or it will pass designs that abguard rejects.

### 3. The 250-residue cap is per chain, not combined

`MAX_SEQUENCE_LENGTH = 250` is a column check applied to `heavy_sequence` and `light_sequence`
**separately**. A `paired` design may be 250 + 250. The code comment says it is "sized for the scFv
case — a VH-linker-VL construct runs to about 240", so the cap only ever binds on scFv.

Both [task.md](task.md) and the Apheris slides describe it as a combined limit. **A paired Fab design
has effectively no length pressure**, which removes a constraint we had been designing against.

---

## The reference database ships inside the wheel

`reference_data/manifest.json`: `{"n_rows": 610109, "scheme": "imgt", "min_confidence": 0.1,
"index_table": "abguard_cdrh3"}`.

So we do **not** need to build a reference set from the 525,063 HER2 CDRH3s — which corrects
[apheris-slides.md](apheris-slides.md) §3. Note 610,109 > 525,063, so the bundle is broader than the
HER2 tables; whether it is a strict superset is unverified (`abguard reference-info <path>` would say).

The novelty gate is **on by default**. `--no-novelty` is required to skip it, "so that skipping the
check is always something you asked for". But `novelty-report` *without* `--reference-db` compares
against trastuzumab alone and prints `WARNING --no-novelty: prior art was not checked` — use
`team-validate` for the real verdict.

## The submission table

`abguard team-validate --help`: the table needs `sequence_id`, `kind`, `heavy_sequence`,
`light_sequence`, `design_description`. Rows are partitioned on `kind` and each partition validated
against its own schema. Accepted: `.csv .tsv .parquet .json .jsonl .xlsx .arrow .feather` and more.

| Column | Rule |
|---|---|
| `sequence_id` | primary key, unique, min length 1 |
| `kind` | exactly one of `vhh`, `scfv`, `paired` (lowercase) |
| `heavy_sequence` | `^[ACDEFGHIKLMNPQRSTVWY]+$`, 1–250 |
| `light_sequence` | **must be empty for `vhh` and `scfv`**; required for `paired` |
| `design_description` | must be present and non-null |

Domain counts, measured by `immunum`:

| kind | heavy_sequence | light_sequence |
|---|---|---|
| `vhh` | exactly 1 domain, labelled `H` | null |
| `scfv` | exactly **2** domains, either orientation | null |
| `paired` | exactly 1 domain labelled `H` | exactly 1 labelled `K` or `L` |

**There is no track column and no rank column.** The track is computed (`novelty_class`), which
confirms the task PDF. How we express ranking is therefore unresolved — most likely row order, since
`competition-validate` treats each file as one team named by its file stem. **TODO: ask an organiser**
whether rank is row order, and where the submission is actually sent. No doc on the VM says.

## immunum — numbering confidence is computable now

`immunum 2.0.0`, a Rust CLI at `$ABG/immunum`. Trastuzumab VH numbers at **0.8754**, far above the 0.1
floor, so that hard check is satisfied and no longer indeterminate in our pipeline.

```bash
$ABG/immunum number  "<SEQ>" --min-confidence 0.1 -f tsv
$ABG/immunum segment "<SEQ>" --min-confidence 0.1 -f json   # prefix fr1 cdr1 fr2 cdr2 fr3 cdr3 fr4 postfix
```

**Pass `--min-confidence 0.1` explicitly — the CLI default is 0.5.** At 0.5, abguard's own comment notes
343 of 2,306 real nanobodies get rejected as `low_confidence`. Numbering is IMGT and not configurable,
because the cysteine rules are defined on IMGT positions 23 and 104.

## Two traps that reject silently

- **Cysteines are checked twice**: the whole column count must be even *and* each domain's count must be
  even independently. An scFv with one spare Cys in VH and one in VL is even overall and still fails.
- **Swapped heavy/light columns are rejected.** `paired` needs heavy to label `H` and light `K`/`L`.

Full error vocabulary: `invalid_amino_acids`, `sequence_too_long`, `unpaired_cysteine`,
`numbering_failed`, `wrong_domain_count`, `missing_sequence`, `unexpected_sequence`,
`duplicate_sequence_id`, `unknown_kind`, `insufficient_cdrh3_novelty`.

## A developability axis we did not know we had

`abguard` implements the **LAP Antibody Liability Reference** (Satława et al., PLOS Comput Biol 2024;
20(3):e1011881) — 13 motif rules, computed per design for free:

| Severity | Tags |
|---|---|
| high | `DeAmdH` N[GS] · `FragH` DP · `Isom` D[DGHST] · `mCys` no C at IMGT 23/104 · `xCys` C outside 23/104 · `Ngly` N[^P][ST] |
| medium | `DeAmdM` N[AHNT] · `Hydro` NP · `FragM` TS · `TrpOx` W · `MetOx` M |
| low | `DeAmdL` [STK]N · `IntBind` GPR\|RGD\|RYD\|LDV\|DGE\|KGD\|NGR |

CDR-scoped motifs include one residue of framework flank each side, per LAP's convention. These are
**advisory, not gating** — only `mCys`/`xCys` overlap the hard checks.

This matters for [probe-findings.md](probe-findings.md) §4: it is a real, organiser-sanctioned
developability signal to rank on, where we previously had only a germline-likeness proxy.

```bash
$ABG/abguard liability-report <file>
$ABG/abguard team-validate --all-liabilities -o report.json <file>
```
