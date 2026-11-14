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
| `chai1` | batch ~4 min | absent | absent | absent | absent |
| `alphafold3` | batch | not delivered | file-level only | — | — |
| `openfold3-openbind` | batch | absent | absent | absent | absent |
| `protenix-v2` | batch ~20 min | absent | absent | absent | absent |

The gateway contract states boltz2 "does not expose ... **full-PAE** features", and RECIPES says
outright "The output has **no ipTM**, so do not report one." Five of six models publish no output
schema at all, so for those, "which fields come back" is unanswerable until a run returns — that
absence is itself the finding.

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

Keeping the framework does preserve most of the molecule — but the eligibility rules force a **≥4-residue
rewrite of CDRH3**, and CDRH3 carries most of trastuzumab's HER2 contact (heavy chain dominates epitope
residues 557–593). Rewriting it is exactly the change most likely to move the epitope. **Epitope
preservation still has to be screened for by co-folding**, on both tracks.

Also: the RECIPES `sampling_temp` of `0.20` is far too conservative to clear the identity window. It
must be raised, and a temperature ladder in one ~110 s job can yield a few hundred candidates.

Still open: how abguard computes CDRH3 identity. Our ≥4-mutation filter assumes it is over the loop
alone. If abguard uses a wider window the threshold moves. Cheap to ask on site, expensive to get wrong.

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
Weakest members, which a design can miss without real epitope drift: P579 (9.7 Å²), D596 (6.4 Å²).

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
