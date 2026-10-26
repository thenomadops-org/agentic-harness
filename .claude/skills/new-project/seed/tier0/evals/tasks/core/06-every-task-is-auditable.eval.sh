#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# Every eval must say where it came from.
#
# The rule this suite is built on is that every incident becomes an eval. A task
# with no PROVENANCE cannot be audited against that rule: nobody reviewing it in
# six months can tell whether it encodes a failure this repo actually had or an
# opinion somebody held on a Tuesday, and the second kind is what makes a suite
# get switched off. The provenance line is also what tells a future reader
# whether a rule that has run out of subjects should be deleted or fought for.
#
# The runner already refuses a malformed task at load time. This task is the
# quality bar on top of the structural one: a provenance string long enough to
# name something, and the two functions every task must ship — a `check` and the
# `break_it` that proves the check can fail.
# shellcheck source=../../lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

ID="every-task-is-auditable"
TITLE="Every eval task declares an id, a title, a provenance, a check and a mutation"
PROVENANCE="the playbook rule that every incident becomes an eval — unauditable evals cannot be held to it (seen on one project, repeatedly)"

check() {
  local v n t rel rc meta
  v="$(mktemp)"; n=0
  while IFS= read -r t; do
    [ -n "$t" ] || continue
    n=$((n + 1))
    rel="${t#"$CORPUS"/}"
    meta="$(
      (
        ID=""; TITLE=""; PROVENANCE=""
        # shellcheck disable=SC1090
        . "$t" >/dev/null 2>&1
        printf '%s\n%s\n%s\n' "$ID" "$TITLE" "$PROVENANCE"
        declare -F check    >/dev/null && echo HAS_CHECK
        declare -F break_it >/dev/null && echo HAS_BREAK
      )
    )"
    [ -n "$(sed -n 1p <<<"$meta")" ] || echo "$rel has no ID" >>"$v"
    [ -n "$(sed -n 2p <<<"$meta")" ] || echo "$rel has no TITLE" >>"$v"
    if [ "$(printf '%s' "$(sed -n 3p <<<"$meta")" | wc -c)" -lt 20 ]; then
      echo "$rel has no usable PROVENANCE — name the failure or the work this came from" >>"$v"
    fi
    grep -q HAS_CHECK <<<"$meta" || echo "$rel defines no check()" >>"$v"
    grep -q HAS_BREAK <<<"$meta" || echo "$rel defines no break_it() — an unprovable check" >>"$v"
  done < <(find "$CORPUS/evals/tasks" -name '*.eval.sh' | sort)

  report_violations "eval task files" "$n" "$v"
  rc=$?
  rm -f "$v"
  return $rc
}

break_it() {
  mkdir -p "$CORPUS/evals/tasks/core"
  cat >"$CORPUS/evals/tasks/core/zz-probe-unauditable.eval.sh" <<'PROBE'
ID="probe-unauditable"
TITLE="fixture: a task with no provenance"
PROVENANCE=""
check()    { echo "SUBJECTS=1"; return 0; }
break_it() { :; }
PROBE
}
