#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# The documents and workflows the config points an agent at must exist.
#
# Sibling of task 08, different subject and a different failure. A missing script
# fails loudly when it is run; a missing DOCUMENT fails silently, because nothing
# executes it. The agent is told "read docs/X.md before opening a PR", finds
# nothing there, and proceeds on whatever it already believed — which is exactly
# the state the document existed to correct. Nothing in the transcript records
# that the briefing was empty.
#
# `.github/workflows/*.yml` citations are in the same subject set because they
# are how the config tells an agent which gate will judge its change. A citation
# of a workflow that was renamed teaches an agent to wait for a check that will
# never report, or to believe a check exists that does not.
# shellcheck source=../../lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

ID="cited-workflows-and-docs-exist"
TITLE="Every doc and workflow the agent config cites is present in the tree"
PROVENANCE="a briefing that points at a missing document leaves the agent on its prior belief, silently (seen on one project, repeatedly)"

check() {
  local v n rel p rc
  v="$(mktemp)"; n=0
  while IFS=$'\t' read -r rel p; do
    [ -n "$p" ] || continue
    n=$((n + 1))
    [ -e "$CORPUS/$p" ] || echo "$rel cites $p, which does not exist" >>"$v"
  done < <(
    scan_citations 'docs/[A-Za-z0-9._/-]+\.md'
    scan_citations '\.github/workflows/[A-Za-z0-9._-]+\.ya?ml'
  )

  report_violations "doc and workflow citations in the agent config" "$n" "$v"
  rc=$?
  rm -f "$v"
  return $rc
}

break_it() {
  cat >>"$CORPUS/CLAUDE.md" <<'PROBE'

Read `docs/AGENT-EVAL-CONTRACT.md` before writing a story, and watch
`.github/workflows/agent-eval-nightly.yml` for the result.
PROBE
}
