#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# A check that examined nothing must ERROR, not pass.
#
# Task 03 covers the suite discovering no tasks. This one covers the subtler and
# far more likely case: the suite runs 24 tasks, all green, and one of them
# looked at zero things. That happens without anybody touching the check — the
# file it globbed gets renamed, the skill it guarded gets deleted, the section it
# parsed gets rewritten — and from the outside it is indistinguishable from a
# check that ran and found nothing wrong. Both print PASS.
#
# It is the same defect as a `grep` guard whose subject file was renamed: the
# guard survives, its subject does not, and the green tick now means "this rule
# has no subjects" while everyone reads it as "this rule holds".
#
# The cure is that a check must declare what it examined and the runner must
# refuse a zero. That makes a vanished subject set LOUD — it becomes an error
# demanding either the rule be deleted or the missing subject be explained —
# instead of a silent promotion to always-green.
# shellcheck source=../../lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

ID="runner-refuses-a-zero-subject-check"
TITLE="A check reporting SUBJECTS=0 is an error, never a pass"
PROVENANCE="four gates shipped passing while inspecting nothing; one reported green over zero tests (seen on one project, repeatedly)"

check() {
  local d out rc v n
  v="$(mktemp)"; n=1
  d="$(mktemp -d)"
  mkdir -p "$d/tasks"

  # A well-formed task in every respect except that it looks at nothing.
  cat >"$d/tasks/zz-fixture.eval.sh" <<'FIXTURE'
ID="fixture-examines-nothing"
TITLE="fixture: a check with an empty subject set"
PROVENANCE="fixture for evals/tasks/04"
check()    { echo "SUBJECTS=0"; [ -e "$CORPUS/EVAL_FIXTURE_BROKEN" ] && return 1; return 0; }
break_it() { touch "$CORPUS/EVAL_FIXTURE_BROKEN"; }
FIXTURE

  out="$(bash "$CORPUS/evals/run.sh" --tasks "$d/tasks" 2>&1)"
  rc=$?

  if [ "$rc" -eq 0 ]; then
    echo "the runner PASSED a check that declared SUBJECTS=0 — vacuity reported as success" >>"$v"
  fi
  if ! grep -q 'SUBJECTS=0' <<<"$out"; then
    echo "the runner did not name zero subjects as the reason; got: $(head -5 <<<"$out" | tr '\n' ' ')" >>"$v"
  fi

  rm -rf "$d"
  report_violations "runner invocation over a check that examines nothing" "$n" "$v"
  rc=$?
  rm -f "$v"
  return $rc
}

break_it() {
  sed -i 's/^  if \[ "\$subj" -eq 0 \]; then$/  if false; then/' "$CORPUS/evals/run.sh"
  grep -q '^  if false; then' "$CORPUS/evals/run.sh"
}
