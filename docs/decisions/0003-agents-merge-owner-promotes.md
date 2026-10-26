# ADR-0003 — Agents merge behind a gate; the owner promotes to production

**Status:** Accepted, 2026-10-07 (the owner merged PR #227, which the record named as acceptance)
**Decided by:** the owner, in the grill-plan session on the
[portable-workforce intent](../intent/portable-workforce.md)

## Context

Law 7 of the SDLC reads "agents open pull requests; the owner merges and
deploys." The portable-workforce intent wants work returned "completed and
reviewed ready for a human to test", across many projects at once.

The owner chose to test after the merge, on staging (intent ruling 4). Under law
7 as written, that makes the owner a gate twice for every change: once to merge
an untested change, and again to test it. With several projects running in
parallel, the owner's merge becomes the bottleneck. The review that merge was
meant to provide is already done by the council review and a QA verification on
a different model.

## Decision

- **Agents may merge a pull request to `main`.** Merging deploys staging. The
  merge is allowed only when all of these hold, enforced by a hook rather than
  by the agent's judgement:
  1. council review passed;
  2. QA verified the change on a model different from the builder's;
  3. CI is green;
  4. the merging actor is not the builder.
- **Production stays the owner's.** Promotion to production, and any
  destructive production change, needs the owner's authorization in
  conversation.
- **Workforce changes stay the owner's to merge.** A pull request that touches
  `plugin/` (role agents, skills, hooks, org lessons) changes every project, so
  it needs the owner's merge (intent ruling 7).
- **The owner's override.** A direct instruction from the owner in conversation
  overrides any of these gates, and is recorded as authorized.

## Consequences

**Easier.** Work flows from approval to staging without the owner. The owner
spends time testing on staging and promoting to production, not merging.
Several projects can progress at once.

**Harder.** `main` can hold changes the owner has not yet tested. A failure
found on staging becomes a fix story or a revert, not a rejected PR. The gate
hook is now load-bearing, so it must be proven able to fail (break-it tests)
and covered by CI.

**Ruled out.** An agent merging its own work. An agent merging without a
cross-model QA verification. An agent deploying to production on its own
initiative.

## Alternatives considered

- **The owner merges every PR (law 7 unchanged).** Rejected: with testing on
  staging, the owner gates every change twice.
- **Agents merge and deploy to production.** Rejected: production stays a human
  promotion.
- **Test before the merge on per-PR previews.** Rejected in intent ruling 4,
  where the owner chose staging after the merge.
