#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# Regression suite for scripts/runner-pinning-check.sh.
#
# Every MUST-FAIL case is a way the check could be hollowed out, asserted to still
# be red. The two that matter most are the vacuity cases: an empty workflow
# directory and a scanner that sees zero runs-on values must both be RED, because
# a guard that passes on nothing is the defect this whole seed exists to prevent.

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/gate-test-lib.sh"

CHECK="$HERE/runner-pinning-check.sh"
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT

printf 'ubuntu-24.04\nself-hosted,Linux,X64\n' >"$TMP/allow"
export ALLOWED_RUNNERS_FILE="$TMP/allow"

# wf <dir> <file> <content> — build a workflow fixture directory.
wf() {
  mkdir -p "$TMP/$1"
  printf '%s\n' "$3" >"$TMP/$1/$2"
}

check() { bash "$CHECK" "$TMP/$1"; }

wf good scalar.yml 'jobs:
  build:
    runs-on: ubuntu-24.04
    steps: []'

wf good flow.yml 'jobs:
  test:
    runs-on: [self-hosted, Linux, X64]
    steps: []'

# Label ORDER must not decide the verdict: the same fleet spelled two ways has to
# get the same answer, or the gate is a coin toss on style.
wf good reordered.yml 'jobs:
  lint:
    runs-on: [X64, self-hosted, Linux]
    steps: []'

wf good quoted.yml 'jobs:
  quoted:
    runs-on: "ubuntu-24.04"
    steps: []'

gate_section "MUST PASS"
gate_expect 0 "listed scalars and flow sequences" "" -- check good \
  --want "runner-pinning-check PASSED"

gate_section "MUST FAIL — the violation this exists for"
# The named incident: a bare `self-hosted` landed Go jobs on a macOS arm64 laptop.
wf bare bare.yml 'jobs:
  build:
    runs-on: self-hosted
    steps: []'
gate_expect 1 "bare self-hosted" "" -- check bare --want "RUNNER-PINNING"

wf partial partial.yml 'jobs:
  build:
    runs-on: [self-hosted, Linux]
    steps: []'
gate_expect 1 "partial label set (arch unpinned)" "" -- check partial --want "RUNNER-PINNING"

wf latest latest.yml 'jobs:
  build:
    runs-on: ubuntu-latest
    steps: []'
gate_expect 1 "a moving image label" "" -- check latest --want "RUNNER-PINNING"

wf mixed mixed.yml 'jobs:
  ok:
    runs-on: ubuntu-24.04
  bad:
    runs-on: windows-latest'
gate_expect 1 "one good job does not excuse a bad one" "" -- check mixed --want "windows-latest"

gate_section "MUST FAIL — unreadable is not compliant"
# The pinned gap. A shape the scanner cannot read must be RED, never assumed fine:
# a regex that guesses at YAML it does not know produces a narrower hole of the
# same shape as the one it fixed.
wf block block.yml 'jobs:
  build:
    runs-on:
      - self-hosted
      - Linux
      - X64'
gate_expect 1 "block sequence is UNCLASSIFIABLE" "" -- check block --want "UNCLASSIFIABLE"

wf expr expr.yml 'jobs:
  build:
    runs-on: ${{ matrix.runner }}'
gate_expect 1 "expression is UNCLASSIFIABLE" "" -- check expr --want "UNCLASSIFIABLE"

gate_section "MUST FAIL — vacuity"
mkdir -p "$TMP/empty"
gate_expect 3 "no workflow files at all" "" -- check empty --want "passes on an empty set"

gate_expect 3 "no workflow directory" "" -- check does-not-exist \
  --want "no workflow directory"

# A file with no runs-on line at all: the census must catch a scanner that has
# stopped seeing its subjects.
wf nojobs reusable.yml 'name: nothing
on: workflow_call'
gate_expect 1 "zero runs-on values found" "" -- check nojobs --want "ZERO"

gate_section "MUST FAIL — configuration"
gate_expect 2 "missing allow-list file" "" -- \
  env ALLOWED_RUNNERS_FILE="$TMP/nope" bash "$CHECK" "$TMP/good" --want "is not configured"

: >"$TMP/empty-allow"
gate_expect 2 "empty allow-list file" "" -- \
  env ALLOWED_RUNNERS_FILE="$TMP/empty-allow" bash "$CHECK" "$TMP/good" --want "lists no runner sets"

# The allow-list is actually consulted — otherwise it is decoration and any
# runner would pass.
printf 'macos-14\n' >"$TMP/mac-only"
gate_expect 1 "ubuntu rejected when only macos-14 is allowed" "" -- \
  env ALLOWED_RUNNERS_FILE="$TMP/mac-only" bash "$CHECK" "$TMP/good" --want "RUNNER-PINNING"

gate_done 13
