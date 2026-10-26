#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# PreToolUse hook: an agent may not weaken the suite it was sent to satisfy.
#
# WHY THIS EXISTS.
#
# The test that existed before the fix, and could not be rewritten, is the proof
# the bug is gone. An agent told "make this pass" has two ways to make it pass,
# and only one of them is the job. Deleting the assertion is faster, produces a
# green build, and is invisible in a diff nobody reads closely. The adjacent
# version of this has already been paid for elsewhere: on one project thirty-five
# database tests skipped themselves on an unset environment variable for weeks
# while every job stayed green, because "did not run" and "passed" printed the
# same.
#
# WHAT IT CHECKS — deliberately narrow, because a guard that blocks legitimate
# work gets switched off, and a switched-off guard is worse than no guard.
#
# It fires on exactly four shapes, and only against a test file that ALREADY
# EXISTS on disk:
#
#   1. An Edit / MultiEdit whose new text contains FEWER assertions than the old
#      text it replaces. Removing assertions from a test is the whole defect.
#   2. A Write over an existing test file whose new content contains fewer
#      assertions than the file on disk. Same defect, different tool.
#   3. Either of the above INTRODUCING a skip/ignore marker (`t.Skip`,
#      `@Ignore`, `@Disabled`, `XCTSkip`, `.skip(`, `xit(`) that was not there.
#      Disabling a test is deleting it with extra steps.
#   4. A Bash command that deletes or truncates an existing test file
#      (`rm`, `shred`, `truncate`, `sed -i`, a `>`/`>>`/`tee` redirect onto it).
#      Without this the hook is evaded by the very tool an agent is nudged
#      toward using for edits.
#
# WHAT IS CONFIGURED, AND WHERE. Everything language-shaped — what counts as a
# test file, what counts as an assertion, what counts as disabling a test, and
# which ticket keys open the bypass — lives in `.factory/test-vocabulary.conf`.
# That file is gate config and is on the read-only list in
# `docs/AGENT-GUARDRAILS.md`: widening the test-path patterns or narrowing the
# assertion vocabulary makes this hook quieter without anybody deciding to make
# it quieter.
#
# A MISSING CONFIG BLOCKS, and the distinction is worth stating because this
# directory's standing rule is "not-configured allows". For THIS hook,
# "not configured" is a repo whose files do not match the test vocabulary — and
# that case already allows, silently, on every write. A missing or degenerate
# `test-vocabulary.conf` is something else: this hook only ever runs because
# `.claude/settings.json` wires it, so its own config being gone is a BROKEN
# INSTALL, and a broken guard that waves everything through is the defect the
# whole directory exists to refuse.
#
# WHAT IT DELIBERATELY DOES NOT CATCH, stated plainly rather than implied:
#
#   * An assertion rewritten to be trivially true while the COUNT stays the same
#     (`assertEquals(want, got)` -> `assertEquals(got, got)`). Counting is a
#     cheap proxy; it is not semantic analysis, and pretending otherwise would be
#     an overclaim.
#   * Creating a NEW test file, or adding to one. Always allowed, no exceptions.
#   * Renaming or `git mv`-ing a test file. `mv` is left out on purpose: a rename
#     is the common legitimate case and blocking it would earn this hook a
#     deletion.
#   * Weakening the CODE UNDER TEST so the assertion passes vacuously. Out of
#     reach of any pre-action check.
#   * Anything written by a program the hook cannot read (a python script that
#     opens the file, a `git checkout` of an old revision).
#   * A Bash path made relative to a DIFFERENT directory: `cd sub && rm
#     pkg/x_test.go`. The Bash rule resolves tokens against the session's repo
#     root and requires the file to exist there, so a token relative to a
#     `cd`-ed directory resolves to nothing and is waved through. Stated rather
#     than papered over: parsing `cd` out of an arbitrary compound command is a
#     rabbit hole, and a hook that guessed would be worse than one that says
#     where it stops.
#
# THE ROUTE TO APPROVAL. A test genuinely does become obsolete. When it has:
#
#     ALLOW_TEST_WEAKENING=<ticket> claude ...
#
# with a real ticket key (see TICKET_RE in the config). The bypass is not
# silent — the hook tells the model, in the same breath, that the PR body must
# say which test was removed and why.
#
# Exit: 0 = allowed, 2 = blocked (the only code that blocks).

set -uo pipefail
# shellcheck source=/dev/null
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

hook_init

TOOL="$(hook_field tool_name)"
ROOT="$(hook_repo_root)"

# --- the vocabulary, from gate config --------------------------------------
# Read, never hard-coded here: see the header, and .factory/test-vocabulary.conf.
CONFIG_REL=".factory/test-vocabulary.conf"

config_missing() { # config_missing <what-went-wrong>
	hook_block \
		"BLOCKED by .claude/hooks/block-test-weakening.sh — it cannot check this call." \
		"" \
		"  $1" \
		"  expected: <repo root>/$CONFIG_REL" \
		"" \
		"WHY THIS BLOCKS RATHER THAN ALLOWS. This hook runs only because" \
		".claude/settings.json wires it, so its own config being absent or empty is a" \
		"BROKEN INSTALL, not an unconfigured repo. A guard that cannot examine its" \
		"subject must refuse; one that waves the call through is indistinguishable" \
		"from one that looked and found nothing wrong." \
		"" \
		"ROUTE TO APPROVAL — pick one:" \
		"  1. Restore $CONFIG_REL from the new-project seed and prune it to the" \
		"     languages this repo actually uses." \
		"  2. If this repo deliberately has no test-weakening control, remove the" \
		"     hook from .claude/settings.json and say so in your PR. Deleting the" \
		"     config while leaving the hook wired is the one option that is not open." \
		"" \
		"Do not work around this by editing the config to match your change."

}

TEST_NAME_RE=""; TEST_BASENAME_RE=""; TEST_DIR_RE=""
ASSERT_RE=""; SHELL_ASSERT_RE=""; SKIP_RE=""; TICKET_RE=""

load_vocabulary() { # load_vocabulary <repo-root>
	local cfg="$1/$CONFIG_REL"
	[ -f "$cfg" ] || config_missing "the test vocabulary this hook reads is not there."
	# shellcheck source=/dev/null
	. "$cfg" || config_missing "$CONFIG_REL could not be sourced (a bash syntax error?)."

	# A vocabulary that matches nothing is a hook that examines nothing. Both of
	# the halves below are load bearing on their own, so both are asserted.
	[ -n "$TEST_NAME_RE$TEST_BASENAME_RE$TEST_DIR_RE" ] || config_missing \
		"$CONFIG_REL defines no test-path patterns, so NO file counts as a test."
	[ -n "$ASSERT_RE$SHELL_ASSERT_RE" ] || config_missing \
		"$CONFIG_REL defines no assertion vocabulary, so NO edit can reduce a count."
	[ -n "$SKIP_RE" ] || config_missing \
		"$CONFIG_REL defines no skip markers, so disabling a test would be invisible."
	[ -n "$TICKET_RE" ] || config_missing \
		"$CONFIG_REL defines no TICKET_RE, so the bypass could not be validated."
}

is_test_path() { # is_test_path <repo-relative-path>
	local p="$1"
	[ -n "$p" ] || return 1
	[ -n "$TEST_NAME_RE" ] && grep -qE "$TEST_NAME_RE" <<<"$p" && return 0
	[ -n "$TEST_BASENAME_RE" ] && grep -qE "$TEST_BASENAME_RE" <<<"$p" && return 0
	[ -n "$TEST_DIR_RE" ] && grep -qE "$TEST_DIR_RE" <<<"$p" && return 0
	return 1
}

# --- counting ---------------------------------------------------------------
count_re() { # count_re <file> <extended-regex>  -> occurrences
	local n
	[ -n "$2" ] || { printf '0'; return; }
	n="$(grep -oE "$2" "$1" 2>/dev/null | wc -l | tr -d ' ')"
	printf '%s' "${n:-0}"
}

count_lines_re() { # count_lines_re <file> <extended-regex>  -> matching lines
	local n
	[ -n "$2" ] || { printf '0'; return; }
	n="$(grep -cE "$2" "$1" 2>/dev/null || true)"
	printf '%s' "${n:-0}"
}

assert_count() { # assert_count <file>
	local a b
	a="$(count_re "$1" "$ASSERT_RE")"
	b="$(count_lines_re "$1" "$SHELL_ASSERT_RE")"
	printf '%s' "$(( a + b ))"
}

skip_count() { count_re "$1" "$SKIP_RE"; }

# --- the bypass -------------------------------------------------------------
bypass_ticket() {
	local v="${ALLOW_TEST_WEAKENING:-}"
	[ -n "$v" ] || return 1
	grep -qE "$TICKET_RE" <<<"$v" || return 1
	printf '%s' "$v"
}

allow_with_bypass() { # allow_with_bypass <path> <what>
	local t
	t="$(bypass_ticket)" || return 1
	hook_note \
		"NOTE from .claude/hooks/block-test-weakening.sh: this change $2 in $1." \
		"It was allowed only because ALLOW_TEST_WEAKENING=$t is set." \
		"You now OWE the PR body an explicit line naming the test you removed or" \
		"disabled and why it is obsolete. docs/STORY-CONTRACT.md treats an" \
		"unexplained assertion count drop as an incomplete Verification section."
}

refuse() { # refuse <path> <headline> <detail>...
	local path="$1" headline="$2"
	shift 2
	hook_block \
		"BLOCKED by .claude/hooks/block-test-weakening.sh" \
		"" \
		"  $headline" \
		"  file: $path" \
		"$@" \
		"" \
		"WHY. The test that existed before your fix, and could not be rewritten, is" \
		"the proof the bug is gone. Making the assertion go away makes the build" \
		"green without making the product correct." \
		"" \
		"ROUTE TO APPROVAL — pick one:" \
		"  1. Fix the code under test instead. This is almost always the answer." \
		"  2. If the test is genuinely obsolete, re-run with" \
		"     ALLOW_TEST_WEAKENING=<a ticket key> set, and say in the PR body" \
		"     which assertion you removed and why." \
		"  3. If you believe this hook is wrong about your edit, say so in the PR" \
		"     body rather than deleting the hook or widening its config."
}

# --- load the vocabulary ----------------------------------------------------
# Deliberately AFTER the definitions above: bash resolves a function at call
# time, not at parse time, so calling load_vocabulary before this point is a
# "command not found" that exits 127 — an exit code that does NOT block, which
# would turn this hook into one that allows everything and says nothing.
#
# Outside a git worktree there is no repo-relative path to key anything on, and
# nothing below can run. Allow, and do not demand a config that has no home.
[ -n "$ROOT" ] || hook_allow
load_vocabulary "$ROOT"

# ===========================================================================
# Bash: deletion / truncation of an existing test file
# ===========================================================================
if [ "$TOOL" = "Bash" ]; then
	CMD="$(hook_field command)"
	[ -n "$CMD" ] || hook_allow
	[ -n "$ROOT" ] || hook_allow

	# Candidate tokens: anything in the command that LOOKS like a test path and
	# actually exists. Both conditions matter — "exists" is what keeps this off
	# build artefacts like build/test-results/, which are not tracked files.
	TOKENS="$(printf '%s' "$CMD" | tr '\047"`;&|()<>$ \t\n' '\n' | sort -u)"
	while IFS= read -r tok; do
		[ -n "$tok" ] || continue
		rel="$(hook_relpath "$tok" "$ROOT")"
		[ -n "$rel" ] || continue
		is_test_path "$rel" || continue
		[ -f "$ROOT/$rel" ] || continue

		esc="$(printf '%s' "$tok" | sed 's/[][\.*^$(){}?+|/]/\\&/g')"
		verb=""
		# A redirect or tee ONTO the file — the token must be the target.
		if grep -qE "(>>?[[:space:]]*|tee[[:space:]]+(-[^[:space:]]+[[:space:]]+)*)$esc([[:space:]]|$)" <<<"$CMD"; then
			verb="truncated by a shell redirect"
		# rm / shred / truncate anywhere in the same command segment.
		elif grep -qE "(^|[^[:alnum:]_-])(rm|shred|truncate)([^[:alnum:]_-][^;&|]*)?$esc" <<<"$CMD"; then
			verb="deleted or truncated"
		# in-place sed.
		elif grep -qE "(^|[^[:alnum:]_-])sed([^;&|]*)-i([^;&|]*)$esc" <<<"$CMD"; then
			verb="rewritten in place by sed -i"
		fi
		[ -n "$verb" ] || continue

		allow_with_bypass "$rel" "$verb an existing test file" && exit 0
		refuse "$rel" "This Bash command would have $verb an existing test file." \
			"  command: $CMD"
	done <<<"$TOKENS"
	hook_allow
fi

# ===========================================================================
# Edit / Write / MultiEdit / NotebookEdit
# ===========================================================================
FILE="$(hook_field file_path)"
[ -n "$FILE" ] || hook_allow
[ -n "$ROOT" ] || hook_allow

REL="$(hook_relpath "$FILE" "$ROOT")"
[ -n "$REL" ] || hook_allow
is_test_path "$REL" || hook_allow

ABS="$ROOT/$REL"
# A file that does not exist yet cannot be weakened — writing a new test is
# always allowed, and this is the branch that keeps the hook off normal work.
[ -f "$ABS" ] || hook_allow

OLD="$P/old_text"
NEW="$P/new_text"

# Write replaces the whole file, so its "old side" is the file on disk. Edit and
# MultiEdit carry their own old side in the payload.
if [ "$TOOL" = "Write" ]; then
	OLD="$ABS"
fi

old_a="$(assert_count "$OLD")"
new_a="$(assert_count "$NEW")"
old_s="$(skip_count "$OLD")"
new_s="$(skip_count "$NEW")"

if [ "$new_s" -gt "$old_s" ]; then
	allow_with_bypass "$REL" "adds a skip/ignore marker" && exit 0
	refuse "$REL" "This change ADDS a skip/ignore marker to an existing test file." \
		"  skip markers before: $old_s   after: $new_s"
fi

if [ "$new_a" -lt "$old_a" ]; then
	allow_with_bypass "$REL" "removes $(( old_a - new_a )) assertion(s)" && exit 0
	refuse "$REL" "This change REMOVES assertions from an existing test file." \
		"  assertions in the text being replaced: $old_a" \
		"  assertions in the text replacing it:   $new_a"
fi

hook_allow
