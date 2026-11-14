# Epitope and paratope — trastuzumab / HER2

Owner: W2 deliverable (12:30 milestone). Computed 14 Nov 14:15 from the structure, not from
literature recall.

**Source structure.** PDB **1N8Z**, trastuzumab Fab bound to the HER2 extracellular domain,
downloaded 14 Nov 2026 from `https://files.rcsb.org/download/1N8Z.pdb` into
`data/target/1n8z.pdb` (703 kB), sequences in `data/target/1n8z.fasta`.
Chains: **A = VL**, **B = VH**, **C = HER2 ECD** (581 resolved residues).

**Method.** `pipeline/score/epitope.py` — all-heavy-atom minimum distance, cutoff **4.5 Å**,
first model, altloc A only, waters and hetero-residues dropped. Reproduce:

```bash
python3 pipeline/score/epitope.py data/target/1n8z.pdb 4.5
```

Chain B's VH sequence in 1N8Z is identical to our `parent=trastuzumab` VH, and chain B residue
numbers coincide with 1-based positions over that VH sequence in the CDRH3 region, so the contact
positions below can be applied to our design tables directly.

---

## Epitope — HER2, 19 residues

Three loops in **subdomain IV**, spanning HER2 **557–605**:

| Loop | Residues |
|---|---|
| 1 | P557, E558, D560, Q561 |
| 2 | K569, D570, P571, P572, F573, P579 |
| 3 | I591, K593, D596, E598, A600, Q602, P603, C604, P605 |

Flat list for downstream tools:

```
P557,E558,D560,Q561,K569,D570,P571,P572,F573,P579,I591,K593,D596,E598,A600,Q602,P603,C604,P605
```

This is the epitope criterion 2 is judged on (competitive binding assay). It matches the published
domain IV footprint, which is the check that the extraction is right.

## Paratope — Fab, 20 residues

| Chain | Residues |
|---|---|
| **VH** (B), 10 | Y33, R50, Y52, Y57, T58, R59, **W99, G103, F104, Y105** |
| **VL** (A), 10 | D28, N30, T31, A32, S50, F53, H91, Y92, T93, T94 |

Numbering is sequential over each variable domain (1-based), as in 1N8Z. IMGT numbering is **not**
recorded here — run ANARCI on the VM and append it rather than hand-converting; nothing downstream
needs IMGT today and a wrong conversion is worse than an absent one.

### The half of the paratope we cannot touch

**VL contributes 10 of the 20 interface residues — half the paratope — and our light chain is
frozen.** Every design in batch 1 shares one identical `light_sequence`. The HER2-fine-tuned
Apheris weights redesign CDRH3 only, so VL contact is carried over from trastuzumab unchanged.
That is a point in our favour on epitope preservation, and it is the reason a CDRH3-only
optimisation can plausibly keep the epitope at all.

### The four residues that matter in CDRH3

Only **4 of the 10 VH contacts** fall inside the generator's mutable window (VH 99–107,
wild-type `WGGDGFYAM`):

| VH position | Wild type | Min distance to HER2 | HER2 partners |
|---|---|---|---|
| 99 | W | 4.05 Å | 2 |
| **103** | **G** | **2.42 Å** | 4 |
| 104 | F | 4.27 Å | 1 |
| 105 | Y | 3.32 Å | 4 |

**G103 is the closest contact in the entire interface** (2.42 Å, 4 partners). The other five window
positions — 100, 101, 102, 106, 107 — make no contact at 4.5 Å and are free to mutate.

---

## Measured on batch 1: the novelty target is ablating the paratope

`pipeline/score/paratope_check.py` over the 121 unique eligible designs in
`reports/<batch>-eligible.csv`. Full per-design table: `reports/<batch>-paratope.csv`.

```bash
python3 pipeline/score/paratope_check.py reports/<batch>-eligible.csv \
    designs/raw/<batch>.csv
```

| CDRH3 contacts preserved | Designs | Share |
|---|---|---|
| 4 of 4 | 0 | 0% |
| 3 of 4 | **0** | **0%** |
| 2 of 4 | 16 | 13.2% |
| 1 of 4 | 68 | 56.2% |
| 0 of 4 | 37 | 30.6% |

| Contact | Designs that mutate it |
|---|---|
| **F104** | **121 / 121 — 100%** |
| **G103** (closest, 2.42 Å) | 117 / 121 — 96.7% |
| W99 | 108 / 121 — 89.3% |
| Y105 | 38 / 121 — 31.4% |

**Not one design in the batch preserves more than 2 of the 4 contact residues, and F104 is lost in
every single one.**

### It is a structural conflict, not bad luck

Mutation count against contacts preserved:

| CDRH3 mutations | 2 kept | 1 | 0 | n |
|---|---|---|---|---|
| 5 | 6 | 0 | 0 | 6 |
| 6 | 4 | 13 | 0 | 17 |
| 7 | 6 | 36 | 3 | 45 |
| 8 | 0 | 19 | 29 | 48 |
| 9 | 0 | 0 | 5 | 5 |

The window is 9 residues and 4 of them touch HER2, so mutations and contact preservation compete
for the same positions. The 13:25 decision set the novelty floor at **≥6 mutations** because
abguard measured 5 → 44% and 3–4 → 0/12. But at 8–9 mutations, **34 of 53 designs keep zero
contacts**. The ≥6 floor was derived from the gate alone, with no interface term, and it is
pointing generation at designs that pass the filter by destroying the binding site.

Criterion 1 (SPR binding) and criterion 2 (epitope preserved) are two of the three judged axes.
The gate does not measure either.

### The arithmetic of the window

Holding contacts fixed caps the achievable mutation count:

| Hold fixed | Free positions | Max mutations | abguard pass at that count (batch 1) |
|---|---|---|---|
| all 4 contacts | 100,101,102,106,107 | 5 | 44% |
| G103 + F104 + W99 | 100,101,102,105,106,107 | **6** | **83%** |
| G103 + F104 | 100,101,102,105,106,107 + W99 | 7 | 79% |
| nothing (batch 1) | all 9 | 9 | 70.5% overall |

**Holding W99 + G103 + F104 still allows 6 mutations at an 83% measured novelty pass rate.** That
is the band to generate in: 3 of 4 contacts preserved and the novelty floor met at the best pass
rate in the table. It is a constraint on *which* positions move, not on how many — so it costs
nothing against the gate.

---

## Batch 2 confirms the prediction — the constraint works

`b2-explor-s2-fixed` (exploratory weight, seed 2) landed at 14:25, after the analysis above
was written. It was generated with CDRH3 positions held, and it is the test of the claim.
Same script, same interface, 70 unique eligible designs:

| CDRH3 contacts preserved | b1-novel-s1 | **b2-explor-s2-fixed** |
|---|---|---|
| 3 of 4 | 0 (0%) | **18 (25.7%)** |
| 2 of 4 | 16 (13.2%) | 26 (37.1%) |
| 1 of 4 | 68 (56.2%) | 19 (27.1%) |
| 0 of 4 | 37 (30.6%) | 7 (10.0%) |

| Contact | b1 mutated | **b2 mutated** |
|---|---|---|
| W99 | 89.3% | **45.7%** |
| G103 | 96.7% | **54.3%** |
| F104 | 100% | 75.7% |
| Y105 | 31.4% | 45.7% |

**G103 preserved: 3.3% → 45.7%.** And the band the arithmetic above predicted is populated:
**8 designs at 6 mutations keeping 3 of 4 contacts**, every one of them holding exactly
W99 + G103 + Y105 and spending F104:

```
b2-explor-s2-fixed-her2_cdrh3_134  WFWHGTYSY   6 muts  W99+G103+Y105  lost F104T
b2-explor-s2-fixed-her2_cdrh3_139  WYNRGEYQF   6 muts  W99+G103+Y105  lost F104E
b2-explor-s2-fixed-her2_cdrh3_187  WDAPGSYSV   6 muts  W99+G103+Y105  lost F104S
b2-explor-s2-fixed-her2_cdrh3_2    WHPMGTYVF   6 muts  W99+G103+Y105  lost F104T
b2-explor-s2-fixed-her2_cdrh3_26   WDDYGNYYY   6 muts  W99+G103+Y105  lost F104N
b2-explor-s2-fixed-her2_cdrh3_52   WYLGYFYEY   6 muts  W99+F104+Y105  lost G103Y
b2-explor-s2-fixed-her2_cdrh3_67   WNAHGGYWY   6 muts  W99+G103+Y105  lost F104G
b2-explor-s2-fixed-her2_cdrh3_93   WPNRGLYSP   6 muts  W99+G103+Y105  lost F104L
```

Six mutations at the 83% novelty band *and* three of four contacts, which the 13:25 ≥6 floor
said was unreachable and which 121 batch-1 designs never once produced. The constraint costs
nothing against the gate.

Two things to be careful about before treating these as the submission:

- **This is the exploratory weight**, which the task PDF's own table scores at 0.3% known-binder
  recovery. Good novelty, weakest affinity prior of the three. The contact residues survived;
  that is not the same as the loop being a good binder. Re-running the constraint on
  `her2-novel-2026-11-09` is the missing experiment.
- **F104 is spent in 7 of the 8.** It is the shallowest of the four contacts (4.27 Å, 1 partner),
  so it is the right one to spend, but no design in either batch keeps all four.

## What this does not prove

- Contact-residue identity is a **proxy** for epitope preservation, not the assay. A design can
  substitute a contact conservatively (Y105→F, G103→A) and keep the interaction, and a redesigned
  loop can form a new contact that holds the same epitope. The competitive binding assay is the
  judge, and we cannot run it.
- Nothing here is a refold. The claim is "these designs delete the measured contact residues",
  not "these designs do not bind". Confirming the second needs the boltz2 co-fold against
  `data/target/1n8z.pdb` chain C, which is still unrun — `scored = 0` in `pipeline/status.py`.
- One batch, one weight, one seed.

The proxy is cheap, needs no GPU, and runs in under a second on a batch. At **0/121 keeping 3 of 4
contacts and 100% loss of F104**, the signal is too one-sided to be sampling noise, which is why it
is worth acting on before the refolds come back.
