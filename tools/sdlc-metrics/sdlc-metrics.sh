#!/usr/bin/env bash
# sdlc-metrics.sh — launcher for the sdlc-metrics collector beside it.
#
# ============================================================================
# WHAT IT REFUSES TO DO, AND WHY EACH REFUSAL IS A HARD FAILURE
# ============================================================================
#
# Every one of these could be a warning-and-continue, and every one of them
# would then be a way for this to run, examine nothing, and report a reassuring
# answer.
#
#   NO GO TOOLCHAIN         exit 2. A check that silently does not run is
#                           indistinguishable from a check that passed.
#   TOOL NOT WHERE EXPECTED exit 2. Same reason.
#   BUILD FAILS             exit 2. Same reason.
#   NO GH_TOKEN             exit 1, from the tool. A missing token is not a
#                           degraded measurement; it is no measurement, and an
#                           empty window would read as a quiet fortnight.
#   NOTHING EXAMINED        exit 3, from the tool. The vacuity guard. No
#                           document is written at all, so nothing downstream
#                           can consume a metrics.json full of zeroes.
#
# The ONE thing that is deliberately NOT a failure is an unconfigured publish
# destination: it is announced, recorded as `not_configured`, and the
# measurement — which is the deliverable — is produced anyway. See SCHEMA.md §6.
#
# ============================================================================
# USAGE
# ============================================================================
#
#   tools/sdlc-metrics/sdlc-metrics.sh --repo owner/name
#   tools/sdlc-metrics/sdlc-metrics.sh --repo owner/name --window-days 7
#   tools/sdlc-metrics/sdlc-metrics.sh --self-test        # the tool's own suite
#
# Any other flag is passed straight through; see SCHEMA.md §10 for every
# repository-shaped knob, and `go run . -h` in this directory for the rest.
#
# BEFORE THIS IS USEFUL IN A NEW REPOSITORY, read SCHEMA.md §0. In short:
# GH_TOKEN, --defect-labels, --class-label-prefixes, --surface-depth2-roots and
# --review-excludes-author all describe YOUR repository and the defaults do not.
#
# Environment:
#   GH_TOKEN / GITHUB_TOKEN   required for a live fetch
#   NOTION_API_TOKEN          optional; absent is announced, never silent
#   NOTION_DATABASE_ID        optional; same
#   SDLC_METRICS_REPO         default for --repo
#
# Exit codes: 0 measured · 1 run-time failure · 2 refused to run (no toolchain,
#             tool missing, build failed) · 3 vacuity guard: nothing examined.
set -uo pipefail

die() { echo "::error::sdlc-metrics: $*" >&2; exit 2; }

TOOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || die "could not locate this script's own directory."

[ -f "$TOOL_DIR/go.mod" ] || die "$TOOL_DIR/go.mod is missing — the collector is not beside this launcher. Refusing rather than reporting a clean run over nothing."

command -v go >/dev/null 2>&1 || die "the Go toolchain is not on PATH, so the metrics cannot be computed. This is a hard failure on purpose: a check that silently does not run is indistinguishable from a check that passed."

# --self-test runs the tool's own unit tests. -count=1 is not optional:
# `ok (cached)` hides a real failure behind a previous run's success.
if [ "${1:-}" = "--self-test" ]; then
  cd "$TOOL_DIR" || die "could not enter $TOOL_DIR"
  echo "== gofmt =="
  fmt_out="$(gofmt -l .)"
  if [ -n "$fmt_out" ]; then
    echo "$fmt_out"
    die "the above files are not gofmt-clean."
  fi
  echo "== go vet =="
  go vet ./... || die "go vet failed."
  echo "== go test -count=1 =="
  go test -count=1 ./... || exit 1
  exit 0
fi

# Built, not `go run`: a caller may invoke this repeatedly and `go run`
# re-links every time. The binary is cached by the tool's own content.
stamp="$(cat "$TOOL_DIR"/*.go "$TOOL_DIR"/go.mod 2>/dev/null | cksum | tr -d ' \t')"
bin_dir="${TMPDIR:-/tmp}/sdlc-metrics-build"
bin="$bin_dir/sm-$stamp"
if [ ! -x "$bin" ]; then
  mkdir -p "$bin_dir" || die "could not create $bin_dir"
  ( cd "$TOOL_DIR" && go build -o "$bin" . ) >&2 || die "the collector failed to build."
fi

# --repo defaults to $SDLC_METRICS_REPO when the caller named neither a repo nor
# an input. Scanning the arguments rather than rewriting them keeps every other
# flag pass-through, so a new flag on the tool needs no edit here.
have_repo=0
have_input=0
for a in "$@"; do
  case "$a" in
    -repo|--repo|-repo=*|--repo=*) have_repo=1 ;;
    -input|--input|-input=*|--input=*) have_input=1 ;;
  esac
done

if [ "$have_repo" -eq 0 ] && [ "$have_input" -eq 0 ]; then
  if [ -n "${SDLC_METRICS_REPO:-}" ]; then
    set -- -repo "$SDLC_METRICS_REPO" "$@"
  else
    die "no repository to measure. Pass --repo owner/name, set SDLC_METRICS_REPO, or pass --input a saved dataset. Guessing one would measure the wrong thing and say nothing about it."
  fi
fi

"$bin" "$@"
rc=$?

# The exit code is the contract a calling workflow depends on, so it is passed
# through untouched and each value is named in the log rather than being left
# for somebody to look up.
case "$rc" in
  0) ;;
  3) echo "::error::sdlc-metrics: REFUSED (exit 3) — the run examined nothing, so no document was written. A row of zeroes is indistinguishable from a broken query and is not an acceptable substitute. Check --window-days and the token's scope." >&2 ;;
  2) echo "::error::sdlc-metrics: usage error (exit 2)." >&2 ;;
  *) echo "::error::sdlc-metrics: failed (exit $rc)." >&2 ;;
esac
exit "$rc"
