#!/usr/bin/env bash
# The submission gate. Run this on the VM before anything goes on the list, and again at 16:00.
#
#   bash pipeline/filter/gate.sh                     # gate designs/submission.csv
#   bash pipeline/filter/gate.sh path/to/batch.csv   # gate one generation batch
#
# Exit 0 = every design is eligible. Non-zero = it is not a submission yet, and the
# reason is printed per design.
#
# Why `bash -lc` around abguard: it lives in ~/.local/bin, which is only on PATH in a
# login shell. Called from a plain script it is "command not found" - see docs/abguard.md.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IN="${1:-$REPO/designs/submission.csv}"
GENERATED="${IN%.csv}.abguard.csv"
REPORTS="$REPO/reports"
# Report names are per batch. They used to be fixed, which meant gating batch 2 silently
# overwrote batch 1's novelty/liability/solubility evidence - and that evidence is what the
# decision log cites. BASE also matches what pipeline/status.py globs for.
BASE="$(basename "${IN%.csv}")"

ABGUARD="$HOME/.local/bin/abguard"
if [[ ! -x "$ABGUARD" ]]; then
  if command -v abguard >/dev/null 2>&1; then
    ABGUARD="$(command -v abguard)"
  else
    echo "abguard not found. This script is meant to run on the team VM." >&2
    echo "On the VM it is $HOME/.local/bin/abguard - see docs/abguard.md." >&2
    exit 127
  fi
fi

echo "== 1/5  our table -> abguard's columns"
# The handover rules (<=20 rows, ranks 1..N, no duplicate sequences) apply to the submission
# table, not to a 200-row generation batch. Turn them on automatically for the real thing.
conv_args=(-i "$IN" -o "$GENERATED")
case "$(basename "$IN")" in
  submission.csv|submission-*.csv) conv_args+=(--submission); echo "   (submission mode: handover rules enforced)" ;;
esac
python3 "$REPO/pipeline/filter/to_abguard.py" "${conv_args[@]}" || exit $?

mkdir -p "$REPORTS"

echo
echo "== 2/5  novelty detail (filters nothing, for the decision log)"
"$ABGUARD" novelty-report "$GENERATED" -o "$REPORTS/$BASE-novelty.csv" || true
"$ABGUARD" novelty-report "$GENERATED" || true

echo
echo "== 3/5  liability detail"
"$ABGUARD" liability-report "$GENERATED" -o "$REPORTS/$BASE-liability.json" || true

echo
echo "== 4/5  NetSolP solubility  (OURS, not the organisers' gate - advisory)"
CALIB="$REPO/reports/netsolp-calibration-spr190.csv"
if [[ -x "${NETSOLP_HOME:-$HOME/tools/netsolp}/netsolp_csv.py" || -f "${NETSOLP_HOME:-$HOME/tools/netsolp}/netsolp_csv.py" ]]; then
  sol_args=("$REPO/pipeline/filter/solubility.py" "$GENERATED" -o "$REPORTS/$BASE-solubility.csv")
  [[ -f "$CALIB" ]] && sol_args+=(--calibrate "$CALIB")
  [[ "${SOLUBILITY_STRICT:-0}" == "1" ]] && sol_args+=(--strict)
  if python3 "${sol_args[@]}"; then :; else
    sol_status=$?
    if [[ "${SOLUBILITY_STRICT:-0}" == "1" ]]; then
      echo "FAIL: designs below the measured-binder solubility floor, and SOLUBILITY_STRICT=1." >&2
      exit "$sol_status"
    fi
    echo "   (non-fatal: NetSolP is a floor and a tiebreak here, not a cut - see solubility.py)"
  fi
else
  echo "   skipped: NetSolP not installed here. On the VM it is ~/tools/netsolp."
fi

echo
echo "== 5/5  THE GATE  (abguard; no --drop: any failure is a failure)"
"$ABGUARD" team-validate "$GENERATED"
status=$?   # must be captured here: `$?` after `fi` is the if-construct's status, not abguard's

if [[ $status -eq 0 ]]; then
  echo
  echo "PASS - every design in $(basename "$IN") is eligible."
  "$ABGUARD" team-validate "$GENERATED" --drop -o "$REPORTS/$BASE-eligible.csv" >/dev/null 2>&1 || true
  echo "Reports: reports/$BASE-{novelty.csv,liability.json,solubility.csv,eligible.csv}"
  exit 0
fi

echo
echo "FAIL (exit $status) - the designs named above are NOT submittable."
echo "Writing the survivors anyway, so the funnel is measurable:"
"$ABGUARD" team-validate "$GENERATED" --drop -o "$REPORTS/$BASE-eligible.csv" 2>&1 | grep -E "valid|wrote" || true
echo "  -> reports/$BASE-eligible.csv"
exit "$status"
