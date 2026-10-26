#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# factory-provenance-check.sh — every vendored gate still says where it came from.
#
# ============================================================================
# WHY THIS EXISTS
# ============================================================================
#
# A vendored seed is a fork the moment it lands. Five repos in, `dod-check.sh`
# has a bug fixed in one of them and nowhere else, and the factory is five
# divergent copies wearing one name — which is worse than no factory, because
# people trust the name.
#
# The cheap half of the fix is provenance: every vendored file records the seed
# revision it came from, so a human can answer "is this the current one?" without
# guessing. That only works if the recording is enforced. A provenance header
# that is optional is absent within a month, and a stamp step that can be skipped
# silently WILL be skipped — which is why the seed ships with the literal marker
# `UNSTAMPED` and this check fails on it. An install that forgot to stamp is red
# on its first PR rather than discovered a year later.
#
# What this does NOT do: compare content against upstream. That needs the network
# and belongs in a scheduled job that OPENS A PR on drift and never auto-merges —
# a gate that changes itself is not a gate. This check answers the offline
# question only: is every file the manifest claims we vendored still here, and
# does it still say what it is.
#
# ============================================================================
# THE MANIFEST IS THE SUBJECT LIST, SO THE MANIFEST CANNOT ALSO BE THE FLOOR
# ============================================================================
#
# The version of this script that shipped first had exactly one vacuity guard —
# `seen -eq 0`. That guard is correct and it is not enough, because everything
# else the check knows comes out of the same file the change is allowed to edit:
#
#     - delete `scripts/dod-check.sh`                     -> MISSING, red. Good.
#     - delete its manifest LINE as well                  -> seen falls 15 -> 14,
#                                                            nothing is MISSING,
#                                                            and the check PASSES.
#
# One extra line in the diff turns the loudest possible drift into a silent one.
# A guard whose expectation is a list the author of the change controls is a
# guard that measures whatever is left.
#
# Two derivations close it, and neither is a number anybody typed here.
#
# 1. A HIGH-WATER COUNT, WALKED FROM THE MANIFEST'S OWN GIT HISTORY. The floor is
#    the most entries this manifest has ever held, computed at run time from
#    `git log` — the same technique the coverage ratchet uses for a coverage
#    floor, and for the same reason: the only honest baseline for "did this
#    change make it worse" is what was there before, and that lives in git rather
#    than in anybody's memory. Removing a vendored gate is then exactly as loud
#    as lowering a coverage floor: possible, deliberate, and it must name the move
#    and the reason on a note in the manifest.
#
# 2. THE TREE TESTIFIES. Every file in the repo that carries a `factory-seed@`
#    marker must appear in the manifest. This closes the other half — dropping a
#    line while leaving the file behind — using a subject set derived by grep
#    rather than read out of the record being audited.
#
# Together: drop the line, the file testifies. Drop the file, MISSING fires. Drop
# both, the count falls below its high-water and the removal must be justified.
#
# WHAT IS STILL OPEN, said plainly rather than left for the next reader to find.
# A high-water walked from history is only as good as the history. Squash the
# manifest's past away, or land the removal in the same commit that first tracks
# the manifest, and there is nothing to compare against. That residual is shared
# with every ratchet of this shape. It is bounded, not closed, and the degraded
# mode below is REPORTED rather than silent — a run that could not derive a floor
# says so on stdout and never spells that the same way as a run that derived one
# and passed.
#
# ============================================================================
# CONFIG — .factory/MANIFEST, written at install, never vendored
# ============================================================================
#
#   <seed-sha><TAB or spaces><repo-relative path>
#
# Example:
#   a1b2c3d4  scripts/dod-check.sh
#   a1b2c3d4  .github/pull_request_template.md
#
# A removal note, when the entry count goes down, on a line of its own:
#
#   # REMOVED: PROJ-231 15->14 dropped the design-token lint, this repo has no client
#
# The `<from>-><to>` is not decoration. Without it the note is a property of the
# FILE rather than of the MOVE, so the first removal writes it and every later
# removal is covered by somebody else's sentence. `<to>` must equal the entry
# count the manifest actually has; `<from>` must equal the high-water it is
# coming down from.
#
# Usage:  scripts/factory-provenance-check.sh
# Exit:   0 conformant · 1 a violation · 2 config error

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="${FACTORY_MANIFEST:-$ROOT/.factory/MANIFEST}"

# A reason, not a shrug. Same bounds as the coverage ratchet's lowering note.
REMOVE_MIN_REASON_CHARS=16
REMOVE_MIN_REASON_WORDS=3

if [ ! -r "$MANIFEST" ]; then
  echo "::error::factory-provenance-check: cannot read '$MANIFEST'" >&2
  echo "          The seed was installed without recording what it installed. Write one" >&2
  echo "          '<seed-sha>  <path>' line per vendored file — see the new-project skill." >&2
  exit 2
fi

seen=0
bad=0

while IFS= read -r line || [ -n "$line" ]; do
  line="${line%%#*}"
  [ -z "${line//[[:space:]]/}" ] && continue

  sha="$(printf '%s' "$line" | awk '{print $1}')"
  path="$(printf '%s' "$line" | awk '{$1=""; sub(/^[ \t]+/, ""); print}')"

  if [ -z "$sha" ] || [ -z "$path" ]; then
    echo "::error::MANIFEST-MALFORMED  '$line' — want '<seed-sha>  <path>'" >&2
    bad=$((bad + 1))
    continue
  fi

  seen=$((seen + 1))
  full="$ROOT/$path"

  # A vendored gate that was DELETED is the loudest possible drift, and without
  # this it is the quietest: nothing runs, nothing fails, nothing is reported.
  if [ ! -r "$full" ]; then
    echo "::error::MISSING  $path is in the manifest and not in the tree." >&2
    echo "          A vendored gate that was deleted removes its own failure mode too." >&2
    bad=$((bad + 1))
    continue
  fi

  marker="$(grep -m1 -oE 'factory-seed@[A-Za-z0-9._-]+' -- "$full" 2>/dev/null || true)"

  if [ -z "$marker" ]; then
    echo "::error::NO-PROVENANCE  $path carries no 'factory-seed@<sha>' marker." >&2
    echo "          Restore it on line 2. Without it nobody can tell a current copy from" >&2
    echo "          a two-year-old one, and both look identical in review." >&2
    bad=$((bad + 1))
    continue
  fi

  got="${marker#factory-seed@}"

  if [ "$got" = "UNSTAMPED" ]; then
    echo "::error::UNSTAMPED  $path still carries the seed's placeholder." >&2
    echo "          The install did not stamp the seed revision. Stamp it now — an install" >&2
    echo "          that can skip this step silently will skip it." >&2
    bad=$((bad + 1))
    continue
  fi

  if [ "$got" != "$sha" ]; then
    echo "::error::PROVENANCE-MISMATCH  $path says factory-seed@$got, manifest says $sha." >&2
    echo "          Either the file was updated without updating the manifest, or the" >&2
    echo "          manifest was edited without updating the file. Both make the record lie." >&2
    bad=$((bad + 1))
    continue
  fi
done < "$MANIFEST"

# Vacuity: a manifest that lists nothing is not a clean repo, it is an unconfigured
# one, and it would otherwise report success having examined no files.
if [ "$seen" -eq 0 ]; then
  echo "::error::factory-provenance-check: '$MANIFEST' lists no files. A check that" >&2
  echo "          examined nothing has not passed." >&2
  exit 2
fi

# ============================================================================
# DERIVATION 2 — the tree testifies
# ============================================================================
#
# Subjects found by grep, not read out of the record being audited. A file that
# carries the marker and is not in the manifest is either a vendored gate whose
# line was dropped, or a copy nobody recorded; both make the manifest a lie about
# what this repo took from the seed.
#
# Scoped to git's index when this is a work tree, so a stray copy under a build
# directory or someone's scratch folder is not a finding. Outside git it walks the
# tree and prunes the usual noise, because a check that cannot run at all outside
# CI is a check nobody runs locally.
declare -a tree_files=()
if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  while IFS= read -r f; do [ -n "$f" ] && tree_files+=("$f"); done < <(
    git -C "$ROOT" grep -l -I -E 'factory-seed@[A-Za-z0-9._-]+' -- . 2>/dev/null || true
  )
else
  # `cd && grep || true` would let the `|| true` swallow a FAILED cd as well as
  # grep's empty-result exit 1 — shellcheck SC2015, and here it would mean
  # "found nothing" for a root that could not be entered. Separate statements.
  while IFS= read -r f; do [ -n "$f" ] && tree_files+=("${f#./}"); done < <(
    cd "$ROOT" || exit 2
    grep -rl -I -E 'factory-seed@[A-Za-z0-9._-]+' . \
      --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=vendor 2>/dev/null || true
  )
fi

# The manifest paths, as a newline-delimited blob for exact-line matching.
declared="$(sed 's/#.*$//' "$MANIFEST" | awk 'NF >= 2 { $1=""; sub(/^[ \t]+/, ""); print }')"

for f in ${tree_files+"${tree_files[@]}"}; do
  # The check and its own suite carry the marker by construction and are the
  # thing doing the asking; requiring them to declare themselves is circular.
  case "$f" in
  scripts/factory-provenance-check.sh | scripts/factory-provenance-check.test.sh) continue ;;
  esac
  if ! printf '%s\n' "$declared" | grep -qxF "$f"; then
    echo "::error::VENDORED-BUT-UNDECLARED  $f carries a factory-seed marker and is" >&2
    echo "          not in the manifest. Either its line was dropped — which is how a" >&2
    echo "          vendored gate leaves the record without leaving the tree — or it was" >&2
    echo "          copied in without being recorded. Add the line, or remove the marker." >&2
    bad=$((bad + 1))
  fi
done

# ============================================================================
# DERIVATION 1 — the high-water entry count, walked from git history
# ============================================================================
count_entries_blob() { # reads a manifest on stdin -> number of well-formed entries
  sed 's/#.*$//' | awk 'NF >= 2 { n++ } END { print n + 0 }'
}

high_water=""
hw_source=""
if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  # The manifest's path as git knows it. `git log` on an untracked path returns
  # nothing and exits 0, which is indistinguishable from "no history" — so the
  # tracked-ness is asked directly rather than inferred from an empty log.
  man_rel="$(git -C "$ROOT" ls-files --full-name --error-unmatch -- "$MANIFEST" 2>/dev/null || true)"
  if [ -n "$man_rel" ]; then
    hw=0
    while IFS= read -r rev; do
      [ -n "$rev" ] || continue
      c="$(git -C "$ROOT" show "$rev:$man_rel" 2>/dev/null | count_entries_blob)"
      [ "${c:-0}" -gt "$hw" ] && hw="$c"
    done < <(git -C "$ROOT" log --format=%H -- "$man_rel" 2>/dev/null || true)
    if [ "$hw" -gt 0 ]; then
      high_water="$hw"
      hw_source="$(git -C "$ROOT" log --oneline -1 --format=%h -- "$man_rel" 2>/dev/null)"
    fi
  fi
fi

if [ -z "$high_water" ]; then
  # DEGRADED, AND SAID SO. This is the day-0 case — the manifest is written by the
  # install and has no history until its first commit — and it is also what a
  # squashed history looks like. It must never print the same thing as a run that
  # derived a floor and cleared it, because "the count check did not run" and "the
  # count check passed" are the two sentences this whole file exists to keep apart.
  echo "COUNT FLOOR: NOT DERIVED — '$MANIFEST' has no git history here, so there is"
  echo "  no previous entry count to compare against. Nothing checked the count on"
  echo "  this run. It starts working on the commit after this one."
else
  removal_note="$(grep -m1 -oE '# REMOVED:[^#]*' "$MANIFEST" 2>/dev/null || true)"
  if [ "$seen" -lt "$high_water" ]; then
    nk="$(printf '%s' "$removal_note" | sed -nE 's/.*# REMOVED:[[:space:]]+([A-Z][A-Z0-9]*-[0-9]+).*/\1/p')"
    nf="$(printf '%s' "$removal_note" | sed -nE 's/.*# REMOVED:[[:space:]]+[A-Z][A-Z0-9]*-[0-9]+[[:space:]]+([0-9]+)->([0-9]+).*/\1/p')"
    nt="$(printf '%s' "$removal_note" | sed -nE 's/.*# REMOVED:[[:space:]]+[A-Z][A-Z0-9]*-[0-9]+[[:space:]]+([0-9]+)->([0-9]+).*/\2/p')"
    nr="$(printf '%s' "$removal_note" | sed -nE 's/.*# REMOVED:[[:space:]]+[A-Z][A-Z0-9]*-[0-9]+[[:space:]]+[0-9]+->[0-9]+[[:space:]]+(.*)$/\1/p')"
    nr="${nr%"${nr##*[![:space:]]}"}"

    if [ -z "$nk" ] || [ -z "$nf" ] || [ -z "$nt" ]; then
      echo "::error::ENTRY-COUNT-FELL  the manifest lists $seen file(s); it has held as" >&2
      echo "          many as $high_water (high-water walked from its git history). A" >&2
      echo "          vendored gate left the record. That is allowed and it is not quiet:" >&2
      echo "          add a line to the manifest reading" >&2
      echo "            # REMOVED: <TICKET-nnn> $high_water->$seen <why, in a sentence>" >&2
      bad=$((bad + 1))
    elif [ "$nt" != "$seen" ] || [ "$nf" != "$high_water" ]; then
      echo "::error::REMOVAL-NOTE-STALE  the manifest went $high_water -> $seen, but its" >&2
      echo "          note justifies $nf->$nt. A note justifies the move it names, not the" >&2
      echo "          file it is parked on — left alone it would cover every future removal" >&2
      echo "          with the reason somebody wrote for the first one. Rewrite it as" >&2
      echo "          '# REMOVED: $nk $high_water->$seen <why>'." >&2
      bad=$((bad + 1))
    elif [ "${#nr}" -lt "$REMOVE_MIN_REASON_CHARS" ] ||
      [ "$(printf '%s\n' "$nr" | wc -w | tr -d ' ')" -lt "$REMOVE_MIN_REASON_WORDS" ]; then
      echo "::error::REMOVAL-REASON-THIN  '$nr' is not a reason for dropping a vendored" >&2
      echo "          gate (want at least $REMOVE_MIN_REASON_CHARS chars and $REMOVE_MIN_REASON_WORDS words). The next person" >&2
      echo "          to read this is deciding whether to trust it. Write the sentence." >&2
      bad=$((bad + 1))
    else
      echo "COUNT FLOOR: $seen of a high-water $high_water — removal justified: $removal_note"
    fi
  else
    # A stale note left behind after the count recovered is the same defect one
    # move later: it sits there pre-approving the next removal.
    if [ -n "$removal_note" ]; then
      nt="$(printf '%s' "$removal_note" | sed -nE 's/.*[0-9]+->([0-9]+).*/\1/p')"
      if [ -n "$nt" ] && [ "$nt" != "$seen" ]; then
        echo "::error::REMOVAL-NOTE-STALE  the manifest lists $seen file(s) and carries a" >&2
        echo "          note justifying a move to $nt. It was written for a different move" >&2
        echo "          and is now parked on this one. Delete it or rewrite it." >&2
        bad=$((bad + 1))
      fi
    fi
    [ "$bad" -eq 0 ] && echo "COUNT FLOOR: $seen of a high-water $high_water ($hw_source) — not below."
  fi
fi

if [ "$bad" -ne 0 ]; then
  echo "" >&2
  echo "factory-provenance-check FAILED — $bad violation(s) across $seen vendored file(s)." >&2
  exit 1
fi

echo "factory-provenance-check PASSED — $seen vendored file(s), all present and stamped."
