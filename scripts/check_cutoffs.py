import numpy as np
from Bio.PDB import PDBParser
from Bio.PDB.Polypeptide import is_aa
m = PDBParser(QUIET=True).get_structure("x","/private/tmp/claude-501/-Users-josef-Developer-Fab4/1a5e8913-7572-4a34-bed2-fe001b07f4e7/scratchpad/epitope/1n8z.pdb")[0]
def atoms(cids):
    out=[]
    for c in cids:
        for r in m[c]:
            if r.id[0]==" " and is_aa(r,standard=True):
                for a in r:
                    if a.element!="H": out.append((c,r.id[1],r.get_resname(),a.coord))
    return out
ag=atoms(["C"]); fab=atoms(["A","B"])
AG=np.array([a[3] for a in ag]); FB=np.array([a[3] for a in fab])
D=np.linalg.norm(AG[:,None,:]-FB[None,:,:],axis=2)
per_ag_min={}
for i,(c,n,rn,_) in enumerate(ag):
    d=D[i].min()
    per_ag_min[(n,rn)]=min(per_ag_min.get((n,rn),9e9),d)
for cut in (4.0,4.5,5.0,5.5,6.0):
    sel=sorted([k for k,v in per_ag_min.items() if v<=cut])
    print(cut, len(sel), " ".join(f"{k[1]}{k[0]}" for k in sel))
print("\nHER2 residues with min dist 4.5-6.0:")
for k,v in sorted(per_ag_min.items()):
    if 4.5 < v <= 6.0: print(f"  {k[1]}{k[0]} {v:.2f}")
