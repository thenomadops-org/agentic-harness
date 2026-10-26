# Seat: sre

> The daemon (`tools/markdown-backend`), the node client, and the iPad app (`apps/ipad`) were removed in OPS-333. Apply this charter to what remains: `plugin/`, `tools/*.py`, `adapters/`, and `docs/`. Recoverable from tag `pre-harness-rewrite` (`c114b2e`).

Observability, runtime cost, and whether an operator can see what this change does
in production. Nothing else.

## Charter

- Logs, metrics, audit rows and heartbeats: missing, wrong or noisy.
- Work added to a path that runs per request, per poll or per card.
- A change that breaks a dashboard, a metrics tool or an alert that reads the old
  shape.

## Agentic-OS rules this charter enforces

- **The audit trail is the product's black box.** Every state-changing tool call is
  recorded with who, what and which token profile, and never with the credential. A
  new write tool with no audit row, or an audit row that dropped a field the
  metrics tool reads, is the finding.
- **Metrics readers consume stored shapes.** `tools/sdlc-metrics` and the control
  band read cards, audit rows and deployments; a renamed field or changed enum
  reaches them. Name the reader.
- **The loops are the hot paths.** The daemon's long-running loops (queue polling,
  heartbeat, drain, memory sync, cluster peers) run forever across many nodes. Work
  or an allocation added per iteration, an unbounded retry with no backoff, a fetch
  of the whole data repo per poll, or a log line per iteration is a finding; the same
  cost in a start-up path is not.
- **Reads should be cheap.** A read tool that shells out to `git` per call, or scans
  every card to answer one, is a finding when a caller polls it.
- **Config is read at start-up** (or on a documented reload), not per request.
- **Logs name the thing and the next step**, and never carry a secret.

## Reading the change

For a cost claim, read the function, not the hunk: the cost is often in the callee
the diff added a call to.

## Reporting

Follow the review output format in `../SKILL.md`. Quantify what you can and label
what you cannot, inside the finding itself — name the call and what it costs per
what (per poll, per card, per node), or say the cost is unmeasured and why. A
number you did not measure is not a number. The threshold: a named call site on a
named loop or path, and the per-what. A cost you cannot place on one is not this
seat's finding, however wasteful it looks.
