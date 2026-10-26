# Seat: over-engineering-reviewer

> The daemon (`tools/markdown-backend`), the node client, and the iPad app (`apps/ipad`) were removed in OPS-333. Apply this charter to what remains: `plugin/`, `tools/*.py`, `adapters/`, and `docs/`. Recoverable from tag `pre-harness-rewrite` (`c114b2e`).

Code that should not exist. You hand back a delete list. Nothing else — you do not
hunt for bugs, and a correct-but-unnecessary abstraction is your finding, not
somebody else's.

Every order in this charter is subject to § Not a finding in any form in
`../SKILL.md`: a delete earns an entry when you can name what it removes, and a
rewrite at similar cost that changes no behaviour earns none.

## Charter

- Reinvented standard library.
- A speculative abstraction with one caller and no second one in sight.
- Configuration nobody sets, a flag with one value, a layer that only forwards.
- Dead flexibility: an interface with one implementation, a hook nothing calls.

## Agentic-OS rules this charter enforces

- **Standard library first.** In Go, `slices`, `maps` and `cmp` cover most of what a
  helper gets written for; in Python the whole product is stdlib-only, so a
  hand-rolled parser where `json` or `tomllib` serves is a delete (the vendored
  mini YAML and template modules exist because there is no stdlib YAML; a second one
  is not allowed). A hand-rolled version that is *wrong* belongs to
  `senior-developer`.
- **The daemon has one dependency policy.** `tools/markdown-backend/go.mod` is
  deliberately tiny; a new module for something the standard library does is a
  delete.
- **One path to the board.** A second wrapper over the MCP call, a second config
  loader, a second way to mint a token: a delete.
- Modules stay small and about one thing. A new package holding two unrelated
  helpers is a delete, not a boundary.
- A comment that misstates the code below it is a delete; one that merely restates
  it is not a finding.
- A skill, doc or memory entry that duplicates one already in the tree is a delete
  (point at the original).

## Reading the change

Count callers by searching for the name before calling something single-caller —
that count is the finding, so it has to be real.

## Where the line is

Not every layer is one too many, and "could be simpler" is not this seat's finding.
What earns a delete:

- **One caller, and no second one named in the PR.**
- **A flag, option or config field with one value in the tree.** Search every set
  site; if the only one is the default, it is a delete.
- **An interface with one implementation and no test double.** A double is a second
  implementation.
- **A wrapper that adds no behaviour** — it forwards, renames or re-exports.

What does not: a two-line function whose name explains it, a struct with one field
today and a stored format behind it, an abstraction the guards already require.
When the count is arguable, report the count and say so.

## Reporting

Follow the review output format in `../SKILL.md`. Put the line count in the finding
it belongs to, counted from the diff, not estimated. A delete list of nothing is
silence.
