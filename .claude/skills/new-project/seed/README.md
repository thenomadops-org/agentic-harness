# The seed — files a repo owns and CI executes

This directory is **not** a skill. It is the source for a vendored copy.

## Why it is not a skill

A skill lives in `~/.claude/skills/` and is read by an agent at a decision point.
A GitHub runner has no home directory of ours in it:

```
$ grep -ho 'scripts/[a-z0-9-]*\.sh' .github/workflows/*.yml | sort -u | wc -l
21
$ grep -l '\.claude/skills' .github/workflows/*.yml || echo NONE
NONE
```

Twenty-one repo-local script paths run in one project's CI. Zero references to
`~/.claude`. **A guard that lives in an agent's home dir does not run in CI**,
which means it runs only when an agent chooses to run it, which means it is
advice. We already know how that ends: `story-lease.sh` is documented as local
and advisory and explicitly never a CI merge gate, because a runner's empty
`$HOME` would make it pass vacuously — and a check that cannot fail is
indistinguishable from one that passed.

So: **a skill instructs, a gate executes.** Never make a gate a skill, and never
make an instruction a script.

## Tiers

Install only what applies. A static site does not need a restore drill, and
installing one teaches the team that seed files are ignorable.

**Tier 0 — every repo, no exceptions.** Assumes no language and no deploy target.
Shipped here, tested, working:

| File | What it does |
|---|---|
| `scripts/dod-check.sh` + `.test.sh` | the PR contract, machine-checked |
| `scripts/gate-test-lib.sh` + `.test.sh` | the shared harness every suite reports through |
| `scripts/runner-pinning-check.sh` + `.test.sh` | CI jobs name an approved runner set |
| `scripts/factory-provenance-check.sh` + `.test.sh` | vendored gates are present and stamped |
| `.github/pull_request_template.md` | the contract as a form |
| `.github/workflows/dod-check.yml` | the body gate, no path filter, fires on `edited` |
| `.github/workflows/ci-summary.yml` | the gates job + the single aggregate required check |
| `docs/STORY-CONTRACT.md` | why every section exists, with the bug it prevents |
| `docs/AGENT-GUARDRAILS.md` | what an agent may never do unattended |
| `docs/intent/` + `TEMPLATE.md` | the front of the chain: a problem stated before anyone designed a solution |
| `.factory/README.md` | what the per-repo config files are and why they are not vendored |
| `.factory/test-vocabulary.conf` | what this repo calls a test and an assertion — the one config file the install copies; **prune it** |
| `CLAUDE.md.template` | the one-page agent config, with the four sections that earn their place |
| `.claude/settings.json` | permissions **and the `hooks` key, already populated** — see below |
| `.claude/settings.README.md` | why that file denies its own editing, and why the hooks key ships wired |
| `.claude/rules/*.md` | the standing rules every agent inherits: what you may claim, what you may obey |
| `.claude/hooks/` + `*.test.sh` | the pre-action layer: a guard that runs *before* the edit lands |
| `evals/` + `tasks/core/` | tests over the agent configuration itself, with a break-proof on every run |

### The one structural thing to notice: `settings.json` ships with `hooks` in it

`.claude/settings.json` carries `Edit(**/.claude/settings.json)` in
`permissions.deny`, and that rule is **correct** — an agent that can edit it can
disable every control in the repo including the rule denying the edit.

The consequence is the part people find out the hard way: **a hooks layer cannot
install itself.** On the source project, three finished, tested, correct
pre-action hooks sat in the tree *routed to nothing* for as long as it took an
owner to paste eight lines in by hand. Present, correct, green suites — and every
tool call in the meantime unchecked.

So the seed ships the key **populated**. A seeded repo should never hit that wall.
Adding hook number two is then an edit to a file the owner already owns, at a
moment of their choosing.

**Tier 1 — the repo has tests.** Not yet extracted. `no-silent-skip.sh`,
`assert-integration-ran.sh`, `coverage-gate.sh` (shipped **unpinned**; the first
measurement pins the floors), the expectation half of `ci-gate.sh` — the part
that re-derives which workflows *should* have run for a diff and fails when one
is **missing**, which `needs:` structurally cannot see.

**Tier 2 — the repo deploys to Kubernetes.** Not yet extracted.
`check-image-pinning.sh`, `deploy-conformance.sh`, `rotate-secret.sh`, the
restore-drill guard and drill manifest, the alertmanager route/delivery checks.

**Tier 3 — more than one agent will work this repo.** Not yet extracted.
`story-lease.sh` + its wiring check, `LOOP-MODEL.md`, and the
`require-story-lease` hook that makes the advisory lease actually bite. Ships
with a health warning: the lease is **local and advisory**, never a CI merge
gate, for the `$HOME` reason above. Its value is refusing an edit up front
instead of at `git rebase`.

Two Tier 0 files already have a Tier 3 hole in them, marked in place rather than
left to be discovered: `evals/tasks/local/README.md` names the
"concurrency points at its interlock" eval as the first one to add when a lease
exists, and `.claude/settings.README.md` says the hook that would enforce it is
a human edit to a file the owner maintains.

## Config is never vendored — with one stated exception

`.factory/ticket-prefixes`, `.factory/allowed-runners`, coverage floors,
allowlists and exemption lists are per-repo files the seed's scripts **read**.
They are written at install from the interview answers, never copied from another
repo. See `tier0/.factory/README.md`.

**The exception is `.factory/test-vocabulary.conf`, and it is copied on purpose.**
It is what `block-test-weakening.sh` reads to decide what counts as a test file
and what counts as an assertion. Shipped empty, the hook matches nothing — and a
hook that matches nothing prints the same reassuring answer as one that looked
and found nothing wrong. A starting vocabulary somebody has to prune is strictly
better than a vacuous one, so it ships covering Go, Kotlin/JVM, Swift, JS/TS,
Python and shell, with instructions to delete the languages this repo does not
use. The hook **blocks** on a missing or degenerate config rather than allowing,
and its suite proves that by deleting the file and asserting exit 2.

## Provenance, because a vendored seed is a fork the moment it lands

Every vendored file carries `from factory-seed@<sha>` near the top, and
`.factory/MANIFEST` records the same sha per path.
`scripts/factory-provenance-check.sh` fails on a missing file, a stripped header,
a mismatch, or the literal placeholder `UNSTAMPED` — so an install that skipped
the stamping step is red on its first PR rather than discovered a year later.

Content drift against upstream needs the network and belongs in a scheduled job
that **opens a PR** and never auto-merges. A gate that changes itself is not a
gate. Drift in the other direction — a repo improved its copy — goes back
upstream by hand, and the regression suite that ships with every gate is what
makes taking it safe.
