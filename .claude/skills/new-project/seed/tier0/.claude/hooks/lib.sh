#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# Shared plumbing for the PreToolUse hooks in this directory.
#
# Source it, do not execute it.
#
# THE ONE RULE THIS FILE ENFORCES: a hook that cannot examine its input must
# BLOCK, never allow. On the project this came from, an overnight audit found
# four guards at once that ran, examined nothing, and reported the reassuring
# answer — one of them existed only because "SKIPPED" and "passed" printed the
# same. A hook that fails open is that defect wearing a new name, so every error
# path below exits 2 (block) with a message that says what went wrong and how to
# proceed.
#
# THE FOUR INVARIANTS every hook in this directory obeys:
#
#   * Blocking is exit 2, and nothing else blocks. stderr is what the model sees.
#   * Cannot-check REFUSES. An unparseable payload, a missing python3, an
#     unreadable transcript: block, loudly, with a reason. "Could not look" must
#     never print the same as "looked and found nothing".
#   * Not-configured ALLOWS — and must never print the same as broken. A repo
#     that does not have a given control lets every write through silently. That
#     is the opposite outcome from broken, on purpose.
#   * Every block states a ROUTE TO APPROVAL, not just a refusal. A refusal with
#     no next step gets the hook deleted.

# ---------------------------------------------------------------------------
# hook_block <line>...    refuse the tool call. Exit 2 is the ONLY exit code
#                         that blocks; stderr is what the model is shown.
# ---------------------------------------------------------------------------
hook_block() {
	printf '%s\n' "$@" >&2
	exit 2
}

# ---------------------------------------------------------------------------
# hook_note <line>...     let the call through, but put a line in front of the
#                         model. Uses the documented PreToolUse JSON form so the
#                         text is actually delivered rather than swallowed.
# ---------------------------------------------------------------------------
hook_note() {
	local text
	text="$(printf '%s\n' "$@")"
	python3 - "$text" <<'PY'
import json, sys
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": sys.argv[1],
    }
}))
PY
	exit 0
}

# ---------------------------------------------------------------------------
# hook_allow              let the call through silently.
# ---------------------------------------------------------------------------
hook_allow() { exit 0; }

# ---------------------------------------------------------------------------
# hook_init               read the payload from stdin into $P (a temp dir with
#                         one file per field — see payload.py). Sets $HOOK_DIR.
#                         Registers the cleanup trap.
# ---------------------------------------------------------------------------
hook_init() {
	HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
	command -v python3 >/dev/null 2>&1 || hook_block \
		"BLOCKED by .claude/hooks — python3 is not on PATH, so the pre-action hooks" \
		"cannot read their own payload and cannot vouch for this call." \
		"" \
		"Route: install python3, or remove the \"hooks\" key from .claude/settings.json" \
		"deliberately and say so in your PR. Do not work around this silently."

	P="$(mktemp -d)" || hook_block "BLOCKED by .claude/hooks — mktemp failed; the hook cannot stage its input."
	# shellcheck disable=SC2064
	trap "rm -rf '$P'" EXIT

	if ! python3 "$HOOK_DIR/payload.py" "$P"; then
		hook_block \
			"BLOCKED by .claude/hooks — the PreToolUse payload could not be parsed (see above)." \
			"A hook that cannot read the action it is guarding refuses it; it does not guess." \
			"" \
			"Route: this is a harness/plumbing fault, not a policy one. Report it to whoever" \
			"owns .claude/hooks/ in this repo, and say what tool call triggered it."
	fi
}

# ---------------------------------------------------------------------------
# hook_field <name>       print one payload field. Always succeeds; a field the
#                         payload did not carry is the empty string.
# ---------------------------------------------------------------------------
hook_field() { cat "$P/$1" 2>/dev/null || true; }

# ---------------------------------------------------------------------------
# hook_repo_root          the git top-level for the session's cwd, or "" if the
#                         session is not in a git worktree.
# ---------------------------------------------------------------------------
hook_repo_root() {
	local cwd
	cwd="$(hook_field cwd)"
	[ -n "$cwd" ] || cwd="$PWD"
	[ -d "$cwd" ] || return 0
	git -C "$cwd" rev-parse --show-toplevel 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# hook_relpath <abs-or-rel> <root>
#     Repo-relative form of a path, keyed exactly the way
#     scripts/story-lease.sh keys a lease. Prints nothing when the path is
#     outside <root> — callers treat "no answer" as "not my business".
# ---------------------------------------------------------------------------
hook_relpath() {
	local raw="$1" root="$2" abs
	[ -n "$raw" ] || return 0
	[ -n "$root" ] || return 0
	case "$raw" in
	/*) abs="$raw" ;;
	*) abs="$root/$raw" ;;
	esac
	# Collapse . and .. textually — the target may not exist yet (a new file),
	# so realpath -e is not usable and realpath -m is not portable enough.
	abs="$(printf '%s' "$abs" | awk -F/ '{
		n=0
		for (i = 1; i <= NF; i++) {
			if ($i == "" || $i == ".") continue
			if ($i == "..") { if (n > 0) n--; continue }
			stack[++n] = $i
		}
		out = ""
		for (i = 1; i <= n; i++) out = out "/" stack[i]
		print out
	}')"
	case "$abs" in
	"$root"/*) printf '%s' "${abs#"$root"/}" ;;
	*) return 0 ;;
	esac
}
