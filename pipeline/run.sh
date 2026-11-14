#!/usr/bin/env bash
# One entry point for the whole pipeline. Deterministic, re-runnable, and honest about
# which stages need hardware we will not have after tonight.
#
#   bash pipeline/run.sh                                  # default target + batch 1
#   bash pipeline/run.sh --target 1N8Z --designs designs/raw/batch1-b1-novel-s1.csv
#   bash pipeline/run.sh --target 7MN8 --out runs/unseen   # a target we have never seen
#   bash pipeline/run.sh --offline                         # no network, use committed structure
#   bash pipeline/run.sh --stage epitope                   # one stage only
#   bash pipeline/run.sh --list                            # what runs where
#
# Design rule: every stage that can run on a laptop with nothing but python3 does.
# The stages that need the VM (abguard), a VM-local binary (netsolp) or a Nebius key
# (boltz2) are isolated, skipped cleanly when unavailable, and their last real output is
# committed so the rest of the pipeline is still reproducible without them.
#
# Exit 0 = every stage that could run, ran and passed.
# Exit 2 = a local stage failed. That is a real failure.
# Exit 3 = a local stage passed but a remote stage was unavailable (partial run).
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

TARGET="1N8Z"
DESIGNS=""          # empty = every batch in designs/raw/
OUT="reports"
CUTOFF="4.5"
OFFLINE=0
ONLY=""
SEED="20261114"
TARGET_CHAIN="C"

# Pinned so a re-run is byte-identical. PYTHONHASHSEED matters for any dict/set iteration
# that leaks into output ordering; -I ignores the venv and user site-packages so the
# stdlib-only stages cannot pick up a different library than the one we tested.
export PYTHONHASHSEED=0
export LC_ALL=C
PY=(python3 -I)

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m   %s\n' "$*"; }
skip() { printf '   \033[33mskip\033[0m %s\n' "$*"; }
bad()  { printf '   \033[31mFAIL\033[0m %s\n' "$*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)   TARGET="$2"; shift 2;;
    --designs)  DESIGNS="$2"; shift 2;;
    --out)      OUT="$2"; shift 2;;
    --cutoff)   CUTOFF="$2"; shift 2;;
    --chain)    TARGET_CHAIN="$2"; shift 2;;
    --seed)     SEED="$2"; shift 2;;
    --offline)  OFFLINE=1; shift;;
    --stage)    ONLY="$2"; shift 2;;
    --list)
      cat <<'TABLE'
Stage        Needs                        Runs on a laptop?
---------------------------------------------------------------------------
fetch        network (RCSB) or committed  yes (--offline uses data/target/)
epitope      python3 stdlib only          yes
paratope     python3 stdlib only          yes
gate         abguard, team VM, login sh   no  - cached verdicts committed
solubility   netsolp binary on the VM     no  - cached scores committed
refold       Nebius API key (boltz2)      no  - cached metrics committed
rank         python3 stdlib only          yes (refuses to emit without scores)
TABLE
      exit 0;;
    -h|--help) sed -n '2,25p' "$0"; exit 0;;
    *) echo "unknown argument: $1" >&2; exit 64;;
  esac
done

mkdir -p "$OUT" data/target
PARTIAL=0
FAILED=0
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
PROV="$OUT/run-${RUN_ID}.provenance.txt"

want() { [[ -z "$ONLY" || "$ONLY" == "$1" ]]; }

{
  echo "run_id         $RUN_ID"
  echo "target         $TARGET  chain $TARGET_CHAIN"
  echo "designs        $DESIGNS"
  echo "cutoff         $CUTOFF A all-heavy-atom"
  echo "seed           $SEED"
  echo "offline        $OFFLINE"
  echo "python         $(python3 -V 2>&1)"
  echo "uname          $(uname -srm)"
  echo "git            $(git rev-parse --short HEAD 2>/dev/null || echo 'not a git repo')"
  echo "PYTHONHASHSEED $PYTHONHASHSEED"
} > "$PROV"

# ---------------------------------------------------------------- 0. target structure
PDB="data/target/$(echo "$TARGET" | tr '[:upper:]' '[:lower:]').pdb"
if want fetch; then
  say "0. target structure - $TARGET"
  if [[ -s "$PDB" ]]; then
    ok "$PDB already present ($(wc -c <"$PDB" | tr -d ' ') bytes), not refetching"
  elif [[ "$OFFLINE" == 1 ]]; then
    bad "$PDB missing and --offline given"; FAILED=1
  else
    URL="https://files.rcsb.org/download/${TARGET}.pdb"
    if curl -sSf --max-time 90 -o "$PDB.part" "$URL"; then
      mv "$PDB.part" "$PDB"; ok "fetched $URL"
    else
      rm -f "$PDB.part"; bad "could not fetch $URL"; FAILED=1
    fi
  fi
  if [[ -s "$PDB" ]]; then
    SUM="$(shasum -a 256 "$PDB" | cut -d' ' -f1)"
    echo "target_sha256  $SUM  $PDB" >> "$PROV"
    ok "sha256 ${SUM:0:16}..."
  fi
fi

# ---------------------------------------------------------------- 1. epitope
EPI="$OUT/epitope-$(echo "$TARGET" | tr '[:upper:]' '[:lower:]')-${CUTOFF}.txt"
if want epitope; then
  say "1. interface - $CUTOFF A, all heavy atoms"
  if [[ ! -s "$PDB" ]]; then
    bad "no structure at $PDB"; FAILED=1
  elif "${PY[@]}" pipeline/score/epitope.py "$PDB" "$CUTOFF" > "$EPI" 2>"$EPI.err"; then
    N="$(grep -c '^| [A-Z][0-9]' "$EPI" || true)"
    ok "$EPI"
    grep -m1 '^## Epitope' "$EPI" | sed 's/^/        /'
    grep -m1 '^# .* epitope span' "$EPI" | sed 's/^/        /'
    rm -f "$EPI.err"
  else
    bad "epitope.py failed:"; sed 's/^/        /' "$EPI.err"; FAILED=1
  fi
fi

# ---------------------------------------------------------------- 2. paratope proxy
# Every batch, not just one - batch names change and a silently-skipped batch is how a
# bad design reaches the list. No GPU, no network, ~1 s per batch.
batches() {
  if [[ -n "$DESIGNS" ]]; then echo "$DESIGNS"; return; fi
  find designs/raw -maxdepth 1 -name '*.csv' 2>/dev/null | sort
}

if want paratope; then
  say "2. paratope conservation - free, no GPU"
  FOUND=0
  while read -r RAWB; do
    [[ -n "$RAWB" ]] || continue
    FOUND=1
    B="$(basename "${RAWB%.csv}")"
    ELIG="$OUT/$B-eligible.csv"
    SRC="$ELIG"; [[ -s "$SRC" ]] || SRC="$RAWB"
    LOG="$OUT/$B-paratope.stdout"
    if "${PY[@]}" pipeline/score/paratope_check.py "$SRC" "$RAWB" -o "$OUT/$B-paratope.csv" >"$LOG" 2>&1; then
      N="$(sed -n 's/^Unique eligible designs analysed: //p' "$LOG")"
      K3="$(sed -n 's/^| 3 of 4 | \([0-9]*\) .*/\1/p' "$LOG")"
      PRI="$(sed -n 's/^Priority for refold scoring.*: //p' "$LOG")"
      ok "$B - $N designs, ${K3:-0} keep 3/4 contacts, ${PRI:-0} in the >=3-contact/>=6-mutation band"
      [[ -s "$ELIG" ]] || skip "  (no gate verdicts for $B - scored the raw batch)"
    else
      bad "$B - paratope_check failed:"; tail -4 "$LOG" | sed 's/^/        /'; FAILED=1
    fi
  done < <(batches)
  [[ $FOUND == 1 ]] || { bad "no batches found in designs/raw/"; FAILED=1; }
fi

# ---------------------------------------------------------------- 3. abguard gate (VM)
if want gate; then
  say "3. abguard gate - team VM only"
  while read -r RAWB; do
    [[ -n "$RAWB" ]] || continue
    B="$(basename "${RAWB%.csv}")"
    bash pipeline/filter/gate.sh "$RAWB" >"$OUT/$B-gate.stdout" 2>&1
    RC=$?
    case $RC in
      0)   ok "$B - every design eligible";;
      127) skip "$B - abguard not on this machine (exit 127); cached verdicts in $OUT/$B-novelty.csv"
           echo "stage_gate     SKIPPED - abguard not on this machine" >> "$PROV"; PARTIAL=1;;
      *)   bad "$B - gate rejected designs (exit $RC), see $OUT/$B-gate.stdout"
           tail -4 "$OUT/$B-gate.stdout" | sed 's/^/        /';;
    esac
  done < <(batches)
fi

# ---------------------------------------------------------------- 4. solubility (VM binary)
if want solubility; then
  say "4. solubility floor - netsolp, VM binary"
  if [[ -x "$HOME/tools/netsolp/netsolp" ]] || command -v netsolp >/dev/null 2>&1; then
    "${PY[@]}" pipeline/filter/solubility.py "$DESIGNS" >"$OUT/solubility.stdout" 2>&1 \
      && ok "scored" || { bad "solubility.py failed"; FAILED=1; }
  else
    skip "netsolp not installed here. Calibration committed: reports/netsolp-calibration-spr190.csv (190 measured binders, floor 0.4960)"
    echo "stage_solubility SKIPPED - netsolp is VM-local" >> "$PROV"; PARTIAL=1
  fi
fi

# ---------------------------------------------------------------- 5. refold (Nebius)
if want refold; then
  say "5. refold / co-fold - boltz2 on Nebius"
  FORGE="$REPO/../agent/nebius-scientific-ai/forge.py"
  CREDS="$REPO/../credentials.private.json"
  if [[ -f "$FORGE" && -f "$CREDS" ]]; then
    skip "credentials present but co-folds not launched by this script - run pipeline/score/refold.sh explicitly (it spends shared GPU budget)"
  else
    skip "no Nebius credentials on this machine. Verified timing: boltz2 63 s (nebius-runs/pae-probe.json)"
  fi
  echo "stage_refold   SKIPPED - needs Nebius key, launched explicitly" >> "$PROV"; PARTIAL=1
fi

# ---------------------------------------------------------------- 6. rank
if want rank; then
  say "6. rank -> submission"
  PARA_TABLES=()
  while read -r P; do [[ -n "$P" ]] && PARA_TABLES+=(--paratope "$P"); done \
    < <(find "$OUT" -maxdepth 1 -name '*-paratope.csv' | sort)
  if [[ ${#PARA_TABLES[@]} == 0 ]]; then
    bad "no *-paratope.csv in $OUT - run stage 2 first"; FAILED=1
  elif "${PY[@]}" pipeline/score/rank.py "${PARA_TABLES[@]}" \
        --out designs/submission.csv --seed "$SEED" >"$OUT/rank.stdout" 2>&1; then
    ok "designs/submission.csv"
    sed 's/^/        /' "$OUT/rank.stdout"
  else
    RC=$?
    if [[ $RC == 3 ]]; then
      skip "rank refused to emit a submission - required scores missing"
      sed 's/^/        /' "$OUT/rank.stdout"; PARTIAL=1
    else
      bad "rank.py failed"; tail -10 "$OUT/rank.stdout" | sed 's/^/        /'; FAILED=1
    fi
  fi
fi

say "summary"
echo "   provenance: $PROV"
if [[ $FAILED == 1 ]]; then
  bad "a local stage failed - this is a real failure"; exit 2
elif [[ $PARTIAL == 1 ]]; then
  skip "local stages passed; remote stages unavailable on this machine (expected off-VM)"; exit 3
else
  ok "all stages passed"; exit 0
fi
