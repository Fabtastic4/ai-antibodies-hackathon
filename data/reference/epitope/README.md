# Reference epitope: trastuzumab Fab / HER2 from PDB 1N8Z

Produced 14 Nov 2026, team-4. Pure local computation, no platform job.

## Source
- `1n8z.pdb` (703,809 bytes) and `1n8z.cif` (845,613 bytes), downloaded HTTP 200 from
  `https://files.rcsb.org/download/1N8Z.pdb` / `.cif`.
- HEADER `TRANSFERASE 21-NOV-02 1N8Z`; `EXPDTA X-RAY DIFFRACTION`; `REMARK 2 RESOLUTION. 2.52 ANGSTROMS.`
- Single model (no `MODEL` records), no hydrogens in the file (element column: C/N/O/S only),
  no altloc indicators (all 7778 ATOM records have a blank altloc column).

## Method
- Parser: Biopython 1.88 (`Bio.PDB.PDBParser(QUIET=True)`), installed in a local venv at
  `/private/tmp/claude-501/-Users-josef-Developer-Fab4/1a5e8913-7572-4a34-bed2-fe001b07f4e7/scratchpad/venv`. System python untouched.
- Script: `/private/tmp/claude-501/-Users-josef-Developer-Fab4/1a5e8913-7572-4a34-bed2-fe001b07f4e7/scratchpad/scripts/epitope.py`
  (independent brute-force cross-check: `.../scripts/check_cutoffs.py`).
- **Atom set: heavy atoms only, standard amino-acid residues only.** All HETATM groups are excluded:
  79 HOH (19 on A, 13 on B, 47 on C), 2 NAG on chain C, 1 SO4 on chain C. The two NAG glycans
  (MODRES: ASN C 165, ASN C 237 glycosylation sites) are therefore not part of the interface
  calculation; neither site is anywhere near the epitope.
- **Contact definition: a HER2 (chain C) residue is in the epitope if any of its heavy atoms is
  within the cutoff of any heavy atom of chain A or chain B.** Distances are plain Euclidean
  atom-atom distances. Cutoffs reported: 4.5 A (headline) and 5.0 A (sensitivity).
- Paratope: the mirror of the same calculation, Fab residues within the cutoff of chain C.
- Burial: `Bio.PDB.SASA.ShrakeRupley` at library defaults (`probe_radius=1.40`, `n_points=100`).
  `dSASA = SASA(unbound reference) - SASA(ABC complex)`, per residue, same heavy-atom/no-water set.
  Unbound reference for HER2 = chain C alone. Unbound reference for Fab = chains A+B together, so
  the heavy-light interface is not miscounted as antigen burial. No extra dependencies were needed;
  this step is fully computed, not approximated.

## Chain inventory (identities concluded from the structure, see evidence)
| Chain | Role concluded | Observed aa | SEQRES | Author numbering | Unresolved |
|---|---|---|---|---|---|
| A | trastuzumab Fab **light** chain (kappa) | 214 | 214 | 1-214 | 0 |
| B | trastuzumab Fab **heavy** chain (VH + IgG1 CH1) | 220 | 220 | 1-220 | 0 |
| C | **HER2 / ERBB2 extracellular region** (antigen) | 581 | 607 | 1-607 | 26 |

Evidence used (all read off the coordinates/sequence, not assumed):
- Chain A carries the kappa constant domain, `RTVAAPSVFIFPPS` at observed position 108 and
  `SFNRGEC` at 208, plus kappa framework-2 `WYQQKP` at 35 and the trastuzumab CDR-L3 `QQHYTTPPT`
  at 89 -> light chain.
- Chain B carries the IgG1 CH1 start `ASTKGPSVFPLAP` at 121, heavy framework-2 `WVRQAP` at 36,
  the trastuzumab CDR-H2 core `RIYPTNGYTR` at 50 and CDR-H3 `WGGDGFYAMDY` at 99 -> heavy chain.
- Chain C contains none of those motifs, is 581 observed residues with 25 intrachain disulfides,
  and is the only chain both A and B touch -> antigen.
- Interchain heavy-atom contacts at 4.5 A: A-B 516 atom pairs / 95 residue pairs (the Fab's own
  H-L pairing, by far the largest), A-C 105 / 19, B-C 116 / 23. So A and B are a pair and C is the
  partner of both, consistent with one Fab bound to one antigen.
- Header agrees independently (`COMPND`: Herceptin Fab light chain = A, heavy chain = B,
  receptor protein-tyrosine kinase ERBB-2 extracellular domain = C), but the assignment above does
  not depend on it.

Unresolved chain C residues (from `REMARK 465`, 26 residues, 607 SEQRES - 581 observed = 26, consistent):
102-110 (NNTTPVTGA), 303-305 (EDG), 361-364 (GDPA), 581-590 (GVKPDLSYMP).
Chains A and B have no unresolved residues. No insertion codes anywhere.

## Numbering, stated explicitly
`DBREF  1N8Z C    1   607  UNP  P04626  ERBB2_HUMAN  23  629` — chain C residue *n* is
UniProt P04626 residue *n+22*. All HER2 numbers below are **PDB/mature-protein numbering
(signal peptide removed)**. Add 22 for UniProt/precursor numbering. The epitope 557-605 here is
UniProt 579-627. Any downstream epitope-overlap scoring must agree on which of the two it uses.

## Result: HER2 epitope at 4.5 A (19 residues, headline)
`P557 E558 D560 Q561 K569 D570 P571 P572 F573 P579 I591 K593 D596 E598 A600 Q602 P603 C604 P605`

At 5.0 A the set is **identical** — no additions. Verified twice (NeighborSearch and a brute-force
all-pairs distance matrix). The next-nearest HER2 residues are Y532 (5.31 A), V575 (5.35 A) and
C601 (5.12 A), which enter only at 5.5 A; at 4.0 A the set loses only P579 and P605 (17 residues).
The epitope is therefore numerically stable across 4.0-5.0 A, which is good news for the
overlap-scoring axis.

## Files
- `1n8z.pdb`, `1n8z.cif` — downloaded structure.
- `1n8z_interface_residues.csv` — residue-level table, both sides of the interface. Columns:
  `side` (epitope|paratope), `chain`, `resnum`, `icode`, `resname`, `one_letter`, `min_distance`,
  `within_4.5A` (yes|no), `contacting_chain` (`chain:min_dist`, semicolon-separated),
  `dsasa_A2`, `sasa_unbound_A2`, `sasa_complex_A2`. Rows are the 5.0 A sets, with the
  `within_4.5A` flag marking the 4.5 A subset, so one file serves both cutoffs.
- `1n8z_epitope_report.json` — full machine-readable report: chain inventory with sequences,
  motif evidence, interchain contact counts, epitope and paratope at both cutoffs, dSASA rankings,
  SASA method block.
- `README.md` — this file.

## Caveats to carry forward
- HER2 **C604 is in the epitope and is the only chain-C cysteine with no `SSBOND` record**; its
  partner would lie past the construct end (607). Harmless for scoring, but do not read it as a
  free thiol in the real receptor.
- 1N8Z chain C spans residues 1-607, i.e. a large part of the ECD, not domain IV alone. The
  computed epitope falls entirely in the C-terminal 557-605 stretch (domain IV), consistent with
  the usual description, but the coordinates themselves contain much more than domain IV.
- The epitope is one continuous-ish surface made of three loops: 557-573, 579-593, 596-605.
  It is heavily proline-rich (P557, P571, P572, P579, P603, P605) and acidic/polar
  (E558, D560, Q561, D570, D596, E598, Q602), with K569/K593 the only basic contacts.
- Burial is modest: 751 A2 buried on HER2, 706 A2 on the Fab (sum of per-residue dSASA).
  That is a small-to-average antibody interface, so epitope-overlap scoring should expect few
  contacts per design and weight loop 557-573 / 596-605 most.
