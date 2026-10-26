#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# Definition-of-Done checker for a pull request body.
#
# WHY THIS EXISTS. The most expensive failure shape in an agent-built repo is
# *the implementation is real and the wiring isn't*: on one project, nine-plus
# changes merged green and did nothing because an env var, a manifest patch, a
# NetworkPolicy peer or a gateway policy row lived outside the code diff and
# nobody asked what the change needed that wasn't in front of them. The second
# most expensive is a guard that cannot fail — a check that cannot fail is
# indistinguishable from one that passed, and both are green. The third is a
# stale result: `go test ./...` answers `ok (cached)` after a change that broke
# the package, which has already hidden real failures.
#
# None of those are catchable by a human skimming a PR at speed, because in every
# case the PR *looks* complete. They are catchable by asking, mechanically, on
# every single PR: did you write down the wiring, did you watch your guard go red,
# and did you defeat the cache. That is all this script does.
#
# It checks for the PRESENCE of an answer, not its quality. It cannot tell you the
# answer is true. What it can do is remove the option of never having been asked —
# which is why "Wiring required" has a mandatory literal fallback (`no wiring
# required`) rather than being satisfied by omission. A missing section is
# ambiguous between "nothing to say" and "never considered", and those two have
# very different failure modes.
#
# The full contract, and the named bug behind each section, is docs/STORY-CONTRACT.md.
#
# Usage:
#   scripts/dod-check.sh path/to/body.md
#   gh pr view 138 --json body -q .body | scripts/dod-check.sh
#
# Exit: 0 pass · 1 a mandatory section is missing · 2 usage or configuration error.
#
# Dependency-free on purpose (bash + awk + grep, no network, no pip, no action
# download): a guard that can fail for reasons unrelated to what it guards is not
# one you trust on a red day.

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX_FILE="${TICKET_PREFIX_FILE:-$ROOT/.factory/ticket-prefixes}"

if [ "$#" -gt 1 ]; then
  echo "usage: $0 [PR_BODY_FILE]   (reads stdin when no file is given)" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Ticket prefixes are the ONE per-repo fact in this file, so they are read, never
# baked in. Config is never vendored — a seed that ships another repo's ticket
# prefix teaches the first author that seed files are wrong by default, and from
# then on every seed file is negotiable.
#
# A missing or empty config is exit 2, NOT a pass. The whole point of this script
# is that absence must fail; a checker that silently skips its ticket rule
# because a file it depends on went missing is the exact defect it exists to
# catch, wearing the checker's own badge.
# ---------------------------------------------------------------------------
if [ ! -r "$PREFIX_FILE" ]; then
  echo "::error::dod-check is not configured — cannot read '$PREFIX_FILE'" >&2
  echo "          Create it with one ticket prefix per line, e.g.:  printf 'ACME\\n' > .factory/ticket-prefixes" >&2
  exit 2
fi

prefixes=""
bad_prefix=0
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%%#*}"
  line="$(printf '%s' "$line" | tr -d '[:space:]')"
  [ -z "$line" ] && continue
  # Prefixes are interpolated into an ERE below. Anything that is not a bare
  # uppercase key is refused rather than escaped: a `.*` that slipped into this
  # file would make the ticket rule match every body, and it would do it
  # silently and look green.
  case "$line" in
    *[!A-Z0-9]* | [!A-Z]*)
      echo "::error::dod-check: invalid ticket prefix '$line' in $PREFIX_FILE (want ^[A-Z][A-Z0-9]*$)" >&2
      bad_prefix=1
      continue
      ;;
  esac
  prefixes="${prefixes:+$prefixes|}$line"
done < "$PREFIX_FILE"

[ "$bad_prefix" -ne 0 ] && exit 2

if [ -z "$prefixes" ]; then
  echo "::error::dod-check: no usable ticket prefixes in $PREFIX_FILE" >&2
  exit 2
fi

if [ "$#" -eq 1 ]; then
  if [ ! -r "$1" ]; then
    echo "dod-check: cannot read '$1'" >&2
    exit 2
  fi
  body="$(cat -- "$1")"
else
  body="$(cat)"
fi

if [ -z "${body//[[:space:]]/}" ]; then
  echo "::error::PR body is empty — every mandatory section is missing" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Three views of the body.
#
#   raw    — HTML comments stripped. Used for CONTENT signatures (the literal
#            `no wiring required`, a `-count=1` flag, a ticket key). Comments are
#            stripped first and everywhere: the PR template's own instructions
#            name every section, so a body that deleted a heading but kept the
#            comment would otherwise pass on the instructions telling it what to
#            write.
#   prose  — raw with fenced code blocks removed. Used for LABEL matching, so a
#            section name that only appears inside pasted test output does not
#            count as a section.
#   labels — one candidate section label per line, extracted from prose.
# ---------------------------------------------------------------------------

strip_comments='
BEGIN { inc = 0 }
{
  line = $0; out = ""
  while (1) {
    if (inc) {
      p = index(line, "-->")
      if (p == 0) { break }
      line = substr(line, p + 3); inc = 0
    } else {
      p = index(line, "<!--")
      if (p == 0) { out = out line; break }
      out = out substr(line, 1, p - 1)
      line = substr(line, p + 4); inc = 1
    }
  }
  print out
}'

# Fence handling follows CommonMark's open/close rule rather than toggling on
# every ``` line: a fence opened with N markers is closed only by N-or-more of the
# SAME character with nothing but whitespace after it. Toggling desynchronises on
# a body that quotes a fence inside a fence (```` wrapping ```yaml) — which is how
# a reviewer pastes the workflow snippet they are talking about — and from that
# line on, every section is mis-classified. A checker that goes red on a GOOD body
# is a checker the first person it annoys will delete.
fence_fns='
function fence_marker(line, out,    ch, cnt, i, n) {
  sub(/^[ \t]+/, "", line)
  ch = substr(line, 1, 1)
  if (ch != "`" && ch != "~") { return 0 }
  n = length(line); cnt = 0
  for (i = 1; i <= n; i++) { if (substr(line, i, 1) == ch) { cnt++ } else { break } }
  if (cnt < 3) { return 0 }
  out["char"] = ch
  out["len"] = cnt
  out["info"] = substr(line, cnt + 1)
  return 1
}
function fence_closes(line, ochar, olen, f) {
  if (!fence_marker(line, f)) { return 0 }
  # An info string ("```yaml") can only open, never close.
  return (f["char"] == ochar && f["len"] >= olen && f["info"] ~ /^[ \t]*$/)
}'

strip_fences='
{
  if (!open) {
    if (fence_marker($0, f)) { open = 1; ochar = f["char"]; olen = f["len"]; next }
    print
    next
  }
  if (fence_closes($0, ochar, olen, f)) { open = 0 }
  next
}'

# A line is a section label if it is a heading, a bold label, a "Label: ..."
# bullet, or the first cell of a table row. Anything else is body text — a bullet
# that merely mentions wiring in passing must not satisfy the wiring section.
extract_labels='
{
  line = $0

  if (match(line, /^[ \t]*#+[ \t]+/)) {
    print substr(line, RSTART + RLENGTH); next
  }

  if (match(line, /^[ \t]*\*\*/)) {
    rest = substr(line, RSTART + RLENGTH)
    p = index(rest, "**")
    if (p > 1) { print substr(rest, 1, p - 1); next }
  }

  if (match(line, /^[ \t]*[-*+][ \t]+/)) {
    rest = substr(line, RSTART + RLENGTH)
    sub(/^\[[ xX]\][ \t]*/, "", rest)
    c = index(rest, ":")
    # Require the colon: without it there is no label, only prose, and treating
    # 80 characters of prose as a label is how a checker gets hollowed out.
    if (c > 1 && c <= 80) {
      rest = substr(rest, 1, c - 1)
      gsub(/\*\*/, "", rest)
      print rest
    }
    next
  }

  if (match(line, /^[ \t]*\|/)) {
    n = split(line, f, "|")
    if (n >= 2) {
      cell = f[2]; gsub(/\*\*/, "", cell)
      if (cell !~ /^[ \t-]*$/) print cell
    }
    next
  }
}'

raw="$(printf '%s\n' "$body" | awk "$strip_comments")"
prose="$(printf '%s\n' "$raw" | awk "$fence_fns$strip_fences")"
labels="$(printf '%s\n' "$prose" | awk "$extract_labels")"

# Prose before the first heading: the lede. A PR that opens by explaining itself
# in plain paragraphs has a summary whether or not it labelled one, and the three
# best PR bodies in that project's history all do exactly that. A line that is nothing
# but ticket keys is not a lede, so it is filtered out first.
preamble="$(printf '%s\n' "$prose" | awk '
  /^[ \t]*#+[ \t]+/ { exit }
  { print }
' | grep -vE "^[[:space:]]*(($prefixes)-[0-9nN]+[[:space:]]*)+$" | tr -d '[:space:]')"

has_label() { printf '%s\n' "$labels" | grep -qiE "$1"; }
has_text() { printf '%s\n' "$raw" | grep -qiE "$1"; }

# "Not verified here" contains "verified". Without this, the advisory honesty
# section silently satisfies the mandatory verification section — the checker's
# own regression suite caught exactly that, which is the entire argument for the
# suite existing.
positive_labels="$(printf '%s\n' "$labels" | grep -viE '(^|[^a-z])(not|non|un|never|isn.?t|aren.?t|cannot|can.?t|couldn.?t|missing|without|left)([^a-z]|$)')"
has_positive_label() { printf '%s\n' "$positive_labels" | grep -qiE "$1"; }

# ---------------------------------------------------------------------------
# Section bodies, for the empty-heading rule.
#
# A heading with nothing under it is not an answer. It is the shape a template
# leaves behind when its instructions are read and its question is not, and it
# reads to a reviewer exactly like a considered one.
#
# Split on `raw`, not `prose`: the heading LINES must be found outside fences (so
# a `## Wiring required` pasted inside test output is not a section) but fenced
# CONTENT still counts as content — a Verification section whose whole answer is
# a pasted `-count=1` run is answered, not empty.
#
# Headings only. A bold label with nothing under it is not detected here; that is
# a deliberate limit, not an oversight — the template ships `##` headings, and
# widening this to bold labels makes "the next paragraph" ambiguous.
# ---------------------------------------------------------------------------
section_split='
{
  if (!open) {
    if (fence_marker($0, f)) { open = 1; ochar = f["char"]; olen = f["len"]; if (ing) print; next }
    if ($0 ~ /^[ \t]*#+[ \t]+/) {
      hd = $0; sub(/^[ \t]*/, "", hd); sub(/[^#].*$/, "", hd); depth = length(hd)
      # A DEEPER heading inside a matched section is that section content, not a
      # terminator. Without this, an honest body that answers "## Wiring required"
      # with "### Env vars / ### Manifests" reads as EMPTY and is rejected — a
      # regression the first version of this fix introduced, against a body shape
      # the naive version accepted. A checker that goes red on a good body is how
      # a check gets switched off by the first person it annoys.
      if (ing && depth > sdepth) { print; next }
      h = tolower($0); sub(/^[ \t]*#+[ \t]+/, "", h)
      if (h ~ pat && !(neg != "" && h ~ neg)) { ing = 1; seen = 1; sdepth = depth } else { ing = 0 }
      next
    }
    if (ing) print
    next
  }
  if (fence_closes($0, ochar, olen, f)) { open = 0 }
  if (ing) print
}
END { exit(seen ? 0 : 1) }'

# section_content <lowercase-ERE> [negative-ERE] — prints the body; exit 1 when
# no such heading exists.
section_content() {
  printf '%s\n' "$raw" | awk -v pat="$1" -v neg="${2:-}" "$fence_fns$section_split"
}

# True only when the heading EXISTS and its body is blank. A section that is
# absent is somebody else's check (1–5 below); this one is about the hollow one.
section_is_empty() {
  local content
  content="$(section_content "$1" "${2:-}")" || return 1
  [ -z "${content//[[:space:]]/}" ]
}

missing=0
fail() {
  echo "::error::MISSING — $1" >&2
  echo "          $2" >&2
  missing=1
}

# --- 1. Summary / why -------------------------------------------------------
# Prevents a PR whose reviewer has to reconstruct the intent from the diff.
if ! has_label '(summary|what changed|the change|overview|background|why)' \
  && [ "${#preamble}" -lt 80 ]; then
  fail "summary / what changed and why" \
    "Add a '## Summary — what changed and why' section, or open with a paragraph that says it."
fi

# --- 2. Ticket reference ----------------------------------------------------
# Prevents work that cannot be traced back to the story that authorised it.
if ! has_text "\\b($prefixes)-[0-9]+\\b"; then
  fail "ticket reference" \
    "Name the story key (one of: $prefixes) in the body."
fi

# --- 3. Wiring required -----------------------------------------------------
# THE ONE. Nine-plus green-and-inert merges. The literal fallback is mandatory
# because omission cannot be distinguished from consideration.
if ! has_label 'wiring' && ! has_text 'no wiring required'; then
  fail "wiring required" \
    "What does this change need to work that is NOT in the diff — env var, secret, network policy, migration, CI job, manifest tag? If nothing, write the literal words: no wiring required"
fi

# --- 4. Prove it by breaking ------------------------------------------------
# A guard nobody watched fail is not verified.
if ! has_label '(prov(e|ed|en|ing)|proof).*break|break.*(guard|the check|the test)'; then
  fail "prove it by breaking" \
    "Remove or invert the guard, record the RED output, restore it, record the GREEN output. Both go in the body."
fi

# --- 5. Verification --------------------------------------------------------
# Satisfied by a labelled section OR by demonstrated cache-defeating evidence:
# a body showing `-count=1` has done the thing the section exists to ask for.
if ! has_positive_label '(verif(y|ied|ication|ying)|how i tested|tests? run|test plan)' \
  && ! has_text '[-]count[= ]1'; then
  fail "verification" \
    "State the exact commands with cache-defeating flags (go test -count=1 ./...). 'ok (cached)' has hidden real failures."
fi

# --- 6. No hollow sections --------------------------------------------------
# A heading with nothing under it is not an answer, and checks 1–5 above only ask
# whether the heading exists. Left alone, the cheapest way past this checker is to
# keep every heading the template ships and answer none of them — which produces a
# body that reads, to a reviewer, exactly like a considered one.
#
# The template's instruction comments do not count as content: `raw` has comments
# stripped before this runs, so reading the instructions and skipping the question
# leaves a section that is, correctly, empty.
NEGATED='(^|[^a-z])(not|non|un|never|isn.?t|aren.?t|cannot|can.?t|couldn.?t|missing|without|left)([^a-z]|$)'

if section_is_empty 'wiring'; then
  fail "wiring required (heading present, nothing under it)" \
    "The section is empty. Say what this change needs that is not in the diff — or, having actually walked the list, type the literal words: no wiring required"
fi

if section_is_empty '(prov(e|ed|en|ing)|proof).*break|break.*(guard|the check|the test)'; then
  fail "prove it by breaking (heading present, nothing under it)" \
    "The section is empty. Name the edit you made to break the guard, and paste BOTH the red and the green run."
fi

if section_is_empty '(verif(y|ied|ication|ying)|how i tested|tests? run|test plan)' "$NEGATED"; then
  fail "verification (heading present, nothing under it)" \
    "The section is empty. Give the exact commands with cache-defeating flags (go test -count=1 ./...)."
fi

if section_is_empty '(summary|what changed|the change|overview|background)'; then
  fail "summary (heading present, nothing under it)" \
    "The section is empty. Say what was broken, what it looked like from the outside, and why it looked correct."
fi

# --- 7. No unfilled evidence boxes ------------------------------------------
# The PR template ships empty fences for the red and green output. Submitting
# them empty is submitting the template, not the evidence.
if printf '%s\n' "$raw" | awk "$fence_fns"'
{
  if (!open) {
    if (fence_marker($0, f)) { open = 1; ochar = f["char"]; olen = f["len"]; blank = 1 }
    next
  }
  if (fence_closes($0, ochar, olen, f)) {
    if (blank) { found = 1 }
    open = 0
    next
  }
  if ($0 !~ /^[ \t]*$/) { blank = 0 }
}
END { exit(found ? 0 : 1) }
'; then
  fail "evidence (empty code fence)" \
    "An empty \`\`\` block was left in the body — fill in the red/green output or delete the box."
fi

if [ "$missing" -ne 0 ]; then
  echo "" >&2
  echo "dod-check FAILED. Contract and rationale: docs/STORY-CONTRACT.md" >&2
  exit 1
fi

# Advisory. Deliberately NOT fatal: an author with a genuinely empty list has
# nothing to write, and a mandatory heading answered with nothing produces ritual
# instead of honesty. Reviewers should still not let it slide — a confident false
# success is the most dangerous thing a PR can contain.
if ! has_label '(not verified|unverified|left undone|not done|limitations?|caveats?|known gaps?|recorded honestly|honest|open questions?)'; then
  echo "::warning::no 'Not verified / left undone' section — say plainly what you could not run or reach, or say 'nothing'." >&2
elif section_is_empty '(not verified|unverified|left undone|not done|limitations?|caveats?|known gaps?|open questions?)'; then
  # Same reasoning as above, one step in: the heading is there and answers nothing.
  # Still a warning, not a failure — the honesty section is the one place where
  # forcing words produces ritual, and the word wanted here ("nothing") is one an
  # author will write freely and an author with something to hide will write anyway.
  echo "::warning::'Not verified / left undone' has a heading and nothing under it — write what you could not run or reach, or write 'nothing'." >&2
fi

echo "dod-check PASSED — summary, ticket, wiring, prove-by-breaking and verification are all present."
