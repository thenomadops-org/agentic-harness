#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# The other half of task 01, and the sharper half.
#
# Task 01 asks whether a file reasoned about the false negative anywhere. This
# one asks whether any single line tells an agent, in words, to treat emptiness
# as good news: "the board is clear", "no duplicate exists", "all green",
# "nothing to do, proceed". That sentence is the whole bug in one line — it is
# what the dispatcher effectively said to nine agents at once — and it is worth
# catching on its own because a file can carry a perfectly good positive control
# in section 2 and this sentence in section 7.
#
# BLOCKQUOTES AND POST-MORTEMS ARE EXCLUDED, and that exclusion is the reason
# this check is usable rather than noisy. A repo that documents its incidents inside
# the config that caused them will have the exact sentence being banned appear —
# correctly — in the retrospective that bans it. A grep that cannot tell a
# tombstone from a live instruction reports both, and the first false red is when
# somebody stops reading the output. Quoted incident prose lives in `>`
# blockquotes here, and past-tense incident markers cover the rest.
# shellcheck source=../../lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

ID="no-benign-conclusion-from-empty"
TITLE="No instruction may turn an empty result into good news"
PROVENANCE="a dispatcher read [] as 'the board is clear' and fanned out nine agents on it; a second skill read [] as 'no duplicate exists' (seen on one project, repeatedly)"

EMPTINESS='empty|zero|no results|nothing found|\[\]|totalcount'
BENIGN='is clear|no duplicate|nothing to do|all green|is green|you may proceed|proceed with|conclude (that )?none|means none|so none'
# Anything that marks the line as a refusal, a prohibition, or a past incident
# being described rather than an instruction being given.
EXEMPT='not green|not clear|never|refuse|halt|stop|wrong|broken|must be|do not|don.t|read (that|it) as|used to|until 20|incident|retired|no longer'

check() {
  local v n scan f rc
  v="$(mktemp)"; scan="$(mktemp)"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    prose_lines "$f" | grep -vE '^[[:space:]]*>' | sed "s|^|${f#"$CORPUS"/}: |" >>"$scan"
  done < <(config_files)

  # Subjects are the lines that talk about emptiness at all — the population this
  # rule actually judges, not the whole corpus.
  n="$(grep -icE "$EMPTINESS" "$scan")"

  grep -iE "$EMPTINESS" "$scan" | grep -iE "$BENIGN" | grep -viE "$EXEMPT" >>"$v"

  report_violations "instruction lines mentioning an empty/zero result" "$n" "$v"
  rc=$?
  rm -f "$v" "$scan"
  return $rc
}

break_it() {
  cat >>"$CORPUS/CLAUDE.md" <<'PROBE'

If the duplicate search comes back empty, the board is clear and you may proceed
to create the ticket.
PROBE
}
