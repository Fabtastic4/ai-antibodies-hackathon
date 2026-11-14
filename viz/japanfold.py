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
    service as "the one Adaptyv's ipSAE pipeline reads". We read it here and compute the
    `ipsae` column from it ourselves, labelled as locally computed -- the service returns
    the matrix, not an ipSAE number.
  * `openfold3` -- the OpenFold Consortium model. docs/tools-apheris.md notes the monetary
    prize wants OpenFold in the pipeline; this is a second, independent way to satisfy it.
  * `opendde-abag` -- an antibody-antigen co-folding checkpoint with epitope constraints,
    so a refold can be steered onto the 19 HER2 residues from docs/epitope.md.

ONE JOB, MANY DESIGNS. A prediction runs each target on its own chip and is billed per
chip-second, so the whole submission goes in a single job as a `targets` list: one queue
wait instead of eighteen, and the price is `usd_per_target` x targets. Scoring all 18
folded designs with af2ig is about $0.007 (p90 $0.018) -- not the $0.09 that multiplying
the per-JOB median would suggest, which is what this module used to quote.

Cost and consent. Every run bills the account's credit. Nothing here submits a job unless
it is asked to: `estimate()` prices a plan without starting anything, and the CLI requires
--yes before it spends. `list_models()`, `--check` and `--estimate` are free.

The key is never written into this repo. It is read from, in order:
    $JAPANFOLD_API_KEY           (a shell export always wins)
    .env                         (gitignored; see .env.example -- the normal route)
    $JAPANFOLD_KEY_FILE          (point it at the Slack codes txt)
    the login keychain           (python3 japanfold.py --set-key, macOS)
    ../credentials.private.json  (key "japanfold" or "japanfold_api_key")
    viz/japanfold.key            (gitignored, last resort)

    python3 japanfold.py --check                        # key + balance + queue, free
    python3 japanfold.py --key-help                     # every way to set the key
    python3 japanfold.py --models                       # catalogue and prices, free
    python3 japanfold.py --estimate af2ig --all         # what scoring the submission costs
    python3 japanfold.py --score-af2ig --all --yes      # ONE job, every design, live
    python3 japanfold.py --watch JOB_ID                 # re-attach to a running job
"""

from __future__ import annotations

import csv
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent


def load_dotenv(path: pathlib.Path | None = None) -> list[str]:
    """Read .env into the environment, without a dependency and without overwriting.

    Keeps the secret in one gitignored file instead of scattered across shells, so
    `python3 viz/japanfold.py --check` works in a fresh terminal with nothing exported.
    A real environment variable always wins, so a shell export still overrides the file.

    Returns the names it set, never the values.
    """
    paths = [path] if path else [REPO / ".env", HERE / ".env", REPO.parent / ".env"]
    set_names = []
    for p in paths:
        if p is None or not p.is_file():
            continue
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
_SPLIT = urllib.parse.urlsplit(BASE)
HOST = _SPLIT.netloc
MCP_URL = f"{_SPLIT.scheme}://{HOST}/mcp"
TOKEN_URL = "https://japanfold.aiand.com/account/token"
CLIENT_ID = "her2-viz"                   # X-JapanFold-Client, so our jobs are identifiable

# Where folded structures and scores land. Mirrors results/cofold/ so the viewer can read
# either lane the same way.
OUT_ROOT = REPO.parent / "results" / "japanfold"
# The axis-1 table rank.py and catalog.py read. Written in the refold-metrics schema on
# purpose: `rank.py --refold <this>` then ranks on a measured min_ipae, and catalog.py's
# join-on-heavy-sequence lights the viewer up with no further wiring.
METRICS_CSV = REPO / "reports" / "japanfold-af2ig-metrics.csv"
METRICS_COLS = ["query_id", "design", "model", "status", "binder_chain", "target_chains",
                "binder_sequence", "min_ipae", "interface_pae", "iptm", "ptm", "plddt",
                "binder_plddt", "binder_ptm", "ipsae", "ipsae_basis", "job_id", "measured_at"]

KEYCHAIN_SERVICE = "japanfold"           # security add-generic-password -s japanfold


class JapanFoldError(RuntimeError):
    pass


class NoKey(JapanFoldError):
    pass


class OutOfCredit(JapanFoldError):
    pass


class Busy(JapanFoldError):
    """A 429. Carries how long the service asked us to wait, and which limit it was."""

    def __init__(self, msg: str, retry_after: int = 30, reason: str = ""):
        super().__init__(msg)
        self.retry_after = retry_after
        self.reason = reason


# ---------------------------------------------------------------------------
# key
# ---------------------------------------------------------------------------

KEY_RE = re.compile(r"\b(jf_[A-Za-z0-9_\-]{8,}|[A-Za-z0-9_\-]{24,})\b")


def key_path() -> pathlib.Path:
    """Where to read the key from, without copying it into the repo.

    docs/SETUP.md §6 is explicit: the key lives in `japanfold-oslo-hackathon-codes 4.txt`
    in the Slack folder, and must not be copied into any file in this repo or pasted into a
    chat. `.env` is the normal route now (gitignored, one file, no exporting); pointing at
    the Slack file in place also works and copies nothing:

        export JAPANFOLD_KEY_FILE="$HOME/Downloads/japanfold-oslo-hackathon-codes 4.txt"

    viz/japanfold.key is only a last-resort local fallback; it is gitignored, but SETUP.md
    would rather you did not create it.
    """
    p = (os.environ.get("JAPANFOLD_KEY_FILE") or "").strip()
    return pathlib.Path(os.path.expanduser(p)) if p else HERE / "japanfold.key"


def _key_from_file(p: pathlib.Path) -> str:
    """Pull a key out of a file that may be a bare key or a page of hackathon notes.

    The Slack txt is prose with the key somewhere inside it, so a blind read() would send
    the whole file as a bearer token. Take the first thing that looks like a key, and never
    echo the file's contents.
    """
    text = p.read_text(errors="replace")
    if len(text.strip().split()) == 1:
        return text.strip()
    # Prefer an explicitly labelled key. The separator must exclude key characters, or it
    # eats the key's own prefix: \D{0,20} would swallow "jf_FAKE" and capture only the
    # digits after it.
    m = re.search(r"(?:api[_ -]?key|token|bearer)[^A-Za-z0-9]{0,12}([A-Za-z0-9_\-]{20,})",
                  text, re.I)
    if m:
        return m.group(1)
    # Then a jf_-prefixed token, which is the shape this service issues.
    cands = [c for c in KEY_RE.findall(text) if c.startswith("jf_")] or KEY_RE.findall(text)
    if cands:
        return max(cands, key=len)
    raise NoKey(f"{p} has no key-shaped string in it. Check you have the right file.")


def _key_from_keychain() -> str | None:
    """The login keychain: out of the repo, out of the shell history, survives a reboot."""
    if not shutil.which("security"):
        return None
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return (out.stdout.strip() or None) if out.returncode == 0 else None


def _key_from_credentials() -> str | None:
    cred = REPO.parent / "credentials.private.json"
    if not cred.is_file():
        return None
    try:
        d = json.loads(cred.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    for name in ("japanfold", "japanfold_api_key", "JAPANFOLD_API_KEY"):
        v = d.get(name)
        if isinstance(v, dict):
            v = v.get("api_key") or v.get("key")
        if v:
            return str(v).strip()
    return None


def _key_source() -> str | None:
    """Where the key is coming from. Names the source, never the value."""
    if "JAPANFOLD_API_KEY" in DOTENV_LOADED:
        return f"{REPO / '.env'} (JAPANFOLD_API_KEY)"
    if os.environ.get("JAPANFOLD_API_KEY"):
        return "$JAPANFOLD_API_KEY (shell)"
    if key_path().is_file():
        return str(key_path())
    if _key_from_keychain():
        return f"login keychain (service {KEYCHAIN_SERVICE!r})"
    if _key_from_credentials():
        return f"{REPO.parent / 'credentials.private.json'} (japanfold field)"
    return None


def api_key(required: bool = True) -> str | None:
    """The key and nothing else. Never logged, never printed, never echoed."""
    k = (os.environ.get("JAPANFOLD_API_KEY") or "").strip()
    if not k and key_path().is_file():
        k = _key_from_file(key_path())
    if not k:
        k = _key_from_keychain() or ""
    if not k:
        k = _key_from_credentials() or ""
    if not k and required:
        raise NoKey(KEY_HELP)
    return k or None


def key_fingerprint() -> str | None:
    """Enough to tell two keys apart in a demo, not enough to use. Last 4 characters."""
    k = api_key(required=False)
    return f"...{k[-4:]} ({len(k)} chars)" if k else None


KEY_HELP = (
    "No JapanFold API key found.\n"
    "\n"
    "The team key is in 'japanfold-oslo-hackathon-codes 4.txt' in the Slack folder\n"
    "(docs/SETUP.md §6: do not copy it into this repo, do not paste it into a chat).\n"
    "Pick ONE of these, best first:\n"
    "\n"
    "  1. .env, which is gitignored and read automatically -- the normal route:\n"
    "       cp .env.example .env && $EDITOR .env      # fill in JAPANFOLD_API_KEY=\n"
    "\n"
    "  2. Point at the Slack file where it already is -- nothing is copied:\n"
    "       export JAPANFOLD_KEY_FILE=\"$HOME/Downloads/japanfold-oslo-hackathon-codes 4.txt\"\n"
    "\n"
    "  3. The login keychain, so every shell and the viewer find it with no file at all\n"
    "     (read from stdin, never echoed):\n"
    "       python3 viz/japanfold.py --set-key\n"
    "       python3 viz/japanfold.py --set-key --from-file \"$HOME/Downloads/japanfold-oslo-hackathon-codes 4.txt\"\n"
    "\n"
    "  4. This shell only:\n"
    "       export JAPANFOLD_API_KEY=...     # also what .mcp.json expands for Claude Code\n"
    "\n"
    f"Without the Slack file, a personal key comes from {TOKEN_URL}\n"
    "($100 of credit on a new account). Then run: python3 viz/japanfold.py --check\n"
    "Do not paste the key into a chat -- it goes to the model provider.")


def set_key(key: str) -> str:
    """Put the key in the login keychain. Returns where it went, never the key."""
    key = (key or "").strip()
    if not key:
        raise NoKey("nothing on stdin. Paste the key, then press ctrl-d.")
    if len(key.split()) != 1 or len(key) < 12:
        raise NoKey("that does not look like a key (one token, 12+ characters). "
                    "If you pasted the whole Slack file, use --from-file instead.")
    if not shutil.which("security"):
        raise JapanFoldError("no `security` binary, so no keychain on this machine. "
                             "Put the key in .env instead.")
    r = subprocess.run(["security", "add-generic-password", "-U", "-a",
                        os.environ.get("USER", "japanfold"), "-s", KEYCHAIN_SERVICE,
                        "-D", "api key", "-j", "JapanFold API key (AI x Antibodies Oslo)",
                        "-w", key], capture_output=True, text=True)
    if r.returncode != 0:
        raise JapanFoldError(f"keychain refused it: {r.stderr.strip()[:300]}")
    return f"login keychain, service {KEYCHAIN_SERVICE!r}"


# ---------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------

class _NoAuthRedirect(urllib.request.HTTPRedirectHandler):
    """Follow a redirect, but never carry the bearer token to another host.

    Artifact URLs redirect to object storage. urllib replays our headers on the new
    request, which would hand the key to a third party; this drops it when the host
    changes and keeps it when it does not.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).netloc != HOST:
            for store in (new.headers, new.unredirected_hdrs):
                for k in [k for k in store if k.lower() == "authorization"]:
                    store.pop(k, None)
        return new


_OPENER = urllib.request.build_opener(_NoAuthRedirect)


def _problem(raw: bytes) -> dict:
    try:
        return json.loads(raw)
    except Exception:                                          # noqa: BLE001
        return {"detail": raw.decode(errors="replace")[:500]}


def _say(p: dict) -> str:
    """RFC 9457 problem detail, as one readable line."""
    said = " - ".join(str(p[k]) for k in ("title", "detail") if p.get(k))
    return said or json.dumps(p)[:400]


def _request(method: str, path: str, body: dict | None = None, *,
             auth: bool = True, timeout: int = 180,
             headers: dict | None = None) -> dict:
    url = path if path.startswith("http") else f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("X-JapanFold-Client", CLIENT_ID)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if data:
        req.add_header("Content-Type", "application/json")
    if auth:
        req.add_header("Authorization", f"Bearer {api_key()}")
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            raw = r.read()
            out = json.loads(raw) if raw else {}
            # A refused hold is not an error: the job's current state comes back at once
            # with a Retry-After. Carry both so wait_for() can pace itself rather than
            # hammer the API.
            if isinstance(out, dict):
                ra = r.headers.get("Retry-After")
                if ra and str(ra).strip().isdigit():
                    out.setdefault("_retry_after", int(str(ra).strip()))
                if r.headers.get("Preference-Applied"):
                    out.setdefault("_held", True)
            return out
    except urllib.error.HTTPError as e:
        payload = _problem(e.read())
        if e.code == 402:
            raise OutOfCredit(
                f"402 out of credit. Add funds at "
                f"{payload.get('billing_url') or TOKEN_URL}: {_say(payload)}") from e
        if e.code in (401, 403):
            raise NoKey(
                f"{e.code} JapanFold rejected the key ({_say(payload)}).\n"
                f"The key came from: {_key_source() or 'nowhere'}. "
                f"If it was revoked, get another at {TOKEN_URL}.") from e
        if e.code == 429:
            ra = (e.headers.get("Retry-After") or "").strip()
            raise Busy(f"429 {_say(payload)}", int(ra) if ra.isdigit() else 30,
                       payload.get("reason", "")) from e
        raise JapanFoldError(f"{method} {url} -> {e.code}: {_say(payload)}") from e
    except urllib.error.URLError as e:
        raise JapanFoldError(f"{method} {url} unreachable: {e.reason}") from e


def _download(path: str, dest: pathlib.Path, timeout: int = 600) -> pathlib.Path:
    url = path if path.startswith("http") else f"{BASE}{path}"
    req = urllib.request.Request(url)
    req.add_header("X-JapanFold-Client", CLIENT_ID)
    req.add_header("Authorization", f"Bearer {api_key()}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with _OPENER.open(req, timeout=timeout) as r, tmp.open("wb") as fh:
        while chunk := r.read(65536):
            fh.write(chunk)
    tmp.replace(dest)              # so a half-written artifact is never read as a whole one
    return dest


# ---------------------------------------------------------------------------
# free, read-only
# ---------------------------------------------------------------------------

_MODELS_CACHE: dict | None = None


def list_models(refresh: bool = False) -> dict:
    """Free and starts nothing. Answer every price question from this."""
    global _MODELS_CACHE
    if _MODELS_CACHE is None or refresh:
        _MODELS_CACHE = _request("GET", "/models", auth=False)
    return _MODELS_CACHE


def model_info(model: str) -> dict:
    m = list_models()
    for bucket in ("models", "design_models", "embed_models"):
        for x in m.get(bucket, []):
            if x.get("id") == model:
                return x
    raise JapanFoldError(f"unknown model {model!r}. Free list: --models")


def account() -> dict:
    return _request("GET", "/account")


def credits() -> dict:
    return _request("GET", "/credits")


def cluster() -> dict:
    """Fleet load: how busy the service is before we promise a live demo.

    Free (it bills nothing and starts nothing) but it DOES need the key, even though the
    published spec lists no 401 for it -- so it is called only once a key is present.
    """
    return _request("GET", "/cluster")


def check() -> dict:
    """Is the lane usable, what would it spend against, and how busy is the queue?"""
    out = {"base": BASE, "mcp": MCP_URL,
           "key_present": bool(api_key(required=False)),
           "key_source": _key_source(),
           "key_fingerprint": key_fingerprint(),
           "dotenv": str(REPO / ".env") if (REPO / ".env").is_file() else None,
           "dotenv_set": DOTENV_LOADED,
           "key_file": str(key_path()), "key_file_exists": key_path().is_file()}
    try:
        models = list_models(refresh=True)
        out["reachable"] = True
        out["n_predict_models"] = len(models.get("models", []))
    except JapanFoldError as e:
        out["reachable"] = False
        out["error"] = str(e)
        return out
    if not out["key_present"]:
        out["next_step"] = "python3 viz/japanfold.py --key-help"
        return out
    try:
        c = cluster()
        out["fleet"] = {k: c.get(k) for k in
                        ("online_agents", "chips", "busy", "out_of_service",
                         "accounts_waiting", "jobs") if k in c}
    except JapanFoldError:
        pass
    try:
        acct = account()
        out["key_valid"] = True
        out["account"] = {k: acct.get(k) for k in
                          ("balance", "balance_usd", "balance_micros", "rate", "email",
                           "credits", "name") if k in acct}
        # The viewer's lane row shows whichever of these exists; keep the familiar name.
        if "balance" in acct and "balance_usd" not in out["account"]:
            out["account"]["balance_usd"] = acct["balance"]
    except NoKey as e:
        out["key_valid"] = False
        out["account_error"] = str(e)
    except JapanFoldError as e:
        out["account_error"] = str(e)
    return out


def price(model: str, n: int = 1) -> dict:
    """What `n` targets of `model` have cost lately. History, not a quote.

    GET /v1/models is explicit about this: a prediction runs each target on its own chip
    and is billed per chip-second, so the per-TARGET figures are the ones that scale with a
    batch. The per-JOB usd_p50/usd_p90 follow whatever batch sizes other users happened to
    send that week (targets_p50), so multiplying those by n -- which this module used to do
    -- overstates a batch several-fold: af2ig's per-job median is $0.0049 at a typical 12
    targets, i.e. $0.0004 a target, so 18 designs is under a cent, not $0.09. Design and
    embedding jobs split their own work across chips and publish per-job figures only; for
    those, n is reported but the total stays the per-job figure.
    """
    m = model_info(model)
    tc = m.get("typical_cost") or {}
    per50, per90 = tc.get("usd_per_target_p50"), tc.get("usd_per_target_p90")
    job50, job90 = tc.get("usd_p50"), tc.get("usd_p90")
    per_target = per50 is not None or per90 is not None
    each50 = per50 if per_target else job50
    each90 = per90 if per_target else job90

    def tot(each):
        if each is None:
            return None
        return round(each * n, 6) if per_target else round(each, 6)

    return {
        "model": model, "n": n,
        "usd_p50_each": each50, "usd_p90_each": each90,
        "usd_p50_total": tot(each50), "usd_p90_total": tot(each90),
        "basis": ("per target x n, one job (each target gets its own chip)" if per_target
                  else "per job (this model publishes no per-target figure)"),
        "jobs_observed": tc.get("jobs"), "since": tc.get("since"),
        "usd_p50_per_job_observed": job50, "usd_p90_per_job_observed": job90,
        "targets_p50_observed": tc.get("targets_p50"),
        "one_job": per_target,
        "note": ("median/p90 of the last 7 days of real jobs, not a quote: a run bills for "
                 "the chip-time it actually takes. null means fewer than 20 jobs."),
    }


def estimate(model: str, design_ids: list[str]) -> dict:
    p = price(model, len(design_ids))
    p["design_ids"] = design_ids
    p["spends_nothing"] = True
    p["plan"] = (f"one job, {len(design_ids)} target(s), {model}" if p["one_job"]
                 else f"{len(design_ids)} job(s) on {model}")
    return p


# ---------------------------------------------------------------------------
# structure conversion: our mmCIF co-folds -> the PDB block af2ig wants
# ---------------------------------------------------------------------------

AA3 = {"ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q", "GLU": "E",
       "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F",
       "PRO": "P", "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V"}


def _backends():
    sys.path.insert(0, str(HERE))
    import backends as B
    return B


def cif_to_pdb_block(cif: pathlib.Path,
                     chains: dict[str, str]) -> tuple[str, dict[str, int]]:
    """Write selected chains as PDB ATOM records, renaming them.

    `chains` maps source chain -> output chain, e.g. {"C": "A", "H": "B"}. af2ig wants one
    target chain and one binder chain, and PDB gives a chain id a single column, so the
    rename is not cosmetic -- it is what keeps the two chains distinguishable.

    Returns the block and a residue count per OUTPUT chain. The counts are not decoration:
    af2ig requires the binder chain in the structure to be the same length as the binder
    sequence, and they decide the token axis when the PAE matrix is read back.
    """
    B = _backends()
    atoms = B.parse_structure(cif)
    lines, serial, counts = [], 1, {}
    for src, dst in chains.items():
        sel = [a for a in atoms if a[0] == src]
        if not sel:
            raise JapanFoldError(f"{cif}: chain {src!r} absent")
        counts[dst] = len({a[1] for a in sel})
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
    return "\n".join(lines), counts


def chain_sequence(cif: pathlib.Path, chain: str) -> str:
    B = _backends()
    seen: dict[int, str] = {}
    for ch, resseq, comp, name, *_ in B.parse_structure(cif):
        if ch == chain and name == "CA":
            seen[resseq] = AA3.get(comp.upper(), "X")
    return "".join(seen[k] for k in sorted(seen))


def af2ig_target(cif: pathlib.Path, *, target_chain: str = "C",
                 binder_chain: str = "H") -> dict:
    """One `targets` entry for af2ig: target coordinates plus the binder's sequence.

    Only VH goes in as the binder, matching the VH-vs-VH baseline the catalog compares
    against (the 19-residue epitope was defined from the whole Fab; the light chain
    accounts for the residues neither VH reaches).

    af2ig's input is NOT a chain list -- a `sequences:` block is refused -- and it is NOT
    the request's `input` field: it is one target's `content`. Sending it as `input` is
    what this module did before, and it fails at submit, after the queue wait.
    """
    block, counts = cif_to_pdb_block(cif, {target_chain: "A", binder_chain: "B"})
    binder_seq = chain_sequence(cif, binder_chain)
    if not binder_seq:
        raise JapanFoldError(f"{cif}: no CA atoms in chain {binder_chain!r}")
    if counts.get("B") != len(binder_seq):
        raise JapanFoldError(
            f"{cif}: binder chain {binder_chain!r} has {counts.get('B')} residues but "
            f"{len(binder_seq)} have a CA. af2ig requires the binder backbone and the "
            f"binder sequence to be the same length, so this would be refused at submit.")
    n_tokens = counts.get("A", 0) + counts.get("B", 0)
    cap = model_info("af2ig").get("max_residues", 1024)
    if n_tokens > cap:
        raise JapanFoldError(
            f"{cif}: {n_tokens} residues (target {counts.get('A')} + binder "
            f"{counts.get('B')}) is over af2ig's {cap}-residue ceiling.")
    indented = "\n".join("    " + l for l in block.splitlines())
    content = (f"target:\n  structure: |\n{indented}\n  chain: A\n"
               f"binder:\n  sequence: {binder_seq}\n  chain: B\n")
    return {"content": content, "n_target": counts.get("A", 0),
            "n_binder": counts.get("B", 0), "binder_sequence": binder_seq}


def af2ig_yaml(cif: pathlib.Path, *, target_chain: str = "C",
               binder_chain: str = "H") -> str:
    """The YAML alone, for callers that only want to see what would be sent."""
    return af2ig_target(cif, target_chain=target_chain,
                        binder_chain=binder_chain)["content"]


# ---------------------------------------------------------------------------
# job plumbing
# ---------------------------------------------------------------------------

def submit_prediction(*, model: str, name: str, targets: list[dict] | None = None,
                      input_text: str | None = None, params: dict | None = None,
                      idempotency_key: str | None = None) -> dict:
    """POST /v1/predictions. `targets` for one-per-chip batches, `input_text` for one complex.

    The Idempotency-Key matters to a budget, not just to tidiness: resending a submit that
    timed out returns the FIRST job instead of starting a second one to pay for. A key
    names its job for 24 h.
    """
    if not targets and not input_text:
        raise JapanFoldError("submit needs either targets or input_text")
    body: dict = {"model": model, "name": name, "params": params or {}}
    if targets:
        body["targets"] = targets
    else:
        body["input"] = input_text
    return _request("POST", "/predictions", body,
                    headers={"Idempotency-Key": idempotency_key or str(uuid.uuid4())})


def job(job_id: str, wait: int = 0) -> dict:
    """One job's state. `wait` holds the request open (the service caps the hold at 60 s)."""
    w = max(0, min(int(wait), 60))
    return _request("GET", f"/jobs/{job_id}" + (f"?wait={w}" if w else ""), timeout=w + 60)


def jobs(limit: int = 20, status: str | None = None) -> list[dict]:
    q = f"/jobs?limit={max(1, min(int(limit), 100))}" + (f"&status={status}" if status else "")
    out = _request("GET", q)
    for k in ("data", "jobs", "items"):
        if isinstance(out.get(k), list):
            return out[k]
    return []


def _fmt_elapsed(s: float) -> str:
    s = int(s)
    return f"{s // 60}m{s % 60:02d}s" if s >= 60 else f"{s}s"


def wait_for(job_id: str, *, max_wait: int = 3600, progress=None, hold: int = 60) -> dict:
    """Hold on one job until it ends, without sleeping between polls.

    `GET /jobs/{id}?wait=60` answers the moment the job finishes, so the loop paces itself
    and a finished job is seen immediately -- which is the difference between a demo that
    looks live and one that looks like it hung. Two rules from the service, both honoured
    here: one account is held on two jobs at a time (so wait on ONE job, never a batch in
    parallel -- itself a reason to put every design in a single job), and a refused hold
    comes back at once with Retry-After, which is the only time this sleeps.
    """
    t0 = time.monotonic()
    while True:
        try:
            j = job(job_id, wait=hold)
        except Busy as e:
            if progress:
                progress({"status": "queued",
                          "stage": f"rate-limited ({e.reason or 'busy'})"},
                         time.monotonic() - t0)
            time.sleep(min(e.retry_after, 60))
            continue
        status = (j.get("status") or "").lower()
        if progress:
            progress(j, time.monotonic() - t0)
        if status in ("succeeded", "failed", "canceled", "cancelled"):
            return j
        # Only sleep when the service said it would not hold the request open.
        if not j.get("_held") and j.get("_retry_after"):
            time.sleep(min(int(j["_retry_after"]), 60))
        if time.monotonic() - t0 >= max_wait:
            raise JapanFoldError(
                f"job {job_id} still {status} after {_fmt_elapsed(time.monotonic() - t0)}. "
                f"It is NOT lost and nothing extra is billed by leaving it: re-attach any "
                f"time, from any machine with the same key:\n"
                f"  python3 viz/japanfold.py --watch {job_id}")


def results(job_id: str) -> dict:
    return _request("GET", f"/jobs/{job_id}/results")


def job_input(job_id: str) -> dict:
    return _request("GET", f"/jobs/{job_id}/input")


def usage(job_id: str) -> dict:
    """What the job actually billed. Answers once the job has ended."""
    return _request("GET", f"/jobs/{job_id}/usage")


def logs(job_id: str) -> str:
    try:
        out = _request("GET", f"/jobs/{job_id}/logs")
        return out if isinstance(out, str) else json.dumps(out)[:8000]
    except JapanFoldError as e:
        return f"(logs unavailable: {e})"


def fetch_artifacts(job_id: str, dest: pathlib.Path, res: dict | None = None,
                    only: str | None = None) -> list[pathlib.Path]:
    """Download a job's files. `only` keeps the ones whose path contains it (one target)."""
    res = res if res is not None else results(job_id)
    got = []
    for a in (res.get("artifacts") or res.get("files") or []):
        if isinstance(a, dict):
            rel, url = a.get("path") or a.get("name"), a.get("url")
        else:
            rel, url = str(a), None
        if not rel or (only and only not in rel):
            continue
        try:
            got.append(_download(url or f"/jobs/{job_id}/artifacts/{rel}",
                                 dest / pathlib.Path(rel).name))
        except (urllib.error.HTTPError, urllib.error.URLError, JapanFoldError) as e:
            print(f"  ! could not fetch {rel}: {e}", file=sys.stderr)
    (dest / "results.json").write_text(json.dumps(res, indent=2))
    return got


# ---------------------------------------------------------------------------
# reading a prediction's scores
# ---------------------------------------------------------------------------

def _rows(res: dict) -> list[dict]:
    """Per-target score rows. The service calls them `rows`; be generous about the rest."""
    for k in ("rows", "targets", "predictions", "scores"):
        v = res.get(k)
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v
    return []


def _dig(row: dict, *names):
    for n in names:
        if row.get(n) is not None:
            return row[n]
    for src in (row.get("scores"), row.get("metrics"), row.get("confidence")):
        if isinstance(src, dict):
            for n in names:
                if src.get(n) is not None:
                    return src[n]
    return None


def row_scores(row: dict) -> dict:
    """The numbers axis 1 needs, out of one results row.

    af2ig's row carries plddt, ptm, iptm, pae, ipae and interface_pae (Angstrom); the
    co-folders carry iptm, complex_plddt, confidence_score and the chain-pair matrix. This
    used to look in a `scores`/`metrics` dict that the API does not return, so every number
    came back None and the lane reported success having measured nothing.
    """
    return {
        "iptm": _dig(row, "iptm", "ipTM", "interface_ptm"),
        "interface_pae": _dig(row, "interface_pae", "ipae", "pae_interaction", "min_ipae"),
        "plddt": _dig(row, "plddt", "complex_plddt", "mean_plddt"),
        "binder_plddt": _dig(row, "binder_plddt", "chain_plddt_B"),
        "ptm": _dig(row, "ptm"),
        "confidence_score": _dig(row, "confidence_score"),
        "pair_chains_iptm": _dig(row, "pair_chains_iptm"),
    }


def _row_name(row: dict) -> str:
    return str(_dig(row, "name", "target", "target_name", "id") or "")


# ---------------------------------------------------------------------------
# ipSAE, computed here from the PAE matrix the service returns
# ---------------------------------------------------------------------------

def ipsae_from_npz(npz: pathlib.Path, n_target: int, n_binder: int,
                   cutoff: float = 15.0) -> dict:
    """ipSAE for a two-chain interface, from <name>_pae.npz.

    OURS, not the service's: JapanFold returns the PAE matrix and says it is the one
    Adaptyv's ipSAE pipeline reads, but it does not return an ipSAE number, so this
    computes one and every report of it says locally computed. The definition followed is
    Dunbrack's ipSAE: for each residue i on one side, take the partner residues j across
    the interface with PAE(i,j) < cutoff, set d0 from that count by the Yang-Skolnick
    form, average 1/(1+(PAE/d0)^2) over them, and report the best residue. PAE is
    asymmetric, so both directions are computed and the larger is taken.

    The token axis is the structure's own order, which for our af2ig input is the target
    chain then the binder chain. If the matrix is not exactly n_target + n_binder long the
    split is not certain, so nothing is reported and the reason is returned instead. A
    missing array is never read as zeros.
    """
    try:
        import numpy as np
    except ImportError:
        return {"ipsae": None,
                "basis": f"numpy not available here; the PAE matrix is kept at {npz}"}
    side = npz.with_name(npz.name.replace("_pae.npz", "_pae.json"))
    if side.is_file():
        try:
            arrays = (json.loads(side.read_text()) or {}).get("arrays")
        except (json.JSONDecodeError, OSError):
            arrays = None
        if arrays:
            names = list(arrays) if isinstance(arrays, dict) else [
                (a.get("name") if isinstance(a, dict) else str(a)) for a in arrays]
            if "pae" not in names:
                return {"ipsae": None,
                        "basis": f"{side.name} lists no `pae` array (has {names})"}
    with np.load(npz) as m:
        if "pae" not in m:
            return {"ipsae": None, "basis": f"{npz.name} has no `pae` array"}
        pae = np.asarray(m["pae"], dtype="float64")
    if pae.ndim != 2 or pae.shape[0] != pae.shape[1]:
        return {"ipsae": None, "basis": f"{npz.name}: pae is {pae.shape}, not square"}
    n = pae.shape[0]
    if n != n_target + n_binder:
        return {"ipsae": None,
                "basis": (f"{npz.name}: {n} tokens but the input was {n_target} target + "
                          f"{n_binder} binder = {n_target + n_binder}; the chain split is "
                          f"not certain, so no ipSAE rather than a wrong one")}
    a, b = slice(0, n_target), slice(n_target, n)

    def directional(block):
        """block[i, j]: PAE of partner j aligned on residue i. The best residue wins."""
        best, best_i, best_n0 = 0.0, None, 0
        for i in range(block.shape[0]):
            sel = block[i][block[i] < cutoff]
            n0 = int(sel.size)
            if n0 == 0:
                continue
            d0 = max(1.0, 1.24 * (n0 - 15) ** (1.0 / 3.0) - 1.8) if n0 > 15 else 1.0
            val = float(np.mean(1.0 / (1.0 + (sel / d0) ** 2)))
            if val > best:
                best, best_i, best_n0 = val, i, n0
        return best, best_i, best_n0

    fwd, i_f, n_f = directional(pae[a, b])        # binder judged from the target
    rev, i_r, n_r = directional(pae[b, a])        # target judged from the binder
    inter = np.concatenate([pae[a, b].ravel(), pae[b, a].ravel()])
    forward_wins = fwd >= rev
    return {
        "ipsae": round(max(fwd, rev), 4),
        "ipsae_forward": round(fwd, 4), "ipsae_reverse": round(rev, 4),
        "ipsae_anchor": {"direction": "target->binder" if forward_wins else "binder->target",
                         "token": i_f if forward_wins else i_r,
                         "partners_under_cutoff": n_f if forward_wins else n_r},
        "min_interface_pae_from_matrix": round(float(inter.min()), 4),
        "mean_interface_pae_from_matrix": round(float(inter.mean()), 4),
        "n_tokens": n, "cutoff_A": cutoff,
        "basis": (f"COMPUTED LOCALLY from this job's {npz.name} (the PAE matrix as returned "
                  f"by JapanFold): ipSAE, PAE cutoff {cutoff} A, d0 by Yang-Skolnick on the "
                  f"partner count, max over both directions. The service returns the matrix "
                  f"and no ipSAE of its own, so this number is ours, from its matrix."),
    }


# ---------------------------------------------------------------------------
# axis 1: ipTM and interface pAE for designs we already folded
# ---------------------------------------------------------------------------

def _progress_printer(label: str, n_targets: int = 1):
    """A live status line. Rewrites in place on a tty, one line per change elsewhere."""
    tty = sys.stderr.isatty()
    last = [""]

    def p(j: dict, elapsed: float):
        bits = [f"{label} {(j.get('status') or '?').lower()}"]
        if j.get("stage"):
            bits.append(str(j["stage"]))
        done, total = j.get("done"), j.get("total") or (n_targets or None)
        if done is not None and total:
            bits.append(f"{done}/{total} targets")
        elif isinstance(j.get("progress"), (int, float)):
            bits.append(f"{round(j['progress'] * 100)}%")
        q = j.get("queue") or {}
        if q:
            fleet = q.get("fleet") or {}
            qbits = []
            if q.get("accounts_ahead") is not None:
                qbits.append(f"behind {q['accounts_ahead']} account(s)")
            if fleet.get("busy") is not None and fleet.get("chips") is not None:
                qbits.append(f"{fleet['busy']}/{fleet['chips']} chips busy")
            if q.get("reason"):
                qbits.append(str(q["reason"]))
            if qbits:
                bits.append("; ".join(qbits))
        if j.get("attempt"):
            bits.append(f"attempt {j['attempt']} (a box stopped answering; billed once)")
        line = f"  {' | '.join(bits)}  [{_fmt_elapsed(elapsed)}]"
        if tty:
            print("\r" + line + " " * max(0, len(last[0]) - len(line)),
                  end="", file=sys.stderr, flush=True)
            last[0] = line
        elif line.strip() != last[0].strip():
            print(line, file=sys.stderr, flush=True)
            last[0] = line

    def done():
        if tty and last[0]:
            print(file=sys.stderr)

    p.done = done                                              # type: ignore[attr-defined]
    return p


def score_af2ig(design_ids: str | list[str], *, cif: pathlib.Path | None = None,
                write_pae: bool = True, wait: bool = True, ipsae: bool = True,
                job_name: str | None = None) -> dict | list[dict]:
    """Run AF2-IG on co-folds we already have. Returns ipTM and interface pAE per design.

    This is the one call that turns `iptm`/`min_ipae` from 'n/a' into a measured number.

    One design or eighteen, it is ONE job: each target gets its own chip, so a batch costs
    per target and queues once. Passing a single id returns a single dict (what the
    viewer's backend expects); passing a list returns a list.
    """
    single = isinstance(design_ids, str)
    ids = [design_ids] if single else list(design_ids)
    if not ids:
        raise JapanFoldError("no design ids given")
    B = _backends()
    index = B._cofold_index()

    targets, meta, skipped = [], {}, []
    for did in ids:
        path = pathlib.Path(cif) if (cif is not None and single) else index.get(did)
        if path is None:
            skipped.append({"design_id": did, "status": "skipped", "error": (
                f"no co-fold in {B.COFOLD}. af2ig scores a complex you already have; "
                f"fold it first (--fold, or the hosted lane).")})
            continue
        try:
            t = af2ig_target(pathlib.Path(path))
        except JapanFoldError as e:
            skipped.append({"design_id": did, "status": "skipped", "error": str(e)})
            continue
        targets.append({"name": did, "content": t["content"]})
        meta[did] = {**{k: v for k, v in t.items() if k != "content"}, "cif": str(path)}

    if not targets:
        if single:
            raise JapanFoldError(skipped[0]["error"] if skipped else "nothing to score")
        return skipped

    name = job_name or (f"af2ig-{ids[0]}" if len(targets) == 1
                        else f"af2ig-her2-{len(targets)}designs")
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    batch_dir = OUT_ROOT / "af2ig" / "_jobs" / stamp
    batch_dir.mkdir(parents=True, exist_ok=True)
    # The idempotency key is written down BEFORE the submit: if the POST times out, the
    # retry reuses it and we get the first job back instead of paying for a second one.
    idem = str(uuid.uuid4())
    (batch_dir / "submit.json").write_text(json.dumps(
        {"model": "af2ig", "name": name, "idempotency_key": idem,
         "targets": [t["name"] for t in targets],
         "params": {"write_pae": bool(write_pae)},
         "meta": meta, "skipped": skipped}, indent=2))
    for t in targets:
        d = OUT_ROOT / "af2ig" / t["name"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "input.yaml").write_text(t["content"])

    j = submit_prediction(model="af2ig", name=name, targets=targets,
                          params={"write_pae": bool(write_pae)}, idempotency_key=idem)
    job_id = j.get("id") or j.get("job_id")
    if not job_id:
        raise JapanFoldError(f"no job id in response: {j}")
    (batch_dir / "job.json").write_text(json.dumps(j, indent=2))
    print(f"  submitted {job_id}: af2ig x {len(targets)} target(s)"
          + (f", skipped {len(skipped)}" if skipped else ""), file=sys.stderr)
    for w in (j.get("warnings") or []):
        print(f"  ! warning: {w}", file=sys.stderr)

    if not wait:
        pending = [{"design_id": d, "job_id": job_id, "status": j.get("status", "queued"),
                    "dest": str(OUT_ROOT / "af2ig" / d),
                    "watch": f"python3 viz/japanfold.py --watch {job_id}"} for d in meta]
        return (pending + skipped)[0] if single else pending + skipped

    out = collect_af2ig(job_id, meta=meta, ipsae=ipsae, batch_dir=batch_dir) + skipped
    return out[0] if single else out


def collect_af2ig(job_id: str, *, meta: dict | None = None, ipsae: bool = True,
                  batch_dir: pathlib.Path | None = None,
                  wait: bool = True) -> list[dict]:
    """Wait on an af2ig job (if it is still running), then write one score.json per design.

    Separate from the submit so a job can be re-attached later -- `--watch JOB_ID` lands
    here -- and so a closed laptop never costs a re-run.
    """
    pr = _progress_printer(f"af2ig {job_id}", len(meta or {}) or 1)
    done = wait_for(job_id, progress=pr) if wait else job(job_id)
    pr.done()                                                  # type: ignore[attr-defined]
    batch_dir = batch_dir or (OUT_ROOT / "af2ig" / "_jobs" / job_id)
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "job.json").write_text(json.dumps(done, indent=2))

    # Re-attaching to someone else's submit: recover the target names from the job itself.
    if not meta:
        names = [t.get("name") for t in (done.get("targets") or [])
                 if isinstance(t, dict) and t.get("name")]
        if not names:
            try:
                inp = job_input(job_id)
                names = [t.get("name") for t in (inp.get("targets") or [])
                         if isinstance(t, dict) and t.get("name")]
            except JapanFoldError:
                names = []
        index = _backends()._cofold_index()
        meta = {}
        for nm in names:
            m: dict = {}
            saved = OUT_ROOT / "af2ig" / nm / "input.yaml"
            if nm in index:
                try:
                    t = af2ig_target(pathlib.Path(index[nm]))
                    m = {k: v for k, v in t.items() if k != "content"}
                    m["cif"] = str(index[nm])
                except JapanFoldError:
                    m = {}
            elif saved.is_file():
                m = {}
            meta[nm] = m

    status = (done.get("status") or "").lower()
    if status != "succeeded":
        (batch_dir / "logs.txt").write_text(logs(job_id))
        err = done.get("error") or done.get("message") or status
        print(f"  ! job {status}: {err}\n    logs: {batch_dir / 'logs.txt'}",
              file=sys.stderr)
        return [{"design_id": d, "job_id": job_id, "status": status, "error": err,
                 "logs": str(batch_dir / "logs.txt")} for d in (meta or {"?": {}})]

    if done.get("partial"):
        p = done["partial"]
        print(f"  ! partial: {p.get('delivered')} of {p.get('requested')} "
              f"{p.get('unit', 'targets')} came back. {done.get('error') or ''}",
              file=sys.stderr)

    res = results(job_id)
    (batch_dir / "results.json").write_text(json.dumps(res, indent=2))
    rows = _rows(res)
    if not rows:
        print(f"  ! the job succeeded but returned no score rows; keeping "
              f"{batch_dir / 'results.json'} to look at", file=sys.stderr)

    # Match rows to designs by name, and fall back to order only when the service echoes no
    # name at all. Never by position when names exist: a silent misalignment here staples
    # one design's interface error onto another, the exact failure catalog.py calls out for
    # the id-collision case.
    by_name = {_row_name(r): r for r in rows if _row_name(r)}
    ids = list(meta or by_name or {})
    out = []
    for i, did in enumerate(ids):
        row = by_name.get(did) or ({} if by_name else (rows[i] if i < len(rows) else {}))
        m = (meta or {}).get(did) or {}
        dest = OUT_ROOT / "af2ig" / did
        dest.mkdir(parents=True, exist_ok=True)
        files = fetch_artifacts(job_id, dest, res=res, only=did) if rows else []
        sc = row_scores(row)
        rec = {
            "design_id": did, "job_id": job_id, "status": "succeeded", "model": "af2ig",
            "iptm": sc["iptm"], "interface_pae": sc["interface_pae"],
            "plddt": sc["plddt"], "binder_plddt": sc["binder_plddt"], "ptm": sc["ptm"],
            "confidence_score": sc["confidence_score"],
            "pair_chains_iptm": sc["pair_chains_iptm"],
            "binder_sequence": m.get("binder_sequence"),
            "n_target": m.get("n_target"), "n_binder": m.get("n_binder"),
            "cofold": m.get("cif"), "dest": str(dest),
            "artifacts": [str(f) for f in files],
            "row_raw": row,
            "basis": ("MEASURED: JapanFold af2ig (AlphaFold2 initial-guess, "
                      "params_model_1_ptm, CC BY 4.0) on the Boltz-2 co-fold complex; VH "
                      "as binder, HER2 as target. Deterministic: no MSA, no sampling, no "
                      "seed, so the same input gives the same answer."),
            "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if ipsae and m.get("n_target"):
            npz = next((f for f in files if f.name.endswith("_pae.npz")), None)
            if npz is not None:
                rec["ipsae_detail"] = ipsae_from_npz(npz, m["n_target"], m["n_binder"])
                rec["ipsae"] = rec["ipsae_detail"].get("ipsae")
                rec["ipsae_basis"] = rec["ipsae_detail"].get("basis")
            else:
                rec["ipsae"] = None
                rec["ipsae_basis"] = "no *_pae.npz artifact (was write_pae set?)"
        (dest / "score.json").write_text(json.dumps(rec, indent=2))
        out.append(rec)

    try:
        u = usage(job_id)
        (batch_dir / "usage.json").write_text(json.dumps(u, indent=2))
        if u.get("amount") is not None:
            per = (f", ~${round(u['amount'] / len(out), 5)} each" if len(out) > 1 else "")
            print(f"  billed ${u['amount']}{per} for {len(out)} target(s)"
                  + (f", {u.get('billable_s')}s of chip time" if u.get("billable_s")
                     else ""), file=sys.stderr)
    except JapanFoldError:
        pass

    write_metrics_csv(out)
    return out


def write_metrics_csv(records: list[dict], path: pathlib.Path = METRICS_CSV) -> pathlib.Path:
    """Write/refresh reports/japanfold-af2ig-metrics.csv in the refold-metrics schema.

    Deliberately the same column names as reports/b*_refold_metrics.csv, because that is
    what the rest of the pipeline already reads:

        python3 pipeline/score/rank.py --refold reports/japanfold-af2ig-metrics.csv ...

    gets a MEASURED min_ipae for axis 1, and viz/catalog.py's join-on-heavy-sequence picks
    the same rows up with no change at all. `query_id` carries the full batch-qualified
    design id, which rank.py's score_table() keeps as-is -- so nothing is ever stripped to
    a bare number that could collide across batches.
    """
    keep = [r for r in records if r.get("status") == "succeeded"
            and (r.get("interface_pae") is not None or r.get("iptm") is not None)]
    if not keep:
        return path
    rows = {}
    if path.is_file():
        with path.open() as fh:
            for r in csv.DictReader(fh):
                rows[r.get("query_id", "")] = r
    for r in keep:
        rows[r["design_id"]] = {
            "query_id": r["design_id"],
            "design": r.get("cofold", ""),
            "model": "japanfold:af2ig",
            "status": "measured",
            "binder_chain": "B (VH)",
            "target_chains": "A (HER2, 1N8Z chain C)",
            "binder_sequence": r.get("binder_sequence") or "",
            # min_ipae is the column rank.py ranks on; af2ig's interface_pae IS the
            # interface error for this complex, so it is written there under both names.
            "min_ipae": r.get("interface_pae"),
            "interface_pae": r.get("interface_pae"),
            "iptm": r.get("iptm"),
            "ptm": r.get("ptm"),
            "plddt": r.get("plddt"),
            "binder_plddt": (r.get("binder_plddt") if r.get("binder_plddt") is not None
                             else r.get("plddt")),
            "binder_ptm": r.get("ptm"),
            "ipsae": r.get("ipsae"),
            "ipsae_basis": ("locally computed from this job's PAE matrix; see score.json"
                            if r.get("ipsae") is not None
                            else (r.get("ipsae_basis") or "")),
            "job_id": r.get("job_id", ""),
            "measured_at": r.get("measured_at", ""),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=METRICS_COLS, extrasaction="ignore", restval="")
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])
    print(f"  wrote {path.relative_to(REPO)} ({len(rows)} design(s) with a measured "
          f"axis 1)", file=sys.stderr)
    return path


def measured_axis1() -> dict[str, dict]:
    """What this lane has already measured, read off disk. Free, and starts nothing.

    The viewer calls this on every page load, so it must never touch the network.
    """
    out = {}
    if METRICS_CSV.is_file():
        with METRICS_CSV.open() as fh:
            for r in csv.DictReader(fh):
                if r.get("query_id"):
                    out[r["query_id"]] = r
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
    """Boltz-style YAML: VH (H), VL (L), HER2 (C), with an optional epitope constraint.

    OpenDDE addresses residues by ENTITY NUMBER, not chain letter: `entity` is the 1-based
    position in `sequences`, `copy` the 1-based copy, `position` the 1-based residue. The
    epitope block is written from whatever position HER2 actually ended up in, rather than
    a hard-coded 3, so dropping the light chain cannot silently point the guidance at the
    antibody instead of the antigen.
    """
    B = _backends()
    parts = ["version: 1", "sequences:",
             "  - protein:", "      id: H", f"      sequence: {heavy}"]
    entity = {"H": 1}
    if light:
        parts += ["  - protein:", "      id: L", f"      sequence: {light}"]
        entity["L"] = len(entity) + 1
    if target:
        parts += ["  - protein:", "      id: C", f"      sequence: {her2_sequence()}"]
        entity["C"] = len(entity) + 1
    if epitope_guidance and target:
        movable = "[H, L]" if light else "[H]"
        res = ", ".join("{entity: %d, copy: 1, position: %d}" % (entity["C"], r)
                        for r in B.HER2_EPITOPE)
        parts += ["constraint:",
                  f"  movable_chains: {movable}",
                  "  epitope:",
                  f"    residues: [{res}]",
                  "    min_fraction: 0.5"]
    return "\n".join(parts) + "\n"


def fold(heavy: str, light: str | None = None, *, model: str = "openfold3",
         name: str = "fold", epitope_guidance: bool = False, write_pae: bool = True,
         wait: bool = True, extra_params: dict | None = None) -> dict:
    """Co-fold a design against HER2 on JapanFold.

    openfold3 by default: it is the OpenFold Consortium model, which is the one
    docs/tools-apheris.md flags for the prize condition. opendde-abag is the
    antibody-antigen checkpoint and is the one that accepts epitope guidance.
    """
    info = model_info(model)
    caps = set(info.get("caps") or [])
    if epitope_guidance and "guidance" not in caps:
        raise JapanFoldError(
            f"{model} does not advertise the 'guidance' capability (caps: {sorted(caps)}); "
            f"use opendde-abag for epitope-steered refolds.")
    n_res = len(heavy) + len(light or "") + len(her2_sequence())
    cap, wall = info.get("max_residues"), info.get("measured_wall")
    if cap and n_res > cap:
        raise JapanFoldError(f"{n_res} residues is over {model}'s {cap}-residue ceiling.")
    if wall and n_res > wall:
        print(f"  ! {n_res} residues is above {model}'s measured wall ({wall}); the service "
              f"accepts it on purpose and it may still fail on device.", file=sys.stderr)

    yaml_text = fold_yaml(heavy, light, epitope_guidance=epitope_guidance)
    params: dict = {}
    if write_pae and "pae" in caps:
        params["write_pae"] = True
    params.update(extra_params or {})
    if epitope_guidance:
        params["use_tfg_guidance"] = True

    dest = OUT_ROOT / model / name
    dest.mkdir(parents=True, exist_ok=True)
    idem = str(uuid.uuid4())
    (dest / "input.yaml").write_text(yaml_text)
    (dest / "submit.json").write_text(json.dumps(
        {"model": model, "name": name, "params": params, "idempotency_key": idem}, indent=2))

    j = submit_prediction(model=model, name=name, input_text=yaml_text, params=params,
                          idempotency_key=idem)
    job_id = j.get("id") or j.get("job_id")
    if not job_id:
        raise JapanFoldError(f"no job id in response: {j}")
    (dest / "job.json").write_text(json.dumps(j, indent=2))
    print(f"  submitted {job_id}  ({model}/{name})", file=sys.stderr)
    for w in (j.get("warnings") or []):
        print(f"  ! warning: {w}", file=sys.stderr)
    if not wait:
        return {"job_id": job_id, "status": j.get("status"), "dest": str(dest),
                "watch": f"python3 viz/japanfold.py --watch {job_id}"}

    pr = _progress_printer(f"{model} {job_id}")
    done = wait_for(job_id, progress=pr)
    pr.done()                                                  # type: ignore[attr-defined]
    (dest / "job.json").write_text(json.dumps(done, indent=2))
    if (done.get("status") or "").lower() != "succeeded":
        (dest / "logs.txt").write_text(logs(job_id))
        return {"job_id": job_id, "status": done.get("status"),
                "error": done.get("error"), "logs": str(dest / "logs.txt"),
                "dest": str(dest)}

    res = results(job_id)
    files = fetch_artifacts(job_id, dest, res=res)
    cif = next((f for f in files if f.suffix.lower() in (".cif", ".pdb")), None)
    # Make it readable by the viewer exactly like a hosted co-fold.
    if cif and cif.name != "model.cif":
        try:
            (dest / "model.cif").write_bytes(cif.read_bytes())
        except OSError:
            pass
    rows = _rows(res)
    return {"job_id": job_id, "status": "succeeded", "model": model,
            "dest": str(dest), "structure": str(cif) if cif else None,
            "scores": row_scores(rows[0]) if rows else {},
            "results": res,
            "basis": (f"MEASURED: JapanFold {model} co-fold of VH"
                      + ("+VL" if light else "") + " with HER2"
                      + (", sampling steered onto the 19 epitope residues"
                         if epitope_guidance else ""))}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_check(st: dict) -> None:
    def tick(b):
        return "ok " if b else "-- "

    print(f"\n  JapanFold  {st['base']}")
    print(f"  {tick(st.get('reachable'))}reachable"
          + (f", {st.get('n_predict_models')} prediction models" if st.get("reachable")
             else f": {st.get('error', '')[:160]}"))
    f = st.get("fleet") or {}
    if f:
        j = f.get("jobs") or {}
        print(f"      fleet: {f.get('online_agents')} agents, {f.get('busy')}/"
              f"{f.get('chips')} chips busy, {j.get('queued', '?')} queued / "
              f"{j.get('running', '?')} running, "
              f"{f.get('accounts_waiting')} accounts waiting")
    print(f"  {tick(st.get('key_present'))}key"
          + (f" from {st['key_source']}  [{st['key_fingerprint']}]"
             if st.get("key_present") else " not found"))
    if st.get("key_present"):
        if st.get("key_valid"):
            acct = st.get("account") or {}
            bal = acct.get("balance", acct.get("balance_usd"))
            rate = (acct.get("rate") or {}).get("description") if isinstance(
                acct.get("rate"), dict) else acct.get("rate")
            print(f"  {tick(True)}key works"
                  + (f", balance ${bal}" if bal is not None else "")
                  + (f", {rate}" if rate else ""))
            if bal is not None:
                print(f"      that is about {int(float(bal) / 0.0004):,} af2ig targets at "
                      f"the current per-target median")
        else:
            print(f"  {tick(False)}key rejected: {str(st.get('account_error'))[:200]}")
    else:
        print("\n" + KEY_HELP)
    print()


def _cli() -> int:
    import argparse
    B = _backends()

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="key, reachability, balance, queue (free)")
    ap.add_argument("--key-help", action="store_true", help="every way to set the key")
    ap.add_argument("--set-key", action="store_true",
                    help="read a key from stdin (never echoed) into the login keychain")
    ap.add_argument("--from-file", metavar="PATH",
                    help="with --set-key: pull the key out of the Slack codes txt")
    ap.add_argument("--models", action="store_true", help="catalogue + prices (free)")
    ap.add_argument("--estimate", metavar="MODEL", help="price a plan, start nothing")
    ap.add_argument("--score-af2ig", metavar="DESIGN_ID", nargs="?", const="",
                    help="ipTM + interface pAE; with --all, every co-fold in ONE job")
    ap.add_argument("--fold", metavar="DESIGN_ID", help="co-fold one design against HER2")
    ap.add_argument("--watch", metavar="JOB_ID",
                    help="re-attach to a job already running (any machine, same key)")
    ap.add_argument("--jobs", action="store_true", help="recent jobs on this account")
    ap.add_argument("--model", default="openfold3")
    ap.add_argument("--epitope-guidance", action="store_true")
    ap.add_argument("--all", action="store_true", help="every design with a co-fold")
    ap.add_argument("--yes", action="store_true", help="required before anything bills")
    ap.add_argument("--no-wait", action="store_true",
                    help="submit and return the job id; re-attach with --watch")
    ap.add_argument("--no-ipsae", action="store_true",
                    help="skip the local ipSAE computation from the PAE matrix")
    a = ap.parse_args()

    if a.key_help:
        print("\n" + KEY_HELP + "\n")
        return 0
    if a.set_key:
        if a.from_file:
            key = _key_from_file(pathlib.Path(os.path.expanduser(a.from_file)))
        else:
            if sys.stdin.isatty():
                print("Paste the JapanFold key, then press ctrl-d. It is not echoed and "
                      "not written into this repo:", file=sys.stderr)
            key = sys.stdin.read()
        print(f"  stored in {set_key(key)}. Nothing was written into the repo.")
        _print_check(check())
        return 0
    if a.check:
        _print_check(check())
        return 0
    if a.models:
        m = list_models()
        for bucket, unit in (("models", "per target"), ("design_models", "per job"),
                             ("embed_models", "per job")):
            if not m.get(bucket):
                continue
            print(f"\n== {bucket}  ({unit}; price, max/measured residues, tagline)")
            for x in m[bucket]:
                tc = x.get("typical_cost") or {}
                p = tc.get("usd_per_target_p50") if bucket == "models" else tc.get("usd_p50")
                print(f"  {x['id']:<16} {('$' + format(p, '.5f')) if p else '--':<10}"
                      f" {str(x.get('max_residues') or ''):>5}/"
                      f"{str(x.get('measured_wall') or '?'):<5} {x.get('tagline', '')}")
        print()
        return 0
    if a.jobs:
        for j in jobs(20):
            print(f"  {str(j.get('id')):<28} {str(j.get('status')):<10} "
                  f"{str(j.get('model')):<14} {j.get('name', '')}")
        return 0
    if a.watch:
        out = collect_af2ig(a.watch, ipsae=not a.no_ipsae)
        print(json.dumps(out, indent=2, default=str))
        return 0 if all(r.get("status") == "succeeded" for r in out) else 1

    want_af2ig = a.score_af2ig is not None
    ids = sorted(B._cofold_index()) if a.all else [
        i for i in [(a.score_af2ig or None), a.fold] if i]
    if not ids:
        ap.error("give --score-af2ig ID, --fold ID, --all, or --watch JOB_ID")

    which = "af2ig" if (want_af2ig or not a.fold) else a.model
    if a.estimate:
        print(json.dumps(estimate(a.estimate, ids), indent=2))
        return 0
    if not a.yes:
        est = estimate(which, ids)
        print(json.dumps(est, indent=2))
        print(f"\nThis would start {est['plan']} and bill about ${est['usd_p50_total']} "
              f"(p90 ${est['usd_p90_total']}). Re-run with --yes to spend.", file=sys.stderr)
        return 1

    if a.fold and not a.all:
        rows = [r for r in csv.DictReader((REPO / "designs" / "submission.csv").open())
                if r["design_id"] == a.fold]
        if not rows:
            print(f"  ! {a.fold} not in designs/submission.csv", file=sys.stderr)
            return 1
        r = rows[0]
        out = fold(r["sequence"], r.get("light_sequence") or B.TZ_VL, model=a.model,
                   name=a.fold, epitope_guidance=a.epitope_guidance, wait=not a.no_wait)
        print(json.dumps(out, indent=2, default=str))
        return 0 if out.get("status") in ("succeeded", "queued", "running") else 1

    out = score_af2ig(ids, wait=not a.no_wait, ipsae=not a.no_ipsae)
    out = out if isinstance(out, list) else [out]
    print(json.dumps(out, indent=2, default=str))
    ok = [r for r in out if r.get("status") == "succeeded"]
    if ok:
        print(f"\n  {len(ok)}/{len(out)} design(s) now carry a measured ipTM and interface "
              f"pAE. Feed them to the ranker:\n"
              f"    python3 pipeline/score/rank.py --refold "
              f"{METRICS_CSV.relative_to(REPO)} ...\n"
              f"  then reload the viewer: it joins on the heavy sequence and shows them as "
              f"measured.", file=sys.stderr)
    return 0 if len(ok) == len(out) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(_cli())
    except NoKey as e:
        print(f"\n{e}\n", file=sys.stderr)
        raise SystemExit(2)
    except OutOfCredit as e:
        print(f"\n{e}\n", file=sys.stderr)
        raise SystemExit(3)
    except KeyboardInterrupt:
        print("\n  stopped. Any job already submitted keeps running and is not lost: "
              "python3 viz/japanfold.py --jobs", file=sys.stderr)
        raise SystemExit(130)
