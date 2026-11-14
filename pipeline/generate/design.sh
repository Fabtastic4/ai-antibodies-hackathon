#!/usr/bin/env bash
# RFD4-Proteina design launcher. Run on the team VM, from $HOME.
#
#   bash pipeline/generate/design.sh --model her2-exploratory --seed 2 --reps 200 --out mark/runs/b2-explor-s2
#   bash pipeline/generate/design.sh --model her2-exploratory --seed 2 --check     # preflight only, no GPU
#
# Why this exists: ~/mark/generate.sh pointed the diversity arm at the her2-novel IMAGE while asking
# for the her2-exploratory MODEL. Each weight ships as its own image, so the run died on contact:
#   error[precondition]: Model her2-exploratory is not in this image; available: her2-novel
# It failed at 12:41 UTC and left the GPU idle on our work for ~20 minutes before anyone noticed.
#
# The fix is structural: you name the MODEL, the script derives the IMAGE. You cannot mismatch them.
# Everything is then preflighted on CPU before the GPU is requested, so a typo costs 10 seconds
# instead of a silent hole in the schedule.
set -euo pipefail

REGISTRY=quay.io/apheris/oslo-hackathon
PREFIX=apheris-rfd4-proteina-v0.3.0
MAX_REPS=200          # the CLI's own cap: "Designs generated per input, up to 200"
INPUT=Data/12-her2/her2_cdrh3.yaml

# model -> image tag. Verified by probing each image on 14 Nov; `release` is NOT pulled on this VM.
image_for() {
  case "$1" in
    antibody)                                        echo "$PREFIX-antibody-2026-10-30" ;;
    her2-conservative|her2-balanced|her2-exploratory) echo "$PREFIX-her2-2026-11-07" ;;
    her2-novel)                                      echo "$PREFIX-her2-novel-2026-11-09" ;;
    *) return 1 ;;
  esac
}

MODEL="" SEED="" REPS=200 OUT="" CHECK=0 RECYCLE="high/front_loaded" TSRK=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)   MODEL="$2"; shift 2 ;;
    --seed)    SEED="$2"; shift 2 ;;
    --reps)    REPS="$2"; shift 2 ;;
    --out)     OUT="$2"; shift 2 ;;
    --recycle) RECYCLE="$2"; shift 2 ;;
    --tsr-k)   TSRK="$2"; shift 2 ;;
    --check)   CHECK=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

die() { echo "FAIL: $*" >&2; exit 1; }

[[ -n "$MODEL" ]] || die "--model is required (antibody | her2-conservative | her2-balanced | her2-exploratory | her2-novel)"
[[ -n "$SEED"  ]] || die "--seed is required. Record it: an unseeded run is not reproducible, and provenance is the Execution score."

TAG="$(image_for "$MODEL")" || die "unknown model '$MODEL'. 'release' has no image on this VM."
IMAGE="$REGISTRY:$TAG"
OUT="${OUT:-mark/runs/${MODEL}-s${SEED}}"

(( REPS >= 1 )) || die "--reps must be >= 1"
if (( REPS > MAX_REPS )); then
  die "--reps $REPS exceeds the CLI cap of $MAX_REPS per run. For more, launch several runs with DIFFERENT seeds
     (replicates of one seed give diminishing diversity: batch 1 went from 93.4% unique at n=129 to 86.4% at n=200)."
fi

cd "$HOME"

echo "== preflight"
[[ -f "$INPUT" ]] || die "input not found: \$HOME/$INPUT"
command -v docker >/dev/null || die "docker not on PATH"
docker image inspect "$IMAGE" >/dev/null 2>&1 || die "image not pulled locally: $IMAGE"

# The check that would have caught the 12:41 failure: ask the image which models it has, on CPU.
echo -n "   model '$MODEL' present in $TAG ... "
probe="$(docker run --rm -e HOME=/tmp "$IMAGE" module-run design \
          --model "$MODEL" --input /dev/null --output /tmp/preflight 2>&1 || true)"
if grep -q "is not in this image" <<<"$probe"; then
  echo "NO"
  die "$(grep -o 'available:.*' <<<"$probe" | head -1)
     '$MODEL' is not in $TAG. This is exactly the bug that killed the diversity arm."
fi
echo "yes"

if [[ -e "$OUT" ]] && find "$OUT" -name '*_generated.cif' -print -quit 2>/dev/null | grep -q .; then
  n=$(find "$OUT" -name '*_generated.cif' | wc -l | tr -d ' ')
  die "$OUT already holds $n generated CIFs. Pick another --out, or delete it deliberately.
     Never resubmit a run you have already paid for."
fi

free_mib=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
others=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l | tr -d ' ')
echo "   GPU: ${free_mib} MiB free, ${others} other process(es) running"
(( free_mib > 20000 )) || echo "   WARNING: under 20 GB free. One H100 for six people - say so in Slack before you start."

est=$(awk -v r="$REPS" 'BEGIN{printf "%.0f", r/4.37 + 1.5}')
echo "   est wall clock: ~${est} min at the measured 4.37 designs/min (plus ~90s compile)"

if (( CHECK )); then
  echo "== --check only, nothing launched. Drop --check to run."
  exit 0
fi

# Create the PARENT only. Pre-creating $OUT makes it a non-Foundry directory, and the CLI then
# refuses: "--overwrite refuses to delete a non-Foundry directory (no .apheris-foundry)".
mkdir -p "$(dirname "$OUT")"
rmdir "$OUT" 2>/dev/null || true
digest=$(docker image inspect --format '{{index .RepoDigests 0}}' "$IMAGE" 2>/dev/null || echo "$IMAGE")

# Provenance beside the run dir, not inside it, for the same reason. Written before launch so a
# failed run still leaves a record of what was attempted.
cat > "$(dirname "$OUT")/$(basename "$OUT").manifest.json" <<JSON
{
  "model": "$MODEL",
  "image": "$IMAGE",
  "image_digest": "$digest",
  "num_replicates": $REPS,
  "seed": $SEED,
  "recycle_strategy": "$RECYCLE",
  "sequence_tsr_k": "${TSRK:-default}",
  "input": "$INPUT",
  "started_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON

args=(module-run design --input "$INPUT" --output "$OUT" --model "$MODEL"
      --num-replicates "$REPS" --seed "$SEED" --recycle-strategy "$RECYCLE"
      --compile true --overwrite true)
[[ -n "$TSRK" ]] && args+=(--sequence-tsr-k "$TSRK")

echo "== launching $MODEL seed $SEED reps $REPS -> $OUT   $(date -u +%H:%M:%S)Z"
docker run --rm --gpus all --shm-size 16g --user "$(id -u):$(id -g)" \
  -e HOME=/tmp -v /etc/passwd:/etc/passwd:ro -v "$PWD:/work" -w /work \
  "$IMAGE" "${args[@]}" 2>&1 | tee -a "$OUT/generate.log"

echo "== done $(date -u +%H:%M:%S)Z"
n=$(find "$OUT" -name '*_generated.cif' | wc -l | tr -d ' ')
echo "   $n CIFs in $OUT"
[[ -f "$OUT/error.json" ]] && { echo "   ERROR recorded:"; cat "$OUT/error.json"; exit 1; }

cat <<NEXT

Next, to turn these into gated candidates:
  python3 pipeline/filter/cif_to_submission.py $OUT -o designs/raw/$(basename "$OUT").csv \\
      --model-version $MODEL --seed $SEED
  bash pipeline/filter/gate.sh designs/raw/$(basename "$OUT").csv
NEXT
