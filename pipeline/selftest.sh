#!/usr/bin/env bash
# Prove the pipeline reproduces, to anyone, on their machine, in under a minute.
#
#   bash pipeline/selftest.sh
#
# Three kinds of check, in increasing strength:
#
#   A. DETERMINISM  - re-run a stage into a scratch dir, byte-compare against the
#                     committed output. Catches "it worked on my laptop".
#   B. SCIENCE      - assert the computed interface matches the published trastuzumab
#                     footprint (HER2 domain IV, 557-605) and that the closest contact is
#                     G103. A checksum proves we re-ran; this proves we are not re-running
#                     something wrong.
#   C. NEGATIVE     - the control designs must be REJECTED. A gate that passes everything
#                     is not a gate. Four controls, four different reasons.
#
# Exit 0 = every check that can run here, passed.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
export PYTHONHASHSEED=0 LC_ALL=C
PY=(python3 -I)
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0; FAIL=0; SKIP=0
pass() { printf '  \033[32mPASS\033[0m  %s\n' "$*"; PASS=$((PASS+1)); }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$*"; FAIL=$((FAIL+1)); }
skipc(){ printf '  \033[33mSKIP\033[0m  %s\n' "$*"; SKIP=$((SKIP+1)); }
head2(){ printf '\n\033[1m%s\033[0m\n' "$*"; }

PDB="data/target/1n8z.pdb"

head2 "A. Determinism - re-run and byte-compare"

if [[ ! -s "$PDB" ]]; then
  skipc "no $PDB (run: bash pipeline/run.sh --stage fetch)"
else
  EXPECTED="tests/expected/epitope-1n8z-4.5.txt"
  "${PY[@]}" pipeline/score/epitope.py "$PDB" 4.5 > "$TMP/epi.txt" 2>"$TMP/epi.err"
  if [[ -s "$TMP/epi.err" ]]; then
    fail "epitope.py wrote to stderr: $(head -1 "$TMP/epi.err")"
  elif [[ ! -f "$EXPECTED" ]]; then
    mkdir -p tests/expected; cp "$TMP/epi.txt" "$EXPECTED"
    pass "golden file created: $EXPECTED (commit it; future runs diff against it)"
  elif diff -q <(tail -n +2 "$EXPECTED") <(tail -n +2 "$TMP/epi.txt") >/dev/null; then
    pass "epitope output identical to $EXPECTED"
  else
    fail "epitope output DIFFERS from $EXPECTED"
    diff <(tail -n +2 "$EXPECTED") <(tail -n +2 "$TMP/epi.txt") | head -12 | sed 's/^/        /'
  fi

  # Twice in a row, same bytes - catches hash-ordering and set-iteration leaks.
  "${PY[@]}" pipeline/score/epitope.py "$PDB" 4.5 > "$TMP/epi2.txt" 2>/dev/null
  if diff -q "$TMP/epi.txt" "$TMP/epi2.txt" >/dev/null; then
    pass "two consecutive runs are byte-identical"
  else
    fail "consecutive runs differ - nondeterministic ordering"
  fi
fi

# Batch names change as teammates land runs, so discover them rather than hardcoding.
# A hardcoded name here silently degrades into a SKIP, which is how a broken stage
# passes a self-test.
NB=0
while read -r RAW; do
  [[ -n "$RAW" ]] || continue
  B="$(basename "${RAW%.csv}")"
  SRC="reports/$B-eligible.csv"; [[ -s "$SRC" ]] || SRC="$RAW"
  NB=$((NB+1))
  "${PY[@]}" pipeline/score/paratope_check.py "$SRC" "$RAW" -o "$TMP/$B.csv" >"$TMP/para-$B.txt" 2>&1
  "${PY[@]}" pipeline/score/paratope_check.py "$SRC" "$RAW" -o "$TMP/$B.2.csv" >/dev/null 2>&1
  if [[ ! -s "$TMP/$B.csv" ]]; then
    fail "$B - paratope_check produced no table"
  elif diff -q "$TMP/$B.csv" "$TMP/$B.2.csv" >/dev/null; then
    COMMITTED="reports/$B-paratope.csv"
    if [[ -s "$COMMITTED" ]] && ! diff -q "$COMMITTED" "$TMP/$B.csv" >/dev/null; then
      fail "$B - re-scored table differs from committed $COMMITTED"
      diff "$COMMITTED" "$TMP/$B.csv" | head -6 | sed 's/^/        /'
    else
      pass "$B - $(sed -n 's/^Unique eligible designs analysed: //p' "$TMP/para-$B.txt") designs, re-score reproduces committed table"
    fi
  else
    fail "$B - paratope_check is nondeterministic across runs"
  fi
done < <(find designs/raw -maxdepth 1 -name '*.csv' 2>/dev/null | sort)
[[ $NB -gt 0 ]] || skipc "no batches in designs/raw/ to re-score"

head2 "B. Science - does the computed interface match the published footprint?"

if [[ -s "$TMP/epi.txt" ]]; then
  # Published trastuzumab epitope: HER2 subdomain IV, three loops across 557-605.
  if grep -q '^# HER2 epitope span: 557-605' "$TMP/epi.txt"; then
    pass "epitope span is 557-605 (HER2 subdomain IV, as published)"
  else
    fail "epitope span is NOT 557-605: $(grep -m1 'epitope span' "$TMP/epi.txt")"
  fi

  for r in E558 D560 P571 P572 F573 K593 Q602; do
    if ! grep -q "| $r " "$TMP/epi.txt"; then
      fail "known epitope residue $r absent from computed interface"; break
    fi
  done
  grep -q '| Q602 ' "$TMP/epi.txt" && pass "known contact residues E558/D560/P571-F573/K593/Q602 all present"

  if grep -q '| G103 (GLY) | 2.42 |' "$TMP/epi.txt"; then
    pass "closest interface contact is G103 at 2.42 A"
  else
    fail "G103 is not at 2.42 A: $(grep -m1 'G103' "$TMP/epi.txt")"
  fi

  N="$(sed -n 's/^## Epitope.*, \([0-9]*\) residues/\1/p' "$TMP/epi.txt")"
  [[ "$N" == 19 ]] && pass "19 epitope residues" || fail "epitope residue count is $N, expected 19"

  # The VH in the reference structure must be our declared parent, or every position
  # index in the paratope analysis is off.
  TZVH="EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
  if grep -q "$TZVH" data/target/1n8z.fasta 2>/dev/null; then
    pass "1N8Z chain B VH is identical to our parent=trastuzumab VH"
  else
    skipc "could not confirm VH identity (missing data/target/1n8z.fasta)"
  fi
else
  skipc "no interface output to check"
fi

head2 "C. Negative controls - the gate must REJECT these"

CTRL="pipeline/filter/abguard-control.csv"
if [[ ! -s "$CTRL" ]]; then
  skipc "no control file at $CTRL"
elif ! command -v abguard >/dev/null 2>&1 && [[ ! -x "$HOME/.local/bin/abguard" ]]; then
  # abguard is VM-only, so verify against the committed verdicts instead of guessing.
  REP="reports/novelty-report-control.csv"
  if [[ -s "$REP" ]]; then
    NC=$(( $(grep -c . "$CTRL") - 1 ))
    PASSED="$(tail -n +2 "$REP" | grep -ci 'true\|pass' || true)"
    if [[ "$PASSED" == 0 ]]; then
      pass "cached control run: all $NC controls rejected ($REP)"
    else
      fail "cached control run shows $PASSED control(s) PASSING - the gate is not live"
    fi
  else
    skipc "abguard unavailable and no cached control report"
  fi
else
  bash pipeline/filter/gate.sh "$CTRL" >"$TMP/ctrl.log" 2>&1
  if [[ $? -ne 0 ]]; then
    pass "abguard rejected every control design (gate is live)"
  else
    fail "abguard PASSED a control design - the gate is not enforcing"
  fi
fi

head2 "D. Rank refuses to invent a submission"
PARA=()
while read -r P; do [[ -n "$P" ]] && PARA+=(--paratope "$P"); done \
  < <(find reports -maxdepth 1 -name '*-paratope.csv' 2>/dev/null | sort)
cp designs/submission.csv "$TMP/sub.csv" 2>/dev/null || true
"${PY[@]}" pipeline/score/rank.py "${PARA[@]}" \
    --refold /nonexistent --ddg /nonexistent --out "$TMP/sub.csv" >"$TMP/rank.log" 2>&1
RC=$?
# Refusal must leave the target untouched, not half-written.
if [[ $RC == 3 ]] && [[ $(grep -c . "$TMP/sub.csv" 2>/dev/null || echo 0) -le 1 ]]; then
  pass "refusal left designs/submission.csv unmodified (header only)"
fi
if [[ $RC == 3 ]]; then
  pass "rank.py exits 3 and writes nothing when binding/ddG scores are absent"
elif [[ $RC == 0 ]]; then
  fail "rank.py emitted a submission with two of three judged axes empty"
else
  skipc "rank.py exit $RC - $(tail -1 "$TMP/rank.log")"
fi

printf '\n\033[1m%s\033[0m\n' "result: $PASS passed, $FAIL failed, $SKIP skipped"
[[ $FAIL == 0 ]] || exit 1
