#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# Regression suite for gate-test-lib.sh.
#
# WHY THIS EXISTS, and why it is written the long way. Every other suite in the
# repo uses the harness. If the harness's scoreboard cannot report a failure,
# every one of those suites is green and meaningless — and a suite testing the
# harness *with* the harness would be green too, for the same reason. So this one
# file counts by hand. Independence is the whole point of it; do not "tidy" it to
# use the library it is testing.
#
# The named scar: dod-check.test.sh's first draft ran cases through a pipeline,
# so the counters incremented in a subshell and were discarded. It printed
# `passed=1 failed=0` while running twelve cases and exited 0.
#
# Usage: scripts/gate-test-lib.test.sh   (exit 0 = the harness can fail)

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LIB="$HERE/gate-test-lib.sh"
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT

pass=0
fail=0
cases=0

# check <want-exit> <name> <script-body>
check() {
  local want="$1" name="$2" body="$3" out rc f
  cases=$((cases + 1))
  f="$TMP/case-$cases.sh"
  {
    printf '#!/usr/bin/env bash\nset -uo pipefail\n. %q\n' "$LIB"
    printf '%s\n' "$body"
  } >"$f"
  out="$(bash "$f" 2>&1)"
  rc=$?
  if [ "$rc" -eq "$want" ]; then
    pass=$((pass + 1))
    printf 'ok    %-46s exit=%s\n' "$name" "$rc"
  else
    fail=$((fail + 1))
    printf 'FAIL  %-46s want exit=%s got exit=%s\n' "$name" "$want" "$rc"
    printf '%s\n' "$out" | sed 's/^/        | /'
  fi
}

echo "== the harness reports a PASS correctly =="
check 0 "all cases pass" '
gate_expect 0 "true exits 0" "" -- true
gate_expect 1 "false exits 1" "" -- false
gate_done 2
'

echo
echo "== THE ONE: the harness can report a FAILURE =="
# If this case ever goes green-when-it-should-be-red, every suite in the repo is
# decoration. It is the reason this file exists.
check 1 "a wrong expectation goes red" '
gate_expect 0 "false wrongly expected to pass" "" -- false
gate_done 1
'

check 1 "counters survive — 1 bad among many" '
gate_expect 0 "ok a" "" -- true
gate_expect 0 "ok b" "" -- true
gate_expect 0 "bad" "" -- false
gate_expect 0 "ok c" "" -- true
gate_done 4
'

check 1 "a missing --want substring goes red" '
gate_expect 0 "echoes hello" "" -- echo hello --want "goodbye"
gate_done 1
'

check 0 "a present --want substring passes" '
gate_expect 0 "echoes hello" "" -- echo hello --want "hello"
gate_done 1
'

echo
echo "== zero cases is a FAILURE, not a pass =="
# A suite whose case construction silently broke otherwise exits 0 having tested
# nothing, and nothing green ever gets investigated.
check 1 "no cases at all" '
gate_done 1
'

check 1 "fewer cases than declared" '
gate_expect 0 "only one" "" -- true
gate_done 5
'

echo
echo "== stdin cases do not lose their counters to a subshell =="
check 0 "stdin is fed without a pipeline" '
gate_expect_in 0 "cat sees input" "hello" -- cat --want "hello"
gate_done 1
'

check 1 "stdin case failure still counts" '
gate_expect_in 0 "grep finds nothing" "hello" -- grep -q "absent"
gate_done 1
'

echo
echo "== misuse is loud =="
check 2 "gate_done without a minimum" '
gate_expect 0 "x" "" -- true
gate_done
'

check 2 "gate_done with a non-numeric minimum" '
gate_expect 0 "x" "" -- true
gate_done many
'

# Running the library directly must not be a silent green.
out="$(bash "$LIB" 2>&1)"; rc=$?
cases=$((cases + 1))
if [ "$rc" -eq 2 ]; then
  pass=$((pass + 1)); printf 'ok    %-46s exit=%s\n' "executing the library is refused" "$rc"
else
  fail=$((fail + 1)); printf 'FAIL  %-46s want exit=2 got exit=%s\n' "executing the library is refused" "$rc"
  printf '%s\n' "$out" | sed 's/^/        | /'
fi

echo
echo "cases=$cases passed=$pass failed=$fail"

# This file's own vacuity guard, hand-written for the same reason as everything
# else here.
if [ "$cases" -lt 12 ]; then
  echo "FAIL  ran $cases cases, expected at least 12 — case construction collapsed" >&2
  exit 1
fi
[ "$fail" -eq 0 ]
