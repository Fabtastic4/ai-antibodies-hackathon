#!/usr/bin/env python3
"""Re-poll every recorded hosted run and write its TRUE state back into nebius-runs/.

Why this exists. Each record in `nebius-runs/*.json` is written at submit time with
`"state": "queued"` and never updated, so the folder claims 24 queued jobs forever -- while
18 of them in fact succeeded (their mmCIFs are in results/cofold/) and two FAILED. A
provenance folder that says "queued" for a job that failed 90 minutes ago is worse than no
record: it is why nobody noticed that two designs in designs/submission.csv have no
structure behind them.

So this asks the platform what actually happened and records the answer, keeping what the
record claimed at submit time beside it:

    state              the platform's answer now
    state_at_submit    what the record said before (kept, never overwritten)
    state_checked_at   when we asked
    error              the platform's message, on a failure

Read-only against the platform: it polls operations and starts nothing, so it costs
nothing and cannot resubmit work by accident.

    python3 scripts/reconcile_runs.py                 # report, write nothing
    python3 scripts/reconcile_runs.py --write         # update the records
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
ROOT = REPO.parent
RUNS = ROOT / "nebius-runs"
COFOLD = ROOT / "results" / "cofold"
FORGE_DEFAULT = pathlib.Path(
    os.path.expanduser("~/.claude/skills/nebius-scientific-ai/forge.py"))


def _forge(path: pathlib.Path):
    """Import forge.py as a module so its REST client is reused rather than reimplemented."""
    if not path.is_file():
        sys.exit(f"no forge.py at {path}. Pass --forge /path/to/forge.py")
    sys.path.insert(0, str(path.parent))
    import forge                                                   # noqa: PLC0415
    return forge


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write the true state back")
    ap.add_argument("--creds", default=str(ROOT / "credentials.private.json"))
    ap.add_argument("--forge", default=str(FORGE_DEFAULT))
    a = ap.parse_args()

    if not RUNS.is_dir():
        sys.exit(f"no {RUNS}")
    forge = _forge(pathlib.Path(a.forge))
    api = forge.Api(forge.Creds(a.creds))

    records = sorted(RUNS.glob("*.json"))
    rows, changed = [], 0
    for p in records:
        try:
            rec = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError) as e:
            rows.append((p.name, "?", "unreadable", str(e)[:60]))
            continue
        op = rec.get("operation_id")
        if not op:
            continue
        status, doc = api.rest_json("GET", "/operations/" + op)
        if status >= 300:
            rows.append((p.name, rec.get("state"), f"http {status}", ""))
            continue
        state, ready = forge.op_state(doc)
        err = ((doc.get("error") or {}).get("message") or "") if isinstance(
            doc.get("error"), dict) else ""

        # Does a structure actually exist for this label? That is the only claim the
        # submission depends on, so it is checked rather than inferred from the state.
        label = rec.get("label", "")
        design = label[3:] if label.startswith("cf-") else label
        has_cif = (COFOLD / design / "model.cif").is_file()

        rows.append((p.name, rec.get("state"), state, err[:70] +
                     ("  [structure on disk]" if has_cif else "")))
        if state != rec.get("state"):
            changed += 1
            if a.write:
                rec.setdefault("state_at_submit", rec.get("state"))
                rec["state"] = state
                rec["result_available"] = ready
                rec["state_checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                        time.gmtime())
                rec["structure_on_disk"] = has_cif
                if err:
                    rec["error"] = err
                p.write_text(json.dumps(rec, indent=1) + "\n")

    w = max((len(r[0]) for r in rows), default=10)
    print(f"\n  {'record':<{w}}  {'recorded':<10} {'actual':<12} note")
    for name, was, now, note in rows:
        flag = " " if was == now else "*"
        print(f" {flag}{name:<{w}}  {str(was):<10} {now:<12} {note}")

    states: dict[str, int] = {}
    for _, _, now, _ in rows:
        states[now] = states.get(now, 0) + 1
    print(f"\n  {len(rows)} records: "
          + ", ".join(f"{v} {k}" for k, v in sorted(states.items())))
    print(f"  {changed} record(s) disagree with the platform"
          + (" -- written" if a.write else " -- run with --write to correct them"))
    failed = [r[0] for r in rows if r[2] == "failed"]
    if failed:
        print(f"\n  FAILED on the hosted lane, so these designs have no co-fold:")
        for f in failed:
            print(f"    {f}")
        print("  The inputs are not implicated (the platform says so itself). Re-fold them\n"
              "  on another lane instead of resubmitting into the same failure:\n"
              "    python3 viz/japanfold.py --fold <design_id> --model openfold3 --yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
