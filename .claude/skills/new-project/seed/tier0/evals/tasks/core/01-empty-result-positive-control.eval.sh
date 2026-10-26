#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# An empty result is a BROKEN QUERY until proven otherwise.
#
# THE INCIDENT. Two skills on one project named a tracker project that did not
# exist. A query naming a nonexistent project returns an empty result set with a
# SUCCESS status — no error, no warning, no hint — so the duplicate search in one of them
# returned `[]` every time it was ever run, and it sat on the path of every unit
# of work: a machine that answered "no duplicate exists" to every question it was
# ever asked. The same defect in the dispatcher meant "the board is clear" at
# nine-agent scale. Measured on the day it was found: the wrong key returned
# totalCount 0, the right key returned 395, and the two responses were otherwise
# byte-identical.
#
# THE RULE, generalised past the tool that produced it. Any instruction that
# DECIDES something on an empty or zero result must first prove the query works —
# a positive control beside the negative one. The negative control alone proves
# nothing: a correct empty result and a wrong-query empty result look the same.
#
# This is deliberately not written against any tracker, query language or named
# skill. The shape outlives all of them: it applies to a `gh` search, a
# `kubectl get`, a grep over a file list, and to skills nobody has written yet.
# shellcheck source=../../lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

ID="empty-result-positive-control"
TITLE="Config that decides on an empty result must prove the query works first"
PROVENANCE="two skills named a tracker project that did not exist; every search returned [] and both read that as 'nothing found' (seen on one project, repeatedly)"

# Text that DECIDES on emptiness: a conditional whose subject is a zero/empty
# result. Kept close ({0,60}) so it matches an instruction rather than any two
# words in a paragraph.
TRIGGER='(if|when|should)[^.]{0,60}(empty|zero|totalcount|returns? *\[\]|no (results?|issues|matches|checks|hits|duplicates?))'

# Text that proves the query worked, or refuses to act until it does. Any one of
# these in the same file is enough: this asserts the author reasoned about the
# false negative, not that they used a particular phrasing.
CONTROL='must be > 0|greater than 0|non-?zero|positive control|broken query|query is wrong|is not green|is not clear|refuse|halt|stop and report|prove the query|assert.*not empty'

check() {
  local v n f rel rc
  v="$(mktemp)"; n=0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    grep -qiE "$TRIGGER" "$f" || continue
    n=$((n + 1))
    rel="${f#"$CORPUS"/}"
    if ! grep -qiE "$CONTROL" "$f"; then
      echo "$rel decides on an empty/zero result but never proves the query works (no positive control, no refusal)" >>"$v"
    fi
  done < <(config_files)
  report_violations "config files that decide on an empty result" "$n" "$v"
  rc=$?
  rm -f "$v"
  return $rc
}

break_it() {
  # A new skill that concludes from an empty result with no control at all —
  # the exact defect, reintroduced under a name that has never existed.
  mkdir -p "$CORPUS/.claude/skills/eval-probe-empty"
  cat >"$CORPUS/.claude/skills/eval-probe-empty/SKILL.md" <<'PROBE'
---
name: eval-probe-empty
description: Fixture for the evals suite. Use when running evals/run.sh.
---
# Probe

Search the tracker for an existing ticket. If the search returns zero rows,
conclude that none has been filed and create a new one.
PROBE
}
