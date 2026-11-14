# Pre-read: what the organizers expect us to already know

Distilled from the **participant field guide**
(https://oslo-ai-antibodies-hackathon.vercel.app/participant_guide), printable view.

**What that source is.** The guide is a real organiser document, written as pre-event preparation and
published *before* today. Its own last line: "This is a preparation guide, not the task: the task is
released at 09:30 on the day." So:

- Every figure below is cited **(participant guide)** when the guide states it, **(event website)**
  when the front page states it, or marked **TODO: confirm** when neither does. Anything marked TODO
  does not go in the pitch as a number.
- **Where the guide and the task PDF disagree, the task PDF wins** and we say so out loud. Known
  disagreements, all resolved in favour of the task PDF:

  | Thing | Participant guide | Task PDF (wins) |
  |---|---|---|
  | How many designs we submit | "Select up to 10 to validate" | ranked list of **up to 20** (16 + 4 spare), p7–8 |
  | How many get tested | "We can probably test five designs per team" | **4 per team** whatever happens, +12 for 1st, p7 |
  | Scoring weights | 40/20/20/20, flagged "provisional and will be confirmed" | 40/20/20/20 confirmed, p7 (and event website FAQ) |
  | Affinity-regression model name | "AF-IG2" | **AF2-IG**, p6 |

- The guide is about VHHs because they are the easy case. Our submission may be **VHH, scFv or Fab**
  (task PDF p3; the guide's own funnel says the same).

## The molecule

A **VHH / nanobody** is the binding domain of a camelid heavy-chain-only antibody used on its own:
**~120 amino acids, ~15 kDa, three** CDR loops instead of six, no light chain, roughly a tenth of an
IgG (~150 kDa) (participant guide). One gene, one domain — "the sequence you design is literally what
a lab would order", cheaper to make and easier to model than a paired format (participant guide).

- **CDR3** (heavy chain) is usually the longest and most variable loop and often plays the most
  important role — but CDR1, CDR2 and nearby framework residues can also touch the antigen
  (participant guide). It is also where structure prediction is weakest (participant guide, ch. 4).
- **Framework** is the conserved scaffold. The framework-2 **hallmark residues** are replaced by more
  water-friendly residues in a VHH so the domain stays soluble without a light chain; reverting them
  towards a conventional VH is called out as risky (participant guide).
- **Epitope** = the patch on the antigen that gets touched. **Paratope** = the patch doing the
  touching. Epitope residues can be far apart in sequence and close in 3D (participant guide).
- Affinity = **KD**, lower is tighter. The guide's own targets: **1 nM is good, 100 pM tight, above
  1 µM usually too weak** (participant guide, developability reference table).
- ΔG_bind = RT·ln(KD / 1 M). **One decade of KD = 1.36 kcal/mol** and **a 1 nM binder sits near
  −12 kcal/mol** (participant guide, KD ⇄ ΔG calculator; RT ≈ 0.592 kcal/mol at 298 K). A claimed
  **5 kcal/mol** gain from one point mutation is **more than three orders of magnitude** in KD — it
  happens, rarely, and is usually the model reporting its own failure. **Most single mutations land
  roughly between −1 and +2 kcal/mol** (participant guide).
- Noise floor: assay repeats often differ by a few tenths of a kcal/mol, already a factor of 1.5–2 in
  KD (participant guide). A 1.4 kcal/mol error is a tenfold error in KD.
- Stability is read out as **Tm**; the guide's typical target is **above ~65 °C** (participant guide,
  developability reference table). We have no platform model for it — see
  [probe-findings.md §4](probe-findings.md).

## What the models can and cannot do

The guide's own maturity read (participant guide, ch. 4 — "an editorial read of the field, not a
benchmark"):

| Task | State of the art |
|---|---|
| Fold a single VHH | Largely solved for the framework; CDR3 is the weak spot |
| Predict a VHH–antigen complex | Improving quickly, poor on novel epitopes, confidence overstates |
| Predict developability | Scattered rules plus a few models; this hurdle is often failed |
| Rank mutations by affinity | Weak — **classical scoring functions land around Pearson 0.3–0.5** on antibody ΔΔG benchmarks such as AB-Bind; rank order beats absolute values |
| Decide what to test next | Active learning and uncertainty are not used often enough — **our opening** |

Pearson 0.3–0.5 is the guide's figure for **classical / empirical** scoring functions (FoldX, Rosetta
family) on AB-Bind, which is built mainly on conventional antibodies; matching VHH data is scarcer
(participant guide, physics page). Do not quote it as the accuracy of a learned model.

Model score meanings (participant guide): **pLDDT** 0–100 local-structure confidence, higher better.
**PAE** predicted error in relative residue positioning, in Å, lower better. **ipTM** 0–1 confidence
in chain placement in a complex, higher better. **ipSAE** 0–1 interface-focused score derived from
PAE, "implementations vary". **None of these is a KD.**

## Model families worth reaching for

The guide's lists, verbatim in content (participant guide, "Where can machine learning help?"):

- Structure / co-folding: AlphaFold2/3, OpenFold, NanoBodyBuilder2, ABodyBuilder3, Boltz-2, Chai-1,
  ESMFold-2
- De novo / conditional generation: RFD4-Proteina, RFdiffusion3, RFantibody, IgDiff, PXDesign, BoltzGen
- Inverse folding: ProteinMPNN, ESM-IF1, AntiFold
- Affinity regression: **AF2-IG**, OpenDDE, related affinity models — or our own regressor on a matched
  dataset. (The guide prints "AF-IG2"; the task PDF p6 writes **AF2-IG** and wins. Search for AF2-IG.)
- Embeddings: ESMC, SaProt, ESM-2, nanoBERT, IgBERT — one-hot is a fair baseline
- Developability: stability → ThermoMPNN, ESM-IF; solubility/aggregation → Aggrescan 3D, SoluProt,
  NetSolP, ProteinMPNN with soluble weights; chemical liabilities → TNP (VHH), TAP (conventional)

What is actually reachable today is a different question — [tools-nebius.md](tools-nebius.md) and
[probe-findings.md](probe-findings.md) are authoritative on that, not this list.

## Developability — the cheap win

We never measure it, but it shapes selection (participant guide, "What is developability?"):

1. Rank beyond the binding score — between two equal binders, take the one with fewer flags. This is
   the step where most designs get cut.
2. Fix what the sequence shows: liability motifs, odd cysteine counts, hydrophobic or charged
   stretches. Then **re-score binding** — a fix that breaks the interface is not a fix.
3. Make the selection defensible, in the pitch.

Liability motifs the guide names: **NG** deamidation, **DG** isomerization, **N-x-S/T** unwanted
glycosylation, **DP** acid-labile (participant guide, glossary). *M/W oxidation is **not** in the
guide's motif list — it is standard antibody-engineering practice but has no source above.*
**TODO: confirm** before any pitch slide claims an oxidation flag; cheapest route is to run TNP and
quote whatever it flags.

Which motifs matter depends on whether they sit **in a CDR or an exposed position**, and on pH, buffer
and storage — more formulation than biology (participant guide).

A bare VHH (~15 kDa) is filtered by the kidneys **within hours**, so half-life extension (fusing an Fc
or an albumin binder) is a product decision, not a binding one (participant guide). Tighter is not
automatically better: in solid tumors a very tight binder can get stuck at the first target it meets at
the edge of a blood vessel and never reach the tissue behind it; for T-cell engagers, too tight can
trigger dangerous cytokine release (participant guide, medicine page).

## Traps the guide calls out explicitly

- **Numbering**: IMGT / Kabat / Chothia positions are **not** PDB residue numbers. Run ANARCI /
  ANARCII and map onto chain residue identifiers. Plain counting does not work because VHH CDR3 length
  varies (participant guide). This is the silent bug.
- **Confidence is not affinity.** pLDDT, ipTM and PAE say how sure the model is about the geometry
  (participant guide).
- **One lucky seed**: report the spread across random seeds and run at least one case we did not tune
  on (participant guide). That is also exactly what the judges do to us — "a judge runs your skill on
  a case your team hasn't seen" (event website, FAQ).
- **Disagreement is information**: where dissimilar predictors disagree, treat it as uncertainty
  rather than averaging it away (participant guide).
- **Breaking bonds**: changes at cysteines or conserved framework positions can score well and still
  ruin the fold (participant guide).
- **A "perfect" list is not the goal**: the guide says a rough list of reasons plus a "how sure" per
  design is worth more than endless numbers (participant guide). That is the 40% Judgment.

## Data sources

The guide's list, with what each is (participant guide): SAbDab / SAbDab-nano (curated antibody and
VHH structures) · Observed Antibody Space (repertoire sequences) · SKEMPI 2.0 (experimental binding
free-energy changes on mutation) · AB-Bind (antibody-specific mutational binding data) · Adaptyv Bio
competition data (prospective wet-lab results on designed binders) · Ginkgo Datapoints (developability
sets, including VHH) · PDB/RCSB · UniProt

## Warm-up tutorial — and why it is NOT our route

This is the guide's **pre-event practice exercise**, on a lysozyme nanobody, written before the task
PDF existed. Do it to learn what a contig is. **Do not follow it for our HER2 designs.**

The exercise (participant guide, "How can I design a VHH in JapanFold?"): PDB **1ZVY** — a VHH
(chain A) bound to hen egg-white lysozyme (chain B). Open JapanFold, choose "Drug Design", then
RFD4-Proteina, paste the mmCIF, and set the **contig** field:

| Option | Contig | What it means (guide's words) |
|---|---|---|
| A — new binder to the target | `B1-129, /0, 110-130` | `B1-129` is the target segment, `/0` separates chains, `110-130` asks for a new segment of 110–130 residues. **The resulting binder is not necessarily a VHH.** |
| B — redesign a VHH loop | `B1-129, /0, A2-96, 20, A117-125` | Retains target chain B, preserves VHH segments A2–96 and A117–125, requests a new 20-residue segment between them. |

Residue A1 of chain A is unresolved in 1ZVY, which is why option B starts at A2 — verify numbering
against the downloaded file before copying either string (participant guide). A backbone-only
generator may need a sequence-design step afterwards (participant guide).

**For our task the route is Apheris Foundry on the team VM, not JapanFold.** The task PDF puts
RFD4-Proteina in Foundry as Docker images on the VM (p5–6) and names JapanFold as complementing the
toolbox with RoseTTAFold3, OpenDDE and AF2-IG (p6) — it does not list RFD4-Proteina as a JapanFold
model. And the checkpoints we actually want (`antibody-2026-10-30`, `her2-2026-11-07`,
`her2-novel-2026-11-09`) exist **only** as Foundry Docker images on the VM; Nebius's hosted
`rfd4-proteina` is the general checkpoint and produces a general mini-binder, which is not VHH, scFv or
Fab and fails the format gate. See [probe-findings.md §2](probe-findings.md).
