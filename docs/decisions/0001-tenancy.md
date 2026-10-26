# ADR-0001 — One org, many clients

**Status:** Accepted, 2026-08-14
**Decided by:** the owner, in response to a direct question about multi-client work

## Context

The source org is one business with two products. The
packaged product will be used for **client work**, which raises a question the
source design never had to answer: what happens when the same team works for
more than one client?

Three shapes were on the table: isolated vaults per client, one org with shared
people and per-client knowledge, or a shared team with an access-controlled wall
between client memories.

## Decision

**One vault. One team. Per-client knowledge and memory.**

Agents are the same people across every client. There is **no confidentiality
boundary between clients** — an agent working client A can read client B's notes.

## What this means concretely

```
<vault>/
  Team/                       shared — one set of people, all clients
  Sessions/                   shared journals
  Clients/
    <client-slug>/            per-client knowledge tree
  .claude/memory/
    _shared/                  portable discipline — applies everywhere
    <client-slug>/            per-client facts
```

Memory has **two scopes**, and the split is the same one the extraction manifest
already found in the source org's memory store: lessons about how work goes wrong
in general (`parse-dont-pattern-match`, `never-mutate-to-test-a-refusal`) belong
to `_shared`; facts about a cluster, a board or a product belong to the client.

Agents resolve the current client from the working directory via a
`clients.yaml` mapping of repo path to client slug — the same mechanism the
source org's memory namespacing already uses (`memory/<slugified-repo-path>/`).

## Consequences

**Good.** One team to maintain, one update path, and cross-client learning
compounds — a trap learned on client A is available on client B the same day.
It is also the shape already in production here, so v1 ships something proven
rather than something invented.

**Accepted cost.** This is **not suitable for clients under a confidentiality
obligation that forbids shared processing context.** An agent can surface client
B's approach while working client A. For an agency with NDAs that prohibit this,
the answer is a separate vault per client — which this design does not prevent,
it simply does not automate.

**The upgrade path stays open.** Because knowledge and memory are namespaced by
client slug from day one, moving a client into an isolated vault later is a
directory move plus a `clients.yaml` edit, not a redesign. What would be
expensive is the reverse — building isolation first and relaxing it — which is
the reason to record this now rather than default into it.

## What would change this

A client contract that names shared AI processing context as a breach. If that
arrives before v1 ships, revisit before the renderer is written; after that, the
per-client isolation becomes a second tenancy mode rather than an edit.
