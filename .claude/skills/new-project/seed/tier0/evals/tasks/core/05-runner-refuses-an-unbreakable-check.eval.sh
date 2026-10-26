#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# A check that cannot fail is not a check.
#
# The standing rule in docs/STORY-CONTRACT.md is "prove it by breaking": remove or invert the
# guard, watch it go red, restore it, watch it go green. The weakness of that
# rule is that it is proven ONCE, in the pull request that introduces the guard,
# and never again — it says the check worked on the day it was written and
# nothing about the day somebody loosens a regex to get their own change through.
#
# This runner makes the break permanent: every task ships a `break_it` mutation,
# the runner applies it to a throwaway copy of the corpus on EVERY run, and a
# check that stays green against a corpus corrupted in the shape it guards is
# reported as an ERROR — not a pass, and not a failure either, because the corpus
# is not what is wrong.
#
# This task guards that guard, with a fixture whose `break_it` deliberately does
# nothing. If the runner reports PASS on it, the break phase has stopped meaning
# anything and every other green tick in this suite is unverified.
# shellcheck source=../../lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

ID="runner-refuses-an-unbreakable-check"
TITLE="A check that stays green against a broken corpus is an error, never a pass"
PROVENANCE="the story contract's 'prove it by breaking'; four gates shipped unable to fail (seen on one project, repeatedly)"

check() {
  local d out rc v n
  v="$(mktemp)"; n=1
  d="$(mktemp -d)"
  mkdir -p "$d/tasks"

  cat >"$d/tasks/zz-fixture.eval.sh" <<'FIXTURE'
ID="fixture-cannot-fail"
TITLE="fixture: a check with a mutation that changes nothing"
PROVENANCE="fixture for evals/tasks/05"
check()    { echo "SUBJECTS=1"; return 0; }
break_it() { :; }
FIXTURE

  out="$(bash "$CORPUS/evals/run.sh" --tasks "$d/tasks" 2>&1)"
  rc=$?

  if [ "$rc" -eq 0 ]; then
    echo "the runner PASSED a check whose break_it changed nothing — the break phase is not enforcing" >>"$v"
  fi
  if ! grep -q 'stayed GREEN' <<<"$out"; then
    echo "the runner did not name the unbreakable check as the reason; got: $(head -5 <<<"$out" | tr '\n' ' ')" >>"$v"
  fi

  rm -rf "$d"
  report_violations "runner invocation over a check that cannot fail" "$n" "$v"
  rc=$?
  rm -f "$v"
  return $rc
}

break_it() {
  sed -i 's/^    elif \[ "\$break_rc" -eq 0 \]; then$/    elif false; then/' "$CORPUS/evals/run.sh"
  grep -q '^    elif false; then' "$CORPUS/evals/run.sh"
}
