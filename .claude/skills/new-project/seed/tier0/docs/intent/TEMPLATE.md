<!-- from factory-seed@UNSTAMPED -->

# Intent template

Copy the block below into `docs/intent/<name>.md` (or, for a detected anomaly,
`docs/intent/triage/<date>-<metric>.md`). Fill every section; answer an
inapplicable one with its literal fallback phrase rather than deleting it.

Read `README.md` in this directory first — in particular the precedence rule,
which is reproduced inside the template so it travels with every copy.

---

```markdown
# Intent — <the problem, in one line, in the originator's words>

**Originator:** <who wants this>
**Recorded:** <YYYY-MM-DD> by <who wrote it down, if not the originator>
**Status:** ACTIVE | STALE (superseded by <what>, <date>)

> **Precedence.** This project's spec of record wins over anything here. This
> document sits *before* the spec, never restates it, and makes no claim about
> what the system does today. If it disagrees with the spec, this document is
> stale — mark it, do not edit it into agreement.

## Problem
<What is wrong, or missing, or wanted — stated as a problem, not as a solution.
The test: if this paragraph names a feature, a service, an endpoint or a
library, it is a plan wearing a problem's clothes. Rewrite it.>

## Proposed outcome
<What would be true if this were solved. Still not a design. Something you could
recognise from the outside, without reading the code.>

## Affected
**Users:** <who feels this — a role, not a table of everyone>
**Systems:** <what would have to move — named at the level of "billing" and
"the mobile client", not files>

## Constraints
<What must stay true regardless of how it is solved. Owner rulings, legal or
store-policy limits, cost ceilings, "we are not doing X". Each one attributed:
who said it, when, and where it is written down. An unattributed constraint is
an inference and must be labelled as one.>

## Open questions
<What nobody has decided yet, and who would decide it. `nobody has asked yet` is
a valid entry and a useful one. Do not resolve a question here by guessing —
an intent's open questions are the reason to have the conversation.>

## What this is NOT
<The adjacent thing this is deliberately not about, and why. This section is
what stops an intent quietly widening into the spec of record over time.>

## Provenance
<Where each claim above came from: an owner ruling and its date, a GitHub issue,
a Jira key, a conversation. Say plainly which lines are transcription and which
are the scribe's inference. A reader must be able to tell the difference without
asking you.>
```

---

## Why each section is here

| Section | The failure it prevents |
|---|---|
| **Problem** | A "problem statement" that is actually a chosen solution. Then every downstream artifact inherits an unexamined design decision as if it were a requirement. |
| **Proposed outcome** | Work that ships and satisfies nobody, because "done" was never stated in observable terms before the design started. |
| **Affected** | Scope discovered late. The systems list is the earliest honest signal of size. |
| **Constraints** | An owner ruling being re-litigated by an agent who never saw it — or, worse, silently reversed by a change that looked local. Attribution is what makes a constraint checkable instead of folklore. |
| **Open questions** | An agent guessing at an undecided thing and the guess merging green. A story that assumes a conversation does not get that conversation clarified — it gets it guessed at. |
| **What this is NOT** | The intent growing into a second source of truth. Named explicitly because that is the one way this directory can make the repo worse. |
| **Provenance** | A claim strengthening as it propagates. A hedged observation copied once loses its hedge and arrives downstream as fact. Provenance is the thread back to the primary source. |
