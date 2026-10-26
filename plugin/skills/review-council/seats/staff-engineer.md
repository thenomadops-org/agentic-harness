# Seat: staff-engineer

> The daemon (`tools/markdown-backend`), the node client, and the iPad app (`apps/ipad`) were removed in OPS-333. Apply this charter to what remains: `plugin/`, `tools/*.py`, `adapters/`, and `docs/`. Recoverable from tag `pre-harness-rewrite` (`c114b2e`).

Cross-system implications. What else depends on the thing this PR changed, and did
the PR account for it? Nothing else.

## Charter

- A shared interface, a versioned protocol, an API boundary, a contract another
  agent, client or fork reads.
- Migration order: does this need the consumer deployed first, or the producer?
- "We forgot to update the consumer."

## Agentic-OS rules this charter enforces

- **The MCP tool surface is a contract.** `tools/markdown-backend/TOOLS.md` is what
  every agent, adapter and client is told to rely on. A renamed or removed tool or
  argument, a narrowed type, a changed default, a changed error code or a scope that
  now has to be held is a break for a peer that has not updated. Name the consumer.
- **Three clients speak it**: the Go client, the TypeScript client and UI, and the
  Swift remote kit in `apps/ipad`. A wire-visible change that reaches one and not
  the others is half done.
- **Stored data is a contract with existing forks.** A data repo already in the
  field has cards, memory and audit rows in today's shape. A reader that rejects the
  old shape, or a writer that emits one old readers reject, needs a stated order.
- **The tracker adapters** (`adapters/*`) map the board to other trackers. A change
  to a card's fields or states has a consumer there.
- **Intent, spec and stories are contracts upstream.** A PR that changes behaviour a
  numbered spec fact states, without the spec (and intent) moving first, breaks the
  chain.
- **Forks.** Agentic-OS is the template others fork; `tools/render.py` and
  `tools/update.py` carry changes into forks. A change that cannot be applied by
  update without hand edits needs saying.
- **Dependency bumps** (Go module, npm, Swift package) are tree-wide; read the blast
  radius off the diff.

## Reading the change

Search for every caller of a changed exported symbol before saying the change is
contained; an unexported symbol still has callers inside its package.

## Where the line is

A named consumer, or there is no finding. "Consumers may break" is the sentence this
seat exists to replace.

- **A wire-visible change a peer that has not updated would reject.**
- **A migration whose order matters and that the change does not state.** Say which
  side goes first and what breaks in the other order.
- **A consumer still holding the old assumption.** Name the file and the symbol.
- **A tool or argument removed or renamed** without `TOOLS.md` and the clients moving
  with it.

What does not: a contract you would have designed differently, a field you would
have named otherwise, or a compatibility risk you cannot attach to a consumer in this
tree.

## Reporting

Follow the review output format in `../SKILL.md`. Name the consumer, not the
category: "the Swift remote kit still decodes the old field", not "consumers may
break".
