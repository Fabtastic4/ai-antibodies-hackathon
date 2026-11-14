#!/usr/bin/env python3
"""Stage 04b - the thermostability axis.

Thermostability is one of the three properties Adaptyv measures (task PDF p7),
and it was the one term the pipeline had no implementation of. GitHub issue #10.

READ docs/probe-findings.md §4 BEFORE CHANGING ANYTHING HERE. Everything below
is built on it, and it contradicts the obvious reading of the platform catalog:

  * Nothing on Nebius predicts thermostability. Of 59 catalog models, grepping
    `thermo|stabil|ddg|solub|aggreg|foldx|camsol|rosetta|flex|melt` matches
    exactly one model, `stab-ddg`.
  * `stab-ddg` is a *BINDING* ddG. Its only operation is `predict-binding-ddg`,
    it requires two DISJOINT partner chain sets, and its own reference says it
    is "not a generic folding-stability calculation". Nothing in this file may
    label its output a folding ddG or a Tm. It is reported as, and only as, a
    VH-VL interface ddG - a real determinant of antibody Tm, still a proxy, and
    blind to intra-domain destabilisation.
  * For a de novo design every ddG is UNDEFINED, not merely noisy: there is no
    parent to subtract. A ddG reported for a de novo design means someone
    silently picked a reference, and that choice then drives the ranking
    instead of the design. This file returns null with that reason instead.
  * Do NOT spend a job on `bioemu2`. It emits conformations, no dG/ddG/Tm, and
    needs an MSA per chain; a stability number off 8 samples is a metric we
    invented.
  * Disulfide presence is NOT a signal here. abguard hard-rejects unpaired
    cysteines, so every candidate that reaches ranking has already passed it.
    It is a gate, and stage 05 already applies it.
  * Solubility is NOT scored by the organisers. It stays an expression sanity
    screen in 04_score.py and is deliberately absent from this axis.

Per track and format, from §4 as amended by issue #10's third comment (the
Apheris slides require optimisation designs to be the same format as
trastuzumab, i.e. Fab or scFv, so the optimisation+VHH cell is now unreachable -
it is still handled here rather than assumed away):

  | track        | format   | signals                                          |
  |--------------|----------|--------------------------------------------------|
  | optimisation | Fab/scFv | VH-VL interface ddG (stab-ddg) + esm2 variants +
  |              |          | framework germline-likeness                      |
  | optimisation | VHH      | esm2 variants + germline-likeness. stab-ddg gives
  |              |          | NOTHING: one domain has no second partner set.   |
  | de novo      | any      | esm2 PLL (per-residue MEAN) + germline-likeness.
  |              |          | every ddG is undefined.                          |

What this file computes itself, offline, for free, on every candidate:
FRAMEWORK GERMLINE-LIKENESS - the count of substitutions falling OUTSIDE the
CDRs. Antibody Tm is dominated by the framework and by VH-VL pairing, not by the
loops, and CDR-grafting onto a germline framework is the standard
thermostabilisation route, so "how far has the framework drifted" is the
cheapest real proxy available and the only one here with an unambiguous
direction. Drive it to zero.

What this file does NOT do: call the network. Both model interfaces are
unverified in our sources, so `--emit-requests` writes the payloads for a human
to check against `forge.py schema stab-ddg` / `forge.py schema esm2-650m`, and
numbers come back in through `--stab-ddg-scores` / `--esm2-scores`, exactly as
04_score.py takes `--refold-scores`. Dispatching raises ConfirmOnVM.

Two statistical traps this file is written to block:

 1. A single "stability score" would be a number we invented: the terms are
    heterogeneous (a count, a ddG in kcal/mol, a log-likelihood) and three of
    them have no agreed sign convention in our sources. So no composite is
    emitted. Each term is attached separately and stage 05 weights whichever
    the team chooses, which keeps the choice visible in the output.
 2. ESM-2 and ESMC are the same KIND of model. Their agreement is not
    corroboration, and `corroboration_note()` records that instead of letting a
    second number read as a second opinion.

Usage:
  # offline, every candidate, no platform cost:
  python3 thermostability.py runs/scored.jsonl -o runs/stability.jsonl

  # write the request payloads to check against the real schemas:
  python3 thermostability.py runs/scored.jsonl -o runs/stability.jsonl \\
      --emit-requests runs/stability-requests/

  # fold externally-produced numbers back in:
  python3 thermostability.py runs/scored.jsonl -o runs/stability.jsonl \\
      --stab-ddg-scores results/stab_ddg.json --esm2-scores results/esm2.json
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

STAGE = "04b_thermostability"

# --------------------------------------------------------------------------
# the parent: trastuzumab, from the committed 1N8Z report
# --------------------------------------------------------------------------
# pipeline/README.md and common.load_reference_set() both say this repo ships no
# trastuzumab sequence. That is now out of date: the RCSB-derived Fab sequences
# are committed in data/reference/epitope/1n8z_epitope_report.json, chain B
# (heavy, 220 aa, VH+CH1) and chain A (light, 214 aa, VL+CL), with motif
# evidence giving their domain boundaries. This module reads them from there
# rather than carrying a copy, so there is exactly one source in the repo.

EPITOPE_REPORT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "reference", "epitope", "1n8z_epitope_report.json")

# Chain mapping and variable-domain ends, each anchored on a motif index that
# the report records, so load_parent() can verify it rather than trust it.
PARENT_DOMAINS = {
    "H": {"report_chain": "B",
          "constant_start_motif": "IgG1_CH1_start_ASTKGPSVFPLAP",
          "note": "VH is everything before CH1"},
    "L": {"report_chain": "A",
          "constant_start_motif": "IgG_kappa_CL_start_RTVAAPSVFIFPPS",
          "note": "VL is everything before CL"},
}

# CDR spans as 1-based inclusive positions in the VARIABLE DOMAIN sequence of
# 1N8Z (not IMGT positions - IMGT numbering needs ANARCII, which is a stub in
# 02_interface.py, and the two are NOT interchangeable).
#
# Provenance of these spans, because loop boundaries are a choice and no
# organiser source defines them (probe-findings.md §3 says so explicitly):
#   CDRH2, CDRH3, CDRL3 are motif-anchored - the report records
#     RIYPTNGYTR at B:50, WGGDGFYAMDY at B:99, QQHYTTPPT at A:89.
#   CDRH1, CDRL1, CDRL2 are Kabat spans positioned off the FR2 motif indices
#     the report also records (WVRQAP at B:36, WYQQKP at A:35).
# Every span is cross-checked at load time against the buried-residue lists in
# probe-findings.md §3 (verify_spans below): H1 must contain Y33; H2 R50 Y52 Y57
# T58 R59; H3 W99 G103 F104 Y105; L1 D28 N30 T31 A32; L2 S50 F53; L3 H91 Y92 T93
# T94. All 20 paratope residues land inside these spans, which is what makes
# them defensible rather than merely plausible.
CDR_SPANS = {
    "H": {"CDRH1": (31, 35), "CDRH2": (50, 59), "CDRH3": (99, 109)},
    "L": {"CDRL1": (24, 34), "CDRL2": (50, 56), "CDRL3": (89, 97)},
}
CDR_SPAN_DEFINITION = (
    "1-based inclusive positions in the 1N8Z variable domain; CDRH2/CDRH3/CDRL3 "
    "motif-anchored from 1n8z_epitope_report.json, CDRH1/CDRL1/CDRL2 Kabat spans "
    "anchored on the FR2 motif indices. OURS, not an organiser definition. "
    "Override with --cdr-spans-json.")

# The paratope residues each span must contain, from probe-findings.md §3.
# A span that stops containing its residues means the data changed under us.
SPAN_SELF_CHECK = {
    "H": {"CDRH1": {33: "Y"},
          "CDRH2": {50: "R", 52: "Y", 57: "Y", 58: "T", 59: "R"},
          "CDRH3": {99: "W", 103: "G", 104: "F", 105: "Y"}},
    "L": {"CDRL1": {28: "D", 30: "N", 31: "T", 32: "A"},
          "CDRL2": {50: "S", 53: "F"},
          "CDRL3": {91: "H", 92: "Y", 93: "T", 94: "T"}},
}

# --------------------------------------------------------------------------
# score names
# --------------------------------------------------------------------------
# Direction is asserted ONLY where our sources settle it:
#   framework_mutations      we compute it; a count away from the parent, so
#                            lower is better by construction.
#   framework_identity       likewise, higher is better by construction.
#   esm2_pll_per_residue     a pseudo-log-likelihood; more native-like is
#                            higher. Unambiguous.
#   vh_vl_interface_ddg      SIGN CONVENTION UNCONFIRMED. stab-ddg's reference
#   esm2_variant_score       does not state whether a stabilising mutation is
#                            negative or positive, and score-variants' sign is
#                            not documented in our sources either. Ranking on a
#                            score whose direction we guessed would invert the
#                            list silently, so both are marked unconfirmed and
#                            05_filter_rank.py refuses to weight them until
#                            someone confirms the convention and edits this map.
STABILITY_SCORES = {
    "framework_mutations": {"higher_is_better": False,
                            "what": "substitutions outside the CDRs, vs the stated reference"},
    "framework_identity": {"higher_is_better": True,
                           "what": "1 - framework_mutations / framework length"},
    "esm2_pll_per_residue": {"higher_is_better": True,
                             "what": "esm2-650m score-sequences pseudo-log-likelihood, per-residue MEAN"},
    "vh_vl_interface_ddg": {"higher_is_better": None,
                            "what": "stab-ddg predict-binding-ddg across H vs L. NOT a folding ddG"},
    "esm2_variant_score": {"higher_is_better": None,
                           "what": "esm2-650m score-variants, parent-relative"},
}
DIRECTION_UNCONFIRMED = tuple(k for k, v in STABILITY_SCORES.items()
                              if v["higher_is_better"] is None)

# Models, with the operation names our sources do state.
STAB_DDG = {"model": "stab-ddg", "operation": "predict-binding-ddg"}
ESM2 = {"model": "esm2-650m",
        "operation_denovo": "score-sequences",
        "operation_optimisation": "score-variants"}

# Models that must never be used for this axis, with the reason, so that a
# later contributor reading only this file still gets the warning.
REFUSED_MODELS = {
    "bioemu2": "emits conformations only - no dG, ddG or Tm - and needs an MSA "
               "per chain; any stability number off 8 samples is invented "
               "(probe-findings.md §4)",
}


# --------------------------------------------------------------------------
# parent loading
# --------------------------------------------------------------------------

def load_parent(report_path: str | None = None) -> dict:
    """Trastuzumab's variable domains and CDR spans, from the committed report.

    Returns {"H": {"sequence", "span", ...}, "L": {...}, "source": {...}}.
    Raises ValueError if the report's own motif evidence disagrees with the
    spans in this file - a silent shift here would mis-split framework from CDR
    on every candidate at once, so it fails loudly instead.
    """
    path = report_path or EPITOPE_REPORT
    if not os.path.exists(path):
        return {}
    rep = common.read_json(path)
    chains = rep.get("chains") or {}
    motifs = rep.get("identity_motif_evidence_1based_index_in_observed_seq") or {}

    out = {"source": {"path": os.path.abspath(path),
                      "pdb": rep.get("pdb") or "1N8Z",
                      "cdr_span_definition": CDR_SPAN_DEFINITION}}
    for label, spec in PARENT_DOMAINS.items():
        rc = spec["report_chain"]
        full = ((chains.get(rc) or {}).get("sequence") or "").strip().upper()
        if not full:
            raise ValueError("{0}: chain {1} has no sequence".format(path, rc))
        cstart = (motifs.get(rc) or {}).get(spec["constant_start_motif"])
        if not isinstance(cstart, int) or cstart < 2:
            raise ValueError(
                "{0}: chain {1} has no usable index for {2}, so the variable "
                "domain boundary is unknown. Fix the report or pass "
                "--parent-json.".format(path, rc, spec["constant_start_motif"]))
        variable = full[:cstart - 1]
        out[label] = {
            "sequence": variable,
            "length": len(variable),
            "report_chain": rc,
            "variable_domain_1based": [1, len(variable)],
            "constant_domain_starts_at": cstart,
            "cdr_spans": dict(CDR_SPANS[label]),
            "full_chain_length": len(full),
        }
    verify_spans(out)
    return out


def verify_spans(parent: dict) -> None:
    """Cross-check every CDR span against probe-findings.md §3's residue lists.

    This is the one guard that makes CDR_SPANS evidence rather than assertion:
    if a span no longer contains the paratope residues the epitope analysis
    found buried in it, the spans and the data have drifted apart and the
    framework/CDR split is wrong.
    """
    problems = []
    for label in ("H", "L"):
        seq = (parent.get(label) or {}).get("sequence") or ""
        for cdr, expected in SPAN_SELF_CHECK.get(label, {}).items():
            lo, hi = CDR_SPANS[label][cdr]
            for pos, aa in expected.items():
                if not (lo <= pos <= hi):
                    problems.append("{0} {1}: position {2} is outside span {3}-{4}".format(
                        label, cdr, pos, lo, hi))
                elif pos > len(seq):
                    problems.append("{0} {1}: position {2} is past the {3}-residue domain".format(
                        label, cdr, pos, len(seq)))
                elif seq[pos - 1] != aa:
                    problems.append("{0} {1}: position {2} is {3!r}, probe-findings §3 says {4!r}".format(
                        label, cdr, pos, seq[pos - 1], aa))
    if problems:
        raise ValueError(
            "CDR spans disagree with the committed 1N8Z data:\n  " + "\n  ".join(problems) +
            "\nThe framework/CDR split drives the only stability term with a known "
            "direction, so this is a hard stop. Re-derive CDR_SPANS in "
            "pipeline/thermostability.py, or pass --cdr-spans-json.")


def cdr_positions(spans: dict) -> set:
    """Flatten {name: (lo, hi)} to a set of 1-based positions."""
    out = set()
    for lo, hi in spans.values():
        out.update(range(lo, hi + 1))
    return out


# --------------------------------------------------------------------------
# framework germline-likeness - the one term we compute ourselves
# --------------------------------------------------------------------------

def framework_mutations(design_seq: str, parent_seq: str, spans: dict,
                        *, boundary_window: int = 2) -> dict:
    """Substitutions in `design_seq` that fall outside the CDRs of `parent_seq`.

    Aligns the two (Needleman-Wunsch from common.align_global), walks the
    alignment, and classifies every differing column by where it sits in the
    PARENT: inside a CDR span or in the framework. Gap columns count as
    differences, as common.mutation_count does, and are reported separately so a
    length change is never silently read as a point substitution.

    `boundary_sensitive` counts framework differences lying within
    `boundary_window` of a span edge. Those are the ones whose classification
    would flip if the span definition - which is ours, not an organiser's - is
    off by a residue or two. Reporting it is how this number stays honest about
    the one assumption underneath it.
    """
    if not design_seq or not parent_seq:
        return {"framework_mutations": None,
                "note": "empty design or parent sequence"}

    aq, ar = common.align_global(design_seq, parent_seq)
    in_cdr = cdr_positions(spans)
    edges = set()
    for lo, hi in spans.values():
        for e in (lo, hi):
            edges.update(range(max(1, e - boundary_window), e + boundary_window + 1))

    ppos = 0
    fw_sub = fw_gap = cdr_sub = cdr_gap = 0
    fw_len = 0
    boundary = 0
    fw_detail, cdr_detail = [], []
    for x, y in zip(aq, ar):
        if y != "-":
            ppos += 1                      # a real parent position
            is_cdr = ppos in in_cdr
            if not is_cdr:
                fw_len += 1
            if x == y:
                continue
            if x == "-":                   # deletion relative to the parent
                if is_cdr:
                    cdr_gap += 1
                else:
                    fw_gap += 1
                    if ppos in edges:
                        boundary += 1
                continue
            if is_cdr:
                cdr_sub += 1
                cdr_detail.append("{0}{1}{2}".format(y, ppos, x))
            else:
                fw_sub += 1
                fw_detail.append("{0}{1}{2}".format(y, ppos, x))
                if ppos in edges:
                    boundary += 1
        else:
            # insertion relative to the parent: it has no parent position, so it
            # cannot be classified as framework or CDR. Counted, never placed.
            fw_gap += 0
            cdr_gap += 0

    insertions = sum(1 for x, y in zip(aq, ar) if y == "-" and x != "-")
    fw_total = fw_sub + fw_gap
    return {
        "framework_mutations": fw_total,
        "framework_substitutions": fw_sub,
        "framework_gap_columns": fw_gap,
        "framework_length": fw_len,
        "framework_identity": (round(1.0 - fw_total / fw_len, 4) if fw_len else None),
        "cdr_substitutions": cdr_sub,
        "cdr_gap_columns": cdr_gap,
        "insertions_unplaceable": insertions,
        "boundary_sensitive": boundary,
        "framework_detail": fw_detail,
        "cdr_detail": cdr_detail,
        "definition": "substitutions and gap columns at parent positions outside "
                      "the CDR spans; " + CDR_SPAN_DEFINITION,
    }


def germline_likeness(rec: dict, parent: dict, *, germline_panel: dict | None = None) -> dict:
    """Framework germline-likeness for one candidate, per track.

    Optimisation: the parent IS trastuzumab, so the reference is the parent and
    the number is exact - "how far has this design's framework drifted from the
    framework we started from".

    De novo: there is no parent. The reference must be a germline panel, which
    this repo deliberately does not ship: writing IGHV/IGKV sequences from
    memory is precisely the fabricated number common.py exists to prevent. With
    no --germline-json the term is null with that reason. Fetch a panel from
    IMGT, or from the hackathon bucket alongside issue #5, and pass it in.
    """
    track = (rec.get("track_intent") or "unknown").lower()
    chains = common.candidate_sequences(rec)
    if not chains:
        return {"value": None, "note": "candidate carries no sequence"}

    if track.startswith("opt"):
        if not parent.get("H"):
            return {"value": None,
                    "note": "no trastuzumab parent available: "
                            "data/reference/epitope/1n8z_epitope_report.json is missing or "
                            "has no usable domain boundary"}
        per_chain, total, fw_len, boundary, partial = {}, 0, 0, 0, []
        for label, seq in chains.items():
            pl = parent.get(label)
            if not pl:
                partial.append(label)
                continue
            res = framework_mutations(seq, pl["sequence"], pl["cdr_spans"])
            per_chain[label] = res
            if res.get("framework_mutations") is None:
                partial.append(label)
                continue
            total += res["framework_mutations"]
            fw_len += res.get("framework_length") or 0
            boundary += res.get("boundary_sensitive") or 0
        if not per_chain or partial:
            return {"value": (total if per_chain else None),
                    "per_chain": per_chain,
                    "note": "no parent domain for chain(s) {0}, so this is a PARTIAL count - "
                            "not comparable with a complete one".format(",".join(partial))
                            if partial else None,
                    "partial": bool(partial),
                    "reference": "trastuzumab 1N8Z variable domains"}
        return {"value": total,
                "framework_identity": (round(1.0 - total / fw_len, 4) if fw_len else None),
                "framework_length": fw_len,
                "boundary_sensitive": boundary,
                "per_chain": per_chain,
                "partial": False,
                "reference": "trastuzumab 1N8Z variable domains "
                             "(data/reference/epitope/1n8z_epitope_report.json)"}

    # de novo, or a track we were not told
    if not germline_panel:
        return {"value": None,
                "note": "de novo has no parent, and no germline panel was supplied. "
                        "Framework germline-likeness needs an explicit reference; this repo "
                        "ships no germline sequences because writing them from memory is a "
                        "fabricated number. Pass --germline-json "
                        "{\"IGHV3-23\": \"<seq>\", ...} from IMGT or the hackathon bucket.",
                "reference": None}
    best = None
    for name, gseq in germline_panel.items():
        if not isinstance(gseq, str) or not gseq:
            continue
        # The panel is germline V genes, which have CDR1/CDR2 but no CDR3, so
        # the design's CDR3 cannot be excluded by a parent span here. We compare
        # whole variable domains and SAY that, rather than pretending the split
        # is the same as the optimisation one.
        ident = common.identity(next(iter(chains.values())), gseq)
        if ident.get("identity") is None:
            continue
        if best is None or ident["identity"] > best["identity"]:
            best = {"germline": name, **ident}
    if best is None:
        return {"value": None, "note": "germline panel contained no usable sequence"}
    return {"value": None,
            "nearest_germline": best,
            "note": "reported as whole-variable-domain identity to the nearest germline, NOT "
                    "as a framework-only mutation count: a germline V gene has no CDR3, so the "
                    "framework/CDR split used for optimisation does not apply. Not comparable "
                    "with the optimisation framework_mutations column.",
            "reference": "germline panel supplied via --germline-json"}


# --------------------------------------------------------------------------
# model requests - built here, never dispatched here
# --------------------------------------------------------------------------

def vh_vl_interface_ddg_request(rec: dict, parent: dict) -> dict:
    """Build the stab-ddg request, or say why there is none.

    This is the VH-VL INTERFACE ddG. stab-ddg needs two disjoint partner chain
    sets; a Fab or scFv has H and L, so partner_a=["H"] and partner_b=["L"] is a
    legitimate call and VH-VL pairing is a real determinant of antibody Tm. It
    is still a proxy and it is blind to intra-domain destabilisation. It is not
    a folding ddG and must never be reported as one.

    Returns {"request": {...}} or {"request": None, "reason": "..."}.
    """
    track = (rec.get("track_intent") or "unknown").lower()
    fmt = rec.get("format")
    chains = common.candidate_sequences(rec)

    if not track.startswith("opt"):
        return {"request": None,
                "reason": "de novo: a ddG is UNDEFINED without a parent to subtract, not merely "
                          "noisy. Reporting one would mean silently choosing a reference, and "
                          "that choice would drive the ranking instead of the design "
                          "(probe-findings.md §4)."}
    if fmt == "VHH" or set(chains) == {"H"}:
        return {"request": None,
                "reason": "single-domain candidate: stab-ddg requires two DISJOINT partner chain "
                          "sets, so there is no second partner and it returns nothing. Use "
                          "esm2-650m score-variants and framework germline-likeness instead."}
    if "H" not in chains or "L" not in chains:
        return {"request": None,
                "reason": "needs both an H and an L chain to form two disjoint partner sets; "
                          "candidate has {0}".format(",".join(sorted(chains)) or "no chains")}

    mutations, note = parent_point_mutations(rec, parent)
    return {"request": {
                "model": STAB_DDG["model"],
                "operation": STAB_DDG["operation"],
                "partner_a": ["H"],
                "partner_b": ["L"],
                "structure_path": rec.get("structure_path"),
                "sequences": {k: chains[k] for k in ("H", "L")},
                "mutations": mutations,
                "candidate_id": rec.get("candidate_id"),
            },
            "label": "VH-VL interface ddG",
            "never_label_as": ["folding ddG", "stability ddG", "Tm"],
            "mutation_note": note,
            "schema_unverified": "confirm with `python3 forge.py schema stab-ddg`: the argument "
                                 "names for the two partner sets, whether mutations are passed as "
                                 "a list and in what notation, and whether a structure is required "
                                 "or a sequence pair is enough. Also confirm the SIGN CONVENTION - "
                                 "which direction is stabilising - before anything ranks on it."}


def parent_point_mutations(rec: dict, parent: dict) -> tuple:
    """Point mutations of an optimisation design away from trastuzumab, as
    `H:T30A`-style strings. Notation is OURS and unverified against stab-ddg."""
    if not parent.get("H"):
        return [], "no parent available, so no mutation list could be built"
    muts = []
    for label, seq in common.candidate_sequences(rec).items():
        pl = parent.get(label)
        if not pl:
            continue
        res = framework_mutations(seq, pl["sequence"], pl["cdr_spans"])
        for d in (res.get("framework_detail") or []) + (res.get("cdr_detail") or []):
            muts.append("{0}:{1}".format(label, d))
    return sorted(muts), ("notation `<chain>:<parent_aa><parent_pos><design_aa>`, positions "
                          "1-based in the 1N8Z variable domain. OURS - confirm what stab-ddg "
                          "expects before submitting.")


def esm2_request(rec: dict) -> dict:
    """Build the esm2-650m request appropriate to the track.

    Optimisation has a parent, so `score-variants` is the parent-relative call.
    De novo has none, so `score-sequences` gives an absolute pseudo-likelihood.

    The PLL MUST be reported as a per-residue mean, never a sum: candidate
    lengths differ, and a sum ranks long sequences above short ones for being
    long (probe-findings.md §4).
    """
    track = (rec.get("track_intent") or "unknown").lower()
    chains = common.candidate_sequences(rec)
    if not chains:
        return {"request": None, "reason": "candidate carries no sequence"}
    op = (ESM2["operation_optimisation"] if track.startswith("opt")
          else ESM2["operation_denovo"])
    return {"request": {"model": ESM2["model"],
                        "operation": op,
                        "sequences": dict(chains),
                        "candidate_id": rec.get("candidate_id")},
            "reduction": ("per-residue MEAN pseudo-log-likelihood; never a sum"
                          if op == ESM2["operation_denovo"] else "parent-relative variant score"),
            "schema_unverified": "confirm with `python3 forge.py schema esm2-650m`: the operation "
                                 "name, how sequences are passed, whether the reply is a per-residue "
                                 "array or a single reduced number, and the sign convention of "
                                 "score-variants."}


def pll_per_residue_mean(values, *, length: int | None = None) -> dict:
    """Reduce a PLL reply to a per-residue mean.

    Accepts a per-residue list, or a single number WITH the length it covers.
    A single number without a length is refused rather than divided by a guess:
    the whole point of this reduction is that lengths differ.
    """
    if isinstance(values, (list, tuple)):
        nums = [float(v) for v in values if isinstance(v, (int, float))]
        if not nums:
            return {"value": None, "note": "per-residue PLL array contained no numbers"}
        return {"value": round(sum(nums) / len(nums), 6),
                "n_residues": len(nums),
                "reduction": "mean over per-residue pseudo-log-likelihoods"}
    if isinstance(values, (int, float)):
        if not length:
            return {"value": None,
                    "note": "a single PLL number was given with no sequence length, so it cannot "
                            "be made per-residue. A summed PLL ranks long sequences above short "
                            "ones for being long; pass the length or the per-residue array."}
        return {"value": round(float(values) / length, 6),
                "n_residues": length,
                "reduction": "summed PLL divided by stated length"}
    return {"value": None, "note": "unrecognised PLL reply shape"}


def corroboration_note(present: list) -> str | None:
    """ESM-2 and ESMC are the same kind of model, so two of them agreeing is one
    piece of evidence twice, not a second opinion."""
    fam = [p for p in present if p.startswith("esm")]
    if len(fam) < 2:
        return None
    return ("{0} are all masked-language-model likelihoods of the same family. Their agreement is "
            "NOT corroboration and they must not be averaged as independent evidence. A genuine "
            "second opinion on stability would have to come from a different kind of model, and "
            "probe-findings.md §4 establishes the platform has none.".format(", ".join(sorted(fam))))


def dispatch(*_args, **_kwargs):
    """No model call happens in this file."""
    raise common.must_confirm(
        "the stab-ddg and esm2-650m request schemas",
        "`python3 forge.py schema stab-ddg` and `python3 forge.py schema esm2-650m` on the VM. "
        "Write the payloads with --emit-requests, check them against those schemas, submit them "
        "with forge.py, then feed the replies back with --stab-ddg-scores / --esm2-scores.")


# --------------------------------------------------------------------------
# attach
# --------------------------------------------------------------------------

def stability_terms(rec: dict, parent: dict, *, germline_panel=None,
                    stab_ddg=None, esm2=None) -> dict:
    """Every stability term for one candidate, as common.score_entry cells.

    No composite is produced. The terms are a count, a ddG and a log-likelihood,
    three of which have no confirmed sign convention in our sources; averaging
    them would be a metric we invented. Stage 05 weights them explicitly.
    """
    entries, meta = {}, {}

    gl = germline_likeness(rec, parent, germline_panel=germline_panel)
    entries["framework_mutations"] = common.score_entry(
        gl.get("value"), model=None,
        note=gl.get("note") or "computed locally; no model involved",
        higher_is_better=STABILITY_SCORES["framework_mutations"]["higher_is_better"])
    fi = gl.get("framework_identity")
    entries["framework_identity"] = common.score_entry(
        fi, model=None,
        note=gl.get("note") if fi is None else "1 - framework_mutations / framework length",
        higher_is_better=STABILITY_SCORES["framework_identity"]["higher_is_better"])
    meta["germline_likeness"] = gl

    ddg_req = vh_vl_interface_ddg_request(rec, parent)
    cid = str(rec.get("candidate_id"))
    ddg_val = (stab_ddg or {}).get(cid, {}).get("vh_vl_interface_ddg") if stab_ddg else None
    if ddg_req.get("request") is None:
        entries["vh_vl_interface_ddg"] = common.score_entry(
            None, model=STAB_DDG["model"], note=ddg_req.get("reason"),
            higher_is_better=None)
    else:
        entries["vh_vl_interface_ddg"] = common.score_entry(
            ddg_val, model=STAB_DDG["model"],
            note=("VH-VL INTERFACE ddG from predict-binding-ddg across partner_a=[H] and "
                  "partner_b=[L]. NOT a folding ddG, NOT a Tm. Sign convention unconfirmed, so "
                  "stage 05 will not rank on it yet."
                  if ddg_val is not None else
                  "request buildable but no value supplied; run it and pass --stab-ddg-scores"),
            higher_is_better=None)
    meta["vh_vl_interface_ddg"] = ddg_req

    e2 = esm2_request(rec)
    raw = (esm2 or {}).get(cid, {}) if esm2 else {}
    track = (rec.get("track_intent") or "unknown").lower()
    if track.startswith("opt"):
        entries["esm2_variant_score"] = common.score_entry(
            raw.get("esm2_variant_score"), model=ESM2["model"],
            version=ESM2["operation_optimisation"],
            note=("parent-relative variant score; sign convention unconfirmed, so stage 05 will "
                  "not rank on it yet" if raw.get("esm2_variant_score") is not None else
                  "no value supplied; run score-variants and pass --esm2-scores"),
            higher_is_better=None)
        entries["esm2_pll_per_residue"] = common.score_entry(
            None, model=ESM2["model"],
            note="optimisation uses the parent-relative score-variants call, not an absolute PLL",
            higher_is_better=STABILITY_SCORES["esm2_pll_per_residue"]["higher_is_better"])
    else:
        seqs = common.candidate_sequences(rec)
        n = sum(len(s) for s in seqs.values()) or None
        if raw.get("esm2_pll") is None:
            # Nothing was supplied. That is different from a reply we could not
            # read, and the note has to say which, or a missing run looks like a
            # malformed one.
            entries["esm2_pll_per_residue"] = common.score_entry(
                None, model=ESM2["model"], version=ESM2["operation_denovo"],
                note="no value supplied; run score-sequences and pass --esm2-scores",
                higher_is_better=STABILITY_SCORES["esm2_pll_per_residue"]["higher_is_better"])
        else:
            red = pll_per_residue_mean(raw.get("esm2_pll"), length=raw.get("length") or n)
            entries["esm2_pll_per_residue"] = common.score_entry(
                red.get("value"), model=ESM2["model"], version=ESM2["operation_denovo"],
                note=red.get("note") or red.get("reduction"),
                higher_is_better=STABILITY_SCORES["esm2_pll_per_residue"]["higher_is_better"])
        entries["esm2_variant_score"] = common.score_entry(
            None, model=ESM2["model"],
            note="de novo has no parent, so a parent-relative variant score is undefined",
            higher_is_better=None)
    meta["esm2"] = e2

    present = [k for k, v in entries.items() if v.get("value") is not None]
    # The two esm2 terms here are mutually exclusive by track, so they alone can
    # never trip the guard. It is written against the case that actually
    # threatens the ranking: someone adds an ESMC term in another stage and the
    # table then shows two "independent" stability numbers that are the same
    # kind of model. So look at every score on the record, not just ours.
    merged = dict(rec.get("scores") or {})
    merged.update(entries)
    esm_family = sorted(k for k, v in merged.items()
                        if k.startswith("esm") and (v or {}).get("value") is not None)
    meta["axis"] = {
        "axis": "thermostability",
        "is_proxy": True,
        "evidence_strength": "weakest of the three judged axes - say so in the pitch",
        "composite_emitted": False,
        "why_no_composite": "the terms are a count, a ddG in kcal/mol and a log-likelihood, and "
                            "three have no confirmed sign convention; a single number would be "
                            "one we invented",
        "terms_with_values": present,
        "direction_unconfirmed": list(DIRECTION_UNCONFIRMED),
        "cross_track_warning":
            "framework_mutations is computable for optimisation designs (parent = trastuzumab) "
            "but null for de novo designs unless a germline panel is supplied. Stage 05 "
            "normalises within the whole candidate set, so weighting this term in a MIXED-track "
            "run gives every de novo design rank_score=None and sorts them all last - not "
            "because they are worse, but because the term does not exist for them. Rank within "
            "track, or supply --germline-json, or weight it only in an optimisation-only run.",
        "refused_models": REFUSED_MODELS,
        # Only the terms that actually CARRY a value can corroborate each other.
        # Warning off the term names would fire on every candidate, including
        # ones where no esm2 run happened at all.
        "corroboration_warning": corroboration_note(esm_family),
        "source": "docs/probe-findings.md §4; GitHub issue #10",
    }
    return {"entries": entries, "meta": meta}


def attach(recs: list, parent: dict, *, germline_panel=None, stab_ddg=None,
           esm2=None, inputs=None, run_id=None) -> list:
    """Attach the stability terms to every record, with provenance."""
    for rec in recs:
        res = stability_terms(rec, parent, germline_panel=germline_panel,
                              stab_ddg=stab_ddg, esm2=esm2)
        scores = rec.setdefault("scores", {})
        scores.update(res["entries"])
        rec.setdefault("stability", {}).update(res["meta"])
        rec.setdefault("stage_provenance", []).append(common.provenance(
            STAGE,
            model=None,
            settings={"cdr_span_definition": CDR_SPAN_DEFINITION,
                      "parent": (parent.get("source") or {}).get("path"),
                      "germline_panel_supplied": bool(germline_panel),
                      "stab_ddg_values_supplied": bool(stab_ddg),
                      "esm2_values_supplied": bool(esm2)},
            inputs=inputs or [],
            run_id=run_id))
    return recs


def parse_model_scores(path: str) -> dict:
    """Read externally-produced stability numbers into {candidate_id: {...}}.

    Mirrors 04_score.py's parse_refold_scores: JSON object keyed by id, JSON
    list with an id field, or CSV with a header. Recognised value columns:
    vh_vl_interface_ddg, esm2_variant_score, esm2_pll (number or list), length.
    An unrecognised column is ignored; a candidate not in the file keeps null.
    """
    id_keys = ("candidate_id", "id", "design", "design_id", "name")
    wanted = ("vh_vl_interface_ddg", "esm2_variant_score", "esm2_pll", "length")

    def row_scores(row: dict) -> dict:
        out = {}
        for k, v in row.items():
            kk = str(k).strip().lower()
            if kk not in wanted or v in (None, "", "NA", "nan", "None"):
                continue
            if kk == "esm2_pll" and isinstance(v, (list, tuple)):
                out[kk] = list(v)
                continue
            try:
                out[kk] = float(v)
            except (TypeError, ValueError):
                pass
        return out

    if path.lower().endswith((".csv", ".tsv")):
        import csv
        delim = "\t" if path.lower().endswith(".tsv") else ","
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh, delimiter=delim))
        out = {}
        for row in rows:
            cid = next((row[k] for k in row if str(k).strip().lower() in id_keys and row[k]), None)
            if cid:
                out[str(cid)] = row_scores(row)
        return out

    data = common.read_json(path)
    if isinstance(data, list):
        out = {}
        for row in data:
            cid = next((row[k] for k in row if str(k).strip().lower() in id_keys and row[k]), None)
            if cid:
                out[str(cid)] = row_scores(row)
        return out
    if isinstance(data, dict):
        return {str(cid): row_scores(v) for cid, v in data.items() if isinstance(v, dict)}
    raise SystemExit("{0}: cannot read as stability scores".format(path))


# --------------------------------------------------------------------------

def main(argv=None) -> int:
    p = common.base_parser(
        "Stage 04b: attach the thermostability axis - framework germline-likeness "
        "(local, free), plus the VH-VL interface ddG and esm2 terms when their values "
        "are supplied. Emits no composite score and fabricates nothing.",
        epilog="Read docs/probe-findings.md §4 first. `stab-ddg` is a BINDING ddG: it is "
               "reported here as a VH-VL interface ddG and never as a folding ddG or a Tm.")
    p.add_argument("candidates", help="candidates JSONL (stage 03 or 04 output)")
    common.add_io_args(p, out_default=None)
    p.add_argument("--parent-json", default=None,
                   help="override the 1N8Z epitope report used for the trastuzumab parent")
    p.add_argument("--cdr-spans-json", default=None,
                   help='override CDR spans: {"H": {"CDRH3": [99, 109], ...}, "L": {...}}')
    p.add_argument("--germline-json", default=None,
                   help='germline panel for de novo framework comparison: '
                        '{"IGHV3-23": "<seq>", ...}. Without it the de novo term is null.')
    p.add_argument("--stab-ddg-scores", default=None,
                   help="JSON/CSV of stab-ddg replies (vh_vl_interface_ddg per candidate)")
    p.add_argument("--esm2-scores", default=None,
                   help="JSON/CSV of esm2-650m replies (esm2_variant_score, esm2_pll, length)")
    p.add_argument("--emit-requests", default=None, metavar="DIR",
                   help="write the request payloads here for schema checking; no network call")
    args = p.parse_args(argv)

    recs = common.read_jsonl(args.candidates)
    if not recs:
        print("{0}: no candidate records - nothing to score".format(args.candidates),
              file=sys.stderr)
        return 1

    parent = load_parent(args.parent_json)
    if args.cdr_spans_json:
        override = common.read_json(args.cdr_spans_json)
        for label in ("H", "L"):
            if label in override and parent.get(label):
                parent[label]["cdr_spans"] = {k: tuple(v) for k, v in override[label].items()}
        parent.setdefault("source", {})["cdr_span_definition"] = \
            "overridden from {0}".format(os.path.abspath(args.cdr_spans_json))

    germline = common.read_json(args.germline_json) if args.germline_json else None
    stab = parse_model_scores(args.stab_ddg_scores) if args.stab_ddg_scores else None
    esm2v = parse_model_scores(args.esm2_scores) if args.esm2_scores else None

    inputs = [p_ for p_ in (args.candidates, args.parent_json or EPITOPE_REPORT,
                            args.germline_json, args.stab_ddg_scores, args.esm2_scores) if p_]
    attach(recs, parent, germline_panel=germline, stab_ddg=stab, esm2=esm2v,
           inputs=inputs, run_id=args.run_id)

    if args.emit_requests:
        os.makedirs(args.emit_requests, exist_ok=True)
        reqs = []
        for rec in recs:
            meta = rec.get("stability") or {}
            reqs.append({"candidate_id": rec.get("candidate_id"),
                         "track_intent": rec.get("track_intent"),
                         "format": rec.get("format"),
                         "stab_ddg": meta.get("vh_vl_interface_ddg"),
                         "esm2": meta.get("esm2")})
        common.write_json(os.path.join(args.emit_requests, "stability_requests.json"),
                          {"stage": STAGE, "generated_at": common.utc_now(),
                           "warning": "schemas UNVERIFIED - check against `forge.py schema "
                                      "stab-ddg` and `forge.py schema esm2-650m` before submitting",
                           "requests": reqs})

    common.write_jsonl(args.out, recs)

    rows = []
    for rec in recs:
        s = rec.get("scores") or {}
        rows.append([rec.get("candidate_id"), rec.get("track_intent"), rec.get("format"),
                     s.get("framework_mutations", {}).get("value"),
                     s.get("framework_identity", {}).get("value"),
                     s.get("vh_vl_interface_ddg", {}).get("value"),
                     s.get("esm2_pll_per_residue", {}).get("value"),
                     s.get("esm2_variant_score", {}).get("value")])
    common.say(args.quiet, common.table(
        [[("" if c is None else c) for c in r] for r in rows],
        ["candidate", "track", "format", "fw_muts", "fw_ident", "vh_vl_ddg", "pll/res", "variant"]))
    common.say(args.quiet, "")
    common.say(args.quiet, "thermostability is a PROXY axis and our weakest evidence "
                           "(docs/probe-findings.md §4). No composite score is emitted.")
    unconf = ", ".join(DIRECTION_UNCONFIRMED)
    common.say(args.quiet, "sign convention unconfirmed, not rankable yet: {0}".format(unconf))
    common.say(args.quiet, "wrote {0}".format(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(common.cli(main))
