================================================================================
DATASET: AlphaFold3 Confidence Scores – "Champloo" Benchmarking Study
================================================================================

ASSOCIATED PUBLICATION
----------------------
Title:   Structural Plausibility Without Binding Specificity: Limits of
         AI-Based Antibody-Antigen Structure Prediction Confidence Scores

Authors: Eva Smorodina, Montader Ali, Klara Kropivšek Brumat,
         Leonardo Salicari, Samo Miklavc, Aibek Kappassov,
         Chengcheng Fu, Pietro Sormanni, Ario de Marco, Victor Greiff

DOI:     https://doi.org/10.64898/2026.03.02.709004
bioRxiv: https://www.biorxiv.org/content/10.64898/2026.03.02.709004v1


DATASET CONTENTS
----------------
This dataset contains raw AlphaFold3 confidence output files (confidences.json)
for all VHH-antigen predictions performed in the Champloo benchmarking study.
Files are split into two archives:

  af3_real_per_replica_confidence_metrics.tar.zst      (~1.3 GB compressed)
    -> Real VHH-antigen binding pairs (123 systems, experimentally validated)

  af3_shuffled_per_replica_confidence_metrics.tar.zst  (~152 GB compressed)
    -> Shuffled (non-binding) VHH-antigen pairs
       Note: the folder inside this archive is named "dreamy/" which is the
       internal Champloo study term for shuffled non-binding pairs.


ARCHIVE STRUCTURE
-----------------
Both archives follow the same internal structure:

  confidences/
    real/          (in af3_real archive)
    dreamy/        (in af3_shuffled archive; "dreamy" = shuffled non-binding pairs)
      system_{A}_{B}_{pdb1}_{pdb2}/
        seed-1_sample-0.json
        seed-1_sample-1.json
        ...
        seed-1_sample-49.json


SYSTEM NAMING CONVENTION
------------------------
  system_{VHH_index}_{antigen_index}_{VHH_PDB}_{antigen_PDB}

  Example: system_53_13_7xtp_5mje
    VHH index:     53
    Antigen index: 13
    VHH PDB:       7XTP
    Antigen PDB:   5MJE


CONFIDENCE FILE FORMAT
----------------------
Each seed-1_sample-N.json is a raw AlphaFold3 confidences.json output containing:

  - iptm          : interface predicted TM-score (main confidence metric)
  - ptm           : predicted TM-score (global fold confidence)
  - ranking_score : composite score (0.8 * iptm + 0.2 * ptm)
  - plddt         : per-residue local distance difference test scores
  - pae           : Predicted Aligned Error (PAE) matrix
                    (used for ipSAE computation in the paper)


PREDICTION SCOPE
----------------
  Model:             AlphaFold3 (AF3)
  Diffusion samples: 50 per system (fixed seed=1)
  Dataset:           123-system VHH-nanobody-antigen benchmark
                     (curated from SAbDab-nano)
  Pair types:        Real binding pairs + shuffled non-binding pairs


HOW TO DECOMPRESS
-----------------
Requires zstd (https://github.com/facebook/zstd) and tar.

  # Extract
  tar --use-compress-program=unzstd -xf af3_real_per_replica_confidence_metrics.tar.zst
  tar --use-compress-program=unzstd -xf af3_shuffled_per_replica_confidence_metrics.tar.zst

  # List contents without extracting
  tar --use-compress-program=unzstd -tf af3_real_per_replica_confidence_metrics.tar.zst | head -20


COMPUTE INFRASTRUCTURE
----------------------
Predictions were generated on the Leonardo Booster cluster at CINECA, Italy,
funded via the EuroHPC/EPICURE grant (project EUHPC_D27_047). Computational support through Leonardo Salicari.
Fellowship funding: MSCA SMASH Postdoctoral Fellowship (Klara Kropivšek Brumat).


LICENSE & REQUIRED CITATIONS
-----------------------------
AlphaFold3 output files are distributed under the AlphaFold 3 Output Terms
of Use (non-commercial research use only):
https://github.com/google-deepmind/alphafold3/blob/main/OUTPUT_TERMS_OF_USE.md

If you use this dataset, please cite BOTH of the following:

  1. This dataset and associated study:
     Smorodina E, Ali M, Kropivšek Brumat K, Salicari L, Miklavc S,
     Kappassov A, Fu C, Sormanni P, de Marco A, Greiff V.
     Structural Plausibility Without Binding Specificity: Limits of
     AI-Based Antibody-Antigen Structure Prediction Confidence Scores.
     bioRxiv (2026). https://doi.org/10.64898/2026.03.02.709004

  2. AlphaFold3:
     Abramson J et al. Accurate structure prediction of biomolecular
     interactions with AlphaFold 3. Nature (2024).
     https://doi.org/10.1038/s41586-024-07487-w


CONTACT info about the AF3 predictions
-------
Klara Kropivšek Brumat  – klara.kropivsek[at]ung.si/klara.kropivsek[at]gmail.com; University of Nova Gorica (SMASH Postdoctoral Fellow)

================================================================================
