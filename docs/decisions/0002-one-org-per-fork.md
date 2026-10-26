# ADR-0002 — One org per fork

**Status:** Accepted, 2026-08-14
**Decided by:** the owner, when scoping `setup-my-org`

## Context

[ADR-0001](0001-tenancy.md) settled that one org serves many clients. That left
a smaller question unanswered: can one *installation* hold more than one org —
two different teams, two principals, two reporting structures, side by side?

Supporting that means namespacing everything. Agents, `Team/`, the org config,
the symlinks into `~/.claude`, and every skill that resolves "who am I" would
need an org dimension threaded through them. It is a large amount of machinery
for a case nobody has yet had.

## Decision

**One fork, one org.** A second org means a second fork of the base repo and a
second vault.

`setup-my-org` runs **once**. If it finds an org already rendered into the
vault, it refuses and points at `org update` — which re-renders the generated
files from `roles.yaml` while preserving Souls, memory and the operating
agreement.

## Consequences

**Good.** No namespace threading anywhere. `~/.claude` holds one set of links, a
skill asking "which org" has one answer, and the vault lint's
skills-in-the-vault check stays a simple identity comparison. The cost of a
second org is a `git clone` and running setup again — genuinely cheap, and it
gets clean isolation for free, which a shared installation would not have.

**Accepted cost.** You cannot run two orgs from one machine *simultaneously*,
because `~/.claude` can only point at one vault. Switching means re-running
`install-org` from the other vault, which repoints the links. That is a real
limitation and it is the correct trade at this scale: the alternative is
per-org namespacing carried by every future skill, forever, to serve a case
that has not come up.

**Changing a role is not a new org.** Adding a pack, renaming someone, changing
the reporting line — all of that is `roles.yaml` plus `org update`. A second
fork is for a genuinely different team, not a different shape of this one.

## What would change this

Someone running several client orgs simultaneously from one machine — an agency
model where each client gets its own team rather than sharing one. If that
arrives, the namespacing work is additive: `roles.yaml` and the renderer stay
as they are, and what changes is where output lands and how `install-org`
resolves the active org.
