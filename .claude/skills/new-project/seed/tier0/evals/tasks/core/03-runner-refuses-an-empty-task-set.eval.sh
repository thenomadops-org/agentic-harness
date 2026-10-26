#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# The suite must refuse to grade a run in which it examined nothing.
#
# An overnight audit on one project found FOUR gates passing while inspecting
# nothing, one of them reporting green on zero tests. That is the failure mode an
# eval suite is most exposed to, because a suite whose discovery glob stops
# matching prints no failures, and no failures reads as success on every CI badge
# ever made. A moved directory, a renamed extension, a `--tasks` typo in a
# workflow, a checkout that did not include `evals/` — each of them silently
# converts this suite into a green rubber stamp over an untested configuration.
#
# So: zero discovered tasks is exit 2 with a named reason, never exit 0. This
# task holds that guard down permanently, by running the real runner against a
# real empty directory on every single run.
#
# IT ASSERTS THE MESSAGE, NOT ONLY THE EXIT CODE. The runner has three separate
# vacuity guards and they all exit non-zero; an assertion on the code alone would
# stay green if this one were deleted and a different guard caught the fallout,
# which is how a specific check quietly turns into a general one.
# shellcheck source=../../lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

ID="runner-refuses-an-empty-task-set"
TITLE="A run that discovers zero tasks errors out; it never reports success"
PROVENANCE="an overnight audit found four gates passing while inspecting nothing, one green on zero tests (seen on one project, repeatedly)"

check() {
  local d out rc v n
  v="$(mktemp)"; n=1
  d="$(mktemp -d)"
  mkdir -p "$d/no-tasks-here"

  out="$(bash "$CORPUS/evals/run.sh" --tasks "$d/no-tasks-here" 2>&1)"
  rc=$?

  if [ "$rc" -eq 0 ]; then
    echo "the runner exited 0 on a task set of size zero — a vacuous run reported as a pass" >>"$v"
  elif [ "$rc" -ne 2 ]; then
    echo "expected exit 2 (vacuous run) but got exit $rc" >>"$v"
  fi
  if ! grep -q 'no eval tasks found' <<<"$out"; then
    echo "the refusal did not name its reason ('no eval tasks found'); got: $(head -3 <<<"$out" | tr '\n' ' ')" >>"$v"
  fi

  rm -rf "$d"
  report_violations "runner invocation over an empty task directory" "$n" "$v"
  rc=$?
  rm -f "$v"
  return $rc
}

break_it() {
  # Defeat exactly the discovery guard, leaving every other guard intact — the
  # realistic form of this regression is somebody "simplifying" one condition.
  sed -i 's/^if \[ "${#TASKS\[@\]}" -eq 0 \]; then$/if false; then/' "$CORPUS/evals/run.sh"
  grep -q 'if false; then' "$CORPUS/evals/run.sh"
}
