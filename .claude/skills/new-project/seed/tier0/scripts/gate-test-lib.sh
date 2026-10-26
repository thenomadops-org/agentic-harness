#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# gate-test-lib.sh — the shared harness for guard regression suites.
#
# Source it, declare cases, call gate_done. It is not executable on its own.
#
# ============================================================================
# WHY THIS EXISTS
# ============================================================================
#
# Every guard ships with a `<guard>.test.sh` beside it, and on one project seventeen
# of them each re-implemented the same forty lines of scoreboard by hand. That is
# not merely duplication — it is seventeen independent chances to write a
# scoreboard that cannot report a failure. One of them did:
#
#   The first draft of dod-check.test.sh ran its cases through a pipeline
#   (`printf ... | expect ...`). A pipeline stage runs in a SUBSHELL, so every
#   `fail=$((fail+1))` incremented a copy and threw it away. The suite printed
#   `passed=1 failed=0` while running twelve cases and exited 0.
#
# That is the same bug the guards exist to catch, wearing the test suite's badge:
# a check that reports success while inspecting nothing. So this harness closes
# it structurally rather than by care.
#
# THREE PROPERTIES, none of them optional:
#
#  1. NO SUBSHELL. Case functions are called directly, never piped into. Input
#     for the command under test is passed as an ARGUMENT and fed via a here-string
#     inside the function, so the counters live in the caller's shell.
#
#  2. ZERO CASES IS A FAILURE. `gate_done <min-cases>` takes a REQUIRED minimum
#     and fails if fewer ran. A suite whose case-construction silently broke —
#     a fixture directory that moved, a `for` loop over an empty glob — otherwise
#     exits 0 having tested nothing, and nothing green ever gets investigated.
#     The minimum is required rather than defaulted because an author who cannot
#     say how many cases they have does not know whether the suite collapsed.
#
#  3. THE HARNESS IS ITSELF TESTED. gate-test-lib.test.sh asserts that a
#     deliberately wrong case makes the scoreboard red, and that a suite running
#     zero cases is red. A harness nobody watched fail is not a harness.
#
# ============================================================================
# USAGE
# ============================================================================
#
#   #!/usr/bin/env bash
#   set -uo pipefail
#   HERE="$(cd "$(dirname "$0")" && pwd)"
#   . "$HERE/gate-test-lib.sh"
#
#   gate_section "MUST PASS"
#   gate_expect    0 "clean tree"        ""            -- bash "$HERE/my-guard.sh"
#   gate_expect_in 0 "good body"         "$GOOD"       -- bash "$HERE/dod-check.sh"
#
#   gate_section "MUST FAIL"
#   gate_expect_in 1 "wiring removed"    "$BROKEN"     -- bash "$HERE/dod-check.sh"
#   gate_expect_in 1 "empty body"        ""            -- bash "$HERE/dod-check.sh" \
#     --want "every mandatory section is missing"
#
#   gate_done 4
#
# Argument order is fixed and positional up to `--`; `--want SUBSTR` may follow
# the command to assert on combined stdout+stderr.

# Refuse to be executed. A harness run directly does nothing and exits 0, which
# is a green result from a file that tested nothing — the shape this whole file
# exists to prevent.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  echo "gate-test-lib.sh is a library — source it from a .test.sh, do not run it" >&2
  exit 2
fi

GATE_PASS=0
GATE_FAIL=0
GATE_CASES=0
GATE_NAME="${GATE_NAME:-$(basename "${0}")}"

gate_section() {
  printf '\n== %s ==\n' "$1"
}

# _gate_report <want> <got> <name> <output> <want_substr>
_gate_report() {
  local want="$1" got="$2" name="$3" out="$4" want_sub="$5"
  GATE_CASES=$((GATE_CASES + 1))

  if [ "$got" -ne "$want" ]; then
    GATE_FAIL=$((GATE_FAIL + 1))
    printf 'FAIL  %-46s want exit=%s got exit=%s\n' "$name" "$want" "$got"
    printf '%s\n' "$out" | sed 's/^/        | /'
    return 0
  fi

  if [ -n "$want_sub" ] && ! printf '%s\n' "$out" | grep -qF -- "$want_sub"; then
    GATE_FAIL=$((GATE_FAIL + 1))
    printf 'FAIL  %-46s exit=%s but output lacked: %s\n' "$name" "$got" "$want_sub"
    printf '%s\n' "$out" | sed 's/^/        | /'
    return 0
  fi

  GATE_PASS=$((GATE_PASS + 1))
  printf 'ok    %-46s exit=%s\n' "$name" "$got"
}

# _gate_split_want — pull a trailing `--want SUBSTR` off the argument list.
# Sets GATE_WANT_SUB and rewrites GATE_ARGV.
_gate_split_want() {
  GATE_WANT_SUB=""
  GATE_ARGV=()
  local a
  while [ "$#" -gt 0 ]; do
    a="$1"
    if [ "$a" = "--want" ]; then
      shift
      GATE_WANT_SUB="${1:-}"
      shift || true
      continue
    fi
    GATE_ARGV+=("$a")
    shift
  done
}

# gate_expect <want-exit> <name> <ignored-slot> -- <cmd...> [--want SUBSTR]
#
# The third positional is a deliberately empty slot so that gate_expect and
# gate_expect_in have the same shape at the call site; pass "".
gate_expect() {
  local want="$1" name="$2"
  shift 3
  [ "${1:-}" = "--" ] && shift
  _gate_split_want "$@"
  local out rc
  out="$("${GATE_ARGV[@]}" 2>&1)"
  rc=$?
  _gate_report "$want" "$rc" "$name" "$out" "$GATE_WANT_SUB"
}

# gate_expect_in <want-exit> <name> <stdin-string> -- <cmd...> [--want SUBSTR]
gate_expect_in() {
  local want="$1" name="$2" input="$3"
  shift 3
  [ "${1:-}" = "--" ] && shift
  _gate_split_want "$@"
  local out rc
  # Here-string, not a pipeline: a pipeline would put this function in a
  # subshell and the counters would be discarded. See property 1 above.
  out="$("${GATE_ARGV[@]}" <<<"$input" 2>&1)"
  rc=$?
  _gate_report "$want" "$rc" "$name" "$out" "$GATE_WANT_SUB"
}

# gate_tmpdir — a scratch directory removed on exit. Echoes the path.
gate_tmpdir() {
  local d
  d="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf -- '$d'" EXIT
  printf '%s\n' "$d"
}

# gate_done <min-cases> — scoreboard and exit status.
#
# min-cases is REQUIRED. See property 2.
gate_done() {
  if [ "$#" -ne 1 ] || ! printf '%s' "${1:-}" | grep -qE '^[0-9]+$'; then
    printf '\nFAIL  gate_done needs a required minimum case count: gate_done <n>\n' >&2
    exit 2
  fi
  local min="$1"

  printf '\n%s: cases=%s passed=%s failed=%s (minimum expected %s)\n' \
    "$GATE_NAME" "$GATE_CASES" "$GATE_PASS" "$GATE_FAIL" "$min"

  if [ "$GATE_CASES" -lt "$min" ]; then
    printf 'FAIL  suite ran %s case(s), fewer than the %s it declares. Case construction\n' \
      "$GATE_CASES" "$min" >&2
    printf '      collapsed — a suite that tests nothing exits 0 and nobody investigates green.\n' >&2
    exit 1
  fi

  [ "$GATE_FAIL" -eq 0 ]
}
