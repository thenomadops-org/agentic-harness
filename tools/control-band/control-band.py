#!/usr/bin/env python3
"""control-band.py — a control band over a health metric, and the tiered
response that turns a breach back into a triageable artifact.

============================================================================
CONFIGURE THIS BEFORE IT IS USEFUL
============================================================================

Four things, and none of them has a default this file can safely pick for you:

 1. **`gh`, authenticated.** `collect` shells out to `gh run list`. It needs the
    GitHub CLI on PATH and a `GH_TOKEN` (or `gh auth login`) that can read the
    repository's Actions API. Inside a workflow that is the `actions: read`
    permission — a scope `contents: read` does NOT imply. Omit it and every
    day's fetch returns HTTP 403, which this script reports as exit 3,
    FETCH-FAILED, rather than as a calm sky.

 2. **A branch.** `--branch` defaults to `main`. A repository whose default
    branch is named something else measures nothing until you pass it, and says
    so (FETCH-EMPTY) instead of emitting an empty series with a clean
    conscience.

 3. **At least MIN_BASELINE days of CI history** (7, below). A brand-new repo
    has none, so the first runs here exit 3, COULD NOT MEASURE. **That is the
    correct answer and it is not green.** Any wrapper that treats exit 3 as
    success has re-introduced the single conflation this whole file exists to
    forbid.

 4. **The ACT flag decision.** ACT defaults OFF and turning it on is an owner
    decision, not a configuration detail — see THE TIERS below.

`report`'s `--triage-dir` defaults to `docs/intent/triage`. **That default
assumes the project has the `docs/intent/` scaffold installed** — the README and
TEMPLATE that say what one of these artifacts is and who empties the queue. The
directory must exist or be creatable; `report` creates it. Without the
surrounding convention the artifact still lands, correctly formed, somewhere
nobody has agreed to read — so either install the scaffold or point
`--triage-dir` at wherever this project already files problem statements.

============================================================================
WHY THIS EXISTS
============================================================================

A repo that alerts when its default branch goes red has the front of the loop
and not the back. An alert has no downstream: somebody reads it, thinks "CI was
bad on Tuesday", and closes the tab — and that outcome is not distinguishable
afterwards from nobody having looked at all. What is missing is a control band
(is today's failure rate unusual, or is it Tuesday), a response proportionate to
how unusual it is, and a path from a breach back into the ordinary pipeline as
an artifact somebody triages.

So a breach is written out as an INTENT — the same artifact shape a human
problem statement uses — into a triage directory. That is what puts it on the
conveyor everything else already rides: intent -> decision -> story -> PR.

============================================================================
WHAT IS PORTABLE HERE, AND WHAT IS THE ADAPTER
============================================================================

The BAND is metric-agnostic. `compute_band` takes buckets of
`{bucket, total, failures}` and knows nothing about CI; the tier ladder, the two
sigma corrections, the vacuity refusals and `selfcheck` are all pure functions of
that shape. Point them at flaky-test counts, deploy failures or support tickets
and they work unchanged.

`collect` is the ADAPTER — the one part that knows where numbers come from. It
ships as a working reference rather than a stub, because "CI failure rate on the
default branch, from `gh run list`" is portable to any repo using GitHub Actions,
and because **a stubbed collector is a guard that examines nothing**, which is
precisely the defect the rest of this file is built to refuse. To measure
something else, write a second collector that emits the same series JSON. The
band never has to know.

============================================================================
THE FAILURE MODE THIS SCRIPT IS MOST LIKELY TO HAVE: NEVER FIRING
============================================================================

Guards that run, examine nothing, and report green are ordinary. On one project a
wiring test sat unwired and permanently passing for the life of the repository;
on the same tree, thirty-five tests skipped themselves on an unset environment
variable while their jobs went green. A detector is the same shape of artifact
and fails the same way, except worse: a guard that examines nothing at least has
a fixed subject you can go and count, whereas "no anomaly today" and "the maths
is broken" are the same output.

Four things are done about that, and none of them is a comment:

 1. **`selfcheck` runs real fixtures through the real band code.** Four series
    with hand-computed z-scores: one that must NOT breach, one that must breach
    at 1 sigma, one at 2 sigma, one at 3 sigma, plus a rate DROP that must not
    breach in the other direction. `selfcheck` is a subcommand, not a
    test-file-only concept, so CI runs it against the shipped script on every PR
    and every scheduled run — before the run that matters. A detector that has
    stopped firing fails here rather than reporting a calm sky.

 2. **Vacuity is exit 3, never exit 0.** No buckets, no non-empty buckets, or a
    baseline shorter than the minimum are all distinct typed refusals. "I could
    not measure" must never render as "I measured, and it was fine" — that is
    the single conflation that makes every other line of this file worthless.

 3. **Zero variance does not silence the detector.** A baseline of a perfectly
    green fortnight has sigma 0, and (current - mean)/0 is either a crash or, if
    someone "fixes" it with a guard clause, a permanent no-breach on the exact
    repo state where the first failure matters most. Instead sigma is floored at
    the measurement's own resolution — see THE RESOLUTION FLOOR below.

 4. **The band maths is unit-tested, and the tests are proved load-bearing by
    mutation.** tools/control-band/control-band.test.sh copies this file, breaks
    the variance calculation, and asserts the must-breach fixtures stop
    breaching. If the maths can be broken without a test going red, the tests
    are theatre.

============================================================================
THE METRIC (the shipped adapter's)
============================================================================

**CI failure rate on the collected branch, bucketed by UTC day.**

    rate(day) = failing runs / decided runs

DECIDED, not "all runs". `cancelled` is excluded from both numerator and
denominator, because on a repo using `cancel-in-progress` nearly every
cancellation is a concurrency supersession on the PR path — counting those as
successes would dilute the rate by an amount that varies with how fast people
push, which is not a CI health signal. `skipped`, `neutral` and `action_required`
are excluded for the same reason: nothing was decided. FAILING = `failure`,
`timed_out`, `startup_failure`.

Buckets are compared UNWEIGHTED — the mean is the mean of the daily rates, not
the pooled rate over all runs. A quiet Sunday with 6 runs is a real observation
of the system's health; pooling would let a busy Monday erase it.

The current (incomplete) UTC day is dropped by default. A partial day's rate is
not comparable with full ones, and a single early failure at 02:00 UTC is a 100%
failure rate. `--include-partial` opts back in, for a human looking at now.

============================================================================
THE BAND
============================================================================

    baseline    = the WINDOW buckets immediately before the current one
    mean        = mean of the baseline rates
    sigma_obs   = population standard deviation of the baseline rates
    resolution  = 1 / n_current                        <- (1) RESOLUTION FLOOR
    sigma_base  = max(sigma_obs, resolution)
    sampling    = sqrt(mean * (1 - mean) / n_current)  <- (2) SAMPLING NOISE
    sigma       = sqrt(sigma_base^2 + sampling^2)
    z           = (current_rate - mean) / sigma        <- ONE-SIDED

ONE-SIDED, deliberately. A failure rate falling three sigma below baseline is
CI getting better, and a detector that pages for that trains everyone to ignore
it. Negative z is always WITHIN. (It is not nothing — a sudden collapse in the
failure rate can mean jobs stopped running at all — but that is a *coverage*
question with a different subject, and folding it in here would produce one
signal that means two incompatible things.)

(1) THE RESOLUTION FLOOR — `1 / n_current`, one whole failure's worth of rate in
the bucket being tested. This metric cannot resolve a change smaller than one
run flipping, so claiming a standard deviation finer than that claims precision
the measurement does not have. On a baseline with real variance it is inert. On
a perfectly clean baseline it is the whole mechanism: sigma_obs is 0, and
without a floor the z is either a division by zero or — if someone "fixes" that
with a guard clause — a permanent no-breach on exactly the repo state where the
first failure matters most. With 40 decided runs, a spotless fortnight followed
by three failures in one day is z = 3.0 and gets seen.

(2) THE SAMPLING TERM — the current bucket's own binomial noise, under the null
that the day was drawn at the baseline rate, added in quadrature because the two
are independent sources of spread in the quantity actually being tested.

**This term was NOT in the first draft, and real data is what added it.** The
first `collect` on the project this was extracted from returned 21 real days;
the band read the most recent one — 1 failure in 12 decided runs, 8.33% against
a 2.88% baseline — as **z = 2.74, DIAGNOSE**. That is a false positive, and a
loud one: a single failure on a quiet Tuesday is entirely ordinary at n=12, where
the binomial standard error alone is 4.8%. A detector that files a triage intent
for that gets muted within a fortnight, and a muted detector and a dead one end
in the same place. With the sampling term the same day reads z = 0.57, WITHIN.

The correction is self-tuning and has no arbitrary constant: on a 400-run day it
moves sigma by ~8% and changes nothing, and on a 12-run day it dominates. That
is the property that matters — it costs no sensitivity on the days that can
actually resolve a rate.

RESIDUAL, stated rather than hidden: unweighted daily rates still let a quiet
day count as much as a busy one in the BASELINE mean. The sampling term corrects
the bucket under test, not the baseline's composition. Pooling the baseline
would fix that and would also let one busy Monday erase a genuinely bad quiet
Sunday, which is worse. If quiet days become the norm rather than the weekend,
the honest fix is a volume-weighted baseline, not a threshold on n.

============================================================================
THE TIERS, AND WHY 3-SIGMA DEFAULTS OFF
============================================================================

    z < 1     WITHIN     nothing
    z >= 1    OBSERVE    log the reading. No artifact, no side effect.
    z >= 2    DIAGNOSE   write a triage intent; invoke READ-ONLY diagnosis.
    z >= 3    ACT        all of the above, and MAY open a PR into the review
                         gate — ONLY if CI_HEALTH_BAND_ACT_ENABLED=true.

(The flag is named for the metric the shipped adapter measures, CI health, not
for the tool. Rename it if you point the band at something else — and change it
in one place, `ACT_FLAG_ENV` below, not in prose.)

**ACT defaults OFF and needs an owner decision.** It is the only tier where
software changes the repo with nobody in the invocation path. Two things must be
true before that is reasonable: the change lands in the review gate rather than
on the default branch, and a rollback has been REHEARSED rather than assumed.
Neither is true of a fresh installation, so the flag is unset and this script's
`report` will refuse to act even when it measures a 3-sigma breach — it says so,
in the artifact and on stderr, rather than quietly downgrading.

THE EXIT CODE REPORTS THE MEASUREMENT; THE FLAG GATES THE EFFECT. A 3-sigma
breach exits 30 whether or not acting is enabled. Conflating the two would mean
turning the flag off also changed what the detector *says it saw*, which is how a
disabled feature becomes an invisible one.

============================================================================
USAGE
============================================================================

  control-band.py collect [--repo R] [--limit N] [--branch B] [--days D]
                          [--include-partial] [--out FILE]
      Query `gh run list` ONE DAY AT A TIME and emit a bucketed observation
      series as JSON. --limit is therefore per day, and a day that hits it is
      a refusal (PAGE-CAP), not a truncated number — see collect()'s own
      docstring for the measurement that forced the per-day shape.
      This is the ONLY subcommand that touches the network; every other one
      reads a series file, which is what keeps the tests offline.

  control-band.py band --series FILE [--json]
      Compute the band and print the verdict. Pure function of the file.

  control-band.py report --series FILE [--triage-dir DIR] [--dry-run]
      band, plus: write the triage intent for a DIAGNOSE/ACT breach.

  control-band.py selfcheck
      Run the built-in must-fire / must-not-fire fixtures through the real
      band code. Exit 0 only if every one behaved.

EXIT CODES
  0   ran; WITHIN the band
  10  ran; OBSERVE  (>= 1 sigma)
  20  ran; DIAGNOSE (>= 2 sigma)
  30  ran; ACT      (>= 3 sigma) — measurement only; see the flag above
  2   usage error, or malformed input
  3   COULD NOT MEASURE — vacuity guard. Never conflated with 0.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import subprocess
import sys
from typing import Any

METRIC = "ci-failure-rate"

# --- band configuration -----------------------------------------------------
# Version-controlled on purpose. These are the tiered-response config; they are
# not read from a settings file, because a threshold that can be changed without
# a diff is a threshold nobody can audit after an incident.
BASELINE_WINDOW = 14  # buckets of history the band is computed from
MIN_BASELINE = 7  # fewer than this is exit 3, not "no anomaly"
TIERS = (  # (sigma threshold, tier name, exit code) — descending
    (3.0, "ACT", 30),
    (2.0, "DIAGNOSE", 20),
    (1.0, "OBSERVE", 10),
)
# A z that IS the threshold must land ON the tier, and "is" has to survive
# binary floating point. Three failures in forty runs against a spotless
# baseline is 0.075/0.025, which evaluates to 2.9999999999999996 and would sit
# one tier down from where the arithmetic says it belongs — while the same
# nominal z=3.0 reached by a different division lands on ACT. A tier boundary
# that depends on how the fraction happened to divide is not a threshold, it is
# a coin toss with a rounding step, so the comparison is `>= threshold - eps`.
# Found by tools/control-band/control-band.test.sh's spotless-baseline case,
# not by reasoning about it in advance.
TIER_EPSILON = 1e-9
WITHIN = ("WITHIN", 0)

# The only tier with a side effect on the repo. Owner decision, default off.
ACT_FLAG_ENV = "CI_HEALTH_BAND_ACT_ENABLED"

FAILING = {"failure", "timed_out", "startup_failure"}
DECIDED = FAILING | {"success"}

EXIT_USAGE = 2
EXIT_CANNOT_MEASURE = 3


class CannotMeasure(Exception):
    """A typed refusal. Carries the code that names WHICH vacuity guard fired."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class BadInput(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------------
# THE BAND. Pure. Everything below `collect` depends on this and nothing else.
# ---------------------------------------------------------------------------


def mean(xs: list[float]) -> float:
    if not xs:
        raise CannotMeasure("EMPTY-SERIES", "mean of nothing")
    return sum(xs) / len(xs)


def pstdev(xs: list[float]) -> float:
    """Population standard deviation.

    POPULATION, not sample. The baseline is the whole set of observations the
    band is defined over, not a sample drawn from a larger one — there is no
    larger one. Using n-1 here would inflate sigma on short windows and make the
    detector quietest exactly when it has least history, which is backwards.

    This is the function tools/control-band/control-band.test.sh mutates to
    prove the tests are load-bearing.
    """
    if not xs:
        raise CannotMeasure("EMPTY-SERIES", "stdev of nothing")
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def load_series(path: str) -> dict[str, Any]:
    try:
        if path == "-":
            raw = sys.stdin.read()
        else:
            with open(path, encoding="utf-8") as fh:
                raw = fh.read()
    except OSError as exc:
        raise BadInput("UNREADABLE-SERIES", str(exc)) from exc
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BadInput("MALFORMED-SERIES", f"not JSON: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("buckets"), list):
        raise BadInput("MALFORMED-SERIES", "expected an object with a 'buckets' list")
    return doc


def validate_buckets(raw: list[Any]) -> list[dict[str, Any]]:
    """Every bucket must be well-formed, and the series must be in ascending
    bucket order.

    ORDER IS CHECKED, not assumed. The whole band rests on "the last bucket is
    the current observation and the ones before it are the baseline". A series
    that arrived shuffled would still produce a plausible-looking z against the
    wrong current value, with no symptom. That is the quiet-wrong-answer shape
    these systems keep paying for, so it is a refusal (exit 2), not a sort.
    """
    out: list[dict[str, Any]] = []
    prev_key = None
    for i, b in enumerate(raw):
        if not isinstance(b, dict):
            raise BadInput("MALFORMED-BUCKET", f"bucket {i} is not an object")
        key = b.get("bucket")
        if not isinstance(key, str) or not key:
            raise BadInput("MALFORMED-BUCKET", f"bucket {i} has no 'bucket' label")
        total, failures = b.get("total"), b.get("failures")
        if not isinstance(total, int) or isinstance(total, bool) or total < 0:
            raise BadInput("MALFORMED-BUCKET", f"bucket {key}: 'total' must be a non-negative int")
        if not isinstance(failures, int) or isinstance(failures, bool) or failures < 0:
            raise BadInput("MALFORMED-BUCKET", f"bucket {key}: 'failures' must be a non-negative int")
        if failures > total:
            raise BadInput("MALFORMED-BUCKET", f"bucket {key}: failures {failures} > total {total}")
        if prev_key is not None and key <= prev_key:
            raise BadInput(
                "UNSORTED-SERIES",
                f"bucket {key} does not sort after {prev_key}; the band depends on order",
            )
        prev_key = key
        out.append({"bucket": key, "total": total, "failures": failures})
    return out


def compute_band(
    buckets: list[dict[str, Any]],
    window: int = BASELINE_WINDOW,
    min_baseline: int = MIN_BASELINE,
) -> dict[str, Any]:
    """The control band. Raises CannotMeasure rather than returning a calm verdict."""
    buckets = validate_buckets(buckets)
    if not buckets:
        raise CannotMeasure("NO-BUCKETS", "the series contains zero buckets")

    # A bucket with no decided runs has no rate. It is not a rate of zero — that
    # would read a day CI did not run as a perfect day, which is the same
    # mistake as a skipped test reporting green.
    observed = [b for b in buckets if b["total"] > 0]
    if not observed:
        raise CannotMeasure(
            "NO-DECIDED-RUNS",
            f"{len(buckets)} bucket(s), none with a decided run — nothing was measured",
        )

    current = observed[-1]
    baseline = observed[:-1][-window:]
    if len(baseline) < min_baseline:
        raise CannotMeasure(
            "INSUFFICIENT-BASELINE",
            f"{len(baseline)} baseline bucket(s), need {min_baseline}",
        )

    rates = [b["failures"] / b["total"] for b in baseline]
    cur_rate = current["failures"] / current["total"]
    mu = mean(rates)
    sigma_obs = pstdev(rates)

    n_cur = float(current["total"])
    if n_cur <= 0:  # unreachable via the total>0 filter; a floor, not a hope
        raise CannotMeasure("NO-VOLUME", "the current bucket carries no runs")

    # (1) RESOLUTION FLOOR — one run flipping in the bucket UNDER TEST.
    resolution_sigma = 1.0 / n_cur
    sigma_baseline = max(sigma_obs, resolution_sigma)
    floored = sigma_obs < resolution_sigma

    # (2) THE CURRENT BUCKET'S OWN SAMPLING NOISE, under the null that the day
    # was drawn at the baseline rate. Added in quadrature, because the two are
    # independent sources of spread in the quantity actually being tested.
    sampling_var = mu * (1.0 - mu) / n_cur
    sigma = math.sqrt(sigma_baseline**2 + sampling_var)

    z = (cur_rate - mu) / sigma

    tier, code = WITHIN
    for threshold, name, exit_code in TIERS:
        if z >= threshold - TIER_EPSILON:
            tier, code = name, exit_code
            break

    return {
        "metric": METRIC,
        "bucket": current["bucket"],
        "current_rate": cur_rate,
        "current_failures": current["failures"],
        "current_total": current["total"],
        "baseline_buckets": len(baseline),
        "baseline_from": baseline[0]["bucket"],
        "baseline_to": baseline[-1]["bucket"],
        "mean": mu,
        "sigma_observed": sigma_obs,
        "resolution_sigma": resolution_sigma,
        "sigma_baseline": sigma_baseline,
        "sigma_sampling": math.sqrt(sampling_var),
        "sigma": sigma,
        "sigma_floored": floored,
        "z": z,
        "tier": tier,
        "exit_code": code,
        "act_enabled": act_enabled(),
    }


def act_enabled() -> bool:
    return os.environ.get(ACT_FLAG_ENV, "").strip().lower() == "true"


# ---------------------------------------------------------------------------
# COLLECT — the only networked path.
# ---------------------------------------------------------------------------


def _gh_runs_for_day(day: dt.date, args: argparse.Namespace) -> list[dict[str, Any]]:
    cmd = [
        "gh", "run", "list",
        "--branch", args.branch,
        "--created", day.isoformat(),
        "--limit", str(args.limit),
        "--json", "conclusion,createdAt,status,name,event",
    ]
    if args.repo:
        cmd += ["--repo", args.repo]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CannotMeasure("FETCH-FAILED", f"`gh run list` did not run for {day}: {exc}") from exc
    if proc.returncode != 0:
        raise CannotMeasure(
            "FETCH-FAILED",
            f"`gh run list` exited {proc.returncode} for {day}: {proc.stderr.strip()[:400]}",
        )
    try:
        runs = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise CannotMeasure("FETCH-FAILED", f"`gh run list` output for {day} was not JSON: {exc}") from exc
    if not isinstance(runs, list):
        raise CannotMeasure("FETCH-FAILED", f"`gh run list` did not return a list for {day}")
    # THE PAGE CAP IS A REFUSAL, NOT A ROUNDING ERROR. `gh run list` returns
    # newest-first and stops at --limit, so a truncated day is not "most of the
    # day" — it is the last few hours of it, with a failure rate biased by
    # whatever happened to be running late. A biased number that looks like a
    # measurement is worse than no number, so the day that hit the cap takes the
    # whole collection down with a named code.
    if len(runs) >= args.limit:
        raise CannotMeasure(
            "PAGE-CAP",
            f"{day} returned {len(runs)} runs, at or above the --limit of {args.limit}; "
            "the day is truncated and its rate would be biased toward the end of the day. "
            "Raise --limit.",
        )
    return runs


def collect(args: argparse.Namespace) -> dict[str, Any]:
    """Fetch runs a DAY AT A TIME.

    WHY PER-DAY AND NOT ONE BIG FETCH. `gh run list --limit N` caps at 1000 and
    walks backwards from now, and a busy repo runs a few hundred workflow runs a
    day on its default branch — so on the project this was extracted from, a
    single 1000-run fetch reached back FIVE days, against a 7-bucket minimum
    baseline. The band would have refused with INSUFFICIENT-BASELINE forever,
    which is at least honest but is not a working detector. Measured, not
    assumed: the first real `collect` there returned exactly 1000 runs spanning
    five days. A quiet repo will never hit this, and the per-day shape costs it
    nothing; a busy one would otherwise measure an invisible fifth of its
    history.

    One request per day, each with its own cap check, costs ~14 API calls on a
    daily schedule and cannot silently truncate.
    """
    today = dt.datetime.now(dt.timezone.utc).date()
    last = today if args.include_partial else today - dt.timedelta(days=1)
    first = today - dt.timedelta(days=args.days)
    if first > last:
        raise BadInput("EMPTY-WINDOW", f"--days {args.days} leaves no complete day to collect")

    buckets: list[dict[str, Any]] = []
    runs_seen = 0
    day = first
    while day <= last:
        runs = _gh_runs_for_day(day, args)
        runs_seen += len(runs)
        total = failures = 0
        for run in runs:
            if run.get("status") != "completed":
                continue
            conclusion = run.get("conclusion")
            if conclusion not in DECIDED:
                continue
            total += 1
            if conclusion in FAILING:
                failures += 1
        buckets.append({"bucket": day.isoformat(), "total": total, "failures": failures})
        day += dt.timedelta(days=1)

    # An empty fetch is NOT an empty series with a clean conscience. Zero runs
    # across the whole window is indistinguishable here from a token that cannot
    # see them or a branch name that does not exist, so it refuses rather than
    # emitting a series a later `band` would report as NO-DECIDED-RUNS with no
    # clue why.
    if runs_seen == 0:
        raise CannotMeasure(
            "FETCH-EMPTY",
            f"no runs at all on `{args.branch}` across {args.days} day(s) — check auth, "
            "repo and branch before believing this",
        )

    return {
        "metric": METRIC,
        "unit": "fraction of decided runs that failed",
        "branch": args.branch,
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "runs_seen": runs_seen,
        "buckets": buckets,
    }


# ---------------------------------------------------------------------------
# REPORT — a breach, written as an intent.
# ---------------------------------------------------------------------------


def render_intent(band: dict[str, Any], series_meta: dict[str, Any]) -> str:
    pct = lambda x: f"{x * 100:.2f}%"  # noqa: E731
    branch = series_meta.get("branch") or "the collected branch"
    act_note = (
        "The ACT tier is ENABLED for this run, so opening a PR into the review gate is "
        "permitted."
        if band["act_enabled"]
        else "The ACT tier is DISABLED (default). No PR was opened and none may be opened "
        "by this run; a 3-sigma breach is still reported as a 3-sigma breach."
    )
    floored = (
        "\n- This day carries too few runs to resolve the baseline's own spread "
        f"({pct(band['sigma_observed'])}), so sigma was floored at one failure's worth of "
        f"rate ({pct(band['resolution_sigma'])}). The reading is real; that part of the "
        "sigma is a resolution limit, not a measured spread."
        if band["sigma_floored"]
        else ""
    )
    return f"""# Intent — the CI failure rate on `{branch}` left its control band on {band['bucket']}

**Originator:** `tools/control-band/control-band.py` (automated detection)
**Recorded:** {dt.datetime.now(dt.timezone.utc).date().isoformat()}
**Status:** ACTIVE

> **Precedence.** This project's spec of record wins over anything here — that
> document is authoritative about what the system does, and this one is not. An
> intent sits *before* the spec, never restates it, and makes no claim about
> what the system does today. If it disagrees with the spec, this document is
> stale — mark it, do not edit it into agreement.

## Problem

On **{band['bucket']}**, **{band['current_failures']} of {band['current_total']}** decided CI runs on `{branch}` failed — a rate of **{pct(band['current_rate'])}**.

The trailing baseline of {band['baseline_buckets']} day(s) ({band['baseline_from']} … {band['baseline_to']}) has a mean rate of **{pct(band['mean'])}**, and the band's standard deviation is **{pct(band['sigma'])}** (baseline spread {pct(band['sigma_baseline'])}, this day's sampling noise {pct(band['sigma_sampling'])}, combined in quadrature).

That places the day at **z = {band['z']:.2f}**, which is the **{band['tier']}** tier.{floored}

This section states the measurement and stops there **on purpose**. The detector
does not know a cause, and a confident guess written here would anchor whoever
reads it next onto the wrong mechanism. That has happened on another project: a
brief carried a confident diagnosis, the diagnosis was wrong, and the agent found
the right file for the wrong reason and fixed nothing. Candidate causes are
questions, below, and they are unranked.

## Proposed outcome

Either the rate returns inside the band and the reason is understood, or the
band is wrong and is changed deliberately with the change recorded. What must
*not* happen is that the reading is closed unexplained: an anomaly triaged as
"probably fine" with no reason attached is indistinguishable, later, from nobody
having looked.

## Affected

**Users:** everyone shipping into this repo. A raised failure rate is either
real breakage reaching `main` or noise that trains people to re-run and ignore,
and both are expensive.

**Systems:** CI (`.github/workflows/**`), and whatever the failing jobs touch.

## Constraints

- The `ACT` tier is an owner decision and defaults OFF. {act_note}
- Diagnosis at the `DIAGNOSE` tier is **read-only**. It reads runs, logs and the
  tree; it does not write to the repo or to any deployed environment.
- This artifact is a problem statement, not a plan. Turning it into work means
  writing a story under `docs/STORY-CONTRACT.md`, not editing this file.

## Open questions

Unranked, and none of them asserted:

- Did one workflow account for the excess, or was it spread across many?
- Was the change in the code under test, or in the CI configuration, the runner
  fleet, or a dependency the jobs fetch?
- Was the volume itself unusual — did the denominator move as much as the
  numerator?
- Is this the metric moving, or the *measurement* moving (a workflow added,
  renamed, or newly triggered on `main`)?
- Should the band itself change? A baseline that has drifted upward makes real
  breakage look normal.

## What this is NOT

Not a diagnosis, not an incident report, and not an assertion that anything is
broken. A control band detects that a number is unusual for this system; whether
unusual means *bad* is a judgement this script does not make and must not
appear to have made.

## Provenance

Generated by `tools/control-band/control-band.py report`. Every number above is
computed from the observation series; nothing is inferred.

```json
{json.dumps({k: v for k, v in band.items() if k != 'act_enabled'}, indent=2, sort_keys=True)}
```

Series generated: {series_meta.get('generated', 'unknown')} · runs examined:
{series_meta.get('runs_seen', 'unknown')}
"""


# ---------------------------------------------------------------------------
# SELFCHECK — the proof that this thing can fire.
# ---------------------------------------------------------------------------


def _fixture(current_rate: float, per_day: int = 1_000_000) -> list[dict[str, Any]]:
    """A 12-day baseline alternating 4% / 6%: mean 5%, population sigma exactly 1%.

    per_day is deliberately absurd. One million runs a day is not a plausible
    Tuesday; it is chosen so that BOTH corrections to sigma are negligible here
    — resolution is 1e-6 and the sampling variance is 4.75e-8 against a baseline
    variance of 1e-4 — which isolates the baseline-spread half of the formula
    and lets these cases assert round z-scores that a reader can check by hand:
    z = (rate - 0.05) / 0.01. The resolution floor and the sampling term each
    get their own section, at realistic volumes, in
    tools/control-band/control-band.test.sh.
    """
    rates = [0.04, 0.06] * 6
    buckets = [
        {"bucket": f"2026-08-{i + 1:02d}", "total": per_day, "failures": round(r * per_day)}
        for i, r in enumerate(rates)
    ]
    buckets.append(
        {"bucket": "2026-08-13", "total": per_day, "failures": round(current_rate * per_day)}
    )
    return buckets


# (label, current rate, expected tier). z = (rate - 0.05) / 0.01.
SELFCHECK_CASES = (
    ("a normal day must not breach (z=0.5)", 0.055, "WITHIN"),
    ("a rate DROP must not breach — the band is one-sided (z=-4.0)", 0.010, "WITHIN"),
    ("a mild rise must reach OBSERVE (z=1.5)", 0.065, "OBSERVE"),
    ("a real rise must reach DIAGNOSE (z=2.5)", 0.075, "DIAGNOSE"),
    ("a severe rise must reach ACT (z=3.5)", 0.085, "ACT"),
)


def selfcheck() -> int:
    failures = 0
    for label, rate, want in SELFCHECK_CASES:
        try:
            got = compute_band(_fixture(rate))["tier"]
        except (CannotMeasure, BadInput) as exc:
            print(f"FAIL  {label} — refused to measure: {exc}", file=sys.stderr)
            failures += 1
            continue
        if got != want:
            print(f"FAIL  {label} — expected {want}, got {got}", file=sys.stderr)
            failures += 1
        else:
            print(f"ok    {label} -> {got}")

    # The vacuity guards are part of the self-check, because "could not measure"
    # rendering as "measured, all clear" is the failure that would make every
    # case above meaningless.
    for label, buckets, code in (
        ("an empty series must refuse, not pass", [], "NO-BUCKETS"),
        (
            "buckets with no decided runs must refuse, not read as 0%",
            [{"bucket": f"2026-08-{i:02d}", "total": 0, "failures": 0} for i in range(1, 13)],
            "NO-DECIDED-RUNS",
        ),
        (
            "too little history must refuse, not pass",
            [{"bucket": f"2026-08-{i:02d}", "total": 100, "failures": 5} for i in range(1, 4)],
            "INSUFFICIENT-BASELINE",
        ),
    ):
        try:
            band = compute_band(buckets)
        except CannotMeasure as exc:
            if exc.code == code:
                print(f"ok    {label} -> {code}")
                continue
            print(f"FAIL  {label} — expected {code}, got {exc.code}", file=sys.stderr)
            failures += 1
            continue
        print(f"FAIL  {label} — did not refuse; returned tier {band['tier']}", file=sys.stderr)
        failures += 1

    if failures:
        print(
            f"\ncontrol-band selfcheck: {failures} case(s) failed. The detector is NOT "
            "known to fire. Do not trust a 'within band' verdict from this build.",
            file=sys.stderr,
        )
        return 1
    print(f"\ncontrol-band selfcheck: all {len(SELFCHECK_CASES) + 3} cases behaved.")
    return 0


# ---------------------------------------------------------------------------


def print_verdict(band: dict[str, Any]) -> None:
    print(
        f"{METRIC} {band['bucket']}: "
        f"{band['current_failures']}/{band['current_total']} = {band['current_rate'] * 100:.2f}%  "
        f"baseline mean {band['mean'] * 100:.2f}% sigma {band['sigma'] * 100:.2f}% "
        f"over {band['baseline_buckets']}d  ->  z={band['z']:.2f}  {band['tier']}"
    )
    if band["sigma_floored"]:
        print(
            "  note: sigma floored at the measurement resolution "
            f"({band['resolution_sigma'] * 100:.2f}% = one failure in this bucket's "
            f"{band['current_total']} run(s)) — the baseline's own spread "
            f"({band['sigma_observed'] * 100:.2f}%) is finer than this day can resolve."
        )
    if band["tier"] == "ACT" and not band["act_enabled"]:
        print(
            f"  note: 3-sigma breach measured, but {ACT_FLAG_ENV} is not true, so no PR may "
            "be opened. The measurement is unchanged; only the permission is withheld.",
            file=sys.stderr,
        )


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="control-band.py", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="fetch runs and emit an observation series (network)")
    c.add_argument("--repo")
    c.add_argument("--branch", default="main")
    c.add_argument("--limit", type=int, default=1000, help="per DAY, not per run of this script")
    # 21 complete days: enough to fill the 14-bucket baseline window plus the
    # current bucket, with a week of slack for days CI did not run.
    c.add_argument("--days", type=int, default=21)
    c.add_argument("--include-partial", action="store_true")
    c.add_argument("--out")

    b = sub.add_parser("band", help="compute the band from a series file")
    b.add_argument("--series", required=True, help="path, or - for stdin")
    b.add_argument("--json", action="store_true")

    r = sub.add_parser("report", help="band, and write a triage intent on a breach")
    r.add_argument("--series", required=True)
    r.add_argument("--triage-dir", default="docs/intent/triage")
    r.add_argument("--dry-run", action="store_true")

    sub.add_parser("selfcheck", help="run the built-in must-fire fixtures")

    args = p.parse_args(argv)

    try:
        if args.cmd == "selfcheck":
            return selfcheck()

        if args.cmd == "collect":
            series = collect(args)
            out = json.dumps(series, indent=2)
            if args.out:
                with open(args.out, "w", encoding="utf-8") as fh:
                    fh.write(out + "\n")
                print(
                    f"collected {series['runs_seen']} run(s) into "
                    f"{len(series['buckets'])} bucket(s) -> {args.out}"
                )
            else:
                print(out)
            return 0

        doc = load_series(args.series)
        band = compute_band(doc["buckets"])

        if args.cmd == "band":
            if args.json:
                print(json.dumps(band, indent=2, sort_keys=True))
            else:
                print_verdict(band)
            return band["exit_code"]

        # report
        print_verdict(band)
        if band["tier"] in ("WITHIN", "OBSERVE"):
            print(f"  tier {band['tier']}: log only, no artifact written.")
            return band["exit_code"]

        path = os.path.join(args.triage_dir, f"{band['bucket']}-{METRIC}.md")
        if args.dry_run:
            print(f"  --dry-run: would write {path}")
            return band["exit_code"]
        os.makedirs(args.triage_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render_intent(band, doc))
        print(f"  wrote triage intent: {path}")
        return band["exit_code"]

    except BadInput as exc:
        print(f"control-band: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except CannotMeasure as exc:
        print(
            f"control-band: COULD NOT MEASURE — {exc}\n"
            "  This is NOT 'no anomaly'. Nothing was measured, so nothing is known.",
            file=sys.stderr,
        )
        return EXIT_CANNOT_MEASURE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
