<!-- from factory-seed@UNSTAMPED -->

# `tasks/local/` — this repo's own evals

**Ships empty. It is yours.**

`tasks/core/` is the portable set the seed installs and a later seed update may
replace wholesale. Anything you write about *this* repo's configuration — its
tracker, its gate ladder, its deploy path, the sentence somebody got wrong once —
goes here instead, where an update cannot touch it.

The runner searches recursively, so both directories are one suite with one
threshold. Source the shared helpers two levels up:

```bash
. "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"
```

## Start with the one that pays for itself

**Write a task that compares what your instructions CLAIM against what your code
DOES.** Not against another document — a doc-to-doc citation chain proves nothing
when all the docs agree and are all wrong, and on one project three documents
agreed about an auth gate order that was wrong for months.

When you do, add the source file it reads to `CORPUS_PATHS` in `../../run.sh`.
The break phase copies exactly that list, and a path that is not in it cannot be
mutated — which makes the task unbreakable, which the runner reports as an ERROR.

## Then the ones the core set deliberately leaves out

Each of these was portable in shape and not in substance, so it was not shipped:

- **Concurrency points at its interlock.** *Wherever the config tells agents to
  work in parallel, the same file names the protocol that keeps them from
  colliding.* The dispatcher that creates the concurrency owns the interlock —
  and the agent that needs it is the one reading the paragraph that created it.
  Add this when you install a lease mechanism; before that it has no subjects,
  and a rule with no subjects is an ERROR here by design.
- **Test commands defeat the cache.** *No config line hands an agent a test
  command that can answer from cache.* One line per language and worth every
  character: an agent that runs what it was told and sees `ok (cached)` reports
  the suite green, honestly. The lie was in the briefing.
- **The honesty contract is present.** *The corpus still states what evidence a
  claim must carry, and still gives a failure a shape to report in.* Prose is
  deletable, and if a rewrite drops it nothing anywhere fails — the next report
  is simply written to a lower standard and reads exactly like every previous
  one.
