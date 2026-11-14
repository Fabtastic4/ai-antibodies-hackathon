"""Shared helpers for the Fab4 pipeline: candidate schema, provenance, IO.

Stdlib only. Heavy deps (biopython, anarcii) are imported lazily inside the
stages that need them, so every stage stays importable and `--help`-able on a
laptop with nothing installed.

Two rules this module exists to enforce:

1. Nothing leaves a stage without provenance. Every record and every score
   carries the model, the weights, the seed and a timestamp.
2. A number we did not read is `null` with a reason, never a guess. Helpers that
   would need an unverified external API raise NotImplementedError through
   `must_confirm()` instead of inventing flags.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import platform
import re
import sys
import tempfile
import uuid

PIPELINE_VERSION = "0.1.0"
CANDIDATE_SCHEMA = "fab4.candidate/v1"

# Formats abguard accepts. Source: task PDF, "Hard filters" and Figure 2.
VALID_FORMATS = ("VHH", "scFv", "Fab")

# Hard filters, verbatim thresholds from the task PDF (p3 Figure 2, p7).
# Anything not listed here is NOT a documented threshold.
HARD_LIMITS = {
    "max_total_length_aa": 250,          # "Maximal total length of 250 amino acids"
    "min_numbering_confidence": 0.1,     # "numbering with at least 0.1 confidence with immunum"
    "max_identity_known_denovo": 0.70,   # de novo: under 70% identity to any known antibody
    "max_cdrh3_identity_trastuzumab_opt": 0.70,  # optimisation: under 70% CDRH3 identity
    "min_cdrh3_mutations_denovo": 2,     # de novo: "at least 2 CDRH3 mutations" -> >= 2
    "min_point_mutations_opt": 3,        # optimisation: "strictly more than 2" -> >= 3
}

# CONTRADICTION IN THE SOURCE, flagged rather than resolved:
# task PDF p2 prose says optimisation needs "at least 2 mutations from any
# provided antibody"; p3 Figure 2 says "More than 2 point mutations" and p7 says
# "strictly more than 2 point mutations". We take the strict reading (>= 3) above
# because it satisfies both. TODO: confirm with the organisers or by running the
# real abguard on a 2-mutation design.

# Submission size. Source: task PDF, "Design submission": a ranked list of up to
# 20 (16 if we win, plus 4 against duplication between teams).
MAX_SUBMISSION = 20


# --------------------------------------------------------------------------
# time, ids, hashes
# --------------------------------------------------------------------------

def utc_now() -> str:
    """ISO-8601 UTC timestamp, second resolution."""
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_run_id(prefix: str = "run") -> str:
    return "{0}-{1}-{2}".format(prefix, _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"), uuid.uuid4().hex[:6])


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_ref(path: str | None) -> dict | None:
    """{path, sha256, bytes} for an input file, so a run can be re-identified."""
    if not path:
        return None
    if not os.path.exists(path):
        return {"path": os.path.abspath(path), "sha256": None, "bytes": None, "note": "missing at stamp time"}
    return {"path": os.path.abspath(path), "sha256": sha256_file(path), "bytes": os.path.getsize(path)}


# --------------------------------------------------------------------------
# IO
# --------------------------------------------------------------------------

def write_json(path: str, obj) -> str:
    """Atomic write, so a half-written file never gets read by the next stage."""
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, sort_keys=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path


def read_json(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_jsonl(path: str, records) -> str:
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    n = 0
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, sort_keys=False) + "\n")
                n += 1
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path


def read_jsonl(path: str) -> list:
    out = []
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError("{0}: line {1} is not JSON: {2}".format(path, i, exc)) from exc
    return out


def read_fasta(path: str) -> list:
    """[(header, sequence)] from a FASTA. Stdlib, no biopython needed."""
    recs, name, buf = [], None, []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if name is not None:
                    recs.append((name, "".join(buf)))
                name, buf = line[1:].strip(), []
            else:
                buf.append(re.sub(r"[^A-Za-z]", "", line).upper())
    if name is not None:
        recs.append((name, "".join(buf)))
    return recs


def write_csv(path: str, rows: list, columns: list) -> str:
    import csv
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in columns})
    return path


# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------

def provenance(stage: str, *, model: str | None = None, model_image: str | None = None,
               weights: str | None = None, seed=None, settings: dict | None = None,
               inputs=None, run_id: str | None = None, extra: dict | None = None) -> dict:
    """Provenance stamp. `model`/`weights`/`seed` are mandatory for anything a
    model produced; pass None only when no model was involved (e.g. stage 01)."""
    prov = {
        "stage": stage,
        "pipeline_version": PIPELINE_VERSION,
        "run_id": run_id or new_run_id(stage.split("_")[0]),
        "timestamp": utc_now(),
        "host": platform.node(),
        "python": platform.python_version(),
        "model": model,
        "model_image": model_image,
        "weights": weights,
        "seed": seed,
        "settings": settings or {},
        "inputs": [file_ref(p) for p in (inputs or []) if p],
    }
    if extra:
        prov.update(extra)
    return prov


def score_entry(value, *, model: str | None, version: str | None = None, seed=None,
                source_file: str | None = None, note: str | None = None,
                higher_is_better: bool | None = None) -> dict:
    """One score cell. `value` is None when we did not measure it; `note` then
    says why. Never put a placeholder number here."""
    return {
        "value": value,
        "model": model,
        "version": version,
        "seed": seed,
        "source_file": source_file,
        "higher_is_better": higher_is_better,
        "note": note,
        "recorded_at": utc_now(),
    }


# --------------------------------------------------------------------------
# candidate records
# --------------------------------------------------------------------------

def new_candidate(candidate_id: str, *, fmt: str, chains: dict, provenance_stamp: dict,
                  track_intent: str = "unknown", parent: str | None = None,
                  structure_path: str | None = None, notes=None) -> dict:
    """A candidate record. `chains` maps a chain label to a sequence:

      VHH  -> {"H": "<seq>"}
      scFv -> {"H": "<vh>", "L": "<vl>", "linker": "<linker>"}   (single chain, linked)
      Fab  -> {"H": "<vh>", "L": "<vl>"}                          (paired chains)

    `track_intent` is what WE aimed for. abguard decides the real track and never
    reclassifies a design (task PDF, Figure 2), so nothing downstream may treat
    this field as the track.
    """
    if fmt not in VALID_FORMATS:
        raise ValueError("format must be one of {0}, got {1!r}".format(VALID_FORMATS, fmt))
    return {
        "schema": CANDIDATE_SCHEMA,
        "candidate_id": candidate_id,
        "format": fmt,
        "track_intent": track_intent,
        "parent": parent,
        "chains": dict(chains),
        "structure_path": structure_path,
        "provenance": provenance_stamp,
        "scores": {},
        "checks": {},
        "notes": list(notes or []),
    }


def candidate_sequences(rec: dict) -> dict:
    """Chain label -> sequence, excluding non-chain entries such as 'linker'."""
    return {k: v for k, v in (rec.get("chains") or {}).items() if k != "linker" and v}


def total_length(rec: dict) -> int:
    """Total amino acids as the task PDF counts them: the whole length of a
    single scFv or VHH, or VH and VL combined for a Fab. The scFv linker is part
    of that single chain, so it counts."""
    chains = rec.get("chains") or {}
    n = sum(len(v) for k, v in chains.items() if k != "linker" and v)
    if rec.get("format") == "scFv" and chains.get("linker"):
        n += len(chains["linker"])
    return n


def count_cysteines(rec: dict) -> int:
    return sum(seq.count("C") for seq in candidate_sequences(rec).values())


# --------------------------------------------------------------------------
# sequence comparison (stdlib; deterministic; no numpy)
# --------------------------------------------------------------------------

def align_global(a: str, b: str, match: int = 1, mismatch: int = -1, gap: int = -2):
    """Needleman-Wunsch with a linear gap penalty. Returns (aln_a, aln_b).

    Deliberately simple and dependency-free: it is used for identity and
    mutation counts between short, closely related antibody sequences, not for
    remote homology. For anything that matters, abguard's own comparison is the
    authority."""
    n, m = len(a), len(b)
    if n == 0 or m == 0:
        return (a or "-" * m, b or "-" * n)
    prev = [j * gap for j in range(m + 1)]
    ptr = [[0] * (m + 1) for _ in range(n + 1)]
    for j in range(1, m + 1):
        ptr[0][j] = 2
    for i in range(1, n + 1):
        cur = [i * gap] + [0] * m
        ptr[i][0] = 1
        for j in range(1, m + 1):
            diag = prev[j - 1] + (match if a[i - 1] == b[j - 1] else mismatch)
            up = prev[j] + gap
            left = cur[j - 1] + gap
            best = max(diag, up, left)
            cur[j] = best
            ptr[i][j] = 0 if best == diag else (1 if best == up else 2)
        prev = cur
    i, j, out_a, out_b = n, m, [], []
    while i > 0 or j > 0:
        d = ptr[i][j]
        if i > 0 and j > 0 and d == 0:
            out_a.append(a[i - 1]); out_b.append(b[j - 1]); i -= 1; j -= 1
        elif i > 0 and (d == 1 or j == 0):
            out_a.append(a[i - 1]); out_b.append("-"); i -= 1
        else:
            out_a.append("-"); out_b.append(b[j - 1]); j -= 1
    return ("".join(reversed(out_a)), "".join(reversed(out_b)))


def identity(query: str, reference: str) -> dict:
    """Sequence identity of `query` against `reference`.

    Returns the fraction AND the definition used, because the denominator is a
    choice and abguard's choice is not documented in the task PDF. We report
    matches / len(reference).

    TODO: confirm abguard's identity definition (denominator, gap handling,
    whether it compares full V-domain or only the numbered region) before any
    novelty number is quoted to a judge.
    """
    if not reference:
        return {"identity": None, "definition": "undefined: empty reference"}
    aq, ar = align_global(query, reference)
    matches = sum(1 for x, y in zip(aq, ar) if x == y and x != "-")
    return {
        "identity": round(matches / len(reference), 4),
        "matches": matches,
        "definition": "matches / len(reference), Needleman-Wunsch 1/-1/-2, local re-implementation",
        "aligned_length": len(aq),
    }


def mutation_count(query: str, reference: str) -> dict:
    """Point mutations of `query` away from `reference`. Equal lengths give a
    plain Hamming distance; otherwise mismatches plus gap columns from the
    alignment, which is an approximation and labelled as one."""
    if len(query) == len(reference) and query and reference:
        n = sum(1 for x, y in zip(query, reference) if x != y)
        return {"mutations": n, "definition": "Hamming distance, equal lengths"}
    aq, ar = align_global(query, reference)
    n = sum(1 for x, y in zip(aq, ar) if x != y)
    return {"mutations": n, "definition": "mismatch+gap columns from global alignment (approximate)"}


# --------------------------------------------------------------------------
# reference data (trastuzumab, provided antibodies)
# --------------------------------------------------------------------------

DEFAULT_REFERENCE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                      "data", "reference", "antibodies.json")


def load_reference_set(path: str | None = None) -> dict:
    """Load the reference antibodies the novelty checks compare against.

    Expected shape:
      {"trastuzumab": {"H": "...", "L": "...", "cdrh3": "..."},
       "provided": [{"id": "...", "H": "...", "L": "..."}, ...]}

    The task PDF does NOT contain any trastuzumab sequence, so this repo ships
    no sequence either: filling it in from memory is exactly the kind of wrong
    number that costs the submission. Populate it from an authoritative source
    (RCSB / the organisers' bucket) and record where it came from in the file's
    "source" field.

    Returns {} when the file is absent. Callers must then record the affected
    checks as "indeterminate", never as "pass".
    """
    p = path or DEFAULT_REFERENCE_PATH
    if not os.path.exists(p):
        return {}
    data = read_json(p)
    return data if isinstance(data, dict) else {}


# --------------------------------------------------------------------------
# unverified external interfaces
# --------------------------------------------------------------------------

class ConfirmOnVM(NotImplementedError):
    """Raised where an external API shape is not verified in our sources."""


def must_confirm(what: str, how: str) -> "ConfirmOnVM":
    """Build the exception to raise instead of guessing a flag or a payload.

    `what` names the interface, `how` says exactly what to run on the VM to
    confirm it. Return it and `raise` at the call site so the traceback points
    at the real caller.
    """
    return ConfirmOnVM("{0} is not verified in our sources.\n  Confirm on the VM: {1}".format(what, how))


# --------------------------------------------------------------------------
# argparse plumbing shared by the stages
# --------------------------------------------------------------------------

def base_parser(description: str, epilog: str | None = None) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description, epilog=epilog,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version="fab4-pipeline {0}".format(PIPELINE_VERSION))
    return p


def add_io_args(p: argparse.ArgumentParser, *, out_default: str | None = None) -> None:
    p.add_argument("-o", "--out", default=out_default, required=out_default is None,
                   help="output file this stage writes")
    p.add_argument("--run-id", default=None, help="reuse a run id (for resuming)")
    p.add_argument("-q", "--quiet", action="store_true", help="no progress on stdout")


def require_deps(*mods: str) -> None:
    """Fail with an install line instead of a bare ImportError. Called at the
    start of the work, never at import time, so --help always works."""
    missing = []
    for m in mods:
        try:
            __import__(m)
        except ImportError:
            missing.append(m)
    if missing:
        pip = {"Bio": "biopython", "anarcii": "anarcii", "numpy": "numpy"}
        names = " ".join(pip.get(m, m) for m in missing)
        raise SystemExit("missing dependency: {0}\n  pip install {1}".format(", ".join(missing), names))


def say(quiet: bool, *parts) -> None:
    if not quiet:
        print(" ".join(str(x) for x in parts))


def cli(main_func, argv=None) -> int:
    """Run a stage's main() and turn an unverified-interface error into a short
    message instead of a traceback. Exit codes: 0 ok, 2 argparse, 3 the stage
    needs something confirmed on the VM first."""
    try:
        return main_func(argv)
    except ConfirmOnVM as exc:
        print("NOT IMPLEMENTED YET - " + str(exc), file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        return 130


def table(rows: list, headers: list) -> str:
    """Fixed-width text table for stdout summaries."""
    cols = [[str(h)] + [str(r[i]) for r in rows] for i, h in enumerate(headers)]
    widths = [max(len(x) for x in c) for c in cols]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    sep = "  ".join("-" * w for w in widths)
    body = ["  ".join(str(r[i]).ljust(widths[i]) for i in range(len(headers))) for r in rows]
    return "\n".join([line, sep] + body)
