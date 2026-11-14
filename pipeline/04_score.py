#!/usr/bin/env python3
"""Stage 04 - score candidates.

Mentor Lluis Artus, step 4: "Filter the results based on solubility, pLDDT,
ipSAE".

Two groups of scores, both attached to the candidate record with their own
provenance (model, version, seed, source file):

  INTERFACE / REFOLD   min_ipae, iptm, binder_plddt.
      Source: task PDF p6 - "run refold-prepare on your designs, fold the
      prepared inputs with any Predict Structure model, then score them with
      refold-score"; and "For the HER2 exercise the pass column stays empty, so
      rank on min_ipae, iptm and binder_plddt." Those three names are the task
      PDF's, so they are the column names here.
      Also from the PDF: "for binders a model that takes a template gives a
      fairer check, because ESMFold2 folds the target unguided". Template
      support per model is in PREDICT_MODELS below.

  DEVELOPABILITY       Aggrescan 3D, SoluProt, NetSolP, ProteinMPNN with
      soluble weights. Source: task PDF p7 - "previous experience of Adaptyv
      tells us that expression success improved once participants started
      scoring candidates with Aggrescan 3D, SoluProt, NetSolP, and ProteinMPNN
      with soluble weights". No threshold is given for any of them, so this
      stage records values and never decides.

Plus LIABILITY FLAGS, which are counted from the sequence here, locally. Those
are not model scores and are labelled as flags.

Nothing in this file fabricates a number. A score we did not read is null with a
note saying why, and stage 05 treats null as missing, not as zero.

This stage only ADDS keys to a candidate record. Everything stage 03 wrote is
carried through untouched, `cdrh3` included - stage 05's novelty check reads it,
and dropping it would silently disable the one hard filter that decides the
track. The summary line below counts how many records still carry it.

Usage:
  python3 04_score.py runs/candidates.jsonl --refold-scores results/refold_score.json \\
      --dev-scores results/dev/ -o runs/scored.jsonl
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

# Predict Structure models in Foundry, and whether they take a template.
# Source: task PDF p5 table. Template support matters: the PDF says a
# template-taking model is the fairer check for a binder.
PREDICT_MODELS = {
    "openfold3": {"weights": "OpenBind, preview 2", "template": True},
    "protenix": {"weights": "v2, v1", "template": True},
    "boltz-2": {"weights": "Boltz-2", "template": True},
    "boltz-1": {"weights": "Boltz-1", "template": False},
    "mol-1": {"weights": "base", "template": True},
    "esmfold2": {"weights": "release", "template": False},
}

# Interface scores we collect, and which direction is better.
# min_ipae is a PAE, in angstrom, so lower is better. iptm and binder_plddt are
# confidences, so higher is better.
INTERFACE_SCORES = {
    "min_ipae": False,
    "iptm": True,
    "binder_plddt": True,
}

# ipSAE is in the mentor's step 4 but NOT in the task PDF's list of what
# refold-score emits. TODO: confirm whether Foundry's refold-score reports ipSAE;
# if not, it has to be computed from the PAE matrix separately. Until then this
# pipeline does not claim an ipSAE.
OPTIONAL_INTERFACE_SCORES = ("ipsae",)

DEV_SCORES = {
    "aggrescan3d": {"tool": "Aggrescan 3D", "higher_is_better": False,
                    "note": "aggregation propensity; needs a structure"},
    "soluprot": {"tool": "SoluProt", "higher_is_better": True,
                 "note": "predicted soluble expression probability"},
    "netsolp": {"tool": "NetSolP", "higher_is_better": True,
                "note": "predicted solubility/usability"},
    "mpnn_soluble": {"tool": "ProteinMPNN (soluble weights)", "higher_is_better": True,
                     "note": "sequence log-likelihood under soluble-weight ProteinMPNN"},
}

# Sequence liability motifs. Source: docs/hackathon-brief.md, "Fix what the
# sequence shows". These are counts of motif occurrences, not scores, and the
# brief is explicit that they matter "mainly in or near a CDR and when
# solvent-exposed" - so a count here is a prompt to look, not a verdict.
LIABILITY_MOTIFS = {
    "NG_deamidation": r"NG",
    "DG_isomerization": r"DG",
    "DP_acid_labile": r"DP",
    "N_glycosylation": r"N[^P][ST]",
    "M_oxidation": r"M",
    "W_oxidation": r"W",
}


def liability_flags(rec: dict) -> dict:
    """Count liability motifs per chain. Local, deterministic, no model."""
    out = {}
    for chain, seq in common.candidate_sequences(rec).items():
        per = {}
        for name, pattern in LIABILITY_MOTIFS.items():
            per[name] = len(re.findall(pattern, seq))
        per["cysteines"] = seq.count("C")
        out[chain] = per
    out["_definition"] = "motif counts over the whole chain; see docs/hackathon-brief.md. " \
                         "Not weighted, not a score, and not restricted to CDRs or exposed positions."
    return out


# --------------------------------------------------------------------------
# refold: prepare -> fold -> score
# --------------------------------------------------------------------------

def foundry_refold_prepare(candidates: list, out_dir: str, predict_model: str):
    """RFD4-Proteina `refold-prepare`: write Predict Structure inputs for the
    designs we picked.

    UNVERIFIED INTERFACE. What the task PDF states and all it states: the task
    exists, it "pick[s] your best designs and write[s] the inputs for refolding
    them with Predict Structure", and "All the models above are available for
    refolding".

    Confirm on the VM:
        foundry-toolkit module list
        open <bucket>/rfd4-proteina/docs/Tutorial.html     # has a ready-made HER2 script
    What must be confirmed: the command, how the design set is selected, the
    output layout, and which Predict Structure model name string is accepted.
    """
    raise common.must_confirm(
        "RFD4-Proteina refold-prepare in Foundry",
        "foundry-toolkit module list and rfd4-proteina/docs/Tutorial.html in the hackathon "
        "bucket; wire it into foundry_refold_prepare() in pipeline/04_score.py. Until then, "
        "run refold-prepare/refold-score by hand and pass the result to --refold-scores.")


def foundry_refold_score(refold_dir: str, out_path: str):
    """RFD4-Proteina `refold-score`: score refolds against its own pass criteria.

    UNVERIFIED INTERFACE. The task PDF names the criteria ("such as interface
    PAE, binder pLDDT and RMSD to the design") and the three columns we rank on
    (min_ipae, iptm, binder_plddt), and warns that "For the HER2 exercise the
    pass column stays empty". It does not give the command or the output format.

    Confirm on the VM: the command, and the exact file the scores land in
    (JSON or CSV, and the column names). Then wire it here and keep
    parse_refold_scores() as the reader.
    """
    raise common.must_confirm(
        "RFD4-Proteina refold-score in Foundry",
        "rfd4-proteina/docs/Tutorial.html in the hackathon bucket; wire it into "
        "foundry_refold_score() in pipeline/04_score.py and confirm the output column names "
        "against min_ipae / iptm / binder_plddt.")


def parse_refold_scores(path: str) -> dict:
    """Read refold-score output into {candidate_id: {score: value}}.

    Accepts, because the real format is not documented in our sources:
      * JSON object keyed by candidate id;
      * JSON list of objects, each with an id field;
      * CSV with a header row.
    The id column is matched case-insensitively against: candidate_id, id,
    design, design_id, name. Score columns are matched by exact name against
    min_ipae / iptm / binder_plddt (and ipsae if present). A column we do not
    recognise is ignored, and a candidate not in the file keeps a null score -
    never a default.
    """
    id_keys = ("candidate_id", "id", "design", "design_id", "name")
    wanted = set(INTERFACE_SCORES) | set(OPTIONAL_INTERFACE_SCORES)

    def row_scores(row: dict) -> dict:
        out = {}
        for k, v in row.items():
            kk = str(k).strip().lower()
            if kk in wanted and v not in (None, "", "NA", "nan", "None"):
                try:
                    out[kk] = float(v)
                except (TypeError, ValueError):
                    pass
        return out

    if path.lower().endswith(".csv") or path.lower().endswith(".tsv"):
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
    raise SystemExit("{0}: cannot read as refold scores (expected JSON object/list or CSV)".format(path))


# --------------------------------------------------------------------------
# developability
# --------------------------------------------------------------------------

def run_developability(tool: str, candidates: list, workdir: str):
    """Run one developability predictor.

    UNVERIFIED FOR ALL FOUR. The task PDF recommends Aggrescan 3D, SoluProt,
    NetSolP and ProteinMPNN-with-soluble-weights by name and links a write-up
    ("Please check the whole write-up here"), but gives no invocation and no
    threshold, and the resource map does not list any of the first three as
    hosted Nebius models. ProteinMPNN IS hosted (resource map: `proteinmpnn`,
    `run`, 2 min) but our sources do not say the hosted copy exposes soluble
    weights - RECIPES.md recipe 3 shows only the default weights.

    Confirm, per tool:
      Aggrescan 3D - needs a structure; web server or local install, which?
      SoluProt     - web server or local install?
      NetSolP      - which model variant (the paper ships several)?
      ProteinMPNN soluble weights - whether `forge.py schema proteinmpnn` exposes
          a weights/checkpoint argument, else install locally on the H100.
          Check: python3 $F schema proteinmpnn
    Until each is confirmed, produce the numbers outside the pipeline and feed
    them in with --dev-scores.
    """
    raise common.must_confirm(
        "the {0} invocation".format(DEV_SCORES.get(tool, {}).get("tool", tool)),
        "the Adaptyv write-up linked from the task PDF's 'General recommendations', and "
        "`python3 forge.py schema proteinmpnn` for the soluble-weights argument. Wire it into "
        "run_developability() in pipeline/04_score.py. Until then use --dev-scores.")


def parse_dev_scores(path: str) -> dict:
    """Read developability scores into {candidate_id: {score_name: value}}.

    A directory is read as one file per tool, named <tool>.json or <tool>.csv
    where <tool> is a key of DEV_SCORES (aggrescan3d, soluprot, netsolp,
    mpnn_soluble). A single file is read as {candidate_id: {tool: value}} or as
    a CSV whose columns are tool names.
    """
    out: dict = {}

    def merge(cid, tool, value):
        if value in (None, "", "NA", "nan"):
            return
        try:
            out.setdefault(str(cid), {})[tool] = float(value)
        except (TypeError, ValueError):
            pass

    def read_one(fp, tool_hint=None):
        if fp.lower().endswith((".csv", ".tsv")):
            import csv
            delim = "\t" if fp.lower().endswith(".tsv") else ","
            with open(fp, newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh, delimiter=delim):
                    cid = next((row[k] for k in row
                                if str(k).strip().lower() in ("candidate_id", "id", "name") and row[k]), None)
                    if not cid:
                        continue
                    for k, v in row.items():
                        kk = str(k).strip().lower()
                        if kk in DEV_SCORES:
                            merge(cid, kk, v)
                        elif tool_hint and kk in ("value", "score"):
                            merge(cid, tool_hint, v)
            return
        data = common.read_json(fp)
        if isinstance(data, dict):
            for cid, v in data.items():
                if isinstance(v, dict):
                    for k, val in v.items():
                        if str(k).strip().lower() in DEV_SCORES:
                            merge(cid, str(k).strip().lower(), val)
                elif tool_hint:
                    merge(cid, tool_hint, v)

    if os.path.isdir(path):
        for name in sorted(os.listdir(path)):
            stem = os.path.splitext(name)[0].strip().lower()
            read_one(os.path.join(path, name), stem if stem in DEV_SCORES else None)
    else:
        read_one(path)
    return out


# --------------------------------------------------------------------------

def main(argv=None) -> int:
    p = common.base_parser(
        "Stage 04: attach interface scores (min_ipae, iptm, binder_plddt) and "
        "developability scores to each candidate, with provenance per score.",
        epilog="Predict Structure models and template support:\n" +
               "\n".join("  {0:<12} weights: {1:<22} template: {2}".format(
                   k, v["weights"], "yes" if v["template"] else "no")
                   for k, v in PREDICT_MODELS.items()) +
               "\nFor a binder, prefer a template-taking model: ESMFold2 folds the target unguided "
               "(task PDF).\nBoltz2 on Nebius returns no ipTM (RECIPES.md) - do not report one from it.",
    )
    p.add_argument("candidates", help="candidates.jsonl from stage 03")
    p.add_argument("--refold-scores", default=None,
                   help="refold-score output: JSON or CSV keyed by candidate id")
    p.add_argument("--dev-scores", default=None,
                   help="developability scores: a file, or a directory of <tool>.json/<tool>.csv")
    p.add_argument("--predict-model", default="openfold3", choices=sorted(PREDICT_MODELS),
                   help="which Predict Structure model produced the refolds, recorded per score "
                        "(default %(default)s)")
    p.add_argument("--predict-model-version", default=None,
                   help="exact weights string, e.g. 'OpenBind, preview 2'. Defaults to the task "
                        "PDF's value for the chosen model")
    p.add_argument("--refold-seed", type=int, default=None,
                   help="seed used for the refold, recorded per interface score")
    p.add_argument("--run-refold", action="store_true",
                   help="call Foundry refold-prepare/refold-score instead of reading a file "
                        "(raises until the CLI is confirmed on the VM)")
    p.add_argument("--run-developability", action="store_true",
                   help="call the developability tools instead of reading a file "
                        "(raises until confirmed)")
    p.add_argument("--no-liabilities", action="store_true", help="skip local motif counting")
    common.add_io_args(p, out_default=None)
    args = p.parse_args(argv)

    recs = common.read_input_jsonl(
        args.candidates, what="candidates.jsonl",
        produced_by="03_generate.py --from-sequences (--dispatch none writes no candidates)")
    if not recs:
        raise SystemExit("{0} has no candidates".format(args.candidates))

    if args.run_refold:
        foundry_refold_prepare(recs, os.path.dirname(os.path.abspath(args.out)), args.predict_model)
    if args.run_developability:
        run_developability("soluprot", recs, os.path.dirname(os.path.abspath(args.out)))

    refold = parse_refold_scores(args.refold_scores) if args.refold_scores else {}
    dev = parse_dev_scores(args.dev_scores) if args.dev_scores else {}
    version = args.predict_model_version or PREDICT_MODELS[args.predict_model]["weights"]

    missing_refold = 0
    for rec in recs:
        cid = rec["candidate_id"]
        scores = rec.setdefault("scores", {})
        row = refold.get(cid, {})
        if not row:
            missing_refold += 1
        for name, higher in INTERFACE_SCORES.items():
            scores[name] = common.score_entry(
                row.get(name), model=args.predict_model, version=version,
                seed=args.refold_seed, source_file=args.refold_scores,
                higher_is_better=higher,
                note=None if name in row else (
                    "not present in {0}".format(args.refold_scores) if args.refold_scores
                    else "no --refold-scores given; refold not run"))
        for name in OPTIONAL_INTERFACE_SCORES:
            if name in row:
                scores[name] = common.score_entry(
                    row[name], model=args.predict_model, version=version, seed=args.refold_seed,
                    source_file=args.refold_scores, higher_is_better=True,
                    note="ipSAE is in the mentor's step 4 but not in the task PDF's refold-score "
                         "list; confirm where this value came from")

        drow = dev.get(cid, {})
        for name, meta in DEV_SCORES.items():
            scores[name] = common.score_entry(
                drow.get(name), model=meta["tool"], version=None, seed=None,
                source_file=args.dev_scores, higher_is_better=meta["higher_is_better"],
                note=meta["note"] if name in drow else (
                    "not present in {0}".format(args.dev_scores) if args.dev_scores
                    else "no --dev-scores given; " + meta["note"]))

        if not args.no_liabilities:
            rec["liabilities"] = liability_flags(rec)
        rec.setdefault("stage_provenance", []).append(common.provenance(
            "04_score", model=args.predict_model, weights=version, seed=args.refold_seed,
            run_id=args.run_id,
            settings={"refold_scores": args.refold_scores, "dev_scores": args.dev_scores,
                      "liabilities": not args.no_liabilities},
            inputs=[args.candidates, args.refold_scores,
                    args.dev_scores if args.dev_scores and os.path.isfile(args.dev_scores) else None]))

    path = common.write_jsonl(args.out, recs)

    if not args.quiet:
        names = list(INTERFACE_SCORES) + list(DEV_SCORES)
        rows = [[n, sum(1 for r in recs if (r["scores"].get(n) or {}).get("value") is not None),
                 len(recs)] for n in names]
        print(common.table(rows, ["score", "have", "of"]))
        if missing_refold:
            print("warning: {0}/{1} candidate(s) have no refold scores at all".format(missing_refold, len(recs)))
        no_cdrh3 = sum(1 for r in recs if not r.get("cdrh3"))
        if no_cdrh3:
            print("warning: {0}/{1} candidate(s) carry no 'cdrh3', so stage 05's novelty check will "
                  "be indeterminate for them. Set it in stage 03 (--cdrh3 or --jobspec)."
                  .format(no_cdrh3, len(recs)))
        print("wrote " + path)
    return 0


if __name__ == "__main__":
    raise SystemExit(common.cli(main))
