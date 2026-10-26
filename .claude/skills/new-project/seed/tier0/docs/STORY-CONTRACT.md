<!-- from factory-seed@UNSTAMPED -->

# The story contract

Every story in this repo is executed by **one agent, in one session, with a finite
context window**. The story text is that agent's entire briefing. There is no planning
conversation to fall back on, no sibling story to read, no tribal knowledge, and nobody
to ask. A story that assumes any of those things does not get "clarified" — it gets
**guessed at**, and the guess merges green.

So the contract is not paperwork. Each section below exists because its absence has
already cost a real bug, and the bug is named.

---

## Part 1 — the story template

Copy this block. Fill every section. A section that does not apply is answered with its
literal fallback phrase, never deleted — see *Why empty is not the same as missing*.

```markdown
## KEY-nnn — <one line: the change, in the imperative>

**Size:** S | M | L
**Depends on:** KEY-nnn, KEY-nnn  (or: nothing)

### Files
- `path/to/file` — what changes here
(or: NEW `path/to/file` — what it is for)

### Context the agent needs
<Everything the agent cannot discover cheaply from the tree: the invariant being
protected, the prior incident, the name of the thing that will look right and be wrong.>

### Scope
IN: <the change>
OUT: <the adjacent thing you must NOT touch, and why>

### Acceptance criteria
- [ ] <testable statement — a named test, a specific command, a specific observable>

### Wiring required
<The env vars, manifest patches, network policy entries, authz rows, secret-store
entries, CI jobs and route registrations this change needs that are NOT in the code
diff. Or the literal words: no wiring required>

### Prove it by breaking
<The exact edit that must turn the new test red, and the expected failure.>

### Verification
<The exact commands, with cache-defeating flags.>
```

---

## Part 2 — why each section exists

### Size — `S | M | L`

**Prevents:** a story that cannot finish inside one context window, so the agent runs out
of room mid-change and either stops halfway or starts compressing — dropping tests first,
because tests are the part that looks optional.

- **S** — one file, one guard, no new dependency. An hour.
- **M** — one service, a handful of files, possibly a test helper.
- **L** — crosses a service boundary, or touches manifests as well as code. **An L story
  must name its wiring explicitly**, because L is where wiring lives.

If you cannot honestly call it M, split it. An L that is really two stories is the most
common cause of the second one never being written down.

### Depends on

**Prevents:** two agents in two worktrees editing the same file, or an agent building on
an interface that does not exist yet and inventing a plausible one. Agents run in
parallel and cannot see each other. The dependency graph is the only coordination
mechanism there is.

Name keys, not descriptions. `ACME-166` is checkable; "the blocking work" is not.

### Files — an explicit list

**Prevents:** scope drift, and its worse cousin, *scope drift that looks like
thoroughness*. An agent given a goal but no file list will refactor its way outward until
it runs out of context, and the diff arrives touching eleven modules with the actual fix
buried in it.

It also makes parallel dispatch safe: two stories whose file lists do not intersect can
run at the same time, and that is decidable by reading the stories.

If the agent must touch a file that is not listed, that is a signal worth reporting in
the PR — not a rule to break silently.

### Context the agent needs

**Prevents:** the agent solving the stated problem and missing the actual one.

The pattern that keeps recurring is a control that *looks* healthy while doing nothing:
a webhook with no inbound authentication that nevertheless returned 200; a block filter
that ran at exactly one of five call sites, so blocking was enforced on the feed and
evaporated the moment a caller named the id; a service that lost its database URL, came
up healthy, passed both probes and discarded every write.

None of those are visible from the file you are asked to edit. Whoever writes the story
knows them. Write them down, or they do not exist.

Say the quiet part: *"the reason this looks correct is X, and X is false because Y."*

### Scope — IN and OUT

**Prevents:** the fix that is right and the blast radius that is not.

The OUT half matters more than the IN half. "Do not also delete the conversation history"
is the sentence that stops a block-enforcement change from destroying the member's own
evidence of the thing they blocked someone for. An agent optimising for a clean
implementation will happily tear down more than you meant, and it will justify every step.

### Acceptance criteria — testable, not aspirational

**Prevents:** "done" being decided by the agent that wrote the code.

The test is: **could a second agent, reading only this line, tell you whether it is true?**

| Aspirational | Testable |
|---|---|
| Blocking is properly enforced | A blocked member's direct like records no like, opens no conversation, and publishes no match event — asserted as side effects, not status codes |
| Boot fails without config | The test suite in `pkg/billing` fails when `PUBSUB_AUDIENCE` is unset and the rail is enabled |
| Improved error handling | A refund webhook revokes the entitlement and writes exactly one ledger row on redelivery |

Assert **side effects**, not just status codes. A 403 with the record already created is
still the bug.

### Wiring required

**Prevents:** the single most expensive failure shape there is — *the implementation is
real and the wiring isn't*. Nine-plus changes have merged green and done nothing because
something outside the code diff was missing.

The question to answer, out loud, before opening the PR:

> **What does this change need in order to work that is NOT in my diff?**

The catalogue of things that have been the answer:

- an environment variable absent from the service's Deployment — a boot-required var that
  would CrashLoop the pod on the *next* deploy, not this one, which is why it merges green;
- a secret-store entry. The store is the system of record and the sync into the cluster is
  asynchronous, so the secret must exist *before* the deploy, not after;
- a network-policy peer. Under a default-deny floor, `allow-messaging` admitting only the
  gateway meant media→messaging was dropped and the feature failed a second,
  identical-looking way. One such gap had *never* been permitted and degraded silently by
  design, so nothing ever surfaced it;
- an authorization policy row for a new route;
- a CI job, or the **absence of a path filter** on one. A workflow file breaking is not a
  change to the service it builds, so a path-filtered guard skips the exact commit that
  breaks it;
- a manifest that pins `:latest`, which makes a rollout of a stale image "succeed".

If the honest answer is that there is none, write the literal words **`no wiring
required`**. That phrase is machine-checked, and writing it is an assertion — you looked,
and there was nothing. It is not the same as leaving the section out.

#### Why empty is not the same as missing

A missing section is ambiguous between *"nothing to say"* and *"never considered"*, and
those two have wildly different failure modes. The checker cannot read minds, so the
contract removes the ambiguity: the fallback phrase is mandatory, and an agent that has
to type `no wiring required` has, at minimum, been made to ask the question.

Which is why nothing may type it for them — not the PR template, not a snippet, not a bot.
An assertion produced by a default is worth nothing. The heading being present with
nothing under it is treated the same way, and for the same reason: it is the artefact of
skipping the question, not of answering it.

### Prove it by breaking

**Prevents:** a guard that cannot fail. A check that cannot fail is indistinguishable
from one that passed, and green is exactly what both look like.

The procedure is non-negotiable:

1. remove or invert the check;
2. run the test — **watch it go red**, and record the output *and its exit code*;
3. **confirm the break actually landed.** A break-test whose edit did not apply is
   indistinguishable from a guard that does not work, and it looks like success;
4. restore the check;
5. run it again — **watch it go green**, and record that output too.

Both runs go in the PR. A guard nobody watched fail is not verified.

This is not theoretical. A PR description once claimed a set of assertions proved a
service's guards stayed live under `DEV_MODE=true`; blanking `INTERNAL_AUTH_SECRET`
failed **no test in either package**. Nothing was verifying it. The claim was checked
rather than shipped only because the author tried to break it. In another change, a
`!Deleted` filter turned out **not** to be what enforced withdrawal — removing it left the
deletion test green, because the deletion was enforced somewhere else entirely. Both were
found the same way, and neither would have been found by reading the diff.

Write the specific edit in the story: *"delete the `guardNotBlocked` call in
`handleSendMessage`; `TestBlockedSenderCannotSend` must fail."*

### Verification — with cache-defeating flags

**Prevents:** believing a stale result.

`go test ./...` prints `ok (cached)` after a change that broke the package. That has
already hidden real failures — one PR reported clean and, forced with `-count=1`, produced
three failures that had been there the whole time. Every language has its own version of
this; find yours and defeat it.

The rules:

- **always defeat the cache.** `go test -count=1 ./...`, never bare `go test`.
- **linters and formatters too**, per module.
- **never trust a pre-rebase result.** Rebase, then re-run.
- for manifests, a **server-side dry run**, not a local parse.
- for anything deployed, **diff the running workload's image digest**. Manifests that pin
  a moving tag make `apply` answer `unchanged` while the old image keeps running.
  "Applied" is not "deployed".

State the commands, and state what you did **not** run. "The handlers are covered by
tests; a live sandbox refund has not been executed" is a good line in a PR. A silent gap
is not.

---

## Part 3 — the PR

The PR body carries the same contract, minus the sections that were only ever inputs
(Size, Depends on, Files, Context). `.github/pull_request_template.md` is the form;
`scripts/dod-check.sh` is the check, and it runs in CI on every pull request **with no
path filter** — including a PR that changes nothing but this document.

Mandatory in a PR body, enforced by the checker:

| Section | Satisfied by |
|---|---|
| Summary / why | a heading or bold label saying summary, what changed, or why |
| Ticket reference | a key matching a prefix in `.factory/ticket-prefixes` |
| Wiring required | a wiring-labelled section, **or** the literal `no wiring required` |
| Prove it by breaking | a labelled section — heading, bold label, or bullet label |
| Verification | a verification-labelled section, **or** a cache-defeating flag shown in the body |

And, for each of those present as a heading: **content under it.** A heading with nothing
beneath it is not an answer. It is what a template leaves behind when its instructions are
read and its question is not, and to a reviewer it is indistinguishable from a considered
one — the same shape as every other bug in this document.

Strongly expected but **not** machine-enforced: **Not verified / left undone**. It is
advisory — both when absent and when present-but-empty — because an author with a
genuinely empty list has nothing to write, and a mandatory heading answered with nothing
produces ritual rather than honesty. The word wanted here is "nothing", and an author will
write it freely. The checker warns; reviewers should not let it slide.

#### The template does not answer for you

One project's first cut of `.github/pull_request_template.md` shipped the literal words `no
wiring required` **pre-filled as body text**. Every PR therefore asserted them by default:
fill the template minimally, touch nothing in the wiring section, and the checker said
PASSED. In the one section covering the most expensive failure shape there is, the default
answer was an affirmative false claim that reads as considered.

The phrase now lives only inside the instruction comment, so the author has to type it.
`scripts/dod-check.test.sh` asserts both halves permanently: that the template does not
contain the phrase outside a comment, and that submitting the template unanswered is still
red.

---

## Part 4 — running the checker

```bash
scripts/dod-check.sh /path/to/pr-body.md          # a file
gh pr view 138 --json body -q .body | scripts/dod-check.sh   # stdin
scripts/dod-check.test.sh                          # its own regression suite
```

Exit codes: `0` pass · `1` a mandatory section is missing · `2` usage or configuration
error. Configuration lives in `.factory/ticket-prefixes`, and its **absence is an error,
never a skip** — a checker that silently drops a rule because its config went missing is
the exact defect it exists to catch.

---

## Part 5 — the shortest version

- Every section is here because it was once absent and something broke.
- **Ask what your change needs that is not in your diff, and write the answer down —
  even when the answer is nothing.**
- **Break your own guard and watch it go red**, and check the break landed.
- **Defeat the test cache**, always.
- **Say what you could not verify.** A confident false success is the worst thing you can
  produce.
