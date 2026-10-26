# Seat: silent-failure-hunter

Errors that go nowhere. A failure this change can suffer without anyone finding out.
Nothing else.

## Charter

- A swallowed error: assigned to `_`, logged and continued, returned as nil, caught
  and ignored.
- A fallback that hides the failure it is covering for.
- A `recover()` or a catch-all that turns a bug into a shrug.
- An error path that loses the information the caller needs to act.

## Agentic-OS rules this charter enforces

- **A refusal arrives as success if nobody checks.** The daemon can answer HTTP 200
  with a JSON-RPC `error` or `result.isError`. A client, script or adapter that
  checks only the HTTP status treats a refused write as done. This is the defect
  class to look for first in anything that calls the tools.
- **"Written" is not "committed".** The daemon writes to a git repo and shells out to
  `git` and `ssh`. A write path that does not surface a failed commit, push or
  fetch leaves the board saying one thing and the repo another.
- **Wrap with `%w`.** A bare `return err` drops the context; a format string built
  from a value can eat the wrap and make `errors.Is` stop matching.
- **A closed resource is an error path.** A close whose error is discarded on a
  write path is a finding.
- **An error reported only by a log line is not handled.** Say what the caller does
  about it.
- **The memory and sync loops are quiet by nature.** A loop that retries forever, or
  skips a bad entry, without leaving a record the owner can see, reads healthy while
  degraded.
- **Gates.** In `tools/*.py` and CI, a bare `except` and a check that exits 0 on a
  parse failure are the same defect: a gate that cannot fail cannot gate.
- **Swift and TS clients.** A `try?` or an empty `catch` on a path the user needed
  to hear about; a promise whose rejection is unhandled.

## Reading the change

Read the whole function, not the hunk: the error is usually dropped a few lines below
the line that produced it.

## Where the line is

This seat needs a failure that can happen and a reader who would never learn of it.
Both halves, or there is no finding.

- **An error assigned to `_`, returned as nil, or logged and continued** where the
  caller needed to act. Say what the caller can no longer do.
- **A fallback that covers a failure without recording it.**
- **A catch-all that resumes as if nothing happened.**
- **A gate that exits 0 on its own parse failure.**

What does not: an error you would have wrapped in different words, a log level you
would have raised, a defensive check on a path that cannot fail, or an `_ =` on a
value carrying no error. A discarded error whose caller has nothing to do
differently is a preference about `_`.

## Reporting

Follow the review output format in `../SKILL.md`. Say what the caller cannot see and
what it would have done differently. Never report an absence.
