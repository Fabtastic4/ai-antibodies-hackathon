#!/usr/bin/env python3
"""Stage 05 - hard filters first, then ranking, then the submission table.

Order matters and is not negotiable: abguard's hard filters decide what is
submittable at all, and only survivors get ranked. A design that fails a hard
filter "is not submitted" (task PDF). Ranking a rejected design wastes a slot.

HARD FILTERS, verbatim from the task PDF (p3 Figure 2 and p7). Note what runs
FIRST in Figure 2: "Extract antibody sequence - immunum strips tags and linkers",
so every count below is over the stripped sequence, which is not necessarily the
sequence we submit. See common.total_length().
  shared, every design
    * format is VHH, scFv or Fab
    * no unpaired cysteines
    * numbering confidence at least 0.1 (immunum)
    * total length at most 250 amino acids (one scFv/VHH, or VH+VL combined)
  then a type-aware identity comparison picks the track - the track is decided
  for us, never chosen, and a design is never moved between tracks:
    de novo (identity to nearest known antibody under 70%)
      * at least 2 CDRH3 mutations away from trastuzumab
    optimisation (identity 70% or above)
      * CDRH3 identity to trastuzumab under 70%
      * strictly more than 2 point mutations from any provided antibody

abguard IS THE AUTHORITY. This stage shells out to the real CLI when it is
available. The local checks are a PRE-CHECK: they catch the cheap mistakes
before a job runs, they re-implement only what the PDF documents, and they
cannot replace abguard. A check the pre-check cannot decide comes back
"indeterminate", and an indeterminate design never enters the submission table
unless --include-unverified is passed explicitly.

CONSEQUENCE, SO NOBODY IS SURPRISED AT 17:55: the pre-check can only REJECT a
design, never pass one. Unpaired cysteines are indeterminate for every even
count, and numbering confidence needs immunum, which we do not have. So with no
abguard the normal outcome is eligible=0 and a header-only ranked.csv. A
non-empty table needs either --abguard-cmd (the real tool) or
--include-unverified. That direction is deliberate: a local guess must not put a
design in the submission table.

Usage:
  # local pre-check only (no abguard): expect a header-only table
  python3 05_filter_rank.py runs/scored.jsonl -o designs/ranked.csv
  # pre-check plus the unverified designs, ranked, clearly labelled
  python3 05_filter_rank.py runs/scored.jsonl -o designs/ranked.csv --include-unverified
  # the real thing, once `abguard --help` on the VM has told us the invocation
  python3 05_filter_rank.py runs/scored.jsonl -o designs/ranked.csv \\
      --abguard-cmd "abguard check --json" --top 20
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

PASS, FAIL, UNKNOWN = "pass", "fail", "indeterminate"

# Scores the task PDF tells us to rank on for the HER2 exercise: "For the HER2
# exercise the pass column stays empty, so rank on min_ipae, iptm and
# binder_plddt." Equal weights are OUR choice, not the PDF's - change with
# --weight and the choice is recorded in the output.
DEFAULT_WEIGHTS = {"min_ipae": 1.0, "iptm": 1.0, "binder_plddt": 1.0}

# Direction per score. Must agree with 04_score.py and thermostability.py.
HIGHER_IS_BETTER = {
    "min_ipae": False, "iptm": True, "binder_plddt": True, "ipsae": True,
    "aggrescan3d": False, "soluprot": True, "netsolp": True, "mpnn_soluble": True,
    # thermostability axis (pipeline/thermostability.py, GitHub issue #10). Only
    # the two terms we compute ourselves have a direction our sources settle:
    # both are distances from a stated reference sequence, so the direction is
    # true by construction rather than by assumption.
    "framework_mutations": False, "framework_identity": True,
    "esm2_pll_per_residue": True,
}
DEV_COLUMNS = ("aggrescan3d", "soluprot", "netsolp", "mpnn_soluble")
STABILITY_COLUMNS = ("framework_mutations", "framework_identity",
                     "vh_vl_interface_ddg", "esm2_pll_per_residue", "esm2_variant_score")

# Scores we can RECORD but must not RANK on, because our sources do not state
# which direction is better. Ranking on a guessed sign silently inverts the
# list, and only the top few designs are ever tested, so this is the most
# expensive kind of mistake available here. Move a score into HIGHER_IS_BETTER
# once someone confirms its convention - and say where they confirmed it.
DIRECTION_UNCONFIRMED = {
    "vh_vl_interface_ddg":
        "stab-ddg's reference does not state whether a stabilising mutation is "
        "negative or positive. Confirm with `python3 forge.py schema stab-ddg` or a "
        "known-stabilising control, then add it to HIGHER_IS_BETTER.",
    "esm2_variant_score":
        "the sign convention of esm2-650m `score-variants` is not documented in our "
        "sources. Confirm with `python3 forge.py schema esm2-650m`, then add it to "
        "HIGHER_IS_BETTER.",
}


def check(status: str, detail: str, *, source: str) -> dict:
    return {"status": status, "detail": detail, "source": source}


# The ONLY verdict words we accept from abguard. Task PDF p3 Figure 2 is the one
# source that names outcomes: "Eligible for submission", "fails", "Rejected". A
# boolean true/false is also accepted, because parse_abguard_output() maps a bool
# onto "pass"/"fail" before we see it.
# Anything else - including "ok" and the string "true" - falls to needs_abguard
# instead of being guessed at. Words invented here once let a failed stub run put
# two designs in the submission table.
# TODO: confirm abguard's real field name and verdict vocabulary with
# `abguard --help` on the VM, then widen these two sets and say so here.
ABGUARD_PASS = ("pass", "eligible")
ABGUARD_FAIL = ("fail", "fails", "reject", "rejected", "false")


# --------------------------------------------------------------------------
# the real abguard
# --------------------------------------------------------------------------

def abguard_available(cmd: str | None) -> bool:
    if not cmd:
        return False
    return shutil.which(shlex.split(cmd)[0]) is not None


def write_abguard_fasta(recs: list, path: str) -> str:
    """One FASTA for abguard. Paired formats get two headers per design,
    `<id>|H` and `<id>|L`; an scFv is one chain and so one header.

    TODO: confirm abguard's expected input - FASTA vs CSV, whether paired chains
    go in one record separated by a linker or in two records, and what header
    form it keys results on. `abguard --help` on the VM answers this.

    An empty sequence is never written: abguard would be asked to judge nothing
    and whatever it said back would be meaningless. It raises instead, naming the
    candidate, because the only way to get here is a candidate record whose
    chains do not match its format (stage 03 rejects those on both paths).
    """
    lines = []
    for rec in recs:
        chains = rec.get("chains") or {}
        cid = rec["candidate_id"]

        def emit(label, seq, _cid=cid):
            if not seq:
                raise SystemExit(
                    "{0}: empty sequence for chain {1!r} (format {2}). A candidate record with "
                    "no sequence cannot be checked by abguard - fix it in the input to stage 03."
                    .format(_cid, label, rec.get("format")))
            header = _cid if label == "-" else "{0}|{1}".format(_cid, label)
            lines.append(">{0}\n{1}".format(header, seq))

        if rec["format"] == "scFv":
            emit("-", (chains.get("H") or "") + (chains.get("linker") or "") + (chains.get("L") or ""))
        elif rec["format"] == "Fab":
            for c in ("H", "L"):
                emit(c, chains.get(c))
        else:
            emit("-", chains.get("H"))
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def run_abguard(cmd: str, fasta: str, work_dir: str) -> dict:
    """Run the organisers' abguard CLI and keep everything it said.

    Flags are NOT invented here. `cmd` is whatever the operator passes to
    --abguard-cmd, and the FASTA path is appended as the single positional
    argument. If the real CLI needs other flags, put them in --abguard-cmd:
        --abguard-cmd "abguard check --input-format fasta --json"

    TODO: confirm on the VM, then set the default in this file:
        abguard --help
        abguard --version
    What must be confirmed: the subcommand, the input format, the output format,
    and the field names for the per-design verdict and the assigned track.

    A NONZERO EXIT ABORTS THE STAGE. We do not know abguard's exit-code
    convention, so a nonzero exit means its output cannot be trusted - and
    output from a failed run has already put designs in the submission table
    once. Fail closed: the message carries the returncode and the first stderr
    line, and tells the operator how to proceed deliberately (--no-abguard, on
    the local pre-check alone, which can reject but never promote).

    Returns the raw result. Parsing is deliberately separate
    (parse_abguard_output) so an unparsed output is visible rather than silently
    treated as a pass.
    """
    argv = shlex.split(cmd) + [fasta]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True)
    except OSError as exc:
        raise SystemExit("cannot run abguard ({0}): {1}\n  Fix --abguard-cmd, or pass "
                         "--no-abguard to run on the local pre-check alone.".format(
                             shlex.join(argv), exc)) from exc
    raw = {"argv": argv, "returncode": proc.returncode,
           "stdout": proc.stdout, "stderr": proc.stderr[-8000:]}
    raw_path = common.write_json(os.path.join(work_dir, "abguard_raw.json"), raw)
    if proc.returncode != 0:
        first = next((ln for ln in (proc.stderr or "").splitlines() if ln.strip()), "")
        raise SystemExit(
            "abguard exited {0}; its verdicts are NOT used and nothing was ranked.\n"
            "  command: {1}\n  stderr: {2}\n  full output: {3}\n"
            "  Fix the command (`abguard --help` on the VM), or re-run with --no-abguard to "
            "use the local pre-check alone - it can reject a design but never pass one, so "
            "the table will be empty unless you also pass --include-unverified.".format(
                proc.returncode, shlex.join(argv), first or "(empty)", raw_path))
    return raw


def parse_abguard_output(raw: dict) -> dict:
    """{candidate_id: {verdict, track, reasons, raw}} from abguard's output.

    Handles a JSON object keyed by id and a JSON list of per-design objects,
    because those are the two shapes worth guessing at cheaply. Anything else
    returns {} and the caller marks every design "abguard output not parsed" -
    which blocks the submission table rather than faking a pass.

    The verdict string is lower-cased and handed to main() unchanged. main()
    accepts only the vocabulary our sources use (see ABGUARD_PASS /
    ABGUARD_FAIL); anything else falls to needs_abguard.
    """
    import json
    text = (raw.get("stdout") or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    id_keys = ("candidate_id", "id", "design", "design_id", "name")

    def one(row: dict) -> dict:
        verdict = None
        for k in ("verdict", "status", "result", "eligible", "passed", "pass"):
            if k in row:
                verdict = row[k]
                break
        if isinstance(verdict, bool):
            verdict = PASS if verdict else FAIL
        return {"verdict": str(verdict).lower() if verdict is not None else UNKNOWN,
                "track": row.get("track") or row.get("challenge") or row.get("assigned_track"),
                "reasons": row.get("reasons") or row.get("failures") or row.get("errors") or [],
                "raw": row}

    if isinstance(data, list):
        out = {}
        for row in data:
            if not isinstance(row, dict):
                continue
            cid = next((row[k] for k in row if str(k).lower() in id_keys and row[k]), None)
            if cid:
                out[str(cid)] = one(row)
        return out
    if isinstance(data, dict):
        inner = data.get("designs") or data.get("results")
        if isinstance(inner, list):
            return parse_abguard_output({"stdout": __import__("json").dumps(inner)})
        return {str(cid): one(v) for cid, v in data.items() if isinstance(v, dict)}
    return {}


# --------------------------------------------------------------------------
# local pre-check (NOT abguard)
# --------------------------------------------------------------------------

def precheck(rec: dict, refs: dict) -> dict:
    """Re-implement the documented hard checks locally. Labelled as a pre-check
    everywhere it is reported. Every check returns pass / fail / indeterminate,
    and indeterminate is a real answer here, not a soft pass."""
    src = "local pre-check (not abguard)"
    out = {}

    # 1. format
    fmt = rec.get("format")
    out["format"] = check(
        PASS if fmt in common.VALID_FORMATS else FAIL,
        "format={0}; allowed: {1}".format(fmt, ", ".join(common.VALID_FORMATS)), source=src)

    # 2. total length. Two counts, because the PDF gives two counting rules:
    # p7 counts the whole submitted chain(s); p3 Figure 2 strips tags and linkers
    # first. We only decide where both readings agree. See common.total_length().
    lim = common.HARD_LIMITS["max_total_length_aa"]
    rep = common.length_report(rec)
    detail = "{0} aa as submitted, {1} aa with linker/tag stripped, limit {2}".format(
        rep["submitted"], rep["stripped"], lim)
    if rep["carries_linker_or_tag"]:
        detail += " (linker {0} aa, tags {1}; p3 Figure 2 says immunum strips them, p7 counts the " \
                  "whole chain - unresolved)".format(
                      rep["linker_aa"], ", ".join("{0}:{1}aa".format(t["motif"], t["length"])
                                                  for t in rep["tags"]) or "none")
    if rep["submitted"] <= lim:
        out["total_length"] = check(PASS, detail + ": under the limit on both counts", source=src)
    elif rep["stripped"] > lim:
        out["total_length"] = check(FAIL, detail + ": over the limit on both counts", source=src)
    else:
        out["total_length"] = check(
            UNKNOWN, detail + ": the two counting rules disagree for this design, so immunum/"
                              "abguard decides. Not rejected here", source=src)

    # 3. unpaired cysteines. An odd total cannot be fully paired, so odd is a
    # real fail - UNLESS the count includes residues immunum would have stripped,
    # in which case our parity is not the parity abguard computes. An even total
    # is necessary but not sufficient - two cysteines far apart in space are both
    # unpaired - so even is indeterminate, and abguard decides.
    ncys = common.count_cysteines(rec)
    cys_note = "count excludes the scFv linker (immunum strips it, task PDF p3 Figure 2)"
    if ncys % 2 and not rep["tags"]:
        out["unpaired_cysteines"] = check(
            FAIL, "{0} cysteines: odd count, at least one is unpaired ({1}; no tag detected)".format(
                ncys, cys_note), source=src)
    elif ncys % 2:
        out["unpaired_cysteines"] = check(
            UNKNOWN, "{0} cysteines: odd, but this design carries a detected tag ({1}) that immunum "
                     "strips before counting, so the parity abguard sees may differ. Not rejected "
                     "here".format(ncys, ", ".join(t["motif"] for t in rep["tags"])), source=src)
    else:
        out["unpaired_cysteines"] = check(
            UNKNOWN, "{0} cysteines: even, which is necessary but not sufficient. Pairing needs a "
                     "structure or immunum; abguard decides ({1})".format(ncys, cys_note), source=src)

    # 4. numbering confidence - immunum only. We do not have it.
    conf = rec.get("numbering_confidence")
    if conf is None:
        conf = ((rec.get("scores") or {}).get("numbering_confidence") or {}).get("value")
    if conf is None:
        out["numbering_confidence"] = check(
            UNKNOWN, "needs immunum (abguard's own numbering). ANARCII's score is a different "
                     "number and is not substituted here. Threshold: >= {0}".format(
                         common.HARD_LIMITS["min_numbering_confidence"]), source=src)
    else:
        ok = float(conf) >= common.HARD_LIMITS["min_numbering_confidence"]
        out["numbering_confidence"] = check(
            PASS if ok else FAIL, "{0} vs threshold {1}".format(
                conf, common.HARD_LIMITS["min_numbering_confidence"]), source=src)

    # 5. novelty. Needs the reference antibodies, which this repo does not ship:
    # see common.load_reference_set().
    tras = refs.get("trastuzumab") or {}
    provided = refs.get("provided") or []
    known = refs.get("known") or []
    cdrh3 = (rec.get("cdrh3") or ((rec.get("regions") or {}).get("CDR3")))
    heavy = (rec.get("chains") or {}).get("H")

    if not refs:
        msg = ("no reference antibodies loaded ({0} absent). Novelty cannot be pre-checked; "
               "run abguard".format(common.DEFAULT_REFERENCE_PATH))
        out["track_assignment"] = check(UNKNOWN, msg, source=src)
        out["novelty"] = check(UNKNOWN, msg, source=src)
        return out

    # 5a. track: identity to the nearest known antibody
    if known and heavy:
        best = max((common.identity(heavy, k.get("H") or k.get("sequence") or "") for k in known),
                   key=lambda r: (r["identity"] or 0))
        ident = best["identity"]
        track = "de_novo" if ident < common.HARD_LIMITS["max_identity_known_denovo"] else "optimisation"
        out["track_assignment"] = check(
            PASS, "nearest known identity {0:.3f} -> {1} track (pre-check only; abguard's "
                  "type-aware comparison is the authority and never reclassifies)".format(ident, track),
            source=src)
    else:
        track = None
        out["track_assignment"] = check(
            UNKNOWN, "reference set has no 'known' antibody list, so the track cannot be "
                     "pre-assigned", source=src)

    # 5b. the track-specific extra check
    if not cdrh3:
        out["novelty"] = check(
            UNKNOWN, "candidate record carries no CDRH3, so neither track's extra check can run. "
                     "Set it in stage 03: --cdrh3 <loop>, a 'cdrh3' field in the input JSONL, or "
                     "--jobspec jobs/jobspec.json (which carries the parent loop from stage 02)",
            source=src)
        return out
    ref_cdrh3 = tras.get("cdrh3")
    if not ref_cdrh3:
        out["novelty"] = check(UNKNOWN, "reference set has no trastuzumab CDRH3", source=src)
        return out

    if track == "de_novo":
        mut = common.mutation_count(cdrh3, ref_cdrh3)
        need = common.HARD_LIMITS["min_cdrh3_mutations_denovo"]
        out["novelty"] = check(
            PASS if mut["mutations"] >= need else FAIL,
            "de novo: {0} CDRH3 mutation(s) from trastuzumab, need >= {1} ({2})".format(
                mut["mutations"], need, mut["definition"]), source=src)
    elif track == "optimisation":
        ident = common.identity(cdrh3, ref_cdrh3)
        lim = common.HARD_LIMITS["max_cdrh3_identity_trastuzumab_opt"]
        parts, status = [], PASS
        if ident["identity"] is None or ident["identity"] >= lim:
            status = FAIL
        parts.append("CDRH3 identity to trastuzumab {0} vs limit < {1}".format(ident["identity"], lim))
        if provided:
            query = heavy or cdrh3
            compared = "full heavy chain" if heavy else "CDRH3 (no heavy chain on the record)"
            muts = [common.mutation_count(query, pv.get("H") or pv.get("sequence") or "")
                    for pv in provided]
            need = common.HARD_LIMITS["min_point_mutations_opt"]
            best = min(muts, key=lambda m: m["mutations"]) if muts else None
            closest = best["mutations"] if best else None
            if closest is None or closest < need:
                status = FAIL
            parts.append("{0} point mutation(s) from the nearest provided antibody, need >= {1}; "
                         "compared {2} against the provided antibody's H chain ({3}) "
                         "(source contradiction: PDF p2 says 'at least 2', p3/p7 say 'strictly more "
                         "than 2'; we take the strict reading)".format(
                             closest, need, compared,
                             best["definition"] if best else "no comparison made"))
        else:
            status = UNKNOWN if status == PASS else status
            parts.append("reference set has no 'provided' antibodies, so the point-mutation check "
                         "cannot run")
        out["novelty"] = check(status, "optimisation: " + "; ".join(parts), source=src)
    else:
        out["novelty"] = check(UNKNOWN, "track unknown, so the extra check cannot be selected", source=src)
    return out


def roll_up(checks: dict) -> tuple:
    """(verdict, reasons). fail beats indeterminate beats pass."""
    fails = [k for k, v in checks.items() if v["status"] == FAIL]
    unknowns = [k for k, v in checks.items() if v["status"] == UNKNOWN]
    if fails:
        return "reject", ["{0}: {1}".format(k, checks[k]["detail"]) for k in fails]
    if unknowns:
        return "needs_abguard", ["{0}: {1}".format(k, checks[k]["detail"]) for k in unknowns]
    return "eligible", []


# --------------------------------------------------------------------------
# ranking
# --------------------------------------------------------------------------

def score_value(rec: dict, name: str):
    entry = (rec.get("scores") or {}).get(name) or {}
    return entry.get("value")


def rank_candidates(recs: list, weights: dict) -> list:
    """Min-max normalise each weighted score across the candidate set, flip the
    lower-is-better ones, and take the weighted mean.

    Deliberate choices, all reversible from the CLI:
      * normalisation is over THIS set, so a rank_score is not comparable
        between runs. It orders designs, it is not a quantity.
      * a candidate missing any weighted score gets rank_score None and sorts
        after every complete candidate, flagged `incomplete_scores`. It is never
        imputed - an imputed score would be a fabricated number.
      * developability scores are reported as columns and used only as a
        tiebreak, because the task PDF gives no threshold for any of them.
    """
    used = {k: w for k, w in weights.items() if w}
    # Defence in depth: the CLI already refuses these, but rank_candidates is
    # importable and HIGHER_IS_BETTER.get(name, True) would silently treat an
    # unknown direction as "higher is better" and order the list backwards.
    guessed = sorted(k for k in used if k in DIRECTION_UNCONFIRMED)
    if guessed:
        raise ValueError(
            "cannot rank on {0}: direction unconfirmed, so the ordering would be a "
            "guess. See DIRECTION_UNCONFIRMED in this file.".format(", ".join(guessed)))
    bad_w = sorted(k for k, w in used.items()
                   if w != w or w in (float("inf"), float("-inf")) or w < 0)
    if bad_w:
        raise ValueError(
            "weights must be finite and >= 0; got {0}. sum(w) is the divisor in this "
            "function, so a negative weight inverts every other term.".format(
                ", ".join("{0}={1}".format(k, used[k]) for k in bad_w)))
    ranges = {}
    for name in used:
        vals = [v for v in (score_value(r, name) for r in recs) if v is not None]
        ranges[name] = (min(vals), max(vals)) if vals else (None, None)

    for rec in recs:
        parts, missing = [], []
        for name, w in used.items():
            v = score_value(rec, name)
            if v is None:
                missing.append(name)
                continue
            lo, hi = ranges[name]
            norm = 0.5 if hi == lo else (v - lo) / (hi - lo)
            if not HIGHER_IS_BETTER.get(name, True):
                norm = 1.0 - norm
            parts.append((w, norm))
        rec["_missing_scores"] = missing
        if missing or not parts:
            rec["_rank_score"] = None
        else:
            rec["_rank_score"] = round(sum(w * n for w, n in parts) / sum(w for w, _ in parts), 6)
        devs = [score_value(rec, d) for d in DEV_COLUMNS]
        rec["_dev_available"] = sum(1 for d in devs if d is not None)

    recs.sort(key=lambda r: (r["_rank_score"] is None,
                             -(r["_rank_score"] or 0.0),
                             -r["_dev_available"],
                             r["candidate_id"]))
    for i, rec in enumerate(recs, 1):
        rec["_rank"] = i
    return recs


# --------------------------------------------------------------------------

COLUMNS = [
    "rank", "candidate_id", "format", "track_intent", "abguard_track", "verdict",
    "filter_source", "rank_score", "min_ipae", "iptm", "binder_plddt",
    "aggrescan3d", "soluprot", "netsolp", "mpnn_soluble",
    "framework_mutations", "framework_identity", "vh_vl_interface_ddg",
    "esm2_pll_per_residue", "esm2_variant_score",
    "total_length_aa", "n_cysteines", "missing_scores",
    "generator", "model_image", "weights", "seed", "pipeline_version", "generated_at",
]


def row_for(rec: dict, verdict: str, filter_source: str, abguard_track, reasons) -> dict:
    prov = rec.get("provenance") or {}
    row = {
        "rank": rec.get("_rank"),
        "candidate_id": rec["candidate_id"],
        "format": rec.get("format"),
        "track_intent": rec.get("track_intent"),
        "abguard_track": abguard_track,
        "verdict": verdict,
        "filter_source": filter_source,
        "rank_score": rec.get("_rank_score"),
        "total_length_aa": common.total_length(rec),
        "n_cysteines": common.count_cysteines(rec),
        "missing_scores": ",".join(rec.get("_missing_scores") or []),
        "generator": prov.get("model"),
        "model_image": prov.get("model_image"),
        "weights": prov.get("weights"),
        "seed": prov.get("seed"),
        "pipeline_version": prov.get("pipeline_version") or common.PIPELINE_VERSION,
        "generated_at": prov.get("timestamp"),
        "reasons": "; ".join(reasons or []),
    }
    for name in ("min_ipae", "iptm", "binder_plddt") + DEV_COLUMNS + STABILITY_COLUMNS:
        row[name] = score_value(rec, name)
    return row


def main(argv=None) -> int:
    p = common.base_parser(
        "Stage 05: apply abguard's hard filters first, then rank the survivors, then "
        "emit the ranked submission table.",
        epilog="The submission is a ranked list of up to {0} designs (task PDF: 16 if we win, "
               "plus 4 against duplication between teams).\nTeams are ranked by number of S-tier "
               "designs - all three properties improved - so a design we only half believe in is "
               "worth less than the slot it takes.".format(common.MAX_SUBMISSION),
    )
    p.add_argument("scored", help="scored.jsonl from stage 04")
    p.add_argument("--top", type=int, default=common.MAX_SUBMISSION,
                   help="rows in the submission table (default %(default)s)")
    p.add_argument("--abguard-cmd", default=None,
                   help="the real abguard command, INCLUDING its subcommand and flags - none of "
                        'them are guessed: --abguard-cmd "abguard check --json". Unset by default, '
                        "because the bare word `abguard` is not a confirmed invocation; unset means "
                        "the local pre-check only")
    p.add_argument("--no-abguard", action="store_true",
                   help="never run abguard (the default behaviour when --abguard-cmd is unset)")
    p.add_argument("--abguard-verdicts", default=None,
                   help="pre-parsed abguard output: {candidate_id: {verdict, track, reasons}}")
    p.add_argument("--reference", default=None,
                   help="reference antibodies for the local novelty pre-check (default: {0})".format(
                       common.DEFAULT_REFERENCE_PATH))
    p.add_argument("--weight", action="append", default=[], metavar="NAME=W",
                   help="ranking weight, repeatable. Default: " +
                        ", ".join("{0}={1}".format(k, v) for k, v in DEFAULT_WEIGHTS.items()))
    p.add_argument("--include-unverified", action="store_true",
                   help="let designs whose hard checks are indeterminate into the table. Off by "
                        "default: an unverified design can fail abguard at submission time")
    p.add_argument("--rejected", default=None, help="CSV of rejected designs (default: next to --out)")
    p.add_argument("--survivors-jsonl", default=None,
                   help="full records of the ranked survivors (default: next to --out)")
    common.add_io_args(p, out_default=None)
    args = p.parse_args(argv)

    recs = common.read_input_jsonl(
        args.scored, what="scored.jsonl", produced_by="04_score.py")
    if not recs:
        raise SystemExit("{0} has no candidates".format(args.scored))

    weights = dict(DEFAULT_WEIGHTS)
    for item in args.weight:
        if "=" not in item:
            raise SystemExit("--weight takes NAME=VALUE, got {0!r}".format(item))
        k, v = item.split("=", 1)
        k = k.strip()
        if k in DIRECTION_UNCONFIRMED:
            raise SystemExit(
                "refusing to rank on {0!r}: its direction is unconfirmed.\n  {1}\n"
                "  It is still recorded as a column in the output.".format(
                    k, DIRECTION_UNCONFIRMED[k]))
        if k not in HIGHER_IS_BETTER:
            raise SystemExit("unknown score {0!r}; known: {1}".format(k, ", ".join(sorted(HIGHER_IS_BETTER))))
        try:
            w = float(v)
        except ValueError:
            raise SystemExit("--weight {0}: {1!r} is not a number".format(k, v)) from None
        # A negative weight is not "deprioritise": rank_candidates divides by
        # sum(w), so one large enough to turn that denominator negative flips the
        # sign of every other term and inverts the submission order silently.
        # Direction belongs in HIGHER_IS_BETTER, never in a weight's sign.
        if w != w or w in (float("inf"), float("-inf")) or w < 0:
            raise SystemExit(
                "--weight {0}={1}: weights must be finite and >= 0. To flip a score's "
                "direction, change HIGHER_IS_BETTER; a negative weight would invert the "
                "whole ranking, not just this term.".format(k, v))
        weights[k] = w

    out_dir = os.path.dirname(os.path.abspath(args.out)) or "."
    work_dir = os.path.join(out_dir, "filter_work")
    os.makedirs(work_dir, exist_ok=True)

    # ---- hard filters, abguard first
    verdicts, filter_source = {}, None
    if args.abguard_verdicts:
        verdicts = common.read_input_json(
            args.abguard_verdicts, what="abguard verdicts, {candidate_id: {verdict, track, reasons}}",
            produced_by="the real abguard, parsed by hand")
        filter_source = "abguard (verdicts file: {0})".format(args.abguard_verdicts)
    elif not args.no_abguard and abguard_available(args.abguard_cmd):
        fasta = write_abguard_fasta(recs, os.path.join(work_dir, "abguard_input.fasta"))
        raw = run_abguard(args.abguard_cmd, fasta, work_dir)
        verdicts = parse_abguard_output(raw)
        if verdicts:
            filter_source = "abguard ({0})".format(args.abguard_cmd)
        else:
            filter_source = None
            common.say(args.quiet, "abguard ran but its output could not be parsed; see "
                                   "{0}/abguard_raw.json. Falling back to the local pre-check and "
                                   "treating every design as unverified.".format(work_dir))

    refs = common.load_reference_set(args.reference)
    if not filter_source:
        filter_source = "local pre-check (NOT abguard; does not replace it)"
        if not args.quiet:
            if args.no_abguard:
                print("abguard skipped by --no-abguard.")
            elif not args.abguard_cmd:
                print("no --abguard-cmd given, so abguard did not run; using the local pre-check. "
                      "Confirm the real invocation on the team VM (`abguard --help`) and pass it, "
                      'e.g. --abguard-cmd "abguard check --json".')
            elif not abguard_available(args.abguard_cmd):
                print("abguard not on PATH ({0!r}); using the local pre-check. Run the real tool on "
                      "the team VM before submitting - `abguard --help` first.".format(args.abguard_cmd))
            if not refs:
                print("no reference antibodies at {0}; every novelty check is indeterminate."
                      .format(args.reference or common.DEFAULT_REFERENCE_PATH))

    survivors, rejected, unverified = [], [], []
    for rec in recs:
        checks = precheck(rec, refs)
        verdict, reasons = roll_up(checks)
        abg = verdicts.get(rec["candidate_id"])
        if abg:
            v = str(abg.get("verdict", "")).lower()
            if v in ABGUARD_PASS:
                verdict, reasons = "eligible", []
            elif v in ABGUARD_FAIL:
                verdict, reasons = "reject", list(abg.get("reasons") or ["abguard: rejected"])
            else:
                verdict, reasons = "needs_abguard", ["abguard verdict not understood: {0!r}".format(
                    abg.get("verdict"))]
        rec["checks"] = {"source": filter_source, "abguard": abg, "local_precheck": checks,
                         "verdict": verdict, "reasons": reasons}
        rec["_abguard_track"] = (abg or {}).get("track")
        if verdict == "reject":
            rejected.append(rec)
        elif verdict == "eligible":
            survivors.append(rec)
        else:
            unverified.append(rec)

    pool = survivors + (unverified if args.include_unverified else [])
    rank_candidates(pool, weights)

    rows = [row_for(r, r["checks"]["verdict"], filter_source, r.get("_abguard_track"),
                    r["checks"]["reasons"]) for r in pool[:args.top]]
    ranked_path = common.write_csv(args.out, rows, COLUMNS)

    rej_path = args.rejected or os.path.join(out_dir, "rejected.csv")
    rej_rows = [row_for(r, r["checks"]["verdict"], filter_source, r.get("_abguard_track"),
                        r["checks"]["reasons"]) for r in rejected + ([] if args.include_unverified else unverified)]
    common.write_csv(rej_path, rej_rows, COLUMNS + ["reasons"])

    surv_path = args.survivors_jsonl or os.path.join(out_dir, "ranked.jsonl")
    for r in pool:
        r.pop("_dev_available", None)
    common.write_jsonl(surv_path, pool[:args.top])

    manifest = {
        "schema": "fab4.submission_manifest/v1",
        "input": common.file_ref(args.scored),
        "filter_source": filter_source,
        "abguard_cmd": None if args.no_abguard else args.abguard_cmd,
        "hard_limits_applied": common.HARD_LIMITS,
        "ranking_weights": weights,
        "ranking_note": "min-max normalised within this candidate set; equal weights are a team "
                        "choice, not from the task description. rank_score orders designs and is "
                        "not a quantity.",
        "counts": {"input": len(recs), "eligible": len(survivors), "needs_abguard": len(unverified),
                   "rejected": len(rejected), "in_table": len(rows)},
        "include_unverified": args.include_unverified,
        "outputs": {"ranked": ranked_path, "rejected": os.path.abspath(rej_path),
                    "survivors_jsonl": os.path.abspath(surv_path)},
        "provenance": common.provenance("05_filter_rank", run_id=args.run_id,
                                        settings={"top": args.top, "weights": weights},
                                        inputs=[args.scored, args.abguard_verdicts]),
    }
    man_path = common.write_json(os.path.join(out_dir, "submission_manifest.json"), manifest)

    if not args.quiet:
        print(common.table(
            [["input", len(recs)], ["eligible", len(survivors)], ["needs_abguard", len(unverified)],
             ["rejected", len(rejected)], ["in table", len(rows)]], ["bucket", "n"]))
        print("hard filters: " + filter_source)
        if unverified and not args.include_unverified:
            print("{0} design(s) held back as unverified. Run the real abguard, or pass "
                  "--include-unverified and accept the risk.".format(len(unverified)))
        if args.include_unverified and unverified:
            print("ranked.csv holds {0} design(s) with verdict needs_abguard: the local pre-check "
                  "could not pass them and --include-unverified overrode that. Do not submit them "
                  "without running the real abguard.".format(len(unverified)))
        if not verdicts and not args.include_unverified:
            print("NOTE: the local pre-check can only REJECT a design, never pass one - unpaired "
                  "cysteines stay indeterminate for any even count and numbering confidence needs "
                  "immunum, which we do not have. So eligible=0 is the normal result here and "
                  "ranked.csv is header-only. A non-empty ranked.csv needs either the real abguard "
                  "(--abguard-cmd) or --include-unverified.")
        # Count over the POOL, not the truncated table: a design whose score was
        # missing sorts last, so it is the first to fall past --top and would
        # never be counted here. Silence then looks like "everything scored".
        incomplete = sum(1 for r in pool if r.get("_rank_score") is None)
        if incomplete:
            which = sorted({s for r in pool if r.get("_rank_score") is None
                            for s in (r.get("_missing_scores") or [])})
            dropped = sum(1 for r in pool[args.top:] if r.get("_rank_score") is None)
            print("{0} candidate(s) have no rank_score because a weighted score is missing"
                  "{1}; they sort last and are not imputed.{2}".format(
                      incomplete,
                      " (" + ", ".join(which) + ")" if which else "",
                      " {0} of them fell past --top {1} and are NOT in the table.".format(
                          dropped, args.top) if dropped else ""))
            # A weighted term that is structurally null for one whole track
            # removes that track from the submission without failing anything.
            by_track: dict = {}
            for r in pool:
                by_track.setdefault(r.get("track_intent") or "unknown", []).append(r)
            for track, recs_t in sorted(by_track.items()):
                if not recs_t or any(r.get("_rank_score") is not None for r in recs_t):
                    continue
                # Only worth saying when the nullness is TRACK-SPECIFIC. If no
                # candidate anywhere scored, the count above already said so and
                # a per-track line is noise.
                others_scored = any(r.get("_rank_score") is not None
                                    for t, rs in by_track.items() if t != track for r in rs)
                if others_scored:
                    print("  WARNING: every {0} candidate ({1}) lacks a weighted score while "
                          "other tracks have one, so this whole track sorts last - possibly "
                          "because a weighted term only the other track can produce. Rank "
                          "within track instead.".format(track, len(recs_t)))
        print("wrote " + ranked_path)
        print("wrote " + os.path.abspath(rej_path))
        print("wrote " + man_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(common.cli(main))
