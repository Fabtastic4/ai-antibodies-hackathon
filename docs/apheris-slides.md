# The Apheris challenge slides — and where they contradict the task PDF

Source: `2026-11_Oslo_hackathon_Apheris_challenge.pdf`, presented on the day and posted to Slack by
Leonardo Castorina (Apheris) at 10:17, together with the S3 layout below. **These slides are newer than
the task PDF** (which is dated 6 November), so where they disagree, ask an organiser — do not assume
either one silently wins.

## Four differences that change what we do

### 1. Optimisation designs must be the same format as trastuzumab

Slide 6, optimisation column: **"Same format as trastuzumab"**. The task PDF never says this — it lists
VHH, scFv or Fab for both tracks.

Trastuzumab is an IgG1, so as a submittable format that means **Fab or scFv — not VHH**. Consequences:

- Generation on the optimisation track produces **paired H+L designs**, so `antifold` runs with
  `heavy_chain` and `light_chain` set, not `nanobody_mode`.
- **This is good news for thermostability.** `stab-ddg` needs two disjoint partner chain sets, so the
  VH–VL interface ΔΔG proxy (see [probe-findings.md](probe-findings.md) §4) is now available for
  *every* optimisation design instead of only some. The "optimisation + VHH has no stability signal"
  cell disappears from that matrix.
- The ~250 aa cap is described on slide 6 as "up to ~250 aa **in scFv format**", which reads as the cap
  applying to the fused single chain.

**TODO: confirm.** If "same format" is enforced literally, a VHH optimisation design is rejected. Issue
[#7](../../issues/7).

### 2. The mutation bar is "≥2", not "more than 2"

Slide 6: **"≥2 mutations away from every sequence in the provided data"**.

The task PDF said "at least 2" on p2 but "strictly more than 2" in the hard-filter list and the
`abguard` flowchart. **The slides side with the looser reading**, and they are the newer source. Issue
[#12](../../issues/12) was opened on exactly this contradiction; this is now the best evidence we have,
but it is still a slide against a flowchart — worth one sentence from a mentor before we rely on it.

Until confirmed we keep generating to the stricter reading (≥3), which is valid under both.

### 3. "The provided data" is 525,063 CDRH3 sequences

From Leonardo's Slack message: *"The HER2 tables are the provided data for the novelty filter: your
design's CDRH3 must differ from all 525,063 in them."*

That is the FACS binding-class table (524,346 CDRH3s) plus the SPR affinity table (768 variants). So the
mutation check is not against a handful of reference antibodies — it is against **half a million
measured CDRH3 loops**. Our novelty pre-check needs that table loaded, not a short reference list.

### 4. Identity thresholds are written with ≤ and <

Slide 6 writes optimisation as **≤70%** CDRH3 identity and de novo as **<70%** identity. The task PDF
writes both as "under 70%". The boundary case only matters for a design landing exactly on 70%, which we
should simply avoid rather than litigate.

Also new: de novo identity is checked **against Adaptyv's antibody database** (slide 6), which names the
"known databases" the task PDF left unspecified.

## Numbers the slides confirm or revise

| | Task PDF | Slides | Use |
|---|---|---|---|
| Teams | not stated | **16** (slide 7: "4 per team × 16 teams") | 16 — confirms `START-HERE.md` |
| Total designs tested | not stated | **100** (64 guaranteed + 36 extra) | 100 |
| Base per team | 4 | 4 | agree |
| Placement bonus | +12 / +8 / +4 | +12 / +8 / +4 | agree |
| Judge nominations | +2 × 6 judges | +2 × 6 judges | agree |
| Prize pot | **€3000** total, €800/€500/€200 per track | **$1,500 per track**, $720 / $360 / $270, *"draft amounts, total prize fund to be confirmed"* | unresolved — the slides label themselves draft |
| Tiering | S/A/B, S-tier count first | same, and **ranked separately in each track** | agree |

The prize figures are the one place the two organiser sources flatly disagree, and the slides mark their
own numbers as draft. It does not change our strategy either way: each track is ranked separately and
the pot splits evenly, so concentrating on optimisation costs nothing.

## RFD4-Proteina, as the slides describe it

Three checkpoints — **General** (binders, enzymes, scaffolds), **Antibody** (VHH and VH/VL) and
**HER2 Finetuned** ("fine-tuned for this challenge"). Pipeline is **Design → Refold → Score**.

Refolding is defined on slide 4: *"a folding model, given only the sequence, must fold each design into
the designed complex."* Integrated folding models: Protenix v2, Protenix v1, Mol-1, ESMFold2, OpenFold3
OpenBind, OpenFold3, Boltz-1, Boltz-2 — consistent with the task PDF's table, and consistent with our
rule that the ranking refold uses a template-taking model while ESMFold2 is only a second opinion.

## The data, and where it is

Everything is already on the team VM. Leonardo's layout:

```
s3://apheris-oslo-hackathon/
├── data/                                 ~5 GB, README.md explains every file
│   ├── her2-trastuzumab/                 FACS binding classes (524k CDRH3s), SPR affinities (768 variants)
│   ├── zenodo-18390239-ab-ag-complexes/  scores for 1.8M predicted nanobody–antigen complexes
│   ├── sigma2-ab-ag-champloo/            per-sample confidence (ipTM, pLDDT, PAE) for those predictions
│   │   └── spr-supplementary/            measured SPR for a few of those pairs
│   └── zenodo-10831512-trastuzumab-ngs/  ready-made train/val/test splits of the FACS data
└── rfd4-proteina/docs/                   Apheris Foundry and RFD4-Proteina instructions
```

```bash
aws s3 sync s3://apheris-oslo-hackathon/data/ hackathon-data/
aws s3 sync s3://apheris-oslo-hackathon/rfd4-proteina/docs/ ~/rfd4   # then open ~/rfd4/Tutorial.html
```

- `foundry.md` — running RFD4-Proteina through Foundry (UI, CLI and agents), design to evaluation.
- `18-vm.md` ("Run on your hackathon VM") — **start here**: the VM has no Foundry Hub, but every Foundry
  model is already on it as a Docker image. This confirms [probe-findings.md](probe-findings.md) §2 — the
  HER2 checkpoints are VM-local Docker images, not `forge.py` jobs.

Two things worth noticing in that tree. `sigma2-ab-ag-champloo/` carries **per-sample PAE** for 1.8M
predicted complexes — PAE that the Nebius models would not give us, with measured SPR for some pairs in
`spr-supplementary/`. That is a calibration set: it tells us what confidence score actually predicts
binding, instead of assuming. And `zenodo-10831512-trastuzumab-ngs/` ships **ready-made train/val/test
splits**, which removes the main excuse for not training our own ranker on measured data.

Leonardo's closing note: *"Try to do some cool things with the data! Things like data analysis, binding
prediction etc… Try to bring in other models you think are cool!"*
