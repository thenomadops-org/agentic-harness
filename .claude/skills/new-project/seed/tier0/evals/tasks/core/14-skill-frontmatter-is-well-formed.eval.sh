#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# A skill is loaded by its frontmatter, so a broken frontmatter is a skill that
# silently does not exist.
#
# The failure is quiet in the worst way: the file is in the tree, it shows up in
# code review, someone maintains it — and no agent ever loads it, because the
# `name` does not match the directory the harness looks it up by, or the
# frontmatter block is malformed. There is no error message anywhere in that
# story. The work simply gets done without the skill, and the skill's absence is
# indistinguishable from an agent choosing not to use it.
#
# It also catches a duplicate `name` across two directories, where one skill
# shadows the other and the loser is invisible for the same reason.
# shellcheck source=../../lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

ID="skill-frontmatter-is-well-formed"
TITLE="Every skill has YAML frontmatter whose name matches its directory and is unique"
PROVENANCE="a skill whose name does not match its directory is never loaded, and nothing reports it (seen on one project, repeatedly)"

check() {
  local v n f dir name rc names
  v="$(mktemp)"; names="$(mktemp)"; n=0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    n=$((n + 1))
    dir="$(basename "$(dirname "$f")")"

    if [ "$(head -1 "$f")" != "---" ]; then
      echo "$dir/SKILL.md does not open with a --- frontmatter block; it will not load" >>"$v"
      continue
    fi
    name="$(awk 'NR>1 && /^---/{exit} /^name:/{sub(/^name:[[:space:]]*/,""); print; exit}' "$f")"
    if [ -z "$name" ]; then
      echo "$dir/SKILL.md declares no name: in its frontmatter" >>"$v"
      continue
    fi
    if [ "$name" != "$dir" ]; then
      echo "$dir/SKILL.md declares name '$name', which does not match its directory" >>"$v"
    fi
    echo "$name" >>"$names"
  done < <(skill_files)

  while IFS= read -r name; do
    [ -n "$name" ] || continue
    echo "two skills both declare the name '$name'; one shadows the other" >>"$v"
  done < <(sort "$names" | uniq -d)

  report_violations "skills" "$n" "$v"
  rc=$?
  rm -f "$v" "$names"
  return $rc
}

break_it() {
  mkdir -p "$CORPUS/.claude/skills/eval-probe-frontmatter"
  cat >"$CORPUS/.claude/skills/eval-probe-frontmatter/SKILL.md" <<'PROBE'
---
name: probe-frontmatter
description: Fixture whose name does not match its directory. Use when running evals.
---
# Probe
PROBE
}
