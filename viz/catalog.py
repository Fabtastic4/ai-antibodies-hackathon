#!/usr/bin/env python3
"""Assemble one record per design: sequence, antigen, mutations, scores, improvement.

Everything here is read from files the pipeline already wrote -- designs/submission.csv and
reports/*.csv -- plus geometry measured from results/cofold/*/model.cif. Nothing is
recomputed in a way that could disagree with the submission, and nothing is invented: a
field with no source comes back null, and every number carries the basis string the
pipeline gave it.

"Improvement" is measured against wild-type trastuzumab VH on the 1N8Z crystal, scored with
the same function (viz/backends.py: wt_baseline). The comparison is VH-against-VH: the
19-residue epitope was defined from the whole Fab, so the light chain accounts for the
residues neither VH reaches. Comparing a design's VH to the Fab total would manufacture a
deficit that is not there.

    python3 catalog.py                 # the whole catalog as JSON
    python3 catalog.py --summary       # one line per design
"""

from __future__ import annotations

import csv
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import backends as B                                           # noqa: E402

REPO = B.REPO
REPORTS = REPO / "reports"
DESIGNS = REPO / "designs"


def _num(v):
    """CSV cell -> float, or None for the pipeline's explicit 'n/a'."""
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "n/a", "na", "NA", "None", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _read(path) -> list[dict]:
    p = pathlib.Path(path)
    if not p.is_file():
        return []
    with p.open() as fh:
        return list(csv.DictReader(fh))


def _by_key(rows, *keys) -> dict:
    out = {}
    for r in rows:
        for k in keys:
            if r.get(k):
                out.setdefault(r[k], r)
                break
    return out


def load_catalog(submission: str | pathlib.Path | None = None) -> dict:
    sub_path = pathlib.Path(submission) if submission else DESIGNS / "submission.csv"
    rows = _read(sub_path)
    if not rows:
        raise SystemExit(f"no designs found in {sub_path}")

    # Side tables. Keyed differently on purpose -- developability tables are keyed on
    # sequence_id, the structural ones on design_id. rank.py hit this exact trap.
    paratope = _by_key([r for p in sorted(REPORTS.glob("*-paratope.csv")) for r in _read(p)],
                       "design_id")
    solub = _by_key([r for p in sorted(REPORTS.glob("*-solubility.csv")) for r in _read(p)],
                    "sequence_id", "design_id")
    ddg = _by_key(_read(REPORTS / "esm2-axis3-ddg.csv"), "design_id")

    # Axis 1, where it was actually measured. reports/b1_refold_metrics.csv carries real
    # min_ipae / iptm / binder_plddt from the VM refold-score lane.
    #
    # Joined on the HEAVY SEQUENCE, never on the id. The ids collide across runs: that file's
    # `her2_cdrh3_14` is CDRH3 WHSLHEYYF while the submission's b1-novel-s1-her2_cdrh3_14 is
    # WHNLHEYYF -- a different molecule with the same trailing number. An id join would staple
    # a measured interface error onto the wrong sequence, which is worse than leaving it n/a.
    # A sequence join yields nothing until the submitted designs are themselves refolded, and
    # then it populates on its own.
    refold_by_seq = {}
    for p in (REPORTS / "b1_refold_metrics.csv", REPORTS / "b2_refold_metrics.csv"):
        for r in _read(p):
            seq = (r.get("binder_sequence") or "").strip()
            if seq:
                refold_by_seq.setdefault(seq, r)
    contacts = _by_key(_read(REPORTS / "cofold-contacts.csv"), "design_id")
    novelty = _by_key([r for p in sorted(REPORTS.glob("*-novelty.csv")) for r in _read(p)],
                      "design_id")

    base = B.wt_baseline()
    cif_index = B._cofold_index()

    designs = []
    for row in rows:
        did = row["design_id"]
        heavy = (row.get("sequence") or "").strip()
        light = (row.get("light_sequence") or "").strip()
        muts = B.mutation_report(heavy, light)

        # Structure, and the geometry measured from it. Prefer the file on disk over the
        # CSV so the viewer and its numbers can never disagree with the structure shown.
        cif = cif_index.get(did)
        structure = {"available": False, "chains": None}
        measured = {}
        if cif is not None:
            iface = B.interface_from_cif(cif)
            pl = B.plddt_from_cif(cif, B.BINDER_CHAIN)
            pl_loop = B.plddt_from_cif(cif, B.BINDER_CHAIN,
                                       residues=muts["highlight_vh_residues"])
            structure = {
                "available": True,
                "url": f"/api/structure/{did}",
                "path": str(cif.relative_to(REPO.parent)),
                "chains": {"binder_heavy": "H", "binder_light": "L", "antigen": "C"},
                "source": "boltz2 co-fold, Nebius hosted lane",
                "epitope_residues_hit": iface["epitope_residues_hit"],
                "target_residues_touched": iface["target_residues_touched"],
                "binder_residues_touching": iface["binder_residues_touching"],
                "plddt_per_residue": pl["per_residue"],
            }
            measured = {
                "n_contacts": iface["n_contacts"],
                "n_epitope_hit": iface["n_epitope_hit"],
                "epitope_frac": iface["epitope_frac"],
                "n_target_residues": iface["n_target_residues"],
                "binder_plddt": pl["mean"],
                "cdrh3_plddt": pl_loop["mean"],
            }
        else:
            c = contacts.get(did, {})
            measured = {
                "n_contacts": _num(c.get("cofold_n_contacts")),
                "n_epitope_hit": _num(c.get("cofold_n_epitope_hit")),
                "epitope_frac": _num(c.get("cofold_epitope_frac")),
                "n_target_residues": _num(c.get("cofold_n_target_residues")),
                "binder_plddt": None,
                "cdrh3_plddt": None,
            }

        # Axis 1: measured on the VM, or honestly absent.
        rf = refold_by_seq.get(heavy, {})
        axis1 = {
            "min_ipae": _num(rf.get("min_ipae")) if rf else _num(row.get("min_ipae")),
            "iptm": _num(rf.get("iptm")) if rf else _num(row.get("iptm")),
            "binder_plddt": _num(rf.get("binder_plddt")) if rf else None,
            "binder_ptm": _num(rf.get("binder_ptm")) if rf else None,
            "measured": bool(rf),
            "basis": (f"MEASURED on the VM: RFD4-Proteina refold-score, model "
                      f"{rf.get('model', '?')}, binder chain {rf.get('binder_chain', '?')} "
                      f"vs target {rf.get('target_chains', '?')}; matched to this design by "
                      f"heavy sequence, not by id"
                      if rf else
                      "NOT MEASURED for this design. reports/b1_refold_metrics.csv holds real "
                      "min_ipae/iptm, but for a different candidate set -- the trailing ids "
                      "collide across runs, so it is not joined. Run the JapanFold af2ig lane "
                      "or a VM refold on these exact sequences to fill it."),
        }

        p_row = paratope.get(did, {})
        s_row = solub.get(did, {})
        d_row = ddg.get(did, {})
        n_row = novelty.get(did, {})

        # Improvement, only where a like-for-like comparison exists.
        improvement = {}
        if base.get("available") and measured.get("n_epitope_hit") is not None:
            d = measured["n_epitope_hit"] - base["n_epitope_hit"]
            improvement["epitope_recovery"] = {
                "design": measured["n_epitope_hit"],
                "baseline": base["n_epitope_hit"],
                "delta": d,
                "of": len(B.HER2_EPITOPE),
                "direction": "higher is better",
                "comparable": True,
                "basis": ("design VH vs wild-type VH, same 4.5 A scorer; baseline from the "
                          "1N8Z crystal, design from a Boltz-2 co-fold"),
            }
        if measured.get("n_contacts") is not None and base.get("available"):
            improvement["interface_size"] = {
                "design": measured["n_contacts"],
                "baseline": base["n_contacts"],
                "delta": measured["n_contacts"] - base["n_contacts"],
                "direction": "higher is more interface, not necessarily better",
                "comparable": False,
                "basis": ("NOT like-for-like: crystal vs predicted co-fold. Shown for "
                          "context only. " + base["caveat"]),
            }
        improvement["novelty"] = {
            "design": muts["cdrh3_mutations"],
            "baseline": 0,
            "delta": muts["cdrh3_mutations"],
            "direction": "abguard needs >=3 from trastuzumab and all known CDRH3s; "
                         "docs/abguard.md says generate at >=6",
            "comparable": True,
            "passes_gate": muts["cdrh3_mutations"] >= 6,
            "basis": "Hamming over the VH99-107 window vs trastuzumab",
        }
        improvement["paratope_conserved"] = {
            "design": muts["paratope_kept"],
            "baseline": 4,
            "delta": muts["paratope_kept"] - 4,
            "of": 4,
            "direction": "keeping W99/G103/F104/Y105 preserves the measured contacts",
            "comparable": True,
            "basis": "the four CDRH3 residues that touch HER2 in 1N8Z",
        }

        designs.append({
            "design_id": did,
            "rank": int(_num(row.get("rank")) or 0) or None,
            "track": row.get("track"),
            "format": row.get("format"),
            "parent": row.get("parent"),
            "method": row.get("method"),
            "model_version": row.get("model_version"),
            "seed": row.get("seed"),
            "reason_for_selection": row.get("reason_for_selection"),
            "heavy": heavy,
            "light": light,
            "mutations": muts,
            "structure": structure,
            "measured": measured,
            "developability": {
                "netsolp_solubility_min": _num(row.get("netsolp_solubility_min"))
                or _num(s_row.get("netsolp_solubility_min")),
                "netsolp_heavy": _num(s_row.get("netsolp_solubility_heavy")),
                "netsolp_light": _num(s_row.get("netsolp_solubility_light")),
                "solubility_flag": s_row.get("solubility_flag") or row.get("liability_flags"),
                "cysteine_count": _num(row.get("cysteine_count")),
            },
            "thermostability_proxy": {
                "value": _num(row.get("predicted_ddg")) or _num(d_row.get("predicted_ddg")),
                "basis": row.get("thermostability_basis") or d_row.get("thermostability_basis"),
                "measured": False,
            },
            "novelty_report": {
                "min_edit_distance": _num(n_row.get("min_edit_distance")
                                          or n_row.get("min_mutations")),
                "eligible": n_row.get("eligible") or n_row.get("passes"),
            },
            "axis1": axis1,
            "contacts_kept_pos": p_row.get("contacts_kept_pos"),
            "contacts_lost": p_row.get("contacts_lost"),
            "improvement": improvement,
            "unavailable": {
                "iptm": "hosted co-folders report no ipTM (forge.py schema, 14 Nov)",
                "min_ipae": "needs Apheris Foundry refold-score on the VM",
                "thermostability": "no hosted thermostability predictor; the column is an "
                                   "ESM-2 pseudo-likelihood proxy and says so",
            },
        })

    designs.sort(key=lambda d: (d["rank"] is None, d["rank"] or 0))

    # Cohort context, so a single design can be read against its batch.
    def spread(path):
        vals = [d["measured"].get(path) for d in designs]
        vals = [v for v in vals if v is not None]
        if not vals:
            return None
        return {"n": len(vals), "min": min(vals), "median": statistics.median(vals),
                "max": max(vals)}

    return {
        "target": {
            "name": "HER2 (ERBB2) extracellular domain, subdomain IV",
            "pdb": "1N8Z",
            "epitope_residues": B.HER2_EPITOPE,
            "epitope_source": "docs/epitope.md -- 1N8Z, 4.5 A heavy-atom, whole Fab, 19 residues",
            "fasta": str((REPO / "data/target/1n8z.fasta").relative_to(REPO))
            if (REPO / "data/target/1n8z.fasta").is_file() else None,
        },
        "baseline": base,
        "parent": {"name": "trastuzumab", "heavy": B.TZ_VH, "light": B.TZ_VL,
                   "cdrh3": B.TZ_CDRH3, "cdrh3_window": [B.CDRH3_START, 107],
                   "paratope": {str(k): v[0] for k, v in sorted(B.CDRH3_CONTACTS.items())}},
        "lanes": B.lane_status(),
        "cohort": {"n_contacts": spread("n_contacts"),
                   "n_epitope_hit": spread("n_epitope_hit"),
                   "binder_plddt": spread("binder_plddt")},
        "designs": designs,
        # relative_to raises for a path outside the repo, and --submission may well point
        # outside it, so fall back to the absolute path rather than dying on a label.
        "source": {"submission": str(sub_path.relative_to(REPO))
                   if sub_path.is_relative_to(REPO) else str(sub_path),
                   "n_designs": len(designs),
                   "n_with_structure": sum(1 for d in designs if d["structure"]["available"])},
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    cat = load_catalog(a.submission)
    if not a.summary:
        print(json.dumps(cat, indent=2))
        raise SystemExit(0)

    b = cat["baseline"]
    print(f"target {cat['target']['name']}  epitope {len(cat['target']['epitope_residues'])} residues")
    if b.get("available"):
        print(f"baseline trastuzumab VH on 1N8Z: {b['n_epitope_hit']}/"
              f"{len(cat['target']['epitope_residues'])} epitope residues, "
              f"{b['n_contacts']} contacts")
    print(f"{cat['source']['n_designs']} designs, "
          f"{cat['source']['n_with_structure']} with a structure\n")
    print(f"{'rank':<5}{'design_id':<36}{'cdrh3':<11}{'mut':<5}{'par':<5}"
          f"{'epi':<8}{'d_epi':<7}{'contacts':<9}{'pLDDT':<7}struct")
    for d in cat["designs"]:
        m, mu = d["measured"], d["mutations"]
        imp = d["improvement"].get("epitope_recovery", {})
        epi = m.get("n_epitope_hit")
        delta = imp.get("delta")
        n_epi = len(cat["target"]["epitope_residues"])
        print(f"{d['rank'] or '-':<5}{d['design_id'][:35]:<36}{mu['cdrh3_design']:<11}"
              f"{mu['cdrh3_mutations']:<5}{str(mu['paratope_kept']) + '/4':<5}"
              f"{(f'{int(epi)}/{n_epi}' if epi is not None else '-'):<8}"
              f"{(f'{int(delta):+d}' if delta is not None else '-'):<7}"
              f"{(int(m['n_contacts']) if m.get('n_contacts') is not None else '-'):<9}"
              f"{(m.get('binder_plddt') or '-'):<7}"
              f"{'yes' if d['structure']['available'] else 'no'}")
