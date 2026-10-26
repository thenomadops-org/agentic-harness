# Intent

**The front of the chain.** An intent states a problem *in the originator's own
words, before anyone has decided what to build*. It is the artifact that exists
before a spec, before a plan, and before a line of code.

This directory is its home.

---

## Why this exists

Most repos have the middle and the end of the chain and not the front:

| Stage | Artifact | Question it answers |
|---|---|---|
| **1. Intent** | `docs/intent/*.md` — **this directory** | What is the problem, and what is this for? |
| 2. Spec | this project's spec of record | What does the product do, and what constrains it? |
| 3. Plan | [`../STORY-CONTRACT.md`](../STORY-CONTRACT.md) — the story and its PR body | What exactly changes, and how do we know it worked? |
| 4. Change | the PR, its tests, its guards | Did it work? |

Stage 1 usually lives in chat transcripts and meeting notes. That is not a
durable artifact: an agent picking up a story six weeks later can read the spec
and the plan, but it cannot read *why anybody wanted this* — so when the spec and
reality disagree, it has no way to tell which one is wrong. Restating the spec
back at itself is not a substitute; it is how one wrong claim becomes three wrong
documents that all agree with each other.

---

## THE PRECEDENCE RULE — read this before writing anything here

> **The spec of record always wins.**
>
> An intent sits **before** the spec and **never restates it**. If an intent and
> the spec would disagree about what the product does, the spec is right and
> **the intent is stale** — it is a record of what somebody wanted at a point in
> time, not a competing description of what exists.
>
> The correct response to that disagreement is to **mark the intent stale and say
> what overruled it**, never to edit the intent so the two agree. An intent
> quietly rewritten to match today's spec has destroyed the only thing it was for.

**This is not a style note; it is the whole design.** One project was bitten by
exactly the failure the rule prevents: a hedged line in a runbook was copied into
a skill, the copy dropped the hedge, and by the time it reached an agent's prompt
it was a confident causal fact — three documents agreeing with each other, all
three wrong, and no way to find the primary source because every copy looked
equally authoritative. A second source of truth is not extra safety; it is the
mechanism of that failure.

So an intent may state a *goal*, a *constraint the originator cares about*, a
*problem*, or an *open question*. It may **not** state a *fact about what the
system does today*. Facts about the system belong in the spec, cited to
`file:line`. Where an intent needs to refer to one, it **links to the spec's
section** instead of copying the sentence.

---

## The two kinds of intent in here

### 1. The project intent — one file, hand-written

**The goal of the project: what this is for.** It is the document you hand
somebody who asks "what are you actually trying to do here" and does not want a
feature list.

It is deliberately short. An intent that grows section headings until it looks
like the spec has become a second spec, which is the one thing this directory
must not produce. If you are reaching for a service map, a gate ladder, or an API
shape, you are writing the spec and you should stop.

### 2. Triage intents — `triage/*.md`

**Many. Often machine-written. One per detected anomaly.**

A detector that finds an anomaly — a control band breached, an error rate out of
family — writes it into `triage/` using the same template as a human problem
statement. **That shared format is the point.** A detected anomaly re-enters the
pipeline as *the same kind of artifact a human problem statement is*, so it flows
through the same stages — intent → spec/decision → story → PR — instead of dying
as an alert nobody triaged.

An alert has no downstream. Somebody reads it, thinks "CI was bad on Tuesday",
and closes the tab — and afterwards that outcome is not distinguishable from
nobody having looked.

A triage intent is a **problem statement, not a diagnosis and not a plan**. It
records what the numbers did and what would have to be true for that to matter.
It does not say what to change.

> **A confident diagnosis in a brief anchors the agent that reads it.** On one
> project a triage brief named the right file and the wrong mechanism, and the
> agent it was handed to spent its budget confirming the wrong cause. "Verify,
> don't re-derive" applies to *measurements*. It never applies to *causes*.

---

## Writing one

1. Copy `TEMPLATE.md`.
2. Fill every section. A section that does not apply gets its literal fallback
   phrase (`none`, `unknown`, `nobody has asked yet`) — **never** deletion. An
   empty section says "we thought about it and there is nothing"; a missing
   section says nothing at all, and the reader cannot tell which happened. Same
   rule, and the same reason, as [`../STORY-CONTRACT.md`](../STORY-CONTRACT.md).
3. Keep it in the originator's voice. If you are transcribing somebody else's
   intent, **say so in the header and cite where each claim came from**, so a
   later reader can tell an owner ruling from a scribe's inference.
4. Do not restate the spec. Link to it.

## Retiring one

Set the template's **Status** line to `STALE (superseded by <what>, <date>)` and
leave the body untouched. That field is at the top of every intent for exactly
this reason — a reader meets it before the first claim.

Git history is not a substitute: the point of an intent is that a reader who has
*not* gone looking can see that the goal moved.
