# Settled unknowns — 14 Nov, ~11:15

Five read-only probes against the live platform. **No compute jobs were spent.** Every claim below is
from a schema read, an installed skill doc, or local computation — not from memory.

Four of these contradict the plan the team was working from. Read the consequences, not just the facts.

---

## 1. ipSAE is not computable on Nebius. Drop it as the ranking metric.

ipSAE needs the per-residue PAE matrix. No reachable Nebius model documents returning one.

| Model | lane | PAE | ipTM | pTM | pLDDT |
|---|---|---|---|---|---|
| `boltz2` | native ~80 s | **no — explicitly excluded** | **no** | yes | yes |
| `openfold3` | native ~3 min | not stated | **yes** (skill doc prose) | yes | yes |
| `chai1` | file/submit ~270 s | absent | absent | absent | absent |
| `alphafold3` | batch | not delivered | file-level only | — | — |
| `openfold3-openbind` | batch | absent | absent | absent | absent |
| `protenix-v2` | batch ~20 min | absent | absent | absent | absent |

The gateway contract states boltz2 "does not expose ... **full-PAE** features", and RECIPES says
outright "The output has **no ipTM**, so do not report one." Five of six models publish no output
schema at all, so for those, "which fields come back" is unanswerable until a run returns — that
absence is itself the finding.

Lane note: `chai1` is a **file-lane submit** model, not batch — `forge.py` registers it as
`("file", "submit_chai1", "predict", 270)`, i.e. 270 s; the resource map lists it as "submit, 5 min".
Use 5 min for planning, 270 s is the registered estimate. (`docs/tools-nebius.md` also says 5 min.)

`alphafold3` and `openfold3-openbind` have graph deadlines of 12.5 h and 25 h. **Not reachable before
18:00.** Do not queue them.

**What we rank on instead:**
1. `iptm` from `openfold3` (native, ~3 min) — the only interface-aware score named for any reachable
   Nebius model. Caveat: skill-doc prose, hedged as "as rendered by the adapter". **Unverified until
   one real co-fold returns.** Whoever runs the first openfold3 co-fold must read `result.json` and
   confirm the key — treat that as a deliverable of the run, not a side effect.
2. **Cross-chain heavy-atom contact count from the returned mmCIF**, plus pTM and interface ΔSASA.
   Local post-processing, zero platform cost, works on every model in the table, depends on no
   undocumented adapter field. This is the belt-and-braces default and RECIPES recommends it directly.
3. True PAE-derived `min_ipae` exists **only via Apheris Foundry** `refold-score` on the VM. If we want
   an ipSAE-like number for the pitch, it comes from there, not from Nebius.

Standing caveat: none of pLDDT, PAE, ipTM or ipSAE is a K<sub>D</sub>. The judged axis is SPR affinity.

## 2. The antibody and HER2 RFD4 checkpoints are VM-only.

`forge.py` exposes **no checkpoint selector** for `rfd4-proteina` and cannot be made to. The four
weights (`release-2026-10-19`, `antibody-2026-10-30`, `her2-2026-11-07`, `her2-novel-2026-11-09`) exist
only as **Apheris Foundry Docker images on the team VM**, selected by choosing the image.

Nebius's hosted `rfd4-proteina` is the general checkpoint — "a general protein binder, not a VHH,
RFD4-Proteina has no antibody prior". A general mini-binder is **not** VHH, scFv or Fab, so it fails the
format gate before anything else is considered.

**Consequence:** de novo generation runs on the VM through Foundry. Whoever owns that track needs SSH
working before they can start — it is not a `forge.py` job. See [tools-apheris.md](tools-apheris.md).

## 3. antifold does **not** win the epitope axis for free.

This was the main argument for prioritising the optimisation track, and it is wrong as stated.

Keeping the framework does preserve most of the molecule. Two separate things are true, and the old
version of this section conflated them.

**(a) The eligibility rules do force a ≥4-residue rewrite of CDRH3.** Arithmetic, checkable in 60 s:

- Optimisation designs are valid only with **CDRH3 identity to trastuzumab under 70%** (task PDF p2).
- Trastuzumab CDRH3 = `WGGDGFYAMDY`, **11 residues**. Source of that sequence: the motif list in
  `scripts/epitope.py`, matched in 1N8Z chain B starting at position 99 (`identity_motif_evidence` in
  `data/reference/epitope/1n8z_epitope_report.json`), so B:99–109. **No organiser source states the
  CDRH3 sequence or its boundaries** — it is our own input. Weak corroboration only: the task PDF's
  variant dataset has "up to 10 mutated positions in CDRH3" (p4), consistent with an 11-mer.
- 8 of 11 identical = 72.7% ≥ 70% → **fails**. 7 of 11 = 63.6% < 70% → **passes**. So ≥ 4 mutations.
- **TODO: confirm how abguard computes CDRH3 identity.** The arithmetic above holds only if identity
  is over the 11-residue loop alone. A wider window (loop + flanks, or whole VH) moves the floor.
  Ask a mentor on site — cheap to ask, expensive to get wrong.

**(b) CDRH3 does *not* carry most of trastuzumab's HER2 contact.** Our own artifact says otherwise.
Recomputed from the ΔSASA column of `data/reference/epitope/1n8z_interface_residues.csv` (21 listed
interface residues on the Fab side; A = light, B = heavy):

| Paratope element | buried ΔSASA | share of 689.2 Å² |
|---|---|---|
| CDRH3 only — B:W99 15.7, G103 62.7, F104 6.0, Y105 68.4 | **152.8 Å²** | **22%** |
| whole heavy chain B | 332.6 Å² | 48% |
| whole light chain A | 356.6 Å² | 52% |

The two largest single contributors are **light** chain: A:N30 and A:Y92 at 74.0 Å² each, both ahead of
the best heavy residue B:Y105 (68.4 Å²). 689.2 Å² is the sum over the 21 listed residues; against the
report's whole-Fab burial of 705.9 Å² the CDRH3 share is 21.6% — ~22% either way. (The old claim
"heavy chain dominates epitope residues 557–593" is true, but it is about the **HER2** side and says
nothing about CDRH3's share of the paratope. See section 5.)

Per CDR, same CSV. Loop boundaries are **ours**: H2 and H3 and L3 anchored on the motif matches in
`1n8z_epitope_report.json` (`RIYPTNGYTR` at B:50, `WGGDGFYAMDY` at B:99, `QQHYTTPPT` at A:89), H1/L1/L2
assigned by inspection of the canonical set in section 5. No organiser source defines them.

| Loop | buried ΔSASA | share |
|---|---|---|
| CDR-H3 | 152.8 Å² | 22% |
| CDR-H2 (B:R50 Y52 Y57 T58 R59) | 150.9 Å² | 22% |
| CDR-L1 (A:D28 N30 T31 A32) | 129.3 Å² | 19% |
| CDR-L3 (A:H91 Y92 T93 T94) | 129.2 Å² | 19% |
| CDR-L2 (A:S50 F53) | 87.4 Å² | 13% |
| CDR-H1 (B:Y33) | 28.9 Å² | 4% |
| A:Y49 (4.5–5.0 Å only, outside the 4.5 Å set) | 10.7 Å² | 2% |

**Does the conclusion survive? Yes, but on much weaker grounds — say so in the pitch.** What the data
supports: CDRH3 is the **largest single loop, by 1.9 Å² over CDR-H2** — i.e. effectively tied, not
dominant. It is a fifth of the paratope, it holds the best heavy-chain residue, and the ≥4-residue
rewrite is **mandatory, not optional**. Re-burying a fifth of the interface differently can move the
epitope. What the data does **not** support: that CDRH3 does most of the binding, or that it is a
uniquely risky loop. Four other loops are within a factor of two of it, and the two single biggest
contacts are in the light chain. So the pitch line is "a forced rewrite of a fifth of the paratope is a
real epitope risk", not "we are rewriting the part that does most of the binding".

**Epitope preservation still has to be screened by co-folding, on both tracks.** That conclusion is
unchanged — if anything it gets stronger, because the risk is spread across loops rather than
concentrated in the one we were already watching. Anything touching CDR-H2, or the light chain's two
biggest contacts (A:N30, A:Y92), needs the same screen as CDRH3.

Also: the RECIPES `sampling_temp` of `0.20` is far too conservative to clear the identity window. It
must be raised, and a temperature ladder in one ~110 s job can yield a few hundred candidates.

## 4. Nothing on the platform predicts thermostability. `stab-ddg` is a *binding* ddG.

`stab-ddg`'s only operation is `predict-binding-ddg`, it requires two **disjoint** partner chain sets,
and its own reference says it is "**not a generic folding-stability calculation**".

Of 59 catalog models, grepping for `thermo|stabil|ddg|solub|aggreg|foldx|camsol|rosetta|flex|melt`
matches **exactly one: `stab-ddg`**. No ThermoMPNN, no FoldX, no CamSol, no Flex ddG, no PyRosetta, no
Aggrescan, no SoluProt, no NetSolP. The word "thermostability" appears in no installed skill.

| Track × format | Usable stability signal |
|---|---|
| Optimisation, Fab/scFv | `stab-ddg` repurposed to the **VH–VL interface** (`partner_a:["H"]`, `partner_b:["L"]`) — a real determinant of Tm, still a proxy, blind to intra-domain destabilisation |
| Optimisation, VHH | `esm2-650m score-variants` only. One domain has no second partner, so stab-ddg gives **nothing** |
| De novo, either | `esm2-650m score-sequences` (PLL, parent-free). Report per-residue **mean**, not sum — lengths differ |
| **De novo + VHH** | **no model-based stability signal at all** |

For de novo, every ddG is **undefined, not merely noisy** — there is no parent to subtract. Anyone
reporting a ddG for a de novo design has silently picked a reference, and that choice will drive the
ranking instead of the design.

Do **not** spend a job on `bioemu2` for this: it emits conformations, no ΔG/ΔΔG/Tm, needs an MSA per
chain, and any stability number from 8 samples would be a metric we invented.

**Cheapest real proxy — free, local, works on every candidate and both tracks:**
**framework germline-likeness.** Count mutations falling outside the CDRs and drive it to zero. Antibody
Tm is dominated by the framework and VH–VL pairing, not the loops; CDR-grafting onto a germline
framework is the standard thermostabilisation route. Computed in seconds with the numbering we already
run for abguard.

Note disulfide presence is **useless as a discriminator**: abguard hard-rejects unpaired cysteines, so
every candidate that reaches ranking has already passed it. It is a gate, not a signal.

**Pitch consequence:** axis 3 must be weighted as our weakest-evidence axis, and we should say so.
Judgment is 40% — knowing our thermostability term is a proxy scores better than a confident fake number.

## 5. Reference epitope — computed, cross-checked, committed.

1N8Z. Chains concluded from the structure itself, not assumed: **A = Fab light** (kappa, 214 aa),
**B = Fab heavy** (VH+CH1, 220 aa), **C = HER2** (581 of 607 observed).

**HER2 epitope at 4.5 Å — 19 residues:**

```
P557 E558 D560 Q561 K569 D570 P571 P572 F573 P579 I591 K593 D596 E598 A600 Q602 P603 C604 P605
```

**At 5.0 Å the set is identical — zero additions**, verified by an independent brute-force all-pairs
cross-check. At 4.0 Å only P579 and P605 drop. The epitope is numerically stable across 4.0–5.0 Å,
which makes it a sound reference set for the overlap-scoring axis.

Three loops — **557–573, 579–593, 596–605** — proline-rich, acidic/polar, with K569/K593 the only basic
contacts. Heavy chain dominates 557–593; light chain owns 596–605 exclusively; D560/P571/P572 are the
shared hinge. Buried area 751 Å² on HER2, 706 Å² on the Fab — a small-to-average interface.

**Hotspots by ΔSASA:** E558 93.3 Å² · P571 77.6 · F573 73.7 · P603 71.4 · P572 66.0 · D560 45.1.

**Weakest members — two different criteria, do not mix them** (both from
`1n8z_interface_residues.csv`):

| Criterion | Residues |
|---|---|
| smallest buried ΔSASA | D596 (6.4 Å²), C604 (7.5), P579 (9.7) |
| drops out at a 4.0 Å cutoff | P579 (min dist 4.50 Å), P605 (4.15 Å) |

P579 is the only residue weak on both, so it is the one a design can most safely miss. Earlier
versions of this doc named "P579, D596" without saying which criterion was meant; by ΔSASA the two
smallest are D596 and C604, and P579 is third.

**Paratope at 4.5 Å (20 residues)** — the canonical trastuzumab CDR set:
light D28 N30 T31 A32 S50 F53 H91 Y92 T93 T94 · heavy Y33 R50 Y52 Y57 T58 R59 W99 G103 F104 Y105.

### Two traps in this data

1. **Numbering offset.** `DBREF`: chain C residue *n* = UniProt P04626 residue *n+22*. The epitope
   557–605 in PDB numbering is **579–627 in UniProt numbering**. Generation specs and the overlap
   scorer must state which convention they use, or the reference set silently shifts by 22.
2. **C604 is in the epitope** and is the only chain-C cysteine with no `SSBOND` record — its partner
   lies past the construct end at 607. Do not read it as a free thiol in the real receptor.

Also: 1N8Z chain C is residues 1–607, a large part of the ECD, not domain IV alone. The epitope does
fall within the domain-IV stretch, but the coordinates contain much more.

Artifacts: [`data/reference/epitope/`](../data/reference/epitope/) — residue-level CSV (40 rows, both
cutoffs via a `within_4.5A` flag, with ΔSASA), machine-readable JSON report, and the method statement.
