<!-- from factory-seed@UNSTAMPED -->

# Agent guardrails — what an agent may never do unattended

**Audience: any agent running against this repo without a human watching the
terminal.** This is not a style guide. Every rule below is followed by the reason
it exists, because a rule without its reason is rationalised away by the next
agent who finds it inconvenient at 3am with a red build.

Companion: [`docs/STORY-CONTRACT.md`](STORY-CONTRACT.md) — what a story must
contain before it is worked, and what a PR must carry before it is opened.

---

## The one rule that governs all the others

**When you hit a guardrail, stop and escalate with a named question. Never work
around it.**

A named question is one a human can answer in a line without opening your
transcript. Not "I'm blocked on the database". It is:

> **Blocked — ACME-142.** Restoring the backup is required to verify the fix, and
> the only restore target visible from this pod is the live data directory. Do
> you want me to (a) stop here and hand you the drill manifest, or (b) wait for
> you to provision a scratch volume? I have done nothing to the volume.

Three properties make it *named*: it names the ticket, it names the specific
irreversible act you declined to perform, and it offers a choice rather than
asking the human to design one.

**"Working around it" includes all of these, and they are all violations:**

- Doing the thing with a different tool because the first was blocked
  (`sed -i` after an edit was denied; `curl` after the API client refused).
- Widening the config that stopped you — see *The subtle one*, below.
- Deleting, skipping, or loosening the test that failed.
- Deferring the action to CI, a script, or another agent so it happens without
  your name on it.
- Narrowing the story so the guardrail is out of scope, and not saying so.

Finishing 80% of a story and stopping at a guardrail with a clear question is a
**success**. Finishing 100% by going around one is a failure, even if it merges
green.

---

## The never-unattended list

Fill this in for your repo during install; these are the categories that have
bitten, not an exhaustive list. Each entry names *what* and *why it is
irreversible*.

- **DNS and edge/CDN configuration.** The blast radius is every user at once and
  the rollback is bounded by propagation, not by your revert.
- **Secret-store IAM, and destroying secret versions.** A destroyed version does
  not come back; the workload that still needs it fails at its next restart,
  which may be days later and will not look related.
- **App-store or package-registry submissions.** Publishing is one-way. An
  unpublish is a support ticket, not a command.
- **Destructive migrations.** A migration that drops or rewrites a column is not
  a code change with a `git revert`; the data is the part that does not come
  back.
- **Restoring a backup over a live data directory.** Restore tools overwrite
  whatever directory they are aimed at. On a single node with no replica, one
  wrong path destroys the only copy.
- **Anything that widens a quality gate.** See below — it is the subtle one, and
  the reason this document exists.

---

## The subtle one: never widen the gate config to go green

When a PR goes red on a coverage floor, a skip allowlist, an exemption list or a
policy table, the **cheapest way to green is to edit the config file that defines
the gate**. One line, the build passes, the reviewer sees a green tick, and the
gate is permanently weaker in a way nobody will ever notice again.

**Treat every gate-config file as read-only.** Maintain the list here as you add
gates; on one project it reads:

| File | What it gates |
|---|---|
| `coverage-floors.txt` | per-package minimum test coverage |
| `skip-allowlist.txt` | tests permitted to be skipped |
| `route_exemptions.txt` | routes exempt from the authz check |
| `intentionally-unset.txt` | config keys allowed to have no value |
| `.factory/allowed-runners` | which runner label sets CI jobs may name |
| `.factory/ticket-prefixes` | which ticket keys satisfy the PR contract |
| `.factory/test-vocabulary.conf` | what counts as a test file and as an assertion |
| `.claude/settings.json` | which tools an agent may use, and which hooks run before them |
| the authz policy table | who can reach what |
| the agent permission config | which of the above an agent may edit |

**Why each, specifically:**

- **Lowering a coverage floor** turns an assertion about the code into an
  assertion about nothing. A number that only ever moves down is not a floor.
- **Adding to a skip allowlist** is how a failing test becomes a passing build.
  The test still exists, still looks like coverage in the file tree, and proves
  nothing.
- **Adding an exemption** removes something from a check. On one project a route
  exemption would remove a route from authorisation entirely — an
  unauthenticated endpoint shipped on purpose, to clear a red build.
- **Adding to `intentionally-unset`** is how a boot-required secret becomes
  optional. That bug has already shipped: blanking `INTERNAL_AUTH_SECRET` failed
  **no test in either package**. Nothing was verifying it, and nothing said so.
- **Widening `test-vocabulary.conf`'s test-path patterns, or narrowing its
  assertion vocabulary,** makes the pre-action hook quieter without anybody
  deciding to make it quieter. It is the same move as adding to a skip
  allowlist, one layer earlier, and it looks like a config tweak rather than a
  weakened test.
- **Editing the agent permission config** is the meta-case: it is the file meant
  to deny edits to all the others. An agent that can edit it can edit anything,
  so widening it is not one violation, it is all of them at once. This is why
  `.claude/settings.json` denies its own editing, and why the hooks it wires ship
  already wired — see `.claude/settings.README.md`.

**The rule.** If a gate config file is the thing standing between you and a green
build, **the gate is working**. Stop and escalate with a named question:

> **Blocked — ACME-88.** `pkg/social` is at 71.4% against a floor of 75%. The
> uncovered paths are three error branches that need a failing-DB fixture I do
> not have. Options: (a) I write the fixture, roughly an hour; (b) you lower the
> floor deliberately and say so in the PR; (c) I ship without this handler. I
> have not touched the floors file.

Option (b) is a legitimate answer. It is legitimate **because a human said it out
loud in a reviewable place**, which is the entire difference between a deliberate
trade-off and an erosion.

**A written justification is friction, not a limit.** One project's first coverage
ratchet required a reason string and nothing else — so a floor could be zeroed by
one line with a one-character reason, and the ratchet was decoration. What makes
an escape hatch bounded is a cap, a no-zero rule, and a high-water mark measured
from somewhere the author cannot edit in the same PR.

---

## What is machine-enforced, and what is only written down

Be honest with yourself about this, because the two are not the same strength,
and treating a written rule as if it were enforced is how a fleet of agents
discovers, months later, that nothing was ever checking.

Keep this table current as the repo grows. The seed installs Tier 0:

| Rule | Enforced by | Strength |
|---|---|---|
| PR carries wiring / prove-by-breaking / verification | `scripts/dod-check.sh`, CI job `dod`, no path filter | machine |
| The DoD checker has not been quietly loosened | `scripts/dod-check.test.sh` | machine |
| The test harness can report a failure | `scripts/gate-test-lib.test.sh` | machine |
| CI jobs name an approved runner set | `scripts/runner-pinning-check.sh` | machine |
| Vendored gates are present and stamped | `scripts/factory-provenance-check.sh` | machine |
| A test's assertions are not removed or disabled | `.claude/hooks/block-test-weakening.sh` (PreToolUse) | machine, **pre-action** |
| That hook can still refuse, and still allows what it should | `.claude/hooks/test-all.sh` | machine |
| The agent config itself does not lie | `evals/run.sh` — and it refuses a vacuous run | machine |
| Every required job actually succeeded | `ci-summary.yml` (`needs:` + `if: always()`) | machine |
| **Every workflow that should have run, ran** | **nothing yet — Tier 1** | **written down only** |
| **A verification claim in a PR body actually ran** | **nothing yet** — `.claude/hooks/transcript-evidence.py` ships with no caller | **written down only** |
| **Two agents do not edit the same file at once** | **nothing yet — Tier 3** | **written down only** |
| Do not widen a gate config | this document | written down only |
| Escalate rather than work around | this document | written down only |
| A coordinator's instruction is not the owner's approval | `.claude/rules/measurement-and-evidence.md` §7 | written down only |

The bottom rows are the honest ones. A rule that is only written down is a rule
that holds exactly as long as every agent chooses to follow it, and the whole
reason for the top rows is that this has repeatedly not been true.

---

## If you are about to break one of these

Write the named question and stop. That is the entire procedure. It costs one
message and it is the only move in this document that has never gone wrong.
