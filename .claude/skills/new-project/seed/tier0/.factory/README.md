<!-- from factory-seed@UNSTAMPED -->

# `.factory/` — this repo's gate configuration

**Everything in this directory is per-repo config. None of it is vendored.**

That distinction is the one that keeps a factory from rotting. The gates are
copied in from the seed and are the same everywhere; the numbers, lists and
prefixes they read are this repository's measured reality and are the same
nowhere. Vendoring one repo's floors, allowlists or ticket prefixes into another
is how a ratchet becomes a decoration — and worse, it teaches the first author
who reads it that seed files are wrong by default, after which every seed file is
negotiable.

Because these files configure gates, they are on the read-only list in
[`../docs/AGENT-GUARDRAILS.md`](../docs/AGENT-GUARDRAILS.md). If one of them is
the thing standing between you and a green build, **the gate is working** — stop
and escalate with a named question.

---

## `MANIFEST` — what was vendored, and from where

One line per vendored file:

```
<seed-sha>  <repo-relative path>
```

Written by the install and checked on every PR by
`scripts/factory-provenance-check.sh`. A file listed here that is missing from
the tree is a **deleted gate**, which is the loudest possible drift and, without
this check, the quietest failure: nothing runs, nothing fails, nothing is
reported.

## `ticket-prefixes` — which ticket keys satisfy the PR contract

One uppercase prefix per line, `#` comments allowed:

```
# Tracker project keys that authorise work in this repo
ACME
OPS
```

Read by `scripts/dod-check.sh`. The prefixes are interpolated into a regular
expression, so anything that is not `^[A-Z][A-Z0-9]*$` is refused rather than
escaped — a `.*` that slipped in here would make the ticket rule match every
body, silently, and green.

**A missing or empty file is exit 2, not a pass.** A checker that skips a rule
because its config went missing is the exact defect it exists to catch.

## `allowed-runners` — which runner label sets CI jobs may name

One allowed set per line, labels comma-separated. Order does not matter; the
comparison is on the set:

```
ubuntu-24.04
self-hosted,Linux,X64
```

Read by `scripts/runner-pinning-check.sh`. A bare `self-hosted` or a partial
label set lets the platform choose the machine, and it chooses a different one on
different days — on one project's runner fleet a Go job could land on a macOS arm64 laptop.
A moving label like `ubuntu-latest` is the same bug with a slower fuse: green
today, red on the morning the label rolls forward, in a PR that changed nothing.

**Pin the version.** `ubuntu-24.04`, not `ubuntu-latest`.

---

## Adding a gate later

A new gate's config file goes here, gets a row in the read-only table in
`AGENT-GUARDRAILS.md`, and — if it is an escape hatch of any kind — ships
**bounded**: a cap, a no-zero rule, and a high-water mark measured from somewhere
the author cannot edit in the same PR. A written justification is friction, not a
limit. One project's first coverage ratchet required a reason string and nothing
else, so a floor could be zeroed by one line with a one-character reason.
