# Reproduce this pipeline

Written for a judge or a teammate on a machine that is not our VM. No credentials, no GPU,
no network required. Target: under a minute.

```bash
git clone <repo> && cd ai-antibodies-hackathon
bash pipeline/selftest.sh        # does it reproduce, and is it computing the right thing?
bash pipeline/run.sh             # the whole pipeline, every batch
bash pipeline/run.sh --list      # which stages need hardware you do not have
```

Only `python3` (3.9+) and `bash` are needed for everything below the line marked *laptop*.
`pipeline/score/*.py` import nothing outside the standard library and are invoked with
`python3 -I`, so a virtualenv or a stray `site-packages` cannot change the result.

---

## 1. Start with the self-test, not the pipeline

`bash pipeline/selftest.sh` — **12 checks, four kinds.** It is the honest way to decide
whether to trust anything else in this repo.

```
A. Determinism   re-run each stage into a scratch dir, byte-compare against the
                 committed output, and run it twice to catch ordering leaks.
B. Science       assert the computed interface IS the published trastuzumab footprint:
                 HER2 subdomain IV, span 557-605, 19 residues, closest contact G103 at
                 2.42 A, and 1N8Z chain B VH identical to our declared parent.
C. Negative      the four control designs must be REJECTED, each for a different reason.
                 A gate that passes everything is not a gate.
D. Refusal       rank.py must exit 3 and write nothing when the binding and ddG scores
                 are absent, instead of emitting a ranked list it cannot support.
```

A checksum only proves we re-ran something. **B is the check that matters** — it proves we
re-ran something *correct*, against a published result we did not produce. If B fails, the
numbers in `docs/epitope.md` are wrong regardless of what A says.

Expected output: `result: 12 passed, 0 failed, 0 skipped`. Exit 0.

A **SKIP is treated as suspicious, not as success.** Earlier versions of this file
hardcoded batch filenames; when teammates renamed the batches the checks degraded silently
into SKIPs and the self-test still said it passed. Both discovery loops now enumerate
`designs/raw/*.csv` and fail loudly if the directory is empty.

## 2. Then the pipeline

`bash pipeline/run.sh` runs six stages, each writing a file the next one reads.

| # | Stage | Needs | On a laptop? |
|---|---|---|---|
| 0 | fetch target | network (RCSB), or the committed structure | yes — `--offline` uses `data/target/` |
| 1 | epitope | python3 stdlib | **yes** |
| 2 | paratope | python3 stdlib | **yes** |
| 3 | abguard gate | `abguard`, our VM, login shell | no — cached verdicts committed |
| 4 | solubility | `netsolp` binary on the VM | no — cached scores committed |
| 5 | refold | Nebius API key (boltz2) | no — never launched implicitly |
| 6 | rank | python3 stdlib | yes, and refuses without scores |

Exit codes are the contract:

- **0** — everything that could run, ran and passed.
- **2** — a local stage failed. A real failure; the pipeline is broken.
- **3** — local stages passed, remote stages unavailable. **The expected result off-VM.**

Stage 5 is never launched by `run.sh` even when credentials are present, because it spends
shared GPU budget. It has to be asked for explicitly.

### Run it on a target we have never seen

This is what we expect to be asked to do at the pitch:

```bash
bash pipeline/run.sh --target 7MN8 --chain C --out runs/unseen
```

Stage 0 fetches the structure by accession and records its SHA-256; stage 1 recomputes the
interface from scratch. Nothing about stages 0–2 is specific to HER2 — the epitope code
takes chain IDs and a distance cutoff and knows nothing about this target.

The one piece that *is* trastuzumab-specific is the contact-position table in
`pipeline/score/paratope_check.py` (VH 99/103/104/105). It was read off stage 1 output by
hand, and the script asserts that each position still holds the wild-type residue it
expects, so pointing it at a different parent sequence raises `AssertionError` rather than
silently scoring the wrong positions. **It does not re-derive those positions from stage 1
at runtime** — on a genuinely new target you would re-run stage 1 and update the table.
That hand-off is the weakest link in the chain and we would rather name it than have a
judge find it.

## 3. What is pinned

| Thing | How |
|---|---|
| Target structure | accession + SHA-256 in `reports/run-*.provenance.txt`, file committed in `data/target/` |
| Python | `python3 -I`, stdlib only, `PYTHONHASHSEED=0`, `LC_ALL=C` |
| Interface cutoff | 4.5 Å all-heavy-atom, on the command line and in the output header |
| Seeds | `--seed`, default 20261114, written into every submission row |
| Model versions | `model_version` and `run_id` columns, per design |
| Golden output | `tests/expected/epitope-1n8z-4.5.txt`, byte-compared by the self-test |
| Every run | `reports/run-<UTC timestamp>.provenance.txt`: target, sha256, python, uname, git rev, which stages skipped and why |

Re-running overwrites derived reports and never touches `designs/raw/` or `data/`.

## 4. What you cannot reproduce here, and what we did about it

Being straight about this is the point of the section.

**`abguard` (stage 3)** is on the team VM in `~/.local/bin` and only on `PATH` in a login
shell. Off the VM `gate.sh` exits 127 and `run.sh` reports a skip. The verdicts it produced
are committed per batch (`reports/<batch>-novelty.csv`, `-eligible.csv`, `-liability.json`),
so stages 2 and 6 still run against real gate output. The self-test verifies the cached
**control** run instead: four designs, all four rejected.

**`netsolp` (stage 4)** is a VM-local binary at `~/tools/netsolp`, and **the VM is wiped at
the end of today.** The calibration (`reports/netsolp-calibration-spr190.csv`, 190 measured
binders, floor 0.4960) and the per-batch scores are committed; the tool is not. Vendoring it
or recording exact provenance is still open.

**`boltz2` (stage 5)** needs a Nebius key. Verified working at 63 s per call
(`nebius-runs/pae-probe.json`). **Not yet run on any design** — `min_ipae` is empty for all
191 candidates, which is why stage 6 refuses.

## 5. The honest status

Run it yourself; this is what you will see:

```
stage 1  epitope     19 HER2 residues, span 557-605            reproduces published footprint
stage 2  paratope     b1-novel-s1          121 designs,  0 keep 3/4 contacts,  0 in band
                      b2-explor-s2-fixed    70 designs, 18 keep 3/4 contacts,  8 in band
stage 6  rank        REFUSED - min_ipae and predicted_ddg absent
```

**Two of the three judged axes are unmeasured.** Axis 2 (epitope) has a cheap structural
proxy and it is doing real work — it is what separates batch 2 from batch 1. Axis 1 (SPR
binding) has no number at all yet, and axis 3 (thermostability) has none either.

So the pipeline reproduces, the gate is live, the interface is right, and the ranking
machinery refuses to pretend. What is missing is the refold, and it is missing because of
time, not because of a broken stage.

One caveat we will not bury: **the paratope score is a proxy, not the competitive binding
assay.** Contact-residue identity is not binding. A conservative substitution can keep an
interaction, and a redesigned loop can form new contacts holding the same epitope. It is
evidence about the designs, not a measurement of them — see the last section of
`docs/epitope.md`.
