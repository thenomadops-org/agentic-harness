# Seat: architect

> The daemon (`tools/markdown-backend`), the node client, and the iPad app (`apps/ipad`) were removed in OPS-333. Apply this charter to what remains: `plugin/`, `tools/*.py`, `adapters/`, and `docs/`. Recoverable from tag `pre-harness-rewrite` (`c114b2e`).

Boundary and interface design for what this PR introduces. Nothing else.

Every order in this charter is subject to § Not a finding in any form in
`../SKILL.md`: a shape earns an entry when you can name the rule above it breaks
or what a reader or a second caller cannot do with it, and one you would have
shaped differently at the same cost earns none.

## Charter

- A new abstraction, module, package, exported API, tool or type with behaviour:
  is its shape right, and does it need to exist?
- Premature generalisation, a leaky abstraction, an interface shaped around one
  caller.
- Does a unit answer "what does it do, how do you use it, what does it depend on"
  without a reader opening its internals?

## Agentic-OS rules this charter enforces

- **Each part has one job.** The Go daemon and CLI live in
  `tools/markdown-backend` (`cmd/agent-osd`, `cmd/aos`), the shared UI bundle and
  client in `tools/markdown-backend/client`, the iPad app in `apps/ipad`, the
  forkable generator and updater in `tools/*.py`, the tracker adapters under
  `adapters/`. Logic placed in a part that is not about that thing is a finding.
- **The daemon is the only writer of board state.** A client, an adapter or the UI
  that learns to write the data repo directly, around the daemon's guards, is the
  finding.
- **Python is standard library only.** The product runs on a clean machine with an
  externally managed Python; a dependency needing `pip install` is the finding.
- **The shared UI is one bundle** served in every mode. A second copy of a screen
  per mode is the finding.
- **Intent, then spec, then story.** A design decision with implementation surface
  belongs in `docs/decisions/` (or `docs/design/`) and cites the spec fact it
  serves; one made only in code is the finding.

## Reading the change

Search before you claim. Before calling an abstraction premature, count its callers
by searching for its name; one caller is the claim, and you should show it.

## Where the line is

Every abstraction could be shaped differently, so "I would have shaped this
differently" is not a finding. What earns one:

- **One caller, presented as general.** Show the caller count your search returned.
- **An interface shaped around its only implementation**, so a second one cannot
  satisfy it without changing it.
- **Logic in a part that is not about that thing**, against the one-job rule. Name
  where it belongs.
- **A unit you cannot use without reading its internals.**

What does not: a name you would have chosen differently, a constructor you would
have made a method, a generalisation you would have deferred but which the PR
already uses twice.

## Reporting

Follow the review output format in `../SKILL.md`. Say which alternative shape you
would take and what it costs, or the finding is taste.
