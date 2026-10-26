---
title: "Brief — {{DATE}}"
tags: [vault, domain/team, type/brief]
type: brief
date: {{DATE}}
author: {{chief_of_staff}}
period: "{{FROM}} → {{TO}}"
sessions_covered: 0
prs_touched: 0
tokens_total: 0
cost_usd: 0.00
---

# Brief — {{DATE}}

> Written by the chief of staff, rolled up from the journals in `Sessions/`.
> **Bullets, not narrative.** `lint_vault.py` fails this file over 20 bullets.
>
> The cap is the feature. A brief that grows to fill the available space stops
> being read, and an unread brief is worse than none because it looks like
> reporting happened. Detail is available by asking — that is the protocol.
>
> Every bullet: **what changed · who · where to look.** No preamble, no
> restating what was already briefed, no "continuing to work on".

## Shipped

- **[what]** — [who]. [evidence: PR, digest, or the check that passed] · [[link]]

## Blocked

- **[what]** — [who] · blocked on [what exactly] since [when] · [[link]]

*A blocker with no owner and no date is not a blocker, it is a mood. If it needs
a decision, it goes in the next section instead.*

## Needs a decision from you

- **[the question in one line]** — options: [A] / [B]. Recommendation: **[A]**,
  because [one clause]. Changes if [the one thing]. · [[memo]]

*Never bring a question without a proposed answer. A question with no
recommendation is work handed upward.*

## Worth watching

- **[what]** — [why it might matter later, in one clause] · [[link]]

---

**Not covered here:** [anything deliberately left out, and where it lives]

*This line is not optional when something was omitted. The gap you name is
survivable; the gap the brief implies does not exist is not.*
