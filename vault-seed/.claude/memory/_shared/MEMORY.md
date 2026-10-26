# Shared memory

Lessons that travel. True regardless of client, project or stack — how work
goes wrong in general.

One line per atom: `- [Title](file.md) — the hook, in one line.` The hook is a
pointer, never the content; this file is read at the start of tasks and has to
stay short enough to actually read.

**Not here:** anything naming a specific cluster, board, repo or product. That
belongs in `.claude/memory/<client>/`. `lint_vault.py` flags shared atoms that
read like client facts.

## Index

These eleven ship with the org. They were learned the expensive way somewhere
else, and they are the reason a new org is not starting from zero. The first
seven are about getting a single piece of work right; the last four are about
what breaks once several agents work at the same time.

- [Parse, don't pattern-match](parse-dont-pattern-match.md) — adding a pattern leaves a narrower hole of the same shape; parse it or pin the gap, refuse the middle.
- [Claims strengthen as they propagate](claims-strengthen-as-they-propagate.md) — hedges are the first thing lost in summary; read the primary source and fix the source, not the copy.
- [Reach for a mandate before a wrapper](prefer-a-mandate-over-a-wrapper.md) — a wrapper around a working CLI becomes a second thing that can be wrong.
- [Never mutate to test a refusal](never-mutate-to-test-a-refusal.md) — attempting the action IS the action; read the state instead.
- [Don't engineer around a deny rule](dont-engineer-around-a-deny-rule.md) — the workaround wears an engineering costume; say you are blocked and stop.
- [Verify the merge, don't take the report](verify-the-merge-dont-take-the-report.md) — five reported merged, four were; check the artefact, not the account.
- [--delete-branch closes stacked PRs](git-delete-branch-closes-stacked-prs.md) — silent and irreversible; check for children before merging.
- [A name is not an address](a-name-is-not-an-address.md) — a name resolves to a type AND to live sessions; address by session id, attribute by commit.
- [A guard is a snapshot, not a subscription](a-guard-is-a-snapshot-not-a-subscription.md) — a check that passed before your last ten edits is not evidence; re-run it, then theorise.
- [Zero rows inspected is not a pass](zero-rows-inspected-is-not-a-pass.md) — a check that selects nothing is green; report the denominator and break the guard on purpose.
- [The opener merges; a watcher escalates](the-opener-merges.md) — two agents armed to merge one PR halves the accountability, it does not double the confidence.
