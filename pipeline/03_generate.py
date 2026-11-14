#!/usr/bin/env python3
"""Stage 03 - build generator inputs, dispatch, and emit candidate records.

Mentor Lluis Artus, step 3: "Create the input for either RFD4-Proteina or
Bindcraft".

Three dispatch modes, in order of how much we can stand behind them:

  --dispatch none      Write the job spec and the exact command to run, emit
                       nothing else. Always works, no credentials needed.
  --dispatch forge     Nebius Scientific AI, via forge.py. Call shape verified
                       in Files from slack/.../RECIPES.md recipe 6. NOTE: the
                       hosted `rfd4-proteina` is the GENERAL model - RECIPES.md
                       says in bold "The output is a general protein binder, not
                       a VHH", and it has no antibody prior. The per-track HER2
                       weights are an Apheris Foundry thing, not a Nebius thing.
  --dispatch foundry   Apheris Foundry on the team VM, the primary path, because
                       it is the only place the HER2-fine-tuned weights live.
                       Flags NOT verified -> raises ConfirmOnVM with what to run.

Designs produced anywhere else (AntiFold on Nebius, Foundry run by hand, a
teammate's notebook) come in through --from-sequences, which is also how the
skeleton runs end to end on stub data.

Usage:
  python3 03_generate.py --interface runs/interface.json --target-cif data/target.cif \\
      --track optimisation --weights her2-2026-11-07 --sequence-tsr-k 2 \\
      --num-designs 64 --seed 42 --job-dir runs/jobs -o runs/candidates.jsonl

  python3 03_generate.py --from-sequences designs.fasta --format VHH \\
      --generator antifold --weights antifold-hosted --seed 42 \\
      --jobspec runs/jobs/jobspec.json -o runs/candidates.jsonl

--dispatch none writes NO candidate file - no designs exist yet - so it is the
first of two calls, not one step of a five-command run:
  03 --dispatch none ... -o runs/candidates.jsonl    # job spec + commands only
  <run the generator>
  03 --from-sequences <designs> --jobspec runs/jobs/jobspec.json -o runs/candidates.jsonl
Pass --jobspec (or --cdrh3) on the second call: stage 05's novelty check reads
rec['cdrh3'] and is the only hard filter that decides the track.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

# RFD4-Proteina weights available in Apheris Foundry.
# Source: task PDF p5, "Pick the model by choosing its image", plus the
# measured table on p5-p6. The percentages are the organisers' own numbers for
# the trastuzumab CDRH3 task - do not round them, do not reuse them as our own
# results.
#
#  weight                 | known binders | pass novelty filter | interface error (A)
#  antibody-2026-10-30    |      0%       |        100%         |        8.2
#  her2-2026-11-07 cons.  |     21%       |          0%         |        9.4
#  her2-2026-11-07 bal.   |     21%       |          6%         |        9.1
#  her2-2026-11-07 expl.  |      0.3%     |         74%         |        9.1
#  her2-novel-2026-11-09  |      4%       |         86%         |        6.8
#
# "A known binder fails the novelty filter, so filter designs before ranking
# them." (task PDF p6)
WEIGHTS = {
    "release-2026-10-19": {
        "what": "NVIDIA's general RFD4-Proteina model",
        "use_for": "general proteins and miniproteins",
        "redesigns_cdrh3_only": False,
    },
    "antibody-2026-10-30": {
        "what": "NVIDIA's antibody model",
        "use_for": "design or redesign CDRs on a fixed antibody framework; the only "
                   "listed weight that can change CDRs other than CDRH3",
        "redesigns_cdrh3_only": False,
        "measured": {"known_binders": 0.0, "pass_novelty": 1.00, "interface_error_A": 8.2},
    },
    "her2-2026-11-07": {
        "what": "the antibody model, fine-tuned by Apheris on HER2 binders from the "
                "trastuzumab FACS screen",
        "use_for": "redesign trastuzumab's CDRH3; --sequence-tsr-k 2 (balanced) or 1 "
                   "(exploratory) for more varied loops",
        "redesigns_cdrh3_only": True,
        "measured": {
            "conservative": {"known_binders": 0.21, "pass_novelty": 0.00, "interface_error_A": 9.4},
            "balanced": {"known_binders": 0.21, "pass_novelty": 0.06, "interface_error_A": 9.1},
            "exploratory": {"known_binders": 0.003, "pass_novelty": 0.74, "interface_error_A": 9.1},
        },
    },
    "her2-novel-2026-11-09": {
        "what": "the antibody model, trained by Apheris on pairs of high and low binders "
                "from the same screen",
        "use_for": "mostly new CDRH3 loops with the most confident predicted fit to HER2",
        "redesigns_cdrh3_only": True,
        "measured": {"known_binders": 0.04, "pass_novelty": 0.86, "interface_error_A": 6.8},
    },
}

# --sequence-tsr-k settings named in the task PDF. "conservative" is the default
# the PDF implies by contrast but does not give a number for.
TSR_K = {2: "balanced", 1: "exploratory"}

# RFD4-Proteina tasks in Foundry. Source: task PDF p5.
FOUNDRY_TASKS = ("design", "refold-prepare", "refold-score", "finetune")


def pick_weights(track: str) -> str:
    """Our default weight per track, from the organisers' measured table.

    optimisation: her2-2026-11-07 - 21% known binders at conservative/balanced,
    but only 0-6% pass the novelty filter, so the loops must be varied
    (--sequence-tsr-k) or most output is unsubmittable.
    de_novo: her2-novel-2026-11-09 - 86% pass novelty and the lowest interface
    error in the table (6.8 A).
    This is a team choice over the organisers' numbers, not a rule from the PDF.
    """
    return {"optimisation": "her2-2026-11-07", "de_novo": "her2-novel-2026-11-09"}.get(track, "antibody-2026-10-30")


def hotspots_from_interface(interface: dict, max_hotspots: int | None = None) -> list:
    """Epitope residues as hotspot specs, most-contacted first.

    Each entry carries the PDB residue id, because that is what a structure-based
    generator indexes. IMGT positions are not usable here - see 02_interface.py.
    """
    rows = sorted(interface.get("epitope", []), key=lambda r: (-r["n_contacts"], r["min_distance"]))
    if max_hotspots:
        rows = rows[:max_hotspots]
    return [{
        "chain": r["pdb_residue_id"][0],
        "resseq": r["pdb_residue_id"][1],
        "icode": r["pdb_residue_id"][2],
        "aa": r["aa"],
        "n_contacts": r["n_contacts"],
        "spec": "{0}{1}{2}".format(r["pdb_residue_id"][0], r["pdb_residue_id"][1], r["pdb_residue_id"][2]),
    } for r in rows]


def build_job_spec(args, interface: dict | None) -> dict:
    """The generator-agnostic job spec. Every dispatch path reads this, so the
    inputs are identical whichever backend runs and the spec is the artefact we
    show a judge.

    cdrh3_to_redesign is null when stage 02 emitted no CDR assignment (no sound
    numbering map). main() refuses to continue in that state when the chosen
    weight redesigns CDRH3 only - see --allow-missing-cdrh3."""
    ab_chains = (interface or {}).get("antibody_chains", [])
    ag_chains = (interface or {}).get("antigen_chains", [])
    hotspots = hotspots_from_interface(interface or {}, args.max_hotspots)
    cdrh3 = None
    for cid in ab_chains:
        nb = ((interface or {}).get("numbering") or {}).get(cid) or {}
        if nb.get("cdrs"):
            cdrh3 = {"chain": cid, **nb["cdrs"].get("CDR3", {})}
            break

    spec = {
        "schema": "fab4.jobspec/v1",
        "generator": args.generator,
        "task": "design",
        "track_intent": args.track,
        "weights": args.weights,
        "seed": args.seed,
        "num_designs": args.num_designs,
        "settings": {
            "sequence_tsr_k": args.sequence_tsr_k,
            "sequence_tsr_k_meaning": TSR_K.get(args.sequence_tsr_k, "not named in the task PDF"),
            "num_replicates": args.num_replicates,
            "batch_size": args.batch_size,
            "nsteps": args.nsteps,
            "recycle_strategy": args.recycle_strategy,
        },
        "target": {
            "structure": common.file_ref(args.target_cif),
            "antigen_chains": ag_chains,
            "antibody_chains": ab_chains,
        },
        "epitope_hotspots": hotspots,
        "cdrh3_to_redesign": cdrh3,
        "epitope_preservation_note":
            "Judged condition 2 is epitope preservation, measured by competitive binding "
            "against trastuzumab (task PDF). Keeping these hotspots in the design input is "
            "our only lever on it before the assay.",
        "provenance": common.provenance(
            "03_generate", model=args.generator, weights=args.weights, seed=args.seed,
            run_id=args.run_id,
            settings={"dispatch": args.dispatch, "num_designs": args.num_designs},
            inputs=[args.interface, args.target_cif]),
    }
    if args.weights in WEIGHTS:
        spec["weights_info"] = WEIGHTS[args.weights]
    return spec


# --------------------------------------------------------------------------
# dispatch: Apheris Foundry (primary)
# --------------------------------------------------------------------------

def foundry_design(spec: dict, job_dir: str) -> list:
    """Run the RFD4-Proteina `design` task in Apheris Foundry on the team VM.

    UNVERIFIED INTERFACE - no Foundry CLI invocation appears in any of our
    sources. What the task PDF does state, and all it states:
      * Foundry models are Docker images already downloaded on the VM.
      * `foundry-toolkit module list` lists them.
      * Tutorial.html (Hackathon VM tab) shows how to run each one.
      * RFD4-Proteina runs as one Docker image per model, in research preview,
        with tasks: design, refold-prepare, refold-score, finetune.
      * The image selects the weights (release-2026-10-19, antibody-2026-10-30,
        her2-2026-11-07, her2-novel-2026-11-09).
      * `--sequence-tsr-k` takes 2 (balanced) or 1 (exploratory).
      * A step-by-step guide with example inputs and a ready-made HER2 script is
        in the data bucket under rfd4-proteina/docs/ - open Tutorial.html.

    Confirm on the VM, in this order, then wire the result into this one function:
        foundry-toolkit module list
        aws s3 sync s3://apheris-oslo-hackathon/rfd4-proteina ./rfd4-proteina
        open ./rfd4-proteina/docs/Tutorial.html     # the ready-made HER2 script
    What must be confirmed:
      1. the exact command that launches a module and the exact image reference
         per weight (record it in the candidate provenance as `model_image`);
      2. how the annotated mmCIF, the hotspots and the CDRH3 contig are passed;
      3. the flag names for number of designs, seed, recycling schedule,
         partial diffusion and inverse folding;
      4. where the designs land and in what format.
    """
    raise common.must_confirm(
        "the Apheris Foundry CLI for RFD4-Proteina `design`",
        "foundry-toolkit module list, then the ready-made HER2 script in "
        "s3://apheris-oslo-hackathon/rfd4-proteina/docs/ (Tutorial.html). "
        "Wire it into foundry_design() in pipeline/03_generate.py and record the image "
        "reference as model_image. Until then: --dispatch none, run the script by hand, "
        "and bring the designs back in with --from-sequences.")


# --------------------------------------------------------------------------
# dispatch: Nebius Scientific AI (documented alternative)
# --------------------------------------------------------------------------

def forge_argv(spec: dict, target_cif: str, label: str, forge_py: str) -> list:
    """The forge.py command for hosted rfd4-proteina.

    Call shape taken verbatim from RECIPES.md recipe 6, which was run on a real
    participant account on 11-12 November 2026 (test run: 385 s, returns a tar
    of designs). Parameter names come from that recipe, not from us.

    Caveat that must travel with any design from this path: the hosted
    rfd4-proteina is the general model. RECIPES.md: "The output is a general
    protein binder, not a VHH. RFD4-Proteina has no antibody prior. A generated
    backbone usually needs recipe 3 after it to get a sequence." So a design from
    here is a backbone that still needs ProteinMPNN (or AntiFold on an antibody
    framework), and it is not an antibody until something makes it one - while
    abguard requires VHH, scFv or Fab.
    """
    s = spec["settings"]
    params = {
        "num_replicates": s["num_replicates"],
        "batch_size": s["batch_size"],
        "seed": spec["seed"],
        "nsteps": s["nsteps"],
        "recycle_strategy": s["recycle_strategy"],
        "compile": True,
        "save_trajectory_every": 0,
        "save_chain_of_interest": False,
    }
    return [
        sys.executable, forge_py, "submit", "rfd4-proteina",
        "--entry", "annotated-cif|rfd4-proteina-annotated-cif/v1|{0}".format(target_cif),
        "--params", json.dumps(params, separators=(",", ":")),
        "--label", label,
    ]


def forge_dispatch(spec: dict, args, job_dir: str) -> dict:
    """Submit to Nebius and record the run id. Does not wait for the result:
    fetch it with `forge.py fetch <op-id> --dest ...` and bring the designs in
    with --from-sequences.

    Needs NEBIUS_CREDS pointing at the credentials file (see START-HERE.md in
    the Slack folder). The key itself is never read, printed or stored here.
    """
    if not os.environ.get("NEBIUS_CREDS"):
        raise SystemExit("NEBIUS_CREDS is not set. See the Slack folder's START-HERE.md:\n"
                         "  export NEBIUS_CREDS=\"$PWD/credentials.private.json\"")
    if not args.forge_py or not os.path.exists(args.forge_py):
        raise SystemExit("--forge-py must point at forge.py (default location: "
                         "~/.claude/skills/nebius-scientific-ai/forge.py)")
    argv = forge_argv(spec, args.target_cif, args.label or "fab4-gen", args.forge_py)
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = {"argv": argv, "returncode": proc.returncode,
           "stdout": proc.stdout[-8000:], "stderr": proc.stderr[-4000:]}
    common.write_json(os.path.join(job_dir, "forge_submit.json"), out)
    if proc.returncode != 0:
        raise SystemExit("forge.py submit failed (rc={0}); see {1}/forge_submit.json".format(
            proc.returncode, job_dir))
    return out


# --------------------------------------------------------------------------
# ingestion of designs produced elsewhere
# --------------------------------------------------------------------------

def check_chains(fmt: str, chains: dict, where: str) -> None:
    """Chains must match the declared format, on EVERY ingestion path.

    A VHH with only an L chain used to pass here and reach stage 05, which then
    wrote an empty sequence into the abguard FASTA. One check, both paths.
    """
    if fmt not in common.VALID_FORMATS:
        raise SystemExit("{0}: format {1!r} is not one of {2}".format(
            where, fmt, ", ".join(common.VALID_FORMATS)))
    if not (chains.get("H") or "").strip():
        raise SystemExit("{0}: {1} needs an H chain (got chains: {2})".format(
            where, fmt, ", ".join(sorted(chains)) or "none"))
    if fmt in ("scFv", "Fab") and not (chains.get("L") or "").strip():
        raise SystemExit("{0}: {1} needs an L chain. In a FASTA pair the headers as 'name|H' / "
                         "'name|L'; in a JSONL give chains: {{\"H\": ..., \"L\": ...}}".format(
                             where, fmt))
    if fmt == "VHH" and (chains.get("L") or "").strip():
        raise SystemExit("{0}: an L chain was given but the format is VHH".format(where))
    if fmt != "scFv" and (chains.get("linker") or "").strip():
        raise SystemExit("{0}: a linker was given but the format is {1}; only an scFv has one"
                         .format(where, fmt))


def parent_cdrh3_from_jobspec(path: str) -> dict | None:
    """The CDRH3 stage 02 found on the PARENT antibody, read back out of a
    jobspec.json written by an earlier `--dispatch none` run of this stage."""
    spec = common.read_input_json(path, what="jobs/jobspec.json",
                                  produced_by="03_generate.py --dispatch none")
    c = spec.get("cdrh3_to_redesign")
    return c if isinstance(c, dict) and c.get("sequence") else None


def attach_cdrh3(rec: dict, *, explicit: str | None, parent: dict | None) -> None:
    """Write rec['cdrh3'] when we actually know the design's CDRH3, and say where
    it came from. Never guess one.

    Stage 05's novelty check - the one hard filter that decides the track - reads
    rec['cdrh3'], so a record without it can never be checked. Three cases:
      1. the operator or the input record states it      -> use it
      2. the parent's CDRH3 is present verbatim in the H chain (the loop was not
         redesigned)                                     -> use it, say so
      3. neither                                         -> leave it absent and
         note what would fix it. Numbering a designed loop needs ANARCII or
         immunum on the design itself, which stage 02 does from --numbering-json.
    """
    if explicit:
        rec["cdrh3"] = explicit.strip().upper()
        rec["cdrh3_source"] = "stated on the input (operator-supplied; not numbered by us)"
        return
    heavy = (rec.get("chains") or {}).get("H") or ""
    pseq = (parent or {}).get("sequence")
    if pseq and pseq in heavy:
        rec["cdrh3"] = pseq
        rec["cdrh3_source"] = ("parent CDRH3 found verbatim in this design's H chain, so the loop "
                               "is unchanged (from jobspec cdrh3_to_redesign)")
        return
    rec.setdefault("notes", []).append(
        "no CDRH3 on this record: not stated, and the parent loop is not present verbatim in the H "
        "chain. Stage 05's novelty check will report indeterminate. Fix with --cdrh3, a 'cdrh3' "
        "field in the JSONL, or by numbering the design (stage 02 --numbering-json).")


def candidates_from_sequences(path: str, args) -> list:
    """Read designs from a FASTA or a JSONL and emit candidate records.

    FASTA: one record per design. For scFv/Fab, chains are paired by a header
    suffix - `name|H` and `name|L`, or `name_H` / `name_L`. A VHH needs one
    header per design.
    JSONL: {"id": ..., "chains": {"H": ..., "L": ...}} per line, which is the
    escape hatch when headers cannot carry the structure.
    """
    prov_base = dict(
        model=args.generator, model_image=args.model_image, weights=args.weights,
        seed=args.seed, run_id=args.run_id,
    )
    parent_cdrh3 = parent_cdrh3_from_jobspec(args.jobspec) if args.jobspec else None

    recs = []
    if path.lower().endswith((".jsonl", ".json")):
        rows = (common.read_input_jsonl(path, what="designs (JSONL)", produced_by="the generator")
                if path.lower().endswith(".jsonl")
                else common.read_input_json(path, what="designs (JSON)", produced_by="the generator"))
        if isinstance(rows, dict):
            rows = [rows]
        for i, row in enumerate(rows, 1):
            chains = row.get("chains") or {k: row[k] for k in ("H", "L", "linker") if row.get(k)}
            if not chains:
                raise SystemExit("{0}: record {1} has no chains".format(path, i))
            fmt = row.get("format", args.format)
            check_chains(fmt, chains, "{0}: record {1}".format(path, i))
            rec = common.new_candidate(
                row.get("id") or "{0}-{1:04d}".format(args.id_prefix, i),
                fmt=fmt, chains=chains,
                track_intent=row.get("track_intent", args.track),
                parent=row.get("parent", args.parent),
                structure_path=row.get("structure_path"),
                provenance_stamp=common.provenance(
                    "03_generate", settings={"source": "from-sequences", "file": path},
                    inputs=[path], **prov_base),
                notes=row.get("notes"))
            attach_cdrh3(rec, explicit=row.get("cdrh3") or args.cdrh3, parent=parent_cdrh3)
            recs.append(rec)
        return recs

    fasta = common.read_fasta(path)
    groups: dict = {}
    order = []
    for header, seq in fasta:
        name, chain = header, "H"
        for sep in ("|", " "):
            if sep in header:
                left, right = header.split(sep, 1)
                if right.strip().upper() in ("H", "L", "VH", "VL"):
                    name, chain = left.strip(), right.strip().upper()[-1]
                    break
        else:
            if header[-2:].upper() in ("_H", "_L"):
                name, chain = header[:-2], header[-1].upper()
        if name not in groups:
            groups[name] = {}
            order.append(name)
        groups[name][chain] = seq

    for i, name in enumerate(order, 1):
        chains = groups[name]
        fmt = args.format
        check_chains(fmt, chains, "{0}: design {1!r}".format(path, name))
        rec = common.new_candidate(
            "{0}-{1:04d}".format(args.id_prefix, i), fmt=fmt, chains=chains,
            track_intent=args.track, parent=args.parent,
            provenance_stamp=common.provenance(
                "03_generate",
                settings={"source": "from-sequences", "file": path, "fasta_header": name},
                inputs=[path], **prov_base),
            notes=["fasta header: " + name])
        attach_cdrh3(rec, explicit=args.cdrh3, parent=parent_cdrh3)
        recs.append(rec)
    return recs


def main(argv=None) -> int:
    p = common.base_parser(
        "Stage 03: build generator inputs from the interface, dispatch a design job, "
        "and write one candidate record per design with full provenance.",
        epilog="Weights available in Foundry: " + ", ".join(sorted(WEIGHTS)) +
               "\nSee the module docstring for what each dispatch mode can and cannot do.",
    )
    src = p.add_argument_group("inputs")
    src.add_argument("--interface", default=None, help="interface.json from stage 02")
    src.add_argument("--target-cif", default=None, help="annotated mmCIF of the target for the generator")
    src.add_argument("--from-sequences", default=None,
                     help="ingest designs made elsewhere: FASTA or JSONL. Skips dispatch")
    src.add_argument("--jobspec", default=None,
                     help="jobs/jobspec.json from the earlier --dispatch none run. Its "
                          "cdrh3_to_redesign is the PARENT loop; a design that still carries it "
                          "verbatim gets that CDRH3 written onto its record")
    src.add_argument("--cdrh3", default=None,
                     help="CDRH3 of the ingested designs, written onto every record as "
                          "rec['cdrh3']. Stage 05's novelty check needs it. Only pass it if it is "
                          "true for every design in the file")

    gen = p.add_argument_group("generator")
    gen.add_argument("--generator", default="rfd4-proteina",
                     help="generator name recorded in provenance (default %(default)s)")
    gen.add_argument("--track", choices=["optimisation", "de_novo", "unknown"], default="unknown",
                     help="the track we are AIMING for. abguard decides the real track and never "
                          "reclassifies a design")
    gen.add_argument("--weights", default=None,
                     help="Foundry weight / image tag. Default is chosen per track")
    gen.add_argument("--model-image", default=None,
                     help="exact Docker image reference, recorded in provenance. Get it from "
                          "`foundry-toolkit module list`")
    gen.add_argument("--sequence-tsr-k", type=int, default=None, choices=[1, 2],
                     help="2 = balanced, 1 = exploratory (task PDF). HER2 weights only")
    gen.add_argument("--num-designs", type=int, default=64)
    gen.add_argument("--seed", type=int, default=42, help="recorded in every output row")
    gen.add_argument("--num-replicates", type=int, default=1)
    gen.add_argument("--batch-size", type=int, default=1)
    gen.add_argument("--nsteps", type=int, default=60)
    gen.add_argument("--recycle-strategy", default="thinking_medium",
                     help="value from RECIPES.md recipe 6 (default %(default)s)")
    gen.add_argument("--max-hotspots", type=int, default=None,
                     help="keep only the N most-contacted epitope residues as hotspots")
    gen.add_argument("--format", choices=list(common.VALID_FORMATS), default="VHH",
                     help="submission format of the designs (default %(default)s)")
    gen.add_argument("--parent", default=None, help="parent antibody, e.g. trastuzumab")
    gen.add_argument("--id-prefix", default="cand")

    disp = p.add_argument_group("dispatch")
    disp.add_argument("--dispatch", choices=["none", "foundry", "forge"], default="none")
    disp.add_argument("--job-dir", default=None, help="where the job spec and dispatch log go")
    disp.add_argument("--forge-py", default=os.path.expanduser("~/.claude/skills/nebius-scientific-ai/forge.py"))
    disp.add_argument("--label", default=None, help="short run label passed to forge.py")
    disp.add_argument("--allow-missing-cdrh3", action="store_true",
                      help="build a job spec with cdrh3_to_redesign = null even though the chosen "
                           "weight redesigns CDRH3 only. Refused by default, because the job has "
                           "nothing to redesign")
    common.add_io_args(p, out_default=None)
    args = p.parse_args(argv)

    if not args.weights:
        args.weights = pick_weights(args.track)
    if (not args.from_sequences and args.weights in WEIGHTS
            and WEIGHTS[args.weights].get("redesigns_cdrh3_only") and args.sequence_tsr_k is None):
        print("note: {0} redesigns CDRH3 only. Without --sequence-tsr-k the task PDF's measured "
              "'conservative' setting applies, where 0% of designs passed the novelty filter."
              .format(args.weights), file=sys.stderr)

    # 1. ingestion path - no generator runs, designs already exist
    if args.from_sequences:
        recs = candidates_from_sequences(args.from_sequences, args)
        path = common.write_jsonl(args.out, recs)
        common.say(args.quiet, "ingested {0} design(s) from {1}".format(len(recs), args.from_sequences))
        common.say(args.quiet, "wrote " + path)
        return 0

    # 2. generator path - needs an interface and a target
    if not args.interface:
        raise SystemExit("need --interface (stage 02 output) or --from-sequences")
    interface = common.read_input_json(args.interface, what="interface.json",
                                       produced_by="02_interface.py")
    if args.dispatch != "none" and not args.target_cif:
        raise SystemExit("--dispatch {0} needs --target-cif".format(args.dispatch))

    job_dir = args.job_dir or os.path.join(os.path.dirname(os.path.abspath(args.out)), "jobs")
    os.makedirs(job_dir, exist_ok=True)
    spec = build_job_spec(args, interface)

    # A CDRH3-redesign job with no CDRH3 has nothing to redesign. Both HER2
    # weights are redesigns_cdrh3_only (task PDF p5: her2-2026-11-07 and
    # her2-novel-2026-11-09 redesign trastuzumab's CDRH3), so this is the default
    # path, not an edge case. Refuse rather than write a spec that burns GPU time.
    if spec["cdrh3_to_redesign"] is None and WEIGHTS.get(args.weights, {}).get("redesigns_cdrh3_only"):
        msg = ("{0} redesigns CDRH3 only, but stage 02 emitted no CDR assignment so "
               "cdrh3_to_redesign is null - the job would have nothing to redesign.\n"
               "  Fix: re-run 02_interface.py with --numbering-json so interface.json carries "
               "numbering[chain].cdrs, or pick a weight that redesigns more than CDRH3 "
               "(antibody-2026-10-30), or pass --allow-missing-cdrh3 to write the spec anyway."
               .format(args.weights))
        if not args.allow_missing_cdrh3:
            raise SystemExit(msg)
        print("WARNING: " + msg, file=sys.stderr)

    spec_path = common.write_json(os.path.join(job_dir, "jobspec.json"), spec)
    common.say(args.quiet, "job spec: " + spec_path)
    common.say(args.quiet, "hotspots: {0} epitope residue(s)".format(len(spec["epitope_hotspots"])))

    if args.dispatch == "none":
        hint = {
            "foundry": "see foundry_design() in pipeline/03_generate.py for what to confirm on the VM",
            "forge": shlex.join(forge_argv(spec, args.target_cif or "<target.cif>",
                                           args.label or "fab4-gen", args.forge_py)),
        }
        common.write_json(os.path.join(job_dir, "commands.json"), hint)
        common.say(args.quiet, "dispatch=none: wrote the commands to {0}/commands.json".format(job_dir))
        common.say(args.quiet, "NO candidate file was written: no designs exist yet. Next, in order:")
        common.say(args.quiet, "  1. run the generator (see {0}/commands.json)".format(job_dir))
        common.say(args.quiet, "  2. python3 03_generate.py --from-sequences <designs.fasta|jsonl> "
                               "--jobspec {0}/jobspec.json -o {1}".format(job_dir, args.out))
        common.say(args.quiet, "  3. then stage 04 on that file")
        # No designs exist yet, so no candidate file is written. Writing an empty
        # one would let stage 04 "succeed" on nothing.
        return 0

    if args.dispatch == "forge":
        res = forge_dispatch(spec, args, job_dir)
        common.say(args.quiet, "submitted to Nebius; run id is in {0}/forge_submit.json".format(job_dir))
        common.say(args.quiet, "fetch with: python3 {0} fetch <op-id> --dest results/".format(args.forge_py))
        common.say(args.quiet, "then re-run this stage with --from-sequences on the fetched designs")
        return 0 if res["returncode"] == 0 else 1

    designs = foundry_design(spec, job_dir)  # raises ConfirmOnVM until wired
    recs = []
    for i, d in enumerate(designs, 1):
        check_chains(args.format, d["chains"], "foundry design {0}".format(i))
        rec = common.new_candidate(
            "{0}-{1:04d}".format(args.id_prefix, i), fmt=args.format,
            chains=d["chains"], track_intent=args.track, parent=args.parent,
            structure_path=d.get("structure_path"),
            provenance_stamp=common.provenance(
                "03_generate", model=args.generator, model_image=args.model_image,
                weights=args.weights, seed=args.seed, run_id=args.run_id,
                settings=spec["settings"], inputs=[args.interface, args.target_cif]))
        attach_cdrh3(rec, explicit=d.get("cdrh3") or args.cdrh3,
                     parent=spec.get("cdrh3_to_redesign"))
        recs.append(rec)
    path = common.write_jsonl(args.out, recs)
    common.say(args.quiet, "wrote {0} candidate(s) to {1}".format(len(recs), path))
    return 0


if __name__ == "__main__":
    raise SystemExit(common.cli(main))
