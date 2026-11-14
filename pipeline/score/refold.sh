#!/usr/bin/env bash
# The scoring stage: refold every abguard-eligible design and score the refold.
# Run on the team VM, from $HOME. This is the stage the whole submission was blocked on.
#
#   bash pipeline/score/refold.sh --run mark/runs/b1-novel-s1 \
#        --eligible <repo>/reports/b1-novel-s1-eligible.csv
#   bash pipeline/score/refold.sh --run ... --eligible ... --top-n 20     # a cheap subset first
#
#   design run  ->  refold-prepare  ->  keep only eligible  ->  predict  ->  refold-score
#
# Measured cost: ~15 s/design on the idle H100 (2 designs in 54 s wall, OpenFold3-OpenBind).
# So ~190 designs is roughly 50 minutes. Measure, don't assume - that is how this stage got
# mistaken for a three-hour wall nobody had timed.
#
# Two things this script exists to get right:
#   1. `refold-prepare --top-n` ranks by RFD4's own design metrics and knows nothing about
#      abguard, so it will happily queue designs the gate rejects. We prune to the eligible set
#      before spending GPU time. The task PDF: filter before you rank.
#   2. `predict` omits PAE and per-atom pLDDT unless you pass --write-detailed-scores, and
#      without them `refold-score` leaves `min_ipae` and `binder_plddt` EMPTY - two of the three
#      metrics we rank on. They grow with the square of the token count, hence the default.
set -euo pipefail

REG=quay.io/apheris/oslo-hackathon
OF3="$REG:apheris-openfold3-v1.3.0-of3ob"          # template-taking; also the Apheris prize condition
RFD="$REG:apheris-rfd4-proteina-v0.3.0-her2-novel-2026-11-09"

RUN="" ELIGIBLE="" OUT="" TOPN="" MODEL_LABEL="openfold3-openbind" PREFIX=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --run)      RUN="$2"; shift 2 ;;
    --eligible) ELIGIBLE="$2"; shift 2 ;;
    --out)      OUT="$2"; shift 2 ;;
    --top-n)    TOPN="$2"; shift 2 ;;
    --prefix)   PREFIX="$2"; shift 2 ;;
    -h|--help)  sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

die() { echo "FAIL: $*" >&2; exit 1; }
[[ -n "$RUN" ]] || die "--run <design run dir> is required"
cd "$HOME"
[[ -d "$RUN" ]] || die "no such design run: $RUN"
[[ -f "$RUN/result.json" ]] || die "$RUN has no result.json - refold-score reads the DESIGN run, so this must be a completed design output"

BASE="$(basename "$RUN")"
OUT="${OUT:-mark/scoring/$BASE}"
PREFIX="${PREFIX:-$BASE-}"
NDESIGNS=$(find "$RUN" -name '*_generated.cif' | wc -l | tr -d ' ')
(( NDESIGNS > 0 )) || die "$RUN holds no *_generated.cif"

docker_run=(docker run --rm --gpus all --shm-size 16g --user "$(id -u):$(id -g)"
            -e HOME=/tmp -v /etc/passwd:/etc/passwd:ro -v "$PWD:/work" -w /work)

echo "== scoring $BASE  ($NDESIGNS designs generated)"
free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
echo "   GPU ${free} MiB free, $(nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l | tr -d ' ') other process(es)"

mkdir -p "$(dirname "$OUT")"
rm -rf "$OUT"; mkdir -p "$OUT"

echo
echo "== 1/4  refold-prepare"
prep_args=(module-run refold-prepare --input "$RUN" --output "$OUT/prepare")
[[ -n "$TOPN" ]] && prep_args+=(--top-n "$TOPN") || prep_args+=(--top-n "$NDESIGNS")
"${docker_run[@]}" "$RFD" "${prep_args[@]}" 2>&1 | tail -3
[[ -f "$OUT/prepare/holo/queries.json" ]] || die "refold-prepare wrote no holo/queries.json"

echo
echo "== 2/4  keep only abguard-eligible designs"
if [[ -n "$ELIGIBLE" && -f "$ELIGIBLE" ]]; then
  python3 "$(dirname "${BASH_SOURCE[0]}")/filter_queries.py" \
    --queries "$OUT/prepare/holo/queries.json" --eligible "$ELIGIBLE" --prefix "$PREFIX"
else
  echo "   WARNING: no --eligible given, so abguard REJECTS will be refolded too."
  echo "            Gate first (pipeline/filter/gate.sh) and pass reports/<run>-eligible.csv."
fi
NQ=$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))["queries"]))' "$OUT/prepare/holo/queries.json")
echo "   $NQ query/queries to refold, est ~$(( (NQ * 15 + 45) / 60 )) min at the measured 15 s/design"

echo
echo "== 3/4  predict with OpenFold3-OpenBind, template + detailed scores"
"${docker_run[@]}" "$OF3" module-run predict \
  --input "$OUT/prepare/holo/queries.json" \
  --output "$OUT/pred" \
  --template-paths "$OUT/prepare/holo/template.cif" \
  --missing-msas ignore \
  --write-detailed-scores true 2>&1 | tail -4

echo
echo "== 4/4  refold-score"
"${docker_run[@]}" "$RFD" module-run refold-score \
  --input "$RUN" --predictions "$OUT/pred" \
  --output "$OUT/scored" --model "$MODEL_LABEL" 2>&1 | tail -3

M="$OUT/scored/refold_metrics.csv"
[[ -f "$M" ]] || die "refold-score wrote no refold_metrics.csv; see $OUT/scored/error.json"

echo
echo "== done. metrics: $M"
python3 - "$M" <<'PY'
import csv, sys, statistics as st
rows = list(csv.DictReader(open(sys.argv[1])))
print(f"   {len(rows)} refold(s) scored")
for col in ("min_ipae", "iptm", "binder_plddt", "plddt", "binder_ptm"):
    vals = []
    for r in rows:
        v = (r.get(col) or "").strip()
        if v:
            try: vals.append(float(v))
            except ValueError: pass
    if vals:
        print(f"   {col:<14} n={len(vals):<4} min={min(vals):.3f} median={st.median(vals):.3f} max={max(vals):.3f}")
    else:
        print(f"   {col:<14} EMPTY for all rows  <-- cannot rank on this")
PY
echo
echo "Next: join these onto the candidate rows and rank."
