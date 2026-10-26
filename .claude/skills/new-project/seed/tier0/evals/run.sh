#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# Eval runner for the agent configuration corpus (CLAUDE.md + .claude/**).
#
# WHY THIS EXISTS. A repo accumulates tests over its code and, usually, none at
# all over the configuration that steers its agents — `CLAUDE.md` and the skills
# in `.claude/skills/`. That configuration is the only thing every agent reads
# before it reads a line of the codebase, and every failure this suite was seeded
# from was a *configuration* defect that produced a confident false success, not
# a code defect. From one project, in one month:
#
#   * two skills named a tracker project that did not exist, so their duplicate
#     search returned `[]` every time either was ever run — a machine answering
#     "no duplicate exists" to every question, one of them on the path of every
#     unit of work and the other at nine-agent dispatch scale;
#   * `CLAUDE.md` stated the auth gate order wrong for months, and two other
#     documents agreed with it;
#   * an overnight audit found four gates passing while inspecting nothing;
#   * a coordinator told a dozen agents that the PR-body gate rejects closing
#     keywords, which is not what it does;
#   * three of four agents skipped their test suites and reported source-reading
#     as verification.
#
# THE TRAP THIS RUNNER EXISTS TO REFUSE. An eval that passes while examining
# nothing is worse than no eval, because it converts an unexamined subject into a
# green check. That is the exact defect four gates in this repo already shipped
# with, and it is why this runner does three things no ordinary test harness
# does:
#
#   1. ZERO TASKS IS AN ERROR (exit 2), never a pass. A suite that discovered no
#      tasks has not tested anything, and "0 failures" is the most reassuring
#      possible way to say so.
#   2. EVERY CHECK DECLARES ITS SUBJECT COUNT. A check must print `SUBJECTS=<n>`
#      naming how many things it actually looked at. `SUBJECTS=0` is an ERROR,
#      not a pass — a rule whose subject set is empty is green by vacuity, which
#      is how a check survives the deletion of the very thing it guarded.
#   3. EVERY CHECK IS BROKEN ON EVERY RUN. Each task ships a `break_it` mutation.
#      The runner copies the corpus to a scratch directory, applies the mutation
#      there, re-runs the check, and requires it to go RED. A check that stays
#      green against a corpus deliberately corrupted in the shape it guards is
#      reported as an ERROR and fails the suite. This is the story contract's
#      "prove it by breaking" made automatic and permanent instead of a one-off
#      screenshot in the PR that introduced it.
#
# ERRORS ARE NOT FAILURES, and the difference is load-bearing. A FAIL means the
# corpus is wrong — the check worked and found something. An ERROR means the
# CHECK is wrong: it examined nothing, or it could not be made to fail, or it did
# not declare what it looked at. The pass-rate threshold applies to FAILs only;
# any ERROR fails the run outright, whatever the threshold is set to. Otherwise
# the threshold becomes a supported way to ship a vacuous check.
#
# WHAT A TASK LOOKS LIKE. `evals/tasks/*.eval.sh`, sourced by this runner:
#
#     ID="a-stable-slug"
#     TITLE="one line: the acceptable outcome"
#     PROVENANCE="the real failure or work this came from"
#     check()    { ... ; echo "SUBJECTS=$n" ; return 0|1 ; }
#     break_it() { ... mutate "$CORPUS" ... }
#
# `check` reads the corpus through `$CORPUS` and only through `$CORPUS`: in the
# live phase that is the repo root, and in the break phase it is a disposable
# copy. A check that reaches around it with a hard-coded repo path would be
# mutating the developer's checkout, and would also be unbreakable.
#
# Usage:
#   evals/run.sh                        # live + break phases, all tasks
#   evals/run.sh --only <id-substring>  # one task (or a few)
#   evals/run.sh --tasks DIR            # a different task tree (searched recursively)
#   evals/run.sh --json FILE            # machine-readable results
#   evals/run.sh --no-break             # DEBUG ONLY: skips the break phase, and
#                                       # says so loudly; never use it in CI.
#   EVAL_PASS_THRESHOLD=100 evals/run.sh
#
# Exit: 0 pass · 1 below threshold, or any ERROR · 2 vacuous run / usage error.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"

TASKS_DIR="$HERE/tasks"
ONLY=""
JSON_OUT=""
DO_BREAK=1
THRESHOLD="${EVAL_PASS_THRESHOLD:-100}"

# The corpus is these paths and nothing else. `check` bodies read them under
# $CORPUS; the break phase copies exactly this list. Keep it explicit: a copy
# that silently includes the whole repo makes the break phase slow, and a copy
# that silently omits a path makes every task that reads it error out for a
# reason that has nothing to do with the task.
# `evals` is in the list because three tasks assert on the runner's OWN refusal
# behaviour (vacuous task set, zero-subject check, unbreakable check) and their
# break_it mutations remove those guards from the COPY to prove each one is load
# bearing. Without the copy they would have to mutate the real runner.
#
# ADD YOUR GROUND TRUTH HERE. The highest-value tasks compare what the
# instructions CLAIM against what the code actually does — not against another
# document. On the project this came from, `CLAUDE.md` stated the auth gate order
# wrong for months and two other documents agreed with it; the check that would
# have caught it reads the one source file that enforces the order. A
# doc-to-doc citation chain proves nothing when all the docs agree and are all
# wrong. So when you write a task like that, append the file it reads as ground
# truth to this list, in `tasks/local/`.
CORPUS_PATHS=(CLAUDE.md .claude .github docs scripts evals)

while [ "$#" -gt 0 ]; do
  case "$1" in
    --tasks)     TASKS_DIR="${2:?--tasks needs a directory}"; shift 2 ;;
    --only)      ONLY="${2:?--only needs an id substring}"; shift 2 ;;
    --json)      JSON_OUT="${2:?--json needs a path}"; shift 2 ;;
    --threshold) THRESHOLD="${2:?--threshold needs a number}"; shift 2 ;;
    --no-break)  DO_BREAK=0; shift ;;
    -h|--help)   sed -n '1,70p' "$0"; exit 0 ;;
    *) echo "usage: $0 [--tasks DIR] [--only ID] [--json FILE] [--threshold N] [--no-break]" >&2; exit 2 ;;
  esac
done

if [ ! -d "$TASKS_DIR" ]; then
  echo "EVAL RUNNER ERROR: task directory does not exist: $TASKS_DIR" >&2
  echo "  A missing task directory is not an empty test suite. Exiting 2." >&2
  exit 2
fi

TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

# --- discovery + the first vacuity guard ------------------------------------
#
# Discovery failing open is the whole family of bug this suite is about: a glob
# that matches nothing prints no failures, and no failures reads as success to
# every human and every CI badge. So: zero discovered tasks exits 2, and so does
# zero SELECTED tasks after --only, because a typo'd --only in a CI invocation is
# the same silence with a different cause.
# RECURSIVE, so `tasks/core/` (portable, shipped by the seed) and `tasks/local/`
# (this repo's own, never upstreamed) are one suite with one threshold. They are
# separate directories so the next `new-project` install can replace `core/`
# wholesale without touching anything you wrote.
TASKS=()
while IFS= read -r t; do TASKS+=("$t"); done < <(find "$TASKS_DIR" -name '*.eval.sh' | sort)

if [ "${#TASKS[@]}" -eq 0 ]; then
  echo "EVAL RUNNER ERROR: no eval tasks found in $TASKS_DIR (*.eval.sh)"
  echo "  VACUOUS RUN REFUSED. A suite that examined zero tasks has not tested"
  echo "  anything; reporting that as a pass is the defect this suite exists to"
  echo "  catch. Exiting 2."
  exit 2
fi

SELECTED=()
for t in "${TASKS[@]}"; do
  if [ -n "$ONLY" ] && [[ "$(basename "$t")" != *"$ONLY"* ]]; then continue; fi
  SELECTED+=("$t")
done

if [ "${#SELECTED[@]}" -eq 0 ]; then
  echo "EVAL RUNNER ERROR: --only '$ONLY' selected 0 of ${#TASKS[@]} tasks."
  echo "  VACUOUS RUN REFUSED. Exiting 2."
  exit 2
fi

if [ "$DO_BREAK" -eq 0 ]; then
  echo "!! --no-break: the break phase is SKIPPED. Every result below is"
  echo "!! unverified — a check that cannot fail will report PASS. Debug only."
  echo
fi

# --- the pristine corpus snapshot -------------------------------------------
# Built once, copied per task, so one task's mutation can never be visible to
# another. Copies are real (not hardlinks): a hardlinked corpus lets an
# append-mode mutation write straight through into the developer's checkout.
SNAPSHOT="$TMP_ROOT/snapshot"
mkdir -p "$SNAPSHOT"
for p in "${CORPUS_PATHS[@]}"; do
  [ -e "$REPO_ROOT/$p" ] || continue
  mkdir -p "$SNAPSHOT/$(dirname "$p")"
  cp -a "$REPO_ROOT/$p" "$SNAPSHOT/$p"
done

# run_check <task-file> <corpus-dir> <outfile>
# Sources the task in a subshell so its helpers cannot leak between tasks, and
# so a task that calls `exit` kills only itself.
run_check() {
  local task="$1" corpus="$2" out="$3"
  (
    set +e
    CORPUS="$corpus"
    REPO_ROOT_RO="$REPO_ROOT"
    export CORPUS REPO_ROOT_RO
    # shellcheck disable=SC1090
    . "$task"
    check
  ) >"$out" 2>&1
  return $?
}

subjects_of() {
  # Last SUBJECTS= line wins; absent means the task declared nothing, which is
  # an error rather than "probably fine".
  grep -oE '^SUBJECTS=[0-9]+$' "$1" | tail -1 | cut -d= -f2
}

pass=0; failn=0; errn=0; total_subjects=0
RESULTS=()

for task in "${SELECTED[@]}"; do
  base="$(basename "$task")"

  # --- metadata: a task with no provenance is an assertion nobody can audit ---
  meta="$(
    (
      ID=""; TITLE=""; PROVENANCE=""
      # shellcheck disable=SC1090
      . "$task" >/dev/null 2>&1
      printf '%s\n%s\n%s\n' "$ID" "$TITLE" "$PROVENANCE"
      declare -F check    >/dev/null && echo "HAS_CHECK"
      declare -F break_it >/dev/null && echo "HAS_BREAK"
    )
  )"
  id="$(sed -n 1p <<<"$meta")"
  title="$(sed -n 2p <<<"$meta")"
  prov="$(sed -n 3p <<<"$meta")"
  [ -n "$id" ] || id="$base"

  if [ -z "$title" ] || [ -z "$prov" ] || ! grep -q HAS_CHECK <<<"$meta" || ! grep -q HAS_BREAK <<<"$meta"; then
    echo "ERROR $id"
    echo "      malformed task: needs ID, TITLE, PROVENANCE, check(), break_it()"
    errn=$((errn + 1))
    RESULTS+=("$id|ERROR|0|malformed task file")
    continue
  fi

  # --- live phase --------------------------------------------------------
  live_out="$TMP_ROOT/$base.live"
  run_check "$task" "$REPO_ROOT" "$live_out"
  live_rc=$?
  subj="$(subjects_of "$live_out")"

  if [ -z "$subj" ]; then
    echo "ERROR $id"
    echo "      the check printed no SUBJECTS=<n> line, so it did not declare"
    echo "      what it examined. Unauditable; treated as vacuous."
    head -20 "$live_out" | sed 's/^/      | /'
    errn=$((errn + 1))
    RESULTS+=("$id|ERROR|0|no SUBJECTS declaration")
    continue
  fi

  if [ "$subj" -eq 0 ]; then
    echo "ERROR $id"
    echo "      SUBJECTS=0 — the check examined nothing and would have reported"
    echo "      PASS. A rule with an empty subject set is green by vacuity."
    head -20 "$live_out" | sed 's/^/      | /'
    errn=$((errn + 1))
    RESULTS+=("$id|ERROR|0|examined zero subjects")
    continue
  fi

  total_subjects=$((total_subjects + subj))

  # --- break phase -------------------------------------------------------
  # Corrupt a throwaway copy in the shape this rule guards, and require RED.
  broke_ok=1
  if [ "$DO_BREAK" -eq 1 ]; then
    bcorpus="$TMP_ROOT/break-$base"
    cp -a "$SNAPSHOT" "$bcorpus"
    (
      set +e
      CORPUS="$bcorpus"
      REPO_ROOT_RO="$REPO_ROOT"
      export CORPUS REPO_ROOT_RO
      # shellcheck disable=SC1090
      . "$task"
      break_it
    ) >"$TMP_ROOT/$base.mutate" 2>&1
    mutate_rc=$?

    break_out="$TMP_ROOT/$base.break"
    run_check "$task" "$bcorpus" "$break_out"
    break_rc=$?
    rm -rf "$bcorpus"

    if [ "$mutate_rc" -ne 0 ]; then
      broke_ok=0
      brk_reason="break_it itself failed (rc=$mutate_rc) — the mutation never landed"
    elif [ "$break_rc" -eq 0 ]; then
      broke_ok=0
      brk_reason="the check stayed GREEN against a corpus broken in the shape it guards"
    fi
  fi

  if [ "$broke_ok" -eq 0 ]; then
    echo "ERROR $id  (subjects=$subj)"
    echo "      $brk_reason"
    echo "      A guard nobody watched fail is not a guard. docs/STORY-CONTRACT.md."
    errn=$((errn + 1))
    RESULTS+=("$id|ERROR|$subj|unbreakable: $brk_reason")
    continue
  fi

  if [ "$live_rc" -eq 0 ]; then
    echo "PASS  $id  (subjects=$subj)"
    pass=$((pass + 1))
    RESULTS+=("$id|PASS|$subj|")
  else
    echo "FAIL  $id  (subjects=$subj)"
    echo "      $title"
    head -40 "$live_out" | sed 's/^/      | /'
    failn=$((failn + 1))
    RESULTS+=("$id|FAIL|$subj|see output")
  fi
done

ran=$((pass + failn + errn))
echo
echo "── eval summary ───────────────────────────────────────────────"
echo "tasks run        : $ran (of ${#TASKS[@]} discovered)"
echo "subjects examined: $total_subjects"
echo "pass / fail / err: $pass / $failn / $errn"

# --- the third vacuity guard ------------------------------------------------
# Every task individually declared a non-zero subject count, so this can only
# fire if every selected task errored out before the count was taken. It is here
# because "0 subjects, 0 failures" must never print an exit 0.
if [ "$total_subjects" -eq 0 ]; then
  echo "RESULT: ERROR — the whole run examined 0 subjects. Vacuous; exit 2."
  exit 2
fi

gradeable=$((pass + failn))
if [ "$gradeable" -gt 0 ]; then
  rate=$(( pass * 100 / gradeable ))
else
  rate=0
fi
echo "pass rate        : ${rate}% of $gradeable gradeable (threshold ${THRESHOLD}%)"

if [ -n "$JSON_OUT" ]; then
  {
    printf '{"tasks_run":%d,"discovered":%d,"subjects":%d,"pass":%d,"fail":%d,"error":%d,"rate":%d,"threshold":%s,"results":[' \
      "$ran" "${#TASKS[@]}" "$total_subjects" "$pass" "$failn" "$errn" "$rate" "$THRESHOLD"
    sep=""
    for r in "${RESULTS[@]}"; do
      IFS='|' read -r rid rstat rsubj rnote <<<"$r"
      printf '%s{"id":"%s","status":"%s","subjects":%s,"note":"%s"}' \
        "$sep" "$rid" "$rstat" "$rsubj" "${rnote//\"/\'}"
      sep=","
    done
    printf ']}\n'
  } >"$JSON_OUT"
fi

if [ "$errn" -gt 0 ]; then
  echo "RESULT: ERROR — $errn task(s) are broken checks (vacuous, undeclared, or"
  echo "        unbreakable). This is not graded against the threshold: a check"
  echo "        that cannot fail is not a check, whatever the pass rate says."
  exit 1
fi

if [ "$rate" -lt "$THRESHOLD" ]; then
  echo "RESULT: FAIL — ${rate}% is below the ${THRESHOLD}% threshold."
  exit 1
fi

echo "RESULT: PASS"
exit 0
