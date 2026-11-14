#!/usr/bin/env python3
"""Stage 01 - prepare the antigen structure.

Mentor Lluis Artus, step 1: "Accept antigen structure (formats mmcif or pdb) use
biopython library".

Reads one structure, selects chains, and reports what is actually present: the
observed sequence per chain, the SEQRES sequence where the file carries one, the
residues that are NOT resolved, and the numbering gaps. Writes target.json for
stage 02.

Why the unresolved list matters: the pre-read brief's tutorial case (1ZVY) has an
unresolved residue A1, and ProteinMPNN reports exactly that position in
`backbone_coverage` as undesignable. A contig or a hotspot list built from a
residue with no coordinates is a silent failure.

Usage:
  python3 01_prepare_target.py data/1zvy.pdb --chains B -o runs/target.json
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

AA3_TO_1 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V", "SEC": "U", "PYL": "O", "MSE": "M",
}

BACKBONE = ("N", "CA", "C", "O")


def guess_format(path: str, forced: str | None = None) -> str:
    if forced and forced != "auto":
        return forced
    ext = os.path.splitext(path)[1].lower()
    if ext in (".cif", ".mmcif"):
        return "mmcif"
    if ext in (".pdb", ".ent"):
        return "pdb"
    raise SystemExit("cannot tell the format of {0}; pass --format pdb|mmcif".format(path))


def load_structure(path: str, fmt: str):
    """Parse with biopython. QUIET=True because hackathon PDBs are messy and the
    warnings are not the information we want; the gaps we care about are reported
    explicitly below instead."""
    from Bio.PDB import MMCIFParser, PDBParser
    parser = MMCIFParser(QUIET=True) if fmt == "mmcif" else PDBParser(QUIET=True)
    structure = parser.get_structure("target", path)
    return structure


def seqres_from_file(path: str, fmt: str) -> dict:
    """Chain id -> full SEQRES/entity_poly sequence, when the file carries one.

    Returns {} if the file has no sequence records (common for stripped or
    model-generated files). An empty result is reported, not patched over: it
    means "we cannot know what is missing", which is different from "nothing is
    missing"."""
    out: dict = {}
    if fmt == "pdb":
        try:
            from Bio import SeqIO
            for rec in SeqIO.parse(path, "pdb-seqres"):
                cid = rec.annotations.get("chain") or rec.id.split(":")[-1]
                out[str(cid)] = str(rec.seq)
        except Exception:
            return {}
        return out
    # mmCIF: _pdbx_poly_seq_scheme lists every polymer residue of the entity,
    # with '?' or '.' in the pdb_seq_num column when it was not observed.
    try:
        from Bio.PDB.MMCIF2Dict import MMCIF2Dict
        d = MMCIF2Dict(path)
    except Exception:
        return {}

    def col(key):
        v = d.get(key)
        if v is None:
            return None
        return v if isinstance(v, list) else [v]

    chains = col("_pdbx_poly_seq_scheme.pdb_strand_id")
    mons = col("_pdbx_poly_seq_scheme.mon_id")
    if chains and mons and len(chains) == len(mons):
        for cid, mon in zip(chains, mons):
            out.setdefault(str(cid), []).append(AA3_TO_1.get(str(mon).upper(), "X"))
        return {k: "".join(v) for k, v in out.items()}
    return {}


def unobserved_from_mmcif(path: str) -> dict:
    """Chain id -> [{seq_id, residue, auth_seq_id}] for residues present in the
    entity but absent from the coordinates. mmCIF only; {} when unavailable."""
    try:
        from Bio.PDB.MMCIF2Dict import MMCIF2Dict
        d = MMCIF2Dict(path)
    except Exception:
        return {}

    def col(key):
        v = d.get(key)
        if v is None:
            return None
        return v if isinstance(v, list) else [v]

    cid = col("_pdbx_poly_seq_scheme.pdb_strand_id")
    mon = col("_pdbx_poly_seq_scheme.mon_id")
    sid = col("_pdbx_poly_seq_scheme.seq_id")
    # A row is unobserved when the coordinate columns are '?': pdb_mon_id and
    # auth_seq_num. pdb_seq_num stays populated for unobserved residues (checked
    # against 1ZVY: the C-terminal SSRGRHHHHHH tag has pdb_mon_id '?' but
    # pdb_seq_num 126-136), so it is NOT the marker.
    pdb_mon = col("_pdbx_poly_seq_scheme.pdb_mon_id")
    auth = col("_pdbx_poly_seq_scheme.auth_seq_num")
    num = col("_pdbx_poly_seq_scheme.pdb_seq_num")
    marker = pdb_mon or auth
    if not (cid and mon and sid and marker):
        return {}
    if not (len(cid) == len(mon) == len(sid) == len(marker)):
        return {}
    if num and len(num) != len(cid):
        num = None
    out: dict = {}
    for i, (c, m, s, mk) in enumerate(zip(cid, mon, sid, marker)):
        if str(mk).strip() in ("?", ".", ""):
            out.setdefault(str(c), []).append({
                "seq_id": str(s),
                "residue": str(m),
                "one_letter": AA3_TO_1.get(str(m).upper(), "X"),
                "pdb_seq_num": str(num[i]) if num else None,
            })
    return out


def describe_chain(chain) -> dict:
    """Observed residues of one chain, plus numbering gaps and broken backbones."""
    observed, hetero, incomplete, altloc = [], [], [], []
    for res in chain:
        het, resseq, icode = res.id
        rec = {
            "resseq": resseq,
            "icode": icode.strip(),
            "resname": res.get_resname().strip(),
            "one_letter": AA3_TO_1.get(res.get_resname().strip().upper(), "X"),
        }
        if het.strip():
            hetero.append(dict(rec, hetflag=het.strip()))
            continue
        if rec["one_letter"] == "X":
            hetero.append(dict(rec, hetflag="non-standard"))
            continue
        names = {a.get_id() for a in res}
        missing = [a for a in BACKBONE if a not in names]
        if missing:
            incomplete.append(dict(rec, missing_atoms=missing))
        if any(a.is_disordered() for a in res):
            altloc.append(rec)
        observed.append(rec)

    gaps = []
    for a, b in zip(observed, observed[1:]):
        if not a["icode"] and not b["icode"] and b["resseq"] - a["resseq"] > 1:
            gaps.append({
                "after_resseq": a["resseq"],
                "before_resseq": b["resseq"],
                "missing_count": b["resseq"] - a["resseq"] - 1,
            })

    return {
        "chain_id": chain.id,
        "n_observed": len(observed),
        "sequence_observed": "".join(r["one_letter"] for r in observed),
        "first_resseq": observed[0]["resseq"] if observed else None,
        "last_resseq": observed[-1]["resseq"] if observed else None,
        "residue_ids": [[chain.id, r["resseq"], r["icode"]] for r in observed],
        "numbering_gaps": gaps,
        "residues_missing_backbone_atoms": incomplete,
        "residues_with_altloc": altloc,
        "hetero_or_nonstandard": hetero,
    }


def main(argv=None) -> int:
    p = common.base_parser(
        "Stage 01: load an antigen structure (mmCIF or PDB), select chains, report "
        "what is present and what is unresolved.",
        epilog="Writes target.json. Next stage: 02_interface.py --target <target.json>",
    )
    p.add_argument("structure", help="antigen structure, .cif/.mmcif or .pdb")
    p.add_argument("--format", choices=["auto", "pdb", "mmcif"], default="auto")
    p.add_argument("--chains", default=None,
                   help="comma-separated chain ids to keep, e.g. 'B' or 'A,B'. Default: all")
    p.add_argument("--model", type=int, default=0, help="model index for multi-model files (default 0)")
    p.add_argument("--min-residues", type=int, default=20,
                   help="warn about kept chains shorter than this (default 20); our own sanity "
                        "threshold, not from the task description")
    common.add_io_args(p, out_default=None)
    args = p.parse_args(argv)

    common.require_deps("Bio")
    fmt = guess_format(args.structure, args.format)
    structure = load_structure(args.structure, fmt)

    models = list(structure)
    if args.model >= len(models):
        raise SystemExit("file has {0} model(s); --model {1} is out of range".format(len(models), args.model))
    model = models[args.model]

    wanted = [c.strip() for c in args.chains.split(",")] if args.chains else None
    seqres = seqres_from_file(args.structure, fmt)
    unobs = unobserved_from_mmcif(args.structure) if fmt == "mmcif" else {}

    chains, skipped = [], []
    for chain in model:
        if wanted is not None and chain.id not in wanted:
            skipped.append(chain.id)
            continue
        info = describe_chain(chain)
        full = seqres.get(chain.id)
        info["sequence_seqres"] = full
        info["n_seqres"] = len(full) if full else None
        if full:
            info["n_unresolved"] = len(full) - info["n_observed"]
            info["unresolved_source"] = "seqres/entity_poly minus observed"
        else:
            info["n_unresolved"] = None
            info["unresolved_source"] = "unknown: file carries no SEQRES/entity_poly"
        info["unresolved_residues"] = unobs.get(chain.id, [])
        if info["unresolved_residues"]:
            info["unresolved_source"] = "_pdbx_poly_seq_scheme (unobserved rows)"
        chains.append(info)

    if wanted:
        for c in wanted:
            if c not in [i["chain_id"] for i in chains]:
                raise SystemExit("chain {0!r} not found in {1} (present: {2})".format(
                    c, args.structure, ", ".join(ch.id for ch in model)))

    warnings = []
    for info in chains:
        if info["n_observed"] < args.min_residues:
            warnings.append("chain {0}: only {1} standard residues".format(info["chain_id"], info["n_observed"]))
        if info["numbering_gaps"]:
            warnings.append("chain {0}: {1} numbering gap(s) - residue numbers are not contiguous".format(
                info["chain_id"], len(info["numbering_gaps"])))
        if info["residues_missing_backbone_atoms"]:
            warnings.append("chain {0}: {1} residue(s) missing backbone atoms".format(
                info["chain_id"], len(info["residues_missing_backbone_atoms"])))
        if not info["sequence_seqres"]:
            warnings.append("chain {0}: no SEQRES, so unresolved residues cannot be counted".format(info["chain_id"]))

    out = {
        "schema": "fab4.target/v1",
        "source_structure": common.file_ref(args.structure),
        "source_format": fmt,
        "model_index": args.model,
        "chains_kept": [i["chain_id"] for i in chains],
        "chains_skipped": skipped,
        "chains": chains,
        "warnings": warnings,
        "provenance": common.provenance("01_prepare_target", run_id=args.run_id,
                                        settings={"format": fmt, "chains": args.chains,
                                                  "model": args.model},
                                        inputs=[args.structure]),
    }
    path = common.write_json(args.out, out)

    if not args.quiet:
        rows = [[i["chain_id"], i["n_observed"], i["n_seqres"] if i["n_seqres"] else "-",
                 i["n_unresolved"] if i["n_unresolved"] is not None else "?",
                 len(i["numbering_gaps"]), len(i["hetero_or_nonstandard"])] for i in chains]
        print(common.table(rows, ["chain", "observed", "seqres", "unresolved", "gaps", "het"]))
        for w in warnings:
            print("warning: " + w)
        print("wrote " + path)
    return 0


if __name__ == "__main__":
    raise SystemExit(common.cli(main))
