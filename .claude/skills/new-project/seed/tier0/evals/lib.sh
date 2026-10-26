#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# Helpers shared by evals/tasks/**/*.eval.sh.
#
# Every helper reads the corpus through $CORPUS and nothing else. In the live
# phase $CORPUS is the repo root; in the break phase it is a disposable copy
# that break_it has corrupted. A helper that hard-codes a repo path would make
# its task unbreakable — and an unbreakable check is the thing this suite is
# built to refuse.
#
# WHAT COUNTS AS "THE AGENT CONFIGURATION". `CLAUDE.md` plus every Markdown file
# under `.claude/` — which is to say, everything the harness loads into an
# agent's context before it has read a single line of the codebase. The set is
# GLOBBED, never listed. Skills are added and deleted constantly — two were being
# deleted the day this suite was written — and a task that names a file by hand
# turns a routine deletion into a red check, which is how a suite teaches people
# to ignore it.

# Every agent-facing config file in the corpus, one path per line.
config_files() {
  [ -f "$CORPUS/CLAUDE.md" ] && echo "$CORPUS/CLAUDE.md"
  find "$CORPUS/.claude" -name '*.md' -type f 2>/dev/null | sort
}

# Just the skills.
skill_files() {
  find "$CORPUS/.claude/skills" -maxdepth 2 -name 'SKILL.md' -type f 2>/dev/null | sort
}

# Lines inside ``` fenced blocks — the runnable half of a config file. A path or
# a command in a fence is something an agent copies and executes; the same
# string in prose may be a retirement notice ("docs/DECISIONS.md no longer
# exists"), a post-mortem, or an explicit prohibition. Several checks here care
# only about the runnable half, and conflating the two is exactly how a naive
# filename grep reports a dangling pointer and a deliberate tombstone
# identically.
fenced_lines() {
  awk '/^[[:space:]]*```/ { inf = !inf; next } inf { print }' "$1"
}

# Lines outside ``` fenced blocks — the half an agent reads as instruction.
prose_lines() {
  awk '/^[[:space:]]*```/ { inf = !inf; next } !inf { print }' "$1"
}

# A line that marks a path as deliberately gone rather than accidentally broken.
#
# THIS EXCLUSION IS THE POINT, not a loophole. A filename grep cannot tell a
# dangling pointer from a tombstone — "docs/DECISIONS.md no longer exists, do not
# recreate it" and a stale instruction to write to that same file are the same
# string to it. A repo that documents its retirements inside the files that used
# to depend on them will have every honest retirement notice reported as a defect
# by a naive existence check. The first false red is when somebody stops reading.
#
# If you need to widen this, ask which of the two you are doing: admitting a
# valid phrasing the recognizer did not know, or waiving a real violation. They
# look identical in a diff and they are not the same act.
CITATION_TOMBSTONE='no longer exist|does not exist|did not exist|retired|superseded|decommission|removed|deleted|renamed|used to|until 20|do not recreate|is gone|are gone'

# scan_citations <path-regex>
# Emits "<file>\t<path>" for every repo path an agent could be told to act on.
#
# Two filters, both load-bearing:
#   * a line that reads as a tombstone is skipped, and
#   * if ANY line in the same file marks that specific path as gone, every
#     citation of it in that file is skipped — the file has announced the
#     retirement, and the rest of its prose is history, not instruction.
#   * a match preceded by "/" in its own line is a suffix of a longer path
#     (`mobile/iosApp/scripts/release-ios.sh` is not `scripts/release-ios.sh`)
#     and is dropped, because reporting it sends the reader to a file that was
#     never cited.
scan_citations() {
  local re="$1" f rel line p pairs tombs
  pairs="$(mktemp)"; tombs="$(mktemp)"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    rel="${f#"$CORPUS"/}"
    while IFS= read -r line; do
      for p in $(grep -oE "$re" <<<"$line" | sort -u); do
        grep -qF "/$p" <<<"$line" && continue
        printf '%s\t%s\n' "$rel" "$p" >>"$pairs"
      done
    done < <(grep -hE "$re" "$f" 2>/dev/null | grep -viE "$CITATION_TOMBSTONE")
    while IFS= read -r line; do
      for p in $(grep -oE "$re" <<<"$line" | sort -u); do
        printf '%s\t%s\n' "$rel" "$p" >>"$tombs"
      done
    done < <(grep -hE "$re" "$f" 2>/dev/null | grep -iE "$CITATION_TOMBSTONE")
  done < <(config_files)
  sort -u "$pairs" | grep -vxF -f <(sort -u "$tombs"; echo '___never___') || true
  rm -f "$pairs" "$tombs"
}

# report_violations <label> <subject-count> <violations-file>
# The single exit convention for every task: print the subject census FIRST (the
# runner refuses a task that does not), then the violations, then return red iff
# there were any. Printing the census before the verdict is deliberate — a task
# that dies halfway still shows what it had reached.
report_violations() {
  local label="$1" n="$2" vfile="$3"
  echo "SUBJECTS=$n"
  echo "examined $n $label"
  if [ -s "$vfile" ]; then
    echo "VIOLATIONS:"
    sed 's/^/  - /' "$vfile"
    return 1
  fi
  return 0
}
