#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# A skill's description is its trigger, not its title.
#
# The description is the ONLY part of a skill an agent sees before deciding
# whether to load it. A description that says what the skill is ("the release
# process") and never says when to reach for it produces a skill that exists,
# passes review, and is never invoked — the most expensive kind of dead
# configuration, because everyone believes the behaviour it describes is in
# force. A repo can ship instructions nobody executes; the structural
# version of that is a skill nobody triggers.
#
# The bar here is deliberately low and mechanical: the description must contain
# a trigger clause ("use when", "invoke when", "apply", "whenever", "run when",
# "triggers on"), and must be long enough to carry one. It cannot judge whether
# the trigger is a GOOD one. What it can do is remove the option of never having
# written one.
# shellcheck source=../../lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

ID="skill-description-says-when-to-use-it"
TITLE="Every skill's description carries a trigger clause, not just a title"
PROVENANCE="the description is the only text an agent sees before loading a skill; without a trigger it is never selected (seen on one project, repeatedly)"

#
# `load when|load before|read before` are in this list because a rewrite on one project landed
# three new skills that phrase their trigger exactly that way — "Load when adding
# or changing a service" — and the first version of this pattern reported one of
# them as having no trigger. That was a false red in the recognizer, not a defect
# in the skill: the description does say when to reach for it. Widening a
# recognizer to admit a valid phrasing is not the same act as waiving a
# violation, and the difference is worth stating out loud, because the two look
# identical in a diff. The probe in break_it still has no trigger of any kind.
TRIGGER='use (this )?(skill )?when|use it when|invoke when|invoke this|apply (this|it|automatically)|whenever|run when|when the (user|owner)|triggers? on|for any|load (when|before|it)|read (this )?(when|before)|before you'

check() {
  local v n f dir desc rc
  v="$(mktemp)"; n=0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    n=$((n + 1))
    dir="$(basename "$(dirname "$f")")"
    desc="$(awk 'NR>1 && /^---/{exit} /^description:/{sub(/^description:[[:space:]]*/,""); print; exit}' "$f")"
    if [ -z "$desc" ]; then
      echo "$dir declares no description: — an agent has nothing to select it on" >>"$v"
      continue
    fi
    if [ "${#desc}" -lt 40 ]; then
      echo "$dir has a ${#desc}-character description; too short to carry a trigger" >>"$v"
      continue
    fi
    grep -qiE "$TRIGGER" <<<"$desc" ||
      echo "$dir describes what it is but never says WHEN to use it" >>"$v"
  done < <(skill_files)

  report_violations "skill descriptions" "$n" "$v"
  rc=$?
  rm -f "$v"
  return $rc
}

break_it() {
  mkdir -p "$CORPUS/.claude/skills/eval-probe-trigger"
  cat >"$CORPUS/.claude/skills/eval-probe-trigger/SKILL.md" <<'PROBE'
---
name: eval-probe-trigger
description: The deployment procedure for the production cluster and its rollback path.
---
# Probe
PROBE
}
