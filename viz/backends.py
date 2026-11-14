#!/usr/bin/env python3
"""One prediction contract, three lanes behind it.

The UI calls `predict(heavy, light, lane=...)` and always gets the same JSON shape.
What changes is who computed it:

    lane="dummy"    no GPU, no network. Reads a co-fold mmCIF from results/cofold/ when one
                    exists for this sequence and measures it; invents the rest, deterministically,
                    from a hash of the sequence. Every invented number is flagged.
    lane="vm"       the Apheris Foundry Predict Structure model inside our own VM
                    (`foundry-toolkit predict`), reached over ssh. See docs/tools-apheris.md.
    lane="nebius"   the hosted boltz2 lane via agent/nebius-scientific-ai/forge.py.

Why a dummy lane exists at all: the VM round trip is minutes to tens of minutes and sixteen
teams share the hardware. The demo must not depend on a queue. So the dummy lane is the
*same code path* with the slow part replaced, which also means the UI is exercised against
the real contract rather than against a mock that drifts from it.

The honesty rule this file enforces, matching the rest of the pipeline: a number that was
measured and a number that was invented never share a field without a flag. Every score
carries `measured: true|false` and a `basis` string, and the UI prints the basis.

    python3 backends.py --self-test
    python3 backends.py --heavy EVQ...VSS --lane dummy
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent                      # ai-antibodies-hackathon/
RESULTS = REPO.parent / "results"       # participant-05/results/
COFOLD = RESULTS / "cofold"

# ---------------------------------------------------------------------------
# Reference constants. Single source of truth, copied from the scorers so this
# module reports numbers that agree with reports/*.csv rather than its own.
# ---------------------------------------------------------------------------

# pipeline/score/paratope_check.py
TZ_VH = ("EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKG"
         "RFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS")
TZ_VL = ("DIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPKLLIYSASFLYSGVPSRFSGSRSG"
         "TDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVEIK")
# VH position (1-based) -> (wild-type residue, min distance to HER2 in 1N8Z)
CDRH3_CONTACTS = {99: ("W", 4.05), 103: ("G", 2.42), 104: ("F", 4.27), 105: ("Y", 3.32)}
# The generator's mutable span, from pipeline/score/paratope_check.py: VH 99-107,
# 1-based and inclusive. Verified against reports/*-paratope.csv -- the `cdrh3` column
# there is exactly heavy[98:107], so this is the convention the whole pipeline counts in.
CDRH3_START = 99
CDRH3_WINDOW = range(CDRH3_START, 108)
TZ_CDRH3 = TZ_VH[CDRH3_START - 1:107]   # WGGDGFYAM

# pipeline/score/cofold_contacts.py -- PDB 1N8Z, 4.5 A, subdomain IV, auth numbering
HER2_EPITOPE = [557, 558, 560, 561, 563, 570, 571, 573, 593, 594, 595, 596,
                598, 599, 600, 601, 602, 603, 604]
CONTACT_CUTOFF = 4.5

BINDER_CHAIN, LIGHT_CHAIN, TARGET_CHAIN = "H", "L", "C"


def score(value, *, measured: bool, basis: str, unit: str = "") -> dict:
    """A score is never a bare number here. It carries where it came from."""
    return {"value": value, "measured": measured, "basis": basis, "unit": unit}


# ---------------------------------------------------------------------------
# mmCIF reading
# ---------------------------------------------------------------------------

def parse_cif_atoms(path) -> list[tuple]:
    """(chain, resseq, comp, atom_name, element, x, y, z, bfactor) for heavy atoms.

    Same loop reader and same auth_* preference as pipeline/score/cofold_contacts.py,
    so contact counts from this module match reports/cofold-contacts.csv exactly.
    """
    cols: dict[str, int] = {}
    header: list[str] = []
    rows: list[list[str]] = []
    in_loop = False
    for line in pathlib.Path(path).read_text().splitlines():
        s = line.strip()
        if s.startswith("_atom_site."):
            header.append(s.split(".", 1)[1])
            in_loop = True
            continue
        if in_loop and header and not s.startswith("_"):
            if s.startswith("#") or not s:
                if rows:
                    break
                continue
            parts = s.split()
            if len(parts) < len(header):
                continue
            if not cols:
                cols = {n: i for i, n in enumerate(header)}
            rows.append(parts)
    if not cols:
        raise ValueError(f"{path}: no _atom_site loop found")

    def pick(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    ci = pick("auth_asym_id", "label_asym_id")
    ri = pick("auth_seq_id", "label_seq_id")
    mi = pick("label_comp_id", "auth_comp_id")
    ai = pick("label_atom_id")
    ei = pick("type_symbol")
    bi = pick("B_iso_or_equiv")
    xi, yi, zi = pick("Cartn_x"), pick("Cartn_y"), pick("Cartn_z")

    out = []
    for p in rows:
        try:
            if ei is not None and p[ei].upper() == "H":
                continue  # heavy atoms only, as the scorer does
            b = float(p[bi]) if bi is not None and p[bi] not in (".", "?") else None
            out.append((p[ci], int(p[ri]), p[mi], p[ai], p[ei],
                        float(p[xi]), float(p[yi]), float(p[zi]), b))
        except (ValueError, IndexError):
            continue
    return out


def parse_pdb_atoms(path) -> list[tuple]:
    """Same tuple shape as parse_cif_atoms, for the 1N8Z crystal baseline.

    Matches pipeline/score/epitope.py: first model only, altloc blank or A, heavy atoms,
    no waters or hetero-residues -- so the baseline is computed exactly as the epitope
    list in docs/epitope.md was.
    """
    out = []
    for line in pathlib.Path(path).read_text().splitlines():
        if line.startswith("ENDMDL"):
            break
        if not line.startswith("ATOM"):
            continue
        alt = line[16]
        if alt not in (" ", "A"):
            continue
        element = (line[76:78].strip() or line[12:16].strip()[:1]).upper()
        if element == "H":
            continue
        try:
            out.append((line[21], int(line[22:26]), line[17:20].strip(),
                        line[12:16].strip(), element,
                        float(line[30:38]), float(line[38:46]), float(line[46:54]),
                        float(line[60:66]) if line[60:66].strip() else None))
        except ValueError:
            continue
    return out


def parse_structure(path) -> list[tuple]:
    """Read either format. mmCIF from the folders, PDB for the crystal baseline."""
    return (parse_pdb_atoms(path) if str(path).lower().endswith((".pdb", ".ent"))
            else parse_cif_atoms(path))


def interface_from_cif(path, binder=BINDER_CHAIN, target=TARGET_CHAIN,
                       cutoff=CONTACT_CUTOFF) -> dict:
    """Cross-chain heavy-atom contacts. NOT ipTM and NOT min_ipae -- the hosted
    co-folders report neither (docs/tools-nebius.md), which is why we count geometry."""
    atoms = parse_structure(path)
    b = [t for t in atoms if t[0] == binder]
    c = [t for t in atoms if t[0] == target]
    if not b or not c:
        chains = sorted({t[0] for t in atoms})
        raise ValueError(f"chain {binder!r} or {target!r} absent; file has {chains}")

    cut2 = cutoff ** 2
    pairs = 0
    touched: set[int] = set()
    binder_touching: set[int] = set()
    for _, r1, _, _, _, x1, y1, z1, _ in b:
        for _, r2, _, _, _, x2, y2, z2, _ in c:
            if (x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2 < cut2:
                pairs += 1
                touched.add(r2)
                binder_touching.add(r1)

    hits = sorted(touched & set(HER2_EPITOPE))
    return {
        "n_contacts": pairs,
        "n_target_residues": len(touched),
        "n_epitope_hit": len(hits),
        "epitope_frac": round(len(hits) / len(HER2_EPITOPE), 4),
        "epitope_residues_hit": hits,
        "target_residues_touched": sorted(touched),
        "binder_residues_touching": sorted(binder_touching),
        "cutoff": cutoff,
    }


def plddt_from_cif(path, chain=BINDER_CHAIN, residues=None) -> dict:
    """Boltz-2 writes per-atom pLDDT into B_iso_or_equiv. Mean over CA atoms.

    `residues` restricts it to a span (we use the CDRH3 window), which is the number
    that actually matters: a confident framework can hide an unconfident loop.
    """
    atoms = parse_structure(path)
    want = set(residues) if residues else None
    vals = [b for ch, r, _, an, _, _, _, _, b in atoms
            if ch == chain and b is not None and an == "CA"
            and (want is None or r in want)]
    per_res = {r: b for ch, r, _, an, _, _, _, _, b in atoms
               if ch == chain and b is not None and an == "CA"}
    if not vals:
        return {"mean": None, "per_residue": {}}
    return {"mean": round(sum(vals) / len(vals), 2),
            "min": round(min(vals), 2),
            "per_residue": {str(k): round(v, 2) for k, v in sorted(per_res.items())}}


# ---------------------------------------------------------------------------
# Sequence diff: what actually changed, and where it sits in the structure
# ---------------------------------------------------------------------------

def diff_span(wt: str, mut: str) -> tuple[int, int, int]:
    """Longest common prefix/suffix trim. Returns (start_1based, wt_len, mut_len).

    Designs differ from trastuzumab only inside CDRH3, and lengths differ (the
    generator emits 9- and 10-mers), so a positional diff would be wrong past the
    first indel. Trimming both ends isolates the changed span exactly.
    """
    i = 0
    while i < min(len(wt), len(mut)) and wt[i] == mut[i]:
        i += 1
    j = 0
    while (j < min(len(wt), len(mut)) - i and wt[len(wt) - 1 - j] == mut[len(mut) - 1 - j]):
        j += 1
    return i + 1, len(wt) - i - j, len(mut) - i - j


def cdrh3_of(heavy: str) -> str:
    """CDRH3 as this pipeline counts it: the mutable window VH 99-107.

    Anchored on the window rather than on framework motif search, because that is what
    reports/*-paratope.csv contains and what abguard's mutation count was computed over.
    A length change in the loop shifts the C-terminal end only.
    """
    end = 107 + (len(heavy) - len(TZ_VH))
    return heavy[CDRH3_START - 1:max(end, CDRH3_START)]


def mutation_report(heavy: str, light: str = "") -> dict:
    """Everything the viewer needs to draw and caption the changes."""
    # The redesigned span is the generator's window, not a sequence diff: an unchanged
    # W99 is still part of the loop and the viewer must draw it as such.
    start = CDRH3_START
    wt_span, mut_span = TZ_CDRH3, cdrh3_of(heavy)
    wt_len, mut_len = len(wt_span), len(mut_span)

    # Per-position substitutions over the overlapping part of the span, plus the
    # length change called out separately. Positions are 1-based over VH and line up
    # with label_seq_id / auth_seq_id in chain H of the co-fold mmCIFs.
    subs = []
    for k in range(min(wt_len, mut_len)):
        if wt_span[k] != mut_span[k]:
            subs.append({"vh_position": start + k, "wt": wt_span[k], "design": mut_span[k]})
    indel = mut_len - wt_len

    # Hamming distance over the CDRH3 itself, the number abguard counts.
    design_cdrh3 = cdrh3_of(heavy)
    n_mut = sum(1 for a, b in zip(TZ_CDRH3, design_cdrh3) if a != b) \
        + abs(len(TZ_CDRH3) - len(design_cdrh3))

    # The four measured paratope residues inside the mutable window.
    paratope = []
    for pos, (wt_aa, dist) in sorted(CDRH3_CONTACTS.items()):
        now = heavy[pos - 1] if len(heavy) >= pos else "-"
        paratope.append({
            "vh_position": pos, "wt": wt_aa, "design": now,
            "kept": now == wt_aa,
            "distance_to_her2_in_1n8z": dist,
        })

    return {
        "cdrh3_wt": TZ_CDRH3,
        "cdrh3_design": design_cdrh3,
        "cdrh3_mutations": n_mut,
        "changed_span": {"vh_start": start, "wt": wt_span, "design": mut_span,
                         "length_change": indel},
        "substitutions": subs,
        "paratope": paratope,
        "paratope_kept": sum(1 for p in paratope if p["kept"]),
        "light_changed": bool(light) and light.strip() != TZ_VL,
        # Residue ids to highlight in chain H. Covers the whole mutable window so the
        # loop reads as a loop in 3D, not as scattered sticks.
        "highlight_vh_residues": sorted(set(
            [s["vh_position"] for s in subs]
            + [p["vh_position"] for p in paratope]
            + list(range(start, start + max(wt_len, mut_len)))
        )),
    }


# ---------------------------------------------------------------------------
# Finding an existing co-fold for a sequence
# ---------------------------------------------------------------------------

def _cofold_index() -> dict[str, pathlib.Path]:
    """design_id -> model.cif, for every co-fold we already paid for."""
    out = {}
    if COFOLD.is_dir():
        for d in sorted(COFOLD.iterdir()):
            cif = d / "model.cif"
            if cif.is_file():
                out[d.name] = cif
    return out


def _heavy_to_design_id() -> dict[str, str]:
    """Map a heavy sequence back to the design that was folded, via the paratope tables."""
    import csv
    m = {}
    for p in sorted((REPO / "reports").glob("*-paratope.csv")):
        try:
            for row in csv.DictReader(p.open()):
                h = (row.get("heavy_sequence") or "").strip()
                if h:
                    m.setdefault(h, row["design_id"])
        except Exception:
            continue
    for p in sorted((REPO / "designs").glob("*.csv")):
        try:
            for row in csv.DictReader(p.open()):
                h = (row.get("sequence") or row.get("heavy_sequence") or "").strip()
                if h:
                    m.setdefault(h, row.get("design_id", ""))
        except Exception:
            continue
    return m


def locate_cofold(heavy: str, design_id: str | None = None) -> tuple[str | None, pathlib.Path | None]:
    idx = _cofold_index()
    if design_id and design_id in idx:
        return design_id, idx[design_id]
    did = _heavy_to_design_id().get(heavy.strip())
    if did and did in idx:
        return did, idx[did]
    return did or None, None


# ---------------------------------------------------------------------------
# Deterministic stand-in numbers
# ---------------------------------------------------------------------------

def _rand_stream(seed_text: str):
    """Deterministic uniforms in [0,1) from a sequence hash. Same sequence, same
    numbers, on any machine, forever -- so a screenshot can be reproduced."""
    h = hashlib.sha256(seed_text.encode()).digest()
    i = 0
    while True:
        if i + 4 > len(h):
            h = hashlib.sha256(h).digest()
            i = 0
        yield int.from_bytes(h[i:i + 4], "big") / 2 ** 32
        i += 4


def _synthetic_scores(heavy: str, light: str) -> dict:
    """Plausible stand-ins, anchored to the ranges this batch actually produced
    (reports/cofold-contacts.csv: 148-283 contacts, 0-11 epitope hits; CDRH3 pLDDT
    from the co-fold B-factors sits around 55-80).

    These are NOT predictions. They exist so the viewer has something to draw while a
    real run is queued, and every one of them comes back with measured=false.
    """
    g = _rand_stream(heavy + "|" + light)
    u = [next(g) for _ in range(6)]
    n_contacts = int(148 + u[0] * 135)
    # Keeping the paratope should matter, so let it: the synthetic epitope count is
    # conditioned on how many of W99/G103/F104/Y105 survived.
    kept = sum(1 for p in mutation_report(heavy, light)["paratope"] if p["kept"])
    base = {0: 0.0, 1: 0.05, 2: 0.2, 3: 0.45, 4: 0.6}[kept]
    hit = int(round(len(HER2_EPITOPE) * max(0.0, min(1.0, base + (u[1] - 0.5) * 0.3))))
    return {
        "n_contacts": n_contacts,
        "n_epitope_hit": hit,
        "epitope_frac": round(hit / len(HER2_EPITOPE), 4),
        "binder_plddt": round(55 + u[2] * 25, 2),
        "cdrh3_plddt": round(50 + u[3] * 28, 2),
        "interface_pae": round(6.0 + u[4] * 4.5, 2),
        "rmsd_to_design": round(0.8 + u[5] * 2.4, 2),
    }


# ---------------------------------------------------------------------------
# The lanes
# ---------------------------------------------------------------------------

SYNTH = "SYNTHETIC stand-in from a hash of the sequence. Not a prediction."


def predict_dummy(heavy: str, light: str = "", design_id: str | None = None) -> dict:
    """Measure whatever a local co-fold already answers; invent the rest, flagged."""
    did, cif = locate_cofold(heavy, design_id)
    muts = mutation_report(heavy, light)
    synth = _synthetic_scores(heavy, light)
    scores: dict[str, dict] = {}
    structure = {"available": False, "design_id": did, "path": None, "source": None}

    if cif is not None:
        iface = interface_from_cif(cif)
        window = [p for p in muts["highlight_vh_residues"]]
        pl_all = plddt_from_cif(cif, BINDER_CHAIN)
        pl_loop = plddt_from_cif(cif, BINDER_CHAIN, residues=window)
        basis = f"MEASURED from {cif.relative_to(RESULTS.parent)} (boltz2 co-fold, {CONTACT_CUTOFF} A heavy-atom)"
        scores["n_contacts"] = score(iface["n_contacts"], measured=True, basis=basis)
        scores["n_epitope_hit"] = score(iface["n_epitope_hit"], measured=True,
                                        basis=basis + f"; {len(HER2_EPITOPE)} epitope residues from 1N8Z")
        scores["epitope_frac"] = score(iface["epitope_frac"], measured=True, basis=basis)
        scores["binder_plddt"] = score(pl_all["mean"], measured=True,
                                       basis="MEASURED: mean CA B_iso (pLDDT) over chain H of the co-fold",
                                       unit="pLDDT")
        scores["cdrh3_plddt"] = score(pl_loop["mean"], measured=True,
                                      basis="MEASURED: mean CA pLDDT over the redesigned span only",
                                      unit="pLDDT")
        # The hosted co-folders return neither ipTM nor PAE, confirmed 14 Nov with
        # `forge.py schema`. So these two stay synthetic even when the structure is real.
        scores["interface_pae"] = score(synth["interface_pae"], measured=False,
                                        basis=SYNTH + " The hosted boltz2/openfold3 lane returns "
                                              "no PAE; a real interface PAE needs the VM "
                                              "(lane=vm, RFD4 refold-score).", unit="A")
        scores["rmsd_to_design"] = score(synth["rmsd_to_design"], measured=False,
                                         basis=SYNTH + " Needs RFD4-Proteina refold-score on the VM.",
                                         unit="A")
        structure = {"available": True, "design_id": did,
                     "path": str(cif), "source": "results/cofold (boltz2, hosted lane)",
                     "epitope_residues_hit": iface["epitope_residues_hit"],
                     "target_residues_touched": iface["target_residues_touched"],
                     "binder_residues_touching": iface["binder_residues_touching"],
                     "plddt_per_residue": pl_all["per_residue"]}
    else:
        for k in ("n_contacts", "n_epitope_hit", "epitope_frac", "binder_plddt",
                  "cdrh3_plddt", "interface_pae", "rmsd_to_design"):
            scores[k] = score(synth[k], measured=False,
                              basis=SYNTH + " No co-fold exists for this sequence yet; "
                                    "run lane=vm or lane=nebius to replace it.")

    return {
        "design_id": did or "(unfolded sequence)",
        "lane": "dummy",
        "model": "dummy-v1 (local mmCIF measurement + deterministic stand-ins)",
        "any_synthetic": any(not s["measured"] for s in scores.values()),
        "mutations": muts,
        "scores": scores,
        "structure": structure,
        "heavy": heavy,
        "light": light or TZ_VL,
    }


def predict_vm(heavy: str, light: str = "", design_id: str | None = None,
               model: str | None = None, timeout: int = 1800) -> dict:
    """Apheris Foundry Predict Structure, inside our VM. Same contract out.

    Configure with env vars (nothing hard-coded, nothing secret in this file):
        FOUNDRY_SSH      user@vm-host           ssh target; omit if running ON the VM
        FOUNDRY_BIN      foundry-toolkit        default
        FOUNDRY_MODEL    openfold3              default; openfold3 is the prize condition
                                                (docs/tools-apheris.md)
        FOUNDRY_WORKDIR  ~/foundry              where to drop the request json on the VM
        FOUNDRY_TEMPLATE path to 1n8z.cif       template complex, if the model takes one

    On any failure this returns the dummy result with `lane_error` set, rather than
    throwing -- a queued or unreachable VM should degrade the demo, not break it.
    """
    bin_ = os.environ.get("FOUNDRY_BIN", "foundry-toolkit")
    ssh = os.environ.get("FOUNDRY_SSH", "").strip()
    model = model or os.environ.get("FOUNDRY_MODEL", "openfold3")
    workdir = os.environ.get("FOUNDRY_WORKDIR", "~/foundry")
    template = os.environ.get("FOUNDRY_TEMPLATE", "")

    target_fasta = REPO / "data" / "target" / "1n8z.fasta"
    request = {
        "model": model,
        "chains": [
            {"id": "H", "sequence": heavy, "type": "protein"},
            {"id": "L", "sequence": (light or TZ_VL), "type": "protein"},
        ],
        "template": template or None,
        "target_fasta": str(target_fasta) if target_fasta.exists() else None,
    }
    payload = json.dumps(request)

    # One shell line, quoted once, so it behaves the same locally and over ssh.
    remote = (f"mkdir -p {workdir} && cat > {workdir}/request.json && "
              f"{bin_} predict --request {workdir}/request.json --json")
    cmd = ["ssh", ssh, remote] if ssh else ["bash", "-lc", remote]

    try:
        if not ssh and not shutil.which(bin_):
            raise FileNotFoundError(
                f"{bin_} not on PATH and FOUNDRY_SSH is unset -- this laptop is not the VM. "
                f"Set FOUNDRY_SSH=user@vm-host (see docs/tools-apheris.md) or use lane=dummy.")
        proc = subprocess.run(cmd, input=payload, capture_output=True, text=True,
                              timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "").strip()[:800]
                               or f"exit {proc.returncode}")
        out = json.loads(proc.stdout)
    except Exception as exc:                                   # noqa: BLE001
        fallback = predict_dummy(heavy, light, design_id)
        fallback["lane_error"] = f"{type(exc).__name__}: {exc}"
        fallback["lane_attempted"] = "vm"
        return fallback

    return _from_foundry(out, heavy, light, design_id, model)


def _from_foundry(out: dict, heavy: str, light: str, design_id, model: str) -> dict:
    """Normalise a Foundry predict/refold-score payload into our contract.

    Foundry's exact key names are not in the task PDF, so we accept the obvious
    spellings and leave anything we cannot find as null rather than guessing a value.
    """
    def dig(*names):
        for n in names:
            for src in (out, out.get("scores", {}) or {}, out.get("metrics", {}) or {}):
                if isinstance(src, dict) and n in src and src[n] is not None:
                    return src[n]
        return None

    cif_path = dig("cif", "structure", "model_cif", "output_cif")
    basis = f"MEASURED on the VM: Apheris Foundry Predict Structure, model={model}"
    scores = {
        "binder_plddt": score(dig("binder_plddt", "plddt_binder"), measured=True,
                              basis=basis, unit="pLDDT"),
        "cdrh3_plddt": score(dig("cdrh3_plddt", "loop_plddt"), measured=True,
                             basis=basis, unit="pLDDT"),
        "interface_pae": score(dig("interface_pae", "min_ipae", "ipae"), measured=True,
                               basis=basis + " (RFD4 refold-score interface PAE)", unit="A"),
        "rmsd_to_design": score(dig("rmsd", "rmsd_to_design"), measured=True,
                                basis=basis, unit="A"),
    }

    structure = {"available": False, "design_id": design_id, "path": cif_path,
                 "source": f"VM Foundry {model}"}
    # If Foundry handed back a structure we can read, measure the interface ourselves
    # with the same scorer used on the hosted lane, so the two lanes stay comparable.
    if cif_path and pathlib.Path(str(cif_path)).is_file():
        try:
            iface = interface_from_cif(cif_path)
            m = f"MEASURED from the VM co-fold ({CONTACT_CUTOFF} A heavy-atom, same scorer as the hosted lane)"
            scores["n_contacts"] = score(iface["n_contacts"], measured=True, basis=m)
            scores["n_epitope_hit"] = score(iface["n_epitope_hit"], measured=True, basis=m)
            scores["epitope_frac"] = score(iface["epitope_frac"], measured=True, basis=m)
            structure.update(available=True,
                             epitope_residues_hit=iface["epitope_residues_hit"],
                             target_residues_touched=iface["target_residues_touched"],
                             binder_residues_touching=iface["binder_residues_touching"],
                             plddt_per_residue=plddt_from_cif(cif_path, BINDER_CHAIN)["per_residue"])
        except Exception as exc:                               # noqa: BLE001
            structure["note"] = f"returned structure unreadable: {exc}"

    return {
        "design_id": design_id or out.get("design_id") or "(vm run)",
        "lane": "vm-foundry",
        "model": f"foundry:{model}",
        "any_synthetic": any(s["value"] is None or not s["measured"] for s in scores.values()),
        "mutations": mutation_report(heavy, light),
        "scores": scores,
        "structure": structure,
        "raw": out,
        "heavy": heavy,
        "light": light or TZ_VL,
    }


def predict_nebius(heavy: str, light: str = "", design_id: str | None = None,
                   timeout: int = 2400) -> dict:
    """The hosted boltz2 lane via forge.py. Submits and waits; see pipeline/score/refold.sh
    for the batch version. Degrades to dummy with `lane_error`, like the VM lane."""
    forge = pathlib.Path(os.path.expanduser(
        os.environ.get("FORGE", "~/.claude/skills/nebius-scientific-ai/forge.py")))
    try:
        if not forge.is_file():
            raise FileNotFoundError(f"forge.py not found at {forge}; run agent/install.sh "
                                    "or set FORGE=/path/to/forge.py")
        creds = os.environ.get("NEBIUS_CREDS") or str(REPO.parent / "credentials.private.json")
        if not pathlib.Path(creds).is_file():
            raise FileNotFoundError(f"credentials not found at {creds}; export NEBIUS_CREDS")
        raise NotImplementedError(
            "The hosted lane is a queued submit+poll, not a request/response: use "
            "pipeline/score/refold.sh to launch it and the viewer picks the structure up "
            "from results/cofold/ when it lands. Wired here only so the UI can offer it.")
    except Exception as exc:                                   # noqa: BLE001
        fallback = predict_dummy(heavy, light, design_id)
        fallback["lane_error"] = f"{type(exc).__name__}: {exc}"
        fallback["lane_attempted"] = "nebius"
        return fallback


def wt_baseline() -> dict:
    """Trastuzumab against HER2, measured on the 1N8Z crystal with our own scorer.

    This is what "improvement" is measured against. One caveat the UI must repeat: 1N8Z is
    a crystal structure and the designs are Boltz-2 co-fold predictions, so raw contact
    COUNTS are not strictly comparable across the two. Epitope *recovery* is -- the 19
    epitope residues were defined from this very structure, so "how many of the 19 does
    the binder still touch" means the same thing on both sides.
    """
    pdb = REPO / "data" / "target" / "1n8z.pdb"
    if not pdb.is_file():
        return {"available": False,
                "note": f"{pdb} missing; fetch 1N8Z to enable the wild-type baseline"}
    iface = interface_from_cif(pdb, binder="B", target="C")   # A=VL, B=VH, C=HER2 ECD
    return {
        "available": True,
        "source": "PDB 1N8Z (crystal), chains B=VH / C=HER2 ECD, 4.5 A heavy-atom",
        "kind": "crystal",
        "cdrh3": TZ_CDRH3,
        "heavy": TZ_VH,
        "light": TZ_VL,
        "n_contacts": iface["n_contacts"],
        "n_epitope_hit": iface["n_epitope_hit"],
        "epitope_frac": iface["epitope_frac"],
        "epitope_residues_hit": iface["epitope_residues_hit"],
        "paratope_kept": 4,
        "cdrh3_mutations": 0,
        "caveat": ("crystal vs predicted co-fold: compare epitope recovery, not raw "
                   "contact counts. For a like-for-like contact count, co-fold wild-type "
                   "trastuzumab through the same lane."),
    }


def predict_japanfold(heavy: str, light: str = "", design_id: str | None = None,
                      mode: str = "af2ig", model: str = "openfold3",
                      epitope_guidance: bool = False) -> dict:
    """JapanFold: the only lane here that returns a real ipTM and interface pAE.

    mode="af2ig" scores an existing co-fold (fast, deterministic, no MSA) and is what fills
    axis 1. mode="fold" co-folds the design against HER2 from scratch with openfold3 or
    opendde-abag. Both bill the account, so the server only calls this on an explicit
    request from the UI, never while just loading a page.
    """
    sys.path.insert(0, str(HERE))
    try:
        import japanfold as J
    except ImportError as exc:                                 # noqa: BLE001
        fb = predict_dummy(heavy, light, design_id)
        fb["lane_error"] = f"japanfold client unavailable: {exc}"
        fb["lane_attempted"] = "japanfold"
        return fb

    base = predict_dummy(heavy, light, design_id)   # geometry + mutations, already measured
    did = base["design_id"]
    try:
        if mode == "fold":
            out = J.fold(heavy, light or TZ_VL, model=model, name=did,
                         epitope_guidance=epitope_guidance)
            if out.get("status") != "succeeded":
                raise RuntimeError(out.get("error") or out.get("status") or "fold failed")
            res = out.get("results") or {}
            sc = res.get("scores") or res.get("metrics") or {}
            lane_model = f"japanfold:{model}" + (" +epitope-guidance" if epitope_guidance else "")
            basis = (f"MEASURED: JapanFold {model} co-fold of VH+VL with HER2"
                     + (", sampling steered onto the 19 epitope residues" if epitope_guidance else ""))
            for key, names in (("iptm", ("iptm", "ipTM", "interface_ptm")),
                               ("interface_pae", ("interface_pae", "pae_interaction", "ipae")),
                               ("binder_plddt", ("binder_plddt", "plddt", "mean_plddt"))):
                val = next((sc[n] for n in names if sc.get(n) is not None), None)
                if val is not None:
                    base["scores"][key] = score(val, measured=True, basis=basis)
            base["japanfold"] = out
        else:
            out = J.score_af2ig(did)
            if out.get("status") != "succeeded":
                raise RuntimeError(out.get("error") or out.get("status") or "af2ig failed")
            lane_model = "japanfold:af2ig"
            if out.get("iptm") is not None:
                base["scores"]["iptm"] = score(out["iptm"], measured=True, basis=out["basis"])
            if out.get("interface_pae") is not None:
                base["scores"]["interface_pae"] = score(
                    out["interface_pae"], measured=True, basis=out["basis"], unit="A")
            if out.get("plddt") is not None:
                base["scores"]["af2ig_plddt"] = score(out["plddt"], measured=True,
                                                      basis=out["basis"], unit="pLDDT")
            base["japanfold"] = {k: v for k, v in out.items() if k != "scores_raw"}
    except Exception as exc:                                   # noqa: BLE001
        base["lane_error"] = f"{type(exc).__name__}: {exc}"
        base["lane_attempted"] = "japanfold"
        return base

    base["lane"] = "japanfold"
    base["model"] = lane_model
    base["any_synthetic"] = any(not s["measured"] for s in base["scores"].values())
    return base


LANES = {"dummy": predict_dummy, "vm": predict_vm, "nebius": predict_nebius,
         "japanfold": predict_japanfold}


def predict(heavy: str, light: str = "", lane: str = "dummy",
            design_id: str | None = None, **kw) -> dict:
    heavy = (heavy or "").strip().upper()
    light = (light or "").strip().upper()
    if not heavy:
        raise ValueError("heavy sequence is required")
    bad = set(heavy + light) - set("ACDEFGHIKLMNPQRSTVWY")
    if bad:
        raise ValueError(f"not amino acids: {''.join(sorted(bad))}")
    fn = LANES.get(lane)
    if fn is None:
        raise ValueError(f"unknown lane {lane!r}; pick one of {sorted(LANES)}")
    return fn(heavy, light, design_id, **kw)


def lane_status() -> list[dict]:
    """What the UI shows in its lane picker: which lanes can actually run right now."""
    bin_ = os.environ.get("FOUNDRY_BIN", "foundry-toolkit")
    ssh = os.environ.get("FOUNDRY_SSH", "").strip()
    forge = pathlib.Path(os.path.expanduser(
        os.environ.get("FORGE", "~/.claude/skills/nebius-scientific-ai/forge.py")))
    n_cofold = len(_cofold_index())

    jf = {"lane": "japanfold", "ready": False,
          "label": "JapanFold — af2ig / OpenFold3 (billed)",
          "detail": "no API key; see viz/README.md", "billed": True}
    try:
        sys.path.insert(0, str(HERE))
        import japanfold as J
        st = J.check()
        if not st.get("reachable"):
            jf["detail"] = f"unreachable: {st.get('error', '')[:120]}"
        elif not st.get("key_present"):
            jf["detail"] = (f"reachable, {st.get('n_predict_models')} models, but no API key. "
                            f"Put one in {J.key_path().name} or $JAPANFOLD_API_KEY "
                            f"(get it at {J.TOKEN_URL})")
        else:
            jf["ready"] = True
            bal = (st.get("account") or {})
            jf["detail"] = ("af2ig gives the ipTM + interface pAE the hosted lane cannot; "
                            "~$0.005/design. " + (f"balance {bal}" if bal else ""))
    except Exception as exc:                                   # noqa: BLE001
        jf["detail"] = f"client error: {exc}"

    return [
        jf,
        {"lane": "dummy", "ready": True,
         "label": "Dummy model (local, instant)",
         "detail": f"measures {n_cofold} existing co-folds; stand-ins elsewhere, all flagged"},
        {"lane": "vm", "ready": bool(ssh) or bool(shutil.which(bin_)),
         "label": "VM — Apheris Foundry Predict Structure",
         "detail": (f"ssh {ssh}" if ssh else
                    (f"{bin_} on PATH (running on the VM)" if shutil.which(bin_)
                     else "set FOUNDRY_SSH=user@vm-host to enable"))},
        {"lane": "nebius", "ready": False,
         "label": "Nebius hosted boltz2 (queued)",
         "detail": ("submit with pipeline/score/refold.sh; results land in results/cofold/"
                    if forge.is_file() else "forge.py not installed")},
    ]


# ---------------------------------------------------------------------------

def _self_test() -> int:
    ok = True

    def check(name, got, want):
        nonlocal ok
        good = got == want
        ok &= good
        print(f"{'PASS' if good else 'FAIL'}  {name}: got {got!r}" + ("" if good else f" want {want!r}"))

    import csv as _csv

    # Wild type against itself: zero changes, all four measured contacts kept.
    w = mutation_report(TZ_VH)
    check("wt has no substitutions", w["substitutions"], [])
    check("wt keeps 4/4 paratope", w["paratope_kept"], 4)
    check("wt cdrh3 is the VH99-107 window", w["cdrh3_design"], "WGGDGFYAM")

    # The real check: CDRH3 extraction, mutation count and paratope must agree with the
    # pipeline's own paratope tables, row for row. If this drifts, the viewer would be
    # captioning different mutations than the submission was filtered on.
    rows_checked = 0
    for p in sorted((REPO / "reports").glob("*-paratope.csv")):
        for row in _csv.DictReader(p.open()):
            h = (row.get("heavy_sequence") or "").strip()
            if not h or not row.get("cdrh3"):
                continue
            m = mutation_report(h)
            check(f"{row['design_id']} cdrh3", m["cdrh3_design"], row["cdrh3"])
            if row.get("cdrh3_mutations"):
                check(f"{row['design_id']} mutation count",
                      m["cdrh3_mutations"], int(row["cdrh3_mutations"]))
            if row.get("contacts_kept"):
                check(f"{row['design_id']} paratope kept",
                      m["paratope_kept"], int(row["contacts_kept"]))
            rows_checked += 1
            if rows_checked >= 6:
                break
        if rows_checked >= 6:
            break
    if not rows_checked:
        print("SKIP  no reports/*-paratope.csv to cross-check")

    # Determinism: stand-ins must not move between calls, or a screenshot is unreproducible.
    design = TZ_VH[:98] + "WDAPGSYSV" + TZ_VH[107:]
    check("stand-ins deterministic",
          _synthetic_scores(design, TZ_VL), _synthetic_scores(design, TZ_VL))

    # A real design must reproduce reports/cofold-contacts.csv exactly.
    import csv as _csv
    tbl = REPO / "reports" / "cofold-contacts.csv"
    if tbl.is_file():
        rows = {r["design_id"]: r for r in _csv.DictReader(tbl.open())}
        idx = _cofold_index()
        checked = 0
        for did, cif in idx.items():
            if did not in rows:
                continue
            iface = interface_from_cif(cif)
            check(f"{did} n_contacts matches report",
                  iface["n_contacts"], int(rows[did]["cofold_n_contacts"]))
            check(f"{did} epitope hits match report",
                  iface["n_epitope_hit"], int(rows[did]["cofold_n_epitope_hit"]))
            checked += 1
            if checked >= 3:
                break
        if not checked:
            print("SKIP  no overlap between results/cofold and cofold-contacts.csv")
    else:
        print("SKIP  reports/cofold-contacts.csv absent")

    print("\n" + ("all checks passed" if ok else "FAILURES above"))
    return 0 if ok else 1


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--heavy")
    ap.add_argument("--light", default="")
    ap.add_argument("--lane", default="dummy", choices=sorted(LANES))
    ap.add_argument("--design-id")
    ap.add_argument("--lanes", action="store_true", help="show which lanes are ready")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(_self_test())
    if a.lanes:
        print(json.dumps(lane_status(), indent=2))
        raise SystemExit(0)
    if not a.heavy:
        ap.error("--heavy is required (or --self-test / --lanes)")
    print(json.dumps(predict(a.heavy, a.light, a.lane, a.design_id), indent=2))
