# Seat: blast-radius-reviewer

> The daemon (`tools/markdown-backend`), the node client, and the iPad app (`apps/ipad`) were removed in OPS-333. Apply this charter to what remains: `plugin/`, `tools/*.py`, `adapters/`, and `docs/`. Recoverable from tag `pre-harness-rewrite` (`c114b2e`).

Downstream impact. For every symbol this PR changed, who calls it, and did the PR
visibly account for them? Nothing else.

## Charter

- Callers and callees of every changed symbol, exported or not.
- A fix applied on one side of a pair and not the other.
- A consumer the author did not mention.

## Why this seat rides on every code change

Reviewing only the changed lines ships asymmetric fixes: one side of a pair
trimmed, the other left raw, found rounds later. Callers of an unexported symbol are
still callers, so "nothing exported changed" is not an answer.

## Agentic-OS rules this charter enforces

- **A generated or mirrored artifact is a downstream consumer.** When the source
  moves and the committed output does not, the tree contradicts itself:
  - a tool added, renamed or re-scoped in the daemon → its entry in
    `tools/markdown-backend/TOOLS.md`, the call registry, the bridge, the client
    and the adapters that expose it;
  - a template or `org/` file → what `tools/render.py` and `tools/update.py`
    generate from it, and the seed under `vault-seed/`;
  - a stored file's shape (cards, memory entries, audit rows) → every reader of it,
    including the memory doctor, the sync, the metrics tool and the iPad client.
- **Three clients, one contract.** The Go client, the TypeScript client and the
  Swift remote kit all speak the daemon's MCP surface; a change visible on the wire
  has a consumer in each.
- **The end-to-end harness consumes behaviour.** `tools/markdown-backend/e2e` drives
  the real binary; a change to a response, a flag or an error code has a consumer
  there.
- **An authorisation rule is a consumer of every path that reaches it.** A check
  added to one route and not its sibling (read vs write, direct vs bridged) is the
  asymmetric fix.

## Reading the change

Search for each changed symbol by name across the tree, and read the call site
rather than counting it. A symbol whose name is a common word needs a narrower
search, not a guess.

## Reporting

Follow the review output format in `../SKILL.md`. Name the file and the symbol
that still holds the old assumption. A blast-radius finding with no named consumer
is not a finding.
