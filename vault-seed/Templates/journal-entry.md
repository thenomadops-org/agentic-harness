---
title: "{{AGENT}} — {{DATE}}"
tags: [vault, domain/team, type/journal]
type: journal
agent: {{agent_id}}
role_id: {{role_id}}
client: {{client_slug}}
date: {{DATE}}
prs: []
tickets: []
tokens_in: 0
tokens_out: 0
cost_usd: 0.00
---

# {{AGENT}} — {{DATE}}

> Copy this into `Sessions/{{AGENT}}_{{ROLE}}_{{DATE}}.md` at the end of a
> working session. The frontmatter is a contract — `lint_vault.py` fails on a
> journal missing `agent`, `date`, `prs`, `tokens_in` or `tokens_out`.
>
> `prs: []` is a valid and meaningful value: it records that none were touched.
> An **absent** key records nothing, which is the failure the check exists for.
>
> **Measure the token figures, do not estimate them.** A guessed number in a
> field that looks measured is worse than a blank one — it will be summed,
> charted, and believed.

## What I did

-

## What I got wrong

-

*This section is the reason the journal is worth keeping. An entry that only
lists accomplishments is a status update; the org already has those. Write the
thing you had to back out, the assumption that turned out false, the check you
skipped and regretted.*

## What I handed off

-

## What I could not verify

-

*Name the gap. A stated gap is survivable; an implied all-clear is not.*

## Durable lesson

Did anything here deserve a memory atom? If yes, write it and link it:

-

Scope it: a lesson about *how work goes wrong* travels and belongs in
`.claude/memory/_shared/`. A fact about this client's cluster, board or product
belongs in `.claude/memory/{{client_slug}}/`.
