#!/usr/bin/env python
"""1N8Z: chain inventory, trastuzumab epitope on HER2, paratope, dSASA burial."""
import sys, csv, json
from collections import defaultdict
from Bio.PDB import PDBParser, Selection
from Bio.PDB.Polypeptide import is_aa
from Bio.PDB.SASA import ShrakeRupley
from Bio.PDB.NeighborSearch import NeighborSearch
from Bio.Data.IUPACData import protein_letters_3to1

OUT = "/private/tmp/claude-501/-Users-josef-Developer-Fab4/1a5e8913-7572-4a34-bed2-fe001b07f4e7/scratchpad/epitope"
PDB = OUT + "/1n8z.pdb"

def one(resname):
    return protein_letters_3to1.get(resname.capitalize(), "X")

p = PDBParser(QUIET=True)
s = p.get_structure("1n8z", PDB)
model = s[0]

report = {}

# ---------- 0. hetero inventory ----------
het = defaultdict(int)
for ch in model:
    for r in ch:
        if r.id[0] != " ":
            het[(ch.id, r.id[0].strip(), r.get_resname())] += 1
report["hetero_groups"] = {f"{c}/{h}/{n}": v for (c, h, n), v in sorted(het.items())}

# ---------- 1. chain inventory ----------
# SEQRES from header
seqres = defaultdict(list)
with open(PDB) as fh:
    for line in fh:
        if line.startswith("SEQRES"):
            cid = line[11]
            seqres[cid] += line[19:70].split()
missing = defaultdict(list)
with open(PDB) as fh:
    for line in fh:
        if line.startswith("REMARK 465") and len(line) > 26:
            f = line[10:].split()
            if len(f) == 3 and len(f[0]) == 3 and len(f[1]) == 1 and f[2].lstrip("-").isdigit():
                missing[f[1]].append((int(f[2]), f[0]))

chains = {}
for ch in model:
    aas = [r for r in ch if r.id[0] == " " and is_aa(r, standard=True)]
    if not aas:
        continue
    nums = [r.id[1] for r in aas]
    icodes = sorted({r.id[2] for r in aas if r.id[2] != " "})
    seq = "".join(one(r.get_resname()) for r in aas)
    chains[ch.id] = dict(
        observed_residues=len(aas),
        seqres_length=len(seqres.get(ch.id, [])),
        resnum_range=[min(nums), max(nums)],
        insertion_codes=icodes,
        unresolved_from_REMARK465=[f"{n}{r}" for n, r in missing.get(ch.id, [])],
        n_unresolved=len(missing.get(ch.id, [])),
        sequence=seq,
    )
report["chains"] = chains

# ---------- evidence for chain identity (from structure, not assumption) ----------
MOTIFS = {
    "IgG1_CH1_start_ASTKGPSVFPLAP": "ASTKGPSVFPLAP",
    "IgG_kappa_CL_start_RTVAAPSVFIFPPS": "RTVAAPSVFIFPPS",
    "IgG_kappa_CL_end_SFNRGEC": "SFNRGEC",
    "trastuzumab_CDRH3_WGGDGFYAMDY": "WGGDGFYAMDY",
    "trastuzumab_CDRH2_core_RIYPTNGYTR": "RIYPTNGYTR",
    "trastuzumab_CDRL3_QQHYTTPPT": "QQHYTTPPT",
    "Ig_FR2_WVRQAP": "WVRQAP",
    "Ig_kappa_FR2_WYQQKP": "WYQQKP",
}
evid = {}
for cid, d in chains.items():
    hits = {k: d["sequence"].find(v) for k, v in MOTIFS.items()}
    evid[cid] = {k: (v + 1 if v >= 0 else None) for k, v in hits.items()}  # 1-based index in observed seq
report["identity_motif_evidence_1based_index_in_observed_seq"] = evid

# ---------- interchain contact counts (heavy atoms, 4.5 A) ----------
def heavy_atoms(cids):
    out = []
    for cid in cids:
        for r in model[cid]:
            if r.id[0] != " " or not is_aa(r, standard=True):
                continue
            for a in r:
                if a.element != "H":
                    out.append(a)
    return out

cids = sorted(chains)
pair_counts = {}
for i in range(len(cids)):
    for j in range(i + 1, len(cids)):
        A, B = heavy_atoms([cids[i]]), heavy_atoms([cids[j]])
        ns = NeighborSearch(B)
        n = 0
        rp = set()
        for a in A:
            nb = ns.search(a.coord, 4.5)
            n += len(nb)
            for b in nb:
                rp.add((a.get_parent().id[1], b.get_parent().id[1]))
        pair_counts[f"{cids[i]}-{cids[j]}"] = {
            "heavy_atom_pairs_<=4.5A": n, "residue_pairs_<=4.5A": len(rp)}
report["interchain_contacts"] = pair_counts

# ---------- 2/3. epitope + paratope ----------
# antigen = chain whose sequence lacks Ig motifs and is longest -> decided below from evidence, but
# computed for all three roles so the data speaks for itself.
ANTIGEN = "C"
FAB = ["A", "B"]

def contacts(cutoff):
    """return {(chain,resnum,icode): {resname, min_dist, partners:{chain:min_dist}}} for both sides"""
    ag_atoms = heavy_atoms([ANTIGEN])
    ns_ag = NeighborSearch(ag_atoms)
    epi = {}
    para = {}
    for fc in FAB:
        for r in model[fc]:
            if r.id[0] != " " or not is_aa(r, standard=True):
                continue
            for a in r:
                if a.element == "H":
                    continue
                for b in ns_ag.search(a.coord, cutoff):
                    d = float(a - b)
                    rb = b.get_parent()
                    ke = (ANTIGEN, rb.id[1], rb.id[2], rb.get_resname())
                    e = epi.setdefault(ke, {"min": d, "by": {}})
                    e["min"] = min(e["min"], d)
                    e["by"][fc] = min(e["by"].get(fc, 9e9), d)
                    kp = (fc, r.id[1], r.id[2], r.get_resname())
                    q = para.setdefault(kp, {"min": d, "by": {}})
                    q["min"] = min(q["min"], d)
                    q["by"][ANTIGEN] = min(q["by"].get(ANTIGEN, 9e9), d)
    return epi, para

epi45, para45 = contacts(4.5)
epi50, para50 = contacts(5.0)

def fmt(d):
    return [
        {"chain": k[0], "resnum": k[1], "icode": k[2].strip(), "resname": k[3],
         "one_letter": one(k[3]), "min_distance": round(v["min"], 2),
         "contacting_chains": {c: round(x, 2) for c, x in sorted(v["by"].items())}}
        for k, v in sorted(d.items(), key=lambda kv: (kv[0][1], kv[0][2]))
    ]

report["epitope_4.5A"] = fmt(epi45)
report["epitope_5.0A"] = fmt(epi50)
report["paratope_4.5A"] = fmt(para45)
report["paratope_5.0A"] = fmt(para50)

# ---------- 4. dSASA ----------
sr = ShrakeRupley()  # defaults: probe 1.40 A, n_points 100

def strip_copy(cids):
    import copy
    st = copy.deepcopy(model)
    for ch in list(st):
        if ch.id not in cids:
            st.detach_child(ch.id)
    for ch in st:
        for r in list(ch):
            if r.id[0] != " " or not is_aa(r, standard=True):
                ch.detach_child(r.id)
    return st

def sasa_per_res(cids):
    st = strip_copy(cids)
    sr.compute(st, level="R")
    return {(ch.id, r.id[1], r.id[2]): r.sasa for ch in st for r in ch}

complex_sasa = sasa_per_res(["A", "B", "C"])
ag_free = sasa_per_res(["C"])
fab_free = sasa_per_res(["A", "B"])   # Fab alone: H-L interface not counted as burial

dsasa = {}
for k, v in ag_free.items():
    dsasa[k] = v - complex_sasa[k]
for k, v in fab_free.items():
    dsasa[k] = v - complex_sasa[k]
report["sasa_method"] = {
    "implementation": "Bio.PDB.SASA.ShrakeRupley (defaults: probe_radius=1.40, n_points=100)",
    "dSASA_definition": "SASA(unbound reference) - SASA(ABC complex), heavy atoms only, waters removed",
    "unbound_reference_HER2": "chain C alone",
    "unbound_reference_Fab": "chains A+B together (so the H-L interface is not scored as burial)",
}

# ---------- CSV ----------
csv_path = OUT + "/1n8z_interface_residues.csv"
rows = []
seen = set()
for tag, dd in (("epitope", epi50), ("paratope", para50)):
    for k, v in sorted(dd.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        key = (k[0], k[1], k[2])
        rows.append({
            "side": tag,
            "chain": k[0],
            "resnum": k[1],
            "icode": k[2].strip(),
            "resname": k[3],
            "one_letter": one(k[3]),
            "min_distance": round(v["min"], 2),
            "within_4.5A": "yes" if (k in epi45 or k in para45) else "no",
            "contacting_chain": ";".join(f"{c}:{round(x,2)}" for c, x in sorted(v["by"].items())),
            "dsasa_A2": round(dsasa.get(key, float("nan")), 1),
            "sasa_unbound_A2": round((ag_free.get(key) if k[0] == ANTIGEN else fab_free.get(key)), 1),
            "sasa_complex_A2": round(complex_sasa.get(key), 1),
        })
with open(csv_path, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

report["epitope_hotspots_by_dsasa"] = sorted(
    [{"resnum": r["resnum"], "resname": r["resname"], "one_letter": r["one_letter"],
      "dsasa_A2": r["dsasa_A2"], "min_distance": r["min_distance"],
      "contacting_chain": r["contacting_chain"], "within_4.5A": r["within_4.5A"]}
     for r in rows if r["side"] == "epitope"],
    key=lambda x: -x["dsasa_A2"])
report["paratope_hotspots_by_dsasa"] = sorted(
    [{"chain": r["chain"], "resnum": r["resnum"], "resname": r["resname"],
      "dsasa_A2": r["dsasa_A2"], "min_distance": r["min_distance"], "within_4.5A": r["within_4.5A"]}
     for r in rows if r["side"] == "paratope"],
    key=lambda x: -x["dsasa_A2"])
report["total_buried_sasa_A2"] = {
    "HER2_chain_C": round(sum(ag_free[k] - complex_sasa[k] for k in ag_free), 1),
    "Fab_chains_A+B": round(sum(fab_free[k] - complex_sasa[k] for k in fab_free), 1),
}

json_path = OUT + "/1n8z_epitope_report.json"
with open(json_path, "w") as fh:
    json.dump(report, fh, indent=1)

# ---------- console summary ----------
def line(lst):
    return " ".join(f"{r['one_letter']}{r['resnum']}{r['icode']}" for r in lst)
print("HETERO:", report["hetero_groups"])
for cid, d in sorted(chains.items()):
    print(f"\nCHAIN {cid}: observed={d['observed_residues']} seqres={d['seqres_length']} "
          f"range={d['resnum_range']} icodes={d['insertion_codes']} unresolved={d['n_unresolved']}")
    print("  seq:", d["sequence"])
    print("  motifs:", {k: v for k, v in evid[cid].items() if v})
    if d["n_unresolved"]:
        print("  missing:", ",".join(d["unresolved_from_REMARK465"]))
print("\nINTERCHAIN:", json.dumps(pair_counts))
print("\nEPITOPE 4.5A (n=%d):" % len(report["epitope_4.5A"]), line(report["epitope_4.5A"]))
print("\nEPITOPE 5.0A (n=%d):" % len(report["epitope_5.0A"]), line(report["epitope_5.0A"]))
for r in report["epitope_4.5A"]:
    print("   %s%-4s min=%.2f  %s" % (r["one_letter"], r["resnum"], r["min_distance"], r["contacting_chains"]))
print("\nEPITOPE 5.0A-only additions:",
      line([r for r in report["epitope_5.0A"] if (ANTIGEN, r["resnum"], r["icode"] or " ", r["resname"]) not in epi45]))
for side, cl in (("4.5", para45), ("5.0", para50)):
    print("\nPARATOPE %sA (n=%d):" % (side, len(cl)))
    for fc in FAB:
        sub = [r for r in fmt(cl) if r["chain"] == fc]
        print("  chain %s (n=%d): %s" % (fc, len(sub), line(sub)))
print("\nBURIED SASA:", report["total_buried_sasa_A2"])
print("\nTOP EPITOPE dSASA:")
for r in report["epitope_hotspots_by_dsasa"][:20]:
    print("   %s%-4s dSASA=%7.1f  min=%.2f  %s  <=4.5A:%s" % (
        r["one_letter"], r["resnum"], r["dsasa_A2"], r["min_distance"], r["contacting_chain"], r["within_4.5A"]))
print("\nTOP PARATOPE dSASA:")
for r in report["paratope_hotspots_by_dsasa"][:20]:
    print("   %s %s%-4s dSASA=%7.1f min=%.2f <=4.5A:%s" % (
        r["chain"], r["resname"], r["resnum"], r["dsasa_A2"], r["min_distance"], r["within_4.5A"]))
print("\nWROTE", csv_path, json_path)
