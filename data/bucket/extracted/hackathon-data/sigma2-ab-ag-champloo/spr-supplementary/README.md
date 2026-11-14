# SPR measurements extracted from Champloo Supplementary File 1

Source: Supplementary File 1 for Smorodina E, Ali M, Kropivšek Brumat K, Salicari L,
Miklavc S, Kappassov A, Fu C, Sormanni P, de Marco A, Greiff V. "Structural Plausibility
Without Binding Specificity: Limits of AI-Based Antibody-Antigen Structure Prediction
Confidence Scores." bioRxiv (2026), doi 10.64898/2026.03.02.709004.

Extracted 2026-11-13 from the supplementary PDF, section "Experimental affinity values of
selected cognate and non-cognate VHH-antigen pairs" (pages 1-4) and Methods "Selection of
VHH-antigen pairs for experimental KD measurements" (pages 49-50).

These data are NOT in the sibling archives in `../` (af3/boltz2/chai1 confidence metrics),
nor on the Zenodo record 10.5281/zenodo.18390239, nor in the GitHub repo
csi-greifflab/ab_ag_champloo. They exist only in the supplementary PDF text.

## Files

- `spr_table_s1_pairwise.csv` — Supplementary Table S1. 29 rows: the 28 pairs selected for
  experimental verification plus one pair (8w90_a vs CD8α) added by the provider.
- `spr_crossreactivity_14target.csv` — the 14-target cross-reactivity screen (page 4). Only
  the responses the text quantifies are recorded; the screen's full matrix is not in the PDF.

## Two separate experiments, two providers

The PDF states the pair selection applies "exclusively to the GenScript dataset (main text,
Supplementary Figure 3B)" and that "the Adaptyv results were selected independently and are
therefore not intended to represent a systematic or directly comparable selection." Table S1
and the 14-target screen are therefore not one dataset.

## Counts

Of the 29 rows in Table S1:
- 17 reported (5 cognate, 12 non-cognate)
- 7 ordered but did not express ("not reported")
- 5 cancelled when the CDK7 antigen was never produced

Of the 5 cognate pairs, 4 returned a fitted KD: 0.401 nM (CD8α), 4.03 nM (CNPase),
7.41 nM (CD4), 767 nM steady-state (C3b). The fifth (leptin receptor) gave a
concentration-dependent response with no fitted affinity.

None of the 12 non-cognate pairs returned a reportable affinity.

## Caveats stated by the authors

- "N/A denotes no reportable affinity fit, NOT confirmed non-binding." The N/A rows must not
  be relabelled as measured true negatives.
- "These comparisons are descriptive. Four quantified pairs is a small number, and no fitted
  affinity is not confirmed non-binding."
- 8fsl_c expressed very poorly and was flagged for discard, so its N/A may reflect material
  quality rather than absence of binding.
- In the 14-target screen, loading was low across almost the entire chip; only one surface
  (8k4q_d on IL-4Rα) confirmed a binder outright.

## AF3 ipTM

The PDF reports AF3 ipTM 0.75-0.90 for eleven of the twelve non-cognate pairs but does not
tabulate per-pair values; they appear only as printed cells in Supplementary Figure S1B.
The `af3_iptm` column therefore holds only the three cognate values stated in the text
(CD4 0.12, leptin receptor 0.15, CNPase 0.46). Per-pair non-cognate values would have to be
recomputed from the confidence archives in `../` or read off Figure S1B.
