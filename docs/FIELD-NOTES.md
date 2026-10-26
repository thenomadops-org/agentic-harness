# Field notes

What broke while running the source org at real concurrency, measured rather than
recalled. One session, 2026-08-27 → 28: **six to nine agents working one repo for
about fourteen hours, eleven PRs merged, five issues filed that had existed only as
prose.** Every entry below names the incident that produced it.

These are the traps the README promises the org "arrives already knowing". They are
recorded here first because Phase 0 has nowhere else to put them yet — `.claude/rules/`
and `vault-seed/` do not exist. When they do, most of this becomes their content.

**Read this as a bug report against the design, not a retrospective.** The org worked;
what follows is the set of things that cost real time anyway, and which a packaged OS
can prevent for free.

---

## 1. Identity

### A name is a lookup, not an address

`README.md` design rule 1 says *role ID is the key, the name is presentation*. That is
right about **authoring** and silent about **runtime**, where the same string resolves
two ways at once.

Measured, from the live agent roster:

```
a55a3d87582271599   jared             running     → ref b6bb49
ae2aba520c4c22368   general-purpose   (peer)      → ref 3bd124
```

Two agents, one name, **nothing in a message distinguishing them.** Once the seat
definitions registered as spawnable subagent types mid-session, `jared` meant both *a
type to instantiate* and *a session already running*. Five misroutes followed.

Three distinct failure modes, and the third is the one to design against:

- **Misroute** — a message reaches the wrong session. Cost: a wasted round trip, and
  once a near-miss where a lane was asked to ratify a design artifact it had never
  written. **Two tickets were one agreeable answer away from being cut on manufactured
  authorship.** It was caught only because that lane refused.
- **No route** — an agent holds an urgent finding and has no channel. Two agents hit
  this; both findings reached their destination third-hand. One had no agent-listing
  tool at all, so it could see the problem, know exactly who needed it, and not send it.
- **False conclusion** — an agent reasons correctly from true observations to a wrong
  answer, because the disambiguating tool is not in its toolbox. One concluded,
  reasonably, that something was impersonating it. **Nothing looks broken from inside
  this one.**

**What the OS should do:** give every agent a stable session-scoped address and a
lookup tool for resolving names to it, or make the name unusable as an address. Half
the org having `ListAgents` and half not is worse than neither having it.

### The principal's identity is the only one git sees

Every agent commits as the principal — same `user.name`, same `user.email`. So
`author.login`, `git log --author`, and the commit message convention are **not
attribution signals**, and every one of them was misread at least once.

The sharpest instance: a commit was attributed to the wrong agent by its message
convention and shared identity, in a message correcting someone else about precision.
Two commits, same title prefix, same author, different sessions, different files.

**What the OS should do:** route by the commit that touched the artifact, not the name
attached to it. If agents must share a git identity, say so in the standing rules and
name what does carry information — branch prefix, worktree path, PR number.

---

## 2. Isolation

### A spawned agent inherits its parent's working directory

One omitted parameter, three levels deep. A coordinator dispatched leads without
`isolation: "worktree"`; they inherited its directory; one of them dispatched a
subagent, which inherited theirs. That directory was checked out on **the head branch
of an unrelated open PR**, and a design lane had 33 uncommitted lines sitting in it —
**one `git commit` from landing design work inside an infrastructure PR.**

It had already happened once that night: a 388-line docs commit landed on another
agent's branch and was pushed under that branch's title. Unpicking it took a verified
rebase and an md5 check.

**What the OS should do:** make per-agent isolation the default at dispatch, not a
parameter someone remembers. `docs/LOOP-MODEL.md` in the source org mandates
per-agent worktrees; the mandate existed and the parameter was still omitted, which is
the argument for a default over a rule.

### `refs/stash` is repo-wide, not per-worktree

`git stash` in one worktree **empties another worktree's tracked files, with no
warning.** Confirmed: `git-common-dir` differs from `git-dir`, and the stash stack held
three prior recovery notes from agents hitting this before. Tonight made four.

An agent watched its files vanish mid-task with a reflog line that looked like external
tampering. It was another lane's routine `git stash`.

### A lease going quiet is not the same as a lease releasing

The file-lease TTL models **how long work takes**. It does not model **how long a PR
waits on a person.** A PR blocked on an owner decision outlives its lease, so the
interlock releases contended files under work that has not finished — and it goes quiet
precisely when it is most needed.

Measured live: a lease on the gateway policy table expired while its PR sat open with
**60 unmerged lines in that exact file.** The board read the file as free. A second lane
was one acquire away from adding rows to a table whose other rows were staged
elsewhere — the failure the source org's own `CLAUDE.md` names by hand: *two agents add
their own row on different lines, both PRs merge clean, and one capability ships twice
under two endpoint names.* Git does not conflict on non-adjacent additions. Nothing
would have gone red.

**What the OS should do:** a lease should be held against a PR's lifetime, not a
timer — or the board must distinguish *expired* from *released*, because only one of
those means the file is safe.

### File-level leases do not cover everything contended

Four artifacts had no isolation primitive at all: **in-progress notes, issues, agent
identity, and branch pointers.** A lease guards contended *files*; it saw none of these.

Concrete: two agents filed near-duplicate issues 18 seconds apart. Five `git add -A`
sweeps in one night, each silently committing another agent's in-progress work. Two
agents each computing "next free migration number" from a stale tree, creating
**different filenames** — so the file lease detected no contention at all, both PRs
merged clean, and the ordering was ambiguous forever.

**What the OS should do:** assign migration numbers (and any other
next-sequential-resource) at dispatch. Ban `git add -A` in the standing rules; explicit
paths only.

### A guard is a snapshot; the report treats it as a subscription

An agent ran the contention guard, got `guard ok (0 exclusive-set paths touched, all
leased)`, then kept working for another hour and quoted that result as its verification.
By the end it had modified a file another lane held the lease on. Re-running the same
command named the violation in one line.

The interesting part is the second-order failure. Told "the guard passed and a violation
exists", the coordinator concluded the guard's *scope* was too narrow and said so, in
writing, to the agent — a plausible theory, since the guard genuinely only enforces a
named subset of contended paths. Running the command instead of reasoning about it
showed the file **was** in that subset and the tool was fine. The pass was true when
taken and stale when quoted, and the wrong diagnosis would have taught an agent to
distrust a working guard.

**What the OS should do:** require the guard immediately before the commit, not once per
session — and, in the standing rules, make *re-run the check* the first response to a
check disagreeing with reality, ahead of any theory about the check.

---

## 3. Delivery

### Briefing an agent is not dispatching work

Twice, a lead wrote a detailed, correct brief for ten rows — and the lanes closed out
cleanly with all ten still open. **Nineteen "dispatchable rows" produced one PR.** The
brief was reported upward as progress.

The lead's own words afterward: *"briefing a seat is not dispatching work."*

**What the OS should do:** when an agent reports done, the check is whether its rows
closed and its PRs merged — not whether it produced a report. A clean close-out with
open rows is the failure mode, and it is silent.

### A PR you open is yours until it merges

Added as a standing rule mid-session by the principal, after green PRs sat waiting for
a reviewer nobody had named:

> **A PR you open is yours until it merges.** Opening one is not the deliverable —
> merging it is. Work it until every check is green, fix what CI finds rather than
> waiting to be told, then merge it. If you genuinely cannot — a gate-config file the
> owner owns, or a gate refusing for a reason you must not route around — say exactly
> what blocks it and who owns that.

The exception clause is load-bearing. Without it, *"blocked"* becomes a euphemism for
*"left it"*.

### A watcher escalates; it does not merge

The rule above, plus a sentinel role briefed to "merge tracked issues as they land",
produced **two sessions of one role both armed to merge the same PR.** They raced. Both
had verified independently and agreed, so nothing broke — but nothing arbitrated, and
had the two verifications differed, whichever clicked first would have won and the
other's objection would have arrived after the merge.

Resolution: *the opener merges; a watcher reports to the opener and to the chief of
staff.* Merge someone else's PR only when its opener has genuinely gone dark, and say
so explicitly.

**Two agents armed to merge one PR is not redundancy.**

---

## 4. Verification

### Seven gates in one week that could not fail

Every one was green. Every one was inspecting nothing.

| Gate | What it missed |
|---|---|
| `lint \| tail && git commit` — three agents, all day | `&&` reads `tail`'s exit status, always 0 |
| the vault linter's superseded-notes check | 0 of 920 notes — dead twice over, wrong directory *and* wrong status value |
| a scheduled drift sweep | `--strict` never passed through, eleven days |
| a forged-header rejection test | passed with the guard entirely unwired |
| a fixture aged with `"3 days ago"` | git rejected the date; the error went to `/dev/null` |
| merge Gate 1's review provenance | read a CI capability probe as a human read |
| a mutation run over an emptied case table | `--- PASS` over zero cases |

**One clause catches four of them: "zero rows inspected" is a failure, not a pass.**
It is also the fix that survives an incomplete fix — the vault linter was dead for two
independent reasons at once, so repairing the obvious one would have left it just as
dead and looking repaired.

### Two defence classes, and neither substitutes for the other

Ten-plus corrections landed in one night. **Not one was caught by its own author before
publication.** They sort cleanly:

- **Instrument failure** — a grep, a filter, a count; the tool did not run, or ran
  against the wrong shape. Caught by **a control against a known answer**, solo and
  free.
- **Interpretation error** — the tool ran perfectly and answered the wrong question.
  Caught by **a peer**, and by nothing else.

> A control proves your tool ran. It cannot tell you that you asked the wrong thing.

Four of the five worst errors were the second kind.

### Derive the set; never enumerate it

Every hand-written list was a sample.

```
stale code citations   ticket claimed  4   ·  tree held 15
allowlist rows         agent claimed   6   ·  file held 20
token references       three counts: 5 live · 9 with comments · 82 raw
the backlog itself     moved five times under measurement in one session
```

The ticket arguing that line numbers go stale had its own enumeration stale by nearly
4×.

### Run a control before believing a zero

Fifteen instrument failures in one session; **most pointed at absence.** A
case-sensitive grep, a `head -30` default, an `--include` filter that silently excluded
two of four languages, an empty-result branch sharing an exit path with a failed
comparison, a prefix-anchored search against a board that mixes prefixes, an unquoted
glob whose `grep` errored while `wc -l` still printed `0`.

**A failed command and a true zero look identical.** Every false positive looked odd
enough to investigate; every false negative read as a clean bill.

### Agreement is not verification when the source is shared

Three agents read the same script, reached the same conclusion, and reported it as
three confirmations. Later, two agents ran the same grep and read its silence as an
answer.

> **A shared method is as much a shared source as a shared file.**

Peer review does not catch this — the peers are running the same query.

### A citation stops being true when it leaves its sentence

*"No Swift test target — per #426"* circulated through four messages. #426 is about
agents starving a CI machine's load average; it says nothing about test targets. The
claim belongs to a different issue, which cites #426 inside its own paragraph for an
adjacent question.

The same shape, three more times: a code citation whose line range had drifted onto a
fail-closed guard, so a reader landed on a refusal and concluded the check was
enforced; a git stash label read as an inventory of the stash's contents when it
records only where you were standing; a worktree ID transposed between two real
worktrees.

**A citation correct in its original sentence stops being correct the moment it is
repeated without that sentence.**

---

## 5. Escalation

### A desk has no notification channel

The chief-of-staff role's `fails_by` is *"summarising what he has instead of chasing
what is missing."* The sharper version, measured: **reporting a desk built hours
earlier without re-measuring it.**

Three of four items on one such list were already closed — two of them by work landing
on the default branch, which was never going to tell anyone. The principal would have
re-derived answers he had already given.

The same failure has three forms, in ascending cost:

- **a count** — re-run when someone needs the number
- **a standing claim** — re-testable on demand (*"the classifier refuses this"* was
  reported for hours; when finally re-tested, the block turned out to be a different
  mechanism entirely)
- **a desk** — nothing will ever tell you it changed, and **the cost lands on the
  principal, not on you**

### A finding too thin for memory is too thin for the principal

An agent refused to write a speculative infrastructure finding into the shared memory —
correctly — and then escalated the same claim, on the same thin evidence, to the
principal. Its own conclusion:

> Labelling it "unverified" is not a disclaimer that makes it free.

### Permission to add, and belonging in the file, are different questions

An agent proposed adding an exemption line to a gate-config file and correctly escalated
it, because additions there are owner-only. **The file's own header excluded that entire
class of entry** — the line would have retired a live defect rather than recording a
known gap.

Two agents checked whether they had *permission*. Neither checked whether the line
*belonged*.

### Cost is not the axis that decides whether an action is yours

An agent proposed testing a gate by *"one cheap API call."* The test was **submitting
the approval the gate exists to require** — manufacturing the signal rather than
observing it. The description of the cost was accurate and said nothing about the
nature of the act.

> *"Just testing"* is the phrase that most reliably disguises that difference.

### A dead hatch: a gate whose clearing signal cannot exist

The strongest single finding, because it wedged real work rather than being theorised.

A gate-config ratchet required an `APPROVED` review from the owner's account. **GitHub
forbids a pull-request author from approving their own PR, and every PR in that repo is
authored by the owner.** Measured: **zero `APPROVED` reviews across forty PRs**, ever.

It is deliberate — the script's own comments record that an author-is-owner exemption
was considered and **rejected**, because git authorship is a field an agent can set. So
the reasoning is sound and the situation is unsatisfiable, and nobody noticed for six
days until it blocked a merge that two other PRs were queued behind.

Worse, the gate **postdates by two days a delegation that moved that approval to two
named roles.** The delegation lived in prose; the enforcing check never implemented it.

Three separate agents, all careful, all correct about what the script wanted, routed the
principal an action GitHub would refuse at the button. **None had asked whether the
signal could be produced.**

**What the OS should do:** any gate with a human-approval hatch needs a test that the
hatch is *reachable* — not that it is configured. A hatch nobody has pulled is
indistinguishable from a hatch that cannot be pulled.

---

## 6. The tension this design has not resolved

Three of the four ruling defects that night were caught by **adjacent readers** —
agents who happened to be looking — not by anyone assigned to review.

Every correction that mattered happened because two lanes were close enough to see each
other's work: one refusing to ratify an artifact it had not written; one catching a
claim line that would have auto-closed a live defect on merge; one stopping a premature
"CI is green" before it reached the principal.

**The isolation this OS is built on removes exactly that overlap.** And it degrades on
success, not failure: nothing goes red, and by every metric the model tracks, the board
improves while this gets worse. The spend accelerates as the org grows.

The agent that found it declined to propose a review stage — *"ceremony added to replace
an accident is how this role becomes an administrator"* — and pointed at the alternative
instead:

> **A self-applied technique does not thin out when lanes separate.**

Which is why the rules worth shipping are the ones an agent runs on itself: a control
before believing a zero, the command named beside the claim, and the question one agent
asked before shipping a sentence —

> **If this sentence became false, what would go red?**

---

## Where these landed

A document nobody loads changes nothing, so each finding is carried by something
that ships:

| Finding | Carried by |
|---|---|
| A name resolves to a type *and* to live sessions | `README.md` design rule 1 · `org/templates/agent.md.tmpl` · seed memory `a-name-is-not-an-address` |
| The opener merges; a watcher escalates | `agent.md.tmpl` · `roles.yaml` `engineering-lead` · seed memory `the-opener-merges` |
| Isolation is neither free nor automatic | `agent.md.tmpl` · `roles.yaml` `senior-engineer` |
| A guard is a snapshot, not a subscription | `agent.md.tmpl` · seed memory `a-guard-is-a-snapshot-not-a-subscription` |
| Zero rows inspected is not a pass | `agent.md.tmpl` · `roles.yaml` `scrum-master` · seed memory `zero-rows-inspected-is-not-a-pass` |
| Briefing is not dispatching; re-measure the desk | `roles.yaml` `chief-of-staff` |
| A hatch nobody has pulled | `agent.md.tmpl` · `roles.yaml` `engineering-lead` |

The seed memories are the part that actually reaches a new org — they are copied into
the vault at setup and read at the start of tasks. This file is the evidence behind
them, kept so a future reader can check whether a rule still earns its place.
