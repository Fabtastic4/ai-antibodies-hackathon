#!/usr/bin/env bash
# Submit the VH-VL interface ddG job to stab-ddg. Run this where NEBIUS_CREDS lives
# (the VM, or a laptop with credentials.private.json) -- it needs the platform.
#
# Axis 3 for the optimisation + Fab/scFv cell. This is a VH-VL INTERFACE ddG used as a
# thermostability proxy, never a folding ddG and never a Tm (docs/decision-log.md [11:15]).
#
#   bash scripts/stab_ddg_run.sh                 # schema check, then submit
#   bash scripts/stab_ddg_run.sh --schema-only   # just print the live schema
#
# stab-ddg is ~12 minutes to first call, so start it before anything short.

set -euo pipefail
cd "$(dirname "$0")/.."

FORGE="${FORGE:-Files from slack/extracted/participant-05/agent/nebius-scientific-ai/forge.py}"
CREDS="${NEBIUS_CREDS:-}"
MANIFEST="reports/stab_ddg_request.json"
OUTDIR="nebius-runs"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ ! -f "$FORGE" ]]; then
  echo "forge.py not found at: $FORGE" >&2
  echo "set FORGE=/path/to/forge.py" >&2
  exit 2
fi
if [[ ! -f "$MANIFEST" ]]; then
  echo "$MANIFEST missing -- run: python3 -I scripts/stab_ddg_prep.py" >&2
  exit 2
fi

# bash 3.2 (macOS default) errors on "${arr[@]}" when arr is empty under `set -u`,
# so expand with the +alternate form everywhere.
creds_arg=()
if [[ -n "$CREDS" ]]; then creds_arg=(--creds "$CREDS"); fi

echo "== live schema for stab-ddg =="
# The request shape below is built from the recorded schema (operation predict-binding-ddg,
# two disjoint partner sets, named point mutations). If the live schema has moved, STOP and
# adjust rather than letting the submit invent fields -- a mutation named at the wrong
# residue is not an error, it is a different experiment.
python3 -I "$FORGE" ${creds_arg[@]+"${creds_arg[@]}"} schema stab-ddg | tee "$OUTDIR/stab-ddg-schema-$STAMP.json"

if [[ "${1:-}" == "--schema-only" ]]; then
  echo
  echo "Schema written to $OUTDIR/stab-ddg-schema-$STAMP.json."
  echo "Compare it against $MANIFEST before submitting:"
  echo "  .operation        expected: predict-binding-ddg"
  echo "  .partners         expected: two disjoint chain sets, here [[\"B\"],[\"A\"]]"
  echo "  .mutations        expected: chain / position / wild_type / mutant per entry"
  exit 0
fi

mkdir -p "$OUTDIR/inputs" "results"

n=$(python3 -I -c "import json;print(json.load(open('$MANIFEST'))['n_designs'])")
echo
echo "== submitting $n designs =="
echo "structure : $(python3 -I -c "import json;print(json.load(open('$MANIFEST'))['structure'])")"
echo "partners  : chain B (VH) vs chain A (VL)"
echo "convention: positive ddG = weaker binding = less stable Fv. LOWER IS BETTER."
echo

REQ="$OUTDIR/inputs/stab-ddg-$STAMP.json"
python3 -I scripts/stab_ddg_payload.py --manifest "$MANIFEST" --out "$REQ"
echo "request body: $REQ"

python3 -I "$FORGE" ${creds_arg[@]+"${creds_arg[@]}"} submit stab-ddg --request "$REQ" \
  | tee "$OUTDIR/stab-ddg-submit-$STAMP.txt"

echo
echo "Recorded in $OUTDIR/. Poll with:"
echo "  python3 -I \"$FORGE\" status <op-id>"
echo "  python3 -I \"$FORGE\" wait   <op-id>"
echo "  python3 -I \"$FORGE\" fetch  <op-id> -o results/stab-ddg-$STAMP/"
echo
echo "Then: confirm the returned sign on a known case before ranking on it, and write the"
echo "values into reports/b1_ddg.csv / reports/b2_ddg.csv with a design_id column so"
echo "pipeline/score/rank.py joins them (it pools those two paths by default)."
