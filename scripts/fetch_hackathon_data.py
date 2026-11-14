#!/usr/bin/env python3
"""Pull the subsets of s3://apheris-oslo-hackathon we actually need. Issue #5.

RUNS ON THE TEAM VM. The read-only bucket credentials are on the VM and nowhere
else, so this script refuses early and says so rather than failing halfway
through a sync on a laptop.

Why a script instead of four `aws s3 sync` lines: the sync is the easy half. The
half that matters is knowing whether what landed is COMPLETE, because two
downstream things break silently on a partial copy:

  * The optimisation novelty filter (#12) compares our CDRH3 against every
    sequence in these tables. A short table does not error - it just stops
    finding neighbours, and a design that is actually a known binder passes
    the filter. That is a rejected submission, discovered at judging.
  * The confidence-calibration set (the 454 VHH-antigen true negatives, 21 of
    which score AF3 ipTM >= 0.7 while not binding) is only a calibration set if
    all 454 are there. Calibrating on a subset silently moves the threshold.

So every subset carries the counts the organisers stated, this script reports
found-vs-expected per subset, and a mismatch is loud. A count it cannot verify
is reported as unverified, never as a pass.

The directory layout below is Leonardo's (Apheris), posted in Slack at 10:17 and
quoted in issue #5. The directory names are therefore known. The FILE names
inside them are NOT in any source we have, so this script discovers whatever is
there instead of assuming names - if a file is missing, it says the count is
unverified rather than inventing a path.

Layout, verbatim from the issue:

  s3://apheris-oslo-hackathon/
  |-- data/                                 ~5 GB, README.md explains every file
  |   |-- her2-trastuzumab/                 FACS binding classes, SPR affinities
  |   |-- zenodo-18390239-ab-ag-complexes/  1.8M predicted nanobody-antigen scores
  |   |-- sigma2-ab-ag-champloo/            per-sample ipTM, pLDDT, PAE
  |   |   `-- spr-supplementary/            measured SPR for some of those pairs
  |   `-- zenodo-10831512-trastuzumab-ngs/  ready-made train/val/test splits
  `-- rfd4-proteina/docs/                   Foundry + RFD4-Proteina instructions

Usage, on the VM:
  python3 scripts/fetch_hackathon_data.py --dryrun          # show what would move
  python3 scripts/fetch_hackathon_data.py                   # all of it, in priority order
  python3 scripts/fetch_hackathon_data.py --only rfd4-docs  # just the tutorial
  python3 scripts/fetch_hackathon_data.py --verify-only      # re-check an existing copy

The data itself is NOT committed - 5 GB of it, and .gitignore covers the
destination. The manifest this writes IS committable, and is the provenance
record of which copy of which table every downstream number came from.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "pipeline"))
import common  # noqa: E402

BUCKET = "s3://apheris-oslo-hackathon"
DEFAULT_DEST = "hackathon-data"

# Counts the organisers stated, as stated. `exact` is checked hard; `approx` is
# reported but not failed on; None means no count was given and anything found
# is reported as unverified.
#
# ONE SOURCE CONFLICT, recorded rather than resolved: issue #5's priority list
# says "~700 optimisation designs, 190 with SPR affinities", while Leonardo's
# layout in the same issue says her2-trastuzumab holds "SPR affinities (768
# variants)". 190 and 768 are both quoted for SPR. They may be two different
# tables - 190 optimisation designs with SPR, 768 CDRH3 variants with SPR - or
# one of the two is wrong. This script reports what it finds against both.
SUBSETS = [
    {
        "key": "rfd4-docs",
        "s3": "rfd4-proteina/docs/",
        "local": "rfd4-docs",
        "priority": 1,
        "why": "the step-by-step Foundry guide, the ready-made HER2 script and Tutorial.html. "
               "Start with 18-vm.md ('Run on your hackathon VM'): the VM has no Foundry Hub, "
               "but every Foundry model is already there as a Docker image. Blocks the whole "
               "de novo track (probe-findings.md §2: the HER2/antibody RFD4 checkpoints are "
               "VM-only), and blocks refold-prepare/refold-score in pipeline/04_score.py.",
        "expect": {"files_at_least": 1,
                   "must_contain_names": ["Tutorial.html", "18-vm.md"]},
    },
    {
        "key": "her2-trastuzumab",
        "s3": "data/her2-trastuzumab/",
        "local": "data/her2-trastuzumab",
        "priority": 2,
        "why": "the labelled dataset on exactly our task: trastuzumab CDRH3 FACS binding "
               "classes, up to 10 mutated positions, three affinity classes, plus SPR "
               "affinities. REQUIRED, not optional: the optimisation novelty filter (#12) "
               "compares our CDRH3 against every sequence in here, and it is large enough to "
               "train a ranker on measured binders.",
        "expect": {"rows_exact": {"facs_variants": 524346, "spr_rows": 768},
                   "bytes_at_least": 5_000_000,
                   "must_contain_names": ["trastuzumab_her2_spr_all_768.csv"],
                   "derived": {"spr_with_measurable_kd":
                               "190 of the 768 SPR rows carry a real KD, spanning 0.023-13863 nM "
                               "- 5.8 orders of magnitude, so fit on log KD or the numbers will "
                               "flatter you. The other 578 are MEASURED NON-BINDERS on our exact "
                               "target, which is signal, not waste. Trastuzumab itself appears 8x "
                               "at 0.03-0.18 nM: that is the baseline every design is scored "
                               "against. Observed on the VM, docs/vm-data.md."},
                   "note": "190 vs 768 is NOT a source conflict: 768 is the SPR table's row "
                           "count, 190 is how many have a measurable KD. Both numbers quoted in "
                           "issue #5 were right about different things. Separately, 524346 FACS "
                           "+ 717 optimisation designs = 525063 (the corpus size in #12), but "
                           "that is now descriptive only - abguard ships its own reference DB "
                           "(abguard_cdrh3.parquet), so do NOT assemble a second novelty corpus."},
    },
    {
        "key": "trastuzumab-ngs",
        "s3": "data/zenodo-10831512-trastuzumab-ngs/",
        "local": "data/zenodo-10831512-trastuzumab-ngs",
        "priority": 3,
        "why": "ready-made train/val/test splits of the FACS data. Using the organisers' own "
               "splits removes the main way to fool ourselves when training a ranker - "
               "a split we choose ourselves can leak near-duplicate CDRH3s across folds.",
        "expect": {"files_at_least": 1,
                   "bytes_at_least": 2_000_000_000,
                   "note": "~2.4 GB and ships STILL ZIPPED (observed on the VM). Extract before "
                           "any row count means anything. The splits are clonotype-split, which "
                           "is the point: a split we choose ourselves leaks near-duplicate "
                           "CDRH3s across folds and flatters the model."},
    },
    {
        "key": "champloo-confidence",
        "s3": "data/sigma2-ab-ag-champloo/",
        "local": "data/sigma2-ab-ag-champloo",
        "priority": 4,
        "why": "per-replica AF3/Chai-1 confidence archives plus a 29-pair SPR supplement in "
               "spr-supplementary/. NARROWER THAN THE BUCKET README CLAIMS: the README says this "
               "folder holds ipTM, pLDDT and PAE, but that is true only for the AF3 REAL pairs - "
               "pLDDT exists locally only in af3_real_per_replica_confidence_metrics.tar.zst, as "
               "123 systems x 50 samples = 6150 confidences.json with per-ATOM atom_plddts. The "
               "AF3 shuffled pairs (152 GB) and the Boltz-2 per-replica archive (1.7 TB) are in "
               "the table of contents but were NOT downloaded, so pLDDT cannot be compared "
               "between real and shuffled pairs - which is the dataset's central question. Use "
               "ipTM (both classes) or Chai-1 ptm/iptm for that instead. Whether a PAE matrix is "
               "in those same files is UNVERIFIED - open one and look before any ipSAE plan "
               "depends on it. See docs/vm-data.md §2.",
        "expect": {"files_at_least": 1,
                   "must_contain_dirs": ["spr-supplementary"],
                   "bytes_at_least": 1_500_000_000,
                   "note": "~1.7 GB of per-replica AF3/Chai-1 confidence JSONs, 50 samples per "
                           "pair, plus a 29-pair SPR supplement. Row counts do not apply, so the "
                           "size floor is what catches a truncated sync here."},
    },
    {
        "key": "ab-ag-complexes",
        "s3": "data/zenodo-18390239-ab-ag-complexes/",
        "local": "data/zenodo-18390239-ab-ag-complexes",
        "priority": 5,
        "why": "scores for 1.8M predicted nanobody-antigen complexes, and the source of the "
               "VHH-antigen true negatives: 454 pairs with no measurable binding, 21 of which "
               "still score AF3 ipTM >= 0.7. Those 21 are the reason to calibrate a confidence "
               "filter before trusting it to rank. 106 cognate + 11342 shuffled pairs. Note the "
               "Chai-1 archive here (735172 npz over 14722 systems) carries ptm/iptm/per-chain "
               "variants and clash flags but NO pLDDT, so this is the subset that supports a "
               "real-vs-shuffled confidence comparison (see docs/vm-data.md §2). LARGEST subset "
               "- fetch it last.",
        "expect": {"rows_approx": {"predicted_complexes": 1800000},
                   "rows_exact": {"true_negative_pairs": 454},
                   "bytes_at_least": 500_000_000,
                   "derived": {"true_negatives_iptm_ge_0.7":
                               "21 of the 454 pairs score AF3 ipTM >= 0.7 while having no "
                               "measurable binding. That is a FILTER over the true-negative "
                               "table, not a file of its own, so this script does not look for "
                               "a 21-row file. Compute it after the sync and assert 21 - it is "
                               "also how you confirm WHICH ipTM column is the AF3 one, and "
                               "those 21 are the whole reason to calibrate a confidence filter "
                               "before ranking on it."},
                   "note": "if the 454-row table cannot be located, report unverified rather "
                           "than assuming a file is it"},
    },
]

ROW_READABLE = (".csv", ".tsv", ".txt")
ROW_NEEDS_READER = (".parquet", ".feather", ".h5", ".hdf5", ".npy", ".npz", ".pkl", ".arrow")
# Archives: zenodo-10831512 ships still zipped (observed on the VM, docs/vm-data.md), so a
# row count is meaningless until it is extracted. Say that, rather than "not a row format".
ROW_ARCHIVE = (".zip", ".gz", ".tgz", ".tar", ".bz2", ".xz", ".7z")


# --------------------------------------------------------------------------
# preflight
# --------------------------------------------------------------------------

def preflight(bucket: str) -> dict:
    """Confirm aws is installed and the bucket is actually readable from here.

    Both failures are the same mistake - running this somewhere that is not the
    VM - so they get the same explicit message instead of a stack trace.
    """
    if not shutil.which("aws"):
        return {"ok": False, "reason": "no `aws` on PATH",
                "fix": "This script runs ON THE TEAM VM, where the read-only bucket "
                       "credentials already are. See docs/SETUP.md and docs/tools-apheris.md "
                       "for getting onto the VM. Nothing here works from a laptop without "
                       "those credentials, and they must not be copied off the VM "
                       "(docs/workplan.md: secrets never enter the repo)."}
    try:
        r = subprocess.run(["aws", "s3", "ls", bucket + "/"],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "reason": "could not run `aws s3 ls {0}`: {1}".format(bucket, exc),
                "fix": "check network and credentials on the VM"}
    if r.returncode != 0:
        return {"ok": False,
                "reason": "`aws s3 ls {0}` exited {1}: {2}".format(
                    bucket, r.returncode, (r.stderr or "").strip()[:300]),
                "fix": "the bucket is read-only and credentialed on the VM; confirm you are on "
                       "the VM and the credentials are in place"}
    return {"ok": True, "listing_head": [ln for ln in (r.stdout or "").splitlines()[:10]]}


# --------------------------------------------------------------------------
# sync
# --------------------------------------------------------------------------

def sync_one(sub: dict, dest_root: str, *, bucket: str, dryrun: bool, quiet: bool) -> dict:
    """`aws s3 sync` one subset. Idempotent: sync only moves what changed, so
    re-running after an interruption resumes rather than restarting."""
    src = "{0}/{1}".format(bucket.rstrip("/"), sub["s3"])
    dst = os.path.join(dest_root, sub["local"])
    cmd = ["aws", "s3", "sync", src, dst]
    if dryrun:
        cmd.append("--dryrun")
    if not dryrun:
        os.makedirs(dst, exist_ok=True)
    common.say(quiet, "[{0}] {1}".format(sub["key"], " ".join(cmd)))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        return {"ok": False, "error": str(exc), "cmd": cmd, "src": src, "dest": dst}
    tail = [ln for ln in (r.stdout or "").splitlines() if ln.strip()][-5:]
    if r.returncode != 0:
        return {"ok": False, "returncode": r.returncode, "cmd": cmd, "src": src, "dest": dst,
                "stderr": (r.stderr or "").strip()[:600], "stdout_tail": tail}
    return {"ok": True, "cmd": cmd, "src": src, "dest": dst, "stdout_tail": tail,
            "dryrun": dryrun}


# --------------------------------------------------------------------------
# inventory and verification
# --------------------------------------------------------------------------

MAX_INLINE_COUNT_BYTES = 2_000_000_000


def count_rows(path: str) -> dict:
    """Row count for a file we can read without a dependency.

    Returns one of three shapes, and the distinction matters:
      {"rows": N}                 counted
      {"rows": None, "unverified": r}   a table we COULD NOT count (needs
                                  pyarrow, is an archive, is oversized,
                                  unreadable). verify() treats these as
                                  "a real count may be hiding here".
      {"rows": None, "not_tabular": r}  not a table at all (a README, an
                                  image). These must NEVER mask a count
                                  mismatch, which is why they are a
                                  separate key rather than `unverified`.

    Counting goes through the csv module, not a newline count: a quoted
    embedded newline, a CRLF file or a blank trailing line each shift a raw
    line count by one, and a one-off artefact exactly cancels one missing data
    row - turning an incomplete table into an exact `rows_exact` match.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in ROW_ARCHIVE:
        return {"rows": None, "unverified": "{0} archive - extract it before any count from it "
                                            "means anything".format(ext)}
    if ext in ROW_NEEDS_READER:
        return {"rows": None, "unverified": "{0} needs a reader (pandas/pyarrow); "
                                            "count it separately".format(ext)}
    if ext not in ROW_READABLE:
        return {"rows": None, "not_tabular": "{0} is not a row format".format(ext or "no suffix")}
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        return {"rows": None, "unverified": "cannot stat: {0}".format(exc)}
    if size == 0:
        # An empty file is present but carries nothing. Reporting rows=0 would
        # let it satisfy "files_at_least" while disproving nothing.
        return {"rows": None, "unverified": "empty file (0 bytes)"}
    if size > MAX_INLINE_COUNT_BYTES:
        return {"rows": None,
                "unverified": "{0} bytes is over the {1}-byte inline-count guard; count it "
                              "with pyarrow/pandas".format(size, MAX_INLINE_COUNT_BYTES)}

    import csv as _csv
    delim = "\t" if ext == ".tsv" else ","
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as fh:
            reader = _csv.reader(fh, delimiter=delim)
            records = 0
            first = None
            widths = set()
            for row in reader:
                if not row or (len(row) == 1 and not row[0].strip()):
                    continue                     # blank or trailing empty line
                if first is None:
                    first = row
                widths.add(len(row))
                records += 1
    except (OSError, UnicodeError, _csv.Error) as exc:
        return {"rows": None, "unverified": "unreadable as csv: {0}".format(exc)}

    if first is None:
        return {"rows": None, "unverified": "no non-blank records"}

    # Header: a first record in which NO field parses as a number. Do not test
    # for digits in the column name - these tables have columns called `cdrh3`
    # and `iptm`, and a digit in the name would put every count off by one on
    # exactly the tables that matter most.
    def numeric(x: str) -> bool:
        try:
            float(x.strip().strip(chr(34)).strip("'"))
            return True
        except ValueError:
            return False

    fields = [f for f in first if f.strip()]
    header = bool(fields) and not any(numeric(f) for f in fields)
    return {"rows": max(0, records - (1 if header else 0)),
            "records_incl_header": records,
            "header_assumed": header,
            "ragged_widths": sorted(widths) if len(widths) > 1 else None}


def inventory(root: str) -> dict:
    """Every file under `root`, with size, plus row counts where readable."""
    files, total = [], 0
    if not os.path.isdir(root):
        return {"exists": False, "files": [], "n_files": 0, "bytes": 0}
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in sorted(filenames):
            fp = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(fp)
            except OSError:
                continue
            total += size
            rec = {"path": os.path.relpath(fp, root), "bytes": size}
            # Always ask: count_rows() itself reports 0-byte and oversized files
            # with a reason. Skipping them here left them with no row key and no
            # explanation, so an empty file passed as merely "present".
            rec.update(count_rows(fp))
            files.append(rec)
    return {"exists": True, "files": files, "n_files": len(files), "bytes": total}


def verify(sub: dict, inv: dict) -> dict:
    """Found-vs-expected for one subset. Never reports a pass it cannot show."""
    exp = sub.get("expect") or {}
    checks, status = [], "ok"

    def add(name, ok, detail):
        nonlocal status
        checks.append({"check": name, "result": ok, "detail": detail})
        if ok == "FAIL":
            status = "FAIL"
        elif ok == "UNVERIFIED" and status == "ok":
            status = "unverified"

    if not inv.get("exists") or inv["n_files"] == 0:
        add("present", "FAIL", "nothing at the destination")
        return {"status": "FAIL", "checks": checks}

    if "bytes_at_least" in exp:
        got = inv["bytes"]
        want = exp["bytes_at_least"]
        # Most of this bucket is parquet, zip and JSON, where a row count says
        # nothing. A size floor is the only check that catches a truncated sync
        # for those subsets, so it is a FAIL, not a warning.
        add("bytes_at_least", "ok" if got >= want else "FAIL",
            "{0:.1f} MB on disk, expected at least {1:.1f} MB".format(got / 1e6, want / 1e6))

    if "files_at_least" in exp:
        n = inv["n_files"]
        add("files_at_least", "ok" if n >= exp["files_at_least"] else "FAIL",
            "found {0}, expected at least {1}".format(n, exp["files_at_least"]))

    names = [os.path.basename(f["path"]) for f in inv["files"]]
    allp = [f["path"] for f in inv["files"]]
    for want in exp.get("must_contain_names", []):
        hit = any(want.lower() == n.lower() for n in names)
        add("has:" + want, "ok" if hit else "FAIL",
            "found" if hit else "not in the {0} files synced".format(len(names)))
    for want in exp.get("must_contain_dirs", []):
        hit = any(want.strip("/") in p.split(os.sep) for p in allp)
        add("has_dir:" + want, "ok" if hit else "FAIL", "found" if hit else "absent")

    # Row-count expectations. The file holding a given table is not named in any
    # source, so a count matches if ANY synced file has exactly that many rows.
    counted = [f for f in inv["files"] if f.get("rows") is not None]
    # ONLY files that might be hiding a real count. A README is `not_tabular`
    # and must never send a disproved count down the UNVERIFIED branch, which
    # exits 0, instead of FAIL, which exits 1.
    unreadable = [f for f in inv["files"] if f.get("unverified") and f.get("rows") is None]
    for label, want in (exp.get("rows_exact") or {}).items():
        hit = [f["path"] for f in counted if f["rows"] == want]
        if hit:
            add("rows:" + label, "ok", "{0} rows in {1}".format(want, ", ".join(hit[:3])))
        elif unreadable:
            add("rows:" + label, "UNVERIFIED",
                "expected {0}; no readable file has that many, and {1} file(s) need a reader "
                "({2}). Count those before trusting this subset.".format(
                    want, len(unreadable), ", ".join(f["path"] for f in unreadable[:3])))
        else:
            near = sorted(((abs(f["rows"] - want), f) for f in counted), key=lambda t: t[0])[:2]
            add("rows:" + label, "FAIL",
                "expected {0}; nearest readable counts: {1}".format(
                    want, "; ".join("{0}={1}".format(f["path"], f["rows"]) for _, f in near)
                          or "none"))
    for label, want in (exp.get("rows_approx") or {}).items():
        hit = [f["path"] for f in counted if abs(f["rows"] - want) <= max(1, want // 100)]
        add("rows~:" + label, "ok" if hit else "UNVERIFIED",
            "within 1% in {0}".format(", ".join(hit[:3])) if hit
            else "expected ~{0}; not matched in a readable file".format(want))
    for label, options in (exp.get("rows_conflicting") or {}).items():
        found = {f["path"]: f["rows"] for f in counted if f["rows"] in options}
        add("rows?:" + label, "ok" if found else "UNVERIFIED",
            "sources disagree ({0}); found {1}".format(
                " vs ".join(str(o) for o in options),
                found or "neither in a readable file - resolve against the bucket README"))
    for label, how in (exp.get("derived") or {}).items():
        checks.append({"check": "derived:" + label, "result": "info", "detail": how})
    if exp.get("note"):
        checks.append({"check": "note", "result": "info", "detail": exp["note"]})
    return {"status": status, "checks": checks}


# --------------------------------------------------------------------------

def main(argv=None) -> int:
    p = common.base_parser(
        "Fetch the hackathon bucket subsets we need, in priority order, and verify the "
        "counts the organisers stated. Runs on the team VM.",
        epilog="Subsets, in priority order:\n" + "\n".join(
            "  {0}. {1:<20} {2}".format(s["priority"], s["key"], s["s3"]) for s in SUBSETS))
    p.add_argument("--dest", default=DEFAULT_DEST,
                   help="destination directory (default %(default)s; gitignored)")
    p.add_argument("--bucket", default=BUCKET, help="source bucket (default %(default)s)")
    p.add_argument("--only", action="append", default=[], metavar="KEY",
                   help="fetch just this subset, repeatable. Keys: " +
                        ", ".join(s["key"] for s in SUBSETS))
    p.add_argument("--dryrun", action="store_true",
                   help="pass --dryrun to aws s3 sync; moves nothing")
    p.add_argument("--verify-only", action="store_true",
                   help="skip syncing, just inventory and verify what is already there")
    p.add_argument("--manifest", default=None,
                   help="where to write the provenance manifest "
                        "(default <dest>/fetch_manifest.json)")
    p.add_argument("-q", "--quiet", action="store_true")
    args = p.parse_args(argv)

    keys = [s["key"] for s in SUBSETS]
    unknown = [k for k in args.only if k not in keys]
    if unknown:
        raise SystemExit("unknown --only {0}; known: {1}".format(
            ", ".join(unknown), ", ".join(keys)))
    chosen = [s for s in SUBSETS if not args.only or s["key"] in args.only]
    chosen.sort(key=lambda s: s["priority"])

    dest = os.path.abspath(args.dest)
    pre = {"skipped": True} if args.verify_only else preflight(args.bucket)
    if not args.verify_only and not pre.get("ok"):
        print("cannot fetch: {0}\n  {1}".format(pre["reason"], pre["fix"]), file=sys.stderr)
        print("\n(--verify-only still works on an existing copy.)", file=sys.stderr)
        return 3

    results = []
    for sub in chosen:
        entry = {"key": sub["key"], "s3": sub["s3"], "priority": sub["priority"],
                 "why": sub["why"]}
        if not args.verify_only:
            entry["sync"] = sync_one(sub, dest, bucket=args.bucket,
                                     dryrun=args.dryrun, quiet=args.quiet)
            if not entry["sync"]["ok"]:
                # stderr, not common.say: -q must not be able to hide a failed sync.
                print("[{0}] SYNC FAILED: {1}".format(sub["key"],
                      entry["sync"].get("stderr") or entry["sync"].get("error") or
                      "exit {0}".format(entry["sync"].get("returncode"))), file=sys.stderr)
        inv = inventory(os.path.join(dest, sub["local"]))
        entry["inventory"] = {"n_files": inv["n_files"], "bytes": inv["bytes"],
                              "files": inv["files"][:200]}
        entry["verify"] = ({"status": "skipped", "checks": [],
                            "reason": "--dryrun moves nothing, so there is nothing to verify"}
                           if args.dryrun and not args.verify_only else verify(sub, inv))
        # A sync that aborted part-way must not be able to report "ok" because
        # the files that DID arrive happen to satisfy the expectations. Its
        # failure was previously only printed, never folded into the status or
        # the exit code - and -q swallowed the print entirely.
        syn = entry.get("sync")
        if syn and not syn.get("ok"):
            entry["verify"]["status"] = "FAIL"
            entry["verify"].setdefault("checks", []).insert(0, {
                "check": "sync", "result": "FAIL",
                "detail": "aws s3 sync failed: {0}".format(
                    (syn.get("stderr") or syn.get("error") or
                     "exit {0}".format(syn.get("returncode"))))[:600]})
        results.append(entry)

    manifest_path = args.manifest or os.path.join(dest, "fetch_manifest.json")
    manifest = {
        "schema": "fab4.hackathon-data-fetch/v1",
        "bucket": args.bucket,
        "dest": dest,
        "issue": "#5",
        "dryrun": bool(args.dryrun),
        "verify_only": bool(args.verify_only),
        "provenance": common.provenance("fetch_hackathon_data", model=None,
                                        settings={"bucket": args.bucket, "dest": dest,
                                                  "only": args.only or "all",
                                                  "dryrun": bool(args.dryrun)}),
        "layout_source": "Leonardo (Apheris), Slack 10:17, quoted in GitHub issue #5",
        "subsets": results,
    }
    common.write_json(manifest_path, manifest)

    rows = []
    for e in results:
        rows.append([e["key"], e["inventory"]["n_files"],
                     "{0:.1f}".format(e["inventory"]["bytes"] / 1e6),
                     e["verify"]["status"],
                     sum(1 for c in e["verify"]["checks"] if c["result"] == "FAIL")])
    common.say(args.quiet, "")
    common.say(args.quiet, common.table(rows, ["subset", "files", "MB", "status", "failed"]))

    bad = [e for e in results if e["verify"]["status"] == "FAIL"]
    unv = [e for e in results if e["verify"]["status"] == "unverified"]
    common.say(args.quiet, "")
    for e in bad + unv:
        common.say(args.quiet, "{0} [{1}]".format(e["key"], e["verify"]["status"]))
        for c in e["verify"]["checks"]:
            if c["result"] in ("FAIL", "UNVERIFIED"):
                common.say(args.quiet, "   {0}: {1} - {2}".format(
                    c["result"], c["check"], c["detail"]))
    common.say(args.quiet, "")
    common.say(args.quiet, "manifest: {0}".format(manifest_path))
    if bad:
        common.say(args.quiet,
                   "A FAILED count means the copy is INCOMPLETE. Do not load it into the "
                   "novelty filter (#12) or the calibration set until it is resolved - a short "
                   "table does not error, it just stops finding neighbours.")
        return 1
    if unv:
        common.say(args.quiet,
                   "Unverified counts are not passes. Count the files that need a reader "
                   "before any number from them is quoted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(common.cli(main))
