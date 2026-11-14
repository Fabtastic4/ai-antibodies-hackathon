# Pre-read: what the organizers expect us to already know

Distilled from the participant field guide
(https://oslo-ai-antibodies-hackathon.vercel.app/participant_guide). Not the task.

## The molecule

A **VHH / nanobody** is the binding domain of a camelid heavy-chain-only antibody used on its
own: ~120 amino acids, ~15 kDa, **three** CDR loops instead of six, no light chain. That is why
the hackathon centres on it — one gene, one domain, easy to model and cheap to make.

- **CDR3** is the longest and most variable loop and usually does most of the binding. It is also
  where structure prediction is weakest.
- **Framework** is the conserved scaffold. The framework-2 **hallmark residues** keep a VHH
  soluble without a light chain — reverting them towards a conventional VH is a known way to
  ruin a design.
- **Epitope** = the patch on the target that gets touched. **Paratope** = the patch doing the
  touching. Affinity = **KD**; lower is tighter. nM is good, pM is tight, above 1 µM is too weak.
- ΔG = RT·ln KD. One decade of KD ≈ 1.36 kcal/mol; a 1 nM binder sits near −12 kcal/mol. A
  claimed 5 kcal/mol gain from one point mutation is three orders of magnitude in KD — rare, and
  usually the model reporting its own failure. Most single mutations land between −1 and +2.

## What the models can and cannot do

| Task | State of the art |
|---|---|
| Fold a single VHH | Largely solved for the framework; CDR3 is the weak spot |
| Predict a VHH–antigen complex | Improving fast, poor on novel epitopes, confidence overstates |
| Predict developability | Scattered rules plus a few models; often failed |
| Rank mutations by affinity | Weak — Pearson ~0.3–0.5; rank order beats absolute values |
| Decide what to test next | Active learning and uncertainty are underused — **our opening** |

Model score meanings: **pLDDT** 0–100 local-structure confidence, higher better. **PAE** predicted
positional error in Å, lower better. **ipTM** 0–1 confidence in chain placement in a complex.
**ipSAE** 0–1 interface-focused score from PAE. **None of these is a KD.**

## Model families worth reaching for

- Structure / co-folding: AlphaFold2-3, OpenFold, NanoBodyBuilder2, ABodyBuilder3, Boltz-2, Chai-1, ESMFold-2
- De novo / conditional generation: RFD4-Proteina, RFdiffusion3, RFantibody, IgDiff, PXDesign, BoltzGen
- Inverse folding: ProteinMPNN, ESM-IF1, AntiFold
- Affinity regression: AF-IG2, OpenDDE, or our own regressor on a matched dataset
- Embeddings: ESMC, SaProt, ESM-2, nanoBERT, IgBERT — one-hot is a fair baseline
- Developability: TNP (VHH), TAP (conventional), ThermoMPNN, Aggrescan 3D, SoluProt, NetSolP

## Developability — the cheap win

We never measure it, but it shapes selection:

1. Rank beyond the binding score — between two equal binders, take the one with fewer flags.
2. Fix what the sequence shows: liability motifs (**NG** deamidation, **DG** isomerization,
   **DP** acid-labile, **N-x-S/T** glycosylation, **M/W** oxidation), odd cysteine counts,
   hydrophobic or charged stretches. Then **re-score binding** — a fix that breaks the interface
   is not a fix.
3. Make the selection defensible, in the pitch.

Motifs matter mainly in or near a CDR and when solvent-exposed. A bare VHH is kidney-filtered in
hours, so half-life extension (Fc or albumin binder) is a product decision, not a binding one.
Tighter is not automatically better: in solid tumours a very tight binder can get stuck at the
first target it meets.

## Traps the guide calls out explicitly

- **Numbering**: IMGT / Kabat / Chothia positions are **not** PDB residue numbers. Run ANARCI /
  ANARCII and map onto chain residue identifiers. This is the silent bug.
- **Confidence is not affinity.**
- **One lucky seed**: report spread across seeds, and run at least one case we did not tune on —
  which is also exactly what the judge will do to us.
- **Disagreement is information**: where dissimilar predictors disagree, call it uncertainty
  rather than averaging it away.
- **Breaking bonds**: changes at cysteines or conserved framework positions can score well and
  still destroy the fold.

## Data sources

SAbDab / SAbDab-nano (structures) · Observed Antibody Space (sequences) · SKEMPI 2.0 (ΔΔG) ·
AB-Bind (antibody mutational binding) · Adaptyv Bio competition data (prospective wet-lab) ·
Ginkgo Datapoints (developability, incl. VHH sets) · PDB/RCSB · UniProt

## Tutorial worth having done

PDB **1ZVY** — a VHH (chain A) bound to hen egg-white lysozyme (chain B). In JapanFold →
Drug Design → RFD4-Proteina, contigs:

- new binder to the target: `B1-129, /0, 110-130`
- redesign a VHH loop: `B1-129, /0, A2-96, 20, A117-125`

Residue A1 is unresolved in that structure — verify numbering against the file before copying.
A backbone-only generator needs a sequence-design step afterwards.
