# viz — antibody, antigen, and what the redesign changed

A local web app that shows each submitted design in 3D against HER2, says exactly which
CDRH3 residues changed, and measures the improvement against wild-type trastuzumab. It also
carries a pluggable inference lane, so the same screen can run a real folding or scoring
model instead of reading a file.

```bash
python3 viz/server.py                 # http://127.0.0.1:8765
python3 viz/server.py --host 0.0.0.0  # also prints a LAN URL for the room
```

Standard library only. Nothing to install. The one external asset is 3Dmol.js from cdnjs;
every number works without it, only the 3D panel needs the network.

## What it shows

| Panel | Reads |
| --- | --- |
| Design list | `designs/submission.csv`, ranked, with the epitope delta per design |
| 3D viewer | `results/cofold/<id>/model.cif` — chain **H** redesigned heavy, **L** light, **C** HER2 |
| CDRH3 | the VH 99–107 window, wild type above the design, substitutions in red, surviving contacts in green |
| Improvement | design vs wild-type trastuzumab, measured with the same scorer |
| Scores | the measured columns, plus a plain list of what is *not* measured and why |
| Provenance | which file every number came from |

In the viewer: HER2 epitope residues the binder reaches are **green**, the ones it misses are
**amber**, CDRH3 is **orange**, substituted side chains are **red** sticks labelled e.g. `G100D`.
Toggles for the antigen surface, the light chain, contact lines, and colour-by-pLDDT.

## The improvement number, and what it is honestly comparing

Wild-type trastuzumab VH on the **1N8Z crystal** touches **8 of the 19** epitope residues, scored
with the same 4.5 Å cross-chain function used on the designs (`backends.wt_baseline`). That is
the reference line in every bar.

Two things kept deliberately straight:

* The comparison is **VH against VH**. The 19-residue epitope was defined from the whole Fab,
  so the light chain accounts for the residues neither VH reaches. Comparing a design's VH to
  the Fab total would invent a deficit that is not there.
* **Epitope recovery is comparable; raw contact counts are not.** The baseline is a crystal
  structure and the designs are Boltz-2 co-folds. The UI marks the contact-count row
  "not like-for-like" rather than quietly ranking on it. For a true like-for-like contact
  count, co-fold wild-type trastuzumab through the same lane.

On the current submission the rank-1 design reaches **11/19 (+3 over wild type)** while keeping
3 of the 4 measured paratope contacts, at 6 CDRH3 mutations — above abguard's ≥6 target.

## Inference lanes

One contract, four lanes (`viz/backends.py`). The UI never changes when the lane does.

| Lane | What runs | Cost |
| --- | --- | --- |
| `dummy` | **Default.** Measures the local co-fold mmCIF (contacts, epitope hits, pLDDT from the B-factor column) and stands in for the rest, deterministically from a hash of the sequence. Every stand-in is flagged `measured: false` with a basis string. | free, instant |
| `japanfold` | **Real inference.** `af2ig` scores an existing co-fold and returns **ipTM and interface pAE**; `openfold3` / `opendde-abag` co-fold from scratch, optionally steered onto the epitope. | ~$0.005–0.03 per design |
| `vm` | Apheris Foundry `foundry-toolkit predict` inside our VM, over ssh. | VM time |
| `nebius` | The hosted boltz2 lane. Queued submit+poll — launch it with `pipeline/score/refold.sh`; results land in `results/cofold/` and the viewer picks them up. | queue |

The dummy lane exists so the demo never depends on a queue, and so the UI is exercised
against the real contract rather than a mock that drifts from it.

```bash
python3 viz/backends.py --self-test   # cross-checks against reports/*.csv
python3 viz/backends.py --lanes       # which lanes can run right now
python3 viz/catalog.py --summary      # the whole table, one line per design
```

`--self-test` is not a smoke test: it re-derives every CDRH3, mutation count and paratope
verdict from the heavy sequences and asserts they equal `reports/*-paratope.csv`, and
re-measures the co-folds and asserts they equal `reports/cofold-contacts.csv`. If the viewer
ever disagrees with the submission, it fails.

## JapanFold — the lane that closes the axis-1 gap

`docs/tools-nebius.md` records that the hosted co-folders return **no ipTM and no PAE**, which
is why `submission.csv` carries `n/a` in `iptm`, `ipsae` and `min_ipae` and why
`cofold_contacts.py` counts geometry instead. JapanFold's **`af2ig`** (AlphaFold2
initial-guess) takes a designed complex — target coordinates plus the binder sequence, which
is exactly what `results/cofold/*/model.cif` already is — and reports ipTM and interface pAE.
No MSA, no sampling, so the same input gives the same answer.

With `write_pae: true` it also returns the full PAE matrix, which the service describes as
"the one Adaptyv's ipSAE pipeline reads" — that feeds the `ipsae` column.

Also available and relevant: **`openfold3`** (the OpenFold Consortium model —
`docs/tools-apheris.md` flags OpenFold for the monetary prize, so this is a second
independent way to satisfy it) and **`opendde-abag`**, an antibody–antigen checkpoint that
accepts `site` constraints, so a refold can be steered onto the 19 HER2 epitope residues.

Scoring all 18 folded designs with `af2ig` costs about **$0.09** (p90 $0.40), from 990 past jobs.

### Setting the key

The team key is in `japanfold-oslo-hackathon-codes 4.txt` in the Slack folder.
`docs/SETUP.md` §6 says not to copy it into any file in this repo and not to paste it in a
chat, so **point at it where it already is**:

```bash
export JAPANFOLD_KEY_FILE="$HOME/Downloads/japanfold-oslo-hackathon-codes 4.txt"
```

The client pulls the key out of that file without echoing it, and handles the file being
prose with the key somewhere inside rather than a bare token. Alternatives, in precedence
order: `$JAPANFOLD_API_KEY` in your own shell; a `japanfold` field in
`credentials.private.json`; `viz/japanfold.key` as a last resort (gitignored, but SETUP.md
would rather you did not create it).

Without the Slack file, a personal key comes from
<https://japanfold.aiand.com/account/token> — a new account carries $100 of credit.

`.mcp.json` registers the same service as an MCP server for Claude Code, reading
`${JAPANFOLD_API_KEY}` from the environment so the key stays out of the commit. A new session
picks it up.

```bash
python3 viz/japanfold.py --check                   # key, reachability, balance
python3 viz/japanfold.py --models                  # catalogue and prices, free
python3 viz/japanfold.py --estimate af2ig --all    # price the batch, start nothing
python3 viz/japanfold.py --score-af2ig b2-explor-s2-fixed-her2_cdrh3_187 --yes
python3 viz/japanfold.py --score-af2ig --all --yes # the whole submission
```

### Spending is gated

Nothing bills while a page loads: everything on arrival is read from files the pipeline
already wrote. `POST /api/predict` on a billed lane returns **402 with the price** unless the
request carries `confirm=true`, and the UI turns that into a confirm dialog quoting the
median cost. The CLI requires `--yes`. `--estimate`, `--models` and `--check` start nothing.

## API

| Route | |
| --- | --- |
| `GET /api/catalog` | every design: sequences, mutations, scores, improvement, provenance |
| `GET /api/design/<id>` | one design |
| `GET /api/structure/<id>` | its co-fold mmCIF |
| `GET /api/baseline/structure` | 1N8Z, the trastuzumab–HER2 crystal |
| `GET /api/lanes` | which lanes can run |
| `GET /api/price?model=&n=` | what a run would cost; starts nothing |
| `POST /api/predict` | `{design_id, lane, mode, model, confirm}` |

## Files

```
viz/
  server.py     stdlib HTTP server, static + API
  catalog.py    one record per design, assembled from submission.csv + reports/ + mmCIFs
  backends.py   the prediction contract, the four lanes, mmCIF/PDB readers, the WT baseline
  japanfold.py  JapanFold REST client: af2ig scoring, co-folding, pricing, artifacts
  static/       index.html, app.js (3Dmol), style.css
```

`backends.py` holds the reference constants — `TZ_VH`, the CDRH3 window, the four paratope
positions, the 19 epitope residues — copied from the scorers with a comment naming the
source, so the viewer reports numbers that agree with `reports/` instead of its own.
