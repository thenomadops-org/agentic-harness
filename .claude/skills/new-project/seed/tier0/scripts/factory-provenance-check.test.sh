#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# Regression suite for scripts/factory-provenance-check.sh.

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/gate-test-lib.sh"

CHECK="$HERE/factory-provenance-check.sh"
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT

# Each case gets its own fake repo root, because the script derives ROOT from its
# own location. The script is copied in rather than symlinked so that ROOT/.. is
# the fixture and not the real seed.
mkrepo() { # mkrepo <name> -> echoes root
  local r="$TMP/$1"
  mkdir -p "$r/scripts" "$r/.factory"
  cp "$CHECK" "$r/scripts/"
  printf '%s\n' "$r"
}

run() { bash "$1/scripts/factory-provenance-check.sh"; }

# --- a conformant repo ------------------------------------------------------
GOOD="$(mkrepo good)"
printf '#!/usr/bin/env bash\n# from factory-seed@abc1234\necho hi\n' >"$GOOD/scripts/dod-check.sh"
printf '<!-- from factory-seed@abc1234 -->\n' >"$GOOD/template.md"
printf 'abc1234  scripts/dod-check.sh\nabc1234  template.md\n' >"$GOOD/.factory/MANIFEST"

gate_section "MUST PASS"
gate_expect 0 "stamped files matching the manifest" "" -- run "$GOOD" \
  --want "factory-provenance-check PASSED"

gate_section "MUST FAIL"
# THE ONE the placeholder exists for: an install that never stamped.
#
# The placeholder is built with %s rather than written as one literal, and that
# is load-bearing. The install stamps provenance with a `sed` over the vendored
# tree; when this fixture was one literal string, that sed rewrote THIS LINE too
# and the case silently stopped testing what it names. It was green in the seed
# directory and red only after a real install — which is the entire argument for
# proving an install against a throwaway repo instead of in place.
UN="$(mkrepo unstamped)"
printf '# from factory-seed@%s\n' 'UNSTAMPED' >"$UN/scripts/dod-check.sh"
printf 'abc1234  scripts/dod-check.sh\n' >"$UN/.factory/MANIFEST"
gate_expect 1 "install forgot to stamp" "" -- run "$UN" --want "UNSTAMPED"

# A deleted gate is the loudest drift and, without this, the quietest failure:
# nothing runs, nothing fails, nothing is reported.
DEL="$(mkrepo deleted)"
printf 'abc1234  scripts/dod-check.sh\n' >"$DEL/.factory/MANIFEST"
gate_expect 1 "vendored gate deleted from the tree" "" -- run "$DEL" --want "MISSING"

NOP="$(mkrepo noprov)"
printf '#!/usr/bin/env bash\necho hi\n' >"$NOP/scripts/dod-check.sh"
printf 'abc1234  scripts/dod-check.sh\n' >"$NOP/.factory/MANIFEST"
gate_expect 1 "provenance header stripped" "" -- run "$NOP" --want "NO-PROVENANCE"

MIS="$(mkrepo mismatch)"
printf '# from factory-seed@deadbee\n' >"$MIS/scripts/dod-check.sh"
printf 'abc1234  scripts/dod-check.sh\n' >"$MIS/.factory/MANIFEST"
gate_expect 1 "file and manifest disagree" "" -- run "$MIS" --want "PROVENANCE-MISMATCH"

# A malformed line ALONGSIDE a usable one is a violation: the record lies about
# one file while the manifest itself is still readable.
MAL="$(mkrepo malformed)"
printf '# from factory-seed@abc1234\n' >"$MAL/scripts/dod-check.sh"
printf 'abc1234  scripts/dod-check.sh\njustonefield\n' >"$MAL/.factory/MANIFEST"
gate_expect 1 "malformed line among good ones" "" -- run "$MAL" --want "MANIFEST-MALFORMED"

# A manifest whose every line is malformed is a CONFIG error, not a violation —
# there is nothing to check against, and saying "1 file failed" would misdescribe
# a repo that has recorded nothing at all.
ALLMAL="$(mkrepo allmalformed)"
printf '# from factory-seed@abc1234\n' >"$ALLMAL/scripts/dod-check.sh"
printf 'justonefield\n' >"$ALLMAL/.factory/MANIFEST"
gate_expect 2 "every manifest line malformed" "" -- run "$ALLMAL" --want "MANIFEST-MALFORMED"

gate_section "MUST FAIL — vacuity and config"
NOMAN="$(mkrepo nomanifest)"
rm -f "$NOMAN/.factory/MANIFEST"
gate_expect 2 "no manifest at all" "" -- run "$NOMAN" --want "cannot read"

EMPTY="$(mkrepo emptymanifest)"
printf '# only a comment\n\n' >"$EMPTY/.factory/MANIFEST"
gate_expect 2 "manifest lists nothing" "" -- run "$EMPTY" --want "lists no files"

# ---------------------------------------------------------------------------
# THE DERIVED COUNT FLOOR
#
# Everything above this line audits the manifest against the tree. None of it can
# see a change that edits BOTH — which is one extra line in the diff and the only
# thing an author who wants a gate gone would actually do. These cases are that
# attack, and they need a fixture with real git history, because the floor is
# walked from it rather than written down anywhere.
# ---------------------------------------------------------------------------
mkgitrepo() { # mkgitrepo <name> <n-entries> -> echoes root, one commit holding n files
  local r="$TMP/$1" n="$2" i
  mkdir -p "$r/scripts" "$r/.factory"
  cp "$CHECK" "$r/scripts/"
  git -C "$r" init -q -b main
  git -C "$r" config user.email t@t
  git -C "$r" config user.name t
  : >"$r/.factory/MANIFEST"
  for i in $(seq 1 "$n"); do
    printf '#!/usr/bin/env bash\n# from factory-seed@abc1234\n' >"$r/scripts/gate$i.sh"
    printf 'abc1234  scripts/gate%s.sh\n' "$i" >>"$r/.factory/MANIFEST"
  done
  git -C "$r" add -A >/dev/null 2>&1
  git -C "$r" commit -qm seed >/dev/null 2>&1
  printf '%s\n' "$r"
}

# drop_both <root> <i> — remove gate i from the tree AND its manifest line, the
# way somebody removing a gate on purpose would.
drop_both() {
  rm -f "$1/scripts/gate$2.sh"
  grep -v "scripts/gate$2.sh" "$1/.factory/MANIFEST" >"$1/.factory/M.tmp"
  mv "$1/.factory/M.tmp" "$1/.factory/MANIFEST"
}

gate_section "MUST PASS — the floor holds when nothing was removed"
HWOK="$(mkgitrepo hwok 4)"
gate_expect 0 "count equal to the high-water" "" -- run "$HWOK" \
  --want "COUNT FLOOR: 4 of a high-water 4"

gate_section "MUST FAIL — the count floor"
# THE ONE. This is the case the first version of this script passed at 14 while a
# gate walked out of the repo. Both the file and its manifest line are gone, so
# MISSING cannot fire and the manifest is internally consistent; only a baseline
# outside the manifest can see it.
FELL="$(mkgitrepo fell 4)"
drop_both "$FELL" 4
gate_expect 1 "gate removed from BOTH the tree and the manifest" "" -- run "$FELL" \
  --want "ENTRY-COUNT-FELL"

# A note is the escape hatch, so the escape hatch gets bounds — otherwise it is
# the same hole with a comment character in front of it.
THIN="$(mkgitrepo thin 4)"
drop_both "$THIN" 4
printf '# REMOVED: PROJ-1 4->3 x\n' >>"$THIN/.factory/MANIFEST"
gate_expect 1 "removal note whose reason is a shrug" "" -- run "$THIN" \
  --want "REMOVAL-REASON-THIN"

# The note must name THIS move. Left unbound it is written once and silently
# pre-approves every removal after it.
STALE="$(mkgitrepo stale 4)"
drop_both "$STALE" 4
drop_both "$STALE" 3
printf '# REMOVED: PROJ-1 4->3 dropped one gate for a stated and sufficient reason\n' \
  >>"$STALE/.factory/MANIFEST"
gate_expect 1 "note justifies 4->3 while the manifest went 4->2" "" -- run "$STALE" \
  --want "REMOVAL-NOTE-STALE"

# And it must not survive the move it justified — a note parked on a recovered
# count is a pre-approval for the next removal.
LEFT="$(mkgitrepo left 4)"
printf '# REMOVED: PROJ-1 4->3 dropped one gate for a stated and sufficient reason\n' \
  >>"$LEFT/.factory/MANIFEST"
gate_expect 1 "note left behind after the count recovered" "" -- run "$LEFT" \
  --want "REMOVAL-NOTE-STALE"

gate_section "MUST PASS — a justified removal is allowed through"
JUST="$(mkgitrepo just 4)"
drop_both "$JUST" 4
printf '# REMOVED: PROJ-231 4->3 this repo has no client, so the design-token lint is dead weight\n' \
  >>"$JUST/.factory/MANIFEST"
gate_expect 0 "removal with a bound note and a real reason" "" -- run "$JUST" \
  --want "removal justified"

gate_section "MUST FAIL — the tree testifies"
# The other half of the same attack: drop the LINE and leave the file. The
# manifest is again internally consistent; the subject set has to come from grep.
UNDEC="$(mkgitrepo undec 4)"
grep -v 'scripts/gate4.sh' "$UNDEC/.factory/MANIFEST" >"$UNDEC/.factory/M.tmp"
mv "$UNDEC/.factory/M.tmp" "$UNDEC/.factory/MANIFEST"
printf '# REMOVED: PROJ-231 4->3 this repo has no client, so the design-token lint is dead weight\n' \
  >>"$UNDEC/.factory/MANIFEST"
gate_expect 1 "manifest line dropped, marked file left in the tree" "" -- run "$UNDEC" \
  --want "VENDORED-BUT-UNDECLARED"

gate_section "MUST NOT BE SILENT — the degraded mode"
# Day 0 of a seeded repo, and also what a squashed history looks like. The floor
# genuinely cannot be derived. That must not be spelled the same way as deriving
# one and clearing it, which is the entire failure this file guards against.
gate_expect 0 "no git history says so out loud" "" -- run "$GOOD" \
  --want "COUNT FLOOR: NOT DERIVED"

gate_done 17
