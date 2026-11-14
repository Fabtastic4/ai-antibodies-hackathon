#!/usr/bin/env python3
"""JapanFold client: the lane that produces the numbers rank.py has been refusing to fake.

Why this matters to the submission. `rank.py` wants `min_ipae` for axis 1 and
`docs/tools-nebius.md` records that the hosted co-folders return no ipTM and no PAE, which
is why `designs/submission.csv` carries `n/a` in those columns and why
`pipeline/score/cofold_contacts.py` counts geometry instead. JapanFold closes that hole:

  * `af2ig`  -- AlphaFold2 initial-guess. Takes a designed complex (target coordinates +
    binder sequence) and reports **ipTM and interface pAE**, which is exactly axis 1. No MSA,
    no sampling: the same input gives the same answer, so it is reproducible by construction.
    We already have the complexes in results/cofold/*/model.cif.
  * `write_pae: true` -- returns the full PAE matrix as <name>_pae.npz, described by the
    service as "the one Adaptyv's ipSAE pipeline reads". That feeds the `ipsae` column.
  * `openfold3` -- the OpenFold Consortium model. docs/tools-apheris.md notes the monetary
    prize wants OpenFold in the pipeline; this is a second, independent way to satisfy it.
  * `opendde-abag` -- an antibody-antigen co-folding checkpoint with epitope `site`
    constraints, so a refold can be steered onto the 19 HER2 residues from docs/epitope.md.

Cost and consent. Every run bills the account's credit. Typical published medians are small
(af2ig ~$0.005, boltz2 ~$0.003, openfold3 ~$0.029 per job), but nothing here submits a job
unless it is asked to: `estimate()` prices a plan without starting anything, and the CLI
requires --yes before it spends. `list_models()` is free.

The key is never written into this repo. It is read from, in order:
    $JAPANFOLD_API_KEY
    viz/japanfold.key            (gitignored)
    ../credentials.private.json  (key "japanfold" or "japanfold_api_key")

    python3 japanfold.py --check                      # key + balance, spends nothing
    python3 japanfold.py --models                     # catalogue and prices, spends nothing
    python3 japanfold.py --estimate af2ig --all       # what scoring the submission would cost
    python3 japanfold.py --score-af2ig <design_id> --yes
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
def load_dotenv(path: pathlib.Path | None = None) -> list[str]:
    """Read .env into the environment, without a dependency and without overwriting.

    Keeps the secret in one gitignored file instead of scattered across shells, so
    `python3 viz/japanfold.py --check` works in a fresh terminal with nothing exported.
    A real environment variable always wins, so a shell export still overrides the file.

    Returns the names it set, never the values.
    """
    p = path or (REPO / ".env")
    if not p.is_file():
        return []
    set_names = []
    for line in p.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip()
        # Strip one layer of matching quotes, and drop a trailing inline comment on an
        # unquoted value -- otherwise '# never commit' becomes part of the key.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        if name and value and not os.environ.get(name):
            os.environ[name] = value
            set_names.append(name)
    return set_names


DOTENV_LOADED = load_dotenv()


def _base_url() -> str:
    """The REST root, ending in /v1.

    Accepts either env name, and accepts a bare host without the version suffix --
    JAPANFOLD_BASE_URL=https://api.japanfold.aiand.com is the natural thing to export, and
    silently requesting /models instead of /v1/models would 404 for no visible reason.
    """
    raw = (os.environ.get("JAPANFOLD_BASE")
           or os.environ.get("JAPANFOLD_BASE_URL")
           or "https://api.japanfold.aiand.com/v1").strip().rstrip("/")
    return raw if raw.endswith("/v1") else raw + "/v1"


BASE = _base_url()
MCP_URL = "https://api.japanfold.aiand.com/mcp"
TOKEN_URL = "https://japanfold.aiand.com/account/token"

# Where folded structures and scores land. Mirrors results/cofold/ so the viewer can read
# either lane the same way.
OUT_ROOT = REPO.parent / "results" / "japanfold"


class JapanFoldError(RuntimeError):
    pass


class NoKey(JapanFoldError):
    pass


# ---------------------------------------------------------------------------
# key + transport
# ---------------------------------------------------------------------------

def key_path() -> pathlib.Path:
    """Where to read the key from, without copying it into the repo.

    docs/SETUP.md §6 is explicit: the key lives in `japanfold-oslo-hackathon-codes 4.txt`
    in the Slack folder, and must not be copied into any file in this repo or pasted into a
    chat. So the supported route is to POINT at that file:

        export JAPANFOLD_KEY_FILE="$HOME/Downloads/japanfold-oslo-hackathon-codes 4.txt"

    $JAPANFOLD_API_KEY works too. viz/japanfold.key is only a last-resort local fallback;
    it is gitignored, but SETUP.md would rather you did not create it.
    """
    p = (os.environ.get("JAPANFOLD_KEY_FILE") or "").strip()
    return pathlib.Path(os.path.expanduser(p)) if p else HERE / "japanfold.key"


def _key_from_file(p: pathlib.Path) -> str:
    """Pull a key out of a file that may be a bare key or a page of hackathon notes.

    The Slack txt is prose with the key somewhere inside it, so a blind read() would send
    the whole file as a bearer token. Take the first thing that looks like a key, and never
    echo the file's contents.
    """
    import re
    text = p.read_text(errors="replace")
    if len(text.strip().split()) == 1:
        return text.strip()
    # Longest token that looks like an API key, preferring an explicit label.
    # The separator must exclude key characters, or it eats the key's own prefix:
    # \D{0,20} would swallow "jf_FAKE" and capture only the digits after it.
    m = re.search(r"(?:api[_ -]?key|token|bearer)[^A-Za-z0-9]{0,12}([A-Za-z0-9_\-]{20,})",
                  text, re.I)
    if m:
        return m.group(1)
    cands = re.findall(r"\b[A-Za-z0-9_\-]{24,}\b", text)
    if cands:
        return max(cands, key=len)
    raise NoKey(f"{p} has no key-shaped string in it. Check you have the right file.")


def _key_source() -> str | None:
    """Where the key is coming from. Names the source, never the value."""
    if "JAPANFOLD_API_KEY" in DOTENV_LOADED:
        return f"{REPO / '.env'} (JAPANFOLD_API_KEY)"
    if os.environ.get("JAPANFOLD_API_KEY"):
        return "$JAPANFOLD_API_KEY (shell)"
    if key_path().is_file():
        return str(key_path())
    cred = REPO.parent / "credentials.private.json"
    if cred.is_file():
        try:
            if any(k in json.loads(cred.read_text())
                   for k in ("japanfold", "japanfold_api_key", "JAPANFOLD_API_KEY")):
                return f"{cred} (japanfold field)"
        except (json.JSONDecodeError, OSError):
            pass
    return None


def api_key(required: bool = True) -> str | None:
    k = (os.environ.get("JAPANFOLD_API_KEY") or "").strip()
    if not k and key_path().is_file():
        k = _key_from_file(key_path())
    if not k:
        cred = REPO.parent / "credentials.private.json"
        if cred.is_file():
            try:
                d = json.loads(cred.read_text())
                for name in ("japanfold", "japanfold_api_key", "JAPANFOLD_API_KEY"):
                    v = d.get(name)
                    if isinstance(v, dict):
                        v = v.get("api_key") or v.get("key")
                    if v:
                        k = str(v).strip()
                        break
            except (json.JSONDecodeError, OSError):
                pass
    if not k and required:
        raise NoKey(
            "No JapanFold API key.\n"
            "Your key is in 'japanfold-oslo-hackathon-codes 4.txt' in the Slack folder "
            "(docs/SETUP.md §6). Point at it rather than copying it into the repo:\n"
            "  export JAPANFOLD_KEY_FILE=\"$HOME/Downloads/japanfold-oslo-hackathon-codes 4.txt\"\n"
            "or, if you would rather paste it into your own shell only:\n"
            "  export JAPANFOLD_API_KEY=...\n"
            f"Without the Slack file, a personal key comes from {TOKEN_URL} "
            "($100 of credit on a new account).\n"
            "Do not paste it into a chat.")
    return k or None


def _request(method: str, path: str, body: dict | None = None, *,
             auth: bool = True, timeout: int = 180) -> dict:
    url = path if path.startswith("http") else f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")
    if auth:
        req.add_header("Authorization", f"Bearer {api_key()}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw)
        except Exception:                                      # noqa: BLE001
            payload = {"error": raw.decode(errors="replace")[:500]}
        if e.code == 402:
            raise JapanFoldError(
                "402 out of credit. Add funds at "
                f"{payload.get('billing_url') or TOKEN_URL}: {payload}") from e
        if e.code in (401, 403):
            raise NoKey(f"{e.code} rejected by JapanFold: {payload}") from e
        raise JapanFoldError(f"{method} {url} -> {e.code}: {payload}") from e
    except urllib.error.URLError as e:
        raise JapanFoldError(f"{method} {url} unreachable: {e.reason}") from e
    return json.loads(raw) if raw else {}


def _download(path: str, dest: pathlib.Path, timeout: int = 600) -> pathlib.Path:
    url = path if path.startswith("http") else f"{BASE}{path}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {api_key()}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(req, timeout=timeout) as r, dest.open("wb") as fh:
        while chunk := r.read(65536):
            fh.write(chunk)
    return dest


# ---------------------------------------------------------------------------
# free, read-only
# ---------------------------------------------------------------------------

def list_models() -> dict:
    """Free and starts nothing. Answer price questions from this."""
    return _request("GET", "/models", auth=False)


def account() -> dict:
    return _request("GET", "/account")


def check() -> dict:
    """Is the lane usable, and what would it spend against?"""
    out = {"base": BASE, "mcp": MCP_URL, "key_present": bool(api_key(required=False)),
           "key_source": _key_source(),
           "dotenv": str(REPO / ".env") if (REPO / ".env").is_file() else None,
           "dotenv_set": DOTENV_LOADED}
    try:
        models = list_models()
        out["reachable"] = True
        out["n_predict_models"] = len(models.get("models", []))
    except JapanFoldError as e:
        out["reachable"] = False
        out["error"] = str(e)
        return out
    if out["key_present"]:
        try:
            acct = account()
            out["account"] = {k: acct.get(k) for k in
                              ("balance_usd", "balance", "rate", "email", "credits")
                              if k in acct}
        except JapanFoldError as e:
            out["account_error"] = str(e)
    return out


def price(model: str, n: int = 1) -> dict:
    """Published medians for past jobs of a model. Not a quote -- a run is billed for the
    time it actually takes."""
    models = list_models()
    for bucket in ("models", "design_models", "embed_models"):
        for m in models.get(bucket, []):
            if m.get("id") == model:
                tc = m.get("typical_cost") or {}
                p50, p90 = tc.get("usd_p50"), tc.get("usd_p90")
                return {"model": model, "n": n, "usd_p50_each": p50, "usd_p90_each": p90,
                        "usd_p50_total": round(p50 * n, 4) if p50 is not None else None,
                        "usd_p90_total": round(p90 * n, 4) if p90 is not None else None,
                        "jobs_observed": tc.get("jobs"),
                        "note": "median of past jobs, not a quote; runs bill for time used"}
    raise JapanFoldError(f"unknown model {model!r}")


# ---------------------------------------------------------------------------
# structure conversion: our mmCIF co-folds -> the PDB block af2ig wants
# ---------------------------------------------------------------------------

AA3 = {"ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q", "GLU": "E",
       "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F",
       "PRO": "P", "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V"}


def cif_to_pdb_block(cif: pathlib.Path, chains: dict[str, str]) -> str:
    """Write selected chains as PDB ATOM records, renaming them.

    `chains` maps source chain -> output chain, e.g. {"C": "A", "H": "B"}. af2ig wants one
    target chain and one binder chain, and PDB gives a chain id a single column, so the
    rename is not cosmetic -- it is what keeps the two chains distinguishable.
    """
    sys.path.insert(0, str(HERE))
    import backends as B

    atoms = B.parse_structure(cif)
    lines, serial = [], 1
    for src, dst in chains.items():
        sel = [a for a in atoms if a[0] == src]
        if not sel:
            raise JapanFoldError(f"{cif}: chain {src!r} absent")
        for _, resseq, comp, name, element, x, y, z, b in sel:
            # PDB fixed columns. Atom names of four characters start in column 13,
            # shorter ones in column 14 -- getting this wrong silently shifts elements.
            an = name if len(name) >= 4 else f" {name:<3}"
            lines.append(
                f"ATOM  {serial:>5} {an:<4}{'':1}{comp:>3} {dst}{resseq:>4}{'':4}"
                f"{x:>8.3f}{y:>8.3f}{z:>8.3f}{1.00:>6.2f}{(b or 0.0):>6.2f}"
                f"{'':10}{element:>2}")
            serial += 1
        lines.append("TER")
    lines.append("END")
    return "\n".join(lines)


def chain_sequence(cif: pathlib.Path, chain: str) -> str:
    sys.path.insert(0, str(HERE))
    import backends as B
    seen: dict[int, str] = {}
    for ch, resseq, comp, name, *_ in B.parse_structure(cif):
        if ch == chain and name == "CA":
            seen[resseq] = AA3.get(comp.upper(), "X")
    return "".join(seen[k] for k in sorted(seen))


# ---------------------------------------------------------------------------
# job plumbing
# ---------------------------------------------------------------------------

def submit_prediction(yaml_text: str, model: str, name: str, params: dict | None = None) -> dict:
    body = {"input": yaml_text, "model": model, "name": name,
            "params": params or {}}
    return _request("POST", "/predictions", body)


def wait_for(job_id: str, *, poll: int = 60, max_wait: int = 1800,
             progress=None) -> dict:
    """Hold on one job. The service caps a single wait at 100 s and allows two concurrent
    waits per account, so one job per call -- as its own instructions say."""
    waited = 0
    while True:
        job = _request("GET", f"/jobs/{job_id}?wait={min(poll, 100)}",
                       timeout=min(poll, 100) + 60)
        status = (job.get("status") or "").lower()
        if progress:
            progress(status, waited)
        if status in ("succeeded", "failed", "canceled", "cancelled"):
            return job
        waited += poll
        if waited >= max_wait:
            raise JapanFoldError(
                f"job {job_id} still {status} after {waited}s. It is not lost: "
                f"GET {BASE}/jobs/{job_id} later, from any machine with the same key.")


def results(job_id: str) -> dict:
    return _request("GET", f"/jobs/{job_id}/results")


def logs(job_id: str) -> str:
    try:
        out = _request("GET", f"/jobs/{job_id}/logs")
        return out if isinstance(out, str) else json.dumps(out)[:4000]
    except JapanFoldError as e:
        return f"(logs unavailable: {e})"


def fetch_artifacts(job_id: str, dest: pathlib.Path) -> list[pathlib.Path]:
    res = results(job_id)
    got = []
    items = res.get("artifacts") or res.get("files") or []
    for a in items:
        rel = a.get("path") or a.get("name") if isinstance(a, dict) else str(a)
        if not rel:
            continue
        try:
            got.append(_download(f"/jobs/{job_id}/artifacts/{rel}", dest / rel))
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"  ! could not fetch {rel}: {e}", file=sys.stderr)
    (dest / "results.json").write_text(json.dumps(res, indent=2))
    return got


# ---------------------------------------------------------------------------
# axis 1: ipTM and interface pAE for a design we already folded
# ---------------------------------------------------------------------------

def af2ig_yaml(cif: pathlib.Path, *, target_chain: str = "C",
               binder_chain: str = "H") -> str:
    """Target coordinates + the binder sequence to place on its backbone.

    Only VH goes in as the binder, matching the VH-vs-VH baseline the catalog compares
    against (the 19-residue epitope was defined from the whole Fab; the light chain
    accounts for the residues neither VH reaches).
    """
    block = cif_to_pdb_block(cif, {target_chain: "A", binder_chain: "B"})
    binder_seq = chain_sequence(cif, binder_chain)
    if not binder_seq:
        raise JapanFoldError(f"{cif}: no CA atoms in chain {binder_chain!r}")
    indented = "\n".join("    " + l for l in block.splitlines())
    return (f"target:\n  structure: |\n{indented}\n  chain: A\n"
            f"binder:\n  sequence: {binder_seq}\n  chain: B\n")


def score_af2ig(design_id: str, *, cif: pathlib.Path | None = None,
                write_pae: bool = True, wait: bool = True) -> dict:
    """Run AF2-IG on an existing co-fold. Returns ipTM and interface pAE.

    This is the one call that turns `iptm`/`min_ipae` from 'n/a' into a measured number.
    """
    sys.path.insert(0, str(HERE))
    import backends as B

    if cif is None:
        cif = B._cofold_index().get(design_id)
    if cif is None:
        raise JapanFoldError(
            f"no co-fold for {design_id!r} in {B.COFOLD}. af2ig scores a complex you "
            f"already have; fold it first (lane=japanfold --fold, or the hosted lane).")

    yaml_text = af2ig_yaml(pathlib.Path(cif))
    job = submit_prediction(yaml_text, "af2ig", f"af2ig-{design_id}",
                            {"write_pae": bool(write_pae)})
    job_id = job.get("id") or job.get("job_id")
    if not job_id:
        raise JapanFoldError(f"no job id in response: {job}")

    dest = OUT_ROOT / "af2ig" / design_id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "job.json").write_text(json.dumps(job, indent=2))
    (dest / "input.yaml").write_text(yaml_text)
    print(f"  submitted {job_id}  ({design_id})", file=sys.stderr)
    if not wait:
        return {"design_id": design_id, "job_id": job_id, "status": job.get("status"),
                "dest": str(dest)}

    done = wait_for(job_id, progress=lambda s, w: print(f"    {job_id} {s} ({w}s)",
                                                        file=sys.stderr))
    (dest / "job.json").write_text(json.dumps(done, indent=2))
    status = (done.get("status") or "").lower()
    if status != "succeeded":
        (dest / "logs.txt").write_text(logs(job_id))
        return {"design_id": design_id, "job_id": job_id, "status": status,
                "error": done.get("error") or done.get("message"),
                "logs": str(dest / "logs.txt"), "dest": str(dest)}

    fetch_artifacts(job_id, dest)
    res = results(job_id)
    scores = res.get("scores") or res.get("metrics") or {}

    def dig(*names):
        for n in names:
            for src in (scores, res):
                if isinstance(src, dict) and src.get(n) is not None:
                    return src[n]
        return None

    out = {
        "design_id": design_id,
        "job_id": job_id,
        "status": "succeeded",
        "model": "af2ig",
        "iptm": dig("iptm", "ipTM", "interface_ptm"),
        "interface_pae": dig("interface_pae", "pae_interaction", "ipae", "min_ipae"),
        "plddt": dig("plddt", "mean_plddt", "binder_plddt"),
        "ptm": dig("ptm"),
        "dest": str(dest),
        "scores_raw": scores,
        "basis": ("MEASURED: JapanFold af2ig (AlphaFold2 initial-guess, params_model_1_ptm) "
                  "on the Boltz-2 co-fold complex; VH as binder, HER2 as target. "
                  "Deterministic: no MSA, no sampling."),
    }
    (dest / "score.json").write_text(json.dumps(out, indent=2))
    return out


# ---------------------------------------------------------------------------
# folding a sequence, optionally steered onto the epitope
# ---------------------------------------------------------------------------

def her2_sequence() -> str:
    fa = REPO / "data" / "target" / "1n8z.fasta"
    seqs, name = {}, None
    for line in fa.read_text().splitlines():
        line = line.strip()
        if line.startswith(">"):
            name = line
            seqs[name] = ""
        elif name:
            seqs[name] += line
    for k, v in seqs.items():
        if "Chain C" in k or "erbB-2" in k:
            return v
    raise JapanFoldError(f"HER2 chain C not found in {fa}")


def fold_yaml(heavy: str, light: str | None = None, *, target: bool = True,
              epitope_guidance: bool = False) -> str:
    """Boltz-style YAML: VH (H), VL (L), HER2 (C), with an optional epitope site constraint."""
    sys.path.insert(0, str(HERE))
    import backends as B

    parts = ["version: 1", "sequences:",
             "  - protein:", "      id: H", f"      sequence: {heavy}"]
    if light:
        parts += ["  - protein:", "      id: L", f"      sequence: {light}"]
    if target:
        parts += ["  - protein:", "      id: C", f"      sequence: {her2_sequence()}"]
    if epitope_guidance and target:
        ids = ", ".join(f"[C, {r}]" for r in B.HER2_EPITOPE)
        parts += ["constraints:", "  - site:", "      source_chains: [C]",
                  "      partner_chains: [H]", f"      residue_ids: [{ids}]"]
    return "\n".join(parts) + "\n"


def fold(heavy: str, light: str | None = None, *, model: str = "openfold3",
         name: str = "fold", epitope_guidance: bool = False, write_pae: bool = True,
         wait: bool = True, extra_params: dict | None = None) -> dict:
    """Co-fold a design against HER2 on JapanFold.

    openfold3 by default: it is the OpenFold Consortium model, which is the one
    docs/tools-apheris.md flags for the prize condition. opendde-abag is the
    antibody-antigen checkpoint and is the one that accepts epitope guidance.
    """
    if epitope_guidance and model not in ("opendde-abag", "opendde", "boltz2", "mol1"):
        raise JapanFoldError(
            f"{model} does not advertise the 'guidance' capability; use opendde-abag "
            f"for epitope-steered refolds (see list_models()).")
    yaml_text = fold_yaml(heavy, light, epitope_guidance=epitope_guidance)
    params = {"write_pae": bool(write_pae)}
    params.update(extra_params or {})
    if epitope_guidance:
        params["use_tfg_guidance"] = True

    job = submit_prediction(yaml_text, model, name, params)
    job_id = job.get("id") or job.get("job_id")
    if not job_id:
        raise JapanFoldError(f"no job id in response: {job}")
    dest = OUT_ROOT / model / name
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "input.yaml").write_text(yaml_text)
    (dest / "job.json").write_text(json.dumps(job, indent=2))
    print(f"  submitted {job_id}  ({model}/{name})", file=sys.stderr)
    if not wait:
        return {"job_id": job_id, "status": job.get("status"), "dest": str(dest)}

    done = wait_for(job_id, progress=lambda s, w: print(f"    {job_id} {s} ({w}s)",
                                                        file=sys.stderr))
    (dest / "job.json").write_text(json.dumps(done, indent=2))
    if (done.get("status") or "").lower() != "succeeded":
        (dest / "logs.txt").write_text(logs(job_id))
        return {"job_id": job_id, "status": done.get("status"),
                "error": done.get("error"), "logs": str(dest / "logs.txt"),
                "dest": str(dest)}

    files = fetch_artifacts(job_id, dest)
    cif = next((f for f in files if f.suffix.lower() in (".cif", ".pdb")), None)
    # Make it readable by the viewer exactly like a hosted co-fold.
    if cif and cif.name != "model.cif":
        try:
            (dest / "model.cif").write_bytes(cif.read_bytes())
        except OSError:
            pass
    return {"job_id": job_id, "status": "succeeded", "model": model,
            "dest": str(dest), "structure": str(cif) if cif else None,
            "results": results(job_id)}


# ---------------------------------------------------------------------------

def estimate(model: str, design_ids: list[str]) -> dict:
    p = price(model, len(design_ids))
    p["design_ids"] = design_ids
    p["spends_nothing"] = True
    return p


def _cli() -> int:
    import argparse
    sys.path.insert(0, str(HERE))
    import backends as B

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="key, reachability, balance")
    ap.add_argument("--models", action="store_true", help="catalogue + prices (free)")
    ap.add_argument("--estimate", metavar="MODEL", help="price a plan, start nothing")
    ap.add_argument("--score-af2ig", metavar="DESIGN_ID",
                    help="ipTM + interface pAE for one design")
    ap.add_argument("--fold", metavar="DESIGN_ID", help="co-fold one design against HER2")
    ap.add_argument("--model", default="openfold3")
    ap.add_argument("--epitope-guidance", action="store_true")
    ap.add_argument("--all", action="store_true", help="every design with a co-fold")
    ap.add_argument("--yes", action="store_true", help="required before anything bills")
    ap.add_argument("--no-wait", action="store_true")
    a = ap.parse_args()

    if a.check:
        print(json.dumps(check(), indent=2))
        return 0
    if a.models:
        m = list_models()
        for bucket in ("models", "design_models", "embed_models"):
            print(f"\n== {bucket}")
            for x in m.get(bucket, []):
                tc = x.get("typical_cost") or {}
                print(f"  {x['id']:<16} {str(tc.get('usd_p50')):<10} {x.get('tagline','')}")
        return 0

    ids = sorted(B._cofold_index()) if a.all else (
        [a.score_af2ig or a.fold] if (a.score_af2ig or a.fold) else [])
    ids = [i for i in ids if i]

    if a.estimate:
        print(json.dumps(estimate(a.estimate, ids), indent=2))
        return 0
    if not ids:
        ap.error("give --score-af2ig ID, --fold ID, or --all")

    which = "af2ig" if a.score_af2ig or (a.all and not a.fold) else a.model
    if not a.yes:
        print(json.dumps(estimate(which, ids), indent=2))
        print(f"\nThis would start {len(ids)} billed job(s) on {which}. "
              f"Re-run with --yes to spend.", file=sys.stderr)
        return 1

    out = []
    for i, did in enumerate(ids, 1):
        print(f"[{i}/{len(ids)}] {did}", file=sys.stderr)
        try:
            if a.fold and not a.all:
                rows = [r for r in __import__("csv").DictReader(
                    (REPO / "designs" / "submission.csv").open())
                    if r["design_id"] == did]
                if not rows:
                    raise JapanFoldError(f"{did} not in designs/submission.csv")
                r = rows[0]
                out.append(fold(r["sequence"], r.get("light_sequence"), model=a.model,
                                name=did, epitope_guidance=a.epitope_guidance,
                                wait=not a.no_wait))
            else:
                out.append(score_af2ig(did, wait=not a.no_wait))
        except JapanFoldError as e:
            print(f"  ! {e}", file=sys.stderr)
            out.append({"design_id": did, "error": str(e)})
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_cli())
    except NoKey as e:
        print(f"\n{e}\n", file=sys.stderr)
        raise SystemExit(2)
