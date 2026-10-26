<!-- from factory-seed@UNSTAMPED -->

# Evals over the agent configuration

`CLAUDE.md` and `.claude/**` are the only files every agent reads before it reads
any code. They are also, in most repos, the last thing to get a test. This
directory is that test suite.

```bash
evals/run.sh                        # everything: live checks + break-proofs
evals/run.sh --only skill-front     # one task, by id substring
evals/run.sh --json out.json        # machine-readable results
```

It runs in CI as part of `ci-summary.yml`'s `gates` job, with **no path filter**:
a change to a check is not a change to the thing it checks, so a path-filtered
gate skips exactly the commit that breaks it.

---

## The two task directories

| | |
|---|---|
| `tasks/core/` | **Portable.** Shipped by the `new-project` seed and true of any repo. Improve these **upstream**, in `seed/tier0/evals/tasks/core/`, or your copy is a fork. |
| `tasks/local/` | **Yours.** Everything specific to this repo's config, its tracker, its ground truth. Never upstreamed. Ships empty. |

They are one suite with one threshold — the runner searches recursively. They are
separate directories so a later seed update can replace `core/` wholesale without
touching a line you wrote.

## What the core set is seeded from

Real failures, each a configuration defect that produced a **confident false
success**:

| The failure | Where it lives now |
|---|---|
| Two skills named a tracker project that did not exist, so every search returned `[]` — one on the path of every unit of work, the other dispatching nine agents on "the board is clear" | 01, 02 |
| An overnight audit found four gates passing while inspecting nothing, one green over zero tests | 03, 04, 05 |
| Evals nobody could audit against the rule that every incident becomes one | 06 |
| Instructions outliving the files they name — an agent that cannot run a guard reports the step done anyway | 08, 09 |
| A skill deleted while its references stayed behind; an agent asked to apply a skill that is not there improvises one | 16 |
| A skill that exists, passes review, and is never loaded — its `name` did not match its directory, or its description never said when to use it | 14, 15 |
| An agent blocked by a deny rule building a workaround, twice, the workaround looking like engineering both times | 22 |

**Written against behaviour, not against today's prose.** Every task globs — it
finds the skills, it does not name them. Nothing asserts that a particular file
exists or that a sentence appears verbatim, because skills are added and deleted
constantly and a suite that turns a routine deletion into a red check teaches
people to ignore red checks.

---

## The trap this suite refuses to become

**An eval that passes while examining nothing is worse than no eval**, because it
converts an unexamined subject into a green tick. Three mechanisms make that
impossible, and all three are themselves tested — by tasks 03, 04 and 05, which
run the real runner against real fixtures on every run:

1. **Zero tasks is an error, not a pass.** A discovery glob that stops matching
   exits 2 with a named reason.
2. **Every check declares its subject count.** A `check` prints `SUBJECTS=<n>`.
   `SUBJECTS=0` is an ERROR — a rule whose subject set has emptied out is green
   by vacuity, and that is how a check survives the deletion of the thing it
   guarded.
3. **Every check is broken on every run.** Each task ships a `break_it` mutation.
   The runner copies the corpus to a scratch directory, corrupts it there, and
   requires the check to go RED. "Prove it by breaking" stops being a screenshot
   in one pull request and becomes a property of every run.

**ERRORS are not FAILURES.** A FAIL means the corpus is wrong — the check worked
and found something. An ERROR means the *check* is wrong: it examined nothing,
declared nothing, or could not be made to fail. The pass-rate threshold applies
to FAILs only; **any ERROR fails the run outright**, whatever the threshold says.
Otherwise the threshold becomes a supported way to ship a vacuous check.

This is not hypothetical. Writing the original 23 tasks, the break phase caught
three checks that reported green while testing nothing or nearly nothing: a
normaliser that matched 1 of 3 claims, an exemption keyed on the word "where"
that any sentence ending in "anywhere" walked through, and a rule that found zero
subjects because the config wrapped that instruction across a line break. All
three would have shipped green.

### A rule that runs out of subjects becomes an error, deliberately

If a rule's subject set empties, the run goes ERROR rather than quietly passing.
That is a design choice and the loud outcome is the correct one: it forces the
question *did the corpus lose something, or has this rule outlived its subject?*
A rule nobody can answer that question about should be deleted, and deleting it
is a one-line change with a reviewer attached. Silence is not.

---

## Ground truth: check the code, not another document

The highest-value task you can add is one that compares what the instructions
**claim** against what the code **does**.

> On the project this came from, `CLAUDE.md` stated the auth gate order wrong for
> months. Two other documents agreed with it. All three were wrong and each one
> looked like corroboration for the others.

A doc-to-doc citation chain proves nothing when all the docs agree. So when you
write that task in `tasks/local/`, **append the source file it reads to
`CORPUS_PATHS` in `run.sh`** — the break phase copies exactly that list, and a
path that is not in it cannot be mutated, which makes the task unbreakable and
therefore an ERROR.

---

## Writing a new eval

One file per task, `evals/tasks/local/NN-slug.eval.sh`, sourced by the runner:

```bash
# A header comment naming the incident, in enough detail that a reader in six
# months can decide whether the rule still earns its place.
. "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

ID="a-stable-slug"
TITLE="one line: the acceptable outcome"
PROVENANCE="the real failure or the real work this came from"

check() {
  # Read the corpus through $CORPUS and ONLY through $CORPUS. In the live phase
  # it is the repo root; in the break phase it is a disposable copy. A check
  # that reaches around it with a repo path mutates the developer's checkout and
  # is also unbreakable.
  ...
  report_violations "<what these subjects are>" "$n" "$violations_file"
}

break_it() {
  # Corrupt $CORPUS in the shape this rule guards. Reintroduce the real defect
  # where you can — the wrong order, the deleted skill, the empty-result
  # conclusion — rather than inventing a synthetic one.
  ...
}
```

Rules of thumb, learned from the ones already here:

- **Subjects are what the rule judges**, not how many files you opened. A rule
  about skill descriptions has one subject per skill; a rule about a prohibited
  command has one subject per runnable line.
- **Exempt tombstones, not categories.** A repo documents its retirements inside
  the files that used to depend on them, so a banned string appears — correctly —
  in the paragraph that bans it. `lib.sh` knows how to tell a retirement notice
  from a dangling pointer; use it rather than widening a regex. And when you do
  widen one, say which of the two you are doing: admitting a valid phrasing the
  recognizer did not know, or waiving a real violation. They look identical in a
  diff.
- **Make the mutation the real defect.** A `break_it` that changes something
  adjacent proves the check reacts to *something*, which is not the same claim.
- **Prefer running the tool over describing it.** A claim about a tool is not
  evidence about a tool. That belief is what put a dozen agents wrong about the
  PR-body gate on one project — they had all been told what it does.

---

## The pass-rate threshold is an owner decision

`EVAL_PASS_THRESHOLD` defaults to `100`, and **that number is a proposal, not a
ruling.**

The argument for 100: every task here is deterministic. Each one either reads the
corpus or runs a real gate over a fixture, so there is no flake for a lower
threshold to absorb. At 95%, one permanently-red instruction becomes a supported
configuration.

The argument against, honestly stated: 100% means a single genuine red blocks
every PR touching config, including PRs that had nothing to do with the red. The
mitigation is that the suite runs in seconds and each failure names the file and
the line, but you may prefer a lower gate initially, or prefer this
non-blocking until it has run for a week.

If model-in-the-loop tasks are ever added, they belong in a separate tier with
their own lower threshold. Averaging a stochastic tier into a deterministic one
lets a real red hide behind a lucky green.
