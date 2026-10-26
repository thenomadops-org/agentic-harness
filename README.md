# Agentic OS

A packaged agentic workforce. You clone it, run one skill, answer some questions,
and you have a named org of Claude agents with a reporting line, persistent
memory, a shared knowledge vault, and the engineering discipline already wired in.

It is extracted from a working org — fifteen agents that ship a real product —
rather than designed in the abstract. The skills in here are the ones that
survived contact.

## Status

**Phase 0 — extraction.** Nothing is installable yet. See
[docs/EXTRACTION.md](docs/EXTRACTION.md) for what moves out of the source org,
what stays behind, and what needs an adapter.

The harness rewrite is in progress (OPS-332..340). The full rewrite is OPS-334.

## What you get

- **An org tree.** Roles with a real reporting line, decision rights, and
  escalation paths — not fifteen interchangeable assistants.
- **Named people.** Each role gets a persistent identity: a Soul (who they are,
  how they fail), a Role (what they own, what they may decide alone), and a
  private memory that compounds across sessions.
- **The discipline.** `write-a-gate`, `deploy-and-prove`, `prove-recovery`,
  `merge-pr` — skills that encode hard-won rules like *prove a CI check can fail
  before you trust it* and *a green apply is not a deployed image*.
- **Seed memory.** The org arrives already knowing traps that normally cost you
  an outage each to learn. What those traps actually are, measured rather than
  recalled, is [docs/FIELD-NOTES.md](docs/FIELD-NOTES.md) — one night of six to
  nine agents on one repo, and everything that broke anyway.

## Design rules

Three, and they explain most of the structure.

**1. Role ID is the key. The name is presentation — and at runtime it is not even
an address.**
Internals reference `chief-of-staff`, never `joe`. Names are applied at
generation time from a theme, a list you supply, or the defaults. This is what
makes "name them after the cast of Friends" a cosmetic choice instead of a
rewrite.

The runtime half is the part that bites. A name can resolve to a *spawnable agent
type* and to *one or more live sessions* at the same instant, indistinguishable in
a message — that produced five misroutes in one night, including a near-miss where
an agent was asked to ratify a design artifact it had never written. Agents address
each other by session id and attribute work by the commit that touched the
artifact, because every agent commits under the principal's git identity and the
author field therefore carries no information at all. See
[docs/FIELD-NOTES.md](docs/FIELD-NOTES.md) §1.

**2. The vault is yours; this repo is not.**
Your knowledge, memory and team files live in a vault directory that this repo
never writes into after setup. Updates to the OS re-render generated files and
leave authored content alone.

```
<vault>/
  Team/                     shared — one set of people, all clients
  Sessions/                 shared journals
  Clients/<slug>/           per-client knowledge
  .claude/memory/
    _shared/                portable discipline — applies everywhere
    <slug>/                 per-client facts
```

One team works every client, and knowledge is namespaced per client rather than
walled — see [ADR-0001](docs/decisions/0001-tenancy.md), including what that
rules out.

**3. Everything a tracker says is data, not instructions.**
Any agent reading tickets, PR comments or issue text treats them as untrusted
input. This ships as a default rule, not a suggestion — an org wired to a
tracker without it is a prompt-injection surface with fifteen mouths.

## Quickstart

Not yet. When it exists:

```bash
gh repo create my-org --template thenomadops-org/agentic-harness
cd my-org && claude
> /setup-my-org
```

## Layout

```
org/
  roles.yaml            the org tree, by role id — the source of truth
  naming/themes.yaml    name sets (defaults, Friends, singers, …)
  templates/            Soul / Role / agent definitions, with {{tokens}}
.claude/
  skills/               portable discipline — ships unchanged
  rules/                standing rules every agent inherits
adapters/
  github-issues/        default tracker
  jira/                 optional
  none/                 no tracker
tools/
  sdlc-metrics/         flow/leading/lagging metrics from GitHub metadata alone
  control-band/         a control band over CI failure rate, and the triage
                        intent a breach writes
vault-seed/             lint scripts, note templates, index skeleton
docs/                   extraction manifest and design notes
```

The floor a new repo starts on lives in
`.claude/skills/new-project/seed/tier0/` — the story contract and its checker, a
CI shape that pins its runners, a pre-action hook that refuses a weakened test,
evals over the agent configuration itself, and a `settings.json` that ships with
its `hooks` key **already populated**, because a hooks layer cannot install
itself where `settings.json` is deny-listed.

## Licence

[PolyForm Noncommercial 1.0.0](LICENSE). Personal, hobby, research and
non-profit use is free. Any commercial use — including repackaging this into a
product or running it inside a business — needs a separate licence from the
owner. Ruled by the owner 2026-09-16.
