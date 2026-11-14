#!/usr/bin/env python3
"""What this project actually produced, assembled from the files on disk.

The design-by-design panels answer "is this candidate any good". This answers the other
question a demo and an evaluator both ask in the first minute: *what did you build, what
was really measured, and where is the evidence*. Everything here is read off the
filesystem at request time -- no network, no cost, nothing cached that can go stale
against the repo -- so it is also the honest answer to "is that number real?": every row
carries the file it came from.

Three rules it follows, because they are the ones that make a dashboard lie:

  * A count of rows in a score table is not a count of designs that carry a score. Joins
    miss. So coverage is counted over the candidate pool, by joining, the same way
    pipeline/score/rank.py counts it.
  * Measured and estimated never share a column. Each axis says which lane measured it, or
    says it is absent and what would fill it.
  * Nothing here starts a job or spends credit, so it is safe to open on a projector.

    python3 viz/overview.py            # the whole thing as text
    python3 viz/overview.py --json     # the same, as the viewer's /api/overview sees it
"""

from __future__ import annotations

import csv
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
ROOT = REPO.parent                       # participant-05/, which holds results/ and runs
REPORTS = REPO / "reports"
DESIGNS = REPO / "designs"
DOCS = REPO / "docs"
RESULTS = ROOT / "results"
NEBIUS_RUNS = ROOT / "nebius-runs"


def _rows(p: pathlib.Path) -> list[dict]:
    if not p.is_file():
        return []
    try:
        with p.open(newline="") as fh:
            return list(csv.DictReader(fh))
    except (OSError, UnicodeDecodeError, csv.Error):
        return []


def _num(v):
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return f if f == f else None         # drop NaN


def _rel(p: pathlib.Path) -> str:
    """Repo-relative where possible, so a path reads the way it is typed in a command.

    results/ and nebius-runs/ sit beside the repo rather than inside it, so they come back
    with the ../ that a shell would actually need from the repo root.
    """
    for base, prefix in ((REPO, ""), (ROOT, "../")):
        try:
            return prefix + str(p.relative_to(base))
        except ValueError:
            continue
    return str(p)


def _first_doc_line(p: pathlib.Path) -> str:
    """The first heading or sentence of a doc, for a one-line label."""
    try:
        for line in p.read_text(errors="replace").splitlines():
            line = line.strip().lstrip("#").strip()
            if line and not line.startswith(("<!--", "---", "|", "<")):
                return line[:160]
    except OSError:
        pass
    return ""


def _docstring_line(p: pathlib.Path) -> str:
    """A python file's first docstring line, for the stage table."""
    try:
        text = p.read_text(errors="replace")
    except OSError:
        return ""
    for q in ('"""', "'''"):
        i = text.find(q)
        if 0 <= i < 400:
            rest = text[i + 3:]
            end = rest.find(q)
            body = (rest[:end] if end > 0 else rest).strip()
            return (body.splitlines() or [""])[0][:200]
    return ""


# ---------------------------------------------------------------------------

def axes(designs: list[dict], jf_by_id: dict, refold_by_seq: dict,
         ddg: dict, para: dict, contacts: dict) -> list[dict]:
    """The three judged axes, counted over the candidate pool by joining.

    Counting rows in a score table instead of joining is the exact blindness rank.py was
    written to fix: a table full of ids that join to nothing reads as full coverage.
    """
    n = len(designs) or 1
    with_axis1, lanes1 = 0, set()
    for d in designs:
        did, heavy = d.get("design_id", ""), (d.get("sequence") or "").strip()
        row = jf_by_id.get(did) or refold_by_seq.get(heavy) or {}
        if _num(row.get("min_ipae")) is not None or _num(row.get("iptm")) is not None:
            with_axis1 += 1
            lanes1.add("JapanFold af2ig" if did in jf_by_id else "VM refold-score")
    with_axis2 = sum(1 for d in designs
                     if (para.get(d.get("design_id", "")) or {}).get("contacts_kept")
                     not in (None, ""))
    with_geom = sum(1 for d in designs
                    if _num((contacts.get(d.get("design_id", "")) or {})
                            .get("cofold_epitope_frac")) is not None
                    or _num(d.get("cofold_epitope_frac")) is not None)
    with_axis3 = sum(1 for d in designs
                     if _num((ddg.get(d.get("design_id", "")) or {})
                             .get("predicted_ddg")) is not None)

    return [
        {
            "axis": 1, "name": "Binding", "unit": "ipTM / interface pAE (A)",
            "n_designs": with_axis1, "n_total": len(designs),
            "coverage": round(with_axis1 / n, 3),
            "measured_by": sorted(lanes1) or [],
            "state": "measured" if with_axis1 else "absent",
            "evidence": ([_rel(REPORTS / "japanfold-af2ig-metrics.csv")]
                         if jf_by_id else []) +
                        [_rel(REPORTS / "b1_refold_metrics.csv")],
            "note": ("AF2-IG on each design's own co-fold: deterministic, no MSA, no "
                     "sampling." if jf_by_id else
                     "The hosted co-folders return no ipTM and no PAE "
                     "(docs/tools-nebius.md), which is why the submission carries n/a. "
                     "Fill it with: python3 viz/japanfold.py --score-af2ig --all --yes"),
        },
        {
            "axis": 2, "name": "Epitope", "unit": "CDRH3-HER2 contacts kept (of 4)",
            "n_designs": with_axis2, "n_total": len(designs),
            "coverage": round(with_axis2 / n, 3),
            "measured_by": ["paratope_check.py (1N8Z, 4.5 A)"] if with_axis2 else [],
            "state": "measured" if with_axis2 else "absent",
            "evidence": [_rel(p) for p in sorted(REPORTS.glob("*-paratope.csv"))],
            "note": (f"Plus the geometric read on {with_geom} co-folded complexes: which of "
                     f"the 19 epitope residues the binder actually reaches "
                     f"({_rel(REPORTS / 'cofold-contacts.csv')}). A proxy for the binding "
                     f"assay, labelled as one."),
        },
        {
            "axis": 3, "name": "Thermostability", "unit": "predicted ddG (proxy)",
            "n_designs": with_axis3, "n_total": len(designs),
            "coverage": round(with_axis3 / n, 3),
            "measured_by": ["ESM-2 pseudo-likelihood (Nebius)"] if with_axis3 else [],
            "state": "proxy" if with_axis3 else "absent",
            "evidence": [_rel(REPORTS / "esm2-axis3-ddg.csv")],
            "note": ("No hosted thermostability predictor exists on the lanes we have, so "
                     "this is a sequence-likelihood proxy and says so in every row it "
                     "appears in. StaB-ddG inputs are prepared in "
                     f"{_rel(REPORTS / 'stab_ddg_request.json')}."),
        },
    ]


def gaps(designs: list[dict]) -> dict:
    """Designs in the submission with no structure behind them, and why -- by name.

    This is the question a reviewer asks within a minute of seeing "20 designs, 18
    folded", and the answer was sitting in two places that disagreed: the submission says
    20, results/cofold/ holds 18, and nebius-runs/ claimed all 24 jobs were still queued
    because the records are written at submit and never re-polled. So the reason is read
    from the run record for that exact design, and if the record still says `queued` this
    says so rather than inventing a cause (scripts/reconcile_runs.py refreshes them).
    """
    unfolded = []
    for d in designs:
        did = d.get("design_id", "")
        if (RESULTS / "cofold" / did / "model.cif").is_file():
            continue
        rec_path = NEBIUS_RUNS / f"cf-{did}.json"
        rec = {}
        if rec_path.is_file():
            try:
                rec = json.loads(rec_path.read_text())
            except (OSError, json.JSONDecodeError):
                rec = {}
        state = rec.get("state") or ("no run record" if not rec else "unknown")
        if state == "queued" and rec.get("state_at_submit") is None:
            why = ("the record still says queued because it was written at submit and "
                   "never re-polled; run scripts/reconcile_runs.py to find out")
        elif state == "failed":
            why = (rec.get("error") or "the hosted lane failed this job")
        elif state == "no run record":
            why = "no co-fold was ever submitted for this design"
        else:
            why = f"hosted co-fold {state}"
        # Was the structure the only thing lost? The design's sequence-level scores are
        # unaffected, and that distinction decides whether the row can still be submitted.
        unfolded.append({
            "design_id": did, "state": state, "why": why,
            "model": rec.get("model"), "operation_id": rec.get("operation_id"),
            "record": _rel(rec_path) if rec_path.is_file() else None,
            "inputs_implicated": False if state == "failed" else None,
            "fix": (f"python3 viz/japanfold.py --fold {did} --model openfold3 --yes"
                    if state == "failed" else None),
        })
    return {
        "n_unfolded": len(unfolded),
        "unfolded": unfolded,
        "consequence": (
            "A design with no complex keeps its sequence-level scores (axis 2 paratope, "
            "axis 3 proxy, developability) and loses only the geometric read and axis 1: "
            "af2ig scores a complex you already have, so it cannot score these until they "
            "are folded on another lane." if unfolded else
            "Every submitted design has a co-folded complex behind it."),
    }


def stages() -> list[dict]:
    """The pipeline, in the order it runs, with what each stage left behind."""
    out = []
    for p in sorted((REPO / "pipeline").glob("[0-9]*.py")):
        out.append({"stage": p.stem.split("_")[0], "script": _rel(p),
                    "what": _docstring_line(p)})
    extra = [
        (REPO / "pipeline" / "score" / "cofold_contacts.py", "score"),
        (REPO / "pipeline" / "score" / "paratope_check.py", "score"),
        (REPO / "pipeline" / "score" / "rank.py", "rank"),
        (HERE / "japanfold.py", "axis 1"),
    ]
    for p, label in extra:
        if p.is_file():
            out.append({"stage": label, "script": _rel(p), "what": _docstring_line(p)})
    return out


def artifacts() -> dict:
    """Every table, run record and structure the project produced, grouped and counted."""
    def table(p: pathlib.Path) -> dict:
        rows = _rows(p)
        return {"path": _rel(p), "name": p.name, "rows": len(rows),
                "columns": len(rows[0]) if rows else 0,
                "bytes": p.stat().st_size if p.is_file() else 0}

    report_tables = [table(p) for p in sorted(REPORTS.glob("*.csv"))]
    report_other = [{"path": _rel(p), "name": p.name,
                     "bytes": p.stat().st_size}
                    for p in sorted(REPORTS.iterdir())
                    if p.is_file() and p.suffix != ".csv"]

    cofolds = sorted(d.name for d in (RESULTS / "cofold").iterdir()
                     if d.is_dir() and (d / "model.cif").is_file()) \
        if (RESULTS / "cofold").is_dir() else []
    jf_root = RESULTS / "japanfold"
    jf_scores = sorted(p.parent.name for p in jf_root.glob("af2ig/*/score.json")) \
        if jf_root.is_dir() else []
    jf_folds = sorted(_rel(p.parent) for p in jf_root.glob("*/*/model.cif")) \
        if jf_root.is_dir() else []
    runs = sorted(p.name for p in NEBIUS_RUNS.glob("*.json")) \
        if NEBIUS_RUNS.is_dir() else []

    return {
        "design_tables": [table(p) for p in sorted(DESIGNS.glob("*.csv"))],
        "report_tables": report_tables,
        "report_other": report_other,
        "docs": [{"path": _rel(p), "name": p.name, "title": _first_doc_line(p)}
                 for p in sorted(DOCS.glob("*.md"))],
        "cofold_structures": {"n": len(cofolds), "ids": cofolds,
                              "path": _rel(RESULTS / "cofold")},
        "japanfold_scored": {"n": len(jf_scores), "ids": jf_scores,
                             "path": _rel(jf_root / "af2ig")},
        "japanfold_folds": {"n": len(jf_folds), "paths": jf_folds},
        "nebius_runs": {"n": len(runs), "ids": runs, "path": _rel(NEBIUS_RUNS)},
        "totals": {
            "csv_tables": len(report_tables) + len(list(DESIGNS.glob("*.csv"))),
            "report_rows": sum(t["rows"] for t in report_tables),
            "docs": len(list(DOCS.glob("*.md"))),
            "structures": len(cofolds) + len(jf_folds),
            "run_records": len(runs),
        },
    }


def japanfold_state() -> dict:
    """What the af2ig lane has on disk. Reads no network, so it is free on page load."""
    import japanfold as J                               # local: no network at import

    rows = _rows(J.METRICS_CSV)
    jobs = {}
    for r in rows:
        if r.get("job_id"):
            jobs.setdefault(r["job_id"], 0)
            jobs[r["job_id"]] += 1
    batch_dir = J.OUT_ROOT / "af2ig" / "_jobs"
    submits = sorted((p.name for p in batch_dir.iterdir() if p.is_dir()), reverse=True) \
        if batch_dir.is_dir() else []
    return {
        "metrics_csv": _rel(J.METRICS_CSV),
        "metrics_exists": J.METRICS_CSV.is_file(),
        "n_measured": len(rows),
        "with_ipsae": sum(1 for r in rows if _num(r.get("ipsae")) is not None),
        "jobs": [{"job_id": k, "targets": v} for k, v in sorted(jobs.items())],
        "recent_submits": submits[:10],
        "key_present": bool(J.api_key(required=False)),
        "key_source": J._key_source(),
        "base": J.BASE,
        "commands": {
            "check": "python3 viz/japanfold.py --check",
            "estimate": "python3 viz/japanfold.py --estimate af2ig --all",
            "score_all": "python3 viz/japanfold.py --score-af2ig --all --yes",
            "watch": "python3 viz/japanfold.py --watch <JOB_ID>",
            "rank": ("python3 pipeline/score/rank.py --refold "
                     "reports/japanfold-af2ig-metrics.csv --allow-partial"),
        },
    }


def build() -> dict:
    sys.path.insert(0, str(HERE))
    import backends as B

    designs = _rows(DESIGNS / "submission.csv")
    jf_by_id = {r["query_id"]: r for r in _rows(REPORTS / "japanfold-af2ig-metrics.csv")
                if r.get("query_id")}
    refold_by_seq = {}
    for p in (REPORTS / "b1_refold_metrics.csv", REPORTS / "b2_refold_metrics.csv"):
        for r in _rows(p):
            seq = (r.get("binder_sequence") or "").strip()
            if seq:
                refold_by_seq.setdefault(seq, r)
    ddg = {r["design_id"]: r for r in _rows(REPORTS / "esm2-axis3-ddg.csv")
           if r.get("design_id")}
    para = {}
    for p in sorted(REPORTS.glob("*-paratope.csv")):
        for r in _rows(p):
            if r.get("design_id"):
                para.setdefault(r["design_id"], r)
    contacts = {r["design_id"]: r for r in _rows(REPORTS / "cofold-contacts.csv")
                if r.get("design_id")}

    batches = sorted({(d.get("design_id", "").rsplit("-her2", 1)[0] or "?")
                      for d in designs})
    arts = artifacts()
    base = B.wt_baseline()

    return {
        "project": {
            "title": "HER2 binder redesign - trastuzumab CDRH3",
            "target": "HER2 / ERBB2 extracellular subdomain IV (PDB 1N8Z chain C)",
            "parent": "trastuzumab (Fab, 1N8Z)",
            "epitope_residues": len(B.HER2_EPITOPE),
            "contact_cutoff_A": B.CONTACT_CUTOFF,
            "n_designs": len(designs),
            "batches": batches,
            "n_cofolded": arts["cofold_structures"]["n"],
            "submission": _rel(DESIGNS / "submission.csv"),
        },
        "baseline": ({"available": True,
                      "n_epitope_hit": base.get("n_epitope_hit"),
                      "of": len(B.HER2_EPITOPE),
                      "source": base.get("source"),
                      "caveat": base.get("caveat")}
                     if base.get("available") else {"available": False}),
        "axes": axes(designs, jf_by_id, refold_by_seq, ddg, para, contacts),
        "gaps": gaps(designs),
        "stages": stages(),
        "artifacts": arts,
        "japanfold": japanfold_state(),
        "lanes": B.lane_status(),
    }


def _text(o: dict) -> str:
    L = []
    p = o["project"]
    L.append(f"\n  {p['title']}")
    L.append(f"  target {p['target']}")
    L.append(f"  {p['n_designs']} designs in {len(p['batches'])} batch(es), "
             f"{p['n_cofolded']} with a co-folded complex, "
             f"{p['epitope_residues']} epitope residues at {p['contact_cutoff_A']} A")
    b = o["baseline"]
    if b.get("available"):
        L.append(f"  wild-type baseline: trastuzumab VH reaches "
                 f"{b['n_epitope_hit']}/{b['of']} epitope residues")

    L.append("\n  JUDGED AXES")
    for a in o["axes"]:
        L.append(f"   {a['axis']}. {a['name']:<16} {a['state']:<9} "
                 f"{a['n_designs']}/{a['n_total']} designs"
                 + (f"  [{', '.join(a['measured_by'])}]" if a["measured_by"] else ""))
        L.append(f"      {a['unit']}")
        if a["note"]:
            L.append(f"      {a['note'][:150]}")

    g = o["gaps"]
    if g["n_unfolded"]:
        L.append(f"\n  NOT FOLDED  {g['n_unfolded']} of {p['n_designs']}")
        for u in g["unfolded"]:
            L.append(f"   {u['design_id']}")
            L.append(f"      {u['state']}: {u['why'][:110]}")
            if u.get("fix"):
                L.append(f"      fix: {u['fix']}")
        L.append(f"   {g['consequence'][:150]}")

    L.append("\n  PIPELINE")
    for s in o["stages"]:
        L.append(f"   {s['stage']:<7} {s['script']:<46} {s['what'][:70]}")

    t = o["artifacts"]["totals"]
    L.append(f"\n  PRODUCED  {t['csv_tables']} tables ({t['report_rows']} rows), "
             f"{t['structures']} structures, {t['run_records']} run records, "
             f"{t['docs']} docs")

    j = o["japanfold"]
    L.append(f"\n  JAPANFOLD  key {'present' if j['key_present'] else 'MISSING'}"
             f"{' from ' + str(j['key_source']) if j['key_source'] else ''}")
    L.append(f"   {j['n_measured']} design(s) with a measured axis 1 "
             f"({j['with_ipsae']} with a local ipSAE) -> {j['metrics_csv']}")
    if not j["n_measured"]:
        L.append(f"   fill it:  {j['commands']['score_all']}")

    L.append("\n  LANES")
    for ln in o["lanes"]:
        L.append(f"   [{'x' if ln['ready'] else ' '}] {ln['lane']:<10} {ln['detail'][:88]}")
    return "\n".join(L) + "\n"


def main() -> int:
    o = build()
    if "--json" in sys.argv:
        print(json.dumps(o, indent=2, default=str))
    else:
        print(_text(o))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
