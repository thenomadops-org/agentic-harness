# Extraction manifest

**Phase 0.** What moves from the source org into Agentic-OS, what stays behind,
and what has to become an adapter. Measured 2026-08-14 against
the source vault and its main product repo, not estimated.

Nothing has been copied yet. This document is the decision; the copying is
mechanical once it is agreed.

## Role personas

The workforce is defined by role ids, not personal identities. The role id is
the display label and generated agent id; each live session appends its ticket
as `<persona>-<TICKET>`. Multi-seat roles use a stable numeric suffix before the
ticket, such as `engineer-1-OPS-345`. This keeps one persona definition distinct
from each active session.

The SDLC roles are `product`, `engineer`, `ios-engineer`, `android-engineer`,
`devops`, `qa`, `sre`, and `lead`. Their responsibilities follow the stage
table in the workforce guidance. `org/roles.yaml` is the single source for
these ids and their reporting lines.

## Coupling measurement

Hits are lines naming the source org's products, cluster host, tracker keys,
registry or deploy tooling.

| Skill | Hits | Lines | Density | Disposition |
|---|---:|---:|---:|---|
| `session-reflection` | 1 | 102 | 1% | **move** |
| `prove-recovery` | 3 | 137 | 2% | **move** |
| `write-a-gate` | 4 | 226 | 2% | **move** |
| `merge-pr` | 11 | 486 | 2% | **move**, scrub 11 lines |
| `learn-repo` | 2 | 41 | 5% | **move** |
| `deploy-and-prove` | 11 | 150 | 7% | **move**, scrub 11 lines |
| `run-scrum-meeting` | 25 | 274 | 9% | **adapter** — tracker-bound |
| `new-project` | 32 | 320 | 10% | **move**, scrub 32 lines |
| `adr-flow` | 10 | 73 | 14% | **adapter** — Confluence-bound |
| `release-ios` | 11 | 36 | 31% | **stays** — product-specific |
| `jira-flow` | 18 | 55 | 33% | **adapter** |
| `release-dev` | 79 | 193 | 41% | **stays** — cluster-specific |
| `jira-ai-queue` | 237 | 489 | 48% | **adapter**, heavy |

Density sorts this cleanly. Under ~10% is a scrub. Over ~30% the skill *is* the
integration and should be rebuilt against an adapter interface rather than
edited.

> [!warning] These counts undercount — corrected after the move
> The measurement walked each skill's top-level files only, so any skill with
> subdirectories was scored on a fraction of itself. `new-project` ships a whole
> `seed/tier0/` tree; its real coupling was **32 lines across 14 files**, not 32
> lines in one. The disposition column held up — the ordering was right and
> every "move" was genuinely movable — but the density figures are a floor, not
> a measurement. Anything re-measured should walk recursively.

### Moves unchanged or near-unchanged

`write-a-gate`, `prove-recovery`, `session-reflection`, `learn-repo`,
`deploy-and-prove`, `merge-pr`, `new-project`.

These encode discipline that is true of any repo: prove a gate can fail before
trusting it, restore into a scratch target before claiming a backup works, assert
the running image digest actually moved, verify a PR contains the commit you
reviewed. The scrub is replacing identity-specific examples with placeholders — the
procedures do not change.

### Becomes an adapter

`jira-flow`, `jira-ai-queue`, `run-scrum-meeting`, `adr-flow`.

These are the tracker integration wearing a skill costume. Behind an adapter
interface — `list_ready`, `claim`, `comment`, `transition`, `link_pr` — the
procedure above them is portable and the Jira specifics become one
implementation.

Two hazards belong to the adapter, not the caller, and both are already learned
here: **a malformed JQL returns an empty result set rather than an error**, so
"nothing matched" and "your query was wrong" are indistinguishable at the call
site; and **transition IDs differ per project** — `61` is `AI Queue` on one board
and `Review` on another, so firing an ID resolved against the wrong project
silently moves the ticket somewhere real and wrong.

### Stays behind

`release-dev` (the cluster host, k3s, the registry, one cluster's manifests)
and `release-ios`
(this product's signing and store identity). These are the source org's
deployment, not anyone else's. The *pattern* underneath `release-dev` already
moved out as `deploy-and-prove`.

## Vault assets

| Asset | Disposition | Note |
|---|---|---|
| `lint_vault.py` | **move** | Orphan detection, link integrity, trigger collisions. Zero project coupling. |
| `check_links.py` | **move** | 359 notes / 2,728 links / 0 broken at time of writing. |
| `Templates/` | **move** | Note frontmatter contract. |
| `00-Index/` | **move as skeleton** | Structure only, no content. |
| `Team/` | **move as templates** | Shape ports; content is this org's people. |
| `Decisions/`, `Design/`, `Infra/`, per-product trees | **stays** | Product knowledge. |
| `.claude/memory/<project>/` | **split** — see below | |

## Memory atoms split too

The same portable/specific line runs through the memory store, and the portable
half is a genuine differentiator: an org that arrives already knowing the traps.

**Ship as seed memory** — these are about how work goes wrong in general:

- `parse-dont-pattern-match-and-pin-the-rest` — 7 of 8 fixes left a narrower hole
  of the same shape; offer two outcomes, parse it or pin the gap, refuse the middle
- `claims-strengthen-as-they-propagate` — a hedged line became a confident causal
  fact by the time it reached an agent prompt; fix the source, not the copy
- `prefer-a-mandate-over-a-wrapper` — a script written for a checklist becomes a
  second thing to get wrong
- `never-mutate-to-test-a-refusal` — read the state, do not perform the action
- `dont-engineer-around-a-deny-rule` — the workaround wears an engineering costume
- `verify-the-merge-dont-take-the-report` — the report said five, four were true
- `git-delete-branch-closes-stacked-prs` — silent, irreversible; check for children

**Stays** — true of this cluster and board only: `deployed-is-not-the-same-as-applied`,
`merged-is-not-done-check-the-ac`, the dispatcher-loop atom, and the
local-hardware atom.

## A drift the generated model would have prevented

`Team-ORG.md` records that the Motion seat was retired 2026-08-14 and its remit
folded into **the product-design role**. the generated product persona definition
still describes that role with an outdated scope, scoped to type, colour and elevation —
the pre-amendment role.

Two hand-maintained files describing one persona, disagreeing about the same job. This
is the argument for `roles.yaml` as a single source with the agent definition
generated from it: the drift becomes impossible rather than merely discouraged.

The same class of problem appears in path handling — `~/Code/Obsidian` is
hardcoded six times per agent file, ninety times across fifteen files. Portable
only if generated.

## What has to be built (not extracted)

1. **`org/roles.yaml`** — the tree by role id, with packs so a solo developer can
   take four roles instead of fifteen.
2. **`setup-my-org`** — the interview and renderer.
3. **The adapter interface** — and `github-issues` as the default, because it
   works for anyone with a repo and has no OAuth wall. Jira ships as an adapter,
   not the assumption.
4. **`org update`** — re-render generated files from `roles.yaml` without
   touching authored content. This is what makes the template-repo model work
   and forks unnecessary.

## Defaults taken, pending your call

Three decisions were open. I have defaulted them so work can proceed; each is
cheap to reverse now and expensive later.

| Decision | Default taken | Why |
|---|---|---|
| Distribution | **Template repo + `org update`** | Forks rot. Six months on, a fork is on v1 of every skill with authored content tangled into the update path. |
| First tracker | **GitHub Issues** | No OAuth wall, works for anyone with a repo. Jira is the second adapter, not the first. |
| Scope | **Packs** — 4-role core, rest opt-in | Shipping fifteen agents to someone who wanted four reads as bloatware. |

## Order of work

1. `roles.yaml` + role templates — **done**
2. Move the seven portable skills and remove identity-specific examples — **done**
3. `setup-my-org`, proven by generating a second org with different packs
   and asking one persona to state its role id and manager
4. Adapter interface + `github-issues`
5. Seed memory
6. `org update`

Step 3's proof is deliberate. A setup skill that prints a success message without
round-tripping through a generated agent has not demonstrated anything — the same
argument `write-a-gate` makes about CI checks.

---

# Second extraction — the guards, 2026-09-02

The first pass moved the **skills**: procedures an agent reads at a decision
point. This one moves the **guards**: files a repo owns and CI executes, plus the
one control that runs *before* the tool call. Six agents built these in the
source product repo over a single day and identified what applies across orgs; every
claim below was verified against the file rather than taken from the report.

Everything landed in `.claude/skills/new-project/seed/tier0/` — the seed, not a
skill — because a guard that lives in an agent's home directory runs only when an
agent chooses to run it, which makes it advice. That distinction is already
`seed/README.md`'s opening argument and nothing here changes it.

## What moved

| Artifact | Where it landed | Adaptation |
|---|---|---|
| `evals/run.sh` + `lib.sh` + 12 of 23 tasks | `seed/tier0/evals/`, split `tasks/core/` (portable) and `tasks/local/` (yours, ships empty) | one `CORPUS_PATHS` line; recursive discovery; incidents re-voiced as another project's |
| `payload.py`, `lib.sh`, `test-all.sh` | `seed/tier0/.claude/hooks/` | near-verbatim; names and ticket keys scrubbed |
| `transcript-evidence.py` | same | verbatim logic, **including the CARRIER exclusion and the comment explaining it** |
| `block-test-weakening.sh` + suite | same | the test-path patterns and assertion vocabulary extracted to `.factory/test-vocabulary.conf` |
| `docs/intent/` README + TEMPLATE | `seed/tier0/docs/intent/` | the spec-of-record reference made document-neutral |
| `tools/sdlc-metrics/` | `tools/sdlc-metrics/` — **org-level, not seeded** | reads GitHub metadata for any `owner/repo`, so it runs from here rather than being vendored 4,000 lines at a time |
| the band + `selfcheck` of `ci-health-band.py` | `tools/control-band/` | same reason; `collect` kept working rather than stubbed |

Two things were **written, not extracted**, because the source had no equivalent:

- **`.claude/settings.json`, shipping with the `hooks` key already populated.**
  This is the single most valuable structural change in the promotion, and the
  reason is a genuine dead end: `settings.json` carries
  `Edit(**/.claude/settings.json)` in `permissions.deny`, that rule is correct,
  and the consequence is that **a hooks layer cannot install itself.** In the
  source repo three finished, tested, correct hooks sat routed to nothing until
  an owner pasted eight lines in by hand. A seeded repo should never reach that
  state. `seed/tier0/.claude/settings.README.md` carries the argument.
- **`.claude/rules/measurement-and-evidence.md`** — the doctrine, in
  `.claude/rules/` beside `untrusted-input.md` rather than in a docs graveyard,
  because the rules directory is what an agent inherits. Declare your subjects ·
  zero is an error · ship the mutation that proves your check can fail · an empty
  search is a broken query until proven otherwise · "could not measure" is never
  "no anomaly" · the exit code reports the measurement, the flag gates the effect
  · the four hook invariants · the dispatcher that creates the concurrency owns
  the interlock · a coordinator instruction is not owner approval · verify prose
  against code.

And `CLAUDE.md.template` fixes the one-page shape: commands **with their healthy
output**, conventions that bite, a short architecture overview,
things-that-get-gotten-wrong. Everything else belongs in a skill. It is a
`.template` so it cannot load with its placeholders still in it — an unfilled
`CLAUDE.md` is worse than none, because an agent reads `<the test command>` as an
instruction it cannot follow and improvises one.

## What was deliberately left out

| Left behind | Why |
|---|---|
| 11 of the 23 eval tasks | Each judged a fact about the source repo: its gate ladder against its own `policy.go`, its PR-body gate's exact behaviour, its `LOOP-MODEL.md` prose. Three that are portable *in shape* but have no subjects in a fresh repo — the interlock task, the cache-defeat task, the honesty-contract task — are described in `evals/tasks/local/README.md` as the first ones to write, rather than shipped to error out on an empty subject set. |
| `require-story-lease.sh` | Tier 3. It keys on a lease script the seed does not ship, and a hook whose subject does not exist is the vacuity this whole promotion is against. |
| `assert-toolchain-present.sh` | Coupled to one project's user-local JDK path and one language's test command. Its *helper* — `transcript-evidence.py` — is the valuable half and came alone. |
| the source's `sdlc-metrics` schedule, artifact upload and Notion sink wiring | A scheduled measurement needs a window, a token scope and an output destination that are the adopting repo's decisions. |
| a scheduled `collect` for the control band | It needs ≥7 days of CI history. Shipping one here produces a job that exits 3 every morning — the failure the detector exists to prevent, reproduced in its own workflow. |

## Two warts carried forward on purpose, with a label

Propagating a known defect unflagged is how it becomes permanent.

1. **`defect_containment_rate` mixes units.** Its numerator counts pull requests
   and its denominator counts issues. In the source that caveat lived only in the
   schema document; here it is emitted **in the metric's own `detail` and
   `definitions` entry**, with a test asserting it survives encode/decode. A
   consumer reading `metrics.json` cannot miss it.
2. **Self-review is counted.** In the source, excluding the author would have
   reported zero — every PR is opened, reviewed and merged under one identity, so
   author identity cannot separate self-review from peer review. That decision
   was deliberately *not* a flag there, because shipping it defaulted wrong is
   worse than absent. A reuse repo cannot make that call for a stranger, so
   `-review-excludes-author` now exists, defaults to the source's behaviour, says
   in its own help text that a repo with human reviewers should turn it on, and
   has a fixture proving the flag actually moves five metrics.

## What the seed's own CI is meant to prove — **not yet wired**

> [!warning] Three workflow changes are NOT in the promotion PR
> The token available to the agent that did this promotion lacks the `workflow`
> scope, so `.github/workflows/gate.yml`, `control-band.yml` and
> `sdlc-metrics.yml` could not be pushed. The full diff is in the PR body for a
> one-paste application by somebody who has that scope. **Until it is applied,
> none of the promoted guards' self-tests run in this repository's CI** — they
> pass locally and that is a weaker claim. Stated here rather than discovered
> later.

Three steps for `gate.yml`, and the second is the one that matters:

- the vendored **hook suites** run (`test-all.sh` refuses an empty sweep);
- the seed is **installed into a scratch repo** and the eval suite is run against
  *that*, not against `seed/tier0` in place — an installed repo is the thing the
  evals judge, and running them against the seed directory would silently measure
  something else. Every subject count comes back non-zero;
- the eval **runner's own vacuity guard is mutated** and the suite is required to
  notice, with the mutation confirmed to have landed before either outcome is
  believed. A break-test whose edit did not apply looks exactly like success.

## The one correction to the first extraction

Nothing above changes the earlier dispositions. It does confirm the warning
already added to the coupling table: **those density figures were a floor, not a
measurement**, because the walk was top-level-only. `new-project` was scored on
its `SKILL.md` while shipping a whole `seed/tier0/` tree, and that tree has now
roughly doubled. Anything re-measured should walk recursively.
