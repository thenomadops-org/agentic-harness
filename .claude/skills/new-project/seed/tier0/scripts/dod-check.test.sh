#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# Regression suite for scripts/dod-check.sh.
#
# WHY THIS EXISTS. dod-check.sh is itself a guard, and the standing rule is that
# a guard nobody watched fail is not verified. The prove-by-breaking run recorded
# in the PR that introduced it is a one-off: it proves the check worked on the
# day it was written and says nothing about the day someone loosens a regex to
# get their own PR through. These cases make the break permanent — every
# MUST-FAIL case below is a way the checker could be hollowed out, asserted to
# still be red.
#
# The two subtle ones are FENCED and COMMENTED: a body can name every section
# without having any, by burying the names in pasted test output or in the PR
# template's own instruction comments. Both must still fail.
#
# Usage: scripts/dod-check.test.sh    (exit 0 = all cases behave)

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/gate-test-lib.sh"

CHECK="$HERE/dod-check.sh"
TEMPLATE="$HERE/../.github/pull_request_template.md"
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT

# The suite supplies its own prefix config rather than reading the repo's, so the
# cases below stay true in whatever repo this seed was vendored into. It also
# exercises the TICKET_PREFIX_FILE override, which is the only way CI can run
# this file before .factory/ticket-prefixes has been written.
printf '# fixture\nPROJ\nDEMO\n' >"$TMP/prefixes"
export TICKET_PREFIX_FILE="$TMP/prefixes"

dod() { bash "$CHECK" "$@"; }

# A complete, honest body. Every other case is this one, damaged.
read -r -d '' GOOD <<'EOF'
PROJ-999 — stop the widget resolver answering for media it does not own.

The resolver looked correct because the owner check ran on the read path. Naming
the id on the write path skipped it entirely, so the guard was enforced exactly
where nobody was attacking.

## Wiring required

`WIDGET_URL` added to media's Deployment, and `allow-widget` extended to admit
`media` — the namespace is default-deny, so without it the call is dropped and
the feature fails a second, identical-looking way.

## Proven by breaking it

Removed the owner comparison in `resolveWidget`; `TestForeignOwnerRefused` went
red as below. Restored it and it went green.

## Verification

`go test -count=1 ./...` green in all 14 modules, `go vet` and `gofmt -l` clean.

## Not verified here

No live deploy — the NetworkPolicy change is validated by server-side dry run
only.
EOF

# Delete the section whose heading matches, up to the next heading.
drop_section() { awk -v pat="$1" '/^##/ { skip = ($0 ~ pat) } !skip { print }'; }
# Blank the matched section's body, keeping its heading.
empty_section() { awk -v pat="$1" '/^##/ { skip = ($0 ~ pat); print; next } !skip { print }'; }
mangle() { printf '%s\n' "$GOOD" | "$@"; }

NO_WIRING_HEADING="$(mangle drop_section 'Wiring')"

gate_section "MUST PASS"
gate_expect_in 0 "complete body" "$GOOD" -- dod

# Wiring satisfied by the literal fallback alone, with no heading at all.
gate_expect_in 0 "wiring via literal 'no wiring required'" \
  "$(printf '%s\n' "$NO_WIRING_HEADING" | sed 's|^## Proven by breaking it$|no wiring required\n\n## Proven by breaking it|')" -- dod

# Verification satisfied by cache-defeating evidence with no labelled section.
gate_expect_in 0 "verification via -count=1 evidence" \
  "$(mangle drop_section 'Verification' | sed 's|^## Not verified here$|Ran go test -count=1 ./... in all 14 modules.\n\n## Not verified here|')" -- dod

# The advisory section is a warning, never a failure — and the warning must fire,
# or "advisory" quietly becomes "absent".
gate_expect_in 0 "missing 'not verified' warns only" "$(mangle drop_section 'Not verified')" -- dod \
  --want "::warning::no 'Not verified / left undone' section"

gate_section "MUST FAIL"
gate_expect_in 1 "wiring section removed" "$NO_WIRING_HEADING" -- dod
gate_expect_in 1 "prove-by-breaking removed" "$(mangle drop_section 'Proven by breaking')" -- dod

# "Not verified here" contains the word "verified". This case exists because it
# passed on the first draft: the honesty section satisfied the verification check.
gate_expect_in 1 "verification removed, no -count=1" \
  "$(mangle drop_section 'Verification' | sed 's/-count=1//')" -- dod

gate_expect_in 1 "no ticket key" "$(mangle sed 's/PROJ-999/A widget bug/')" -- dod
gate_expect_in 1 "empty body" "" -- dod

# A section name that exists only inside pasted output is not a section.
gate_expect_in 1 "wiring named only inside a code fence" \
  "$(printf '```\n## Wiring required\nnone needed\n```\n%s\n' "$NO_WIRING_HEADING")" -- dod

# ...nor one that exists only in the PR template's own instruction comment.
gate_expect_in 1 "wiring named only inside an HTML comment" \
  "$(printf '<!-- ## Wiring required — env vars, or: no wiring required -->\n%s\n' "$NO_WIRING_HEADING")" -- dod

# An unfilled evidence box is the template, not the evidence.
gate_expect_in 1 "empty evidence fence left in body" \
  "$(mangle sed 's|^## Verification$|```\n```\n\n## Verification|')" -- dod

gate_section "A HEADING WITH NOTHING UNDER IT IS NOT AN ANSWER"
# Checks 1–5 ask only whether a section EXISTS. Without these cases the cheapest
# way past the checker is to keep every heading the template ships and answer
# none of them, which produces a body that reads like a considered one.
gate_expect_in 1 "wiring heading with nothing under it" "$(mangle empty_section 'Wiring')" -- dod \
  --want "wiring required (heading present, nothing under it)"

gate_expect_in 1 "prove-by-breaking heading, nothing under it" "$(mangle empty_section 'Proven by breaking')" -- dod \
  --want "prove it by breaking (heading present, nothing under it)"

gate_expect_in 1 "verification heading, nothing under it" "$(mangle empty_section 'Verification')" -- dod \
  --want "verification (heading present, nothing under it)"

# The honesty section is the one place where forcing words produces ritual rather
# than honesty, so an empty one warns and does not fail. If that ever becomes a
# hard failure, this case says so out loud rather than letting it drift.
gate_expect_in 0 "empty 'not verified' heading warns only" "$(mangle empty_section 'Not verified')" -- dod \
  --want "::warning::'Not verified / left undone' has a heading and nothing under it"

gate_section "CONFIGURATION — absence must fail, never pass"
# The ticket rule depends on a config file. A checker that silently skips a rule
# because its config went missing is the exact defect this script exists to
# catch, wearing the checker's own badge. All three of these must be exit 2.
gate_expect_in 2 "missing prefix file" "$GOOD" -- \
  env TICKET_PREFIX_FILE="$TMP/does-not-exist" bash "$CHECK" --want "is not configured"

: >"$TMP/empty-prefixes"
gate_expect_in 2 "empty prefix file" "$GOOD" -- \
  env TICKET_PREFIX_FILE="$TMP/empty-prefixes" bash "$CHECK" --want "no usable ticket prefixes"

# A prefix is interpolated into an ERE. `.*` here would make the ticket rule
# match every body — silently, and green.
printf '.*\n' >"$TMP/evil-prefixes"
gate_expect_in 2 "regex metacharacter in prefix file" "$GOOD" -- \
  env TICKET_PREFIX_FILE="$TMP/evil-prefixes" bash "$CHECK" --want "invalid ticket prefix"

# The configured prefix is actually the one enforced — otherwise the config is
# decoration and any key would do.
printf 'ACME\n' >"$TMP/acme-prefixes"
gate_expect_in 1 "SS key rejected when only ACME is configured" "$GOOD" -- \
  env TICKET_PREFIX_FILE="$TMP/acme-prefixes" bash "$CHECK" --want "ticket reference"

gate_expect_in 0 "ACME key accepted when ACME is configured" "$(mangle sed 's/PROJ-999/ACME-999/')" -- \
  env TICKET_PREFIX_FILE="$TMP/acme-prefixes" bash "$CHECK"

gate_section "THE TEMPLATE MUST NOT ANSWER FOR THE AUTHOR"
# THE REGRESSION THIS FILE EXISTS FOR SECOND. One project's first cut of the template
# shipped the literal words `no wiring required` PRE-FILLED as body text, so every
# PR asserted them by default: fill the template minimally, touch nothing in the
# wiring section, and the checker said PASSED. In the one section covering the
# most expensive failure shape there is, the default answer was an affirmative
# false claim that reads as considered.
if [ -r "$TEMPLATE" ]; then
  tpl_body="$(awk '
    BEGIN { inc = 0 }
    {
      line = $0; out = ""
      while (1) {
        if (inc) { p = index(line, "-->"); if (p == 0) break; line = substr(line, p + 3); inc = 0 }
        else {
          p = index(line, "<!--")
          if (p == 0) { out = out line; break }
          out = out substr(line, 1, p - 1); line = substr(line, p + 4); inc = 1
        }
      }
      print out
    }' "$TEMPLATE")"

  # grep exits 1 when it finds nothing, so exit 1 here IS the assertion: the
  # phrase must not appear in the template outside an instruction comment.
  gate_expect_in 1 "template does not pre-fill the phrase" "$tpl_body" -- \
    grep -qiF 'no wiring required'

  gate_expect_in 1 "unanswered template is red on wiring" "$(cat "$TEMPLATE")" -- dod \
    --want "wiring required (heading present, nothing under it)"
else
  gate_expect 1 "template is readable" "" -- test -r "$TEMPLATE"
fi

gate_section "MUST PASS (regression: false failures)"
# A checker that goes red on a GOOD body gets deleted. A PR body quoting a fence
# inside a fence (```` wrapping ```yaml) — how you paste the workflow snippet you
# are talking about — desynchronised the old toggle-based fence parser, and from
# that line on every section was mis-classified.
gate_expect_in 0 "fence quoted inside a fence" \
  "$(printf '%s\n' "$GOOD" | sed 's|^## Verification$|Quoting the fixed block verbatim:\n\n````\n```yaml\njobs:\n  build:\n    runs-on: ubuntu-latest\n```\n````\n\n## Verification|')" -- dod

# A section answered with SUBHEADINGS is answered, not empty. The first version
# of the empty-section check ended a section on ANY heading regardless of depth,
# so "## Wiring required" followed immediately by "### Env vars" read as hollow
# and an honest body was rejected — a body shape the naive checker accepted.
# This is the regression direction that matters most: a false FAIL trains people
# to disable the check, and a disabled check is worth less than no check, because
# it still looks like coverage.
gate_expect_in 0 "section answered with ### subheadings" \
  "$(printf '%s\n' "$GOOD" | sed 's|^## Wiring required$|## Wiring required\n\n### Env vars\nMESSAGING_URL on the media Deployment.\n\n### NetworkPolicy\nallow-messaging gains a media podSelector.\n|')" -- dod

gate_expect_in 0 "section answered with #### sub-subheadings" \
  "$(printf '%s\n' "$GOOD" | sed 's|^## Verification$|## Verification\n\n### Local\n#### Unit\ngo test -count=1 ./...\n#### Integration\nmake test-integration\n|')" -- dod

gate_done 26
