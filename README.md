# Agentic OS

A packaged agentic workforce. Clone it, run one skill, choose roles, and get an
org of role personas with a reporting line, persistent memory, a shared
knowledge vault, and engineering discipline already wired in.

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
  escalation paths.
- **Role personas.** Each role id is its stable display and agent identity. A
  live session is named `<persona>-<TICKET>`. Each role gets a Soul, a Role,
  and a private memory that compounds across sessions.
- **The discipline.** `write-a-gate`, `deploy-and-prove`, `prove-recovery`,
  `merge-pr` — skills that encode hard-won rules like *prove a CI check can fail
  before you trust it* and *a green apply is not a deployed image*.
- **Seed memory.** The org arrives already knowing traps that normally cost you
  an outage each to learn. What those traps actually are, measured rather than
  recalled, is [docs/FIELD-NOTES.md](docs/FIELD-NOTES.md) — one night of six to
  nine agents on one repo, and everything that broke anyway.

## Design rules

Three, and they explain most of the structure.

**1. Role id is the identity.**
The role id is the display label, generated agent id, and persona key. A live
session appends its ticket, such as `engineer-OPS-345`. Multi-seat roles add a
stable seat number (`engineer-1`, `engineer-2`) before the ticket. This keeps
role selection and live work sessions distinct.

**2. The vault is yours; this repo is not.**
Your knowledge, memory and team files live in a vault directory that this repo
never writes into after setup. Updates to the OS re-render generated files and
leave authored content alone.

```
<vault>/
  Team/                     shared — one set of people, all clients
  Sessions/                 shared journals
  Clients/<slug>/           per-client knowledge
  .claude/memory/           the one memory store
    _shared/                portable discipline — applies everywhere
    <slug>/                 per-client facts
  .codex/memory             symlink to .claude/memory
  .grok/memory              symlink to .claude/memory
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

## Lead assignment

The owner names the lead explicitly; quota pressure never swaps the holder.
Record an assignment with the owner's exact words in quotation marks. This
updates both `state/lead.md` and `org/routing.yaml`:

```bash
bin/hx lock lead --holder grok --quote '"Bo holds the lead role per design v3"'
bin/hx lead brief
bin/hx lead handoff --to grok --dry-run
```

Handoff sends the brief to one unambiguous vendor pane and leaves the recorded
lead holder unchanged. At 15% remaining quota, the lead decides how to route
work and posts the call with `hx chat post`.

## Layout

```
org/
  roles.yaml            the org tree, by role id — the source of truth
  vendors.yaml          one adapter record per CLI
  routing.yaml          lead vendor, build lane, QA split, usage floor
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
