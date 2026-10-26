#!/usr/bin/env bash
# control-band.test.sh — the regression suite for tools/control-band/control-band.py.
#
# The detector's dominant failure mode is NEVER FIRING, and the reason that mode
# is dangerous is that its output — "within band" — is the output you also get
# from a healthy repo. You cannot tell a working detector from a dead one by
# looking at a green run. So this suite is built in three layers:
#
#   1. THE BANDS FIRE. A series engineered to sit at z=2.5 must report DIAGNOSE
#      and exit 20; one at z=3.5 must report ACT and exit 30. Every fixture's
#      z-score is computed by hand in the comment above it, so a case that
#      starts passing for a new reason is visible in review.
#
#   2. THE BANDS DO NOT OVER-FIRE. A normal day, and — separately — a rate that
#      DROPS four sigma, must both be WITHIN. A detector that fires on
#      everything is as useless as one that fires on nothing, and it is the
#      easier of the two to ship by accident when tuning the first layer.
#
#   3. THE FIRST TWO LAYERS ARE LOAD-BEARING, PROVED BY MUTATION. Sections
#      MUTATION 1..7 copy the script, break one specific thing in the maths,
#      and assert the suite's own claims go red. Without this, layers 1 and 2
#      are assertions that the current code does what the current code does.
#      A test you have not watched fail is a test you do not know you have.
#
# Every case asserts the TYPED CODE in the message as well as the exit status,
# because several distinct refusals share exit 3 (NO-BUCKETS, NO-DECIDED-RUNS,
# INSUFFICIENT-BASELINE) and $? alone cannot say which one fired.
#
# Fixtures are generated into a temp directory, never committed, so no checked-in
# testdata/ can drift away from what these cases claim.
#
# Needs: bash, python3. No Docker, no network, no gh.
#
# Usage: bash tools/control-band/control-band.test.sh
# Exit:  0 = every case behaved · 1 = a case did not

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BAND="$HERE/control-band.py"

pass=0
fail=0
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Every case runs with the ACT flag explicitly cleared unless it sets it, so a
# developer's exported flag cannot change what this suite proves.
unset CI_HEALTH_BAND_ACT_ENABLED

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

# series <file> <bucket:total:failures> ...
series() {
  local out="$1"; shift
  {
    echo '{"metric":"ci-failure-rate","branch":"main","generated":"2026-08-14T00:00:00+00:00","runs_seen":13000,"buckets":['
    local first=1 spec b t f
    for spec in "$@"; do
      IFS=':' read -r b t f <<<"$spec"
      [ $first -eq 1 ] || echo ','
      first=0
      printf '{"bucket":"%s","total":%s,"failures":%s}' "$b" "$t" "$f"
    done
    echo ']}'
  } >"$out"
}

# alternating <file> <current-failures-per-1000> — the canonical baseline.
#
# Twelve days alternating 4% and 6% failures: mean = 0.05 and the POPULATION
# sigma is exactly 0.01. The argument is failures PER THOUSAND runs, so
# `alternating f 75` is a 7.5% current day.
#
# The real bucket size is one MILLION runs, which is deliberately absurd. It is
# chosen so both volume-dependent corrections to sigma vanish here — the
# resolution floor is 1e-6 and the sampling sigma 6.9e-5, against a baseline
# sigma of 1e-2 — which isolates the baseline-spread half of the formula and
# lets every case below assert a round z a reader can check by hand:
#
#     z = (current/1000 - 0.05) / 0.01
#
# The two corrections get their own sections, at realistic volumes, further
# down. Keeping them out of THIS fixture is what makes a failure here mean
# "the baseline maths moved" rather than "something about volume moved".
alternating() {
  local out="$1" cur="$2" i specs=()
  for i in $(seq 1 12); do
    if [ $((i % 2)) -eq 1 ]; then specs+=("$(printf '2026-08-%02d:1000000:40000' "$i")")
    else specs+=("$(printf '2026-08-%02d:1000000:60000' "$i")"); fi
  done
  specs+=("2026-08-13:1000000:$((cur * 1000))")
  series "$out" "${specs[@]}"
}

# expect <label> <expected-exit> <needle> <script> <args...>
expect() {
  local label="$1" want="$2" needle="$3" script="$4"; shift 4
  local out rc
  out="$(python3 "$script" "$@" 2>&1)"; rc=$?
  if [ "$rc" != "$want" ]; then
    echo "FAIL  $label — expected exit $want, got $rc"
    printf '%s\n' "$out" | sed 's/^/        /'
    fail=$((fail + 1)); return
  fi
  if [ -n "$needle" ] && ! grep -qF -- "$needle" <<<"$out"; then
    echo "FAIL  $label — exit $rc was right but the message did not carry: $needle"
    printf '%s\n' "$out" | sed 's/^/        /'
    fail=$((fail + 1)); return
  fi
  echo "ok    $label"
  pass=$((pass + 1))
}

ok() { echo "ok    $1"; pass=$((pass + 1)); }
no() { echo "FAIL  $1"; shift; [ $# -gt 0 ] && printf '%s\n' "$*" | sed 's/^/        /'; fail=$((fail + 1)); }

# ===========================================================================
echo "== the script's own selfcheck must pass =="
# ===========================================================================
# The shipped `selfcheck` subcommand is the thing CI runs before it trusts a
# scheduled reading. If it does not pass here it must not pass there.
expect "selfcheck: every built-in fixture behaves" 0 "all 8 cases behaved" "$BAND" selfcheck
expect "selfcheck names the ACT fixture explicitly" 0 "must reach ACT" "$BAND" selfcheck

# ===========================================================================
echo
echo "== LAYER 1: the detector must FIRE =="
# ===========================================================================

# 65 failures/1000 = 6.5% -> z = (0.065 - 0.05) / 0.01 = 1.5 -> OBSERVE
alternating "$WORK/observe.json" 65
expect "1.5 sigma reaches OBSERVE" 10 "OBSERVE" "$BAND" band --series "$WORK/observe.json"

# 75/1000 = 7.5% -> z = 2.5 -> DIAGNOSE
alternating "$WORK/diagnose.json" 75
expect "2.5 sigma reaches DIAGNOSE" 20 "DIAGNOSE" "$BAND" band --series "$WORK/diagnose.json"
expect "and reports the z it computed" 20 "z=2.50" "$BAND" band --series "$WORK/diagnose.json"

# 85/1000 = 8.5% -> z = 3.5 -> ACT
alternating "$WORK/act.json" 85
expect "3.5 sigma reaches ACT" 30 "ACT" "$BAND" band --series "$WORK/act.json"
expect "and reports the z it computed" 30 "z=3.50" "$BAND" band --series "$WORK/act.json"

# The EXACT tier boundaries (z of precisely 1.0, 2.0, 3.0) are asserted in the
# sigma-floor section below rather than here. On a spotless baseline the mean is
# 0, which zeroes the sampling term, so sigma is exactly 1/n and the z-scores
# are exact rather than exact-to-two-decimals. A `>=` boundary has to be tested
# where the arithmetic is exact, or the test is really testing float formatting.

# ===========================================================================
echo
echo "== LAYER 2: the detector must NOT over-fire =="
# ===========================================================================

# 55/1000 = 5.5% -> z = 0.5 -> WITHIN
alternating "$WORK/within.json" 55
expect "a normal day stays WITHIN, exit 0" 0 "WITHIN" "$BAND" band --series "$WORK/within.json"

# 10/1000 = 1% -> z = -4.0. CI got much BETTER. The band is one-sided; this
# must not page anybody. A detector that fires on improvement gets muted, and a
# muted detector is the same as no detector.
alternating "$WORK/drop.json" 10
expect "a four-sigma IMPROVEMENT is WITHIN — the band is one-sided" 0 "WITHIN" \
  "$BAND" band --series "$WORK/drop.json"
expect "and the negative z is reported, not hidden" 0 "z=-4.00" "$BAND" band --series "$WORK/drop.json"

# ===========================================================================
echo
echo "== 'could not measure' must never render as 'no anomaly' =="
# ===========================================================================
# Exit 3, every one of them, with a distinct code. This is the conflation that
# would make every other case in this file worthless: a detector that answers
# "all clear" when it examined nothing is precisely the guard-that-inspects-
# nothing defect that ships routinely — on one project a wiring test sat unwired
# and permanently passing, and thirty-five tests on the same tree skipped
# themselves on an unset environment variable while their jobs went green.

series "$WORK/empty.json"
expect "an empty series refuses" 3 "NO-BUCKETS" "$BAND" band --series "$WORK/empty.json"
expect "and says so in as many words" 3 "NOT 'no anomaly'" "$BAND" band --series "$WORK/empty.json"

zero=()
for i in $(seq 1 12); do zero+=("$(printf '2026-08-%02d:0:0' "$i")"); done
series "$WORK/zero.json" "${zero[@]}"
expect "days with no decided runs refuse — 0 runs is not a 0% failure rate" 3 \
  "NO-DECIDED-RUNS" "$BAND" band --series "$WORK/zero.json"

series "$WORK/short.json" 2026-08-01:100:5 2026-08-02:100:5 2026-08-03:100:5 2026-08-04:100:99
expect "too little history refuses rather than passing" 3 "INSUFFICIENT-BASELINE" \
  "$BAND" band --series "$WORK/short.json"

# ...and that fixture matters: its current day is a 99% failure rate. A
# short-baseline series is exactly when a naive implementation is most tempted
# to answer, and exactly when its answer is worthless.
#
# The calm twin is what MUTATION 3 uses. Three unremarkable days and a fourth
# just like them: with the baseline guard gone this computes a serene z=0 over
# almost no history and exits 0 — "could not measure" wearing "all clear"'s
# clothes, which is the exact conflation this whole section exists to forbid.
series "$WORK/short-calm.json" 2026-08-01:100:5 2026-08-02:100:5 2026-08-03:100:5 2026-08-04:100:5
expect "and refuses a CALM short series too — it is the history that is missing, not the drama" 3 \
  "INSUFFICIENT-BASELINE" "$BAND" band --series "$WORK/short-calm.json"

# ===========================================================================
echo
echo "== malformed input is refused, never guessed at =="
# ===========================================================================

printf 'not json at all\n' >"$WORK/bad.json"
expect "non-JSON refuses with exit 2" 2 "MALFORMED-SERIES" "$BAND" band --series "$WORK/bad.json"

printf '{"buckets":"nope"}\n' >"$WORK/nolist.json"
expect "a 'buckets' that is not a list refuses" 2 "MALFORMED-SERIES" "$BAND" band --series "$WORK/nolist.json"

series "$WORK/impossible.json" 2026-08-01:10:99
expect "failures > total refuses" 2 "MALFORMED-BUCKET" "$BAND" band --series "$WORK/impossible.json"

series "$WORK/neg.json" 2026-08-01:-5:0
expect "a negative total refuses" 2 "MALFORMED-BUCKET" "$BAND" band --series "$WORK/neg.json"

# Order is load-bearing: the LAST bucket is the observation and the rest are the
# baseline. A shuffled series would produce a confident z against the wrong
# current value with no symptom at all. So it is a refusal, not a silent sort.
series "$WORK/unsorted.json" 2026-08-05:100:5 2026-08-01:100:5 2026-08-09:100:5
expect "an out-of-order series refuses rather than being sorted for you" 2 \
  "UNSORTED-SERIES" "$BAND" band --series "$WORK/unsorted.json"

series "$WORK/dupe.json" 2026-08-01:100:5 2026-08-01:100:5
expect "a duplicated bucket label refuses too" 2 "UNSORTED-SERIES" "$BAND" band --series "$WORK/dupe.json"

# ===========================================================================
echo
echo "== the sigma floor: a spotless baseline must not silence the detector =="
# ===========================================================================
# Twelve days of 40 decided runs and ZERO failures. mean = 0, sigma_obs = 0.
# Without a floor this is a division by zero, and 'fixed' with a guard clause it
# is a permanent no-breach on exactly the repo state where the first failure
# matters most. resolution_sigma = 1/40 = 0.025 — one failure's worth of rate.

clean=()
for i in $(seq 1 12); do clean+=("$(printf '2026-08-%02d:40:0' "$i")"); done

series "$WORK/clean-0.json" "${clean[@]}" 2026-08-13:40:0
expect "a spotless day after a spotless fortnight is WITHIN" 0 "WITHIN" \
  "$BAND" band --series "$WORK/clean-0.json"

series "$WORK/clean-1.json" "${clean[@]}" 2026-08-13:40:1
expect "ONE failure after a spotless fortnight is z=1.0, OBSERVE" 10 "OBSERVE" \
  "$BAND" band --series "$WORK/clean-1.json"

series "$WORK/clean-2.json" "${clean[@]}" 2026-08-13:40:2
expect "TWO failures is z=2.0, DIAGNOSE" 20 "DIAGNOSE" "$BAND" band --series "$WORK/clean-2.json"

series "$WORK/clean-3.json" "${clean[@]}" 2026-08-13:40:3
expect "THREE failures after a spotless fortnight is z=3.0, ACT" 30 "ACT" \
  "$BAND" band --series "$WORK/clean-3.json"
expect "and the run says the sigma was a resolution floor, not a measured spread" 30 \
  "sigma floored" "$BAND" band --series "$WORK/clean-3.json"

# The three cases above are also THE EXACT TIER BOUNDARIES. A spotless baseline
# has mean 0, which zeroes the sampling term, so sigma is exactly 1/40 and the
# z-scores are exactly 1.0, 2.0 and 3.0 — no float slack. A tier is `>=`, so
# each must land ON its tier and not one below; that is what MUTATION 4 breaks.

# The floor must be INERT when there is real variance — otherwise it is not a
# floor, it is a second, hidden threshold. The alternating fixture's sigma_obs
# (0.01) is 10x its resolution_sigma (0.001), so no floor note may appear.
out="$(python3 "$BAND" band --series "$WORK/act.json" 2>&1)"
if grep -qF "sigma floored" <<<"$out"; then
  no "the floor must stay inert when the baseline has real variance" "$out"
else
  ok "the floor stays inert when the baseline has real variance"
fi

# ===========================================================================
echo
echo "== the sampling term: a thin day cannot resolve a rate =="
# ===========================================================================
# THIS SECTION EXISTS BECAUSE OF A REAL FALSE POSITIVE, not a thought
# experiment. The first `collect` against the project this was extracted from
# returned 21 real days, and the first draft of the band read the most recent
# one — 1 failure in 12 decided runs — as z=2.74, DIAGNOSE. At n=12 the binomial standard error alone is 4.8%;
# one failure on a quiet Tuesday is entirely ordinary. A detector that files a
# triage intent for that gets muted inside a fortnight, and a muted detector
# ends up in the same place as a dead one.
#
# The baseline here is twelve 400-run days alternating 8 and 24 failures:
# rates 0.02 / 0.06, mean 0.04, sigma_obs 0.02.

mid=()
for i in $(seq 1 12); do
  if [ $((i % 2)) -eq 1 ]; then mid+=("$(printf '2026-08-%02d:400:8' "$i")")
  else mid+=("$(printf '2026-08-%02d:400:24' "$i")"); fi
done

# THE PAIR THAT MAKES THE POINT: the SAME failure rate (8.3%), twice.
#
#   12 runs, 1 failure   -> sigma 0.1007 -> z=0.43 -> WITHIN
#   1000 runs, 83 fails  -> sigma 0.0209 -> z=2.05 -> DIAGNOSE
#
# Identical rates, opposite verdicts, because only one of the two days carries
# enough runs to mean anything. A band that cannot tell those apart is not
# measuring CI health, it is measuring how quiet the day was.
series "$WORK/thin.json" "${mid[@]}" 2026-08-13:12:1
expect "one failure in a TWELVE-run day is not a signal" 0 "WITHIN" \
  "$BAND" band --series "$WORK/thin.json"

series "$WORK/fat.json" "${mid[@]}" 2026-08-13:1000:83
expect "the SAME 8.3% rate over a THOUSAND runs is DIAGNOSE" 20 "DIAGNOSE" \
  "$BAND" band --series "$WORK/fat.json"

# The mid-volume case, where the sampling term is doing work that neither the
# resolution floor nor the baseline spread would do alone: at n=100 the floor
# (0.01) is below sigma_obs (0.02) and so inert, while the sampling sigma
# (0.0196) is comparable to sigma_obs and pushes the total to 0.028.
# With the term:    z = 0.05 / 0.028 = 1.79 -> OBSERVE
# Without it:       z = 0.05 / 0.020 = 2.50 -> DIAGNOSE   (see MUTATION 5)
series "$WORK/midvol.json" "${mid[@]}" 2026-08-13:100:9
expect "9 failures in 100 runs is OBSERVE, not DIAGNOSE" 10 "OBSERVE" \
  "$BAND" band --series "$WORK/midvol.json"

# THE REGRESSION PIN: an actual 21-day series, verbatim, from the project this
# was extracted from. This is the data that produced the false positive. If a
# future change to the band maths makes the last day breach again, this goes red
# with real numbers rather than with a fixture somebody can argue with. It is
# kept rather than regenerated on purpose — a fixture derived from the code it
# tests proves nothing.
series "$WORK/real.json" \
  2026-08-19:413:26 2026-08-20:665:42 2026-08-21:512:18 2026-08-22:449:6 \
  2026-08-23:452:10 2026-08-24:146:7 2026-08-25:5:0 2026-08-26:313:11 \
  2026-08-27:491:2 2026-08-28:767:7 2026-08-29:252:6 2026-08-30:393:19 \
  2026-08-31:366:5 2026-09-01:40:1 2026-09-02:12:1
expect "the real 2026-09-02 reading (1 of 12) does NOT breach" 0 "WITHIN" \
  "$BAND" band --series "$WORK/real.json"
expect "and its z is reported, so a regression is visible not just red" 0 "z=0.57" \
  "$BAND" band --series "$WORK/real.json"

# ===========================================================================
echo
echo "== a breach is written back as an intent-shaped artifact =="
# ===========================================================================

TRIAGE="$WORK/triage"

# WITHIN and OBSERVE are log-only. An artifact for every mild wobble is how a
# triage queue becomes a feed nobody reads.
expect "WITHIN writes nothing" 0 "log only" "$BAND" report --series "$WORK/within.json" --triage-dir "$TRIAGE"
expect "OBSERVE writes nothing either" 10 "log only" "$BAND" report --series "$WORK/observe.json" --triage-dir "$TRIAGE"
if [ -d "$TRIAGE" ] && [ -n "$(ls -A "$TRIAGE" 2>/dev/null)" ]; then
  no "the log-only tiers must not have written a file" "$(ls -A "$TRIAGE")"
else
  ok "the log-only tiers wrote no file"
fi

expect "DIAGNOSE writes a triage intent" 20 "wrote triage intent" \
  "$BAND" report --series "$WORK/diagnose.json" --triage-dir "$TRIAGE"

ART="$TRIAGE/2026-08-13-ci-failure-rate.md"
if [ ! -f "$ART" ]; then
  no "the artifact must land at the documented path" "$ART missing"
else
  ok "the artifact lands at <bucket>-<metric>.md"
  # It must be an INTENT, not a log line: the template's sections and the
  # precedence rule have to travel with every copy, or the artifact cannot flow
  # through the same pipeline a human problem statement does.
  for needle in \
    "spec of record wins over anything here" \
    "## Problem" \
    "## Proposed outcome" \
    "## Affected" \
    "## Constraints" \
    "## Open questions" \
    "## What this is NOT" \
    "## Provenance"; do
    if grep -qF -- "$needle" "$ART"; then ok "the artifact carries: $needle"
    else no "the artifact is missing an intent section: $needle"; fi
  done
  # The numbers must be IN it — an artifact that says "CI was bad" without the
  # reading is an alert with extra steps.
  if grep -qF "z = 2.50" "$ART"; then ok "the artifact carries the z-score"
  else no "the artifact does not carry the z-score" "$(grep -n 'z =' "$ART" || true)"; fi
  if grep -qF "**75000 of 1000000** decided" "$ART"; then ok "the artifact carries the raw counts"
  else no "the artifact does not carry the raw counts" "$(grep -n 'decided' "$ART" || true)"; fi
  # And it must NOT name a cause. The detector does not know one, and a
  # confident guess anchors the next reader onto the wrong mechanism.
  if grep -qF "does not know a cause" "$ART"; then ok "the artifact refuses to name a cause"
  else no "the artifact must state that it is not a diagnosis"; fi
fi

# ===========================================================================
echo
echo "== the 3-sigma ACT tier defaults OFF, and says so =="
# ===========================================================================
# The exit code reports the MEASUREMENT; the flag gates the EFFECT. Turning the
# flag off must not change what the detector says it saw — otherwise a disabled
# feature becomes an invisible one.

rm -rf "$TRIAGE"
out="$(python3 "$BAND" report --series "$WORK/act.json" --triage-dir "$TRIAGE" 2>&1)"; rc=$?
if [ "$rc" != 30 ]; then
  no "a 3-sigma breach must still exit 30 with acting disabled" "got $rc"
else ok "a 3-sigma breach still exits 30 with acting disabled"; fi
if grep -qF "no PR may be opened" <<<"$out"; then
  ok "and says plainly that it may not act"
else no "the disabled ACT tier must say so on stderr" "$out"; fi

ACT_ART="$TRIAGE/2026-08-13-ci-failure-rate.md"
if grep -qF "ACT tier is DISABLED (default)" "$ACT_ART" 2>/dev/null; then
  ok "and the artifact records that acting was disabled"
else no "the artifact must record the ACT tier's state" "$(head -1 "$ACT_ART" 2>/dev/null)"; fi

rm -rf "$TRIAGE"
out="$(CI_HEALTH_BAND_ACT_ENABLED=true python3 "$BAND" report --series "$WORK/act.json" \
  --triage-dir "$TRIAGE" 2>&1)"; rc=$?
if [ "$rc" != 30 ]; then
  no "the exit code must not change when the flag is set" "got $rc"
else ok "the exit code is identical with the flag set — it reports the measurement"; fi
if grep -qF "ACT tier is ENABLED" "$ACT_ART" 2>/dev/null; then
  ok "the artifact records the enabled state when the flag is set"
else no "the artifact must record the enabled state" "$(grep -n 'ACT tier' "$ACT_ART" 2>/dev/null)"; fi

# Only the literal string `true` enables it. A flag that turns on for "1", "yes"
# or "TRUE " is a flag that turns on by accident.
rm -rf "$TRIAGE"
out="$(CI_HEALTH_BAND_ACT_ENABLED=1 python3 "$BAND" report --series "$WORK/act.json" \
  --triage-dir "$TRIAGE" 2>&1)"
if grep -qF "ACT tier is DISABLED (default)" "$ACT_ART" 2>/dev/null; then
  ok "CI_HEALTH_BAND_ACT_ENABLED=1 does NOT enable acting"
else no "only the literal 'true' may enable the ACT tier" "$out"; fi

rm -rf "$TRIAGE"
expect "--dry-run reports the path without writing" 20 "would write" \
  "$BAND" report --series "$WORK/diagnose.json" --triage-dir "$TRIAGE" --dry-run
if [ -e "$TRIAGE" ]; then no "--dry-run must not create the triage directory"
else ok "--dry-run created nothing"; fi

# ===========================================================================
echo
echo "== MUTATION: prove the cases above are load-bearing =="
# ===========================================================================
# Everything above asserts that the current code does what the current code
# does — until these three sections. Each copies the script, breaks ONE thing,
# and asserts the suite's own claims turn red. A test nobody has watched fail
# is a test nobody knows they have.

mutate() { # mutate <name> <sed-expr>
  local name="$1" expr="$2"
  cp "$BAND" "$WORK/$name.py"
  sed -i "$expr" "$WORK/$name.py"
  if cmp -s "$BAND" "$WORK/$name.py"; then
    no "MUTATION $name did not change the file — the sed no longer matches, so this section proves nothing"
    return 1
  fi
  return 0
}

# --- MUTATION 1: the standard deviation stops being computed. ---------------
# `pstdev` returns a constant 1.0, so sigma dwarfs every real rate and z
# collapses toward zero. This is the "detector that never fires" failure in its
# purest form, and it must be caught by LAYER 1 and by the shipped selfcheck.
if mutate m1 's|    return math.sqrt(sum((x - m) \*\* 2 for x in xs) / len(xs))|    return 1.0|'; then
  expect "M1: with the stdev broken, the 3-sigma case stops breaching (LAYER 1 goes red)" 0 \
    "WITHIN" "$WORK/m1.py" band --series "$WORK/act.json"
  expect "M1: and the shipped selfcheck refuses to certify the build" 1 \
    "detector is NOT known to fire" "$WORK/m1.py" selfcheck
fi

# --- MUTATION 2: the z-score's sign is flipped. -----------------------------
# The band stops being one-sided in the right direction: real breakage reads as
# WITHIN and an IMPROVEMENT pages. LAYER 2's drop case is what catches this, and
# it is the case a reviewer is most likely to think is redundant.
if mutate m2 's|    z = (cur_rate - mu) / sigma|    z = (mu - cur_rate) / sigma|'; then
  expect "M2: with the sign flipped, a four-sigma IMPROVEMENT pages (LAYER 2 goes red)" 30 \
    "ACT" "$WORK/m2.py" band --series "$WORK/drop.json"
  expect "M2: and real breakage reads as WITHIN" 0 "WITHIN" "$WORK/m2.py" band --series "$WORK/act.json"
  expect "M2: and the shipped selfcheck refuses to certify the build" 1 \
    "detector is NOT known to fire" "$WORK/m2.py" selfcheck
fi

# --- MUTATION 3: the vacuity guard is removed. ------------------------------
# The insufficient-baseline REFUSAL becomes an ANSWER. On the calm short series
# — three days of history and a fourth just like them — the mutant computes a
# serene z over almost nothing and exits 0. "Could not measure" silently
# becoming "all clear" is the single conflation that would make every other
# case in this file worthless.
if mutate m3 's|    if len(baseline) < min_baseline:|    if False:|'; then
  expect "M3: with the baseline guard removed, 'could not measure' becomes 'all clear'" 0 \
    "WITHIN" "$WORK/m3.py" band --series "$WORK/short-calm.json"
  expect "M3: and it will confidently verdict on three days of history" 30 \
    "ACT" "$WORK/m3.py" band --series "$WORK/short.json"
  expect "M3: and the shipped selfcheck refuses to certify the build" 1 \
    "detector is NOT known to fire" "$WORK/m3.py" selfcheck
fi

# --- MUTATION 4: the tier boundary stops tolerating float representation. ---
# `z >= threshold` instead of `z >= threshold - TIER_EPSILON`. Three failures in
# forty against a spotless baseline is nominally z=3.0 but evaluates to
# 2.9999999999999996, so the mutant files it one tier down. This is not a
# hypothetical: it is the defect the spotless-baseline case above caught during
# development, and without that case it would have shipped as a detector that
# quietly under-reports whole tiers depending on how a fraction divides.
if mutate m4 's|        if z >= threshold - TIER_EPSILON:|        if z >= threshold:|'; then
  expect "M4: without the epsilon, a nominal z=3.0 is demoted to DIAGNOSE" 20 \
    "DIAGNOSE" "$WORK/m4.py" band --series "$WORK/clean-3.json"
fi

# --- MUTATION 5: the sampling term is dropped. ------------------------------
# The band goes back to its first draft, which read one failure in twelve runs
# as a 2.74-sigma event on real data. The mid-volume case is what catches it —
# and, importantly, THE SELFCHECK DOES NOT. The shipped selfcheck fixtures are
# volume-neutral by construction (a million runs a bucket), precisely so a
# failure there means the tier maths moved rather than something about volume.
# That is a real gap in the selfcheck, and this section is why it is acceptable:
# the property the selfcheck cannot see is asserted here, in the suite CI runs
# on every PR alongside it. A selfcheck is a smoke test, not the whole proof.
FLOOR_OK='    resolution_sigma = 1.0 \/ n_cur'
FLOOR_BUG='    resolution_sigma = 1.0 \/ mean([float(b["total"]) for b in baseline])'
SAMP_OK='    sampling_var = mu \* (1.0 - mu) \/ n_cur'
SAMP_BUG='    sampling_var = 0.0'

if mutate m5 "s|$SAMP_OK|$SAMP_BUG|"; then
  expect "M5: without the sampling term, a mid-volume day is promoted to DIAGNOSE" 20 \
    "DIAGNOSE" "$WORK/m5.py" band --series "$WORK/midvol.json"
  expect "M5: while the volume-neutral selfcheck stays green — it cannot see this" 0 \
    "all 8 cases behaved" "$WORK/m5.py" selfcheck
  # Honest about the overlap: on the REAL false-positive day the resolution
  # floor alone is enough, so M5 does not resurrect it. Asserted rather than
  # left unsaid, because "this mutation does not break that case" is exactly
  # the kind of thing a reader assumes the other way round.
  expect "M5: but the real thin day is still covered — by the FLOOR, not this term" 0 \
    "WITHIN" "$WORK/m5.py" band --series "$WORK/real.json"
fi

# --- MUTATION 6: the resolution floor is scoped to the wrong bucket. --------
# `1 / mean(baseline totals)` instead of `1 / n_current` — the first draft's
# actual code. The floor then describes the resolution of a TYPICAL day rather
# than of the day being tested, so a thin day gets judged against a precision it
# does not have.
if mutate m6 "s|$FLOOR_OK|$FLOOR_BUG|"; then
  expect "M6: with the floor scoped to baseline volume, the real thin day breaches" 10 \
    "OBSERVE" "$WORK/m6.py" band --series "$WORK/real.json"
fi

# --- MUTATION 7: BOTH corrections broken — the original defect, exactly. ----
# This is the band as first written, run against the real 21 days it was first
# run against. It reports z=2.74 and files a triage intent for one failure in a
# twelve-run day. Neither M5 nor M6 alone reproduces it, which is the point
# worth writing down: the two corrections OVERLAP, and a reviewer removing
# either one on the grounds that "the other case still passes" would be halfway
# to shipping the false positive again.
if mutate m7 "s|$FLOOR_OK|$FLOOR_BUG|;s|$SAMP_OK|$SAMP_BUG|"; then
  expect "M7: both broken reproduces the original false positive, DIAGNOSE" 20 \
    "DIAGNOSE" "$WORK/m7.py" band --series "$WORK/real.json"
  expect "M7: at the z the first draft actually reported" 20 "z=2.74" \
    "$WORK/m7.py" band --series "$WORK/real.json"
fi

# ===========================================================================
echo
echo "== the DEFAULT triage directory is the one the docs promise =="
# ===========================================================================
# `report` writes into docs/intent/triage by default, relative to wherever it
# runs. A grep for that string in the source would also pass on a script that
# parsed the default and then ignored it, so this runs `report` with NO
# --triage-dir from a scratch working directory and looks for the file on disk.
#
# THIS REPLACES A CHECK THAT COULD NOT PORT HONESTLY. In the project this came
# from, the suite also asserted that docs/intent/README.md, TEMPLATE.md and
# triage/README.md existed in the tree — the convention that makes the artifact
# mean anything to a reader. That check belongs to a project which has installed
# that scaffold, not to the repo that ships the tool: here the default resolves
# against a *consuming* project's checkout, so the same assertion would be
# either vacuous or permanently red, and neither is a test. What survives is the
# half that is a property of this script — the default is real, it is used, and
# the directory is created when it is absent.
DEFCWD="$WORK/defaultcwd"
mkdir -p "$DEFCWD"
cp "$WORK/diagnose.json" "$DEFCWD/series.json"
out="$(cd "$DEFCWD" && python3 "$BAND" report --series series.json 2>&1)"; rc=$?
DEFART="$DEFCWD/docs/intent/triage/2026-08-13-ci-failure-rate.md"
if [ "$rc" != 20 ]; then
  no "report with no --triage-dir must still compute the band" "$out"
elif [ ! -f "$DEFART" ]; then
  no "the default --triage-dir did not receive the artifact" \
     "$(find "$DEFCWD" -type f | sed "s|$DEFCWD|.|")"
else
  ok "with no --triage-dir the intent lands in docs/intent/triage, created if absent"
fi

echo
echo "-----------------------------------------------"
echo "control-band.test.sh: $pass passed, $fail failed"
[ "$fail" -eq 0 ] || exit 1
