#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# runner-pinning-check.sh — every CI job must name a runner set that is on the list.
#
# ============================================================================
# WHY THIS EXISTS
# ============================================================================
#
# A bare `runs-on: self-hosted` is scheduled onto whichever registered runner is
# free. On one project's runner fleet that meant a Go job could land on
# chriss-macbook-pro-x64 or jennifers-macbook-air-arm64 — a different OS and a
# different architecture from the one the build was written for. The platform
# then decides for you, differently on different days, and the failure arrives as
# an unreproducible flake in somebody else's PR.
#
# `runs-on: ubuntu-latest` has the same shape with a slower fuse: "latest" is a
# moving image, so a build that is green today goes red on the morning GitHub
# rolls the label forward, in a PR that changed nothing.
#
# The rule is therefore not "use self-hosted" or "use ubuntu"; it is **the set of
# runner labels a job may name is written down in this repo, and anything else is
# red**. That list is per-repo config (.factory/allowed-runners), never vendored —
# vendoring one repo's fleet into another is how a gate becomes decoration.
#
# ============================================================================
# WHY IT CANNOT PASS VACUOUSLY
# ============================================================================
#
#  1. ZERO WORKFLOW FILES IS AN ERROR (exit 3), not a pass. A guard that passes
#     on an empty set is the shell guard that "passed on nothing".
#  2. ZERO runs-on VALUES IS AN ERROR. If a parser regression stops the scanner
#     seeing its subjects, it would otherwise go green while checking nothing.
#  3. MISSING CONFIG IS AN ERROR (exit 2), never a skip.
#  4. AN UNREADABLE VALUE IS AN ERROR, not an assumption of compliance. See the
#     pinned gap below.
#
# ============================================================================
# THE PINNED GAP — read this before extending the script
# ============================================================================
#
# This script does NOT parse YAML. It reads two syntaxes exactly:
#
#     runs-on: <scalar>
#     runs-on: [a, b, c]        (inline flow sequence)
#
# Anything else — a block sequence over following lines, a `${{ }}` expression, a
# matrix reference — is reported as UNCLASSIFIABLE and fails the run. It is not
# skipped and not assumed compliant.
#
# That is deliberate, and it is the whole design. A regex over YAML that guesses
# at the shapes it does not know produces a narrower hole of the same shape as
# the one it fixed: green, and blind. The two honest outcomes are *parse it
# properly* or *pin the gap loudly*; there is no acceptable middle. If this repo
# grows block-sequence runs-on values, the fix is to add a real YAML parse — not
# to widen this regex.
#
# It also does not verify that every job HAS a runs-on: finding the set of jobs
# requires knowing the document structure. GitHub refuses to schedule a job with
# no runs-on, so that failure is loud on its own; the silent one is a runs-on
# that is present and wrong, which is what this checks.
#
# Usage:  scripts/runner-pinning-check.sh [WORKFLOW_DIR]
# Exit:   0 conformant · 1 a violation · 2 config error · 3 nothing to check

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WF_DIR="${1:-$ROOT/.github/workflows}"
ALLOW_FILE="${ALLOWED_RUNNERS_FILE:-$ROOT/.factory/allowed-runners}"

if [ ! -r "$ALLOW_FILE" ]; then
  echo "::error::runner-pinning-check is not configured — cannot read '$ALLOW_FILE'" >&2
  echo "          One allowed runs-on set per line, labels comma-separated, e.g.:" >&2
  echo "              ubuntu-24.04" >&2
  echo "              self-hosted,Linux,X64" >&2
  exit 2
fi

# Labels are compared as a SET: order in the workflow file must not decide the
# verdict, or the same fleet spelled two ways passes once and fails once.
normalise() {
  printf '%s' "$1" \
    | tr -d '"'"'"'[]' \
    | tr ',' '\n' \
    | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' \
    | grep -v '^$' \
    | sort \
    | paste -sd, -
}

allowed=""
n_allowed=0
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%%#*}"
  [ -z "${line//[[:space:]]/}" ] && continue
  allowed="${allowed}$(normalise "$line")"$'\n'
  n_allowed=$((n_allowed + 1))
done < "$ALLOW_FILE"

if [ "$n_allowed" -eq 0 ]; then
  echo "::error::runner-pinning-check: '$ALLOW_FILE' lists no runner sets" >&2
  exit 2
fi

if [ ! -d "$WF_DIR" ]; then
  echo "::error::runner-pinning-check: no workflow directory at '$WF_DIR'" >&2
  exit 3
fi

shopt -s nullglob
files=("$WF_DIR"/*.yml "$WF_DIR"/*.yaml)
shopt -u nullglob

if [ "${#files[@]}" -eq 0 ]; then
  echo "::error::runner-pinning-check: no workflow files in '$WF_DIR' — a guard that" >&2
  echo "          passes on an empty set has not checked anything" >&2
  exit 3
fi

seen=0
bad=0

for f in "${files[@]}"; do
  while IFS= read -r entry; do
    ln="${entry%%:*}"
    val="${entry#*:}"
    val="${val#*runs-on:}"
    val="$(printf '%s' "$val" | sed 's/#.*$//; s/^[[:space:]]*//; s/[[:space:]]*$//')"

    seen=$((seen + 1))

    # An empty value means a block sequence follows on the next lines. Not read.
    if [ -z "$val" ]; then
      echo "::error::UNCLASSIFIABLE  $f:$ln — runs-on has no inline value (block sequence?)." >&2
      echo "          This script reads scalars and inline [a, b] only, by design. Add a real" >&2
      echo "          YAML parse rather than widening the regex — see the header." >&2
      bad=$((bad + 1))
      continue
    fi

    case "$val" in
      *'${{'*)
        echo "::error::UNCLASSIFIABLE  $f:$ln — runs-on is an expression: $val" >&2
        echo "          The runner is then chosen at run time and this file cannot say by whom." >&2
        bad=$((bad + 1))
        continue
        ;;
    esac

    norm="$(normalise "$val")"
    if printf '%s' "$allowed" | grep -qxF -- "$norm"; then
      continue
    fi

    echo "::error::RUNNER-PINNING  $f:$ln — runs-on '$val' is not in $ALLOW_FILE" >&2
    echo "          Allowed sets: $(printf '%s' "$allowed" | paste -sd' | ' -)" >&2
    echo "          An unlisted or partial label set lets the platform pick the machine," >&2
    echo "          and it picks a different one on different days." >&2
    bad=$((bad + 1))
  done < <(grep -nE '^[[:space:]]*runs-on:' -- "$f")
done

# THE CENSUS. Every one of these is a non-zero fact about a repo that has CI. If
# a change to the scanner makes it stop seeing runs-on lines, this turns a
# silently-green run into a red one naming the counter that collapsed.
if [ "$seen" -eq 0 ]; then
  echo "::error::runner-pinning-check examined ${#files[@]} workflow file(s) and found ZERO" >&2
  echo "          runs-on values. Either no job is defined, or the scanner has stopped" >&2
  echo "          seeing its subjects. Both are failures, not passes." >&2
  exit 1
fi

if [ "$bad" -ne 0 ]; then
  echo "" >&2
  echo "runner-pinning-check FAILED — $bad of $seen runs-on value(s) across ${#files[@]} file(s)." >&2
  exit 1
fi

echo "runner-pinning-check PASSED — $seen runs-on value(s) in ${#files[@]} workflow file(s), all listed in $ALLOW_FILE."
