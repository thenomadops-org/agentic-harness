#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# Tests for .claude/hooks/transcript-evidence.py.
#
# WHY THIS EXISTS, AND WHAT THE MOST IMPORTANT CASE IS.
#
# `transcript-evidence.py` answers one question: did this session actually RUN
# the thing the PR body says it ran? It has exactly one way to be worthless —
# accepting the PR body as the evidence for itself. The body is composed inside
# the session, so it IS in the transcript, so a naive `grep 'go test'` succeeds
# for every claim including the false ones. It would pass 100% of the time,
# including on the runs it exists to catch.
#
# "the claim is not its own evidence" below is the case that proves it does not
# do that. It is the one to look at first if this suite is ever edited, and the
# CARRIER exclusion in the script is the thing it is testing.
#
# The rest divides the usual way: "found it" and "did not find it" and "could not
# look" are three outcomes, and the third must never be reported as either of the
# first two.
#
# Usage: .claude/hooks/transcript-evidence.test.sh   (exit 0 = all cases pass)

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
EVID="$HERE/transcript-evidence.py"
[ -f "$EVID" ] || { echo "not found: $EVID"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 is required"; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

passed=0
failed=0
OUT=""
RC=0

# --- transcripts -------------------------------------------------------------
# Written as real JSONL with real tool_use blocks, because a fixture that is not
# the shape of the thing tests nothing about the thing.
jsonl() { # jsonl <outfile> <bash-command>...
	python3 - "$@" <<'PY'
import json, sys
out = sys.argv[1]
with open(out, "w", encoding="utf-8") as fh:
    for i, cmd in enumerate(sys.argv[2:]):
        fh.write(json.dumps({
            "type": "assistant",
            "message": {"role": "assistant", "content": [
                {"type": "text", "text": "step %d" % i},
                {"type": "tool_use", "id": "t%d" % i, "name": "Bash",
                 "input": {"command": cmd}},
            ]},
        }) + "\n")
PY
}

T_RAN="$TMP/ran.jsonl"
jsonl "$T_RAN" 'git status' 'go test ./... -count=1' 'git add -A'

T_NOTHING="$TMP/nothing.jsonl"
jsonl "$T_NOTHING" 'git status' 'cat internal/handler.go' 'git add -A'

# The vacuity fixture: the ONLY mention of the command is inside the `gh` call
# that carries the claim about it.
T_CLAIM_ONLY="$TMP/claim-only.jsonl"
jsonl "$T_CLAIM_ONLY" 'git status' \
	'gh pr create --title x --body "## Verification
go test ./... -count=1 — 214 pass"'

# The claim moved out of the argument list and into a heredoc that writes the
# body file. Same circularity, one layer down — which is why CARRIER excludes the
# heredoc writers (cat/tee/printf) and not only `gh`.
T_BODY_FILE="$TMP/body-file.jsonl"
jsonl "$T_BODY_FILE" 'git status' \
	'cat > /tmp/body.md <<EOF
## Verification
go test ./... -count=1 — 214 pass
EOF' \
	'gh pr create --title x --body-file /tmp/body.md'

# BODY_FLAG, not CARRIER: an absolute path defeats CARRIER's `^\s*gh` anchor, so
# the --body flag is the thing that has to catch it.
T_PATHED_GH="$TMP/pathed-gh.jsonl"
jsonl "$T_PATHED_GH" 'git status' \
	'/usr/local/bin/gh pr edit 7 --body "ran go test ./... -count=1, all green"'

T_ECHOED="$TMP/echoed.jsonl"
jsonl "$T_ECHOED" 'echo "go test ./... -count=1" >> notes.md' 'cat notes.md'

T_COMMIT="$TMP/commit.jsonl"
jsonl "$T_COMMIT" 'git commit -m "ran go test ./... -count=1, all green"'

T_OTHER_TOOL="$TMP/other-tool.jsonl"
python3 - "$T_OTHER_TOOL" <<'PY'
import json, sys
# A tool_use block for a NON-Bash tool. Nothing was executed in a shell, so
# nothing here is evidence that a command ran.
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    fh.write(json.dumps({
        "type": "assistant",
        "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t0", "name": "Write",
             "input": {"file_path": "notes.md",
                       "content": "go test ./... -count=1 passes"}},
        ]},
    }) + "\n")
PY

T_MALFORMED="$TMP/malformed.jsonl"
printf 'not json at all\n{"message": null}\n[]\n' >"$T_MALFORMED"
# The real invocation, on a line the parser must reach despite the garbage above.
python3 - "$T_MALFORMED" <<'PY'
import json, sys
with open(sys.argv[1], "a", encoding="utf-8") as fh:
    fh.write(json.dumps({
        "type": "assistant",
        "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t9", "name": "Bash",
             "input": {"command": "go test ./... -count=1"}},
        ]},
    }) + "\n")
PY

# --- harness ------------------------------------------------------------------
run_evid() { OUT="$(python3 "$EVID" "$1" "$2" 2>&1)"; RC=$?; }

check() { # check <desc> <expected-rc>
	if [ "$RC" = "$2" ]; then
		passed=$((passed + 1)); printf 'PASS  %s (exit %s)\n' "$1" "$RC"
	else
		failed=$((failed + 1)); printf 'FAIL  %s — wanted exit %s, got %s\n' "$1" "$2" "$RC"
		printf '%s\n' "$OUT" | sed 's/^/        | /'
	fi
}

contains() { # contains <desc> <needle>
	case "$OUT" in
	*"$2"*) passed=$((passed + 1)); printf 'PASS  %s\n' "$1" ;;
	*) failed=$((failed + 1)); printf 'FAIL  %s — output lacked %s\n' "$1" "$2"
	   printf '%s\n' "$OUT" | sed 's/^/        | /' ;;
	esac
}

echo "=== the case this file exists for: a claim is not its own evidence ==="

run_evid "$T_CLAIM_ONLY" 'go[[:space:]]+test'
check "a gh pr create carrying the claim is NOT evidence" 1

run_evid "$T_BODY_FILE" 'go[[:space:]]+test'
check "a heredoc that writes the claim into a body file is NOT evidence" 1

run_evid "$T_PATHED_GH" 'go[[:space:]]+test'
check "a path-prefixed gh --body still carries a claim, not evidence" 1

run_evid "$T_ECHOED" 'go[[:space:]]+test'
check "an echo/cat of the command is NOT evidence" 1

run_evid "$T_COMMIT" 'go[[:space:]]+test'
check "a git commit message quoting the command is NOT evidence" 1

run_evid "$T_OTHER_TOOL" 'go[[:space:]]+test'
check "a non-Bash tool call mentioning the command is NOT evidence" 1

echo
echo "=== and it still finds a real invocation, or the whole thing is a no-op ==="

run_evid "$T_RAN" 'go[[:space:]]+test'
check "found in a transcript that really ran it" 0
contains "and prints the command it found" "go test ./..."

run_evid "$T_MALFORMED" 'go[[:space:]]+test'
check "unparseable lines are skipped, not fatal — the real invocation is still found" 0

echo
echo "=== three outcomes, and 'could not look' is not one of the other two ==="

run_evid "$T_NOTHING" 'go[[:space:]]+test'
check "absent from a transcript that did not run it — a FINDING, exit 1" 1

run_evid "$TMP/no-such-file.jsonl" 'go[[:space:]]+test'
check "unreadable transcript is exit 2, distinct from 'not found'" 2
contains "and says it could not read it" "cannot read"

echo
echo "=== two engines, one regex: POSIX classes must be translated, not tolerated ==="

# The caller hands the SAME pattern to `grep -E` and to this script. Python's
# `re` reads [[:space:]] as a nested character set and matches something else
# entirely. Untranslated, the lookup silently finds nothing and every claim is
# refused — fail-closed, survivable, and still a check examining the wrong thing.
run_evid "$T_RAN" 'go[[:space:]]+test[[:space:]]+\./\.\.\.'
check "a POSIX class deeper in the pattern still matches a real invocation" 0

run_evid "$T_RAN" 'go[[:blank:]]+test'
check "[[:blank:]] is translated too" 0

run_evid "$T_RAN" 'go[[:nosuchclass:]]+test'
check "an unknown POSIX class is a bad regex (exit 2), never a silent no-match" 2
contains "and names the class it did not know" "nosuchclass"

echo
echo "=== usage ==="

OUT="$(python3 "$EVID" "$T_RAN" 2>&1)"; RC=$?
check "too few arguments is a usage error, exit 2" 2

echo
printf '=== %s passed, %s failed ===\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
