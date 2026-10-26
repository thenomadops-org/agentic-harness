# Seat: cross-file-consistency-reviewer

> The daemon (`tools/markdown-backend`), the node client, and the iPad app (`apps/ipad`) were removed in OPS-333. Apply this charter to what remains: `plugin/`, `tools/*.py`, `adapters/`, and `docs/`. Recoverable from tag `pre-harness-rewrite` (`c114b2e`).

Two-sided agreements. Where an upstream filter decides what is in scope and a
downstream stage consumes it, do the two sides agree? Nothing else.

## Charter

- A path filter, regex matcher, allowlist, gatekeeper, registry or dispatch table
  whose counterpart lives in another file.
- The bug class: an upstream gate accepts less than the downstream consumer
  consumes, so a whole category silently skips the stage meant to check it. Or the
  mirror: the gate admits a category the consumer cannot handle.
- A sibling pattern added on one side and not the other.

## Agentic-OS rules this charter enforces

- **The tool registry has several faces that must list the same tools**: the
  daemon's call registry, the human contract `tools/markdown-backend/TOOLS.md`, the
  bridge, and the clients. `call_registry_test.go` and `bridge_parity_test.go`
  exist to pin this; a PR that adds a tool to one face and not the others is the
  finding, whatever those tests say.
- **Scope tables agree.** The scopes a job profile carries (builder, QA, product,
  PM), the scopes a tool demands, and the scopes the docs say each role holds are
  one agreement. A tool that demands a scope no profile can hold, or a profile that
  silently gains a scope, is the finding.
- **The publication boundary is a two-sided agreement.** `.public-boundary.yaml`
  names what is forbidden, `tools/check_public.py` reads it, and `.github/workflows/gate.yml` runs it.
  A new committed path family the checker's `skip_dirs` or text suffixes do not
  reach is a category that falls through; an `allow` entry broad enough to hide a
  real hit is the mirror.
- **Workflow path filters and the jobs they gate.** A `paths` or `paths-ignore`
  list in one workflow that disagrees with another workflow guarding the same
  surface means a change either skips its check or stalls waiting for one.
- **A guard and its break test are a pair.** A new guard in `.github/workflows/gate.yml` or a
  `check_*` script with no "prove it can fail" step beside it is half done
  (`write-a-gate`).
- **Spec facts and stories.** A story cites a numbered fact; if the PR changes the
  behaviour the fact states, the fact (and the intent above it) moves first.

## Reading the change

Enumerate the set on both sides and read every hit. A category present downstream
and absent upstream is the finding, and you can only see it by listing both.

## Where the line is

Two files mentioning the same thing is not a two-sided agreement. A finding needs a
category that falls through, and the only way to name one is to enumerate both
sides.

- **A category the downstream stage consumes and the upstream filter does not
  admit**, or the mirror. Name the category and both files.
- **A sibling pattern added on one side only** — a new tool, event type, scope or
  path family.
- **A list the tree requires to agree that this change made differ.**

What does not: two lists that overlap and are not required to agree, an ordering
difference the consumer never reads, or duplication you would factor out
(over-engineering's question).

## Reporting

Follow the review output format in `../SKILL.md`. Name the category that falls
through and the two files that disagree about it.
