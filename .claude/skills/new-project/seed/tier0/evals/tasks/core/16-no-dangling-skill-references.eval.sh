#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# The config must not send an agent to a skill that is not there.
#
# THIS IS LIVE, NOT HYPOTHETICAL. Two skills were being deleted from the source
# repo in the same hours this suite was written. Deleting a skill is easy; finding every
# `CLAUDE.md` bullet, every sibling skill, and every process document that told
# an agent to apply it is not, and the leftovers do not fail — an agent asked to
# apply a skill that does not exist improvises one. It has no way to know that
# what it improvised was supposed to be a specific, load-bearing procedure, and
# the transcript reads as though the step was followed.
#
# WHY THE TOMBSTONE RULE IS THE HEART OF THIS CHECK. A retirement notice and a
# dangling pointer are the same string to a grep — "the `adr-flow` skill is
# superseded" names a skill exactly the way an instruction to use it does. A
# check that cannot tell them apart reports every honest retirement as a defect,
# and the first false red is when somebody stops reading this suite's output. So
# a reference is a violation only when the citing LINE reads as an instruction
# and the citing FILE does not, anywhere, record that skill as gone.
# shellcheck source=../../lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

ID="no-dangling-skill-references"
TITLE="Every skill the config tells an agent to apply exists in .claude/skills/"
PROVENANCE="two skills were deleted while this suite was written; references to a deleted skill do not fail, they get improvised (seen on one project, repeatedly)"

check() {
  local v n rel p name rc
  v="$(mktemp)"; n=0
  while IFS=$'\t' read -r rel p; do
    [ -n "$p" ] || continue
    name="$(sed 's|^\.claude/skills/||; s|/.*$||' <<<"$p")"
    [ -n "$name" ] || continue
    n=$((n + 1))
    [ -d "$CORPUS/.claude/skills/$name" ] ||
      echo "$rel points at the '$name' skill, which is not in .claude/skills/" >>"$v"
  done < <(scan_citations '\.claude/skills/[A-Za-z0-9_-]+')

  report_violations "skill references in the agent config" "$n" "$v"
  rc=$?
  rm -f "$v"
  return $rc
}

break_it() {
  cat >>"$CORPUS/CLAUDE.md" <<'PROBE'

Apply `.claude/skills/ticket-flow` to every unit of work before you start.
PROBE
}
