#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# Run every hook self-test in this directory.
#
# Discovery by glob, deliberately: a hand-maintained list of test scripts is a
# list that goes stale silently, and a suite that stopped being listed is a suite
# that stopped running while everything stayed green. A new
# .claude/hooks/*.test.sh is picked up with no edit to this file.
#
# AND IT REFUSES TO PASS ON AN EMPTY SWEEP. If the glob matches nothing, that is
# an error, not a green run — "0 suites, all passed" is the most reassuring
# possible way to say that nothing was tested. Zero is an error, never a pass.
#
# Usage: .claude/hooks/test-all.sh      (exit 0 = every suite passed)

set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

suites=0
failed=0
for t in "$HERE"/*.test.sh; do
	[ -f "$t" ] || continue
	suites=$((suites + 1))
	printf '\n########## %s ##########\n' "$(basename "$t")"
	if bash "$t"; then
		:
	else
		failed=$((failed + 1))
	fi
done

echo
if [ "$suites" -eq 0 ]; then
	echo "ERROR: no .claude/hooks/*.test.sh found. Zero suites is a broken sweep,"
	echo "       not a passing one."
	exit 2
fi
printf '########## %s suite(s), %s failed ##########\n' "$suites" "$failed"
[ "$failed" -eq 0 ]
