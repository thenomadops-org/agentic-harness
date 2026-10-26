#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# A command the instructions tell an agent to run must exist.
#
# The agent config is not prose, it is a set of instructions somebody will
# execute at 3am with no human watching. When it names `scripts/foo.sh` and that
# file has been renamed, the agent gets "No such file or directory" — and the
# recorded behaviour when that happens is not a clean stop. It is an agent
# deciding the step was optional, or reimplementing the guard itself in a
# throwaway one-liner that checks something adjacent, and then reporting the step
# as done. Both are how a repo produces a confident false success.
#
# A cited path that no longer exists is also the cheapest possible signal that
# the config has drifted from the tree, and drift is what every other failure
# this suite covers has in common.
#
# The tombstone rules in lib.sh matter here more than anywhere, in any repo that
# keeps its retirement notices in the files that used to depend on the retired
# thing.
# shellcheck source=../../lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

ID="cited-scripts-exist"
TITLE="Every script the agent config tells an agent to run is present in the tree"
PROVENANCE="config drift: instructions outlive the files they name, and an agent that cannot run a guard reports the step done anyway (seen on one project, repeatedly)"

check() {
  local v n rel p rc
  v="$(mktemp)"; n=0
  while IFS=$'\t' read -r rel p; do
    [ -n "$p" ] || continue
    n=$((n + 1))
    [ -e "$CORPUS/$p" ] || echo "$rel cites $p, which does not exist" >>"$v"
  done < <(scan_citations 'scripts/[A-Za-z0-9._-]+\.(sh|py)')

  report_violations "script citations in the agent config" "$n" "$v"
  rc=$?
  rm -f "$v"
  return $rc
}

break_it() {
  cat >>"$CORPUS/CLAUDE.md" <<'PROBE'

Before every commit, run `scripts/no-such-guard.sh` to check for a contended file.
PROBE
}
