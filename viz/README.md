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
**amber**, CDRH3 is **orange**, substituted side chains are **red** sticks labelled e.g. `G100D`,
the redesigned heavy chain is **blue** and the unchanged light chain is **violet**. Toggles for
the antigen surface, the light chain, contact lines, and colour-by-pLDDT.

The palette is defined once, in `static/style.css` `:root`, and `app.js` reads it back from
there — so a colour is changed in one place and the 3D view, the legend and the CSS swatches
cannot drift apart. The light chain used to be `#7d8da0`, a hair from the antigen's own pale
grey, which on a projector made the light chain and HER2 read as one object.

## Two views

A tab in the header switches between them:

* **design review** — the three-column screen above: one design at a time, in 3D.
* **what we built** — the whole project on one page: the three judged axes with their real
  coverage, which designs are *not* folded and why, the pipeline stage by stage, every table
  with its row count, and the JapanFold lane with its live job list. It is a read-only pass
  over the repo (`viz/overview.py`, also runnable as `python3 viz/overview.py`), so it costs
  nothing and every path on it can be opened while it is on screen.

Coverage there is counted by **joining against the candidate pool**, never by counting rows in
a score table — a table full of ids that join to nothing would otherwise read as full
coverage, which is the blindness `pipeline/score/rank.py` was written to fix.

## Two designs have no structure, and the viewer says so

`designs/submission.csv` has 20 rows; `results/cofold/` holds 18 complexes. The missing two,
`b2-explor-s2-fixed-her2_cdrh3_26` and `…_67`, had their hosted Boltz-2 co-folds **fail** on
the platform (`EXECUTION_FAILED`, "inference outcome unknown (HTTP 000, no response
captured)") — the platform states its own failure does not implicate the inputs. Nobody
noticed because every `nebius-runs/*.json` record is written at submit time saying `queued`
and was never re-polled; `scripts/reconcile_runs.py` now corrects that (21 succeeded, 2
failed).

This matters to the af2ig lane specifically: **af2ig scores a complex you already have**, so
on those two it can only fail. The lane picker disables it for a design with no structure,
says why, and pre-selects the OpenFold3 co-fold that would fix it:

```bash
python3 viz/japanfold.py --fold b2-explor-s2-fixed-her2_cdrh3_67 --model openfold3 --yes
```

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

### One job, eighteen designs

A prediction runs **each target on its own chip** and is billed per chip-second, so the whole
submission goes in a single job as a `targets` list: one queue wait instead of eighteen.

That also fixes a price this file used to quote. `GET /v1/models` publishes both per-job and
per-target figures and warns against the former: af2ig's per-**job** median is $0.0049 across
a typical batch of 12 targets, i.e. about **$0.0004 a target**. Multiplying the per-job median
by 18 gave "$0.09", roughly 13x the real figure. Scoring all 18 folded designs is about
**$0.007** (p90 $0.018), from 990 past jobs. `--estimate` now prices it this way and says
which basis it used.

### Setting the key

Keep it in `.env` at the repo root, which is gitignored:

```bash
cp .env.example .env
# then fill in JAPANFOLD_API_KEY=...
```

`viz/japanfold.py` reads `.env` by itself, so a fresh terminal needs nothing exported and
the secret lives in exactly one place. A real shell variable still overrides the file.

Sources, in precedence order:

1. `$JAPANFOLD_API_KEY` exported in your shell
2. `.env` at the repo root ← **the recommended one**
3. `$JAPANFOLD_KEY_FILE` — a path to the Slack `japanfold-oslo-hackathon-codes 4.txt`, read
   in place. The client extracts the key without echoing the file, and copes with the file
   being prose with the key somewhere inside rather than a bare token
4. `viz/japanfold.key`
5. a `japanfold` field in `credentials.private.json`

`python3 viz/japanfold.py --check` prints which source it used — the source, never the value.

The team key is in `japanfold-oslo-hackathon-codes 4.txt` in the Slack folder; a personal key
(with $100 of credit) comes from <https://japanfold.aiand.com/account/token>. `docs/SETUP.md`
§6 is the standing rule: never commit it, never paste it into a chat. If a key does reach a
chat, a log or a commit, treat it as burned and reissue it — `POST /v1/keys` issues a new one
and `DELETE /v1/keys/{hash_prefix}` switches the old one off.

`.mcp.json` registers the same service as an MCP server for Claude Code, reading
`${JAPANFOLD_API_KEY}` from the environment so the key stays out of the commit. A new session
picks it up.

```bash
python3 viz/japanfold.py --check                   # key, reachability, balance
python3 viz/japanfold.py --models                  # catalogue and prices, free
python3 viz/japanfold.py --estimate af2ig --all    # price the batch, start nothing
python3 viz/japanfold.py --score-af2ig b2-explor-s2-fixed-her2_cdrh3_187 --yes
python3 viz/japanfold.py --score-af2ig --all --yes # the whole submission, one job
python3 viz/japanfold.py --watch JOB_ID            # re-attach to a job already running
python3 viz/japanfold.py --jobs                    # recent jobs on this key
python3 viz/japanfold.py --key-help                # every way to set the key
```

### What it writes, and what then reads it

A finished run writes `reports/japanfold-af2ig-metrics.csv` **in the same schema as
`reports/b*_refold_metrics.csv`**, because that is the schema the rest of the pipeline
already reads. Nothing new has to learn about this lane:

```bash
python3 pipeline/score/rank.py --refold reports/japanfold-af2ig-metrics.csv --allow-partial
```

ranks on a measured `min_ipae` instead of refusing, and `viz/catalog.py` picks the same rows
up on the next page load. Per design it also keeps
`../results/japanfold/af2ig/<design_id>/` — the exact `input.yaml` sent, `score.json`, the
PAE matrix, and the job id, so any number on screen can be traced back to the run that
produced it.

`ipsae` is **computed here, by us**, from the `*_pae.npz` the service returns — JapanFold
returns the matrix and no ipSAE of its own. Every report of it says so, and the chain split
is verified against the input before it is computed: if the token axis is not exactly
`target + binder`, no ipSAE is written rather than a wrong one.

### Live, and resumable

`--score-af2ig` prints a status line that rewrites in place: queue position, chips busy,
targets done, elapsed. It follows the job with `GET /jobs/{id}?wait=60`, which the service
holds open until the job ends, so a finished job is seen the moment it finishes and the loop
never sleeps on a timer. Two of the service's rules are honoured rather than discovered the
hard way: one account is held on two jobs at a time (another reason for one batched job), and
a refused hold is the only thing that triggers a sleep, for exactly its `Retry-After`.

Every submit carries an **`Idempotency-Key`**, written to disk *before* the request goes out.
If a submit times out, re-running it returns the first job instead of starting a second one to
pay for. And a job is never lost by closing the laptop: `--watch JOB_ID` re-attaches from any
machine with the same key, downloads the artifacts and writes the same CSV.

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
| `GET /api/overview` | what the project produced: axes, gaps, stages, every artifact |
| `GET /api/jobs` | recent JapanFold jobs on this key (read-only, bills nothing) |
| `GET /api/job/<id>` | one job's live status, for the progress line |
| `GET /api/price?model=&n=` | what a run would cost; starts nothing |
| `POST /api/predict` | `{design_id, lane, mode, model, confirm}` |

## Files

```
viz/
  server.py     stdlib HTTP server, static + API
  catalog.py    one record per design, assembled from submission.csv + reports/ + mmCIFs
  backends.py   the prediction contract, the four lanes, mmCIF/PDB readers, the WT baseline
  japanfold.py  JapanFold REST client: af2ig scoring, co-folding, pricing, artifacts
  overview.py   "what we built": axes, coverage, gaps, artifacts, read off disk
  static/       index.html, app.js (3Dmol), style.css
```

`scripts/reconcile_runs.py` belongs to the same honesty: it re-polls every `nebius-runs/*.json`
and writes the platform's real answer back, keeping `state_at_submit` beside it.

`backends.py` holds the reference constants — `TZ_VH`, the CDRH3 window, the four paratope
positions, the 19 epitope residues — copied from the scorers with a comment naming the
source, so the viewer reports numbers that agree with `reports/` instead of its own.
