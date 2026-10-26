# Decision record format

Decision records live in `docs/decisions/` and are numbered sequentially:
`NNNN-slug.md` (for example `0003-job-token-lifetime.md`). List the directory, take
the highest number and add one. Never reuse or renumber a number.

## Template

Match the existing records in that directory:

```md
# ADR-NNNN — {decision title}

**Status:** Accepted, YYYY-MM-DD
**Decided by:** the owner, {in response to what, in one clause}

## Context

{the problem and the forces on it, stated as facts, not as the day it came up}

## Decision

{what was decided, in the active voice, with the boundaries of the decision}

## Consequences

{what this makes easy, what it makes hard, what it rules out}

## Alternatives considered

{each real alternative and why it lost}
```

Notes:

- **Status** is `Proposed`, `Accepted` (with the date) or `Superseded by ADR-NNNN`.
  An agent drafts a record as `Proposed`; the owner accepts it. An agent never
  marks its own record `Accepted`.
- **Decided by** names the role that decided and, in one clause, what prompted it. It
  is the owner's rulings that make a record `Accepted`.
- **Checkable.** A decision cites the spec fact or intent it serves, and a spec fact
  that rests on a decision links back to the record.
- **Facts, not incidents.** Context describes the forces, not the Tuesday they were
  discovered. The publication boundary applies: no names, hosts or tickets from
  another organisation.
- **Supersede, do not edit history.** A changed decision is a new record that says
  which it supersedes; the old one gets its status line updated and nothing else.

## When a design note is needed

A decision with real implementation surface (a new stored shape, a new tool, a new
guard) is written in `docs/decisions/` and cited from the spec fact it serves.
`docs/design/` was removed in OPS-333. A decision that only fixes a shape or a
policy needs the record alone, and the record says that is why.

## When to offer one

All three must be true: hard to reverse, surprising without context, the result of a
real trade-off. What qualifies here:

- **Where state lives** (plain files in a git data repo, the daemon as the only
  writer, one tenant per daemon).
- **Who may do what**: the shape of a job-token profile, a state-machine rule, the
  verifier independence rule.
- **Deliberate deviations from the obvious path**, so the next contributor does not
  "fix" a deliberate choice: standard-library-only Python, one UI bundle for every
  mode, one org per fork.
- **Constraints not visible in the code**: a limit someone else imposes, an owner's
  standing ruling.
