---
title: "The opener merges; a watcher escalates"
tags: [vault, type/memory]
type: memory
status: active
color: purple
created: 2026-08-28
trigger: "arming more than one agent to merge, or being asked to merge someone else's PR"
---

Two rules that are each correct produced a race. "A pull request you open is
yours until it merges" was given to every agent. A sentinel was separately told
to watch for green PRs and land them. Both then held a mandate over the same PR.

**Why:** merging is not idempotent and verification is not deterministic. Two
agents can reach different verdicts on the same head — different check rosters,
different moments, one of them reading a stale run — and nothing arbitrates
between them. The second verifier does not double the confidence; it halves the
accountability, because neither can be asked afterwards why it merged.

**How to apply:** exactly one agent holds merge authority for a given pull
request, and it is the one that opened it. A watcher, reviewer or sentinel
**reports** a green PR to its opener and to the chief of staff — it does not
merge. Merge someone else's only when the opener has genuinely gone dark, and say
explicitly that this is what you are doing.

The corollary is the part agents skip: opening a PR is not the deliverable.
Work it to green, fix what CI finds rather than waiting to be told, and merge it.
If a gate refuses for a reason you must not route around, or the fix is in a file
the principal owns, say exactly what blocks it and who owns that — in the PR and
in your report. "PR opened" is not done.

Related: [[verify-the-merge-dont-take-the-report]] · [[dont-engineer-around-a-deny-rule]]
