---
name: write-a-gate
description: Build a CI check that is actually capable of failing, and prove it. Use whenever adding or changing a guard, linter, conformance check, policy check or regression suite — and before widening, exempting or lowering any existing one. Covers prove-by-breaking, vacuity guards, deriving subjects instead of listing them, bounding escape hatches, and checking fixtures against reality.
---

# Write a gate that can fail

A check that cannot fail is indistinguishable from one that passed. Both are
green, both appear in the rollup, both are cited in a PR body as evidence. This
skill is the standard every gate in the seed was held to, and the reason a repo
gets its eighteenth guard correctly rather than its eighteenth decoration.

---

## 0. First ask whether it should be a script at all

The owner has rejected wrapper scripts twice in a week ("kill the bash file and use
`gh api`"), and the scar is real: I once built a merge gate for a checklist that
`gh api` already ran, and the script became a second thing to get wrong.

**Write a script only if it does one of these three. Otherwise write the mandate
down and stop.**

1. **It parses.** It derives a fact from machine-readable input that a human or
   an agent gets wrong by eye — evaluating every workflow's `paths:` filter
   against a diff; reconciling the env vars the code *reads* against the ones the
   manifest *sets*.
2. **It holds state across runs.** Coverage floors, a mutant kill-list, a lease
   table. State needs a file, a file needs an owner, and the owner is the repo.
3. **It must run with no agent present.** Anything CI invokes. Nobody is there to
   read a SKILL.md at 3am.

**And before any of that, ask what the platform already does.** GitHub Actions
gives you `concurrency`, `needs:`, `if: always()` and `github.sha`. One project grew a
27 KB script to compute "one required context that goes red if any job failed";
most of it was a reimplementation of `needs:` plus `if: always()`. That half was
deleted for the platform. The other half — re-deriving which workflows *should*
have run for a diff, which `needs:` structurally cannot see — was kept, because
it is a genuine parse. Split, do not adopt or reject whole.

---

## 1. Prove it by breaking. Both halves, in the PR.

1. Remove or invert the check.
2. Run it. **Watch it go red.** Record the output *and the exit code*.
3. Restore it.
4. Run it again. **Watch it go green.** Record that too.

A guard nobody watched fail is not verified. Not theoretical: a PR once claimed a
set of assertions proved a service's guards stayed live under `DEV_MODE=true`;
blanking `INTERNAL_AUTH_SECRET` failed **no test in either package**. Nothing was
verifying it, and the PR was green. In another change a `!Deleted` filter turned
out not to be what enforced withdrawal at all — removing it left the deletion
test green, because deletion was enforced somewhere else entirely.

### Verify the mutation actually landed

**A break-test whose edit did not apply is indistinguishable from a guard that
does not work, and it looks exactly like success.** Print the evidence:

```bash
sed -i 's/OLD/NEW/' target.sh
grep -n 'NEW' target.sh        # CONFIRM THE EDIT LANDED — not optional
bash guard.sh; echo "EXIT=$?"
```

Two ways this silently no-ops, both hit during this seed's own build:

- **The file was never committed**, so `git checkout -- <file>` restores nothing.
  Your "green" run is measuring the still-broken file. Commit before you break.
- **A blanket `sed` hit more than you meant.** Stamping provenance with a
  whole-file substitution rewrote a *fixture string* inside a regression suite,
  and the case named "the install forgot to stamp" went on passing while testing
  nothing. It was green in the source directory and only went red after a real
  install into a throwaway repo. Range your substitutions.

### A pipe reports the last stage

`bash guard.sh | tee log` exits with `tee`'s status. Never claim a command
succeeded without its own exit code.

---

## 2. Absence must fail — derive subjects, never list them

The signature defect in this shop is not a red check. It is a check that had
nothing to look at and said so in green.

- **Zero subjects is an error, not a pass.** A guard over an empty file set, an
  empty module list, an empty manifest exits non-zero and names what it expected.
- **Derive the subject set from a source of truth** — `go.work`, the manifest
  tree, the workflow glob, the build steps themselves. A hand-written list goes
  blind the moment it grows, and it goes blind *silently*, which is the only
  moment it mattered.
- **Keep a census.** Count what you actually examined — files, jobs, modules,
  matched values — and fail if any counter is zero. If a parser regression stops
  a rule seeing its subjects, the rule otherwise goes green while checking
  nothing; the census turns that into a red run naming the counter that
  collapsed.
- **Over-expect rather than under-expect.** Fail loudly in the safe direction.

`runner-pinning-check.sh` in the seed is the worked example: no workflow
directory is exit 3, no workflow files is exit 3, zero `runs-on` values found
across files that exist is exit 1, and the message says which counter collapsed.

---

## 3. Parse it, or pin the gap. Refuse the middle.

The failure I keep repeating: seven of eight fixes left a narrower hole of the
same shape as the one they closed. A regex that guesses at the input shapes it
does not know is worse than no check, because it reports green over the gap.

**Two acceptable outcomes, and nothing between them:**

- **Parse it properly** with a real parser for the format, or
- **Pin the gap loudly** — handle the shapes you actually read, and make
  everything else a named, non-zero `UNCLASSIFIABLE` failure. Never a skip, never
  an assumption of compliance.

Write the pinned gap into the script header, with the reason and the upgrade
path, so the next person extends it correctly instead of widening the regex.
`runner-pinning-check.sh` reads two YAML syntaxes and fails on block sequences
and `${{ }}` expressions by name, with a header saying *add a real YAML parse,
do not widen this regex*.

---

## 4. Check fixtures against reality, never against your code

**A fixture that agrees with your code proves nothing.**

The named scar, 2026-08-13: a deploy verifier compared `pod_image_id` against
`containerStatuses.image`. On containerd that field is a bare config digest with
no registry reference in it; the registry ref lives in `.imageID`. The fixtures
encoded the same wrong assumption as the code, so the suite was **25/25 green**
while the verifier was false — and it rolled back 13 healthy deployments.

So: build fixtures from a real capture of the real system, not from what you
believe the field contains. When a fixture and the production object disagree,
the fixture is wrong. Record where the capture came from.

---

## 5. Every escape hatch is bounded

Allowlists, exemptions, floors and baselines are load-bearing config, and the
cheapest path to green is always to edit them.

**A written justification is friction, not a limit.** One project's first coverage
ratchet required a reason string and nothing else — so a floor could be zeroed by
one line carrying a one-character reason. What makes a ratchet a ratchet:

- a **cap** on how far one PR may move it;
- a **no-zero rule** — a floor of 0 is not a floor;
- a **high-water mark** measured from somewhere the author cannot edit in the
  same PR (the merge-base with `main`, not the working tree). One project's first
  workflow baseline *claimed* this property and did not have it: one extra line
  turned a brand-new offender green. **A ratchet you can widen is an allowlist.**

And the standing rule, from `docs/AGENT-GUARDRAILS.md`: **never weaken a gate to
go green.** No lowered floor, no widened allowlist, no deleted case, no excluded
module. If green requires weakening, stop and escalate with a named question —
the human saying "lower it, deliberately, in a reviewable place" is legitimate;
you doing it quietly is not.

---

## 6. The gate ships with its regression suite

The prove-by-breaking run in the introducing PR is a one-off. It proves the check
worked the day it was written and says nothing about the day someone loosens a
regex to get their own PR through. The suite makes the break permanent.

- Use `scripts/gate-test-lib.sh`. Every MUST-FAIL case is a way the guard could be
  hollowed out, asserted to still be red.
- **Declare your minimum case count.** `gate_done <n>` fails when fewer cases ran
  than declared — that is what catches case construction collapsing (a fixture
  directory that moved, a `for` loop over an empty glob). It earns its keep
  immediately: it caught two miscounts while this seed was being written.
- **Include MUST-PASS regression cases for false failures.** A checker that goes
  red on a *good* input gets switched off by the first person it annoys, and a
  disabled check is worth less than no check because it still looks like
  coverage. One project's empty-section rule rejected an honest PR body that answered
  `## Wiring required` with `### Env vars` subheadings — a body shape the naive
  version accepted.
- **Never run cases through a pipeline.** A pipeline stage is a subshell; counters
  increment in a copy and are discarded. A suite once printed `passed=1 failed=0`
  while running twelve cases and exited 0.
- **A suite that tests the harness must not use the harness.** Count by hand.
  Circularity is not a style problem here: with the scoreboard neutered, a
  genuinely broken `dod-check.sh` reports exit 0 and every suite in the repo goes
  green together. That is measured, not feared — reproduce it in five minutes by
  replacing the harness's final `[ "$GATE_FAIL" -eq 0 ]` with `true`.

---

## 7. Wire it, or it does not exist

- Add the job to the aggregate's `needs:` list. **A job missing from `needs:` is a
  job whose failure does not block a merge.**
- **Think hard about the path filter, and say why in the PR.** A workflow file
  breaking is not a change to the service it builds, so a path-filtered guard
  skips the exact commit that breaks it. A guard over PR bodies, workflow shape
  or the contract itself takes **no path filter at all**.
- Path filters make a check **absent**, not red — and absent reads as fine to
  every dashboard there is. Treat `skipped` as a failure in the aggregate.
- If the check needs config, its config file goes in `.factory/`, gets a row in
  the read-only table in `AGENT-GUARDRAILS.md`, and **a missing config is an
  error, never a skip**.

---

## The checklist

- [ ] It parses, holds state, or runs without an agent — otherwise it is a mandate
- [ ] The platform does not already do it
- [ ] Broken, watched red with its exit code, restored, watched green — in the PR
- [ ] The mutation was confirmed to have landed
- [ ] Zero subjects is an error; the subject set is derived, not listed
- [ ] Unreadable input is a named failure, not an assumption of compliance
- [ ] Fixtures came from reality, and where from is recorded
- [ ] Every escape hatch has a cap, a no-zero rule and an uneditable high-water mark
- [ ] A regression suite with a declared minimum case count, MUST-FAIL and MUST-PASS
- [ ] In `needs:`; path filter is deliberate and justified in the PR
