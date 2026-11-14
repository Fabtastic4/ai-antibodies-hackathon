#!/usr/bin/env python3
"""Stage 02 - antibody-antigen interface, epitope and paratope.

Mentor Lluis Artus, step 2: "Find Antibody-antigen interface using ANARCII. Use
it to find the epitope-paratope aminoacids".

Two independent jobs in here, deliberately separable:

  A. CONTACTS - pure geometry. Heavy-atom distance cutoff between the antibody
     chains and the antigen chains. Needs biopython only, always runs.
  B. NUMBERING - ANARCII over the antibody chains, to label positions IMGT and
     assign CDRs. Optional: pass --numbering-json to supply it from elsewhere.

===========================================================================
 IMGT POSITIONS ARE NOT PDB RESIDUE NUMBERS.
===========================================================================
This is the silent bug docs/hackathon-brief.md calls out by name ("Numbering:
IMGT / Kabat / Chothia positions are *not* PDB residue numbers. Run ANARCI /
ANARCII and map onto chain residue identifiers. This is the silent bug.").

Concretely, in this file:
  * A PDB residue id is the triple (chain_id, resseq, icode) as it appears in
    the coordinate file. Every geometric result is keyed on that triple.
  * An IMGT position is an integer from ANARCII's numbering of the SEQUENCE. It
    has no relation to resseq. A VHH whose coordinates start at residue 2
    because residue 1 is unresolved still has IMGT position 1 somewhere, and
    IMGT 105-117 (CDRH3) will not be resseq 105-117.
  * They are joined only through `numbering[chain]["map"]`, which pairs them by
    walking the OBSERVED residues in order. If the chain has unresolved
    residues inside the numbered region, that walk is wrong - the stage detects
    the length mismatch and refuses to emit a map rather than emitting a
    shifted one. Check `numbering[chain]["map_status"]` before using it.
Never index coordinates with an IMGT number, and never hand a resseq to a
generator as if it were an IMGT position.
===========================================================================

Usage:
  python3 02_interface.py complex.cif --antibody-chains A --antigen-chains B \\
      -o runs/interface.json
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

# Our own contact definition, NOT from the task description: any heavy atom of
# residue i within CUTOFF angstrom of any heavy atom of residue j. 4.5 A is the
# common convention for a heavy-atom contact. It is a --contact-cutoff flag and
# the value used is written into the output provenance, so a judge can see it.
# TODO: confirm what cutoff the organisers' competitive-binding comparison
# implies, if any, and whether epitope should be defined on contacts or on
# buried surface area.
DEFAULT_CUTOFF_A = 4.5

# IMGT CDR position ranges, inclusive. Standard IMGT definition, NOT quoted in
# the task description or the participant guide.
# TODO: confirm against ANARCII's own region output and, more importantly,
# against abguard's CDRH3 definition before any CDRH3 identity number from this
# pipeline is quoted. abguard's novelty check is the one that counts.
IMGT_CDR_RANGES = {
    "CDR1": (27, 38),
    "CDR2": (56, 65),
    "CDR3": (105, 117),
}

AA3_TO_1 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V", "MSE": "M",
}


def load_structure(path: str):
    from Bio.PDB import MMCIFParser, PDBParser
    ext = os.path.splitext(path)[1].lower()
    parser = MMCIFParser(QUIET=True) if ext in (".cif", ".mmcif") else PDBParser(QUIET=True)
    return parser.get_structure("complex", path)


def standard_residues(chain):
    out = []
    for res in chain:
        het, _, _ = res.id
        if het.strip():
            continue
        if res.get_resname().strip().upper() not in AA3_TO_1:
            continue
        out.append(res)
    return out


def res_key(res):
    """(chain_id, resseq, icode) - the PDB residue identifier. Not an IMGT position."""
    chain_id = res.get_parent().id
    _, resseq, icode = res.id
    return [chain_id, resseq, icode.strip()]


def heavy_atoms(res):
    return [a for a in res if a.element != "H" and not a.get_id().startswith("H")]


def find_contacts(model, ab_chains: list, ag_chains: list, cutoff: float) -> list:
    """Residue-residue contacts across the two chain sets.

    Returns [{antibody: [cid,resseq,icode], antigen: [...], min_distance,
              n_atom_pairs, antibody_aa, antigen_aa}]
    """
    from Bio.PDB import NeighborSearch

    ag_res = [r for cid in ag_chains for r in standard_residues(model[cid])]
    ab_res = [r for cid in ab_chains for r in standard_residues(model[cid])]
    ag_atoms = [a for r in ag_res for a in heavy_atoms(r)]
    if not ag_atoms or not ab_res:
        return []
    ns = NeighborSearch(ag_atoms)

    pair_min, pair_count = {}, {}
    for r in ab_res:
        for atom in heavy_atoms(r):
            for other in ns.search(atom.coord, cutoff, level="A"):
                d = float(atom - other)
                key = (tuple(res_key(r)), tuple(res_key(other.get_parent())))
                pair_count[key] = pair_count.get(key, 0) + 1
                if key not in pair_min or d < pair_min[key]:
                    pair_min[key] = d

    contacts = []
    for (ab_id, ag_id), d in sorted(pair_min.items(), key=lambda kv: kv[1]):
        ab_r = model[ab_id[0]][(" ", ab_id[1], ab_id[2] or " ")]
        ag_r = model[ag_id[0]][(" ", ag_id[1], ag_id[2] or " ")]
        contacts.append({
            "antibody": list(ab_id),
            "antigen": list(ag_id),
            "antibody_aa": AA3_TO_1.get(ab_r.get_resname().strip().upper(), "X"),
            "antigen_aa": AA3_TO_1.get(ag_r.get_resname().strip().upper(), "X"),
            "min_distance": round(d, 2),
            "n_atom_pairs": pair_count[(ab_id, ag_id)],
        })
    return contacts


def anarcii_number(sequences: dict, scheme: str = "imgt") -> dict:
    """Number antibody chains with ANARCII.

    UNVERIFIED INTERFACE. The ANARCII Python entry point is not documented in
    any of our sources (task PDF, resource map, Nebius RECIPES.md, participant
    guide), so this function does not hard-code a call shape it cannot stand
    behind. It attempts the package's documented public API and, if that import
    or call fails, raises with the exact thing to check.

    Confirm on the VM, then update this function in one place:
        python3 -c "import anarcii, inspect; print(anarcii.__file__); print(dir(anarcii))"
        python3 -m anarcii --help          # if it ships a CLI
    What must be confirmed:
      1. the entry point (class or function) and its constructor arguments;
      2. the argument that selects the numbering scheme ("imgt");
      3. the result shape: per sequence, the list of (position, amino acid) and
         the confidence/score field, and whether insertions come back as
         (number, insertion-letter) tuples;
      4. whether it returns a region/CDR assignment of its own - if it does,
         prefer it over IMGT_CDR_RANGES in this file.

    Returns {chain: {"scheme", "numbering": [[pos, icode, aa], ...], "score",
                     "tool", "tool_version"}}.
    """
    try:
        import anarcii  # noqa: F401
    except ImportError:
        raise common.must_confirm(
            "ANARCII",
            "pip install anarcii, then "
            "python3 -c \"import anarcii; print(dir(anarcii))\" and wire the real entry "
            "point into anarcii_number() in pipeline/02_interface.py. "
            "Until then run this stage with --numbering-json <file>.")
    raise common.must_confirm(
        "the ANARCII call shape (the package imports, but our sources do not document its API)",
        "python3 -c \"import anarcii; print(dir(anarcii)); help(anarcii)\" on the VM, wire it "
        "into anarcii_number(), and record the version it reports. Meanwhile: --numbering-json.")


def numbering_to_map(numbering: list, observed: list) -> dict:
    """Join IMGT positions to PDB residue ids by walking both in order.

    This is the one place the two numbering systems meet, so it is the one place
    the shift can happen. The join is only valid when the numbered amino acids
    and the observed amino acids agree position by position. If they do not, we
    return map_status != "ok" and NO map: a shifted map is worse than none.
    """
    numbered = [(p, ic, aa) for (p, ic, aa) in numbering if aa and aa != "-"]
    if len(numbered) != len(observed):
        return {"map_status": "length-mismatch: {0} numbered vs {1} observed residues; "
                                "unresolved residues inside the numbered region would shift "
                                "every position".format(len(numbered), len(observed)),
                "map": None}
    mismatches = [i for i, ((_, _, aa), obs) in enumerate(zip(numbered, observed)) if aa != obs["aa"]]
    if mismatches:
        return {"map_status": "sequence-mismatch at {0} position(s), first at index {1}".format(
            len(mismatches), mismatches[0]), "map": None}
    return {
        "map_status": "ok",
        "map": [{"imgt_position": p, "imgt_insertion": ic, "aa": aa,
                 "pdb_residue_id": obs["pdb_residue_id"]}
                for (p, ic, aa), obs in zip(numbered, observed)],
    }


def cdr_spans(mapping: list) -> dict:
    """CDR spans as PDB residue ids, derived from the IMGT positions in `mapping`."""
    out = {}
    for name, (lo, hi) in IMGT_CDR_RANGES.items():
        rows = [m for m in mapping if lo <= m["imgt_position"] <= hi]
        out[name] = {
            "imgt_range": [lo, hi],
            "sequence": "".join(m["aa"] for m in rows),
            "pdb_residue_ids": [m["pdb_residue_id"] for m in rows],
            "definition": "IMGT ranges hard-coded in 02_interface.py; TODO confirm vs ANARCII regions and abguard",
        }
    return out


def main(argv=None) -> int:
    p = common.base_parser(
        "Stage 02: find the antibody-antigen interface, map epitope and paratope "
        "residues, and number the antibody chains (ANARCII, IMGT).",
        epilog="Writes interface.json. IMGT positions in that file are NOT PDB residue "
               "numbers - see the module docstring.",
    )
    p.add_argument("complex", help="antibody-antigen complex structure (.cif/.mmcif/.pdb)")
    p.add_argument("--antibody-chains", required=True, help="comma-separated chain ids, e.g. 'A' or 'H,L'")
    p.add_argument("--antigen-chains", required=True, help="comma-separated chain ids, e.g. 'B'")
    p.add_argument("--target", default=None, help="target.json from stage 01, carried into provenance")
    p.add_argument("--contact-cutoff", type=float, default=DEFAULT_CUTOFF_A,
                   help="heavy-atom contact distance in angstrom (default %(default)s; "
                        "our convention, not from the task description)")
    p.add_argument("--numbering-json", default=None,
                   help="supply numbering instead of calling ANARCII. Shape: "
                        '{"<chain>": {"scheme": "imgt", "numbering": [[pos, "", "Q"], ...], '
                        '"score": 0.99, "tool": "...", "tool_version": "..."}}')
    p.add_argument("--no-numbering", action="store_true",
                   help="contacts only; skip ANARCII and emit no CDR assignment")
    p.add_argument("--model", type=int, default=0)
    common.add_io_args(p, out_default=None)
    args = p.parse_args(argv)

    common.require_deps("Bio")
    ab_chains = [c.strip() for c in args.antibody_chains.split(",") if c.strip()]
    ag_chains = [c.strip() for c in args.antigen_chains.split(",") if c.strip()]
    overlap = set(ab_chains) & set(ag_chains)
    if overlap:
        raise SystemExit("chain(s) {0} listed as both antibody and antigen".format(sorted(overlap)))

    structure = load_structure(args.complex)
    models = list(structure)
    if args.model >= len(models):
        raise SystemExit("file has {0} model(s); --model {1} out of range".format(len(models), args.model))
    model = models[args.model]
    present = [c.id for c in model]
    for cid in ab_chains + ag_chains:
        if cid not in present:
            raise SystemExit("chain {0!r} not in {1} (present: {2})".format(cid, args.complex, ", ".join(present)))

    contacts = find_contacts(model, ab_chains, ag_chains, args.contact_cutoff)

    epitope, paratope = {}, {}
    for c in contacts:
        for bucket, side, aa in ((epitope, "antigen", "antigen_aa"), (paratope, "antibody", "antibody_aa")):
            key = tuple(c[side])
            row = bucket.setdefault(key, {"pdb_residue_id": c[side], "aa": c[aa],
                                          "n_contacts": 0, "min_distance": c["min_distance"]})
            row["n_contacts"] += 1
            row["min_distance"] = min(row["min_distance"], c["min_distance"])
    epitope = sorted(epitope.values(), key=lambda r: (r["pdb_residue_id"][0], r["pdb_residue_id"][1]))
    paratope = sorted(paratope.values(), key=lambda r: (r["pdb_residue_id"][0], r["pdb_residue_id"][1]))

    # observed residues per antibody chain, in file order - the left-hand side
    # of the IMGT <-> PDB join
    observed = {}
    for cid in ab_chains:
        observed[cid] = [{"pdb_residue_id": res_key(r),
                          "aa": AA3_TO_1.get(r.get_resname().strip().upper(), "X")}
                         for r in standard_residues(model[cid])]

    numbering_out, numbering_source = {}, "none"
    if not args.no_numbering:
        if args.numbering_json:
            raw = common.read_json(args.numbering_json)
            numbering_source = "file:" + os.path.abspath(args.numbering_json)
        else:
            seqs = {cid: "".join(r["aa"] for r in observed[cid]) for cid in ab_chains}
            raw = anarcii_number(seqs)  # raises ConfirmOnVM until wired on the VM
            numbering_source = "anarcii"
        for cid in ab_chains:
            entry = raw.get(cid)
            if not entry:
                numbering_out[cid] = {"map_status": "no numbering supplied for this chain", "map": None}
                continue
            nb = [(int(row[0]), (row[1] or "").strip(), row[2]) for row in entry.get("numbering", [])]
            joined = numbering_to_map(nb, observed[cid])
            numbering_out[cid] = {
                "scheme": entry.get("scheme", "imgt"),
                "tool": entry.get("tool"),
                "tool_version": entry.get("tool_version"),
                "numbering_score": entry.get("score"),
                "numbering_score_note": "whatever the numbering tool reported. NOT immunum's "
                                        "confidence, which is what abguard's >= 0.1 filter uses.",
                "map_status": joined["map_status"],
                "map": joined["map"],
                "cdrs": cdr_spans(joined["map"]) if joined["map"] else None,
            }

    # paratope residues labelled by CDR, where the join is sound
    paratope_by_region = []
    for row in paratope:
        cid = row["pdb_residue_id"][0]
        nb = numbering_out.get(cid) or {}
        region, imgt = None, None
        if nb.get("map"):
            hit = next((m for m in nb["map"] if m["pdb_residue_id"] == row["pdb_residue_id"]), None)
            if hit:
                imgt = hit["imgt_position"]
                for name, (lo, hi) in IMGT_CDR_RANGES.items():
                    if lo <= imgt <= hi:
                        region = name
                        break
                region = region or "framework"
        paratope_by_region.append(dict(row, imgt_position=imgt, region=region))

    out = {
        "schema": "fab4.interface/v1",
        "complex": common.file_ref(args.complex),
        "target_json": common.file_ref(args.target) if args.target else None,
        "antibody_chains": ab_chains,
        "antigen_chains": ag_chains,
        "contact_definition": {
            "cutoff_angstrom": args.contact_cutoff,
            "atoms": "heavy atoms only",
            "note": "our convention; not specified by the task description",
        },
        "n_contacts": len(contacts),
        "contacts": contacts,
        "epitope": epitope,
        "paratope": paratope_by_region,
        "numbering": numbering_out,
        "numbering_source": numbering_source,
        "numbering_warning": "IMGT positions are not PDB residue numbers. Join only via "
                             "numbering[chain]['map'], and only when map_status == 'ok'.",
        "provenance": common.provenance(
            "02_interface", model=("anarcii" if numbering_source == "anarcii" else None),
            run_id=args.run_id,
            settings={"contact_cutoff": args.contact_cutoff, "antibody_chains": ab_chains,
                      "antigen_chains": ag_chains, "imgt_cdr_ranges": IMGT_CDR_RANGES,
                      "numbering_source": numbering_source},
            inputs=[args.complex, args.target, args.numbering_json]),
    }
    path = common.write_json(args.out, out)

    if not args.quiet:
        print("contacts: {0}  epitope residues: {1}  paratope residues: {2}  cutoff: {3} A".format(
            len(contacts), len(epitope), len(paratope), args.contact_cutoff))
        if epitope:
            print("epitope: " + ", ".join("{0}{1}{2}".format(r["aa"], r["pdb_residue_id"][1],
                                                             r["pdb_residue_id"][2]) for r in epitope))
        for cid, nb in numbering_out.items():
            print("numbering {0}: {1}".format(cid, nb.get("map_status")))
        print("wrote " + path)
    return 0


if __name__ == "__main__":
    raise SystemExit(common.cli(main))
